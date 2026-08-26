from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATASET_CUTOFF = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
FOLLOWUP_DAYS = 30
EXACT_STREAKS = ["1", "2", "3+"]


@dataclass(frozen=True)
class StreakConfig:
    project_root: Path
    data_dir: Path
    output_dir: Path

    @classmethod
    def from_paths(
        cls, project_root: Path, data_dir: Path | None = None
    ) -> "StreakConfig":
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
        )


def prepare_pull_requests(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Select the light PR schema and parse all timestamps as UTC."""
    return frame.select(
        "id",
        "repo_url",
        "agent",
        "user_id",
        pl.col("created_at")
        .str.to_datetime(TIMESTAMP_FORMAT, time_zone="UTC", strict=False)
        .alias("created_dt"),
        pl.col("closed_at")
        .str.to_datetime(TIMESTAMP_FORMAT, time_zone="UTC", strict=False)
        .alias("closed_dt"),
        pl.col("merged_at")
        .str.to_datetime(TIMESTAMP_FORMAT, time_zone="UTC", strict=False)
        .alias("merged_dt"),
    ).filter(
        pl.col("id").is_not_null()
        & pl.col("repo_url").is_not_null()
        & pl.col("agent").is_not_null()
        & pl.col("created_dt").is_not_null()
    )


def load_pull_requests(data_dir: Path) -> pl.LazyFrame:
    path = data_dir / "all_pull_request.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing AIDev input: {path}")
    return prepare_pull_requests(pl.scan_parquet(path))


def build_resolved_events(base: pl.LazyFrame) -> pl.LazyFrame:
    """Build unambiguous outcomes whose full disposition is temporally known."""
    return (
        base.filter(
            pl.col("closed_dt").is_not_null()
            & (pl.col("closed_dt") >= pl.col("created_dt"))
            & (
                pl.col("merged_dt").is_null()
                | (pl.col("merged_dt") >= pl.col("created_dt"))
            )
        )
        .with_columns(
            pl.when(pl.col("merged_dt").is_not_null())
            .then(pl.max_horizontal("closed_dt", "merged_dt"))
            .otherwise(pl.col("closed_dt"))
            .alias("known_dt"),
            pl.col("merged_dt").is_not_null().alias("was_merged"),
        )
        .with_columns(
            pl.len().over(["repo_url", "known_dt"]).alias("known_time_tie_n")
        )
        .filter(pl.col("known_time_tie_n") == 1)
    )


def build_multiagent_onset(base: pl.LazyFrame) -> pl.LazyFrame:
    agent_first = base.group_by("repo_url", "agent").agg(
        pl.col("created_dt").min().alias("agent_first_dt")
    )
    return (
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


def build_current_candidates(base: pl.LazyFrame) -> pl.LazyFrame:
    mature_cutoff = DATASET_CUTOFF - timedelta(days=FOLLOWUP_DAYS)
    return (
        base.filter(pl.col("created_dt") <= pl.lit(mature_cutoff))
        .join(build_multiagent_onset(base), on="repo_url", how="inner")
        .filter(pl.col("created_dt") >= pl.col("multiagent_onset_dt"))
        .with_columns(
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") >= pl.col("created_dt"))
                & (
                    pl.col("merged_dt")
                    <= pl.col("created_dt") + pl.duration(days=FOLLOWUP_DAYS)
                )
            ).alias("merged_30d"),
            pl.col("created_dt").dt.strftime("%Y-%m").alias("calendar_month"),
        )
    )


def _predecessor_lookup(
    resolved: pl.LazyFrame, prefix: str
) -> pl.LazyFrame:
    return resolved.select(
        "repo_url",
        pl.col("id").alias(f"{prefix}_id"),
        pl.col("agent").alias(f"{prefix}_agent"),
        pl.col("user_id").alias(f"{prefix}_user_id"),
        pl.col("created_dt").alias(f"{prefix}_created_dt"),
        pl.col("known_dt").alias(f"{prefix}_known_dt"),
        pl.col("was_merged").alias(f"{prefix}_merged"),
    )


def attach_predecessor(
    query: pl.LazyFrame,
    resolved: pl.LazyFrame,
    query_time: str,
    prefix: str,
) -> pl.LazyFrame:
    """Attach the latest outcome strictly known before ``query_time``."""
    right_time = f"{prefix}_known_dt"
    return query.sort(["repo_url", query_time]).join_asof(
        _predecessor_lookup(resolved, prefix).sort(["repo_url", right_time]),
        left_on=query_time,
        right_on=right_time,
        by="repo_url",
        strategy="backward",
        allow_exact_matches=False,
        check_sortedness=False,
    )


def classify_streaks(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Classify exact 1/2/3+ streaks and retain conservative censor labels."""
    return (
        frame.filter(~pl.col("p1_merged"))
        .with_columns(
            pl.when(pl.col("p2_id").is_null())
            .then(pl.lit("left-censored-1+"))
            .when(pl.col("p2_merged"))
            .then(pl.lit("1"))
            .when(pl.col("p3_id").is_null())
            .then(pl.lit("left-censored-2+"))
            .when(pl.col("p3_merged"))
            .then(pl.lit("2"))
            .otherwise(pl.lit("3+"))
            .alias("nonintegration_streak"),
            (pl.col("agent") != pl.col("p1_agent")).alias("switched"),
            (pl.col("user_id") == pl.col("p1_user_id")).alias("same_user"),
            (
                (pl.col("created_dt") - pl.col("p1_known_dt"))
                .dt.total_seconds()
                / 3600.0
            ).alias("gap_hours"),
        )
        .sort(["repo_url", "created_dt", "id"])
    )


def build_decision_chains(base: pl.LazyFrame) -> pl.LazyFrame:
    """Construct three-step, outcome-known, non-overlapping decision chains."""
    resolved = build_resolved_events(base)
    current = build_current_candidates(base)

    with_p1 = (
        attach_predecessor(current, resolved, "created_dt", "p1")
        .filter(pl.col("p1_id").is_not_null())
        .filter(pl.col("p1_id") != pl.col("id"))
        .sort(["p1_id", "created_dt", "id"])
        .unique("p1_id", keep="first", maintain_order=True)
    )
    with_p2 = attach_predecessor(with_p1, resolved, "p1_created_dt", "p2")

    # A null left as-of key is invalid in Polars. Look up p3 only where p2
    # exists, then attach those columns back to the complete p2 frame.
    p3_columns = [
        "p3_id",
        "p3_agent",
        "p3_user_id",
        "p3_created_dt",
        "p3_known_dt",
        "p3_merged",
    ]
    p3_found = attach_predecessor(
        with_p2.filter(pl.col("p2_created_dt").is_not_null()),
        resolved,
        "p2_created_dt",
        "p3",
    ).select("id", *p3_columns)
    with_p3 = with_p2.join(p3_found, on="id", how="left")
    return classify_streaks(with_p3)


def validate_temporal_invariants(frame: pl.DataFrame) -> dict[str, int]:
    checks = {
        "p1_not_strictly_before_current": frame.filter(
            ~(pl.col("p1_known_dt") < pl.col("created_dt"))
        ).height,
        "p2_not_strictly_before_p1": frame.filter(
            pl.col("p2_id").is_not_null()
            & ~(pl.col("p2_known_dt") < pl.col("p1_created_dt"))
        ).height,
        "p3_not_strictly_before_p2": frame.filter(
            pl.col("p3_id").is_not_null()
            & ~(pl.col("p3_known_dt") < pl.col("p2_created_dt"))
        ).height,
        "duplicate_current_id": frame.height - frame["id"].n_unique(),
        "duplicate_p1_id": frame.height - frame["p1_id"].n_unique(),
        "pre_onset_current": frame.filter(
            pl.col("created_dt") < pl.col("multiagent_onset_dt")
        ).height,
    }
    if any(checks.values()):
        raise ValueError(f"Decision-chain invariant failure: {checks}")
    return checks


def _cluster_fit(
    data: pd.DataFrame, outcome: str, treatment: str | None = None
) -> tuple[float, float, float, float]:
    y = data[outcome].astype(float)
    if treatment is None:
        design = np.ones((len(data), 1))
    else:
        design = sm.add_constant(data[[treatment]].astype(float), has_constant="add")
    groups, _ = pd.factorize(data["repo_url"], sort=False)
    if len(data) < 2 or pd.Series(groups).nunique() < 2:
        return float("nan"), float("nan"), float("nan"), float("nan")
    result = sm.OLS(y, design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    if treatment is None:
        estimate = float(result.params.iloc[0])
        std_error = float(result.bse.iloc[0])
    else:
        estimate = float(result.params.loc[treatment])
        std_error = float(result.bse.loc[treatment])
    return (
        estimate,
        std_error,
        estimate - 1.96 * std_error,
        estimate + 1.96 * std_error,
    )


def estimate_streak_tables(
    frame: pl.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = frame.select(
        "id",
        "repo_url",
        "nonintegration_streak",
        "switched",
        "same_user",
        "merged_30d",
    ).to_pandas()
    exact = data[data["nonintegration_streak"].isin(EXACT_STREAKS)].copy()

    cell_rows: list[dict[str, object]] = []
    effect_rows: list[dict[str, object]] = []
    contributor_rows: list[dict[str, object]] = []
    for streak in EXACT_STREAKS:
        subset = exact[exact["nonintegration_streak"] == streak]
        switch_est = _cluster_fit(subset, "switched")
        contrast = _cluster_fit(subset, "merged_30d", "switched")
        effect_rows.append(
            {
                "nonintegration_streak": streak,
                "n": len(subset),
                "repositories": subset["repo_url"].nunique(),
                "switch_rate": switch_est[0],
                "switch_rate_se": switch_est[1],
                "switch_rate_ci_low": switch_est[2],
                "switch_rate_ci_high": switch_est[3],
                "switch_merge_contrast_pp": contrast[0] * 100,
                "contrast_se_pp": contrast[1] * 100,
                "contrast_ci_low_pp": contrast[2] * 100,
                "contrast_ci_high_pp": contrast[3] * 100,
            }
        )
        for switched in [False, True]:
            cell = subset[subset["switched"] == switched]
            rate = _cluster_fit(cell, "merged_30d")
            cell_rows.append(
                {
                    "nonintegration_streak": streak,
                    "switched": switched,
                    "n": len(cell),
                    "repositories": cell["repo_url"].nunique(),
                    "merge_rate_30d": rate[0],
                    "std_error": rate[1],
                    "ci_low": rate[2],
                    "ci_high": rate[3],
                }
            )
        for same_user in [True, False]:
            stratum = subset[subset["same_user"] == same_user]
            stay = stratum[~stratum["switched"]]
            switch = stratum[stratum["switched"]]
            stay_rate = _cluster_fit(stay, "merged_30d")
            switch_rate = _cluster_fit(switch, "merged_30d")
            contrast = _cluster_fit(stratum, "merged_30d", "switched")
            contributor_rows.append(
                {
                    "nonintegration_streak": streak,
                    "same_user": same_user,
                    "stay_n": len(stay),
                    "switch_n": len(switch),
                    "repositories": stratum["repo_url"].nunique(),
                    "stay_merge_rate_30d": stay_rate[0],
                    "switch_merge_rate_30d": switch_rate[0],
                    "switch_contrast_pp": contrast[0] * 100,
                    "contrast_se_pp": contrast[1] * 100,
                    "contrast_ci_low_pp": contrast[2] * 100,
                    "contrast_ci_high_pp": contrast[3] * 100,
                }
            )

    censoring = (
        data.groupby("nonintegration_streak", observed=True)
        .agg(n=("id", "size"), repositories=("repo_url", "nunique"))
        .reset_index()
    )
    censoring["share"] = censoring["n"] / censoring["n"].sum()
    return (
        pd.DataFrame(cell_rows),
        pd.DataFrame(effect_rows),
        pd.DataFrame(contributor_rows),
        censoring,
    )


def plot_streak_results(effects: pd.DataFrame, output_stem: Path) -> None:
    ordered = effects.set_index("nonintegration_streak").reindex(EXACT_STREAKS)
    x = np.arange(len(EXACT_STREAKS))
    fig, (ax_switch, ax_recovery) = plt.subplots(1, 2, figsize=(7.2, 3.6))

    ax_switch.errorbar(
        x,
        ordered["switch_rate"] * 100,
        yerr=[
            (ordered["switch_rate"] - ordered["switch_rate_ci_low"]) * 100,
            (ordered["switch_rate_ci_high"] - ordered["switch_rate"]) * 100,
        ],
        marker="o",
        color="#D9822B",
        capsize=3,
        linewidth=1.8,
    )
    ax_switch.set_xticks(x, EXACT_STREAKS)
    ax_switch.set_xlabel("Consecutive closed-unmerged PRs")
    ax_switch.set_ylabel("Next PR changes agent (%)")
    ax_switch.set_title("A  Change becomes less common", loc="left", fontweight="bold")
    for xi, value in zip(x, ordered["switch_rate"] * 100):
        ax_switch.annotate(f"{value:.1f}%", (xi, value), xytext=(0, 7),
                           textcoords="offset points", ha="center", fontsize=8)

    ax_recovery.errorbar(
        x,
        ordered["switch_merge_contrast_pp"],
        yerr=[
            ordered["switch_merge_contrast_pp"] - ordered["contrast_ci_low_pp"],
            ordered["contrast_ci_high_pp"] - ordered["switch_merge_contrast_pp"],
        ],
        marker="o",
        color="#3972B6",
        capsize=3,
        linewidth=1.8,
    )
    ax_recovery.axhline(0, color="#252A34", linestyle="--", linewidth=1)
    ax_recovery.set_xticks(x, EXACT_STREAKS)
    ax_recovery.set_xlabel("Consecutive closed-unmerged PRs")
    ax_recovery.set_ylabel("Change minus stay integration (pp)")
    ax_recovery.set_title("B  Observed gap becomes larger", loc="left", fontweight="bold")
    for xi, value in zip(x, ordered["switch_merge_contrast_pp"]):
        ax_recovery.annotate(f"{value:.1f} pp", (xi, value), xytext=(0, 7),
                             textcoords="offset points", ha="center", fontsize=8)

    fig.subplots_adjust(top=0.88, bottom=0.20, left=0.10, right=0.98, wspace=0.38)
    for axis in (ax_switch, ax_recovery):
        axis.grid(axis="x", visible=False)
    fig.savefig(output_stem.with_suffix(".png"), dpi=240, bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def write_summary(
    output_path: Path,
    frame: pl.DataFrame,
    cells: pd.DataFrame,
    effects: pd.DataFrame,
    censoring: pd.DataFrame,
) -> None:
    lines = [
        "# E1 canonical decision-chain results",
        "",
        "**Design:** latest outcome strictly known before each successor PR opened; "
        "resolution time is `max(closed_at, merged_at)`; tied resolution times are excluded.",
        "",
        f"- Prior-non-integration anchors: {frame.height:,}.",
        f"- Exact, non-left-censored streak episodes: "
        f"{int(censoring[censoring['nonintegration_streak'].isin(EXACT_STREAKS)]['n'].sum()):,}.",
        "- Current PRs are post-multi-agent-onset and have 30 complete follow-up days.",
        "- Confidence intervals are repository-clustered; contrasts are observational, not causal.",
        "",
        "## Exact streak estimates",
        "",
        "| Streak | Stay n | Switch n | Stay merge | Switch merge | Contrast | Switch rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for streak in EXACT_STREAKS:
        c = cells[cells["nonintegration_streak"] == streak].set_index("switched")
        e = effects[effects["nonintegration_streak"] == streak].iloc[0]
        lines.append(
            f"| {streak} | {int(c.loc[False, 'n']):,} | {int(c.loc[True, 'n']):,} | "
            f"{c.loc[False, 'merge_rate_30d']:.1%} | {c.loc[True, 'merge_rate_30d']:.1%} | "
            f"{e['switch_merge_contrast_pp']:.2f} pp "
            f"[{e['contrast_ci_low_pp']:.2f}, {e['contrast_ci_high_pp']:.2f}] | "
            f"{e['switch_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Censoring",
            "",
            "Episodes without enough observed predecessor history are excluded from the "
            "main dose-response analysis and retained in `e1_streak_censoring.csv`.",
            "",
            "## Interpretation boundary",
            "",
            "The right-panel contrasts compare observed switching with observed persistence. "
            "They can motivate common-support and fixed-effect models, but do not identify a "
            "causal effect of switching.",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_streak_analysis(config: StreakConfig) -> None:
    tables_dir = config.output_dir / "tables"
    figures_dir = config.output_dir / "figures"
    cache_dir = config.output_dir / "cache"
    for directory in (tables_dir, figures_dir, cache_dir):
        directory.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Loading PRs from {config.data_dir}")
    base = load_pull_requests(config.data_dir)
    print("[2/4] Building canonical three-predecessor decision chains")
    frame = build_decision_chains(base).collect()
    checks = validate_temporal_invariants(frame)
    frame.write_parquet(
        cache_dir / "streak_decision_chains.parquet",
        compression="zstd",
        statistics=True,
    )

    print("[3/4] Estimating repository-clustered rates and contrasts")
    cells, effects, contributor, censoring = estimate_streak_tables(frame)
    cells.to_csv(tables_dir / "e1_streak_cell_rates.csv", index=False)
    effects.to_csv(tables_dir / "e1_streak_effects.csv", index=False)
    contributor.to_csv(tables_dir / "e1_contributor_continuity.csv", index=False)
    censoring.to_csv(tables_dir / "e1_streak_censoring.csv", index=False)
    pd.DataFrame([checks]).to_csv(
        tables_dir / "e1_temporal_validation.csv", index=False
    )

    print("[4/4] Rendering figure and summary")
    plot_streak_results(effects, figures_dir / "e1_streak_adaptation")
    write_summary(
        config.output_dir / "E1_STREAK_SUMMARY.md",
        frame,
        cells,
        effects,
        censoring,
    )
    print(f"Done. See {config.output_dir / 'E1_STREAK_SUMMARY.md'}")
