from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
import statsmodels.api as sm


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATASET_REVISION = "37bbe1533e26cc1e1374917dba1186d1c8a4dc81"
DATASET_CUTOFF = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
FOLLOWUP_DAYS = 30
AGENT_ORDER = [
    "Claude_Code",
    "Copilot",
    "Cursor",
    "Devin",
    "Google_Jules",
    "OpenAI_Codex",
]
BLUE = "#3972B6"
ORANGE = "#D9822B"
GOLD = "#C9A227"
INK = "#252A34"
GRID = "#D9DEE7"


@dataclass(frozen=True)
class AnalysisConfig:
    project_root: Path
    data_dir: Path
    output_dir: Path
    event_window: int = 10
    seed: int = 20260825

    @classmethod
    def from_paths(
        cls,
        project_root: Path,
        data_dir: Path | None = None,
        event_window: int = 10,
    ) -> "AnalysisConfig":
        project_root = project_root.resolve()
        env_data = os.environ.get("AIDEV_DATA_DIR")
        resolved_data = (
            data_dir
            or (Path(env_data) if env_data else None)
            or project_root.parent
            / "Legacy"
            / "AI_Dev_Dataminning"
            / "AIDev-7.6M"
        )
        return cls(
            project_root=project_root,
            data_dir=Path(resolved_data).resolve(),
            output_dir=project_root / "outputs",
            event_window=event_window,
        )


def add_time_columns(frame: pl.LazyFrame) -> pl.LazyFrame:
    return frame.with_columns(
        pl.col("created_at")
        .str.to_datetime(TIMESTAMP_FORMAT, time_zone="UTC", strict=False)
        .alias("created_dt"),
        pl.col("closed_at")
        .str.to_datetime(TIMESTAMP_FORMAT, time_zone="UTC", strict=False)
        .alias("closed_dt"),
        pl.col("merged_at")
        .str.to_datetime(TIMESTAMP_FORMAT, time_zone="UTC", strict=False)
        .alias("merged_dt"),
        pl.col("merged_at").is_not_null().alias("merged"),
    ).drop("created_at", "closed_at", "merged_at")


def valid_resolved_expression() -> pl.Expr:
    """Keep outcomes whose recorded resolution cannot predate PR creation."""
    return (
        pl.col("closed_dt").is_not_null()
        & (pl.col("closed_dt") >= pl.col("created_dt"))
        & (pl.col("merged_dt").is_null() | (pl.col("merged_dt") >= pl.col("created_dt")))
    )


def load_pull_requests(data_dir: Path) -> pl.LazyFrame:
    path = data_dir / "all_pull_request.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing AIDev input: {path}")
    raw = pl.scan_parquet(path).select(
        "id",
        "repo_url",
        "repo_id",
        "agent",
        "user_id",
        "state",
        "created_at",
        "closed_at",
        "merged_at",
    )
    return add_time_columns(raw)


def load_repositories(data_dir: Path) -> pl.LazyFrame:
    return (
        pl.scan_parquet(data_dir / "all_repository.parquet")
        .select(
            pl.col("url").alias("repo_url"),
            pl.col("id").alias("repository_id"),
            "language",
            "stars",
            "forks",
            "is_forked",
        )
        .unique("repo_url", keep="first")
    )


def build_repo_summary(base: pl.LazyFrame) -> pl.LazyFrame:
    return base.group_by("repo_url").agg(
        pl.len().alias("repo_prs"),
        pl.col("agent").n_unique().alias("n_agents"),
        pl.col("created_dt").min().alias("repo_first_pr_dt"),
        pl.col("created_dt").max().alias("repo_last_pr_dt"),
        pl.col("merged").mean().alias("repo_merge_rate"),
    )


