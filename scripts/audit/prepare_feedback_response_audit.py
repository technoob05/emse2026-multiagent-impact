from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.analysis.run_feedback_routing_models import (  # noqa: E402
    DATA,
    feedback_with_text,
)
from scripts.analysis.run_response_ownership_analysis import add_owner  # noqa: E402

INPUT = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "feedback_response_audit"
SCHEMA = ROOT / "protocol" / "feedback_response_label_schema.json"
SEED = 20260825
QUOTAS = {
    "direct_inline_reply": 120,
    "subsequent_review": 140,
    "subsequent_pr_comment": 140,
    "force_push": 80,
    "no_observed_action": 120,
}

SECRET_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9_]{20,}\b|\bsk-[A-Za-z0-9_-]{20,}\b|\bBearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(value: object, limit: int = 2500) -> tuple[str, str, bool, bool]:
    text = "" if value is None or pd.isna(value) else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    contains_secret = bool(SECRET_PATTERN.search(text))
    normalized = re.sub(r"https?://\S+", "[URL]", text)
    normalized = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return normalized[:limit], digest, len(normalized) > limit, contains_secret


def response_text_lookup() -> pd.DataFrame:
    inline = pl.scan_parquet(DATA / "pr_review_comments.parquet").select(
        pl.lit("direct_inline_reply").alias("response_source"),
        pl.col("id").alias("response_event_id"),
        pl.col("body").fill_null("").alias("response_body"),
    )
    reviews = pl.scan_parquet(DATA / "pr_reviews.parquet").select(
        pl.lit("subsequent_review").alias("response_source"),
        pl.col("id").alias("response_event_id"),
        pl.col("body").fill_null("").alias("response_body"),
    )
    comments = pl.scan_parquet(DATA / "pr_comments.parquet").select(
        pl.lit("subsequent_pr_comment").alias("response_source"),
        pl.col("id").alias("response_event_id"),
        pl.col("body").fill_null("").alias("response_body"),
    )
    return pl.concat([inline, reviews, comments]).collect().to_pandas()


def weighted_diversity_sample(frame: pd.DataFrame, n: int, columns: list[str], seed: int) -> pd.DataFrame:
    if len(frame) <= n:
        return frame.copy()
    group_size = frame.groupby(columns, dropna=False)[columns[0]].transform("size")
    weights = 1.0 / np.sqrt(group_size.to_numpy(dtype=float))
    return frame.sample(n=n, replace=False, weights=weights, random_state=seed)


