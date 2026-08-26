"""Artifact-level continuity analysis for sequential agent-authored PRs.

This module tests whether an observed agent-brand transition continues work on
the same files or linked issue.  It deliberately treats file/issue evidence as
a partial AIDev-pop subset and reports join coverage before outcome contrasts.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm


TRANSITION_ORDER = [
    "persistence",
    "brand_change_same_contributor",
    "contributor_change_stable_agent",
    "joint_reconfiguration",
]


def _taxonomy_expression() -> pl.Expr:
    return (
        pl.when(pl.col("same_user") & ~pl.col("switched"))
        .then(pl.lit("persistence"))
        .when(pl.col("same_user") & pl.col("switched"))
        .then(pl.lit("brand_change_same_contributor"))
        .when(~pl.col("same_user") & ~pl.col("switched"))
        .then(pl.lit("contributor_change_stable_agent"))
        .otherwise(pl.lit("joint_reconfiguration"))
        .alias("transition_type")
    )


def load_failed_episodes(transitions_path: Path) -> pl.DataFrame:
    """Load episodes whose latest known prior PR closed without merging."""
    columns = [
        "id",
        "prior_id",
        "repo_url",
        "agent",
        "prior_agent",
        "same_user",
        "switched",
        "merged",
        "prior_merged",
        "gap_hours",
        "calendar_month",
        "stars",
    ]
    return (
        pl.read_parquet(transitions_path, columns=columns)
        .filter(~pl.col("prior_merged"))
        .drop("prior_merged")
        .with_columns(_taxonomy_expression())
    )


def load_relevant_files(details_path: Path, episodes: pl.DataFrame) -> pl.DataFrame:
    """Read only PR id and file path for PRs used by the failed-episode ledger."""
    relevant_ids = pl.concat(
        [episodes.select(pl.col("id").alias("pr_id")), episodes.select(pl.col("prior_id").alias("pr_id"))]
    ).unique()
    return (
        pl.scan_parquet(details_path)
        .select("pr_id", "filename")
        .join(relevant_ids.lazy(), on="pr_id", how="inner")
        .filter(pl.col("filename").is_not_null() & (pl.col("filename") != ""))
        .with_columns(pl.col("filename").str.replace_all(r"\\", "/"))
        .unique(["pr_id", "filename"])
        .collect(engine="streaming")
    )


def add_file_continuity(episodes: pl.DataFrame, files: pl.DataFrame) -> pl.DataFrame:
    """Add exact path overlap, Jaccard, and containment to each episode."""
    file_counts = files.group_by("pr_id").agg(pl.len().alias("n_files"))
    enriched = (
        episodes.join(
            file_counts.rename({"pr_id": "id", "n_files": "current_n_files"}),
            on="id",
            how="left",
        )
        .join(
            file_counts.rename({"pr_id": "prior_id", "n_files": "prior_n_files"}),
            on="prior_id",
            how="left",
        )
    )
    current_files = (
        episodes.select(pl.col("id").alias("episode_id"), pl.col("id").alias("pr_id"))
        .join(files, on="pr_id", how="inner")
        .select("episode_id", "filename")
    )
    prior_files = (
        episodes.select(pl.col("id").alias("episode_id"), pl.col("prior_id").alias("pr_id"))
        .join(files, on="pr_id", how="inner")
        .select("episode_id", "filename")
    )
    intersections = (
        current_files.join(prior_files, on=["episode_id", "filename"], how="inner")
        .group_by("episode_id")
        .agg(pl.len().alias("shared_files"))
    )
    return (
        enriched.join(intersections, left_on="id", right_on="episode_id", how="left")
        .with_columns(
            pl.col("shared_files").fill_null(0),
            (pl.col("current_n_files").is_not_null() & pl.col("prior_n_files").is_not_null()).alias(
                "both_file_observed"
            ),
        )
        .with_columns(
            (pl.col("shared_files") > 0).alias("same_file"),
            (
                pl.col("shared_files")
                / (pl.col("current_n_files") + pl.col("prior_n_files") - pl.col("shared_files"))
            ).alias("file_jaccard"),
            (
                pl.col("shared_files")
                / pl.min_horizontal("current_n_files", "prior_n_files")
            ).alias("file_containment"),
        )
    )


def add_issue_continuity(episodes: pl.DataFrame, related_issue_path: Path) -> pl.DataFrame:
    links = (
        pl.read_parquet(related_issue_path, columns=["pr_id", "issue_id"])
        .drop_nulls()
        .unique(["pr_id", "issue_id"])
    )
    linked_prs = links.select("pr_id").unique()
    current = (
        episodes.select(pl.col("id").alias("episode_id"), pl.col("id").alias("pr_id"))
        .join(links, on="pr_id", how="inner")
        .select("episode_id", "issue_id")
    )
    prior = (
        episodes.select(pl.col("id").alias("episode_id"), pl.col("prior_id").alias("pr_id"))
        .join(links, on="pr_id", how="inner")
        .select("episode_id", "issue_id")
    )
    same_issue = (
        current.join(prior, on=["episode_id", "issue_id"], how="inner")
        .group_by("episode_id")
        .agg(pl.len().alias("shared_issues"))
    )
    current_observed = linked_prs.rename({"pr_id": "id"}).with_columns(pl.lit(True).alias("current_issue_observed"))
    prior_observed = linked_prs.rename({"pr_id": "prior_id"}).with_columns(pl.lit(True).alias("prior_issue_observed"))
    return (
        episodes.join(current_observed, on="id", how="left")
        .join(prior_observed, on="prior_id", how="left")
        .join(same_issue, left_on="id", right_on="episode_id", how="left")
        .with_columns(
            pl.col("current_issue_observed").fill_null(False),
            pl.col("prior_issue_observed").fill_null(False),
            pl.col("shared_issues").fill_null(0),
        )
        .with_columns(
            (pl.col("current_issue_observed") & pl.col("prior_issue_observed")).alias("both_issue_observed"),
            (pl.col("shared_issues") > 0).alias("same_issue"),
        )
    )


def coverage_table(data: pl.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for transition_type in TRANSITION_ORDER:
        cell = data.filter(pl.col("transition_type") == transition_type)
        both = cell.filter(pl.col("both_file_observed"))
        rows.append(
            {
                "transition_type": transition_type,
                "all_episodes": cell.height,
                "both_file_observed": both.height,
                "both_file_coverage": both.height / cell.height if cell.height else np.nan,
                "all_merge_rate": cell["merged"].mean() if cell.height else np.nan,
                "file_subset_merge_rate": both["merged"].mean() if both.height else np.nan,
                "file_subset_same_file_share": both["same_file"].mean() if both.height else np.nan,
            }
        )
    return pd.DataFrame(rows)


def continuity_rates(data: pl.DataFrame) -> pd.DataFrame:
    observed = data.filter(pl.col("both_file_observed"))
    return (
        observed.group_by("transition_type", "same_file")
        .agg(
            pl.len().alias("n"),
            pl.col("repo_url").n_unique().alias("repositories"),
            pl.col("merged").mean().alias("merge_rate_30d"),
            pl.col("shared_files").median().alias("median_shared_files"),
            pl.col("file_jaccard").median().alias("median_jaccard"),
            pl.col("gap_hours").median().alias("median_gap_hours"),
        )
        .sort("transition_type", "same_file")
        .to_pandas()
    )


def threshold_sensitivity(data: pl.DataFrame) -> pd.DataFrame:
    observed = data.filter(pl.col("both_file_observed") & pl.col("same_user"))
    rows: list[dict[str, Any]] = []
    for metric, thresholds in [("file_jaccard", [0.0, 0.1, 0.25, 0.5]), ("file_containment", [0.0, 0.25, 0.5, 0.75])]:
        for threshold in thresholds:
            if threshold == 0:
                cell = observed.filter(pl.col("shared_files") > 0)
            else:
                cell = observed.filter(pl.col(metric) >= threshold)
            stay = cell.filter(~pl.col("switched"))
            switch = cell.filter(pl.col("switched"))
            if not stay.height or not switch.height:
                continue
            stay_rate = float(stay["merged"].mean())
            switch_rate = float(switch["merged"].mean())
            se = math.sqrt(
                stay_rate * (1 - stay_rate) / stay.height
                + switch_rate * (1 - switch_rate) / switch.height
            )
            effect = switch_rate - stay_rate
            rows.append(
                {
                    "metric": metric,
                    "threshold": threshold,
                    "stay_n": stay.height,
                    "switch_n": switch.height,
                    "stay_merge_rate": stay_rate,
                    "switch_merge_rate": switch_rate,
                    "effect_pp": effect * 100,
                    "ci_low_pp": (effect - 1.96 * se) * 100,
                    "ci_high_pp": (effect + 1.96 * se) * 100,
                }
            )
    return pd.DataFrame(rows)


def fit_same_contributor_lpm(data: pl.DataFrame) -> pd.DataFrame:
    """Estimate whether the brand-change contrast differs by file continuity."""
    frame = data.filter(pl.col("both_file_observed") & pl.col("same_user")).to_pandas()
    frame["merged"] = frame["merged"].astype(float)
    frame["switched"] = frame["switched"].astype(float)
    frame["same_file"] = frame["same_file"].astype(float)
    frame["switch_x_same_file"] = frame["switched"] * frame["same_file"]
    frame["log1p_gap_hours"] = np.log1p(frame["gap_hours"].clip(lower=0, upper=24 * 365))
    frame["log1p_current_files"] = np.log1p(frame["current_n_files"].clip(lower=1))
    frame["log1p_prior_files"] = np.log1p(frame["prior_n_files"].clip(lower=1))
    categorical = pd.get_dummies(
        frame[["agent", "prior_agent", "calendar_month"]],
        prefix=["current", "prior", "month"],
        drop_first=True,
        dtype=float,
    )
    core = [
        "switched",
        "same_file",
        "switch_x_same_file",
        "log1p_gap_hours",
        "log1p_current_files",
        "log1p_prior_files",
    ]
    design = pd.concat([frame[core], categorical], axis=1)
    numeric = pd.concat([frame[["merged"]], design], axis=1)
    repo_means = numeric.groupby(frame["repo_url"], sort=False).transform("mean")
    y_within = numeric["merged"] - repo_means["merged"]
    x_within = design - repo_means[design.columns]
    x_within = x_within.loc[:, x_within.var() > 1e-12]
    groups, _ = pd.factorize(frame["repo_url"], sort=False)
    result = sm.OLS(y_within, x_within, hasconst=False).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    table = pd.DataFrame(
        {
            "term": result.params.index,
            "estimate": result.params.values,
            "std_error": result.bse.values,
            "p_value": result.pvalues.values,
            "ci_low": result.conf_int()[0].values,
            "ci_high": result.conf_int()[1].values,
            "n": int(result.nobs),
            "repositories": int(pd.Series(groups).nunique()),
            "r_squared_within": float(result.rsquared),
        }
    )
    if {"switched", "switch_x_same_file"}.issubset(result.params.index):
        covariance = result.cov_params()
        estimate = float(result.params["switched"] + result.params["switch_x_same_file"])
        variance = float(
            covariance.loc["switched", "switched"]
            + covariance.loc["switch_x_same_file", "switch_x_same_file"]
            + 2 * covariance.loc["switched", "switch_x_same_file"]
        )
        std_error = math.sqrt(max(variance, 0.0))
        z_score = estimate / std_error if std_error else float("nan")
        table = pd.concat(
            [
                table,
                pd.DataFrame(
                    {
                        "term": ["switched_with_same_file"],
                        "estimate": [estimate],
                        "std_error": [std_error],
                        "p_value": [math.erfc(abs(z_score) / math.sqrt(2))],
                        "ci_low": [estimate - 1.96 * std_error],
                        "ci_high": [estimate + 1.96 * std_error],
                        "n": [int(result.nobs)],
                        "repositories": [int(pd.Series(groups).nunique())],
                        "r_squared_within": [float(result.rsquared)],
                    }
                ),
            ],
            ignore_index=True,
        )
    return table


def issue_summary(data: pl.DataFrame) -> pd.DataFrame:
    both = data.filter(pl.col("both_issue_observed"))
    if not both.height:
        return pd.DataFrame()
    return (
        both.group_by("transition_type", "same_issue")
        .agg(
            pl.len().alias("n"),
            pl.col("repo_url").n_unique().alias("repositories"),
            pl.col("merged").mean().alias("merge_rate_30d"),
        )
        .sort("transition_type", "same_issue")
        .to_pandas()
    )


def run(
    transitions_path: Path,
    details_path: Path,
    related_issue_path: Path,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("[1/5] Loading closed-unmerged transition episodes")
    episodes = load_failed_episodes(transitions_path)
    print(f"  {episodes.height:,} episodes")
    print("[2/5] Reading file paths for relevant PR pairs")
    files = load_relevant_files(details_path, episodes)
    print(f"  {files.height:,} unique PR-file paths across {files['pr_id'].n_unique():,} PRs")
    print("[3/5] Building exact file and issue continuity measures")
    data = add_file_continuity(episodes, files)
    data = add_issue_continuity(data, related_issue_path)
    data.write_parquet(output_dir / "artifact_handoff_episodes.parquet", compression="zstd")
    coverage = coverage_table(data)
    rates = continuity_rates(data)
    sensitivity = threshold_sensitivity(data)
    issues = issue_summary(data)
    print("[4/5] Fitting same-contributor within-repository model")
    model = fit_same_contributor_lpm(data)
    coverage.to_csv(output_dir / "artifact_handoff_coverage.csv", index=False)
    rates.to_csv(output_dir / "artifact_handoff_rates.csv", index=False)
    sensitivity.to_csv(output_dir / "artifact_handoff_thresholds.csv", index=False)
    issues.to_csv(output_dir / "artifact_handoff_issues.csv", index=False)
    model.to_csv(output_dir / "artifact_handoff_within_repo_lpm.csv", index=False)
    print("[5/5] Key same-contributor cells")
    focus = rates[rates["transition_type"].isin(["persistence", "brand_change_same_contributor"])]
    print(focus.to_string(index=False))
    print("\nThreshold sensitivity")
    print(sensitivity.to_string(index=False))
    print("\nFocused model terms")
    print(model[model["term"].isin(["switched", "switch_x_same_file", "switched_with_same_file"])].to_string(index=False))