def build_latest_resolved_transitions(
    base: pl.LazyFrame, repo_summary: pl.LazyFrame
) -> pl.LazyFrame:
    """Map each mature PR to the latest outcome known before it was opened."""
    agent_first = base.group_by("repo_url", "agent").agg(
        pl.col("created_dt").min().alias("agent_first_dt")
    )
    multiagent_onset = (
        agent_first.group_by("repo_url")
        .agg(
            pl.len().alias("observed_agents"),
            pl.col("agent_first_dt").sort().alias("agent_first_dates"),
        )
        .filter(pl.col("observed_agents") >= 2)
        .select(
            "repo_url",
            pl.col("agent_first_dates").list.get(1).alias("multiagent_onset_dt"),
        )
    )
    mature_cutoff = DATASET_CUTOFF - timedelta(days=FOLLOWUP_DAYS)
    current = (
        base.filter(pl.col("created_dt") <= pl.lit(mature_cutoff))
        .with_columns(
            pl.col("created_dt").dt.strftime("%Y-%m").alias("calendar_month"),
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") >= pl.col("created_dt"))
                & (
                    pl.col("merged_dt")
                    <= pl.col("created_dt") + pl.duration(days=FOLLOWUP_DAYS)
                )
            ).alias("merged"),
        )
        .join(multiagent_onset, on="repo_url", how="inner")
        .filter(pl.col("created_dt") >= pl.col("multiagent_onset_dt"))
        .sort(["repo_url", "created_dt", "id"])
    )
    prior = (
        base.filter(valid_resolved_expression())
        .select(
            "repo_url",
            pl.col("id").alias("prior_id"),
            pl.col("agent").alias("prior_agent"),
            pl.col("user_id").alias("prior_user_id"),
            pl.col("closed_dt").alias("prior_closed_dt"),
            pl.col("merged_dt").alias("prior_merged_dt"),
            pl.col("merged").alias("prior_merged"),
        )
        .with_columns(
            pl.len().over(["repo_url", "prior_closed_dt"]).alias("prior_close_tie_n")
        )
        .sort(["repo_url", "prior_closed_dt", "prior_id"])
    )
    return (
        current.join_asof(
            prior,
            left_on="created_dt",
            right_on="prior_closed_dt",
            by="repo_url",
            strategy="backward",
            allow_exact_matches=False,
        )
        .filter(pl.col("prior_id").is_not_null())
        .filter(pl.col("prior_id") != pl.col("id"))
        .filter(pl.col("prior_close_tie_n") == 1)
        .filter(
            pl.col("prior_merged_dt").is_null()
            | (pl.col("prior_merged_dt") < pl.col("created_dt"))
        )
        .sort(["prior_id", "created_dt", "id"])
        .unique("prior_id", keep="first", maintain_order=True)
        .join(repo_summary, on="repo_url", how="inner")
        .with_columns(
            (pl.col("agent") != pl.col("prior_agent")).alias("switched"),
            (pl.col("agent") == pl.col("prior_agent")).alias("same_agent"),
            (
                (pl.col("created_dt") - pl.col("prior_closed_dt"))
                .dt.total_seconds()
                / 3600.0
            ).alias("gap_hours"),
            (
                (pl.col("closed_dt") - pl.col("created_dt"))
                .dt.total_seconds()
                / 3600.0
            ).alias("resolution_hours"),
            (pl.col("user_id") == pl.col("prior_user_id")).alias("same_user"),
        )
    )


def star_bin_expression() -> pl.Expr:
    return (
        pl.when(pl.col("stars").is_null())
        .then(pl.lit("Missing"))
        .when(pl.col("stars") <= 0)
        .then(pl.lit("0"))
        .when(pl.col("stars") < 10)
        .then(pl.lit("1–9"))
        .when(pl.col("stars") < 100)
        .then(pl.lit("10–99"))
        .otherwise(pl.lit("100+"))
        .alias("star_bin")
    )


def profile_data(
    base: pl.LazyFrame,
    repositories: pl.LazyFrame,
    repo_summary: pl.LazyFrame,
) -> dict[str, Any]:
    overview = base.select(
        pl.len().alias("rows"),
        pl.col("id").n_unique().alias("unique_ids"),
        pl.col("repo_url").n_unique().alias("repositories"),
        pl.col("agent").n_unique().alias("agents"),
        pl.col("created_dt").min().alias("first_created"),
        pl.col("created_dt").max().alias("last_created"),
        pl.col("repo_url").null_count().alias("null_repo_url"),
        pl.col("agent").null_count().alias("null_agent"),
        pl.col("created_dt").null_count().alias("null_created"),
        pl.col("closed_dt").null_count().alias("open_or_null_closed"),
        pl.col("merged_dt").null_count().alias("not_merged"),
        ((pl.col("closed_dt") < pl.col("created_dt")).fill_null(False))
        .sum()
        .alias("closed_before_created"),
        ((pl.col("merged_dt") < pl.col("created_dt")).fill_null(False))
        .sum()
        .alias("merged_before_created"),
        (
            (pl.col("merged_dt").is_not_null() & pl.col("closed_dt").is_null())
        )
        .sum()
        .alias("merged_without_closed"),
    ).collect(engine="streaming").row(0, named=True)
    overview["duplicate_ids"] = overview["rows"] - overview["unique_ids"]

    repo_counts = repo_summary.select(
        pl.len().alias("repo_rows"),
        (pl.col("n_agents") >= 2).sum().alias("multiagent_repositories"),
    ).collect(engine="streaming").row(0, named=True)
    join_coverage = (
        repo_summary.select("repo_url")
        .join(repositories.select("repo_url"), on="repo_url", how="left")
        .select(pl.col("repo_url").is_not_null().sum().alias("matched"), pl.len().alias("total"))
        .collect(engine="streaming")
        .row(0, named=True)
    )
    # A left join on the identically named key cannot expose an unmatched key;
    # compute anti-join coverage explicitly.
    unmatched = (
        repo_summary.select("repo_url")
        .join(repositories.select("repo_url"), on="repo_url", how="anti")
        .select(pl.len().alias("unmatched"))
        .collect(engine="streaming")
        .item()
    )
    join_coverage["unmatched"] = unmatched
    join_coverage["matched"] = join_coverage["total"] - unmatched

    agent_counts = (
        base.group_by("agent")
        .agg(pl.len().alias("prs"), pl.col("repo_url").n_unique().alias("repos"))
        .sort("prs", descending=True)
        .collect(engine="streaming")
        .to_dicts()
    )
    return {
        "dataset_revision": DATASET_REVISION,
        "overview": _json_ready(overview),
        "repository_summary": _json_ready(repo_counts),
        "repository_join": _json_ready(join_coverage),
        "agent_counts": _json_ready(agent_counts),
    }


