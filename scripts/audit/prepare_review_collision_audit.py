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
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import (  # noqa: E402
    AGENT_ACCOUNT_ALIASES,
    INTERACTION_CUTOFF,
    classify_agent_account,
    parse_timestamp,
)


DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
OUTPUT = ROOT / "outputs" / "review_collision"
PACKETS = OUTPUT / "audit_packets"
PRIVATE = OUTPUT / "private"
SCHEMA = ROOT / "protocol" / "review_collision_label_schema.json"
DATASET_REVISION = "37bbe1533e26cc1e1374917dba1186d1c8a4dc81"
SEED = 20260826
MAX_FULL_POPULATION = 300
TEXT_LIMIT = 6000
DIFF_LIMIT = 6000

SECRET_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|"
    r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b|\bsk-[A-Za-z0-9_-]{20,}\b|"
    r"\bBearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)

# The structured product columns never enter coder packets. This pattern also
# removes incidental product self-identification from the visible text.
_PRODUCT_TERMS = sorted(
    set(AGENT_ACCOUNT_ALIASES)
    | {
        "claude code",
        "claude",
        "copilot",
        "cursor",
        "devin",
        "google jules",
        "jules",
        "openai codex",
        "codex",
    },
    key=len,
    reverse=True,
)
PRODUCT_PATTERN = re.compile(
    "|".join(re.escape(term) for term in _PRODUCT_TERMS), re.IGNORECASE
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scalar(frame: pl.DataFrame, name: str) -> int:
    value = frame.row(0, named=True)[name]
    return int(value or 0)


def normalize_for_packet(value: object, limit: int) -> tuple[str, str, bool, bool]:
    text = "" if value is None or pd.isna(value) else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    original_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    had_secret = bool(SECRET_PATTERN.search(text))
    text = SECRET_PATTERN.sub("[REDACTED_SECRET]", text)
    text = re.sub(r"https?://\S+", "[URL]", text)
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL]",
        text,
    )
    text = PRODUCT_PATTERN.sub("[REVIEWER_PRODUCT]", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:limit], original_hash, len(text) > limit, had_secret


