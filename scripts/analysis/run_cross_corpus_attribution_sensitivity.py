from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AIDEV = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
DEFAULT_A2A = (
    ROOT
    / "external_data"
    / "source_repositories"
    / "AI-AI-CodeReviews"
    / "cohorts"
    / "axb_cross.parquet"
)
DEFAULT_EDGE = ROOT / "outputs" / "addressed_edge_landmark" / "analysis_cohort.parquet"
DEFAULT_OUTPUT = ROOT / "outputs" / "external_validation" / "codage_attribution_sensitivity"

AIDEV_REVISION = "37bbe1533e26cc1e1374917dba1186d1c8a4dc81"
A2A_REVISION = "f3d01cd621b4e231e25835c59ecbb851c8269f10"
PRETRIGGER_CONTROLS = [
    "log1p_trigger_age_hours",
    "log1p_pre_events",
    "pre_user_events",
    "pre_bot_events",
    "pre_decisive_reviews",
    "pre_force_pushes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_repo_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .str.replace(r"^https://api\.github\.com/repos/", "")
        .str.replace(r"^https://github\.com/", "")
        .str.strip_chars_end("/")
        .str.to_lowercase()
    )


def load_pr_map(data_dir: Path) -> pl.DataFrame:
    frame = (
        pl.read_parquet(
            data_dir / "pull_request.parquet",
            columns=["id", "number", "repo_url"],
        )
        .rename({"id": "pr_id", "number": "pr_number"})
        .with_columns(normalize_repo_expr("repo_url").alias("repo_name"))
        .select("pr_id", "repo_name", "pr_number")
        .sort("pr_id")
    )
    if frame["pr_id"].n_unique() != frame.height:
        raise AssertionError("AIDev PR map is not unique at pr_id grain.")
    if sum(frame.null_count().row(0)):
        raise AssertionError("AIDev PR map contains null join keys.")
    return frame