def build_event_study(
    base: pl.LazyFrame, repo_summary: pl.LazyFrame, window: int
) -> tuple[pl.DataFrame, pl.DataFrame]:
    multi_repos = repo_summary.filter(pl.col("n_agents") >= 2).select("repo_url")
    ordered = (
        base.filter(valid_resolved_expression())
        .join(multi_repos, on="repo_url", how="inner")
        .sort(["repo_url", "created_dt", "id"])
        .with_columns(
            (pl.col("id").cum_count().over("repo_url") - 1).alias("repo_index"),
            (
                (pl.col("closed_dt") - pl.col("created_dt"))
                .dt.total_seconds()
                / 3600.0
            ).alias("resolution_hours"),
        )
    )
    agent_first = ordered.group_by("repo_url", "agent").agg(
        pl.col("created_dt").min().alias("agent_first_dt")
    )
    multi_start = (
        agent_first.group_by("repo_url")
        .agg(
            pl.len().alias("n_agent_firsts"),
            pl.col("agent_first_dt").sort().alias("agent_first_dates"),
        )
        .filter(pl.col("n_agent_firsts") >= 2)
        .select(
            "repo_url",
            pl.col("agent_first_dates").list.get(1).alias("multi_start_dt"),
        )
    )
    with_start = ordered.join(multi_start, on="repo_url", how="inner")
    start_index = (
        with_start.filter(pl.col("created_dt") >= pl.col("multi_start_dt"))
        .group_by("repo_url")
        .agg(pl.col("repo_index").min().alias("multi_start_index"))
    )
    event_rows = (
        with_start.join(start_index, on="repo_url", how="inner")
        .with_columns(
            (
                pl.col("repo_index").cast(pl.Int64)
                - pl.col("multi_start_index").cast(pl.Int64)
            ).alias("event_index")
        )
        .filter(pl.col("event_index").is_between(-window, window))
    )
    event_summary = (
        event_rows.group_by("event_index")
        .agg(
            pl.len().alias("n"),
            pl.col("merged").mean().alias("merge_rate"),
            pl.col("resolution_hours").median().alias("median_resolution_hours"),
        )
        .with_columns(
            (
                (
                    pl.col("merge_rate")
                    * (1 - pl.col("merge_rate"))
                    / pl.col("n")
                ).sqrt()
                * 1.96
            ).alias("merge_ci_half_width")
        )
        .sort("event_index")
        .collect(engine="streaming")
    )
    paired = (
        event_rows.filter(pl.col("event_index").is_between(-5, 4))
        .with_columns(
            pl.when(pl.col("event_index") < 0)
            .then(pl.lit("pre"))
            .otherwise(pl.lit("post"))
            .alias("period")
        )
        .group_by("repo_url", "period")
        .agg(
            pl.len().alias("n_prs"),
            pl.col("merged").mean().alias("merge_rate"),
            pl.col("resolution_hours").median().alias("median_resolution_hours"),
        )
        .filter(pl.col("n_prs") >= 3)
        .collect(engine="streaming")
    )
    return event_summary, paired


def summarize_transition_rates(transitions: pl.LazyFrame) -> pl.DataFrame:
    return (
        transitions.group_by("prior_merged", "switched")
        .agg(
            pl.len().alias("n"),
            pl.col("merged").mean().alias("merge_rate"),
        )
        .with_columns(
            (
                (
                    pl.col("merge_rate")
                    * (1 - pl.col("merge_rate"))
                    / pl.col("n")
                ).sqrt()
                * 1.96
            ).alias("ci_half_width"),
            pl.when(pl.col("prior_merged"))
            .then(pl.lit("Prior merged"))
            .otherwise(pl.lit("Prior closed-unmerged"))
            .alias("prior_outcome"),
            pl.when(pl.col("switched"))
            .then(pl.lit("Switched agent"))
            .otherwise(pl.lit("Same agent"))
            .alias("transition_type"),
        )
        .sort("prior_merged", "switched")
        .collect(engine="streaming")
    )


