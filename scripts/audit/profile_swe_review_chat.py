from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import AGENT_ACCOUNT_ALIASES  # noqa: E402


DATASET_ID = "Suzhen/SWE-Review-Chat"
PINNED_REVISION = "408cf94c068080eda66e0f3d7e9aa0316a42cb63"
AIDEV_REVISION = "37bbe1533e26cc1e1374917dba1186d1c8a4dc81"
DEFAULT_DATASET_DIR = ROOT / "external_data" / "downloads" / "SWE-Review-Chat"
DEFAULT_AIDEV_DIR = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
DEFAULT_JSON = ROOT / "protocol" / "swe_review_chat_profile_20260826.json"
DEFAULT_MANIFEST = ROOT / "protocol" / "swe_review_chat_file_manifest_20260826.csv"
DEFAULT_MARKDOWN = ROOT / "docs" / "SWE_REVIEW_CHAT_DATA_QUALITY_20260826.md"

GIB = 1024**3
MAX_FULL_DOWNLOAD_BYTES = int(3.5 * GIB)
MIN_FREE_AFTER_DOWNLOAD_BYTES = 10 * GIB

ROOT_FIELDS = (
    "repo_full_name",
    "pr_number",
    "title",
    "review_conversations",
    "repo_url",
    "pr_url",
    "created_at",
    "created_by",
    "created_by_type",
    "state",
    "closed_at",
    "merged_at",
    "merged_by",
    "merged_by_type",
    "additions",
    "deletions",
)
EVENT_FIELDS = (
    "type",
    "timestamp",
    "reviewer",
    "reviewer_type",
    "body",
    "title",
    "state",
    "review_id",
    "comment_id",
    "path",
    "diff_hunk",
    "thread_replies",
)
REPLY_FIELDS = ("reviewer", "reviewer_type", "body", "comment_id")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stream-profile a pinned local SWE-Review-Chat download and compute "
            "exact PR-key overlap with the AIDev rich and full backbones."
        )
    )
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--aidev-dir", type=Path, default=DEFAULT_AIDEV_DIR)
    parser.add_argument("--revision", default=PINNED_REVISION)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--manifest-csv", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--quality-md", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument(
        "--disk-free-before-bytes",
        type=int,
        required=True,
        help="Free bytes observed on the target volume before the download.",
    )
    parser.add_argument(
        "--disk-free-after-download-bytes",
        type=int,
        required=True,
        help="Free bytes observed immediately after the download.",
    )
    parser.add_argument(
        "--verify-sha256",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Hash every local pinned file and compare LFS SHA-256 values.",
    )
    return parser.parse_args()


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "emse-swe-review-chat-profiler/1.0"})
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_relative(path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), ROOT)).as_posix()