def build_candidates() -> tuple[pd.DataFrame, pd.DataFrame]:
    triggers = feedback_with_text(DATA).to_pandas().rename(
        columns={
            "event_id": "trigger_event_id",
            "review_id": "trigger_review_id",
            "interaction_dt": "trigger_dt",
            "source": "trigger_source",
        }
    )
    events = add_owner(pl.read_parquet(INPUT / "cross_feedback_response_events.parquet")).to_pandas()
    first_per_channel = (
        events.sort_values(["pr_id", "response_source", "response_dt", "response_event_id"], na_position="last")
        .drop_duplicates(["pr_id", "response_source"], keep="first")
    )
    first_per_channel = first_per_channel.merge(
        response_text_lookup(), on=["response_source", "response_event_id"], how="left"
    )
    candidates = first_per_channel.merge(
        triggers[
            [
                "pr_id", "repo_id", "author_agent", "reviewer_agent", "trigger_source",
                "trigger_event_id", "trigger_review_id", "trigger_dt", "trigger_body",
                "path", "diff_hunk",
            ]
        ],
        left_on=["pr_id", "author_agent", "trigger_reviewer_agent", "trigger_source", "trigger_event_id", "trigger_review_id"],
        right_on=["pr_id", "author_agent", "reviewer_agent", "trigger_source", "trigger_event_id", "trigger_review_id"],
        how="inner",
    )
    chains = pl.read_parquet(INPUT / "cross_feedback_response_chains.parquet").select("pr_id").to_pandas()
    responded = set(events["pr_id"])
    silent = triggers[triggers["pr_id"].isin(set(chains["pr_id"]) - responded)].copy()
    silent["response_source"] = "no_observed_action"
    silent["response_owner"] = "no_observed_action"
    silent["response_body"] = ""
    silent["response_event_id"] = pd.NA
    silent["response_review_id"] = pd.NA
    silent["response_dt"] = pd.NaT
    silent["hours_after_trigger"] = pd.NA
    return candidates, silent


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    candidates, silent = build_candidates()
    samples = []
    for offset, (channel, quota) in enumerate(QUOTAS.items()):
        population = silent if channel == "no_observed_action" else candidates[candidates["response_source"] == channel]
        sample = weighted_diversity_sample(
            population,
            quota,
            ["author_agent", "reviewer_agent", "trigger_source", "response_owner"],
            SEED + offset,
        )
        samples.append(sample)
    selected = pd.concat(samples, ignore_index=True)

    rows = []
    keys = []
    for _, item in selected.iterrows():
        trigger_text, trigger_hash, trigger_truncated, trigger_secret = normalize_text(item["trigger_body"])
        response_text, response_hash, response_truncated, response_secret = normalize_text(item.get("response_body", ""))
        if trigger_secret or response_secret:
            continue
        raw_key = f"{int(item['pr_id'])}|{item['trigger_source']}|{item['trigger_event_id']}|{item['response_source']}|{item.get('response_event_id')}"
        record_id = "FR-" + hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12].upper()
        path_value = "" if pd.isna(item.get("path")) else str(item.get("path"))
        path_suffix = Path(path_value).suffix.lower()[:12] if path_value else ""
        rows.append(
            {
                "record_id": record_id,
                "author_product": item["author_agent"],
                "reviewer_product": item["reviewer_agent"],
                "trigger_channel": item["trigger_source"],
                "trigger_body": trigger_text,
                "trigger_text_sha256": trigger_hash,
                "trigger_truncated": trigger_truncated,
                "has_diff_context": bool(str(item.get("diff_hunk") or "").strip()),
                "path_suffix": path_suffix,
                "response_channel": item["response_source"],
                "response_owner_rule": item["response_owner"],
                "response_body": response_text,
                "response_text_sha256": response_hash,
                "response_truncated": response_truncated,
                "hours_after_trigger": item.get("hours_after_trigger"),
                "trigger_substance": "",
                "response_relation": "",
                "resolution_signal": "",
                "owner_mapping_valid": "",
                "confidence": "",
                "evidence_note": "",
            }
        )
        keys.append(
            {
                "record_id": record_id,
                "pr_id": int(item["pr_id"]),
                "repo_id": int(item["repo_id"]),
                "trigger_event_id": item["trigger_event_id"],
                "trigger_review_id": item["trigger_review_id"],
                "response_event_id": item.get("response_event_id"),
                "response_review_id": item.get("response_review_id"),
            }
        )
    packet = pd.DataFrame(rows).sort_values("record_id")
    key = pd.DataFrame(keys).sort_values("record_id")
    packet.to_csv(OUTPUT / "coder_A_blinded.csv", index=False)
    packet.to_csv(OUTPUT / "coder_B_blinded.csv", index=False)
    key.to_csv(OUTPUT / "private_record_key.csv", index=False)

    config = {"seed": SEED, "quotas": QUOTAS, "schema_version": "feedback-response-audit-v1"}
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()
    try:
        code_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        code_revision = "unavailable"
    source_files = [
        DATA / "pull_request.parquet", DATA / "pr_reviews.parquet",
        DATA / "pr_review_comments.parquet", DATA / "pr_comments.parquet",
        DATA / "pr_timeline.parquet",
    ]
    manifest = {
        "run_id": f"feedback-response-audit-{SEED}",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": "feedback-response-audit-v1",
        "row_count": len(packet),
        "channel_counts": packet["response_channel"].value_counts().sort_index().to_dict(),
        "config_sha256": config_hash,
        "schema_sha256": sha256_file(SCHEMA),
        "script_sha256": sha256_file(Path(__file__)),
        "source_sha256": {path.name: sha256_file(path) for path in source_files},
        "code_revision": code_revision,
        "raw_identifiers_in_blinded_packet": False,
        "raw_record_key_separate": True,
        "outcomes_visible_to_coders": False,
        "external_upload": False,
        "excluded_likely_secret_records": int(len(selected) - len(packet)),
        "artifact_sha256": {
            "coder_A_blinded.csv": sha256_file(OUTPUT / "coder_A_blinded.csv"),
            "coder_B_blinded.csv": sha256_file(OUTPUT / "coder_B_blinded.csv"),
            "private_record_key.csv": sha256_file(OUTPUT / "private_record_key.csv"),
        },
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(packet), "channels": manifest["channel_counts"]}, indent=2))


if __name__ == "__main__":
    main()
