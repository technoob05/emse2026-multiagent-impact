"""Direct exact-file successor analysis for multi-agent handoff scarcity.

The unit is a closed-unmerged PR in AIDev-pop with at least one observed file.
For every file it touched, we locate the first later PR in the same repository
that touches the exact path, then retain the earliest successor across paths.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm

from multiagent_impact.pipeline import BLUE, INK, ORANGE, add_figure_header, configure_plotting, save_figure


HANDOFF_DAYS = 30
HANDOFF_CUTOFF = pd.Timestamp("2026-03-01 23:59:59", tz="UTC")
GENERIC_PATH = (
    r"(?i)(^|/)(readme(?:\.[^/]*)?|license(?:\.[^/]*)?|changelog(?:\.[^/]*)?|"
    r"package-lock\.json|yarn\.lock|pnpm-lock(?:\.yaml)?|poetry\.lock|cargo\.lock|"
    r"go\.sum|requirements(?:\.[^/]*)?)(?:$|/)"
)


def parse_datetime(column: str) -> pl.Expr:
    return pl.col(column).str.to_datetime(strict=False, time_zone="UTC")


def load_inputs(data_dir: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    prs = (
        pl.scan_parquet(data_dir / "pull_request.parquet")
        .select(
            pl.col("id").alias("pr_id"),
            "repo_id",
            "repo_url",
            "agent",
            "user_id",
            parse_datetime("created_at").alias("created_dt"),
            parse_datetime("closed_at").alias("closed_dt"),
            parse_datetime("merged_at").alias("merged_dt"),
        )
        .collect(engine="streaming")
    )
    files = (
        pl.scan_parquet(data_dir / "pr_commit_details.parquet")
        .select("pr_id", "filename")
        .filter(pl.col("filename").is_not_null() & (pl.col("filename") != ""))
        .unique(["pr_id", "filename"])
        .collect(engine="streaming")
    )
    return prs, files


def build_direct_successors(
    prs: pl.DataFrame,
    files: pl.DataFrame,
    cutoff: pd.Timestamp = HANDOFF_CUTOFF,
    handoff_days: int = HANDOFF_DAYS,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, Any]]:
    """Build an all-index ledger and a successor-only episode ledger."""
    cutoff_value = cutoff.to_pydatetime()
    file_prs = files.select("pr_id").unique()
    covered = prs.join(file_prs, on="pr_id", how="inner")
    eligible = covered.filter(
        pl.col("created_dt").is_not_null()
        & pl.col("closed_dt").is_not_null()
        & (pl.col("closed_dt") >= pl.col("created_dt"))
        & pl.col("merged_dt").is_null()
        & (pl.col("closed_dt") <= pl.lit(cutoff_value))
    )

    successor_files = (
        files.join(
            covered.select("pr_id", "repo_id", "created_dt"), on="pr_id", how="inner"
        )
        .rename({"pr_id": "successor_id", "created_dt": "successor_created_dt"})
        .with_columns(
            pl.len()
            .over(["repo_id", "filename", "successor_created_dt"])
            .alias("path_time_tie_n")
        )
        .sort(["repo_id", "filename", "successor_created_dt", "successor_id"])
    )
    failed_files = (
        files.join(
            eligible.select("pr_id", "repo_id", "closed_dt"), on="pr_id", how="inner"
        )
        .rename({"pr_id": "failed_id", "closed_dt": "prior_closed_dt"})
        .sort(["repo_id", "filename", "prior_closed_dt", "failed_id"])
    )
    matches = (
        failed_files.join_asof(
            successor_files,
            left_on="prior_closed_dt",
            right_on="successor_created_dt",
            by=["repo_id", "filename"],
            strategy="forward",
            allow_exact_matches=False,
            check_sortedness=False,
        )
        .filter(pl.col("successor_id").is_not_null())
        .with_columns((~pl.col("filename").str.contains(GENERIC_PATH)).alias("non_generic_path"))
    )
    pair_candidates = matches.group_by("failed_id", "successor_id", "successor_created_dt").agg(
        pl.len().alias("shared_files"),
        pl.col("non_generic_path").sum().alias("shared_non_generic_files"),
        pl.col("path_time_tie_n").max().alias("path_time_tie_n"),
        pl.col("filename").sort().first().alias("example_shared_file"),
    )
    earliest_time = pair_candidates.group_by("failed_id").agg(
        pl.col("successor_created_dt").min().alias("earliest_successor_dt")
    )
    earliest = (
        pair_candidates.join(earliest_time, on="failed_id", how="inner")
        .filter(pl.col("successor_created_dt") == pl.col("earliest_successor_dt"))
        .with_columns(pl.len().over("failed_id").alias("candidate_time_tie_n"))
        .sort(["failed_id", "successor_id"])
        .unique("failed_id", keep="first", maintain_order=True)
        .with_columns(
            pl.max_horizontal("path_time_tie_n", "candidate_time_tie_n").alias(
                "successor_tie_n"
            )
        )
        .drop("earliest_successor_dt", "path_time_tie_n", "candidate_time_tie_n")
    )

    prior = eligible.select(
        pl.col("pr_id").alias("failed_id"),
        "repo_id",
        "repo_url",
        pl.col("agent").alias("prior_agent"),
        pl.col("user_id").alias("prior_user_id"),
        pl.col("closed_dt").alias("prior_closed_dt"),
    )
    current = covered.select(
        pl.col("pr_id").alias("successor_id"),
        pl.col("agent").alias("current_agent"),
        pl.col("user_id").alias("current_user_id"),
        pl.col("created_dt").alias("successor_created_dt_check"),
        pl.col("merged_dt").alias("successor_merged_dt"),
    )
    successors = (
        earliest.join(prior, on="failed_id", how="inner")
        .join(current, on="successor_id", how="inner")
        .with_columns(
            (
                (pl.col("successor_created_dt") - pl.col("prior_closed_dt")).dt.total_seconds()
                / 86400.0
            ).alias("days_to_successor"),
            (pl.col("prior_agent") != pl.col("current_agent")).alias("changed_agent"),
            (pl.col("prior_user_id") == pl.col("current_user_id")).alias("same_contributor"),
        )
        .with_columns(
            (
                pl.col("successor_merged_dt").is_not_null()
                & (pl.col("successor_merged_dt") >= pl.col("successor_created_dt"))
                & (
                    pl.col("successor_merged_dt")
                    <= pl.col("prior_closed_dt") + pl.duration(days=handoff_days)
                )
            ).alias("recovered_within_30d")
        )
        .filter(pl.col("days_to_successor") <= handoff_days)
        .with_columns(
            pl.len().over("successor_id").alias("failed_prs_per_successor"),
            pl.when(pl.col("same_contributor") & ~pl.col("changed_agent"))
            .then(pl.lit("same contributor / same agent"))
            .when(pl.col("same_contributor") & pl.col("changed_agent"))
            .then(pl.lit("same contributor / different agent"))
            .when(~pl.col("same_contributor") & ~pl.col("changed_agent"))
            .then(pl.lit("different contributor / same agent"))
            .otherwise(pl.lit("different contributor / different agent"))
            .alias("transition_mode"),
        )
    )
    index_ledger = prior.join(
        successors.select("failed_id", "successor_id", "days_to_successor"),
        on="failed_id",
        how="left",
    ).with_columns(pl.col("successor_id").is_not_null().alias("has_successor_30d"))
    quality = {
        "rich_prs": prs.height,
        "file_path_rows": files.height,
        "file_covered_prs": covered.height,
        "usable_file_pr_coverage": covered.height / prs.height if prs.height else np.nan,
        "eligible_closed_unmerged_prs": eligible.height,
        "successors_within_30d": successors.height,
        "successor_prevalence": successors.height / eligible.height if eligible.height else np.nan,
        "ambiguous_earliest_ties": successors.filter(pl.col("successor_tie_n") > 1).height,
        "reused_successor_rows": successors.filter(pl.col("failed_prs_per_successor") > 1).height,
        "unique_successors": successors["successor_id"].n_unique(),
        "repositories": successors["repo_url"].n_unique(),
    }
    return index_ledger, successors, quality


def _clustered_contrast(frame: pd.DataFrame) -> dict[str, float]:
    design = sm.add_constant(frame["changed_agent"].astype(float))
    groups, _ = pd.factorize(frame["repo_url"], sort=False)
    result = sm.OLS(frame["recovered_within_30d"].astype(float), design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    ci = result.conf_int().loc["changed_agent"]
    return {
        "estimate": float(result.params["changed_agent"]),
        "std_error": float(result.bse["changed_agent"]),
        "p_value": float(result.pvalues["changed_agent"]),
        "ci_low": float(ci.iloc[0]),
        "ci_high": float(ci.iloc[1]),
        "n": len(frame),
        "repositories": frame["repo_url"].nunique(),
    }


def build_composition(successors: pl.DataFrame) -> pd.DataFrame:
    return (
        successors.group_by("transition_mode")
        .agg(
            pl.len().alias("n"),
            pl.col("repo_url").n_unique().alias("repositories"),
            pl.col("recovered_within_30d").sum().alias("recovered"),
            pl.col("recovered_within_30d").mean().alias("recovery_rate"),
            pl.col("days_to_successor").median().alias("median_days_to_successor"),
            pl.col("shared_files").median().alias("median_shared_files"),
        )
        .sort("n", descending=True)
        .to_pandas()
    )


def build_clustered_contrasts(successors: pl.DataFrame) -> pd.DataFrame:
    data = successors.to_pandas()
    rows: list[dict[str, Any]] = []
    for same_contributor, label in [(True, "same contributor"), (False, "different contributor")]:
        cell = data.loc[data["same_contributor"] == same_contributor].copy()
        if cell["changed_agent"].nunique() < 2:
            continue
        changed = cell.loc[cell["changed_agent"], "recovered_within_30d"]
        stable = cell.loc[~cell["changed_agent"], "recovered_within_30d"]
        row = _clustered_contrast(cell)
        row.update(
            {
                "contributor_relation": label,
                "changed_agent_n": len(changed),
                "same_agent_n": len(stable),
                "changed_agent_rate": changed.mean(),
                "same_agent_rate": stable.mean(),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_within_context(successors: pl.DataFrame, bootstraps: int = 5000) -> pd.DataFrame:
    data = successors.filter(~pl.col("same_contributor")).to_pandas()
    strata = (
        data.groupby(["repo_url", "prior_agent", "changed_agent"])["recovered_within_30d"]
        .agg(n="size", rate="mean")
        .reset_index()
    )
    counts = strata.pivot(index=["repo_url", "prior_agent"], columns="changed_agent", values="n").dropna()
    rates = strata.pivot(index=["repo_url", "prior_agent"], columns="changed_agent", values="rate").dropna()
    eligible = counts.index.intersection(rates.index)
    rows: list[dict[str, Any]] = []
    groups = [("ALL", list(eligible))]
    groups.extend((agent, [key for key in eligible if key[1] == agent]) for agent in sorted({key[1] for key in eligible}))
    rng = np.random.default_rng(20260825)
    for agent, keys in groups:
        if not keys:
            continue
        weights = 2 / (1 / counts.loc[keys, False] + 1 / counts.loc[keys, True])
        differences = rates.loc[keys, True] - rates.loc[keys, False]
        samples = rng.integers(0, len(keys), size=(bootstraps, len(keys)))
        boot = np.array(
            [np.average(differences.iloc[index], weights=weights.iloc[index]) for index in samples]
        )
        rows.append(
            {
                "prior_agent": agent,
                "repo_prior_agent_strata": len(keys),
                "changed_agent_n": int(counts.loc[keys, True].sum()),
                "same_agent_n": int(counts.loc[keys, False].sum()),
                "estimate": float(np.average(differences, weights=weights)),
                "ci_low": float(np.quantile(boot, 0.025)),
                "ci_high": float(np.quantile(boot, 0.975)),
            }
        )
    return pd.DataFrame(rows)


def build_sensitivity(successors: pl.DataFrame) -> pd.DataFrame:
    data = successors.filter(~pl.col("same_contributor")).to_pandas()
    masks = {
        "all exact-file successors": np.ones(len(data), dtype=bool),
        "unambiguous earliest successor": data["successor_tie_n"] == 1,
        "successor linked to one failed PR": data["failed_prs_per_successor"] == 1,
        "non-generic shared path": data["shared_non_generic_files"] > 0,
        "at least two shared paths": data["shared_files"] >= 2,
        "successor starts within 7 days": data["days_to_successor"] <= 7,
        "successor starts within 14 days": data["days_to_successor"] <= 14,
    }
    rows: list[dict[str, Any]] = []
    for definition, mask in masks.items():
        cell = data.loc[mask].copy()
        if cell.empty or cell["changed_agent"].nunique() < 2:
            continue
        row = _clustered_contrast(cell)
        row.update(
            {
                "definition": definition,
                "changed_agent_n": int(cell["changed_agent"].sum()),
                "same_agent_n": int((~cell["changed_agent"]).sum()),
            }
        )
        rows.append(row)
    nearest_failure = (
        data.sort_values(["successor_id", "days_to_successor"])
        .drop_duplicates("successor_id", keep="first")
        .copy()
    )
    if not nearest_failure.empty and nearest_failure["changed_agent"].nunique() == 2:
        row = _clustered_contrast(nearest_failure)
        row.update(
            {
                "definition": "nearest failed PR per successor",
                "changed_agent_n": int(nearest_failure["changed_agent"].sum()),
                "same_agent_n": int((~nearest_failure["changed_agent"]).sum()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def plot_story(
    quality: dict[str, Any],
    composition: pd.DataFrame,
    contrasts: pd.DataFrame,
    within_context: pd.DataFrame,
    output_dir: Path,
) -> None:
    configure_plotting()
    fig, axes = plt.subplots(1, 3, figsize=(13.4, 4.7))
    fig.subplots_adjust(top=0.77, bottom=0.25, left=0.07, right=0.98, wspace=0.42)
    add_figure_header(
        fig,
        "Co-presence is not coordination: exact-file handoffs are scarce",
        "AIDev-pop; closed-unmerged index PRs by 1 Mar 2026; successor starts within 30 days",
    )

    ax = axes[0]
    modes = [
        "same contributor / same agent",
        "same contributor / different agent",
        "different contributor / same agent",
        "different contributor / different agent",
    ]
    labels = ["Same contributor\nSame agent", "Same contributor\nNew agent", "New contributor\nSame agent", "New contributor\nNew agent"]
    values = composition.set_index("transition_mode").reindex(modes)["n"].fillna(0).to_numpy()
    shares = values / values.sum() * 100
    colors = ["#9AA4AF", ORANGE, BLUE, "#34495E"]
    bars = ax.barh(np.arange(4), shares, color=colors)
    ax.set_yticks(np.arange(4), labels)
    ax.invert_yaxis()
    ax.set_xlabel("Share of exact-file successors (%)")
    ax.set_title("A  Who and what changed?")
    ax.grid(axis="y", visible=False)
    for bar, share, count in zip(bars, shares, values, strict=True):
        ax.text(bar.get_width() + 0.7, bar.get_y() + bar.get_height() / 2, f"{share:.1f}%  n={int(count):,}", va="center", fontsize=8)

    ax = axes[1]
    ordered = composition.set_index("transition_mode").reindex(modes)
    rates = ordered["recovery_rate"].to_numpy() * 100
    counts = ordered["n"].to_numpy()
    bars = ax.bar(np.arange(4), rates, color=colors)
    ax.set_xticks(np.arange(4), ["Same\nSame", "Same\nNew", "New\nSame", "New\nNew"])
    ax.set_ylabel("Successor merged by day 30 after index closure (%)")
    ax.set_xlabel("Contributor / agent")
    ax.set_ylim(0, 70)
    ax.set_title("B  Later-successor integration")
    ax.grid(axis="x", visible=False)
    for bar, rate, count in zip(bars, rates, counts, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, rate + 1.3, f"{rate:.1f}%\nn={int(count):,}", ha="center", fontsize=8)

    ax = axes[2]
    raw = contrasts.set_index("contributor_relation").loc["different contributor"]
    within = within_context.set_index("prior_agent").loc["ALL"]
    estimates = np.array([raw["estimate"], within["estimate"]]) * 100
    lows = np.array([raw["ci_low"], within["ci_low"]]) * 100
    highs = np.array([raw["ci_high"], within["ci_high"]]) * 100
    for position, color in [(1, ORANGE), (0, BLUE)]:
        index = 1 - position
        ax.errorbar(
            estimates[index],
            position,
            xerr=[[estimates[index] - lows[index]], [highs[index] - estimates[index]]],
            fmt="o",
            color=color,
            ecolor=color,
            capsize=4,
        )
    ax.axvline(0, color=INK, linestyle="--", linewidth=1)
    ax.set_yticks([1, 0], ["Repository-clustered", "Comparable repo +\nprior-agent strata"])
    ax.set_xlabel("New-agent minus same-agent successor integration (pp)")
    ax.set_title("C  Aggregate lift is uncertain")
    ax.grid(axis="y", visible=False)
    for position, estimate, low, high in zip([1, 0], estimates, lows, highs, strict=True):
        ax.text(
            high + 0.8,
            position,
            f"{estimate:+.1f} pp\n[{low:+.1f}, {high:+.1f}]",
            va="center",
            fontsize=8,
        )
    ax.text(0.02, -0.32, f"Eligible failed PRs: {quality['eligible_closed_unmerged_prs']:,}; exact-file successors: {quality['successors_within_30d']:,}", transform=ax.transAxes, fontsize=8, color="#667085")
    save_figure(fig, output_dir / "direct_handoff_story")


def run(data_dir: Path, tables_dir: Path, figures_dir: Path, cache_dir: Path) -> None:
    for directory in [tables_dir, figures_dir, cache_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    print("[1/5] Loading AIDev-pop PR and file tables")
    prs, files = load_inputs(data_dir)
    print("[2/5] Linking each failed PR to its first exact-file successor")
    index_ledger, successors, quality = build_direct_successors(prs, files)
    index_ledger.write_parquet(cache_dir / "direct_handoff_index.parquet", compression="zstd")
    successors.write_parquet(cache_dir / "direct_handoff_successors.parquet", compression="zstd")
    print("[3/5] Computing composition and repository-aware inference")
    composition = build_composition(successors)
    contrasts = build_clustered_contrasts(successors)
    within_context = build_within_context(successors)
    sensitivity = build_sensitivity(successors)
    pd.DataFrame([quality]).to_csv(tables_dir / "direct_handoff_quality.csv", index=False)
    composition.to_csv(tables_dir / "direct_handoff_composition.csv", index=False)
    contrasts.to_csv(tables_dir / "direct_handoff_clustered_contrasts.csv", index=False)
    within_context.to_csv(tables_dir / "direct_handoff_within_context.csv", index=False)
    sensitivity.to_csv(tables_dir / "direct_handoff_sensitivity.csv", index=False)
    print("[4/5] Rendering the handoff story figure")
    plot_story(quality, composition, contrasts, within_context, figures_dir)
    print("[5/5] Core result")
    print(pd.DataFrame([quality]).to_string(index=False))
    print(composition.to_string(index=False))
    print(contrasts.to_string(index=False))
    print(within_context.head(1).to_string(index=False))
