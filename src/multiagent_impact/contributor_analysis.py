"""Contributor-aware transition analysis for the EMSE working paper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm

from multiagent_impact.pipeline import (
    BLUE,
    INK,
    add_figure_header,
    configure_plotting,
    save_figure,
)

MUTED = "#667085"


TRANSITION_ORDER = [
    "persistence",
    "brand_change_same_contributor",
    "contributor_change_stable_agent",
    "joint_reconfiguration",
]

TRANSITION_LABELS = {
    "persistence": "Same contributor,\nsame agent",
    "brand_change_same_contributor": "Same contributor,\ndifferent agent",
    "contributor_change_stable_agent": "Different contributor,\nsame agent",
    "joint_reconfiguration": "Different contributor,\ndifferent agent",
}


def add_transition_taxonomy(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Classify episodes by agent-brand and contributor continuity."""
    return frame.with_columns(
        pl.when(pl.col("same_user") & ~pl.col("switched"))
        .then(pl.lit("persistence"))
        .when(pl.col("same_user") & pl.col("switched"))
        .then(pl.lit("brand_change_same_contributor"))
        .when(~pl.col("same_user") & ~pl.col("switched"))
        .then(pl.lit("contributor_change_stable_agent"))
        .otherwise(pl.lit("joint_reconfiguration"))
        .alias("transition_type")
    )


def _clustered_intercept(values: pd.Series, groups: pd.Series) -> dict[str, float]:
    design = np.ones((len(values), 1))
    group_codes, _ = pd.factorize(groups, sort=False)
    result = sm.OLS(values.astype(float), design).fit(
        cov_type="cluster",
        cov_kwds={"groups": group_codes, "use_correction": True},
    )
    estimate = float(result.params.iloc[0])
    std_error = float(result.bse.iloc[0])
    return {
        "estimate": estimate,
        "std_error": std_error,
        "ci_low": estimate - 1.96 * std_error,
        "ci_high": estimate + 1.96 * std_error,
    }