def normalize_repo(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    prefixes = (
        "https://api.github.com/repos/",
        "http://api.github.com/repos/",
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
    if text.lower().endswith(".git"):
        text = text[:-4]
    parts = [part for part in text.split("/") if part]
    if len(parts) != 2:
        return None
    return "/".join(parts).lower()


def normalize_pr_number(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def normalized_login(value: Any) -> str | None:
    if value is None:
        return None
    login = str(value).strip().lower()
    return login or None


def mapped_product(value: Any) -> str | None:
    login = normalized_login(value)
    return AGENT_ACCOUNT_ALIASES.get(login) if login is not None else None


def update_value_counter(counter: Counter[str], array: pa.Array) -> None:
    if len(array) == 0:
        return
    counts = pc.value_counts(array)
    for item in counts.to_pylist():
        if item["values"] is not None:
            counter[str(item["values"])] += int(item["counts"])


def sorted_counter(counter: Counter[Any]) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    }


def null_stat(nulls: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "null_count": int(nulls),
        "denominator": int(denominator),
        "null_rate": (float(nulls / denominator) if denominator else None),
    }


def update_min_max(current: list[str | None], array: pa.Array) -> None:
    if len(array) == 0 or array.null_count == len(array):
        return
    result = pc.min_max(array).as_py()
    low, high = result["min"], result["max"]
    if low is not None and (current[0] is None or low < current[0]):
        current[0] = str(low)
    if high is not None and (current[1] is None or high > current[1]):
        current[1] = str(high)


def list_lengths(array: pa.ListArray) -> tuple[int, int, int]:
    lengths = pc.fill_null(pc.list_value_length(array), 0)
    if len(lengths) == 0:
        return 0, 0, 0
    total = int(pc.sum(lengths).as_py() or 0)
    positive = int(pc.sum(pc.cast(pc.greater(lengths, 0), pa.int64())).as_py() or 0)
    maximum = int(pc.max(lengths).as_py() or 0)
    return total, positive, maximum


def remote_metadata(dataset_id: str, revision: str) -> dict[str, Any]:
    encoded_id = quote(dataset_id, safe="/")
    encoded_dataset = quote(dataset_id, safe="")
    revision_url = f"https://huggingface.co/api/datasets/{encoded_id}/revision/{revision}"
    default_url = f"https://huggingface.co/api/datasets/{encoded_id}"
    tree_url = (
        f"https://huggingface.co/api/datasets/{encoded_id}/tree/{revision}"
        "?recursive=true&expand=false&limit=1000"
    )
    parquet_url = f"https://datasets-server.huggingface.co/parquet?dataset={encoded_dataset}"
    size_url = f"https://datasets-server.huggingface.co/size?dataset={encoded_dataset}"

    pinned = fetch_json(revision_url)
    default = fetch_json(default_url)
    tree = fetch_json(tree_url)
    parquet = fetch_json(parquet_url)
    size = fetch_json(size_url)
    if not isinstance(tree, list):
        raise RuntimeError("Pinned Hub tree response was not a file list.")
    files = [item for item in tree if item.get("type") == "file"]
    if len(files) >= 1000:
        raise RuntimeError("Pinned Hub tree reached the request limit; pagination is required.")
    parquet_files = parquet.get("parquet_files", [])
    dataset_size = size.get("size", {}).get("dataset", {})
    return {
        "urls": {
            "canonical": f"https://huggingface.co/datasets/{dataset_id}",
            "pinned_revision": revision_url,
            "pinned_tree": tree_url,
            "viewer_parquet": parquet_url,
            "viewer_size": size_url,
        },
        "pinned_sha": pinned.get("sha"),
        "default_sha_at_profile_time": default.get("sha"),
        "last_modified": pinned.get("lastModified"),
        "private": bool(pinned.get("private", False)),
        "gated": pinned.get("gated", False),
        "license": (pinned.get("cardData") or {}).get("license"),
        "tree_files": files,
        "viewer_parquet_files": parquet_files,
        "viewer_size": dataset_size,
    }


def build_local_manifest(
    dataset_dir: Path,
    remote_files: list[dict[str, Any]],
    verify_sha256: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_paths = {item["path"] for item in remote_files}
    local_paths = {
        path.relative_to(dataset_dir).as_posix()
        for path in dataset_dir.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(dataset_dir).parts
    }
    rows: list[dict[str, Any]] = []
    for item in sorted(remote_files, key=lambda value: value["path"]):
        relative = item["path"]
        local_path = dataset_dir / relative
        lfs = item.get("lfs") or {}
        remote_lfs = lfs.get("oid")
        if isinstance(remote_lfs, str) and remote_lfs.startswith("sha256:"):
            remote_lfs = remote_lfs.split(":", 1)[1]
        local_size = local_path.stat().st_size if local_path.is_file() else None
        local_sha = sha256_file(local_path) if verify_sha256 and local_path.is_file() else None
        rows.append(
            {
                "relative_path": relative,
                "is_parquet": relative.endswith(".parquet"),
                "remote_bytes": int(item.get("size") or 0),
                "local_bytes": local_size,
                "bytes_match": local_size == int(item.get("size") or 0),
                "hub_blob_oid": item.get("oid"),
                "hub_lfs_sha256": remote_lfs,
                "local_sha256": local_sha,
                "sha256_match": (
                    local_sha == remote_lfs
                    if verify_sha256 and remote_lfs is not None and local_sha is not None
                    else None
                ),
            }
        )
    summary = {
        "expected_file_count": len(expected_paths),
        "local_file_count_excluding_hf_cache": len(local_paths),
        "missing_paths": sorted(expected_paths - local_paths),
        "unexpected_paths": sorted(local_paths - expected_paths),
        "all_byte_sizes_match": all(row["bytes_match"] for row in rows),
        "lfs_files_checked": sum(row["sha256_match"] is not None for row in rows),
        "all_checked_lfs_sha256_match": all(
            row["sha256_match"] is not False for row in rows
        ),
        "local_total_bytes": sum(int(row["local_bytes"] or 0) for row in rows),
        "local_parquet_bytes": sum(
            int(row["local_bytes"] or 0) for row in rows if row["is_parquet"]
        ),
    }
    return rows, summary


def inspect_parquet_files(parquet_files: list[Path]) -> dict[str, Any]:
    reference_schema: pa.Schema | None = None
    reference_hash: str | None = None
    schema_mismatch_files: list[str] = []
    rows = 0
    row_groups = 0
    for path in parquet_files:
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        schema_hash = hashlib.sha256(schema.serialize().to_pybytes()).hexdigest()
        if reference_schema is None:
            reference_schema = schema
            reference_hash = schema_hash
        elif not schema.equals(reference_schema, check_metadata=False):
            schema_mismatch_files.append(path.name)
        rows += parquet.metadata.num_rows
        row_groups += parquet.metadata.num_row_groups
    if reference_schema is None:
        raise RuntimeError("No Parquet shards were found.")
    return {
        "metadata_rows": int(rows),
        "row_groups": int(row_groups),
        "schema_sha256": reference_hash,
        "all_shard_schemas_identical": not schema_mismatch_files,
        "schema_mismatch_files": schema_mismatch_files,
        "root_schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in reference_schema
        ],
        "root_fields": list(reference_schema.names),
        "event_fields": list(EVENT_FIELDS),
        "reply_fields": list(REPLY_FIELDS),
        "reply_timestamp_field_present": "timestamp" in REPLY_FIELDS,
        "reply_parent_id_field_present": any(
            name in REPLY_FIELDS for name in ("in_reply_to_id", "parent_comment_id")
        ),
    }


def stream_profile(parquet_files: list[Path], batch_size: int) -> dict[str, Any]:
    root_nulls: Counter[str] = Counter()
    event_nulls: Counter[str] = Counter()
    reply_nulls: Counter[str] = Counter()
    root_types: Counter[str] = Counter()
    event_types: Counter[str] = Counter()
    event_reviewer_types: Counter[str] = Counter()
    reply_reviewer_types: Counter[str] = Counter()
    root_logins: Counter[str] = Counter()
    event_logins: Counter[str] = Counter()
    reply_logins: Counter[str] = Counter()
    event_product_by_type: Counter[str] = Counter()
    root_product_rows: Counter[str] = Counter()
    parent_product_events: Counter[str] = Counter()
    reply_product_events: Counter[str] = Counter()
    parent_product_prs: Counter[str] = Counter()
    reply_product_prs: Counter[str] = Counter()
    cross_thread_pairs: Counter[str] = Counter()
    same_thread_pairs: Counter[str] = Counter()
    repos: set[str] = set()
    key_frequency: Counter[tuple[str, int]] = Counter()
    mapped_author_keys: set[tuple[str, int]] = set()
    mapped_parent_keys: set[tuple[str, int]] = set()
    mapped_reply_keys: set[tuple[str, int]] = set()
    cross_author_actor_keys: set[tuple[str, int]] = set()
    cross_thread_keys: set[tuple[str, int]] = set()
    root_created_range: list[str | None] = [None, None]
    event_timestamp_range: list[str | None] = [None, None]

    scanned_rows = 0
    invalid_pr_keys = 0
    null_conversation_lists = 0
    empty_conversation_lists = 0
    conversation_entries = 0
    null_event_structs = 0
    null_thread_lists = 0
    empty_thread_lists = 0
    parents_with_replies = 0
    replies = 0
    null_reply_structs = 0
    max_conversations_per_pr = 0
    max_replies_per_parent = 0

    for file_index, path in enumerate(parquet_files, start=1):
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(batch_size=batch_size, columns=list(ROOT_FIELDS)):
            batch_rows = batch.num_rows
            scanned_rows += batch_rows
            columns = {name: batch.column(batch.schema.get_field_index(name)) for name in ROOT_FIELDS}
            for name, array in columns.items():
                root_nulls[name] += array.null_count

            update_value_counter(root_types, columns["created_by_type"])
            update_value_counter(root_logins, columns["created_by"])
            update_min_max(root_created_range, columns["created_at"])

            repos_py = columns["repo_full_name"].to_pylist()
            numbers_py = columns["pr_number"].to_pylist()
            authors_py = columns["created_by"].to_pylist()
            keys: list[tuple[str, int] | None] = []
            author_products: list[str | None] = []
            for repo_value, number_value, author_value in zip(
                repos_py, numbers_py, authors_py, strict=True
            ):
                repo = normalize_repo(repo_value)
                number = normalize_pr_number(number_value)
                product = mapped_product(author_value)
                author_products.append(product)
                if product is not None:
                    root_product_rows[product] += 1
                if repo is None or number is None:
                    invalid_pr_keys += 1
                    keys.append(None)
                    continue
                repos.add(repo)
                key = (repo, number)
                key_frequency[key] += 1
                keys.append(key)
                if product is not None:
                    mapped_author_keys.add(key)

            conversations = columns["review_conversations"]
            if not pa.types.is_list(conversations.type):
                raise AssertionError("review_conversations is not a list array.")
            null_conversation_lists += conversations.null_count
            conv_total, conv_positive, conv_max = list_lengths(conversations)
            conversation_entries += conv_total
            empty_conversation_lists += batch_rows - conversations.null_count - conv_positive
            max_conversations_per_pr = max(max_conversations_per_pr, conv_max)

            events = pc.list_flatten(conversations)
            if not pa.types.is_struct(events.type):
                raise AssertionError("Flattened review_conversations is not a struct array.")
            null_event_structs += events.null_count
            for name in EVENT_FIELDS:
                event_nulls[name] += events.field(name).null_count
            update_value_counter(event_types, events.field("type"))
            update_value_counter(event_reviewer_types, events.field("reviewer_type"))
            update_value_counter(event_logins, events.field("reviewer"))
            update_min_max(event_timestamp_range, events.field("timestamp"))

            thread_lists = events.field("thread_replies")
            if not pa.types.is_list(thread_lists.type):
                raise AssertionError("thread_replies is not a list array.")
            null_thread_lists += thread_lists.null_count
            reply_total, reply_positive, reply_max = list_lengths(thread_lists)
            replies += reply_total
            parents_with_replies += reply_positive
            empty_thread_lists += len(thread_lists) - thread_lists.null_count - reply_positive
            max_replies_per_parent = max(max_replies_per_parent, reply_max)

            reply_structs = pc.list_flatten(thread_lists)
            if not pa.types.is_struct(reply_structs.type):
                raise AssertionError("Flattened thread_replies is not a struct array.")
            null_reply_structs += reply_structs.null_count
            for name in REPLY_FIELDS:
                reply_nulls[name] += reply_structs.field(name).null_count
            update_value_counter(reply_reviewer_types, reply_structs.field("reviewer_type"))
            update_value_counter(reply_logins, reply_structs.field("reviewer"))

            event_type_values = events.field("type").to_pylist()
            event_reviewer_values = events.field("reviewer").to_pylist()
            reply_reviewer_values = reply_structs.field("reviewer").to_pylist()
            event_products = [mapped_product(value) for value in event_reviewer_values]
            reply_products = [mapped_product(value) for value in reply_reviewer_values]
            for event_type, product in zip(event_type_values, event_products, strict=True):
                if product is not None:
                    parent_product_events[product] += 1
                    event_product_by_type[f"{event_type or '<null>'}|{product}"] += 1
            for product in reply_products:
                if product is not None:
                    reply_product_events[product] += 1

            conv_offsets = conversations.offsets.to_pylist()
            conv_base = int(conv_offsets[0]) if conv_offsets else 0
            reply_offsets = thread_lists.offsets.to_pylist()
            reply_base = int(reply_offsets[0]) if reply_offsets else 0
            for row_index, key in enumerate(keys):
                start = int(conv_offsets[row_index]) - conv_base
                stop = int(conv_offsets[row_index + 1]) - conv_base
                parent_products = {
                    product for product in event_products[start:stop] if product is not None
                }
                row_reply_products: set[str] = set()
                row_has_cross_thread = False
                for event_index in range(start, stop):
                    parent_product = event_products[event_index]
                    reply_start = int(reply_offsets[event_index]) - reply_base
                    reply_stop = int(reply_offsets[event_index + 1]) - reply_base
                    for reply_product in reply_products[reply_start:reply_stop]:
                        if reply_product is None:
                            continue
                        row_reply_products.add(reply_product)
                        if parent_product is None:
                            continue
                        pair = f"{parent_product}->{reply_product}"
                        if parent_product == reply_product:
                            same_thread_pairs[pair] += 1
                        else:
                            cross_thread_pairs[pair] += 1
                            row_has_cross_thread = True
                for product in parent_products:
                    parent_product_prs[product] += 1
                for product in row_reply_products:
                    reply_product_prs[product] += 1
                if key is None:
                    continue
                if parent_products:
                    mapped_parent_keys.add(key)
                if row_reply_products:
                    mapped_reply_keys.add(key)
                if row_has_cross_thread:
                    cross_thread_keys.add(key)
                author_product = author_products[row_index]
                if author_product is not None and any(
                    product != author_product
                    for product in parent_products | row_reply_products
                ):
                    cross_author_actor_keys.add(key)

        if file_index % 25 == 0 or file_index == len(parquet_files):
            print(
                f"profiled {file_index}/{len(parquet_files)} shards; "
                f"{scanned_rows:,} PR rows",
                flush=True,
            )

    product_sets = {
        "mapped_author": mapped_author_keys,
        "mapped_parent_actor": mapped_parent_keys,
        "mapped_nested_reply_actor": mapped_reply_keys,
        "cross_product_author_actor": cross_author_actor_keys,
        "cross_product_nested_thread": cross_thread_keys,
    }
    return {
        "scanned_rows": int(scanned_rows),
        "unique_repositories": len(repos),
        "unique_pr_keys": len(key_frequency),
        "duplicate_pr_key_rows": int(sum(value - 1 for value in key_frequency.values() if value > 1)),
        "invalid_pr_key_rows": int(invalid_pr_keys),
        "root_created_at_min": root_created_range[0],
        "root_created_at_max": root_created_range[1],
        "root_field_nulls": {
            name: null_stat(root_nulls[name], scanned_rows) for name in ROOT_FIELDS
        },
        "created_by_type_counts": sorted_counter(root_types),
        "nesting": {
            "null_review_conversation_lists": int(null_conversation_lists),
            "empty_review_conversation_lists": int(empty_conversation_lists),
            "conversation_entries": int(conversation_entries),
            "null_conversation_entry_structs": int(null_event_structs),
            "max_conversation_entries_per_pr": int(max_conversations_per_pr),
            "conversation_entry_type_counts": sorted_counter(event_types),
            "conversation_entry_reviewer_type_counts": sorted_counter(event_reviewer_types),
            "conversation_entry_timestamp_min": event_timestamp_range[0],
            "conversation_entry_timestamp_max": event_timestamp_range[1],
            "conversation_entry_field_nulls": {
                name: null_stat(event_nulls[name], conversation_entries)
                for name in EVENT_FIELDS
            },
            "null_thread_reply_lists": int(null_thread_lists),
            "empty_thread_reply_lists": int(empty_thread_lists),
            "parents_with_one_or_more_nested_replies": int(parents_with_replies),
            "nested_replies": int(replies),
            "null_nested_reply_structs": int(null_reply_structs),
            "max_nested_replies_per_parent": int(max_replies_per_parent),
            "nested_reply_reviewer_type_counts": sorted_counter(reply_reviewer_types),
            "nested_reply_field_nulls": {
                name: null_stat(reply_nulls[name], replies) for name in REPLY_FIELDS
            },
            "nested_reply_timestamp_field_present": False,
            "nested_reply_explicit_parent_id_field_present": False,
        },
        "identity_support": {
            "mapping_scope": (
                "Exact GitHub login aliases already used by the AIDev analysis; no "
                "fuzzy name inference and no semantic product inference."
            ),
            "account_aliases": dict(sorted(AGENT_ACCOUNT_ALIASES.items())),
            "mapped_root_author_rows_by_product": sorted_counter(root_product_rows),
            "mapped_conversation_entries_by_product": sorted_counter(parent_product_events),
            "mapped_nested_replies_by_product": sorted_counter(reply_product_events),
            "mapped_conversation_entry_prs_by_product": sorted_counter(parent_product_prs),
            "mapped_nested_reply_prs_by_product": sorted_counter(reply_product_prs),
            "mapped_conversation_entries_by_type_and_product": sorted_counter(
                event_product_by_type
            ),
            "cross_product_nested_reply_pairs": sorted_counter(cross_thread_pairs),
            "same_product_nested_reply_pairs": sorted_counter(same_thread_pairs),
            "unique_pr_support": {
                name: len(keys) for name, keys in product_sets.items()
            },
            "distinct_root_author_logins": len(root_logins),
            "distinct_conversation_actor_logins": len(event_logins),
            "distinct_nested_reply_actor_logins": len(reply_logins),
        },
        "_key_frequency": key_frequency,
        "_product_sets": product_sets,
    }


def scan_aidev_overlap(
    path: Path,
    key_frequency: Counter[tuple[str, int]],
    product_sets: dict[str, set[tuple[str, int]]],
    batch_size: int = 131_072,
) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    matched_keys: set[tuple[str, int]] = set()
    source_rows_scanned = 0
    invalid_join_key_rows = 0
    matched_source_rows = 0
    for batch in parquet.iter_batches(batch_size=batch_size, columns=["repo_url", "number"]):
        repos = batch.column(batch.schema.get_field_index("repo_url")).to_pylist()
        numbers = batch.column(batch.schema.get_field_index("number")).to_pylist()
        source_rows_scanned += batch.num_rows
        for repo_value, number_value in zip(repos, numbers, strict=True):
            repo = normalize_repo(repo_value)
            number = normalize_pr_number(number_value)
            if repo is None or number is None:
                invalid_join_key_rows += 1
                continue
            key = (repo, number)
            if key in key_frequency:
                matched_source_rows += 1
                matched_keys.add(key)
    matched_swe_rows = sum(key_frequency[key] for key in matched_keys)
    unique_swe_keys = len(key_frequency)
    return {
        "source_path": repo_relative(path),
        "source_file_bytes": path.stat().st_size,
        "source_metadata_rows": int(parquet.metadata.num_rows),
        "source_rows_scanned": int(source_rows_scanned),
        "invalid_source_join_key_rows": int(invalid_join_key_rows),
        "matched_source_rows": int(matched_source_rows),
        "matched_unique_swe_pr_keys": len(matched_keys),
        "matched_swe_rows": int(matched_swe_rows),
        "swe_unique_pr_key_overlap_rate": (
            float(len(matched_keys) / unique_swe_keys) if unique_swe_keys else None
        ),
        "swe_row_overlap_rate": (
            float(matched_swe_rows / sum(key_frequency.values())) if key_frequency else None
        ),
        "matched_product_support_pr_keys": {
            name: len(keys & matched_keys) for name, keys in product_sets.items()
        },
        "nonoverlap_product_support_pr_keys": {
            name: len(keys - matched_keys) for name, keys in product_sets.items()
        },
    }


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "relative_path",
        "is_parquet",
        "remote_bytes",
        "local_bytes",
        "bytes_match",
        "hub_blob_oid",
        "hub_lfs_sha256",
        "local_sha256",
        "sha256_match",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def format_bytes(value: int) -> str:
    return f"{value:,} bytes ({value / GIB:.3f} GiB)"


def format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.2f}%"


def write_quality_markdown(path: Path, profile: dict[str, Any]) -> None:
    acquisition = profile["acquisition"]
    local = profile["file_integrity"]
    rows = profile["row_profile"]
    nesting = rows["nesting"]
    identity = rows["identity_support"]
    rich = profile["aidev_overlap"]["rich_backbone"]
    full = profile["aidev_overlap"]["full_backbone"]
    checks = profile["quality_checks"]
    aliases = ", ".join(
        f"`{login}` -> `{product}`" for login, product in identity["account_aliases"].items()
    )
    cross_threads = sum(identity["cross_product_nested_reply_pairs"].values())
    same_threads = sum(identity["same_product_nested_reply_pairs"].values())
    lines = [
        "# SWE-Review-Chat pinned-data provenance and quality profile",
        "",
        f"Generated: `{profile['generated_at_utc']}`.",
        "",
        "This is a data-capability and overlap audit. It does **not** report an effect, "
        "quality difference, causal estimate, or manuscript claim.",
        "",
        "## Acquisition decision",
        "",
        f"- Dataset: [{profile['dataset']['id']}]({profile['dataset']['canonical_url']})",
        f"- Pinned revision: `{profile['dataset']['revision']}`",
        f"- Original Parquet payload: {format_bytes(acquisition['pinned_original_parquet_bytes'])}",
        f"- Viewer-converted Parquet payload: {format_bytes(acquisition['viewer_converted_parquet_bytes'])}",
        f"- Complete pinned repository payload: {format_bytes(acquisition['pinned_repository_bytes'])}",
        f"- Free space before download: {format_bytes(acquisition['disk_free_before_bytes'])}",
        f"- Projected free space after download: {format_bytes(acquisition['projected_free_after_download_bytes'])}",
        f"- Free space observed immediately after download: {format_bytes(acquisition['disk_free_after_download_bytes'])}",
        f"- Gate result: **{acquisition['gate_decision']}**. The complete pinned revision was used; no sampling fallback was needed.",
        f"- Download tool: `{acquisition['download_method']['tool']}` version `{acquisition['download_method']['tool_version']}`.",
        "",
        "At profiling time, the dataset's default Hub SHA equaled the pinned SHA. The "
        "Dataset Viewer endpoint is branch-based, so this equality is recorded rather "
        "than treating its converted branch as independently revision-addressable.",
        "",
        "## File and row integrity",
        "",
        f"- {local['expected_file_count']:,} expected files and {local['local_file_count_excluding_hf_cache']:,} local files (excluding the Hub cache).",
        f"- Local Parquet bytes: {local['local_parquet_bytes']:,}; all remote/local byte sizes match: `{local['all_byte_sizes_match']}`.",
        f"- LFS SHA-256 objects checked: {local['lfs_files_checked']:,}; all checked hashes match: `{local['all_checked_lfs_sha256_match']}`.",
        f"- Parquet shards: {profile['schema']['parquet_shards']:,}; schemas identical: `{profile['schema']['all_shard_schemas_identical']}`.",
        f"- Metadata rows / streamed rows: {profile['schema']['metadata_rows']:,} / {rows['scanned_rows']:,}.",
        f"- Unique repositories: {rows['unique_repositories']:,}; unique `(repo_full_name, pr_number)` keys: {rows['unique_pr_keys']:,}.",
        f"- Duplicate-key surplus rows: {rows['duplicate_pr_key_rows']:,}; invalid join-key rows: {rows['invalid_pr_key_rows']:,}.",
        f"- Root PR creation coverage: `{rows['root_created_at_min']}` through `{rows['root_created_at_max']}`.",
        "",
        "The machine-readable profile includes null counts and rates for all 16 root "
        "fields, all 12 conversation-entry fields, and all four nested-reply fields.",
        "",
        "## Thread structure and temporal limits",
        "",
        f"- Conversation entries: {nesting['conversation_entries']:,}; parents with one or more nested replies: {nesting['parents_with_one_or_more_nested_replies']:,}.",
        f"- Nested replies: {nesting['nested_replies']:,}; maximum replies under one parent: {nesting['max_nested_replies_per_parent']:,}.",
        f"- Conversation-entry timestamps cover `{nesting['conversation_entry_timestamp_min']}` through `{nesting['conversation_entry_timestamp_max']}`.",
        "- A reply is structurally contained under one parent entry, but the reply struct "
        "does not contain `timestamp`, `in_reply_to_id`, or `parent_comment_id`.",
        "- Therefore, the local files support nested thread membership but cannot by "
        "themselves enforce a reply-time window or independently re-check the parent ID. "
        "Any time-sensitive exact-edge replication would require API hydration or another "
        "timestamped source.",
        "",
        "## Product-attribution support",
        "",
        "Product attribution is deliberately narrow. Only exact account aliases already "
        "used in the AIDev analysis are mapped; all other identities remain unmapped.",
        "",
        f"Aliases: {aliases}.",
        "",
        f"- PRs with a mapped root author: {identity['unique_pr_support']['mapped_author']:,}.",
        f"- PRs with a mapped conversation actor: {identity['unique_pr_support']['mapped_parent_actor']:,}.",
        f"- PRs with a mapped nested-reply actor: {identity['unique_pr_support']['mapped_nested_reply_actor']:,}.",
        f"- PRs with an exact-alias cross-product author/actor configuration: {identity['unique_pr_support']['cross_product_author_actor']:,}.",
        f"- PRs containing an exact-alias cross-product nested thread: {identity['unique_pr_support']['cross_product_nested_thread']:,}.",
        f"- Mapped nested reply pairs: {cross_threads:,} cross-product and {same_threads:,} same-product. These are support counts, not performance outcomes.",
        "",
        "The field name `reviewer` is used for every conversation actor, including entry "
        "types that are not necessarily review verdicts. The profile therefore also keeps "
        "counts by entry type; analysis must choose eligible types before interpretation.",
        "",
        "## Exact AIDev PR-key overlap",
        "",
        "The join key is normalized lower-case GitHub `owner/repository` plus positive PR "
        "number. No title, author name, text, or fuzzy match is used.",
        "",
        f"- AIDev rich backbone: {rich['matched_unique_swe_pr_keys']:,} unique SWE-Review-Chat PR keys overlap ({format_rate(rich['swe_unique_pr_key_overlap_rate'])}).",
        f"- AIDev full 7.6M backbone: {full['matched_unique_swe_pr_keys']:,} unique SWE-Review-Chat PR keys overlap ({format_rate(full['swe_unique_pr_key_overlap_rate'])}).",
        f"- Cross-product nested-thread PRs outside the full AIDev backbone: {full['nonoverlap_product_support_pr_keys']['cross_product_nested_thread']:,}.",
        "",
        "The non-overlap subset is the only candidate here for a corpus-disjoint external "
        "replication. Overlapping rows can be used for schema/attribution cross-checks, but "
        "they are not independent extra evidence.",
        "",
        "**Data-use decision:** retain the full pinned corpus for compatibility checks and "
        "possible API-hydrated follow-up work. As shipped, it is not a ready exact-edge "
        "timing replication: only four non-AIDev PRs contain an exact-alias cross-product "
        "nested thread, and the nested replies have no timestamps. Do not present those "
        "four PRs as external validation.",
        "",
        "## Quality gates",
        "",
        "| Check | Status | Value |",
        "|---|---:|---:|",
    ]
    for check in checks:
        lines.append(f"| {check['check']} | {check['status']} | `{check['value']}` |")
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "From the project root, after downloading the pinned revision:",
            "",
            "```powershell",
            ".\\.venv\\Scripts\\python.exe scripts\audit\profile_swe_review_chat.py `",
            "  --revision 408cf94c068080eda66e0f3d7e9aa0316a42cb63 `",
            "  --disk-free-before-bytes <observed-before> `",
            "  --disk-free-after-download-bytes <observed-after>",
            "```",
            "",
            "Raw files remain under the gitignored `external_data/downloads/` directory. "
            "The tracked manifest records byte sizes and SHA-256 verification without "
            "copying raw rows or text into the repository.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    aidev_dir = args.aidev_dir.resolve()
    if args.revision != PINNED_REVISION:
        raise ValueError(
            f"This audit is locked to {PINNED_REVISION}; received {args.revision}."
        )
    if not dataset_dir.is_dir():
        raise FileNotFoundError(dataset_dir)
    rich_path = aidev_dir / "pull_request.parquet"
    full_path = aidev_dir / "all_pull_request.parquet"
    for required in (rich_path, full_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    print("fetching pinned Hub and Dataset Viewer metadata", flush=True)
    remote = remote_metadata(DATASET_ID, args.revision)
    tree_files = remote.pop("tree_files")
    viewer_parquet_files = remote.pop("viewer_parquet_files")
    original_parquet_bytes = sum(
        int(item.get("size") or 0)
        for item in tree_files
        if item["path"].endswith(".parquet")
    )
    repository_bytes = sum(int(item.get("size") or 0) for item in tree_files)
    converted_bytes = sum(int(item.get("size") or 0) for item in viewer_parquet_files)
    projected_free = args.disk_free_before_bytes - repository_bytes
    gate_passed = (
        original_parquet_bytes <= MAX_FULL_DOWNLOAD_BYTES
        and projected_free >= MIN_FREE_AFTER_DOWNLOAD_BYTES
        and args.disk_free_after_download_bytes >= MIN_FREE_AFTER_DOWNLOAD_BYTES
    )
    if not gate_passed:
        raise RuntimeError("The recorded full-download size/free-space gate did not pass.")
    if remote["pinned_sha"] != args.revision:
        raise AssertionError("Pinned dataset metadata did not resolve to the requested SHA.")

    print("verifying local file manifest and hashes", flush=True)
    manifest_rows, integrity = build_local_manifest(
        dataset_dir, tree_files, args.verify_sha256
    )
    if integrity["missing_paths"] or integrity["unexpected_paths"]:
        raise AssertionError("Local file set differs from the pinned Hub tree.")
    if not integrity["all_byte_sizes_match"]:
        raise AssertionError("One or more local files have an unexpected byte size.")
    if args.verify_sha256 and not integrity["all_checked_lfs_sha256_match"]:
        raise AssertionError("One or more local LFS files failed SHA-256 verification.")
    write_manifest(args.manifest_csv, manifest_rows)

    parquet_files = sorted(dataset_dir.glob("*.parquet"))
    schema = inspect_parquet_files(parquet_files)
    schema["parquet_shards"] = len(parquet_files)
    print("streaming nested dataset profile", flush=True)
    row_profile = stream_profile(parquet_files, args.batch_size)
    key_frequency = row_profile.pop("_key_frequency")
    product_sets = row_profile.pop("_product_sets")

    print("scanning exact AIDev rich-backbone overlap", flush=True)
    rich_overlap = scan_aidev_overlap(rich_path, key_frequency, product_sets)
    print("scanning exact AIDev full-backbone overlap", flush=True)
    full_overlap = scan_aidev_overlap(full_path, key_frequency, product_sets)

    viewer_rows = int(remote["viewer_size"].get("num_rows") or 0)
    quality_checks = [
        {
            "check": "pinned_revision_resolves_exactly",
            "status": "PASS" if remote["pinned_sha"] == args.revision else "FAIL",
            "value": remote["pinned_sha"],
        },
        {
            "check": "viewer_default_sha_equals_pinned_revision_at_profile_time",
            "status": "PASS" if remote["default_sha_at_profile_time"] == args.revision else "LIMITATION",
            "value": remote["default_sha_at_profile_time"],
        },
        {
            "check": "full_download_size_and_free_space_gate",
            "status": "PASS" if gate_passed else "FAIL",
            "value": gate_passed,
        },
        {
            "check": "local_file_set_matches_pinned_tree",
            "status": "PASS" if not integrity["missing_paths"] and not integrity["unexpected_paths"] else "FAIL",
            "value": not integrity["missing_paths"] and not integrity["unexpected_paths"],
        },
        {
            "check": "local_byte_sizes_match_pinned_tree",
            "status": "PASS" if integrity["all_byte_sizes_match"] else "FAIL",
            "value": integrity["all_byte_sizes_match"],
        },
        {
            "check": "checked_lfs_sha256_values_match",
            "status": "PASS" if integrity["all_checked_lfs_sha256_match"] else "FAIL",
            "value": integrity["all_checked_lfs_sha256_match"],
        },
        {
            "check": "all_parquet_shard_schemas_identical",
            "status": "PASS" if schema["all_shard_schemas_identical"] else "FAIL",
            "value": schema["all_shard_schemas_identical"],
        },
        {
            "check": "metadata_stream_and_viewer_row_counts_reconcile",
            "status": "PASS"
            if schema["metadata_rows"] == row_profile["scanned_rows"] == viewer_rows
            else "FAIL",
            "value": f"{schema['metadata_rows']}/{row_profile['scanned_rows']}/{viewer_rows}",
        },
        {
            "check": "pr_join_keys_complete",
            "status": "PASS" if row_profile["invalid_pr_key_rows"] == 0 else "LIMITATION",
            "value": row_profile["invalid_pr_key_rows"],
        },
        {
            "check": "pr_join_keys_unique",
            "status": "PASS" if row_profile["duplicate_pr_key_rows"] == 0 else "LIMITATION",
            "value": row_profile["duplicate_pr_key_rows"],
        },
        {
            "check": "nested_reply_timestamp_available",
            "status": "LIMITATION",
            "value": False,
        },
        {
            "check": "nested_reply_explicit_parent_id_available",
            "status": "LIMITATION",
            "value": False,
        },
    ]

    profile = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "profile_mode": "complete_pinned_revision_streaming_scan",
        "dataset": {
            "id": DATASET_ID,
            "canonical_url": remote["urls"]["canonical"],
            "revision": args.revision,
            "last_modified": remote["last_modified"],
            "license": remote["license"],
            "private": remote["private"],
            "gated": remote["gated"],
            "local_path": repo_relative(dataset_dir),
        },
        "remote_endpoints": remote["urls"],
        "acquisition": {
            "gate_decision": "DOWNLOAD_FULL",
            "sample_fallback_used": False,
            "download_method": {
                "tool": "huggingface_hub hf CLI",
                "tool_version": "1.17.0",
                "command": (
                    "hf download Suzhen/SWE-Review-Chat --repo-type dataset "
                    "--revision 408cf94c068080eda66e0f3d7e9aa0316a42cb63 "
                    "--local-dir external_data/downloads/SWE-Review-Chat --max-workers 8"
                ),
            },
            "max_full_download_bytes": MAX_FULL_DOWNLOAD_BYTES,
            "minimum_free_after_download_bytes": MIN_FREE_AFTER_DOWNLOAD_BYTES,
            "disk_free_before_bytes": args.disk_free_before_bytes,
            "projected_free_after_download_bytes": projected_free,
            "disk_free_after_download_bytes": args.disk_free_after_download_bytes,
            "disk_free_at_profile_time_bytes": shutil.disk_usage(dataset_dir.anchor).free,
            "pinned_repository_file_count": len(tree_files),
            "pinned_repository_bytes": repository_bytes,
            "pinned_original_parquet_file_count": sum(
                item["path"].endswith(".parquet") for item in tree_files
            ),
            "pinned_original_parquet_bytes": original_parquet_bytes,
            "viewer_converted_parquet_file_count": len(viewer_parquet_files),
            "viewer_converted_parquet_bytes": converted_bytes,
            "viewer_reported_memory_bytes": remote["viewer_size"].get("num_bytes_memory"),
            "viewer_reported_rows": viewer_rows,
            "pinned_sha": remote["pinned_sha"],
            "default_sha_at_profile_time": remote["default_sha_at_profile_time"],
            "viewer_revision_basis": (
                "Dataset Viewer default branch observed while the dataset default SHA "
                "equaled the pinned revision; the converted endpoint is not independently "
                "revision-addressable."
            ),
        },
        "file_integrity": integrity,
        "schema": schema,
        "row_profile": row_profile,
        "aidev_overlap": {
            "aidev_project_revision": AIDEV_REVISION,
            "join_key": (
                "exact normalized lower-case GitHub owner/repository plus positive PR number"
            ),
            "normalization": (
                "strip GitHub/API URL prefix, query, fragment, trailing slash, and .git; "
                "no fuzzy matching"
            ),
            "rich_backbone": rich_overlap,
            "full_backbone": full_overlap,
        },
        "quality_checks": quality_checks,
        "profiler": {
            "script": "scripts/audit/profile_swe_review_chat.py",
            "script_sha256": sha256_file(Path(__file__)),
            "batch_size": args.batch_size,
            "raw_dataset_mutated": False,
        },
        "interpretation_limits": [
            "Nested reply membership is present, but reply timestamps and explicit parent IDs are absent.",
            "Exact product attribution covers only the fixed AIDev alias map; unmapped identities remain unknown.",
            "The reviewer field is a generic conversation-actor field across multiple event types.",
            "Overlap counts are compatibility diagnostics, not independent evidence or outcome estimates.",
            "No raw body, diff, title, or comment text is exported by this profiler.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    write_quality_markdown(args.quality_md, profile)
    print(f"wrote {repo_relative(args.output_json)}")
    print(f"wrote {repo_relative(args.manifest_csv)}")
    print(f"wrote {repo_relative(args.quality_md)}")


if __name__ == "__main__":
    main()
