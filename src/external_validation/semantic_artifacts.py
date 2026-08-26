"""Deterministic, aggregate-only profiles for two semantic evidence sources.

The profiler never emits comment text.  It distinguishes a released analysis
row from its underlying public GitHub comment because some file-level rows are
fragments split from one issue comment.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ZENODO_RECORD = "https://zenodo.org/records/19562450"
ZENODO_DOI = "10.5281/zenodo.19562450"
ZENODO_EXPECTED_MD5 = "93cabf0873330f4d75d570d5bf5f31b0"
ZENODO_LICENSE = "CC-BY-4.0"

_ZIP_ROOT = "AIReviewActionAnalysis(Zenodo)/"
_ANALYSIS_INPUT = _ZIP_ROOT + "llm_analysis/input/reviews(llm_input)(consider_path).csv"
_STAGE1_FORMATTED = (
    _ZIP_ROOT
    + "llm_analysis/output/reviews(llm_input)(consider_path)/"
    + "Suggestion_openai-gpt-4.1_p=3.12(1)(f).csv"
)
_STAGE2_FORMATTED = (
    _ZIP_ROOT
    + "llm_analysis/output/reviews(llm_input)(consider_path)/"
    + "Addressed_openai-o3-mini_p=4.7(1)_based_"
    + "Suggestion_openai-o3-mini_p=3.12(1)(f).csv"
)
_STAGE2_DECLARED_STAGE1 = (
    _ZIP_ROOT
    + "llm_analysis/output/reviews(llm_input)(consider_path)/"
    + "Suggestion_openai-o3-mini_p=3.12(1)(f).csv"
)
_HUMAN_FINAL_FILES = (
    _ZIP_ROOT + "llm_analysis/labeled/(resolved)sampled_human_review.csv",
    _ZIP_ROOT + "llm_analysis/labeled/(resolved)sampled_file_level_review.csv",
    _ZIP_ROOT + "llm_analysis/labeled/(resolved)sampled_patch_level_review.csv",
)

_REVIEW_COMMENT = re.compile(r"/pulls/comments/(?P<id>\d+)(?:$|[/?#])")
_ISSUE_COMMENT = re.compile(
    r"/issues/comments/(?P<id>\d+)(?:-(?P<fragment>\d+))?(?:$|[/?#])"
)


@dataclass(frozen=True, slots=True)
class PublicCommentReference:
    """Identity of a public event underlying a released analysis row."""

    kind: str
    public_id: int
    fragment_index: int | None = None

    @property
    def event_key(self) -> tuple[str, int]:
        return self.kind, self.public_id


def parse_public_comment_reference(value: str) -> PublicCommentReference | None:
    """Parse GitHub API comment URLs, including released issue-comment fragments."""

    review = _REVIEW_COMMENT.search(value.strip())
    if review:
        return PublicCommentReference("review_comment", int(review.group("id")))
    issue = _ISSUE_COMMENT.search(value.strip())
    if issue:
        fragment = issue.group("fragment")
        return PublicCommentReference(
            "issue_comment",
            int(issue.group("id")),
            int(fragment) if fragment is not None else None,
        )
    return None


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_tree_digest(root: Path) -> dict[str, Any]:
    """Hash a local dataset tree while excluding downloader cache metadata."""

    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(root).parts
    )
    tree = hashlib.sha256()
    total_bytes = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        file_hash = _digest(path, "sha256")
        tree.update(relative.encode("utf-8"))
        tree.update(b"\0")
        tree.update(file_hash.encode("ascii"))
        tree.update(b"\n")
        total_bytes += path.stat().st_size
    return {
        "algorithm": "sha256(path NUL sha256(file) LF)",
        "sha256": tree.hexdigest(),
        "files": len(files),
        "bytes": total_bytes,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def profile_swe_prbench(root: Path) -> dict[str, Any]:
    """Profile SWE-PRBench grain, identifier scope, and internal consistency."""

    dataset = root / "dataset"
    prs = _read_jsonl(dataset / "prs.jsonl")
    annotation_paths = sorted((dataset / "annotations").glob("*.json"))
    annotations = [json.loads(path.read_text(encoding="utf-8")) for path in annotation_paths]
    annotation_by_task = {row["task_id"]: row for row in annotations}
    annotation_comments = [comment for row in annotations for comment in row["comments"]]
    embedded_comments = [
        comment for row in prs for comment in (row.get("human_review_comments") or [])
    ]

    task_ids = {str(row["task_id"]) for row in prs}
    annotation_task_ids = {str(row["task_id"]) for row in annotations}
    annotation_count_sum = sum(int(row["substantive_comment_count"]) for row in annotations)
    pr_count_sum = sum(int(row["num_substantive_comments"]) for row in prs)
    summary_matches = sum(
        int(row["num_substantive_comments"])
        == int(annotation_by_task[str(row["task_id"])]["substantive_comment_count"])
        for row in prs
    )
    synthetic_ids = [str(comment["comment_id"]) for comment in annotation_comments]
    context_profile: dict[str, Any] = {}
    for config in ("config_A", "config_B", "config_C"):
        paths = sorted((dataset / "contexts" / config).glob("*.json"))
        rows = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        context_profile[config] = {
            "files": len(paths),
            "unique_tasks": len({str(row["task_id"]) for row in rows}),
            "pipeline_versions": dict(sorted(Counter(row.get("pipeline_version") for row in rows).items())),
        }

    revision_file = root / ".cache" / "huggingface" / "download" / "README.md.metadata"
    revision = None
    if revision_file.is_file():
        lines = revision_file.read_text(encoding="utf-8").splitlines()
        revision = lines[0].strip() if lines else None

    return {
        "source": "SWE-PRBench",
        "canonical_url": "https://huggingface.co/datasets/foundry-ai/swe-prbench",
        "revision": revision,
        "declared_license": "CC-BY-4.0",
        "local_tree": directory_tree_digest(root),
        "pull_requests": len(prs),
        "unique_task_ids": len(task_ids),
        "unique_pr_urls": len({str(row["pr_url"]) for row in prs}),
        "repositories": len({str(row["repo"]) for row in prs}),
        "merged_at_present": sum(bool(row.get("merged_at")) for row in prs),
        "annotation_files": len(annotations),
        "annotation_tasks_match_pr_tasks": annotation_task_ids == task_ids,
        "annotation_comments": len(annotation_comments),
        "annotation_comment_ids_global_unique": len(set(synthetic_ids)),
        "annotation_comment_task_keys_unique": len(
            {
                (str(row["task_id"]), str(comment["comment_id"]))
                for row in annotations
                for comment in row["comments"]
            }
        ),
        "annotation_comments_all_initiating": all(
            comment.get("is_initiating_comment") is True for comment in annotation_comments
        ),
        "annotation_reply_to_present": sum(
            comment.get("reply_to") is not None for comment in annotation_comments
        ),
        "annotation_comment_timestamp_field_present": any(
            any(key in comment for key in ("created_at", "createdAt", "timestamp"))
            for comment in annotation_comments
        ),
        "embedded_human_comments": len(embedded_comments),
        "embedded_comments_with_reply_to_id": sum(
            isinstance(comment.get("replyTo"), dict)
            and comment["replyTo"].get("id") is not None
            for comment in embedded_comments
        ),
        "embedded_comment_own_id_field_present": any("id" in comment for comment in embedded_comments),
        "embedded_comment_timestamp_field_present": any(
            any(key in comment for key in ("created_at", "createdAt", "timestamp"))
            for comment in embedded_comments
        ),
        "pr_num_substantive_comments_sum": pr_count_sum,
        "annotation_substantive_comments_sum": annotation_count_sum,
        "prs_where_summary_matches_annotation": summary_matches,
        "prs_where_summary_differs_from_annotation": len(prs) - summary_matches,
        "annotation_bodies_below_10_whitespace_tokens": sum(
            len(str(comment.get("body", "")).split()) < 10 for comment in annotation_comments
        ),
        "ai_comments_removed_sum": sum(int(row.get("ai_comments_removed") or 0) for row in prs),
        "prs_with_ai_comments_removed": sum(
            int(row.get("ai_comments_removed") or 0) > 0 for row in prs
        ),
        "contexts": context_profile,
        "construct_disposition": "semantic_initiating_feedback_only",
        "exact_public_edge_supported": False,
    }


def _csv_rows(bundle: zipfile.ZipFile, member: str) -> list[dict[str, str]]:
    with bundle.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        return list(csv.DictReader(text))


def profile_ai_review_action_archive(path: Path) -> tuple[dict[str, Any], set[int], set[int]]:
    """Profile the Zenodo archive and return aggregate data plus joinable IDs."""

    archive_md5 = _digest(path, "md5")
    archive_sha256 = _digest(path, "sha256")
    with zipfile.ZipFile(path) as bundle:
        corrupt_member = bundle.testzip()
        members = {item.filename for item in bundle.infolist()}
        files = [item for item in bundle.infolist() if not item.is_dir()]
        rows = _csv_rows(bundle, _ANALYSIS_INPUT)
        stage1 = _csv_rows(bundle, _STAGE1_FORMATTED)
        stage2 = _csv_rows(bundle, _STAGE2_FORMATTED)
        human_final_counts = {
            Path(member).name: len(_csv_rows(bundle, member)) for member in _HUMAN_FINAL_FILES
        }

    references = [parse_public_comment_reference(str(row.get("Comment_ID", ""))) for row in rows]
    parsed = [reference for reference in references if reference is not None]
    review_ids = {reference.public_id for reference in parsed if reference.kind == "review_comment"}
    issue_ids = {reference.public_id for reference in parsed if reference.kind == "issue_comment"}
    source_rows = Counter(str(row.get("Source", "")) for row in rows)
    source_event_keys: dict[str, set[tuple[str, int]]] = {}
    for row, reference in zip(rows, references, strict=True):
        if reference is not None:
            source_event_keys.setdefault(str(row.get("Source", "")), set()).add(reference.event_key)

    license_files = [
        member
        for member in members
        if Path(member).name.lower().startswith(("license", "copying"))
    ]
    profile = {
        "source": "AIReviewActionAnalysis",
        "canonical_url": ZENODO_RECORD,
        "doi": ZENODO_DOI,
        "record_metadata_license": ZENODO_LICENSE,
        "embedded_license_files": sorted(license_files),
        "archive_bytes": path.stat().st_size,
        "archive_md5": archive_md5,
        "zenodo_expected_md5": ZENODO_EXPECTED_MD5,
        "zenodo_md5_matches": archive_md5 == ZENODO_EXPECTED_MD5,
        "archive_sha256": archive_sha256,
        "zip_crc_failure": corrupt_member,
        "archive_files": len(files),
        "archive_uncompressed_bytes": sum(item.file_size for item in files),
        "analysis_rows": len(rows),
        "analysis_row_ids_unique": len({str(row.get("Comment_ID", "")) for row in rows}),
        "parsed_analysis_rows": len(parsed),
        "underlying_public_comment_events": len({reference.event_key for reference in parsed}),
        "inline_review_comment_events": len(review_ids),
        "issue_comment_events": len(issue_ids),
        "issue_comment_fragment_rows": sum(
            reference.kind == "issue_comment" for reference in parsed
        ),
        "sources": dict(sorted(source_rows.items())),
        "underlying_events_by_source": {
            source: len(keys) for source, keys in sorted(source_event_keys.items())
        },
        "stage1_formatted_rows": len(stage1),
        "stage1_model_from_filename": "openai-gpt-4.1",
        "stage1_classification": dict(
            sorted(Counter(str(row.get("Classification", "")) for row in stage1).items())
        ),
        "stage2_formatted_rows": len(stage2),
        "stage2_model_from_filename": "openai-o3-mini",
        "stage2_declared_stage1_member": _STAGE2_DECLARED_STAGE1,
        "stage2_declared_stage1_member_present": _STAGE2_DECLARED_STAGE1 in members,
        "released_stage1_member": _STAGE1_FORMATTED,
        "stage2_resolution": dict(
            sorted(Counter(str(row.get("Resolution_Formated", "")) for row in stage2).items())
        ),
        "human_final_label_files": human_final_counts,
        "human_final_label_rows": sum(human_final_counts.values()),
        "construct_disposition": "semantic_code_change_addressing_only",
        "addressed_means_exact_public_reply": False,
        "exact_public_edge_supported": False,
    }
    return profile, review_ids, issue_ids


def compare_aidev(
    *,
    aidev_root: Path,
    swe_pr_urls: set[str],
    review_action_review_ids: set[int],
    review_action_issue_ids: set[int],
) -> dict[str, Any]:
    """Compare stable public identifiers without fuzzy text matching."""

    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    def parquet_ids(filename: str) -> set[int]:
        found: set[int] = set()
        parquet = pq.ParquetFile(aidev_root / filename)
        for batch in parquet.iter_batches(columns=["id"], batch_size=200_000):
            found.update(value for value in batch.column(0).to_pylist() if value is not None)
        return found

    def matching_urls(filename: str) -> set[str]:
        found: set[str] = set()
        parquet = pq.ParquetFile(aidev_root / filename)
        values = pa.array(sorted(swe_pr_urls))
        for batch in parquet.iter_batches(columns=["html_url"], batch_size=200_000):
            column = batch.column(0)
            selected = pc.filter(column, pc.is_in(column, value_set=values))
            found.update(str(value).rstrip("/") for value in selected.to_pylist() if value)
        return found

    aidev_review_ids = parquet_ids("pr_review_comments.parquet")
    aidev_issue_ids = parquet_ids("pr_comments.parquet")
    rich_urls = matching_urls("pull_request.parquet")
    all_urls = matching_urls("all_pull_request.parquet")
    return {
        "aidev_review_comment_ids": len(aidev_review_ids),
        "review_action_review_id_overlap": len(aidev_review_ids & review_action_review_ids),
        "aidev_issue_comment_ids": len(aidev_issue_ids),
        "review_action_issue_id_overlap": len(aidev_issue_ids & review_action_issue_ids),
        "swe_prs": len(swe_pr_urls),
        "swe_rich_pr_url_overlap": len(rich_urls),
        "swe_all_pr_url_overlap": len(all_urls),
    }


def build_profile(*, swe_root: Path, review_action_archive: Path, aidev_root: Path) -> dict[str, Any]:
    """Build the complete aggregate-only audit."""

    swe = profile_swe_prbench(swe_root)
    review_action, review_ids, issue_ids = profile_ai_review_action_archive(
        review_action_archive
    )
    prs = _read_jsonl(swe_root / "dataset" / "prs.jsonl")
    swe_pr_urls = {str(row["pr_url"]).rstrip("/") for row in prs}
    return {
        "audit_date": "2026-08-26",
        "raw_comment_text_exported": False,
        "swe_prbench": swe,
        "ai_review_action_analysis": review_action,
        "aidev_overlap": compare_aidev(
            aidev_root=aidev_root,
            swe_pr_urls=swe_pr_urls,
            review_action_review_ids=review_ids,
            review_action_issue_ids=issue_ids,
        ),
    }
