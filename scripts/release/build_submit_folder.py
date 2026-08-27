"""Assemble one folder that holds everything the portal upload needs.

This script used to copy from `build/submission/emse_portal_staging/`, which is
written by a separate packaging step. When that step had not been re-run, the
folder silently filled with an older draft: on 2026-08-27 it held a 22-page
manuscript and a 46-page appendix from the previous day. Uploading it would have
submitted the wrong paper, and nothing in the output said so.

So it now builds from the compiled PDFs directly, and refuses to write anything
if a PDF is older than a source file it is built from. A stale submission folder
is worse than no submission folder, because it looks finished.
"""

from __future__ import annotations

import hashlib
import pathlib
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANUSCRIPT = ROOT / "paper" / "manuscript"
SUBMIT = ROOT / "SUBMIT"

# Everything needed to compile main.tex, and nothing else. The portal wants a
# flat archive for the article alone; the appendix ships as a rendered PDF.
SOURCE_FILES = (
    "main.tex",
    "references.bib",
    "sn-jnl.cls",
    "sn-basic.bst",
)


def figure_files() -> list[str]:
    return sorted(path.name for path in MANUSCRIPT.glob("Fig[0-9].pdf"))


def staleness_report() -> list[str]:
    """Name every PDF that is older than something it is built from."""
    problems: list[str] = []

    figures = [MANUSCRIPT / name for name in figure_files()]
    appendix_inputs = sorted(MANUSCRIPT.glob("apx_tables_*.tex")) + [
        MANUSCRIPT / "generated_appendix_tables.tex",
        MANUSCRIPT / "technical_appendix.tex",
    ]

    checks = (
        (
            MANUSCRIPT / "main.pdf",
            [MANUSCRIPT / "main.tex", MANUSCRIPT / "references.bib", *figures],
        ),
        (
            MANUSCRIPT / "technical_appendix.pdf",
            [path for path in appendix_inputs if path.exists()],
        ),
    )

    for pdf, inputs in checks:
        if not pdf.is_file():
            problems.append(f"{pdf.relative_to(ROOT)} has not been compiled")
            continue
        built = pdf.stat().st_mtime
        for source in inputs:
            if source.stat().st_mtime > built:
                problems.append(
                    f"{pdf.relative_to(ROOT)} is older than "
                    f"{source.relative_to(ROOT)}"
                )
    return problems


def build_source_archive(destination: pathlib.Path) -> list[str]:
    names = list(SOURCE_FILES) + figure_files()
    missing = [name for name in names if not (MANUSCRIPT / name).is_file()]
    if missing:
        raise SystemExit(f"Cannot build the source archive; missing: {missing}")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(MANUSCRIPT / name, arcname=name)
    return names


def main() -> None:
    problems = staleness_report()
    if problems:
        print("REFUSING to build SUBMIT/. Recompile first:")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nRun pdflatex twice on main.tex and technical_appendix.tex, then "
            "run this again."
        )
        sys.exit(1)

    if SUBMIT.exists():
        shutil.rmtree(SUBMIT)
    SUBMIT.mkdir()

    shutil.copy2(MANUSCRIPT / "main.pdf", SUBMIT / "1_manuscript.pdf")
    shutil.copy2(
        MANUSCRIPT / "technical_appendix.pdf", SUBMIT / "2_online_resource_1.pdf"
    )
    archived = build_source_archive(SUBMIT / "3_manuscript_source.zip")

    documents = (
        (ROOT / "paper" / "COVER_LETTER.md", "4_cover_letter.md"),
        (ROOT / "paper" / "SUBMISSION_METADATA_FORM.md", "5_metadata_form.md"),
        (ROOT / "paper" / "SUBMISSION_READINESS.md", "6_readiness_checklist.md"),
        (ROOT / "paper" / "VENUE_CHECKLIST.md", "7_venue_checklist.md"),
    )
    missing = []
    for source, name in documents:
        if source.is_file():
            shutil.copy2(source, SUBMIT / name)
        else:
            missing.append(str(source.relative_to(ROOT)))

    # Written with explicit newlines so `sha256sum -c` works on every platform;
    # the default on Windows produced CRLF, which sha256sum rejects.
    digests = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(SUBMIT.iterdir())
    ]
    (SUBMIT / "CHECKSUMS.sha256").write_text(
        "\n".join(digests) + "\n", encoding="utf-8", newline="\n"
    )

    readme = f"""# SUBMIT — everything the Editorial Manager upload needs

Built from the compiled PDFs in `paper/manuscript/`. This folder is regenerated,
never edited by hand, and the builder refuses to run if a PDF is older than a
source file it is built from.

| File | What it is | Where it goes in Editorial Manager |
|---|---|---|
| `1_manuscript.pdf` | The article | Manuscript |
| `2_online_resource_1.pdf` | Supplementary Information | Online Resource 1 |
| `3_manuscript_source.zip` | Flat LaTeX source for the article: {", ".join(f"`{name}`" for name in archived)} | Source files |
| `4_cover_letter.md` | Cover letter | Cover letter |
| `5_metadata_form.md` | Title, authors, abstract, keywords, declarations | Typed into the portal |
| `6_readiness_checklist.md` | What is done and what is still open | Not uploaded |
| `7_venue_checklist.md` | The venue's stated requirements | Not uploaded |
| `CHECKSUMS.sha256` | Integrity record; verify with `sha256sum -c` | Not uploaded |

Before uploading, fill in every placeholder the deposit guide lists in
`docs/guides/ARTIFACT_DEPOSIT.md`: author affiliations, ORCIDs, the
corresponding email, and the reserved artifact DOI.
"""
    (SUBMIT / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    print("SUBMIT/ contains:")
    for path in sorted(SUBMIT.iterdir()):
        print(f"  {path.stat().st_size / 1024:9.1f} KB  {path.name}")
    if missing:
        print("\nMissing, so not included:")
        for name in missing:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