def fit_switching_response(transitions_path: Path) -> pd.DataFrame:
    """Estimate outcome-conditioned switch rates with repository-clustered CIs."""
    data = pl.read_parquet(
        transitions_path,
        columns=["repo_url", "prior_merged", "switched"],
    ).to_pandas()
    rows: list[dict[str, Any]] = []
    for prior_merged, label in [
        (False, "Prior closed-unmerged"),
        (True, "Prior merged"),
    ]:
        subset = data.loc[data["prior_merged"] == prior_merged]
        groups, _ = pd.factorize(subset["repo_url"], sort=False)
        design = np.ones((len(subset), 1))
        result = sm.OLS(subset["switched"].astype(float), design).fit(
            cov_type="cluster",
            cov_kwds={"groups": groups, "use_correction": True},
        )
        estimate = float(result.params.iloc[0])
        std_error = float(result.bse.iloc[0])
        rows.append(
            {
                "prior_merged": prior_merged,
                "prior_outcome": label,
                "n": int(len(subset)),
                "repositories": int(pd.Series(groups).nunique()),
                "switch_rate": estimate,
                "std_error": std_error,
                "ci_low": estimate - 1.96 * std_error,
                "ci_high": estimate + 1.96 * std_error,
            }
        )
    return pd.DataFrame(rows)


def build_transition_matrix(transitions: pl.LazyFrame) -> pl.DataFrame:
    return (
        transitions.group_by("prior_agent", "agent")
        .agg(
            pl.len().alias("n"),
            pl.col("merged").mean().alias("next_merge_rate"),
            (~pl.col("prior_merged")).mean().alias("prior_nonintegration_share"),
        )
        .sort("n", descending=True)
        .collect(engine="streaming")
    )


def build_switching_heterogeneity(transitions: pl.LazyFrame) -> pl.DataFrame:
    rates = (
        transitions.filter(~pl.col("prior_merged"))
        .with_columns(star_bin_expression())
        .group_by("star_bin", "switched")
        .agg(pl.len().alias("n"), pl.col("merged").mean().alias("merge_rate"))
        .collect(engine="streaming")
    )
    rows: list[dict[str, Any]] = []
    for star_bin in ["0", "1–9", "10–99", "100+", "Missing"]:
        subset = rates.filter(pl.col("star_bin") == star_bin)
        values = {r["switched"]: r for r in subset.to_dicts()}
        if False not in values or True not in values:
            continue
        stay, switch = values[False], values[True]
        effect = switch["merge_rate"] - stay["merge_rate"]
        se = math.sqrt(
            switch["merge_rate"] * (1 - switch["merge_rate"]) / switch["n"]
            + stay["merge_rate"] * (1 - stay["merge_rate"]) / stay["n"]
        )
        rows.append(
            {
                "star_bin": star_bin,
                "stay_n": stay["n"],
                "switch_n": switch["n"],
                "stay_merge_rate": stay["merge_rate"],
                "switch_merge_rate": switch["merge_rate"],
                "effect_pp": effect * 100,
                "ci_low_pp": (effect - 1.96 * se) * 100,
                "ci_high_pp": (effect + 1.96 * se) * 100,
            }
        )
    return pl.DataFrame(rows)


def build_current_agent_heterogeneity(transitions: pl.LazyFrame) -> pl.DataFrame:
    rates = (
        transitions.filter(~pl.col("prior_merged"))
        .group_by("agent", "switched")
        .agg(pl.len().alias("n"), pl.col("merged").mean().alias("merge_rate"))
        .collect(engine="streaming")
    )
    rows: list[dict[str, Any]] = []
    for agent in AGENT_ORDER:
        values = {
            row["switched"]: row
            for row in rates.filter(pl.col("agent") == agent).to_dicts()
        }
        if False not in values or True not in values:
            continue
        stay, switch = values[False], values[True]
        rows.append(
            {
                "current_agent": agent,
                "stay_n": stay["n"],
                "switch_n": switch["n"],
                "stay_merge_rate": stay["merge_rate"],
                "switch_merge_rate": switch["merge_rate"],
                "effect_pp": (switch["merge_rate"] - stay["merge_rate"]) * 100,
            }
        )
    return pl.DataFrame(rows)


def build_contributor_overlap(transitions: pl.LazyFrame) -> pl.DataFrame:
    return (
        transitions.filter(~pl.col("prior_merged") & pl.col("switched"))
        .group_by("same_user")
        .agg(pl.len().alias("n"), pl.col("merged").mean().alias("merge_rate_30d"))
        .with_columns((pl.col("n") / pl.col("n").sum()).alias("episode_share"))
        .sort("same_user", descending=True)
        .collect(engine="streaming")
    )


