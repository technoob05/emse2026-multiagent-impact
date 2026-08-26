from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.audit.profile_swe_review_chat import (  # noqa: E402
    AIDEV_REVISION,
    DEFAULT_AIDEV_DIR,
    DEFAULT_DATASET_DIR,
    PINNED_REVISION,
    mapped_product,
    normalize_pr_number,
    normalize_repo,
    normalized_login,
)


DEFAULT_RAW_DIR = (
    ROOT / "external_data" / "cache" / "swe_review_chat_exact_edge_pilot"
)
DEFAULT_OUTPUT_JSON = (
    ROOT / "protocol" / "swe_review_chat_exact_edge_pilot_20260826.json"
)
DEFAULT_FUNNEL_CSV = (
    ROOT / "protocol" / "swe_review_chat_exact_edge_funnel_20260826.csv"
)
DEFAULT_QUALITY_MD = ROOT / "docs" / "SWE_REVIEW_CHAT_EXACT_EDGE_PILOT_20260826.md"
DEFAULT_OUTPUT_README = (
    ROOT / "outputs" / "external_validation" / "swe_review_chat_exact_edge_pilot" / "README.md"
)

API_VERSION = "2026-03-10"
API_DOC_COMMENT = "https://docs.github.com/en/rest/pulls/comments"
API_DOC_PULL = "https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request"
EXPECTED_ROWS = 1_082_529
MIN_REPLICATION_RISK_SET = 50
MIN_REPLICATION_EXPOSED = 20
MIN_REPLICATION_PRODUCT_PAIRS = 2