def strict_comment_rows() -> tuple[pl.DataFrame, dict[str, int]]:
    comments_raw = pl.scan_parquet(DATA / "pr_review_comments.parquet")
    reviews_raw = pl.scan_parquet(DATA / "pr_reviews.parquet")

    # A review id must point to exactly one PR. Ambiguous keys are not guessed.
    review_keys = (
        reviews_raw.group_by("pull_request_review_id")
        .agg(
            pl.col("pr_id").n_unique().alias("n_pr_ids"),
            pl.col("pr_id").first().alias("pr_id"),
        )
        .filter(pl.col("n_pr_ids") == 1)
        .select("pull_request_review_id", "pr_id")
    )
    prs = (
        pl.scan_parquet(DATA / "pull_request.parquet")
        .select(
            pl.col("id").alias("pr_id"),
            "repo_id",
            "repo_url",
            parse_timestamp("created_at", "pr_created_dt"),
            parse_timestamp("closed_at", "pr_closed_dt"),
        )
    )
    top_level = comments_raw.filter(pl.col("in_reply_to_id").is_null())
    known_pr = top_level.join(review_keys, on="pull_request_review_id", how="inner")
    mapped = known_pr.with_columns(classify_agent_account("user")).filter(
        pl.col("reviewer_agent").is_not_null()
    )
    mapped_with_context = (
        mapped.join(prs, on="pr_id", how="inner")
        .with_columns(parse_timestamp("created_at", "comment_dt"))
    )
    parseable = mapped_with_context.filter(
        pl.col("comment_dt").is_not_null() & pl.col("pr_created_dt").is_not_null()
    )
    valid_locus = parseable.filter(
        pl.col("original_commit_id").is_not_null()
        & pl.col("original_commit_id").str.contains(r"^[0-9a-fA-F]{40}$")
        & pl.col("path").is_not_null()
        & (pl.col("path").str.strip_chars().str.len_chars() > 0)
        & pl.col("original_position").is_not_null()
        & (pl.col("original_position") > 0)
    )
    after_creation = valid_locus.filter(
        pl.col("comment_dt") >= pl.col("pr_created_dt")
    )
    within_cutoff_sensitivity = after_creation.filter(
        pl.col("comment_dt") <= pl.lit(INTERACTION_CUTOFF)
    )
    within_open_state_sensitivity = after_creation.filter(
        pl.col("pr_closed_dt").is_null()
        | (pl.col("comment_dt") <= pl.col("pr_closed_dt"))
    )
    # GitHub permits review comments after a PR closes. Such timestamps remain
    # valid public events, so closure is reported as a sensitivity subset rather
    # than silently changing the stated same-locus population.
    valid = after_creation

    pr_multi_product = (
        valid.group_by("pr_id")
        .agg(pl.col("reviewer_agent").n_unique().alias("n_products_on_pr"))
        .filter(pl.col("n_products_on_pr") >= 2)
    )
    valid_multi_pr = valid.join(pr_multi_product, on="pr_id", how="inner")
    loci = (
        valid_multi_pr.group_by(
            "pr_id", "original_commit_id", "path", "original_position"
        )
        .agg(
            pl.col("reviewer_agent").n_unique().alias("n_products_at_locus"),
            pl.len().alias("n_comments_at_locus"),
        )
        .filter(pl.col("n_products_at_locus") >= 2)
    )
    collision_rows = (
        valid_multi_pr.join(
            loci,
            on=["pr_id", "original_commit_id", "path", "original_position"],
            how="inner",
        )
        .select(
            "id",
            "pull_request_review_id",
            "pr_id",
            "repo_id",
            "repo_url",
            "reviewer_agent",
            "user",
            "user_type",
            "original_commit_id",
            "path",
            "original_position",
            "body",
            "diff_hunk",
            "comment_dt",
            "pr_closed_dt",
            "n_products_on_pr",
            "n_products_at_locus",
            "n_comments_at_locus",
        )
        .sort(
            [
                "pr_id",
                "original_commit_id",
                "path",
                "original_position",
                "comment_dt",
                "id",
            ]
        )
        .collect()
    )

    counts = {
        "source_inline_comments": scalar(
            comments_raw.select(pl.len().alias("n")).collect(), "n"
        ),
        "top_level_inline_comments": scalar(
            top_level.select(pl.len().alias("n")).collect(), "n"
        ),
        "top_level_with_unambiguous_review_to_pr_key": scalar(
            known_pr.select(pl.len().alias("n")).collect(), "n"
        ),
        "top_level_mapped_product_comments": scalar(
            mapped.select(pl.len().alias("n")).collect(), "n"
        ),
        "mapped_comments_with_parseable_comment_and_pr_creation_timestamps": scalar(
            parseable.select(pl.len().alias("n")).collect(), "n"
        ),
        "mapped_comments_with_complete_valid_locus_key": scalar(
            valid_locus.select(pl.len().alias("n")).collect(), "n"
        ),
        "mapped_comments_at_or_after_pr_creation": scalar(
            after_creation.select(pl.len().alias("n")).collect(), "n"
        ),
        "mapped_comments_within_common_interaction_cutoff": scalar(
            within_cutoff_sensitivity.select(pl.len().alias("n")).collect(), "n"
        ),
        "mapped_comments_at_or_before_pr_close_when_known": scalar(
            within_open_state_sensitivity.select(pl.len().alias("n")).collect(), "n"
        ),
        "strict_valid_mapped_comment_rows": scalar(
            valid.select(pl.len().alias("n")).collect(), "n"
        ),
        "strict_prs_with_two_or_more_mapped_products": scalar(
            pr_multi_product.select(pl.len().alias("n")).collect(), "n"
        ),
        "strict_same_snapshot_same_locus_groups": scalar(
            loci.select(pl.len().alias("n")).collect(), "n"
        ),
        "comment_rows_in_strict_loci": collision_rows.height,
    }
    return collision_rows, counts