def build_paired_repo_recovery(transitions: pl.LazyFrame) -> pl.DataFrame:
    per_repo = (
        transitions.filter(~pl.col("prior_merged"))
        .group_by("repo_url", "switched")
        .agg(pl.len().alias("n"), pl.col("merged").mean().alias("merge_rate"))
        .collect(engine="streaming")
    )
    pivot = per_repo.pivot(
        on="switched", index="repo_url", values=["n", "merge_rate"]
    )
    required = {"n_false", "n_true", "merge_rate_false", "merge_rate_true"}
    if not required.issubset(set(pivot.columns)):
        return pl.DataFrame()
    return (
        pivot.drop_nulls(list(required))
        .filter((pl.col("n_false") >= 2) & (pl.col("n_true") >= 2))
        .with_columns(
            ((pl.col("merge_rate_true") - pl.col("merge_rate_false")) * 100).alias(
                "within_repo_effect_pp"
            )
        )
    )


def fit_within_repo_lpm(transitions_path: Path) -> pd.DataFrame:
    columns = [
        "repo_url",
        "merged",
        "prior_merged",
        "switched",
        "gap_hours",
        "agent",
        "prior_agent",
        "calendar_month",
    ]
    data = pl.read_parquet(transitions_path, columns=columns).to_pandas()
    data = data.dropna(subset=["merged", "prior_merged", "switched", "repo_url"])
    data["merged"] = data["merged"].astype(float)
    data["prior_merged"] = data["prior_merged"].astype(float)
    data["switched"] = data["switched"].astype(float)
    data["prior_merged_x_switched"] = data["prior_merged"] * data["switched"]
    data["log1p_gap_hours"] = np.log1p(data["gap_hours"].clip(lower=0, upper=24 * 365))

    dummies = pd.get_dummies(
        data[["agent", "prior_agent", "calendar_month"]],
        prefix=["current", "prior", "month"],
        drop_first=True,
        dtype=float,
    )
    feature_names = [
        "prior_merged",
        "switched",
        "prior_merged_x_switched",
        "log1p_gap_hours",
    ]
    design = pd.concat([data[feature_names], dummies], axis=1)
    numeric = pd.concat([data[["merged"]], design], axis=1)
    repo_means = numeric.groupby(data["repo_url"], sort=False).transform("mean")
    y_within = numeric["merged"] - repo_means["merged"]
    x_within = design - repo_means[design.columns]
    keep = x_within.var() > 1e-12
    x_within = x_within.loc[:, keep]
    groups, _ = pd.factorize(data["repo_url"], sort=False)
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
    switch_term = "switched"
    interaction_term = "prior_merged_x_switched"
    if switch_term in result.params.index and interaction_term in result.params.index:
        covariance = result.cov_params()
        estimate = float(result.params[switch_term] + result.params[interaction_term])
        variance = float(
            covariance.loc[switch_term, switch_term]
            + covariance.loc[interaction_term, interaction_term]
            + 2 * covariance.loc[switch_term, interaction_term]
        )
        std_error = math.sqrt(max(variance, 0.0))
        z_score = estimate / std_error if std_error else float("nan")
        table = pd.concat(
            [
                table,
                pd.DataFrame(
                    {
                        "term": ["switched_after_prior_merged"],
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


def configure_plotting() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "axes.titleweight": "bold",
        }
    )


def add_figure_header(fig: plt.Figure, title: str, subtitle: str) -> None:
    """Reserve a clean header band so titles never collide with subtitles."""
    fig.subplots_adjust(top=0.82)
    fig.suptitle(
        title,
        x=0.125,
        y=0.975,
        ha="left",
        va="top",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(0.125, 0.91, subtitle, ha="left", va="top", fontsize=9)


def save_figure(fig: plt.Figure, output_stem: Path) -> None:
    fig.savefig(output_stem.with_suffix(".png"), dpi=240, bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_event_study(event: pd.DataFrame, output_dir: Path) -> None:
    fig, (ax, ax_n) = plt.subplots(
        2,
        1,
        figsize=(8.2, 5.4),
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.08},
    )
    ax.plot(event["event_index"], event["merge_rate"] * 100, color=BLUE, marker="o", lw=1.8)
    ax.fill_between(
        event["event_index"],
        (event["merge_rate"] - event["merge_ci_half_width"]) * 100,
        (event["merge_rate"] + event["merge_ci_half_width"]) * 100,
        color=BLUE,
        alpha=0.16,
    )
    ax.axvline(0, color=INK, linestyle="--", lw=1.1)
    add_figure_header(
        fig,
        "Merge rate around first multi-agent participation",
        "Resolved PRs; event 0 is the first PR from a second distinct agent",
    )
    ax.set_ylabel("Merged (%)")
    ax.grid(axis="x", visible=False)
    ax_n.bar(
        event["event_index"],
        event["n"] / 1000,
        color=GRID,
        edgecolor=INK,
        linewidth=0.35,
    )
    ax_n.set_ylabel("n (k)")
    ax_n.set_xlabel("Resolved-PR position relative to second-agent entry")
    ax_n.set_xticks(sorted(event["event_index"].unique()))
    ax_n.grid(False)
    save_figure(fig, output_dir / "rq1_event_study")


def plot_transition_matrix(matrix: pd.DataFrame, output_dir: Path) -> None:
    pivot = matrix.pivot(index="prior_agent", columns="agent", values="n").fillna(0)
    pivot = pivot.reindex(index=AGENT_ORDER, columns=AGENT_ORDER, fill_value=0)
    row_share = pivot.div(pivot.sum(axis=1).replace(0, np.nan), axis=0) * 100
    fig, ax = plt.subplots(figsize=(8.4, 6.4))
    sns.heatmap(
        row_share,
        cmap=sns.light_palette(BLUE, as_cmap=True),
        annot=True,
        fmt=".1f",
        linewidths=0.6,
        linecolor="white",
        cbar_kws={"label": "Share of next resolved PRs (%)"},
        ax=ax,
    )
    add_figure_header(
        fig,
        "Agent transition matrix",
        "Rows are the latest resolved agent; columns are the next agent",
    )
    ax.set_xlabel("Next agent")
    ax.set_ylabel("Latest resolved agent")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha="right")
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
    save_figure(fig, output_dir / "rq1_transition_matrix")


def plot_switching_response(table: pd.DataFrame, output_dir: Path) -> None:
    order = ["Prior closed-unmerged", "Prior merged"]
    data = table.set_index("prior_outcome").reindex(order).reset_index()
    y = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    ax.errorbar(
        data["switch_rate"] * 100,
        y,
        xerr=[
            (data["switch_rate"] - data["ci_low"]) * 100,
            (data["ci_high"] - data["switch_rate"]) * 100,
        ],
        fmt="o",
        color=ORANGE,
        ecolor=INK,
        capsize=3,
        markersize=7,
    )
    ax.set_yticks(y, data["prior_outcome"])
    ax.invert_yaxis()
    for row_y, (_, row) in enumerate(data.iterrows()):
        ax.annotate(
            f"{row['switch_rate'] * 100:.1f}%  (n={int(row['n']):,})",
            (row["ci_high"] * 100, row_y),
            xytext=(7, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
        )
    add_figure_header(
        fig,
        "Observed agent switching responds to the latest known outcome",
        "Post-onset mature cohort; repository-clustered 95% CIs",
    )
    ax.set_xlabel("Current PR uses a different coding-agent label (%)")
    ax.grid(axis="y", visible=False)
    save_figure(fig, output_dir / "rq2_switching_response")


def plot_spillover(rates: pd.DataFrame, output_dir: Path) -> None:
    outcome_order = ["Prior closed-unmerged", "Prior merged"]
    transition_order = ["Same agent", "Switched agent"]
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    x = np.arange(len(outcome_order))
    width = 0.28
    for offset, label, color, hatch in [
        (-width / 2, transition_order[0], BLUE, ""),
        (width / 2, transition_order[1], ORANGE, "//"),
    ]:
        subset = rates.set_index(["prior_outcome", "transition_type"]).loc[
            [(o, label) for o in outcome_order]
        ]
        values = subset["merge_rate"].to_numpy() * 100
        errors = subset["ci_half_width"].to_numpy() * 100
        bars = ax.bar(
            x + offset,
            values,
            width,
            yerr=errors,
            label=label,
            color=color,
            edgecolor=INK,
            linewidth=0.7,
            hatch=hatch,
            capsize=3,
        )
        ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
    add_figure_header(
        fig,
        "30-day merge rate by prior outcome and agent transition",
        "Latest outcome was known before the current PR opened; PR-level 95% normal CIs",
    )
    ax.set_xticks(x, outcome_order)
    ax.set_ylabel("Next PR merged (%)")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="x", visible=False)
    save_figure(fig, output_dir / "rq3_recovery_crossover")


def plot_heterogeneity(table: pd.DataFrame, output_dir: Path) -> None:
    order = ["0", "1–9", "10–99", "100+"]
    data = table.set_index("star_bin").reindex(order).dropna().reset_index()
    y = np.arange(len(data))
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    ax.errorbar(
        data["effect_pp"],
        y,
        xerr=[data["effect_pp"] - data["ci_low_pp"], data["ci_high_pp"] - data["effect_pp"]],
        fmt="o",
        color=ORANGE,
        ecolor=INK,
        capsize=3,
        markersize=6,
    )
    ax.axvline(0, color=INK, lw=1, linestyle="--")
    ax.set_yticks(y, data["star_bin"])
    for row_y, (_, row) in enumerate(data.iterrows()):
        ax.annotate(
            f"n={int(row['stay_n'] + row['switch_n']):,}",
            (row["ci_high_pp"], row_y),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
        )
    ax.invert_yaxis()
    add_figure_header(
        fig,
        "Switching after a closed-unmerged PR, by repository stars",
        "Raw 30-day merge-rate difference: switched minus same agent; snapshot stars",
    )
    ax.set_xlabel("Merge-rate difference (percentage points)")
    ax.set_ylabel("Repository stars")
    ax.grid(axis="y", visible=False)
    save_figure(fig, output_dir / "rq3_switching_heterogeneity")


def plot_model_coefficients(model: pd.DataFrame, output_dir: Path) -> None:
    focus = model[
        model["term"].isin(["switched", "switched_after_prior_merged"])
    ].copy()
    labels = {
        "switched": "Switch after prior closed-unmerged PR",
        "switched_after_prior_merged": "Switch after prior merged PR",
    }
    focus["label"] = focus["term"].map(labels)
    focus = focus.iloc[::-1]
    y = np.arange(len(focus))
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.errorbar(
        focus["estimate"] * 100,
        y,
        xerr=[(focus["estimate"] - focus["ci_low"]) * 100, (focus["ci_high"] - focus["estimate"]) * 100],
        fmt="o",
        color=BLUE,
        ecolor=INK,
        capsize=3,
    )
    ax.axvline(0, color=INK, lw=1, linestyle="--")
    ax.set_yticks(y, focus["label"])
    add_figure_header(
        fig,
        "Outcome-conditioned switching contrasts",
        "30-day merge; repository-demeaned model with repository-clustered 95% CIs",
    )
    ax.set_xlabel("Conditional association (percentage points)")
    ax.grid(axis="y", visible=False)
    save_figure(fig, output_dir / "rq2_adjusted_switching_contrasts")


def write_summary(
    config: AnalysisConfig,
    quality: dict[str, Any],
    rates: pd.DataFrame,
    heterogeneity: pd.DataFrame,
    model: pd.DataFrame,
    paired: pd.DataFrame,
) -> None:
    def rate(prior: bool, switched: bool) -> tuple[int, float]:
        row = rates[(rates["prior_merged"] == prior) & (rates["switched"] == switched)].iloc[0]
        return int(row["n"]), float(row["merge_rate"])

    fail_stay_n, fail_stay = rate(False, False)
    fail_switch_n, fail_switch = rate(False, True)
    success_stay_n, success_stay = rate(True, False)
    success_switch_n, success_switch = rate(True, True)
    core = model.set_index("term")
    switch_coef = core.loc["switched"] if "switched" in core.index else None
    switch_after_merge = (
        core.loc["switched_after_prior_merged"]
        if "switched_after_prior_merged" in core.index
        else None
    )
    paired_median = float(paired["within_repo_effect_pp"].median()) if not paired.empty else float("nan")
    closed_unmerged_switch_rate = fail_switch_n / (fail_stay_n + fail_switch_n)
    merged_switch_rate = success_switch_n / (success_stay_n + success_switch_n)
    lines = [
        "# Exploratory findings",
        "",
        f"**Dataset revision:** `{DATASET_REVISION}`  ",
        f"**Generated from:** `{config.data_dir}`  ",
        "**Status:** exploratory associations; not causal estimates.",
        "",
        "## Headline signals",
        "",
        f"- Data profile: {quality['overview']['rows']:,} PRs across {quality['overview']['repositories']:,} repositories; {quality['repository_summary']['multiagent_repositories']:,} repositories contain at least two agents.",
        f"- Primary ledger: {fail_stay_n + fail_switch_n + success_stay_n + success_switch_n:,} post-onset episodes, one current PR per prior outcome, each with 30 days of follow-up.",
        f"- Switching follows {closed_unmerged_switch_rate:.1%} of prior closed-unmerged episodes versus {merged_switch_rate:.1%} of prior merged episodes.",
        f"- After a prior closed-unmerged outcome, 30-day merge rates are {fail_stay:.1%} for the same agent (`n={fail_stay_n:,}`) and {fail_switch:.1%} after an observed switch (`n={fail_switch_n:,}`).",
        f"- After a prior merged outcome, 30-day merge rates are {success_stay:.1%} for the same agent (`n={success_stay_n:,}`) and {success_switch:.1%} after an observed switch (`n={success_switch_n:,}`).",
        f"- Among repositories with at least two stay and two switch episodes after closed-unmerged outcomes, the median within-repository switch-minus-stay difference is {paired_median:.2f} percentage points.",
    ]
    if switch_coef is not None and switch_after_merge is not None:
        lines.extend(
            [
                f"- In the exploratory repository-demeaned model, switching is associated with {switch_coef['estimate'] * 100:.2f} pp after a prior closed-unmerged outcome (95% CI {switch_coef['ci_low'] * 100:.2f} to {switch_coef['ci_high'] * 100:.2f}) and {switch_after_merge['estimate'] * 100:.2f} pp after a prior merged outcome (95% CI {switch_after_merge['ci_low'] * 100:.2f} to {switch_after_merge['ci_high'] * 100:.2f}).",
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The behavioral and outcome crossover supports continued investigation of outcome-conditioned switching rather than a generic claim that switching is beneficial. Repository fixed effects and controls reduce—but do not eliminate—selection concerns. The star-stratified analysis is a boundary-condition check, especially because the association is weak in mature repositories.",
            "",
            "## Required caveats",
            "",
            "- Agent changes are observed author-label transitions, not verified maintainer procurement decisions.",
            "- Repository activity, task mix, PR complexity, contributor identity, and automation policy can confound both switching and merge outcomes.",
            "- The full corpus does not provide complete change-size and review-depth features; mechanism analyses require AIDev-pop joins.",
            "- Multiple-testing correction and manual episode validation remain pending.",
            "",
            "## RQ recommendation",
            "",
            "Keep the three-RQ structure. Treat the RQ1 event curve as an endogenous-onset diagnostic, not impact. Promote RQ2–RQ3 only if the signal survives agent-pair, contributor, activity, complexity, and common-support checks.",
        ]
    )
    (config.output_dir / "EXPLORATION_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def run_pipeline(config: AnalysisConfig) -> None:
    tables_dir = config.output_dir / "tables"
    figures_dir = config.output_dir / "figures"
    cache_dir = config.output_dir / "cache"
    for directory in [tables_dir, figures_dir, cache_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    print(f"[1/7] Loading AIDev v5 from {config.data_dir}")
    base = load_pull_requests(config.data_dir)
    repositories = load_repositories(config.data_dir)
    repo_summary = build_repo_summary(base)

    print("[2/7] Running data-quality checks")
    quality = profile_data(base, repositories, repo_summary)
    (tables_dir / "data_quality.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    pl.DataFrame(quality["agent_counts"]).write_csv(tables_dir / "agent_counts.csv")

    print("[3/7] Building latest-resolved transition ledger")
    transitions = (
        build_latest_resolved_transitions(base, repo_summary)
        .join(repositories, on="repo_url", how="left")
        .with_columns(star_bin_expression())
    )
    transitions_path = cache_dir / "latest_resolved_transitions.parquet"
    transitions.collect(engine="streaming").write_parquet(
        transitions_path, compression="zstd", statistics=True
    )
    transitions = pl.scan_parquet(transitions_path)

    print("[4/7] Computing RQ1 event study and transition topology")
    event, paired_periods = build_event_study(base, repo_summary, config.event_window)
    event.write_csv(tables_dir / "rq1_event_study.csv")
    paired_periods.write_csv(tables_dir / "rq1_paired_periods.csv")
    matrix = build_transition_matrix(transitions)
    matrix.write_csv(tables_dir / "rq1_transition_matrix.csv")

    print("[5/7] Computing RQ2/RQ3 conditional rates and heterogeneity")
    switching_response = fit_switching_response(transitions_path)
    switching_response.to_csv(tables_dir / "rq2_switching_response.csv", index=False)
    rates = summarize_transition_rates(transitions)
    rates.write_csv(tables_dir / "rq3_recovery_rates.csv")
    heterogeneity = build_switching_heterogeneity(transitions)
    heterogeneity.write_csv(tables_dir / "rq3_star_heterogeneity.csv")
    agent_heterogeneity = build_current_agent_heterogeneity(transitions)
    agent_heterogeneity.write_csv(tables_dir / "rq3_current_agent_heterogeneity.csv")
    contributor_overlap = build_contributor_overlap(transitions)
    contributor_overlap.write_csv(tables_dir / "rq3_contributor_overlap.csv")
    paired_recovery = build_paired_repo_recovery(transitions)
    if paired_recovery.height:
        paired_recovery.write_parquet(tables_dir / "rq3_paired_repo_recovery.parquet")

    print("[6/7] Fitting exploratory within-repository model")
    model = fit_within_repo_lpm(transitions_path)
    model.to_csv(tables_dir / "rq3_within_repo_lpm.csv", index=False)

    print("[7/7] Rendering figures and summary")
    configure_plotting()
    plot_event_study(event.to_pandas(), figures_dir)
    plot_transition_matrix(matrix.to_pandas(), figures_dir)
    plot_switching_response(switching_response, figures_dir)
    plot_spillover(rates.to_pandas(), figures_dir)
    plot_heterogeneity(heterogeneity.to_pandas(), figures_dir)
    plot_model_coefficients(model, figures_dir)
    write_summary(
        config,
        quality,
        rates.to_pandas(),
        heterogeneity.to_pandas(),
        model,
        paired_recovery.to_pandas() if paired_recovery.height else pd.DataFrame(),
    )
    print(f"Done. See {config.output_dir}")