def build_taxonomy_tables(transitions_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = ["repo_url", "prior_merged", "switched", "same_user", "merged"]
    data = pl.read_parquet(transitions_path, columns=columns).lazy()
    data = add_transition_taxonomy(data).collect().to_pandas()

    distribution_rows: list[dict[str, Any]] = []
    for prior_merged in [False, True]:
        subset = data.loc[data["prior_merged"] == prior_merged].copy()
        for transition_type in TRANSITION_ORDER:
            indicator = (subset["transition_type"] == transition_type).astype(float)
            stats = _clustered_intercept(indicator, subset["repo_url"])
            distribution_rows.append(
                {
                    "prior_merged": prior_merged,
                    "prior_outcome": "Prior merged" if prior_merged else "Prior closed-unmerged",
                    "transition_type": transition_type,
                    "transition_label": TRANSITION_LABELS[transition_type].replace("\n", " "),
                    "n": int(indicator.sum()),
                    "episodes": int(len(subset)),
                    "repositories": int(subset["repo_url"].nunique()),
                    "share": stats["estimate"],
                    "std_error": stats["std_error"],
                    "ci_low": stats["ci_low"],
                    "ci_high": stats["ci_high"],
                }
            )

    recovery_rows: list[dict[str, Any]] = []
    subset = data.loc[~data["prior_merged"]].copy()
    for transition_type in TRANSITION_ORDER:
        cell = subset.loc[subset["transition_type"] == transition_type]
        stats = _clustered_intercept(cell["merged"], cell["repo_url"])
        recovery_rows.append(
            {
                "transition_type": transition_type,
                "transition_label": TRANSITION_LABELS[transition_type].replace("\n", " "),
                "n": int(len(cell)),
                "repositories": int(cell["repo_url"].nunique()),
                "merge_rate_30d": stats["estimate"],
                "std_error": stats["std_error"],
                "ci_low": stats["ci_low"],
                "ci_high": stats["ci_high"],
            }
        )
    return pd.DataFrame(distribution_rows), pd.DataFrame(recovery_rows)


def fit_contributor_aware_lpm(transitions_path: Path) -> pd.DataFrame:
    """Fit a repository-FE LPM after a closed-unmerged prior PR.

    Coefficients compare each reconfiguration type with persistence while
    adjusting for current/prior agent, month, and inter-episode gap. Standard
    errors are clustered by repository.
    """
    columns = [
        "repo_url", "merged", "prior_merged", "switched", "same_user",
        "gap_hours", "agent", "prior_agent", "calendar_month",
    ]
    lazy = pl.read_parquet(transitions_path, columns=columns).lazy()
    data = add_transition_taxonomy(lazy).filter(~pl.col("prior_merged")).collect().to_pandas()
    data["merged"] = data["merged"].astype(float)
    data["log1p_gap_hours"] = np.log1p(data["gap_hours"].clip(lower=0, upper=24 * 365))
    for category in TRANSITION_ORDER[1:]:
        data[f"type_{category}"] = (data["transition_type"] == category).astype(float)

    categorical = pd.get_dummies(
        data[["agent", "prior_agent", "calendar_month"]],
        prefix=["current", "prior", "month"],
        drop_first=True,
        dtype=float,
    )
    transition_terms = [f"type_{value}" for value in TRANSITION_ORDER[1:]]
    design = pd.concat([data[transition_terms + ["log1p_gap_hours"]], categorical], axis=1)
    numeric = pd.concat([data[["merged"]], design], axis=1)
    repo_means = numeric.groupby(data["repo_url"], sort=False).transform("mean")
    y_within = numeric["merged"] - repo_means["merged"]
    x_within = design - repo_means[design.columns]
    x_within = x_within.loc[:, x_within.var() > 1e-12]
    groups, _ = pd.factorize(data["repo_url"], sort=False)
    result = sm.OLS(y_within, x_within, hasconst=False).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    return pd.DataFrame(
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


def plot_contributor_taxonomy(distribution: pd.DataFrame, recovery: pd.DataFrame, output_dir: Path) -> None:
    configure_plotting()
    colors = ["#778DA9", BLUE, "#E9A23B", "#8F5DA2"]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.5))
    fig.subplots_adjust(top=0.76, bottom=0.27, left=0.08, right=0.98, wspace=0.28)
    add_figure_header(
        fig,
        "Agent-brand change and contributor turnover are not interchangeable",
        "Outcome-known, non-overlapping episodes after observed multi-agent-brand onset",
    )

    left = axes[0]
    outcomes = ["Prior closed-unmerged", "Prior merged"]
    bottoms = np.zeros(len(outcomes))
    for color, transition_type in zip(colors, TRANSITION_ORDER, strict=True):
        cell = distribution.loc[distribution["transition_type"] == transition_type].set_index("prior_outcome").reindex(outcomes)
        shares = cell["share"].to_numpy() * 100
        left.bar(
            outcomes, shares, bottom=bottoms, color=color, edgecolor="white",
            linewidth=0.8, label=TRANSITION_LABELS[transition_type].replace("\n", " "),
        )
        for position, (bottom, share) in enumerate(zip(bottoms, shares, strict=True)):
            if share >= 6:
                left.text(
                    position, bottom + share / 2, f"{share:.1f}%", ha="center",
                    va="center", fontsize=8.5,
                    color="white" if color != "#E9A23B" else INK, fontweight="bold",
                )
        bottoms += shares
    left.set_title("A  Transition composition")
    left.set_ylabel("Share of next episodes (%)")
    left.set_ylim(0, 100)
    left.tick_params(axis="x", rotation=8)
    left.grid(axis="x", visible=False)

    right = axes[1]
    recovery = recovery.set_index("transition_type").reindex(TRANSITION_ORDER)
    positions = np.arange(len(TRANSITION_ORDER))
    rates = recovery["merge_rate_30d"].to_numpy() * 100
    lower = (recovery["merge_rate_30d"] - recovery["ci_low"]).to_numpy() * 100
    upper = (recovery["ci_high"] - recovery["merge_rate_30d"]).to_numpy() * 100
    right.errorbar(
        positions, rates, yerr=np.vstack([lower, upper]), fmt="o", markersize=8,
        color=INK, ecolor=MUTED, elinewidth=1.6, capsize=4,
    )
    for position, rate, count in zip(positions, rates, recovery["n"].to_numpy(), strict=True):
        right.text(position, rate + 2.1, f"{rate:.1f}%\nn={count:,}", ha="center", fontsize=8)
    right.set_title("B  30-day integration after closed-unmerged")
    right.set_ylabel("PRs merged within 30 days (%)")
    right.set_xticks(positions, [TRANSITION_LABELS[x] for x in TRANSITION_ORDER])
    right.set_ylim(40, 80)
    right.grid(axis="x", visible=False)

    handles, labels = left.get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="lower center", ncol=2, frameon=False,
        bbox_to_anchor=(0.5, 0.01), fontsize=8.5,
    )
    save_figure(fig, output_dir / "contributor_aware_transition_taxonomy")