def canonical_pairs(rows: pl.DataFrame) -> pd.DataFrame:
    frame = rows.to_pandas()
    group_cols = ["pr_id", "original_commit_id", "path", "original_position"]
    pairs: list[dict[str, object]] = []
    for locus, group in frame.groupby(group_cols, sort=True, dropna=False):
        group = group.sort_values(["comment_dt", "id"], kind="mergesort")
        first = group.iloc[0]
        second_pool = group[group["reviewer_agent"] != first["reviewer_agent"]]
        if second_pool.empty:
            continue
        second = second_pool.iloc[0]
        raw_key = "|".join(
            [
                str(int(first["pr_id"])),
                str(first["original_commit_id"]),
                str(first["path"]),
                str(int(first["original_position"])),
                str(int(first["id"])),
                str(int(second["id"])),
            ]
        )
        product_pair = " + ".join(
            sorted([str(first["reviewer_agent"]), str(second["reviewer_agent"])])
        )
        pairs.append(
            {
                "record_id": "RC-" + hashlib.sha256(raw_key.encode()).hexdigest()[:12].upper(),
                "pr_id": int(first["pr_id"]),
                "repo_id": int(first["repo_id"]),
                "repo_url": first["repo_url"],
                "original_commit_id": first["original_commit_id"],
                "path": first["path"],
                "original_position": int(first["original_position"]),
                "first_event_id": int(first["id"]),
                "second_event_id": int(second["id"]),
                "first_review_id": int(first["pull_request_review_id"]),
                "second_review_id": int(second["pull_request_review_id"]),
                "first_product": first["reviewer_agent"],
                "second_product": second["reviewer_agent"],
                "product_pair": product_pair,
                "first_user": first["user"],
                "second_user": second["user"],
                "first_dt": first["comment_dt"],
                "second_dt": second["comment_dt"],
                "first_after_pr_close": bool(
                    pd.notna(first["pr_closed_dt"])
                    and first["comment_dt"] > first["pr_closed_dt"]
                ),
                "second_after_pr_close": bool(
                    pd.notna(second["pr_closed_dt"])
                    and second["comment_dt"] > second["pr_closed_dt"]
                ),
                "gap_seconds": float(
                    (second["comment_dt"] - first["comment_dt"]).total_seconds()
                ),
                "first_body": first["body"],
                "second_body": second["body"],
                "first_diff_hunk": first["diff_hunk"],
                "second_diff_hunk": second["diff_hunk"],
                "n_products_on_pr": int(first["n_products_on_pr"]),
                "n_products_at_locus": int(first["n_products_at_locus"]),
                "n_comments_at_locus": int(first["n_comments_at_locus"]),
            }
        )
    result = pd.DataFrame(pairs).sort_values("record_id").reset_index(drop=True)
    if result.empty:
        raise RuntimeError("No strict review-collision pairs survived.")
    if result.duplicated(["pr_id", "original_commit_id", "path", "original_position"]).any():
        raise AssertionError("Canonical cohort contains more than one pair per locus.")
    if (result["first_product"] == result["second_product"]).any():
        raise AssertionError("Canonical cohort contains a same-product pair.")
    if (result["gap_seconds"] < 0).any():
        raise AssertionError("Canonical pair ordering produced a negative time gap.")
    return result