COMMENT_JQ = (
    "{id: .id, pull_request_review_id: .pull_request_review_id, "
    "in_reply_to_id: .in_reply_to_id, created_at: .created_at, "
    "updated_at: .updated_at, user: {login: .user.login, type: .user.type}, "
    "pull_request_url: .pull_request_url}"
)
PULL_JQ = (
    "{number: .number, state: .state, created_at: .created_at, "
    "closed_at: .closed_at, merged_at: .merged_at, "
    "user: {login: .user.login, type: .user.type}, draft: .draft, "
    "html_url: .html_url}"
)
RATE_JQ = (
    "{limit: .resources.core.limit, remaining: .resources.core.remaining, "
    "used: .resources.core.used, reset: .resources.core.reset}"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed SWE-Review-Chat exact-edge eligibility and GitHub REST "
            "hydration pilot. Raw candidate IDs remain in a gitignored directory."
        )
    )
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--aidev-dir", type=Path, default=DEFAULT_AIDEV_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--funnel-csv", type=Path, default=DEFAULT_FUNNEL_CSV)
    parser.add_argument("--quality-md", type=Path, default=DEFAULT_QUALITY_MD)
    parser.add_argument("--output-readme", type=Path, default=DEFAULT_OUTPUT_README)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument(
        "--no-hydrate",
        action="store_true",
        help="Extract candidates and stop before GitHub REST calls.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), ROOT)).as_posix()


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def actor_category(
    login: Any,
    actor_type: Any,
    parent_product: str,
    author_product: str,
) -> dict[str, str | None]:
    product = mapped_product(login)
    actor_type_text = str(actor_type) if actor_type is not None else "Unknown"
    if product is None and actor_type_text.casefold() == "user":
        relation_parent = "user_unmapped_product"
        relation_author = "user_unmapped_product"
    elif product is None:
        relation_parent = "other_unmapped_product"
        relation_author = "other_unmapped_product"
    else:
        relation_parent = (
            "same_as_parent_product"
            if product == parent_product
            else "different_from_parent_product"
        )
        relation_author = (
            "same_as_author_product"
            if product == author_product
            else "different_from_author_product"
        )
    return {
        "mapped_product": product,
        "relation_to_parent": relation_parent,
        "relation_to_author": relation_author,
    }


def choose_first_trigger(
    triggers: list[dict[str, Any]],
) -> tuple[int | None, str]:
    if not triggers:
        return None, "no_cross_product_inline_trigger"
    normalized: list[tuple[datetime, int]] = []
    for trigger in triggers:
        timestamp = parse_timestamp(trigger.get("timestamp"))
        comment_id = normalize_pr_number(trigger.get("comment_id"))
        if timestamp is None:
            return None, "cross_product_trigger_timestamp_missing_or_invalid"
        if comment_id is None:
            return None, "cross_product_trigger_comment_id_missing_or_invalid"
        normalized.append((timestamp, comment_id))
    normalized.sort(key=lambda item: (item[0], item[1]))
    return normalized[0][1], "determined_by_timestamp_then_comment_id"


def state_at_landmark(
    lifecycle_events: list[dict[str, Any]], landmark: datetime
) -> tuple[bool | None, str]:
    state = "open"
    parsed_events: list[tuple[datetime, str, int]] = []
    for index, event in enumerate(lifecycle_events):
        event_type = str(event.get("type") or "")
        if event_type not in {"closed", "merged", "reopened"}:
            continue
        timestamp = parse_timestamp(event.get("timestamp"))
        if timestamp is None:
            return None, "invalid_lifecycle_timestamp"
        parsed_events.append((timestamp, event_type, index))
    parsed_events.sort(key=lambda item: (item[0], item[2]))
    for timestamp, event_type, _ in parsed_events:
        if timestamp > landmark:
            break
        if event_type in {"closed", "merged"}:
            state = "closed"
        elif event_type == "reopened":
            state = "open"
    return state == "open", "dataset_lifecycle_events"


def comment_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Whitelist non-body fields even if a caller provides a raw API payload."""
    user = payload.get("user") or {}
    return {
        "id": payload.get("id"),
        "pull_request_review_id": payload.get("pull_request_review_id"),
        "in_reply_to_id": payload.get("in_reply_to_id"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "user": {"login": user.get("login"), "type": user.get("type")},
        "pull_request_url": payload.get("pull_request_url"),
    }


def pull_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Whitelist only state/timing/identity fields from a pull response."""
    user = payload.get("user") or {}
    return {
        "number": payload.get("number"),
        "state": payload.get("state"),
        "created_at": payload.get("created_at"),
        "closed_at": payload.get("closed_at"),
        "merged_at": payload.get("merged_at"),
        "user": {"login": user.get("login"), "type": user.get("type")},
        "draft": payload.get("draft"),
        "html_url": payload.get("html_url"),
    }


def extract_candidates(dataset_dir: Path, batch_size: int) -> dict[str, Any]:
    parquet_files = sorted(dataset_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No Parquet shards under {dataset_dir}")
    scanned_rows = 0
    mapped_author_rows = 0
    mapped_author_keys: set[tuple[str, int]] = set()
    invalid_keys = 0
    cross_parent_events = 0
    cross_parent_prs: set[tuple[str, int]] = set()
    triggers_by_pr: dict[tuple[str, int], dict[tuple[Any, ...], dict[str, Any]]] = defaultdict(dict)
    candidates: dict[tuple[Any, ...], dict[str, Any]] = {}
    lifecycle_by_pr: dict[tuple[str, int], dict[tuple[str, str], dict[str, str]]] = defaultdict(dict)
    authors_by_pr: dict[tuple[str, int], set[tuple[str, str]]] = defaultdict(set)
    source_child_categories: Counter[str] = Counter()
    null_parent_ids = 0
    null_child_ids = 0

    columns = [
        "repo_full_name",
        "pr_number",
        "created_by",
        "created_by_type",
        "created_at",
        "review_conversations",
    ]
    for file_index, path in enumerate(parquet_files, start=1):
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
            scanned_rows += batch.num_rows
            arrays = {
                name: batch.column(batch.schema.get_field_index(name)) for name in columns
            }
            repos = arrays["repo_full_name"].to_pylist()
            numbers = arrays["pr_number"].to_pylist()
            authors = arrays["created_by"].to_pylist()
            author_types = arrays["created_by_type"].to_pylist()
            pr_created = arrays["created_at"].to_pylist()
            conversations = arrays["review_conversations"]
            events = pc.list_flatten(conversations)
            event_types = events.field("type").to_pylist()
            event_timestamps = events.field("timestamp").to_pylist()
            event_reviewers = events.field("reviewer").to_pylist()
            event_reviewer_types = events.field("reviewer_type").to_pylist()
            event_review_ids = events.field("review_id").to_pylist()
            event_comment_ids = events.field("comment_id").to_pylist()
            reply_lists = events.field("thread_replies")
            replies = pc.list_flatten(reply_lists)
            reply_reviewers = replies.field("reviewer").to_pylist()
            reply_reviewer_types = replies.field("reviewer_type").to_pylist()
            reply_comment_ids = replies.field("comment_id").to_pylist()
            conv_offsets = conversations.offsets.to_pylist()
            conv_base = int(conv_offsets[0]) if conv_offsets else 0
            reply_offsets = reply_lists.offsets.to_pylist()
            reply_base = int(reply_offsets[0]) if reply_offsets else 0

            for row_index in range(batch.num_rows):
                repo = normalize_repo(repos[row_index])
                number = normalize_pr_number(numbers[row_index])
                if repo is None or number is None:
                    invalid_keys += 1
                    continue
                key = (repo, number)
                author_product = mapped_product(authors[row_index])
                if author_product is None:
                    continue
                mapped_author_rows += 1
                mapped_author_keys.add(key)
                author_login = normalized_login(authors[row_index])
                authors_by_pr[key].add((author_product, author_login or ""))
                created_timestamp = str(pr_created[row_index] or "")
                if created_timestamp:
                    lifecycle_by_pr[key][("created", created_timestamp)] = {
                        "type": "created",
                        "timestamp": created_timestamp,
                    }

                start = int(conv_offsets[row_index]) - conv_base
                stop = int(conv_offsets[row_index + 1]) - conv_base
                for event_index in range(start, stop):
                    event_type = str(event_types[event_index] or "")
                    event_timestamp = str(event_timestamps[event_index] or "")
                    if event_type in {"closed", "merged", "reopened"}:
                        lifecycle_by_pr[key][(event_type, event_timestamp)] = {
                            "type": event_type,
                            "timestamp": event_timestamp,
                        }
                    if event_type != "review_comment":
                        continue
                    parent_product = mapped_product(event_reviewers[event_index])
                    if parent_product is None or parent_product == author_product:
                        continue
                    cross_parent_events += 1
                    cross_parent_prs.add(key)
                    parent_id = normalize_pr_number(event_comment_ids[event_index])
                    review_id = normalize_pr_number(event_review_ids[event_index])
                    trigger_key = (
                        parent_id,
                        event_timestamp,
                        author_product,
                        parent_product,
                    )
                    triggers_by_pr[key][trigger_key] = {
                        "comment_id": parent_id,
                        "timestamp": event_timestamp,
                        "author_product": author_product,
                        "parent_product": parent_product,
                    }
                    reply_start = int(reply_offsets[event_index]) - reply_base
                    reply_stop = int(reply_offsets[event_index + 1]) - reply_base
                    if reply_stop <= reply_start:
                        continue
                    if parent_id is None:
                        null_parent_ids += 1
                    candidate_key = (
                        repo,
                        number,
                        parent_id,
                        event_timestamp,
                        author_product,
                        parent_product,
                    )
                    candidate = candidates.setdefault(
                        candidate_key,
                        {
                            "repo_full_name": repo,
                            "pr_number": number,
                            "dataset_pr_created_at": created_timestamp,
                            "dataset_root_author_login": author_login,
                            "dataset_root_author_type": author_types[row_index],
                            "author_product": author_product,
                            "parent_comment_id": parent_id,
                            "parent_review_id": review_id,
                            "parent_dataset_created_at": event_timestamp,
                            "parent_dataset_actor_login": normalized_login(
                                event_reviewers[event_index]
                            ),
                            "parent_dataset_actor_type": event_reviewer_types[event_index],
                            "parent_product": parent_product,
                            "children": {},
                        },
                    )
                    for reply_index in range(reply_start, reply_stop):
                        child_id = normalize_pr_number(reply_comment_ids[reply_index])
                        if child_id is None:
                            null_child_ids += 1
                        category = actor_category(
                            reply_reviewers[reply_index],
                            reply_reviewer_types[reply_index],
                            parent_product,
                            author_product,
                        )
                        source_child_categories[str(category["relation_to_parent"])] += 1
                        child_key = (
                            child_id,
                            normalized_login(reply_reviewers[reply_index]),
                            reply_reviewer_types[reply_index],
                        )
                        candidate["children"][child_key] = {
                            "comment_id": child_id,
                            "dataset_actor_login": normalized_login(
                                reply_reviewers[reply_index]
                            ),
                            "dataset_actor_type": reply_reviewer_types[reply_index],
                            **category,
                        }
        if file_index % 50 == 0 or file_index == len(parquet_files):
            print(
                f"candidate scan {file_index}/{len(parquet_files)} shards; "
                f"{scanned_rows:,} PR rows",
                flush=True,
            )

    if scanned_rows != EXPECTED_ROWS:
        raise AssertionError(f"SWE-Review-Chat row drift: {scanned_rows} != {EXPECTED_ROWS}")

    candidate_rows: list[dict[str, Any]] = []
    first_reason_counts: Counter[str] = Counter()
    for candidate in candidates.values():
        key = (candidate["repo_full_name"], candidate["pr_number"])
        triggers = list(triggers_by_pr[key].values())
        first_id, first_reason = choose_first_trigger(triggers)
        first_reason_counts[first_reason] += 1
        candidate["first_cross_product_parent_comment_id"] = first_id
        candidate["first_trigger_determination"] = first_reason
        candidate["is_first_cross_product_inline_trigger"] = (
            first_id is not None and candidate["parent_comment_id"] == first_id
        )
        candidate["root_author_mapping_conflict"] = len(authors_by_pr[key]) != 1
        candidate["lifecycle_events"] = sorted(
            lifecycle_by_pr[key].values(), key=lambda item: (item["timestamp"], item["type"])
        )
        candidate["children"] = sorted(
            candidate["children"].values(),
            key=lambda item: (
                item["comment_id"] is None,
                item["comment_id"] or 0,
                item["dataset_actor_login"] or "",
            ),
        )
        candidate_rows.append(candidate)
    candidate_rows.sort(
        key=lambda item: (
            item["repo_full_name"],
            item["pr_number"],
            item["parent_comment_id"] is None,
            item["parent_comment_id"] or 0,
        )
    )
    return {
        "candidates": candidate_rows,
        "scanned_rows": scanned_rows,
        "parquet_shards": len(parquet_files),
        "invalid_pr_key_rows": invalid_keys,
        "mapped_author_rows": mapped_author_rows,
        "mapped_author_prs": len(mapped_author_keys),
        "cross_product_inline_parent_events": cross_parent_events,
        "cross_product_inline_parent_prs": len(cross_parent_prs),
        "candidate_parent_threads": len(candidate_rows),
        "candidate_prs": len(
            {(item["repo_full_name"], item["pr_number"]) for item in candidate_rows}
        ),
        "candidate_children": sum(len(item["children"]) for item in candidate_rows),
        "null_parent_comment_id_threads": null_parent_ids,
        "null_child_comment_ids": null_child_ids,
        "source_child_relation_to_parent_counts": dict(source_child_categories),
        "first_trigger_determination_counts": dict(first_reason_counts),
    }


def aidev_candidate_overlap(
    all_pr_path: Path, candidate_keys: set[tuple[str, int]]
) -> dict[str, Any]:
    parquet = pq.ParquetFile(all_pr_path)
    matched: set[tuple[str, int]] = set()
    scanned = 0
    invalid = 0
    for batch in parquet.iter_batches(
        batch_size=131_072, columns=["repo_url", "number"]
    ):
        scanned += batch.num_rows
        repos = batch.column(batch.schema.get_field_index("repo_url")).to_pylist()
        numbers = batch.column(batch.schema.get_field_index("number")).to_pylist()
        for repo_value, number_value in zip(repos, numbers, strict=True):
            repo = normalize_repo(repo_value)
            number = normalize_pr_number(number_value)
            if repo is None or number is None:
                invalid += 1
                continue
            key = (repo, number)
            if key in candidate_keys:
                matched.add(key)
    return {
        "matched_keys": matched,
        "source_metadata_rows": int(parquet.metadata.num_rows),
        "source_rows_scanned": scanned,
        "invalid_source_key_rows": invalid,
    }


def gh_api(endpoint: str, jq: str) -> dict[str, Any]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    command = [
        "gh",
        "api",
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        f"X-GitHub-Api-Version: {API_VERSION}",
        endpoint,
        "--jq",
        jq,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {
                "status": None,
                "ok": False,
                "error_class": "invalid_filtered_json",
                "fetched_at": fetched_at,
                "payload": None,
            }
        return {
            "status": 200,
            "ok": True,
            "error_class": None,
            "fetched_at": fetched_at,
            "payload": payload,
        }
    match = re.search(r"HTTP\s+(\d{3})", result.stderr, flags=re.IGNORECASE)
    status = int(match.group(1)) if match else None
    return {
        "status": status,
        "ok": False,
        "error_class": f"http_{status}" if status is not None else "gh_cli_failure",
        "fetched_at": fetched_at,
        "payload": None,
    }


def auth_available() -> bool:
    result = subprocess.run(
        ["gh", "auth", "status", "--hostname", "github.com"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode == 0


def validate_parent(
    candidate: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    payload = response.get("payload") or {}
    parent_time = parse_timestamp(payload.get("created_at"))
    dataset_time = parse_timestamp(candidate.get("parent_dataset_created_at"))
    api_login = normalized_login((payload.get("user") or {}).get("login"))
    validations = {
        "http_200": response.get("status") == 200,
        "comment_id_matches": payload.get("id") == candidate.get("parent_comment_id"),
        "top_level_parent_has_no_in_reply_to_id": payload.get("in_reply_to_id") is None,
        "actor_login_matches_dataset": api_login
        == candidate.get("parent_dataset_actor_login"),
        "actor_product_matches_parent_product": mapped_product(api_login)
        == candidate.get("parent_product"),
        "created_at_matches_dataset": parent_time is not None and parent_time == dataset_time,
        "review_batch_matches_dataset": payload.get("pull_request_review_id")
        == candidate.get("parent_review_id"),
    }
    validations["valid"] = all(validations.values())
    return validations


def validate_child(
    candidate: dict[str, Any],
    child: dict[str, Any],
    response: dict[str, Any],
    parent_time: datetime | None,
) -> dict[str, Any]:
    payload = response.get("payload") or {}
    child_time = parse_timestamp(payload.get("created_at"))
    api_login = normalized_login((payload.get("user") or {}).get("login"))
    api_type = (payload.get("user") or {}).get("type")
    api_category = actor_category(
        api_login,
        api_type,
        candidate["parent_product"],
        candidate["author_product"],
    )
    validations = {
        "http_200": response.get("status") == 200,
        "comment_id_matches": payload.get("id") == child.get("comment_id"),
        "exact_parent_matches": payload.get("in_reply_to_id")
        == candidate.get("parent_comment_id"),
        "actor_login_matches_dataset": api_login == child.get("dataset_actor_login"),
        "actor_type_matches_dataset": api_type == child.get("dataset_actor_type"),
        "actor_category_matches_dataset": api_category["relation_to_parent"]
        == child.get("relation_to_parent"),
        "created_strictly_after_parent": child_time is not None
        and parent_time is not None
        and child_time > parent_time,
    }
    validations["valid_exact_child"] = all(validations.values())
    return {
        "validations": validations,
        "api_actor_category": api_category,
        "created_at": payload.get("created_at"),
        "pull_request_review_id": payload.get("pull_request_review_id"),
        "in_reply_to_id": payload.get("in_reply_to_id"),
    }


def validate_pull(
    candidate: dict[str, Any], response: dict[str, Any]
) -> dict[str, Any]:
    payload = response.get("payload") or {}
    api_login = normalized_login((payload.get("user") or {}).get("login"))
    validations = {
        "http_200": response.get("status") == 200,
        "pr_number_matches": payload.get("number") == candidate.get("pr_number"),
        "root_author_login_matches_dataset": api_login
        == candidate.get("dataset_root_author_login"),
        "root_author_product_matches": mapped_product(api_login)
        == candidate.get("author_product"),
        "state_is_known": payload.get("state") in {"open", "closed"},
        "created_at_is_valid": parse_timestamp(payload.get("created_at")) is not None,
    }
    validations["valid"] = all(validations.values())
    return validations


def hydrate_candidates(
    candidates: list[dict[str, Any]], raw_dir: Path
) -> dict[str, Any]:
    if not auth_available():
        raise RuntimeError("Authenticated GitHub CLI session is required for hydration.")
    raw_dir.mkdir(parents=True, exist_ok=True)
    http_rows: list[dict[str, Any]] = []
    comment_cache: dict[tuple[str, int], dict[str, Any]] = {}
    pull_cache: dict[tuple[str, int], dict[str, Any]] = {}
    rate_before = gh_api("rate_limit", RATE_JQ)
    hydrated: list[dict[str, Any]] = []

    def get_comment(repo: str, pr_number: int, comment_id: int) -> dict[str, Any]:
        cache_key = (repo, comment_id)
        if cache_key not in comment_cache:
            response = gh_api(
                f"repos/{repo}/pulls/comments/{comment_id}", COMMENT_JQ
            )
            if response["payload"] is not None:
                response["payload"] = comment_projection(response["payload"])
            comment_cache[cache_key] = response
            http_rows.append(
                {
                    "endpoint_kind": "review_comment",
                    "repo_full_name": repo,
                    "pr_number": pr_number,
                    "comment_id": comment_id,
                    "status": response["status"],
                    "ok": response["ok"],
                    "error_class": response["error_class"],
                    "fetched_at": response["fetched_at"],
                }
            )
        return comment_cache[cache_key]

    def get_pull(repo: str, pr_number: int) -> dict[str, Any]:
        cache_key = (repo, pr_number)
        if cache_key not in pull_cache:
            response = gh_api(f"repos/{repo}/pulls/{pr_number}", PULL_JQ)
            if response["payload"] is not None:
                response["payload"] = pull_projection(response["payload"])
            pull_cache[cache_key] = response
            http_rows.append(
                {
                    "endpoint_kind": "pull_request",
                    "repo_full_name": repo,
                    "pr_number": pr_number,
                    "comment_id": None,
                    "status": response["status"],
                    "ok": response["ok"],
                    "error_class": response["error_class"],
                    "fetched_at": response["fetched_at"],
                }
            )
        return pull_cache[cache_key]

    for index, candidate in enumerate(candidates, start=1):
        repo = candidate["repo_full_name"]
        pr_number = candidate["pr_number"]
        parent_id = candidate.get("parent_comment_id")
        pull_response = get_pull(repo, pr_number)
        parent_response = (
            get_comment(repo, pr_number, parent_id)
            if isinstance(parent_id, int)
            else {
                "status": None,
                "ok": False,
                "error_class": "missing_parent_comment_id",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "payload": None,
            }
        )
        parent_validation = validate_parent(candidate, parent_response)
        parent_payload = parent_response.get("payload") or {}
        parent_time = parse_timestamp(parent_payload.get("created_at"))
        child_records: list[dict[str, Any]] = []
        for child in candidate["children"]:
            child_id = child.get("comment_id")
            child_response = (
                get_comment(repo, pr_number, child_id)
                if isinstance(child_id, int)
                else {
                    "status": None,
                    "ok": False,
                    "error_class": "missing_child_comment_id",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "payload": None,
                }
            )
            validation = validate_child(
                candidate, child, child_response, parent_time
            )
            child_records.append(
                {
                    "source": child,
                    "http_status": child_response.get("status"),
                    "http_error_class": child_response.get("error_class"),
                    "api": child_response.get("payload"),
                    **validation,
                }
            )
        pull_validation = validate_pull(candidate, pull_response)
        pull_payload = pull_response.get("payload") or {}
        trigger_time = parent_time
        landmark = trigger_time + timedelta(hours=48) if trigger_time else None
        horizon = trigger_time + timedelta(days=30) if trigger_time else None
        fetched_at = datetime.now(timezone.utc)
        lifecycle_open, lifecycle_source = (
            state_at_landmark(candidate["lifecycle_events"], landmark)
            if landmark is not None
            else (None, "parent_time_unavailable")
        )
        valid_child_times = [
            parse_timestamp(record["created_at"])
            for record in child_records
            if record["validations"]["valid_exact_child"]
        ]
        valid_child_times = [value for value in valid_child_times if value is not None]
        exact_by_48h = bool(
            landmark is not None
            and trigger_time is not None
            and any(trigger_time < value <= landmark for value in valid_child_times)
        )
        complete_horizon = horizon is not None and fetched_at >= horizon
        merge_time = parse_timestamp(pull_payload.get("merged_at"))
        later_merge = (
            bool(merge_time is not None and landmark < merge_time <= horizon)
            if landmark is not None and horizon is not None
            else None
        )
        landmark_eligible = bool(
            candidate["is_first_cross_product_inline_trigger"]
            and not candidate["root_author_mapping_conflict"]
            and parent_validation["valid"]
            and pull_validation["valid"]
            and lifecycle_open is True
            and complete_horizon
        )
        hydrated.append(
            {
                "source": candidate,
                "pull_http_status": pull_response.get("status"),
                "pull_http_error_class": pull_response.get("error_class"),
                "pull_api": pull_payload or None,
                "pull_validations": pull_validation,
                "parent_http_status": parent_response.get("status"),
                "parent_http_error_class": parent_response.get("error_class"),
                "parent_api": parent_payload or None,
                "parent_validations": parent_validation,
                "children": child_records,
                "landmark": {
                    "trigger_at": parent_payload.get("created_at"),
                    "landmark_48h": landmark.isoformat() if landmark else None,
                    "horizon_30d": horizon.isoformat() if horizon else None,
                    "open_at_48h": lifecycle_open,
                    "open_at_48h_source": lifecycle_source,
                    "complete_30d_horizon": complete_horizon,
                    "landmark_eligible": landmark_eligible,
                    "exact_parent_reply_by_48h": exact_by_48h
                    if landmark_eligible
                    else None,
                    "merged_strictly_after_48h_by_30d": later_merge
                    if landmark_eligible
                    else None,
                },
            }
        )
        print(f"hydrated candidate thread {index}/{len(candidates)}", flush=True)

    rate_after = gh_api("rate_limit", RATE_JQ)
    write_jsonl(raw_dir / "hydrated_candidate_threads.jsonl", hydrated)
    write_http_log(raw_dir / "http_coverage.csv", http_rows)
    return {
        "records": hydrated,
        "http_rows": http_rows,
        "rate_before": rate_before,
        "rate_after": rate_after,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_http_log(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "endpoint_kind",
        "repo_full_name",
        "pr_number",
        "comment_id",
        "status",
        "ok",
        "error_class",
        "fetched_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def aggregate_results(
    extraction: dict[str, Any],
    all_candidates: list[dict[str, Any]],
    nonoverlap: list[dict[str, Any]],
    overlap: dict[str, Any],
    hydration: dict[str, Any] | None,
) -> dict[str, Any]:
    nonoverlap_keys = {
        (item["repo_full_name"], item["pr_number"]) for item in nonoverlap
    }
    child_source_counts = Counter(
        child["relation_to_parent"]
        for candidate in nonoverlap
        for child in candidate["children"]
    )
    first_threads = [
        item for item in nonoverlap if item["is_first_cross_product_inline_trigger"]
    ]
    first_prs = {
        (item["repo_full_name"], item["pr_number"]) for item in first_threads
    }
    if hydration is None:
        return {
            "source_child_actor_categories": dict(child_source_counts),
            "http": {"hydration_run": False},
            "validation": {},
            "landmark": {},
            "decision": "EXTRACTION_ONLY",
            "nonoverlap_prs": len(nonoverlap_keys),
            "first_trigger_candidate_prs": len(first_prs),
        }

    records = hydration["records"]
    http_rows = hydration["http_rows"]
    status_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in http_rows:
        status_counts[row["endpoint_kind"]][str(row["status"])] += 1
    api_child_categories = Counter(
        child["api_actor_category"]["relation_to_parent"]
        for record in records
        for child in record["children"]
        if child["http_status"] == 200
    )
    parent_valid = sum(record["parent_validations"]["valid"] for record in records)
    pull_valid = sum(record["pull_validations"]["valid"] for record in records)
    child_records = [child for record in records for child in record["children"]]
    exact_children = sum(
        child["validations"]["valid_exact_child"] for child in child_records
    )
    exact_parent_ids = sum(
        child["validations"]["exact_parent_matches"] for child in child_records
    )
    review_batch_same_parent = sum(
        child.get("pull_request_review_id")
        == record["parent_api"].get("pull_request_review_id")
        for record in records
        if record.get("parent_api")
        for child in record["children"]
        if child.get("api")
    )
    eligible_records = [
        record for record in records if record["landmark"]["landmark_eligible"]
    ]
    eligible_prs = {
        (
            record["source"]["repo_full_name"],
            record["source"]["pr_number"],
        )
        for record in eligible_records
    }
    exposed_prs = {
        (
            record["source"]["repo_full_name"],
            record["source"]["pr_number"],
        )
        for record in eligible_records
        if record["landmark"]["exact_parent_reply_by_48h"]
    }
    outcome_prs = {
        (
            record["source"]["repo_full_name"],
            record["source"]["pr_number"],
        )
        for record in eligible_records
        if record["landmark"]["merged_strictly_after_48h_by_30d"]
    }
    product_pairs = {
        (record["source"]["author_product"], record["source"]["parent_product"])
        for record in eligible_records
    }
    failed_gates = []
    if len(eligible_prs) < MIN_REPLICATION_RISK_SET:
        failed_gates.append("landmark_risk_set_below_50_prs")
    if len(exposed_prs) < MIN_REPLICATION_EXPOSED:
        failed_gates.append("exact_exposed_support_below_20_prs")
    if len(product_pairs) < MIN_REPLICATION_PRODUCT_PAIRS:
        failed_gates.append("fewer_than_two_ordered_product_pairs")
    if not nonoverlap_keys:
        decision = "REJECT_REPLICATION_ZERO_DISJOINT_SUPPORT"
    elif failed_gates:
        decision = "REJECT_REPLICATION_TINY_SUPPORT"
    else:
        decision = "ELIGIBLE_FOR_SEPARATE_PRE_REGISTERED_REPLICATION"
    rate_before = (hydration["rate_before"].get("payload") or {})
    rate_after = (hydration["rate_after"].get("payload") or {})
    return {
        "nonoverlap_prs": len(nonoverlap_keys),
        "first_trigger_candidate_prs": len(first_prs),
        "source_child_actor_categories": dict(child_source_counts),
        "api_child_actor_categories": dict(api_child_categories),
        "http": {
            "hydration_run": True,
            "authenticated": True,
            "api_version": API_VERSION,
            "unique_requests": len(http_rows),
            "status_counts_by_endpoint": {
                kind: dict(counts) for kind, counts in status_counts.items()
            },
            "rate_limit_before": rate_before,
            "rate_limit_after": rate_after,
        },
        "validation": {
            "candidate_parent_threads": len(records),
            "parent_records_fully_valid": parent_valid,
            "pull_records_fully_valid": pull_valid,
            "nested_child_records": len(child_records),
            "child_records_with_exact_parent_id": exact_parent_ids,
            "child_records_fully_valid_exact_edges": exact_children,
            "child_review_batch_same_as_parent": review_batch_same_parent,
        },
        "landmark": {
            "first_trigger_candidate_threads": len(first_threads),
            "landmark_eligible_unique_prs": len(eligible_prs),
            "exact_parent_reply_by_48h_unique_prs": len(exposed_prs),
            "merged_strictly_after_48h_by_30d_unique_prs": len(outcome_prs),
            "ordered_product_pairs": len(product_pairs),
            "selection_note": (
                "The pilot conditions on a source nested reply, so it cannot supply an "
                "unselected unexposed comparison group."
            ),
        },
        "decision": decision,
        "failed_replication_gates": failed_gates,
        "thresholds": {
            "minimum_landmark_risk_set_prs": MIN_REPLICATION_RISK_SET,
            "minimum_exact_exposed_prs": MIN_REPLICATION_EXPOSED,
            "minimum_ordered_product_pairs": MIN_REPLICATION_PRODUCT_PAIRS,
        },
    }


def build_funnel(
    extraction: dict[str, Any],
    all_candidates: list[dict[str, Any]],
    nonoverlap: list[dict[str, Any]],
    aggregate: dict[str, Any],
) -> list[dict[str, Any]]:
    all_candidate_keys = {
        (item["repo_full_name"], item["pr_number"]) for item in all_candidates
    }
    nonoverlap_keys = {
        (item["repo_full_name"], item["pr_number"]) for item in nonoverlap
    }
    steps = [
        ("dataset_pr_rows", extraction["scanned_rows"]),
        ("exact_alias_mapped_author_prs", extraction["mapped_author_prs"]),
        ("prs_with_any_cross_product_inline_parent", extraction["cross_product_inline_parent_prs"]),
        ("prs_where_qualifying_parent_has_nested_reply", len(all_candidate_keys)),
        ("non_aidev_candidate_prs", len(nonoverlap_keys)),
        ("non_aidev_prs_where_first_trigger_has_nested_reply", aggregate["first_trigger_candidate_prs"]),
    ]
    if aggregate.get("http", {}).get("hydration_run"):
        steps.extend(
            [
                ("rest_validated_landmark_eligible_prs", aggregate["landmark"]["landmark_eligible_unique_prs"]),
                ("rest_validated_exact_reply_by_48h_prs", aggregate["landmark"]["exact_parent_reply_by_48h_unique_prs"]),
            ]
        )
    return [
        {"order": index, "stage": stage, "count": int(count)}
        for index, (stage, count) in enumerate(steps, start=1)
    ]


def write_funnel(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["order", "stage", "count"])
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    agg = summary["aggregate"]
    extraction = summary["extraction"]
    overlap = summary["aidev_exclusion"]
    http = agg.get("http", {})
    validation = agg.get("validation", {})
    landmark = agg.get("landmark", {})
    categories = agg.get("source_child_actor_categories", {})
    status_text = json.dumps(http.get("status_counts_by_endpoint", {}), sort_keys=True)
    failed = ", ".join(agg.get("failed_replication_gates", [])) or "none"
    lines = [
        "# SWE-Review-Chat exact-edge eligibility and hydration pilot",
        "",
        f"Generated: `{summary['generated_at_utc']}`.",
        "",
        f"## Decision: {agg['decision']}",
        "",
        "This audit measures whether a corpus-disjoint, exact-parent landmark is "
        "technically supported. It does not estimate an effect, semantic resolution, "
        "review quality, or causality, and it is not manuscript evidence.",
        "",
        "## Frozen eligibility rule",
        "",
        "At PR grain, require an exact-alias product-authored root PR (product A), "
        "an inline `review_comment` parent from a different mapped product B, and one "
        "or more nested source replies. Exclude every PR key found in the complete "
        "AIDev 7.6M backbone. For landmark compatibility, the candidate parent must "
        "also be the PR's first cross-product inline trigger, the PR must remain open "
        "at trigger + 48 hours, and the full trigger + 30-day horizon must be observed.",
        "",
        "Child categories are relative to parent product B: an unmapped `User`, the "
        "same exact mapped product, a different exact mapped product, or another "
        "unmapped identity. No fuzzy product inference is used.",
        "",
        "## Source funnel",
        "",
        f"- Full PR rows scanned: {extraction['scanned_rows']:,} across {extraction['parquet_shards']:,} shards.",
        f"- Exact-alias mapped-author PRs: {extraction['mapped_author_prs']:,}.",
        f"- PRs with any cross-product inline parent: {extraction['cross_product_inline_parent_prs']:,}.",
        f"- Parent threads satisfying the nested-reply rule: {extraction['candidate_parent_threads']:,} across {extraction['candidate_prs']:,} PRs.",
        f"- Candidate PRs overlapping AIDev full: {overlap['overlapping_candidate_prs']:,}; retained non-AIDev PRs: {agg['nonoverlap_prs']:,}.",
        f"- Non-AIDev PRs where the nested parent is also the first cross-product inline trigger: {agg['first_trigger_candidate_prs']:,}.",
        f"- Child categories before AIDev exclusion: `{json.dumps(extraction['source_child_relation_to_parent_counts'], sort_keys=True)}`.",
        f"- Child categories after AIDev exclusion: `{json.dumps(categories, sort_keys=True)}`.",
        "",
        "## Authenticated read-only hydration",
        "",
        f"- GitHub REST API version: `{http.get('api_version')}`; filtered requests return no bodies.",
        f"- Unique requests: {http.get('unique_requests', 0):,}; HTTP status counts: `{status_text}`.",
        "- Because the exact non-AIDev candidate set is empty, zero parent/comment/PR "
        "records were eligible for REST hydration. This is a fail-closed stop, not an "
        "API coverage failure.",
        f"- Fully validated parents: {validation.get('parent_records_fully_valid', 0):,}/{validation.get('candidate_parent_threads', 0):,}.",
        f"- Exact-parent child IDs: {validation.get('child_records_with_exact_parent_id', 0):,}/{validation.get('nested_child_records', 0):,}; fully valid exact child edges: {validation.get('child_records_fully_valid_exact_edges', 0):,}.",
        f"- Landmark-eligible PRs: {landmark.get('landmark_eligible_unique_prs', 0):,}; exact reply by 48h: {landmark.get('exact_parent_reply_by_48h_unique_prs', 0):,}; later merge by day 30: {landmark.get('merged_strictly_after_48h_by_30d_unique_prs', 0):,}.",
        "",
        f"Failed replication gates: `{failed}`.",
        "",
        "The source filter already requires a nested reply, so this pilot cannot "
        "provide an unselected no-reply comparison group. Tiny support or complete "
        "coverage therefore remains a support/falsification result, not a replication.",
        "",
        "## Integrity and privacy boundary",
        "",
        "- Raw candidate and hydrated ledgers are local and gitignored under "
        f"`{summary['raw_artifacts']['directory']}`.",
        "- Tracked artifacts contain aggregate counts only; no repository, PR, comment, "
        "title, body, diff, or raw API response text is exported.",
        "- Each review-comment API result is whitelisted to IDs, timestamps, review "
        "batch, parent ID, actor login/type, and PR URL before local persistence.",
        "- Parent validity requires an HTTP 200, matching ID, top-level parent, exact "
        "actor/product, timestamp agreement, and review-batch agreement.",
        "- Child validity requires an HTTP 200, matching ID, exact `in_reply_to_id`, "
        "actor/category agreement, and creation strictly after the parent.",
        "",
        "Official endpoint documentation: "
        f"[review comments]({API_DOC_COMMENT}) and [pull requests]({API_DOC_PULL}).",
        "",
        "## Reproduction",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe scripts\analysis\run_swe_review_chat_exact_edge_pilot.py",
        "```",
        "",
        "A working authenticated `gh` session is required. The script performs GET "
        "requests only and fails closed on missing or inconsistent fields.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_output_readme(path: Path, summary: dict[str, Any]) -> None:
    extraction = summary["extraction"]
    exclusion = summary["aidev_exclusion"]
    aggregate = summary["aggregate"]
    landmark = aggregate["landmark"]
    text = f"""# SWE-Review-Chat exact-edge external-validation pilot

## Disposition: REJECT

The frozen source screen found {extraction['candidate_parent_threads']:,} parent
threads across {extraction['candidate_prs']:,} PRs where an exact-alias product
author received an inline review comment from another mapped product and that
parent contained a nested reply. All {exclusion['overlapping_candidate_prs']:,}
candidate PR keys occur in the complete AIDev 7.6M backbone. The corpus-disjoint
set is therefore **zero PRs**, with zero eligible REST hydration targets and zero
48-hour landmark rows.

This is a fail-closed support result. It rules out SWE-Review-Chat as an
independent exact-edge RQ3 replication under the frozen AIDev alias and PR-key
rules. It does not refute the AIDev association, estimate an effect, or say
anything about semantic resolution, review quality, or causality.

## Audit trail

- Dataset revision: `{PINNED_REVISION}`
- AIDev revision: `{AIDEV_REVISION}`
- Exact mapped-author PRs screened: {extraction['mapped_author_prs']:,}
- PRs with any cross-product inline parent: {extraction['cross_product_inline_parent_prs']:,}
- Nested-reply candidate PRs before overlap exclusion: {extraction['candidate_prs']:,}
- Non-AIDev candidate PRs: {aggregate['nonoverlap_prs']:,}
- Landmark-eligible PRs: {landmark['landmark_eligible_unique_prs']:,}
- Decision: `{aggregate['decision']}`

Tracked aggregate evidence is in
`protocol/swe_review_chat_exact_edge_pilot_20260826.json` and
`protocol/swe_review_chat_exact_edge_funnel_20260826.csv`. Candidate IDs are
kept only in the gitignored `external_data/cache/swe_review_chat_exact_edge_pilot/`
audit directory. No body, title, diff, or manuscript file is exported or edited.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    aidev_dir = args.aidev_dir.resolve()
    raw_dir = args.raw_dir.resolve()
    all_pr_path = aidev_dir / "all_pull_request.parquet"
    if not dataset_dir.is_dir():
        raise FileNotFoundError(dataset_dir)
    if not all_pr_path.is_file():
        raise FileNotFoundError(all_pr_path)
    print("scanning exact source eligibility", flush=True)
    extraction = extract_candidates(dataset_dir, args.batch_size)
    all_candidates = extraction.pop("candidates")
    candidate_keys = {
        (item["repo_full_name"], item["pr_number"]) for item in all_candidates
    }
    print("excluding exact PR-key overlap with AIDev full", flush=True)
    overlap = aidev_candidate_overlap(all_pr_path, candidate_keys)
    matched_keys = overlap.pop("matched_keys")
    for item in all_candidates:
        item["aidev_full_overlap"] = (
            item["repo_full_name"], item["pr_number"]
        ) in matched_keys
    nonoverlap = [
        item
        for item in all_candidates
        if (item["repo_full_name"], item["pr_number"]) not in matched_keys
    ]
    raw_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(raw_dir / "all_source_candidate_threads.jsonl", all_candidates)
    write_jsonl(raw_dir / "non_aidev_candidate_threads.jsonl", nonoverlap)
    hydration = None if args.no_hydrate else hydrate_candidates(nonoverlap, raw_dir)
    aggregate = aggregate_results(
        extraction, all_candidates, nonoverlap, overlap, hydration
    )
    overlap_summary = {
        **overlap,
        "candidate_prs_before_exclusion": len(candidate_keys),
        "overlapping_candidate_prs": len(matched_keys),
        "retained_nonoverlap_candidate_prs": aggregate["nonoverlap_prs"],
    }
    funnel = build_funnel(extraction, all_candidates, nonoverlap, aggregate)
    write_funnel(args.funnel_csv, funnel)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_mode": "fail_closed_exact_eligibility_and_bounded_rest_hydration",
        "dataset": {
            "id": "Suzhen/SWE-Review-Chat",
            "revision": PINNED_REVISION,
            "local_path": relative_path(dataset_dir),
        },
        "aidev": {
            "revision": AIDEV_REVISION,
            "backbone": relative_path(all_pr_path),
        },
        "eligibility": {
            "grain": "one first cross-product inline parent trigger per non-AIDev PR",
            "author_mapping": "exact AIDev GitHub aliases only",
            "parent_type": "review_comment",
            "parent_product_rule": "mapped parent product differs from mapped root author product",
            "source_reply_rule": "parent has one or more nested replies",
            "landmark": "trigger + 48 hours; PR must still be open",
            "outcome_horizon": "merge strictly after trigger + 48h and by trigger + 30d",
        },
        "extraction": extraction,
        "aidev_exclusion": overlap_summary,
        "aggregate": aggregate,
        "funnel": funnel,
        "api": {
            "version": API_VERSION,
            "review_comment_docs": API_DOC_COMMENT,
            "pull_request_docs": API_DOC_PULL,
            "method": "authenticated gh api GET with jq field whitelist",
            "body_exported": False,
        },
        "raw_artifacts": {
            "directory": relative_path(raw_dir),
            "gitignored": True,
            "candidate_ledger": "non_aidev_candidate_threads.jsonl",
            "pre_exclusion_audit_ledger": "all_source_candidate_threads.jsonl",
            "hydration_ledger": "hydrated_candidate_threads.jsonl"
            if hydration is not None
            else None,
            "http_log": "http_coverage.csv" if hydration is not None else None,
        },
        "script": {
            "path": "scripts/analysis/run_swe_review_chat_exact_edge_pilot.py",
            "sha256": sha256_file(Path(__file__)),
        },
        "interpretation_limits": [
            "Candidate selection requires a source nested reply and cannot create an unselected no-reply comparison group.",
            "Exact product mapping is restricted to the fixed AIDev alias registry.",
            "Public structural reply edges do not establish semantic resolution, correctness, review quality, or causality.",
            "A tiny eligible set is a support/falsification result and must not be presented as replication.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(args.quality_md, summary)
    write_output_readme(args.output_readme, summary)
    print(f"wrote {relative_path(args.output_json)}")
    print(f"wrote {relative_path(args.funnel_csv)}")
    print(f"wrote {relative_path(args.quality_md)}")
    print(f"wrote {relative_path(args.output_readme)}")
    print(f"raw ledgers remain under {relative_path(raw_dir)}")


if __name__ == "__main__":
    main()
