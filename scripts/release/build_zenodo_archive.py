"""Assemble and verify the archive that goes to Zenodo.

Companion to `build_submit_folder.py`. That one packages the manuscript for the
Editorial Manager upload; this one packages the reproducible artifact for the
archival deposit that the manuscript cites.

The never-publish rules are read out of `.gitignore` rather than restated here,
so the two cannot drift apart. If any of those paths survives into the built
zip, the script refuses and exits non-zero instead of writing a deposit that
de-blinds the human-coding audits.

    python scripts/release/build_zenodo_archive.py
    python scripts/release/build_zenodo_archive.py --self-test
"""

import argparse
import csv
import hashlib
import pathlib
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "build" / "zenodo"
ARCHIVE_STEM = "emse2026-multiagent-impact-artifact"

# The banner that opens the never-publish block in .gitignore. The block runs
# to the end of the file or to the next dashed banner.
NEVER_PUBLISH_BANNER = "NEVER PUBLISH"
BANNER_RULE = re.compile(r"^#\s*-{5,}\s*$")

# Every rule the block is expected to carry. If .gitignore loses one of these,
# the build refuses rather than quietly shipping a weaker guarantee.
REQUIRED_NEVER_PUBLISH = (
    "outputs/**/private/",
    "outputs/**/private_record_key.csv",
    "outputs/**/private_sampling_key.csv",
    "outputs/**/audit_key_do_not_share_before_coding.csv",
    "outputs/**/*_answer_key.csv",
    "docs/audits/AUTHOR_METADATA_AUDIT_*.md",
    "outputs/_exploration/",
    "SUBMIT/",
)

# The AIDev release is third-party data under its own terms with its own home.
# The archive records the pinned revision instead of redistributing the parquet.
THIRD_PARTY_DATA = (
    "external_data/",
    "**/AIDev-7.6M/",
)

# What goes in. Directories are walked; files are taken as they are.
INCLUDE_DIRS = (
    "src",            # shared library
    "scripts",        # analysis, figure, reporting, validation, release code
    "tests",          # pytest suite
    "protocol",       # reproduction contract: disposition ledger, schemas
    "docs",           # guides, decisions, audits
    "outputs",        # derived artifacts the tables and figures are built from
)
INCLUDE_FILES = (
    "README.md",
    "REPRODUCE.md",   # standalone run instructions for someone who has only this zip
    "CITATION.cff",
    "LICENSE",
    "NOTICE.md",
    ".zenodo.json",
    "pyproject.toml",
    "uv.lock",
)

# Not secret, just not part of the deposit: build noise, regenerable caches, and
# the previous study's results, which feed nothing in this paper.
NOT_DEPOSITED = (
    "**/__pycache__/",
    "**/*.pyc",
    "**/.ipynb_checkpoints/",
    "**/.DS_Store",
    "outputs/cache/",
    "outputs/_superseded/",
    "scripts/_superseded/",
    "scripts/_exploration/",   # figure/analysis scratch; the mirror of outputs/_exploration/
    "scripts/__pycache__/",
    # Exploration that ended up in scripts/analysis/ by name rather than by
    # folder. Nothing in the paper reads their outputs.
    "scripts/analysis/run_exploration.py",
    "scripts/analysis/run_cross_agent_review_exploration.py",
    # Our own deliberation, which is not artifact material. These record which
    # paper to write and where to send it: unfinished story candidates, the
    # history of directions tried and dropped, competitive novelty positioning,
    # and venue strategy. Several are superseded and now contradict the
    # manuscript, so publishing them would teach a reader something false.
    # What a reproducer actually needs is kept: docs/guides/ carries the human
    # coding protocols and the dataset guide, and docs/audits/ carries the
    # validation report and the provenance of every external dataset, which is
    # where the third-party licence position lives.
    "docs/notes/",
    "docs/decisions/",
    # Same category, sitting in other folders. The novelty audit is
    # positioning about other people's papers; RESEARCH_BRIEF still carries an
    # abandoned working title, so it contradicts the manuscript; the packaging
    # smoke test certifies a build from two weeks ago.
    "docs/audits/FRONTIER_NOVELTY_AUDIT_*.md",
    "docs/audits/CLEAN_BUNDLE_SMOKE_TEST_*.md",
    "docs/guides/RESEARCH_BRIEF.md",
    "docs/guides/ARTIFACT_DEPOSIT.md",
)