def choose_audit_population(population: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if len(population) <= MAX_FULL_POPULATION:
        return population.copy(), "complete_strict_population"
    rng = np.random.default_rng(SEED)
    chosen = rng.choice(population.index.to_numpy(), size=MAX_FULL_POPULATION, replace=False)
    return population.loc[chosen].copy(), "seeded_simple_random_sample"


def build_packets(
    selected: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, int]]:
    packet_rows: list[dict[str, object]] = []
    key_rows: list[dict[str, object]] = []
    redact_counts = {
        "records_with_secret_redaction": 0,
        "records_with_truncated_comment": 0,
        "records_with_truncated_diff_context": 0,
    }
    for _, item in selected.iterrows():
        body_a, hash_a, trunc_a, secret_a = normalize_for_packet(item["first_body"], TEXT_LIMIT)
        body_b, hash_b, trunc_b, secret_b = normalize_for_packet(item["second_body"], TEXT_LIMIT)
        diff_a, diff_hash_a, diff_trunc_a, diff_secret_a = normalize_for_packet(
            item["first_diff_hunk"], DIFF_LIMIT
        )
        diff_b, diff_hash_b, diff_trunc_b, diff_secret_b = normalize_for_packet(
            item["second_diff_hunk"], DIFF_LIMIT
        )
        any_secret = secret_a or secret_b or diff_secret_a or diff_secret_b
        redact_counts["records_with_secret_redaction"] += int(any_secret)
        redact_counts["records_with_truncated_comment"] += int(trunc_a or trunc_b)
        redact_counts["records_with_truncated_diff_context"] += int(
            diff_trunc_a or diff_trunc_b
        )
        path_suffix = Path(str(item["path"])).suffix.lower()[:16]
        packet_rows.append(
            {
                "record_id": item["record_id"],
                "path_suffix": path_suffix,
                "comment_A": body_a,
                "comment_A_sha256": hash_a,
                "comment_A_truncated": trunc_a,
                "comment_A_diff_context": diff_a,
                "comment_A_diff_sha256": diff_hash_a,
                "comment_A_diff_truncated": diff_trunc_a,
                "comment_B": body_b,
                "comment_B_sha256": hash_b,
                "comment_B_truncated": trunc_b,
                "comment_B_diff_context": diff_b,
                "comment_B_diff_sha256": diff_hash_b,
                "comment_B_diff_truncated": diff_trunc_b,
                "comment_A_substance": "",
                "comment_B_substance": "",
                "pair_relation": "",
                "confidence": "",
                "evidence_note": "",
            }
        )
        key_rows.append(
            {
                "record_id": item["record_id"],
                "pr_id": item["pr_id"],
                "repo_id": item["repo_id"],
                "repo_url": item["repo_url"],
                "original_commit_id": item["original_commit_id"],
                "path": item["path"],
                "original_position": item["original_position"],
                "first_event_id": item["first_event_id"],
                "second_event_id": item["second_event_id"],
                "first_review_id": item["first_review_id"],
                "second_review_id": item["second_review_id"],
                "first_product": item["first_product"],
                "second_product": item["second_product"],
                "product_pair": item["product_pair"],
                "first_dt": item["first_dt"],
                "second_dt": item["second_dt"],
                "first_after_pr_close": item["first_after_pr_close"],
                "second_after_pr_close": item["second_after_pr_close"],
                "gap_seconds": item["gap_seconds"],
            }
        )
    packet = pd.DataFrame(packet_rows)
    private_key = pd.DataFrame(key_rows)
    # Different deterministic row orders reduce shared order effects while both
    # coders still receive every selected record.
    coder_a = packet.sample(frac=1, random_state=SEED).reset_index(drop=True)
    coder_b = packet.sample(frac=1, random_state=SEED + 1).reset_index(drop=True)
    return coder_a, coder_b, private_key, redact_counts


def share_table(population: pd.DataFrame, column: str, output_name: str) -> pd.DataFrame:
    table = (
        population.groupby(column, dropna=False)
        .size()
        .rename("collision_loci")
        .reset_index()
        .sort_values(["collision_loci", column], ascending=[False, True])
    )
    table["share"] = table["collision_loci"] / len(population)
    table.to_csv(OUTPUT / output_name, index=False)
    return table