def load_a2a_pairs(path: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    pairs = (
        pl.read_parquet(
            path,
            columns=[
                "repo_name",
                "pr_number",
                "author_agent",
                "reviewer_agent",
                "first_review_at",
            ],
        )
        .with_columns(
            normalize_repo_expr("repo_name").alias("repo_name"),
            pl.lit(True).alias("a2a_exact_pair"),
        )
        .unique(
            subset=["repo_name", "pr_number", "author_agent", "reviewer_agent"],
            keep="first",
        )
    )
    cross_prs = (
        pairs.select("repo_name", "pr_number")
        .unique()
        .with_columns(pl.lit(True).alias("a2a_cross_pr"))
    )
    if pairs.filter(pl.col("author_agent") == pl.col("reviewer_agent")).height:
        raise AssertionError("External cross-product file contains a same-product pair.")
    return pairs, cross_prs


def build_overlap(
    edge_path: Path,
    pr_map: pl.DataFrame,
    pairs: pl.DataFrame,
    cross_prs: pl.DataFrame,
) -> pl.DataFrame:
    edge = pl.read_parquet(edge_path).sort("pr_id")
    if edge["pr_id"].n_unique() != edge.height:
        raise AssertionError("Addressed-edge cohort is not one row per PR.")

    joined = (
        edge.join(pr_map, on="pr_id", how="left", validate="1:1")
        .join(
            pairs,
            left_on=[
                "repo_name",
                "pr_number",
                "author_agent",
                "trigger_reviewer_agent",
            ],
            right_on=["repo_name", "pr_number", "author_agent", "reviewer_agent"],
            how="left",
            validate="m:1",
        )
        .join(cross_prs, on=["repo_name", "pr_number"], how="left", validate="m:1")
        .with_columns(
            pl.col("a2a_exact_pair").fill_null(False),
            pl.col("a2a_cross_pr").fill_null(False),
        )
        .with_columns(
            (
                (pl.col("first_review_at") - pl.col("trigger_dt"))
                .dt.total_seconds()
                .cast(pl.Float64)
                / 3600
            ).alias("a2a_minus_aidev_trigger_hours")
        )
    )
    if joined.height != edge.height:
        raise AssertionError("External attribution join changed the landmark grain.")
    if joined.filter(pl.col("a2a_exact_pair") & ~pl.col("a2a_cross_pr")).height:
        raise AssertionError("Exact external pair must imply external cross-PR overlap.")
    return joined


def fit_lpm(frame: pd.DataFrame, specification: str) -> dict[str, object]:
    exposure = "exact_parent_reply_by_48h"
    outcome_name = "merged_from_48h_to_30d"
    frame = frame.copy()
    frame[exposure] = frame[exposure].astype(float)
    frame[outcome_name] = frame[outcome_name].astype(float)
    if frame[exposure].nunique(dropna=True) != 2:
        raise AssertionError("External overlap must contain both exposure levels.")
    if specification == "unadjusted":
        terms = [exposure]
    elif specification == "pretrigger_adjusted":
        terms = [
            exposure,
            "C(author_agent)",
            "C(trigger_reviewer_agent)",
            "C(trigger_month)",
            *PRETRIGGER_CONTROLS,
        ]
    else:
        raise ValueError(f"Unknown specification: {specification}")

    formula = outcome_name + " ~ " + " + ".join(terms)
    outcome, design = dmatrices(formula, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    model = sm.OLS(outcome.iloc[:, 0], design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    interval = model.conf_int().loc[exposure]
    return {
        "specification": specification,
        "estimate": float(model.params[exposure]),
        "ci_low": float(interval.iloc[0]),
        "ci_high": float(interval.iloc[1]),
        "p_value": float(model.pvalues[exposure]),
        "n_prs": int(model.nobs),
        "repositories": int(groups.nunique()),
        "exposed_prs": int(frame[exposure].sum()),
        "design_columns": int(design.shape[1]),
        "design_rank": int(np.linalg.matrix_rank(design.to_numpy())),
        "formula": formula,
        "interpretation": (
            "small-overlap attribution sensitivity; observational association, "
            "not an independent outcome replication or causal effect"
        ),
    }


def summarize(joined: pl.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    overlap = joined.filter(pl.col("a2a_cross_pr"))
    matched = joined.filter(pl.col("a2a_exact_pair"))
    conditional_agreement = matched.height / overlap.height if overlap.height else np.nan

    coverage = pd.DataFrame(
        [
            {
                "stage": "AIDev addressed-edge landmark cohort",
                "prs": joined.height,
                "share_of_landmark": 1.0,
            },
            {
                "stage": "PR also appears in external A2A cross-product cohort",
                "prs": overlap.height,
                "share_of_landmark": overlap.height / joined.height,
            },
            {
                "stage": "External source agrees on exact author-reviewer pair",
                "prs": matched.height,
                "share_of_landmark": matched.height / joined.height,
            },
            {
                "stage": "Exact pair agreement conditional on overlapping PR",
                "prs": matched.height,
                "share_of_landmark": conditional_agreement,
            },
            {
                "stage": "Exact-edge exposed PRs in exact-pair overlap",
                "prs": int(matched["exact_parent_reply_by_48h"].sum()),
                "share_of_landmark": (
                    float(matched["exact_parent_reply_by_48h"].mean())
                    if matched.height
                    else np.nan
                ),
            },
        ]
    )

    deltas = matched["a2a_minus_aidev_trigger_hours"].drop_nulls().abs()
    temporal = pd.DataFrame(
        [
            {
                "metric": "exact-pair rows with both trigger timestamps",
                "value": int(deltas.len()),
            },
            {
                "metric": "absolute timestamp difference median hours",
                "value": float(deltas.median()) if deltas.len() else np.nan,
            },
            {
                "metric": "absolute timestamp difference within five minutes",
                "value": float((deltas <= (5 / 60)).mean()) if deltas.len() else np.nan,
            },
            {
                "metric": "absolute timestamp difference within one hour",
                "value": float((deltas <= 1).mean()) if deltas.len() else np.nan,
            },
            {
                "metric": "absolute timestamp difference within 24 hours",
                "value": float((deltas <= 24).mean()) if deltas.len() else np.nan,
            },
        ]
    )

    model_frame = matched.to_pandas()
    models = pd.DataFrame(
        [
            fit_lpm(model_frame, "unadjusted"),
            fit_lpm(model_frame, "pretrigger_adjusted"),
        ]
    )
    return coverage, temporal, models


def write_readme(
    output_dir: Path,
    coverage: pd.DataFrame,
    temporal: pd.DataFrame,
    models: pd.DataFrame,
) -> None:
    overlap = int(coverage.loc[coverage["stage"].str.startswith("PR also"), "prs"].iloc[0])
    agreed = int(coverage.loc[coverage["stage"].str.startswith("External source"), "prs"].iloc[0])
    exposed = int(coverage.loc[coverage["stage"].str.startswith("Exact-edge exposed"), "prs"].iloc[0])
    raw = models.loc[models["specification"] == "unadjusted"].iloc[0]
    adjusted = models.loc[models["specification"] == "pretrigger_adjusted"].iloc[0]
    median = temporal.loc[
        temporal["metric"] == "absolute timestamp difference median hours", "value"
    ].iloc[0]
    text = f"""# Cross-corpus attribution sensitivity

This check joins the paper's fixed AIDev landmark cohort to the independently
released AI-to-AI cross-product cohort derived from CodAGE. The join uses only
public repository name, PR number, and product labels. It does not import an
outcome or post-trigger feature from CodAGE.

Of {overlap:,} landmark PRs that appear in the external cross-product cohort,
{agreed:,} agree on the exact author-reviewer product pair. The median absolute
difference between the two sources' trigger timestamps is {median:.2f} hours.

The exact-pair overlap is too small for a new headline: only {exposed:,} PRs
contain an exact edge. The raw later-merge difference is {100 * raw['estimate']:+.1f}
percentage points, and the pre-trigger-adjusted difference is
{100 * adjusted['estimate']:+.1f} points with a wide interval
[{100 * adjusted['ci_low']:+.1f}, {100 * adjusted['ci_high']:+.1f}]. The direction
is a useful attribution sensitivity, but this is not an independent outcome
replication because both corpora observe public GitHub activity and overlap only
partly.

Safe use: appendix measurement check. Unsafe use: claiming external replication,
causality, semantic resolution, or product-general impact.
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aidev-dir", type=Path, default=DEFAULT_AIDEV)
    parser.add_argument("--a2a-cross", type=Path, default=DEFAULT_A2A)
    parser.add_argument("--edge-cohort", type=Path, default=DEFAULT_EDGE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    pr_map = load_pr_map(args.aidev_dir)
    pairs, cross_prs = load_a2a_pairs(args.a2a_cross)
    joined = build_overlap(args.edge_cohort, pr_map, pairs, cross_prs)
    coverage, temporal, models = summarize(joined)

    public_columns = [
        "pr_id",
        "repo_id",
        "author_agent",
        "trigger_reviewer_agent",
        "trigger_dt",
        "a2a_cross_pr",
        "a2a_exact_pair",
        "first_review_at",
        "a2a_minus_aidev_trigger_hours",
        "exact_parent_reply_by_48h",
        "merged_from_48h_to_30d",
    ]
    joined.select(public_columns).write_parquet(
        args.output_dir / "overlap_cohort.parquet", compression="zstd"
    )
    coverage.to_csv(args.output_dir / "attribution_coverage.csv", index=False)
    temporal.to_csv(args.output_dir / "temporal_concordance.csv", index=False)
    models.to_csv(args.output_dir / "later_merge_sensitivity.csv", index=False)
    write_readme(args.output_dir, coverage, temporal, models)

    manifest = {
        "analysis": "cross-corpus attribution sensitivity",
        "aidev_revision": AIDEV_REVISION,
        "a2a_replication_revision": A2A_REVISION,
        "grain": "one AIDev landmark PR",
        "join_keys": [
            "normalized repository name",
            "PR number",
            "author product",
            "reviewer product",
        ],
        "inputs": {
            str(args.edge_cohort): sha256_file(args.edge_cohort),
            str(args.a2a_cross): sha256_file(args.a2a_cross),
            str(args.aidev_dir / "pull_request.parquet"): sha256_file(
                args.aidev_dir / "pull_request.parquet"
            ),
        },
        "quality_gates": {
            "aidev_pr_map_unique": True,
            "landmark_grain_preserved": True,
            "external_cross_file_has_no_same_product_pairs": True,
            "exact_pair_implies_cross_pr_overlap": True,
            "external_outcome_imported": False,
            "claim_status": "APPENDIX_SENSITIVITY_ONLY",
        },
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(coverage.to_string(index=False))
    print(models[["specification", "estimate", "ci_low", "ci_high", "n_prs"]].to_string(index=False))


if __name__ == "__main__":
    main()