def gitignore_to_regex(pattern):
    """Translate one gitignore path pattern into an anchored regex."""
    dir_only = pattern.endswith("/")
    body = pattern.strip("/")
    parts = []
    segments = body.split("/")
    for index, segment in enumerate(segments):
        if segment == "**":
            parts.append("(?:[^/]+/)*")
            continue
        rendered = ""
        for char in segment:
            if char == "*":
                rendered += "[^/]*"
            elif char == "?":
                rendered += "[^/]"
            else:
                rendered += re.escape(char)
        parts.append(rendered)
        if index != len(segments) - 1:
            parts.append("/")
    # A directory rule covers everything beneath it; a file rule that happens to
    # name a directory behaves the same way in git, so the tail is shared.
    del dir_only
    return re.compile("^" + "".join(parts) + "(?:/.*)?$")


def compile_matchers(patterns):
    return [(pattern, gitignore_to_regex(pattern)) for pattern in patterns]


def first_match(rel_posix, matchers):
    for pattern, regex in matchers:
        if regex.match(rel_posix):
            return pattern
    return None


def read_never_publish_block(gitignore_path):
    """Read the never-publish rules out of .gitignore. Never hardcode them."""
    lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.lstrip("#").strip().startswith(NEVER_PUBLISH_BANNER):
            start = index + 1
            break
    if start is None:
        raise SystemExit(
            f"REFUSING: no '{NEVER_PUBLISH_BANNER}' block found in "
            f"{gitignore_path}. The exclusion contract cannot be verified."
        )
    patterns = []
    for line in lines[start:]:
        # The banner is closed by a second dashed rule. Only a dashed rule that
        # comes after the rules themselves opens a new, unrelated section.
        if BANNER_RULE.match(line) and patterns:
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    missing = [rule for rule in REQUIRED_NEVER_PUBLISH if rule not in patterns]
    if missing:
        raise SystemExit(
            "REFUSING: the .gitignore never-publish block no longer carries "
            "these rules:\n  " + "\n  ".join(missing)
        )
    return patterns


def read_dataset_revision(pipeline_path):
    """Read the pinned AIDev revision from the code, not from memory."""
    text = pipeline_path.read_text(encoding="utf-8")
    match = re.search(r'DATASET_REVISION\s*=\s*"([0-9a-f]{40})"', text)
    if not match:
        raise SystemExit(
            f"REFUSING: could not read DATASET_REVISION from {pipeline_path}. "
            "The archive must record the pinned revision it was built against."
        )
    return match.group(1)


def collect_candidates():
    seen = set()
    candidates = []
    for name in INCLUDE_FILES:
        path = ROOT / name
        if path.is_file() and name not in seen:
            seen.add(name)
            candidates.append(path)
    for name in INCLUDE_DIRS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            candidates.append(path)
    return candidates