def main() -> None:
    PACKETS.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)

    rows, waterfall = strict_comment_rows()
    population = canonical_pairs(rows)
    selected, sampling_mode = choose_audit_population(population)
    coder_a, coder_b, private_key, redact_counts = build_packets(selected)

    # The canonical cohort is private research data; coder packets contain only
    # blinded/redacted text and empty semantic-label columns.
    population.to_parquet(PRIVATE / "strict_collision_population.parquet", index=False)
    private_key.to_csv(PRIVATE / "private_record_key.csv", index=False)
    coder_a.to_csv(PACKETS / "coder_A_blinded.csv", index=False)
    coder_b.to_csv(PACKETS / "coder_B_blinded.csv", index=False)

    repo_counts = share_table(population, "repo_id", "repo_concentration.csv")
    pair_counts = share_table(population, "product_pair", "product_pair_concentration.csv")
    timing = {
        "minimum_gap_seconds": float(population["gap_seconds"].min()),
        "median_gap_minutes": float(population["gap_seconds"].median() / 60.0),
        "p25_gap_minutes": float(population["gap_seconds"].quantile(0.25) / 60.0),
        "p75_gap_minutes": float(population["gap_seconds"].quantile(0.75) / 60.0),
        "p90_gap_minutes": float(population["gap_seconds"].quantile(0.90) / 60.0),
        "share_within_1_minute": float((population["gap_seconds"] <= 60).mean()),
        "share_within_5_minutes": float((population["gap_seconds"] <= 300).mean()),
        "share_within_10_minutes": float((population["gap_seconds"] <= 600).mean()),
        "share_within_60_minutes": float((population["gap_seconds"] <= 3600).mean()),
    }
    concentration = {
        "repositories": int(population["repo_id"].nunique()),
        "product_pairs": int(population["product_pair"].nunique()),
        "largest_repository_count": int(repo_counts.iloc[0]["collision_loci"]),
        "largest_repository_share": float(repo_counts.iloc[0]["share"]),
        "largest_product_pair": str(pair_counts.iloc[0]["product_pair"]),
        "largest_product_pair_count": int(pair_counts.iloc[0]["collision_loci"]),
        "largest_product_pair_share": float(pair_counts.iloc[0]["share"]),
        "repository_hhi": float((repo_counts["share"] ** 2).sum()),
        "product_pair_hhi": float((pair_counts["share"] ** 2).sum()),
    }
    support = {
        **waterfall,
        "canonical_collision_loci": int(len(population)),
        "pull_requests_with_collision_locus": int(population["pr_id"].nunique()),
        "canonical_loci_with_both_comments_during_open_pr_state": int(
            (~population["first_after_pr_close"] & ~population["second_after_pr_close"]).sum()
        ),
        "canonical_loci_with_at_least_one_post_close_comment": int(
            (population["first_after_pr_close"] | population["second_after_pr_close"]).sum()
        ),
        "audit_packet_rows_per_coder": int(len(selected)),
        "sampling_mode": sampling_mode,
        "full_strict_population_covered": bool(len(selected) == len(population)),
        **redact_counts,
    }
    gates = {
        "minimum_100_valid_pairs": {
            "status": "pass" if len(population) >= 100 else "fail",
            "observed": int(len(population)),
            "threshold": 100,
        },
        "minimum_100_pairs_in_open_pr_state_sensitivity": {
            "status": "pass"
            if support["canonical_loci_with_both_comments_during_open_pr_state"] >= 100
            else "fail",
            "observed": support[
                "canonical_loci_with_both_comments_during_open_pr_state"
            ],
            "threshold": 100,
        },
        "largest_repository_supplies_at_most_half": {
            "status": "pass" if concentration["largest_repository_share"] <= 0.5 else "fail",
            "observed": concentration["largest_repository_share"],
            "threshold": 0.5,
        },
        "largest_product_pair_supplies_at_most_half": {
            "status": "pass" if concentration["largest_product_pair_share"] <= 0.5 else "fail",
            "observed": concentration["largest_product_pair_share"],
            "threshold": 0.5,
        },
        "complete_population_if_at_most_300": {
            "status": "pass"
            if len(population) > MAX_FULL_POPULATION or len(selected) == len(population)
            else "fail",
            "population": int(len(population)),
            "packet_rows": int(len(selected)),
            "threshold": MAX_FULL_POPULATION,
        },
        "cohen_kappa_at_least_0_70": {
            "status": "pending_dual_coding",
            "threshold": 0.70,
        },
        "boilerplate_or_unclear_at_most_0_30": {
            "status": "pending_dual_coding",
            "threshold": 0.30,
        },
        "at_least_30_cases_per_headline_semantic_category": {
            "status": "pending_adjudication",
            "threshold": 30,
        },
    }
    quality = {
        "dataset_revision": DATASET_REVISION,
        "selection_contract": {
            "top_level_inline_only": True,
            "exact_account_alias_mapping_imported_from": "src/multiagent_impact/cross_agent_review.py",
            "minimum_mapped_products_at_locus": 2,
            "exact_locus_key": [
                "pr_id",
                "original_commit_id",
                "path",
                "original_position",
            ],
            "valid_time_rule": "parseable comment and PR-creation timestamps, with comment at/after PR creation; post-close public comments are retained and quantified as a sensitivity subset",
            "canonical_pair_rule": "earliest mapped-product comment plus earliest different-product comment, ordered by timestamp then event id",
            "one_pair_per_locus": True,
        },
        "support": support,
        "concentration": concentration,
        "timing": timing,
        "falsification_gates": gates,
        "semantic_labels_assigned": False,
        "interpretation_limit": "Same-locus co-occurrence is not semantic duplication, contradiction, correctness, repair, or causal impact; those claims require the frozen dual-coder audit.",
    }
    (OUTPUT / "quality_and_sampling_summary.json").write_text(
        json.dumps(quality, indent=2), encoding="utf-8"
    )

    try:
        code_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        code_revision = "unavailable"
    artifacts = [
        PACKETS / "coder_A_blinded.csv",
        PACKETS / "coder_B_blinded.csv",
        PRIVATE / "private_record_key.csv",
        PRIVATE / "strict_collision_population.parquet",
        OUTPUT / "repo_concentration.csv",
        OUTPUT / "product_pair_concentration.csv",
        OUTPUT / "quality_and_sampling_summary.json",
    ]
    manifest = {
        "run_id": f"review-collision-audit-{SEED}",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_revision": DATASET_REVISION,
        "schema_version": "review-collision-audit-v1",
        "code_revision": code_revision,
        "source_sha256": {
            path.name: sha256_file(path)
            for path in [
                DATA / "pull_request.parquet",
                DATA / "pr_reviews.parquet",
                DATA / "pr_review_comments.parquet",
            ]
        },
        "schema_sha256": sha256_file(SCHEMA),
        "script_sha256": sha256_file(Path(__file__)),
        "artifact_sha256": {
            str(path.relative_to(OUTPUT)).replace("\\", "/"): sha256_file(path)
            for path in artifacts
        },
        "raw_identifiers_in_blinded_packets": False,
        "product_and_outcome_blinding": True,
        "private_key_separate": True,
        "external_upload": False,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "canonical_collision_loci": len(population),
                "pull_requests": population["pr_id"].nunique(),
                "repositories": concentration["repositories"],
                "product_pairs": concentration["product_pairs"],
                "packet_rows_per_coder": len(selected),
                "sampling_mode": sampling_mode,
                "median_gap_minutes": timing["median_gap_minutes"],
                "share_within_5_minutes": timing["share_within_5_minutes"],
                "largest_repository_share": concentration["largest_repository_share"],
                "largest_product_pair_share": concentration["largest_product_pair_share"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