def write_contributor_summary(
    distribution: pd.DataFrame,
    recovery: pd.DataFrame,
    adjusted: pd.DataFrame,
    output_path: Path,
) -> None:
    rates = recovery.set_index("transition_type")["merge_rate_30d"]
    terms = adjusted.set_index("term")
    key = "type_brand_change_same_contributor"
    failed = distribution.loc[~distribution["prior_merged"]].set_index("transition_type")
    text = f"""# Contributor-aware impact exploration

## Central insight

The aggregate agent-switch contrast hides opposing transition types. Following
an outcome-known closed-unmerged PR:

- same contributor, different agent: {rates['brand_change_same_contributor']:.1%} merged within 30 days;
- same contributor, same agent: {rates['persistence']:.1%};
- different contributor, same agent: {rates['contributor_change_stable_agent']:.1%}; and
- different contributor, different agent: {rates['joint_reconfiguration']:.1%}.

The raw same-contributor brand-change contrast is
{(rates['brand_change_same_contributor'] - rates['persistence']) * 100:.2f} percentage points.
In the within-repository linear probability model adjusting for current/prior
agent, calendar month, and inter-episode gap, the corresponding coefficient is
{terms.loc[key, 'estimate'] * 100:.2f} percentage points (95% CI
{terms.loc[key, 'ci_low'] * 100:.2f}, {terms.loc[key, 'ci_high'] * 100:.2f}).
This is an association, not a causal recovery effect.

## Composition after closed-unmerged outcomes

- same-contributor brand change: {failed.loc['brand_change_same_contributor', 'share']:.1%};
- contributor change with stable agent: {failed.loc['contributor_change_stable_agent', 'share']:.1%};
- joint contributor/agent reconfiguration: {failed.loc['joint_reconfiguration', 'share']:.1%}; and
- persistence: {failed.loc['persistence', 'share']:.1%}.

## Interpretation boundary

The same-contributor/different-agent cell is the strongest observable proxy for
a person changing coding-agent brand, but trace data still do not reveal intent,
decision-maker, task equivalence, or account sharing. Different-contributor
cells must not be described as individual tool switching.
"""
    output_path.write_text(text, encoding="utf-8")


def run(transitions_path: Path, tables_dir: Path, figures_dir: Path) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    distribution, recovery = build_taxonomy_tables(transitions_path)
    adjusted = fit_contributor_aware_lpm(transitions_path)
    distribution.to_csv(tables_dir / "transition_taxonomy_distribution.csv", index=False)
    recovery.to_csv(tables_dir / "transition_taxonomy_recovery.csv", index=False)
    adjusted.to_csv(tables_dir / "transition_taxonomy_within_repo_lpm.csv", index=False)
    plot_contributor_taxonomy(distribution, recovery, figures_dir)
    write_contributor_summary(
        distribution, recovery, adjusted,
        tables_dir.parent / "CONTRIBUTOR_AWARE_SUMMARY.md",
    )