def sha256_of(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(archive_path, never_publish_matchers, third_party_matchers):
    """Re-read the built zip and report any path that must never ship."""
    violations = []
    prefix = ARCHIVE_STEM + "/"
    with zipfile.ZipFile(archive_path) as bundle:
        for name in bundle.namelist():
            rel = name[len(prefix):] if name.startswith(prefix) else name
            hit = first_match(rel, never_publish_matchers) or first_match(
                rel, third_party_matchers
            )
            if hit:
                violations.append((rel, hit))
    return violations


def archive_notes(revision, never_publish, blocked_count):
    return f"""# What is in this archive, and what is not

This is the reproducible analysis artifact for the paper *Participation Is Not
Collaboration: When One LLM Coding Agent Reviews Another on GitHub, a
Person Answers*.
It was assembled by `scripts/release/build_zenodo_archive.py`, which also
verified the exclusions below against the built zip.

## Included

| Path | What it is |
|---|---|
| `src/` | Shared analysis library |
| `scripts/` | Analysis, figure, reporting, validation, and release code |
| `tests/` | The pytest suite |
| `protocol/` | Reproduction contract: experiment disposition ledger, label schemas, acquisition manifests |
| `docs/` | The reproduction guides and protocols, and the validation and data-provenance audits. Internal design notes and venue decisions are not deposited. |
| `outputs/` | The derived analysis products the manuscript tables and figures are built from |
| `REPRODUCE.md` | Standalone instructions: get the data, install, run, and read the outputs |
| `README.md` | Study summary, headline findings, and run order |
| `CITATION.cff`, `LICENSE`, `NOTICE.md`, `.zenodo.json` | Citation and licence metadata |
| `pyproject.toml`, `uv.lock` | Pinned Python environment |
| `MANIFEST.csv`, `SHA256SUMS` | Integrity record for every file above |

## The source data is not included

The study reads the AIDev release. It is third-party data under its own terms
and has its own home; this archive does not redistribute it.

- Dataset: `hao-li/AIDev-7.6M`
- Pinned revision: `{revision}`
- Fetch: <https://huggingface.co/datasets/hao-li/AIDev-7.6M/tree/{revision}>

Point the analysis at your copy with the `AIDEV_DATA_DIR` environment variable,
or place it at the default path documented in `README.md`.

## Excluded, and checked

The build read these rules out of the `NEVER PUBLISH` block of `.gitignore` and
verified that no file in the zip matches any of them. {blocked_count} file(s)
present in the working tree matched and were withheld.

{chr(10).join("- `" + rule + "`" for rule in never_publish)}

These paths hold the private coder keys and answer keys for the blinded
human-coding audits, the author-metadata audit, ad-hoc exploration scratch, and
the submission-portal staging folder. Regenerable caches
(`outputs/cache/`), ad-hoc script scratch (`scripts/_exploration/`), and the
superseded prior study (`outputs/_superseded/`, `scripts/_superseded/`) are also
left out; none of it feeds this paper.

## Licence scope

See `NOTICE.md`. The MIT licence in `LICENSE` covers the code, the build
scripts, and the derived analysis products. It does not cover the AIDev release,
the other third-party datasets recorded in `docs/audits/`, or the manuscript.
"""


def self_test(never_publish_matchers, third_party_matchers):
    """Prove the refusal path fires, without touching the filesystem."""
    should_block = [
        "outputs/review_collision/private/private_record_key.csv",
        "outputs/review_collision/private/strict_collision_population.parquet",
        "outputs/feedback_response_audit/private_record_key.csv",
        "outputs/task_label_validation/private_sampling_key.csv",
        "outputs/human_audit/audit_key_do_not_share_before_coding.csv",
        "outputs/human_audit/round1_answer_key.csv",
        "docs/audits/AUTHOR_METADATA_AUDIT_20260826.md",
        "outputs/_exploration/scratch.csv",
        "SUBMIT/1_manuscript.pdf",
    ]
    should_pass = [
        "outputs/coordination_topology/exact_edge_funnel.csv",
        "outputs/human_audit/round1_public_packet.csv",
        "docs/audits/VALIDATION_REPORT.md",
        "docs/guides/DATASET_GUIDE.md",
        "src/multiagent_impact/pipeline.py",
        "scripts/analysis/run_merge_curves.py",
        "outputs/tables/agent_counts.csv",
        "README.md",
        "REPRODUCE.md",
    ]
    third_party = [
        "external_data/downloads/aidev.parquet",
        "external_data/source_repositories/AIDev-7.6M/pull_request.parquet",
    ]
    failures = []
    for rel in should_block:
        hit = first_match(rel, never_publish_matchers)
        status = "BLOCKED by " + hit if hit else "NOT BLOCKED"
        print(f"  {'ok ' if hit else 'FAIL'} {rel}  ->  {status}")
        if not hit:
            failures.append(rel)
    print()
    for rel in should_pass:
        hit = first_match(rel, never_publish_matchers)
        status = "BLOCKED by " + hit if hit else "included"
        print(f"  {'FAIL' if hit else 'ok '} {rel}  ->  {status}")
        if hit:
            failures.append(rel)
    print()
    for rel in third_party:
        hit = first_match(rel, third_party_matchers)
        status = "BLOCKED by " + hit if hit else "NOT BLOCKED"
        print(f"  {'ok ' if hit else 'FAIL'} {rel}  ->  {status}")
        if not hit:
            failures.append(rel)
    print()
    # Exercise the whole refusal path, not just the matcher. A throwaway zip in
    # a temp directory gets a decoy entry name that matches a never-publish
    # rule; nothing private is created and nothing in the repository is touched.
    decoy = "outputs/human_audit/decoy_answer_key.csv"
    with tempfile.TemporaryDirectory() as scratch:
        probe = pathlib.Path(scratch) / "probe.zip"
        with zipfile.ZipFile(probe, "w") as bundle:
            bundle.writestr(f"{ARCHIVE_STEM}/README.md", "not a real archive\n")
            bundle.writestr(f"{ARCHIVE_STEM}/{decoy}", "")
        violations = verify_archive(probe, never_publish_matchers, third_party_matchers)
    if violations == [(decoy, "outputs/**/*_answer_key.csv")]:
        print(f"  ok   a zip containing {decoy}")
        print(f"       is refused by verify_archive() as {violations[0][1]}")
    else:
        print(f"  FAIL verify_archive() did not refuse a zip containing {decoy}")
        print(f"       it reported: {violations}")
        failures.append(decoy)
    print()

    if failures:
        print("SELF-TEST FAILED. The exclusion check does not behave as stated:")
        for rel in failures:
            print("  ", rel)
        return 1
    print("SELF-TEST PASSED: every never-publish and third-party path is refused,")
    print("a built zip carrying one is rejected outright, and no legitimate")
    print("artifact path is caught by mistake.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=str(OUT_DIR),
        help="Directory to write the archive, manifest, and checksums into.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Check the exclusion rules against synthetic paths and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be included and withheld; write nothing.",
    )
    args = parser.parse_args()

    never_publish = read_never_publish_block(ROOT / ".gitignore")
    never_publish_matchers = compile_matchers(never_publish)
    third_party_matchers = compile_matchers(THIRD_PARTY_DATA)
    not_deposited_matchers = compile_matchers(NOT_DEPOSITED)

    if args.self_test:
        print(f"Never-publish rules read from {ROOT / '.gitignore'}:")
        for rule in never_publish:
            print("  ", rule)
        print()
        return self_test(never_publish_matchers, third_party_matchers)

    revision = read_dataset_revision(ROOT / "src" / "multiagent_impact" / "pipeline.py")

    selected = []
    blocked = []
    skipped = []
    for path in collect_candidates():
        rel = path.relative_to(ROOT).as_posix()
        hit = first_match(rel, never_publish_matchers)
        if hit:
            blocked.append((rel, hit))
            continue
        hit = first_match(rel, third_party_matchers)
        if hit:
            blocked.append((rel, hit))
            continue
        if first_match(rel, not_deposited_matchers):
            skipped.append(rel)
            continue
        selected.append(path)

    if args.dry_run:
        total = sum(path.stat().st_size for path in selected)
        print(f"Would include {len(selected)} file(s), {total / 1048576:.1f} MB.")
        print(f"Would withhold {len(blocked)} never-publish/third-party file(s):")
        for rel, hit in blocked:
            print(f"   {rel}   [{hit}]")
        print(f"Would leave out {len(skipped)} build-noise/superseded file(s).")
        return 0

    out_dir = pathlib.Path(args.out)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    rows = []
    for path in selected:
        rel = path.relative_to(ROOT).as_posix()
        rows.append((rel, path.stat().st_size, sha256_of(path)))
    rows.sort()

    manifest = out_dir / "MANIFEST.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "bytes", "sha256"])
        writer.writerows(rows)

    sums = out_dir / "SHA256SUMS"
    sums.write_text(
        "\n".join(f"{digest}  {rel}" for rel, _, digest in rows) + "\n",
        encoding="utf-8",
    )

    notes = out_dir / "ARCHIVE_CONTENTS.md"
    notes.write_text(
        archive_notes(revision, never_publish, len(blocked)), encoding="utf-8"
    )

    archive = out_dir / f"{ARCHIVE_STEM}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in selected:
            rel = path.relative_to(ROOT).as_posix()
            bundle.write(path, f"{ARCHIVE_STEM}/{rel}")
        for extra in (notes, manifest, sums):
            bundle.write(extra, f"{ARCHIVE_STEM}/{extra.name}")

    # Verify the thing that actually ships, not the intent behind it.
    violations = verify_archive(archive, never_publish_matchers, third_party_matchers)
    if violations:
        print("REFUSING TO SHIP THIS ARCHIVE.")
        print(
            "A path covered by the NEVER PUBLISH block of .gitignore, or by the "
            "third-party data rules, reached the built zip:"
        )
        for rel, hit in violations:
            print(f"   {rel}   [matched {hit}]")
        print(f"\nThe unsafe archive is at {archive}. Delete it and fix the")
        print("include rules in this script before depositing anything.")
        return 1

    total_bytes = sum(size for _, size, _ in rows)
    print(f"Zenodo archive written to {out_dir}")
    print(f"  {archive.stat().st_size / 1048576:9.1f} MB  {archive.name}")
    print(f"  {manifest.stat().st_size / 1024:9.1f} KB  {manifest.name}")
    print(f"  {sums.stat().st_size / 1024:9.1f} KB  {sums.name}")
    print(f"  {notes.stat().st_size / 1024:9.1f} KB  {notes.name}")
    print()
    print(f"Files in archive: {len(rows)} ({total_bytes / 1048576:.1f} MB uncompressed)")
    print(f"AIDev revision recorded (not redistributed): {revision}")
    print()
    print(f"Withheld by the NEVER PUBLISH / third-party rules: {len(blocked)}")
    for rel, hit in blocked:
        print(f"   {rel}   [{hit}]")
    print(f"Left out as build noise or superseded: {len(skipped)}")
    print()
    print("Exclusion check passed: no withheld path appears in the built zip.")
    print("Before depositing, fill in the placeholders listed in")
    print("docs/guides/ARTIFACT_DEPOSIT.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
