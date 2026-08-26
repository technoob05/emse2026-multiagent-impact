from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "review_collision"
OUTPUT = ROOT / "outputs" / "novelty_collision_extension"
SEED = 20260826
BOOTSTRAP_REPS = 10_000
DOMINANT_PAIR = "Copilot + OpenAI_Codex"


def normalize_exact(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    return re.sub(r"\s+", " ", text).strip().casefold()


def cluster_bootstrap_share(
    frame: pd.DataFrame, outcome: str, cluster: str, reps: int, seed: int
) -> tuple[float, float]:
    grouped = [part[outcome].to_numpy(dtype=float) for _, part in frame.groupby(cluster)]
    rng = np.random.default_rng(seed)
    estimates = np.empty(reps, dtype=float)
    for index in range(reps):
        sampled = rng.integers(0, len(grouped), size=len(grouped))
        values = np.concatenate([grouped[item] for item in sampled])
        estimates[index] = values.mean()
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else float("nan")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    population = pd.read_parquet(
        INPUT / "private" / "strict_collision_population.parquet"
    )
    quality = json.loads(
        (INPUT / "quality_and_sampling_summary.json").read_text(encoding="utf-8")
    )

    population = population.copy()
    population["within_1_minute"] = population["gap_seconds"] <= 60
    population["within_5_minutes"] = population["gap_seconds"] <= 300
    population["within_10_minutes"] = population["gap_seconds"] <= 600
    population["both_comments_during_open_pr_state"] = ~population[
        "first_after_pr_close"
    ] & ~population["second_after_pr_close"]
    population["exact_normalized_body_duplicate"] = (
        population["first_body"].map(normalize_exact)
        == population["second_body"].map(normalize_exact)
    )
    population["exact_normalized_diff_match"] = (
        population["first_diff_hunk"].map(normalize_exact)
        == population["second_diff_hunk"].map(normalize_exact)
    )
    population["first_has_suggestion_block"] = population["first_body"].str.contains(
        r"```suggestion", case=False, na=False
    )
    population["second_has_suggestion_block"] = population["second_body"].str.contains(
        r"```suggestion", case=False, na=False
    )
    population["suggestion_format_relation"] = np.select(
        [
            population["first_has_suggestion_block"]
            & population["second_has_suggestion_block"],
            population["first_has_suggestion_block"]
            ^ population["second_has_suggestion_block"],
        ],
        ["both", "exactly_one"],
        default="neither",
    )

    n = len(population)
    eligible_multi_product_prs = int(
        quality["support"]["strict_prs_with_two_or_more_mapped_products"]
    )
    collision_prs = int(population["pr_id"].nunique())
    within5_low, within5_high = cluster_bootstrap_share(
        population, "within_5_minutes", "repo_id", BOOTSTRAP_REPS, SEED
    )

    dominant = population["product_pair"] == DOMINANT_PAIR
    open_state = population["both_comments_during_open_pr_state"]
    summary = {
        "analysis_contract": {
            "unit": "one canonical structural same-snapshot/same-locus cross-product pair",
            "semantic_coding_used": False,
            "causal_analysis_used": False,
            "text_analysis": "exact normalized equality only; no semantic similarity model",
            "repository_cluster_bootstrap_repetitions": BOOTSTRAP_REPS,
            "seed": SEED,
        },
        "support": {
            "canonical_loci": n,
            "pull_requests_with_locus": collision_prs,
            "repositories": int(population["repo_id"].nunique()),
            "product_pairs": int(population["product_pair"].nunique()),
            "eligible_prs_with_two_or_more_mapped_reviewer_products": eligible_multi_product_prs,
            "eligible_pr_share_with_at_least_one_structural_locus_overlap": safe_ratio(
                collision_prs, eligible_multi_product_prs
            ),
            "loci_with_exactly_two_comments": int(
                (population["n_comments_at_locus"] == 2).sum()
            ),
            "maximum_canonical_loci_on_one_pr": int(
                population.groupby("pr_id").size().max()
            ),
        },
        "timing": {
            "median_gap_minutes": float(population["gap_seconds"].median() / 60),
            "share_within_1_minute": float(population["within_1_minute"].mean()),
            "share_within_5_minutes": float(population["within_5_minutes"].mean()),
            "share_within_5_minutes_repository_cluster_bootstrap_95_interval": [
                within5_low,
                within5_high,
            ],
            "share_within_10_minutes": float(population["within_10_minutes"].mean()),
            "open_state_loci": int(open_state.sum()),
            "open_state_share_within_5_minutes": float(
                population.loc[open_state, "within_5_minutes"].mean()
            ),
            "non_dominant_product_pair_loci": int((~dominant).sum()),
            "non_dominant_product_pair_share_within_5_minutes": float(
                population.loc[~dominant, "within_5_minutes"].mean()
            ),
        },
        "format_and_exact_text_checks": {
            "exact_normalized_body_duplicate_loci": int(
                population["exact_normalized_body_duplicate"].sum()
            ),
            "exact_normalized_diff_match_loci": int(
                population["exact_normalized_diff_match"].sum()
            ),
            "suggestion_block_relation_counts": population[
                "suggestion_format_relation"
            ].value_counts().sort_index().to_dict(),
        },
        "concentration": quality["concentration"],
        "falsification": {
            "product_pair_generality_gate": quality["falsification_gates"][
                "largest_product_pair_supplies_at_most_half"
            ],
            "semantic_relation_gate": "pending dual coding; location, timing, exact text inequality, and suggestion syntax do not establish redundancy, complementarity, contradiction, correctness, or response",
            "safe_pre_coding_read": "Same-locus cross-product output is uncommon among eligible multi-product PRs and usually arrives in a short burst. This timing is compatible with parallel fan-out, but does not prove independent generation or coordination.",
        },
    }
    (OUTPUT / "descriptive_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    pair_sensitivity = (
        population.groupby("product_pair", dropna=False)
        .agg(
            loci=("record_id", "size"),
            repositories=("repo_id", "nunique"),
            median_gap_seconds=("gap_seconds", "median"),
            share_within_5_minutes=("within_5_minutes", "mean"),
            open_state_loci=("both_comments_during_open_pr_state", "sum"),
            exact_normalized_body_duplicates=("exact_normalized_body_duplicate", "sum"),
        )
        .reset_index()
        .sort_values(["loci", "product_pair"], ascending=[False, True])
    )
    pair_sensitivity["locus_share"] = pair_sensitivity["loci"] / n
    pair_sensitivity.to_csv(OUTPUT / "product_pair_support_and_timing.csv", index=False)

    timing_bins = pd.cut(
        population["gap_seconds"],
        bins=[-0.001, 60, 300, 600, 3600, float("inf")],
        labels=["0-1m", ">1-5m", ">5-10m", ">10-60m", ">60m"],
        right=True,
    )
    timing_table = (
        timing_bins.value_counts(sort=False)
        .rename("loci")
        .reset_index()
        .rename(columns={"gap_seconds": "gap_bin"})
    )
    timing_table["share"] = timing_table["loci"] / n
    timing_table.to_csv(OUTPUT / "timing_distribution.csv", index=False)

    leave_one_pair_rows = []
    for pair in sorted(population["product_pair"].unique()):
        subset = population[population["product_pair"] != pair]
        leave_one_pair_rows.append(
            {
                "excluded_product_pair": pair,
                "remaining_loci": len(subset),
                "remaining_repositories": int(subset["repo_id"].nunique()),
                "share_within_5_minutes": float(subset["within_5_minutes"].mean()),
                "median_gap_minutes": float(subset["gap_seconds"].median() / 60),
            }
        )
    pd.DataFrame(leave_one_pair_rows).to_csv(
        OUTPUT / "leave_one_product_pair_timing.csv", index=False
    )

    manifest = {
        "input_population_sha256": hashlib.sha256(
            (INPUT / "private" / "strict_collision_population.parquet").read_bytes()
        ).hexdigest(),
        "input_quality_summary_sha256": hashlib.sha256(
            (INPUT / "quality_and_sampling_summary.json").read_bytes()
        ).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "semantic_labels_used": False,
        "manuscript_edited": False,
        "artifacts": [
            "descriptive_summary.json",
            "product_pair_support_and_timing.csv",
            "timing_distribution.csv",
            "leave_one_product_pair_timing.csv",
        ],
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
