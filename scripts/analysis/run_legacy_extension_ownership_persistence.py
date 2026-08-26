"""Measure post-burst ownership persistence after cross-product feedback.

The analysis collapses the first five minutes after a trigger, de-batches review
rows by pull-request review ID, and follows the first two distinct visible
actions through 48 hours.  It is descriptive: account classes and public events
do not identify unaided human labor or causal handoffs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl


ROOT = Path(__file__).resolve().parents[2]
CROSS_DIR = ROOT / "outputs" / "cross_agent_review"
BURST_DIR = ROOT / "outputs" / "burst_topology"
OUTPUT_DIR = ROOT / "outputs" / "ownership_persistence"
BURST_MINUTES = 5
WINDOW_HOURS = 48
SEED = 20260826

ATOMIC_STATES = (
    "user_account",
    "mapped_product",
    "other_bot",
    "branch_movement_untyped",
)
ATOMIC_PRIORITY = {state: index + 1 for index, state in enumerate(ATOMIC_STATES)}
PRIORITY_ATOMIC = {value: key for key, value in ATOMIC_PRIORITY.items()}

OUTCOME_ORDER = {
    "user_account": (
        "same_user",
        "another_user",
        "mapped_product",
        "other_bot",
        "branch_movement_untyped",
        "no_next_action_within_48h",
        "ambiguous_next_owner_tie",
    ),
    "mapped_product": (
        "same_mapped_product",
        "another_mapped_product",
        "user_account",
        "other_bot",
        "branch_movement_untyped",
        "no_next_action_within_48h",
        "ambiguous_next_owner_tie",
    ),
}

KEY_METRICS = (
    "exact_owner_persistence",
    "layer_persistence",
    "cross_layer_handoff",
    "no_next_action",
)
VISIBLE_ACTION_METRICS = KEY_METRICS[:3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Post-burst exact-owner persistence within 48 hours."
    )
    parser.add_argument("--cross-dir", type=Path, default=CROSS_DIR)
    parser.add_argument("--burst-dir", type=Path, default=BURST_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--bootstrap-draws", type=int, default=5_000)
    return parser.parse_args()


def classify_and_key_events(events: pl.DataFrame) -> pl.DataFrame:
    """Assign an atomic owner and a logical action key to each event row."""
    user_type = pl.col("response_user_type").fill_null("").str.to_lowercase()
    login = pl.col("response_user").fill_null("").str.strip_chars().str.to_lowercase()
    classified = (
        events.with_columns(login.alias("response_login"))
        .with_columns(
            pl.when(user_type == "user")
            .then(pl.lit("user_account"))
            .when(pl.col("response_agent").is_not_null())
            .then(pl.lit("mapped_product"))
            .when(user_type == "bot")
            .then(pl.lit("other_bot"))
            .otherwise(pl.lit("branch_movement_untyped"))
            .alias("atomic_state")
        )
        .with_columns(
            pl.when(pl.col("atomic_state") == "user_account")
            .then(pl.concat_str([pl.lit("user:"), pl.col("response_login")]))
            .when(pl.col("atomic_state") == "mapped_product")
            .then(
                pl.concat_str(
                    [pl.lit("product:"), pl.col("response_agent")]
                )
            )
            .when(pl.col("atomic_state") == "other_bot")
            .then(pl.concat_str([pl.lit("bot:"), pl.col("response_login")]))
            .otherwise(pl.lit("movement"))
            .alias("owner_token"),
            pl.col("atomic_state")
            .replace_strict(ATOMIC_PRIORITY, return_dtype=pl.Int8)
            .alias("state_priority"),
        )
    )
    return classified.with_columns(
        pl.when(pl.col("response_review_id").is_not_null())
        .then(
            pl.concat_str(
                [
                    pl.lit("review:"),
                    pl.col("response_review_id").cast(pl.String),
                ]
            )
        )
        .when(pl.col("response_event_id").is_not_null())
        .then(
            pl.concat_str(
                [
                    pl.col("response_source"),
                    pl.lit(":"),
                    pl.col("response_event_id").cast(pl.String),
                ]
            )
        )
        .otherwise(
            pl.concat_str(
                [
                    pl.lit("movement:"),
                    pl.col("response_dt").cast(pl.String),
                    pl.lit(":"),
                    pl.col("response_login"),
                ]
            )
        )
        .alias("action_key")
    )


def build_action_records(events: pl.DataFrame) -> pl.DataFrame:
    """Collapse all rows belonging to one logical review/comment/push action."""
    return (
        events.group_by("pr_id", "action_key")
        .agg(
            pl.col("response_dt").min().alias("action_dt"),
            pl.col("response_dt").max().alias("action_last_dt"),
            pl.col("trigger_dt").first(),
            pl.len().alias("event_rows_in_action"),
            pl.col("response_dt").n_unique().alias("timestamps_in_action"),
            pl.col("owner_token").n_unique().alias("owners_in_action"),
            pl.col("atomic_state").n_unique().alias("states_in_action"),
            pl.col("state_priority").min().alias("action_state_priority"),
            pl.col("owner_token")
            .sort_by("response_dt")
            .first()
            .alias("action_owner_token"),
            pl.col("response_login")
            .sort_by("response_dt")
            .first()
            .alias("action_user_login"),
            pl.col("response_agent")
            .sort_by("response_dt")
            .drop_nulls()
            .first()
            .alias("action_product"),
            pl.col("response_source")
            .unique()
            .sort()
            .str.join("|")
            .alias("action_sources"),
        )
        .with_columns(
            pl.col("action_state_priority")
            .replace_strict(PRIORITY_ATOMIC, return_dtype=pl.String)
            .alias("action_state"),
            (
                (pl.col("owners_in_action") > 1)
                | (pl.col("states_in_action") > 1)
            ).alias("action_owner_ambiguous"),
            (
                (pl.col("action_dt") - pl.col("trigger_dt")).dt.total_seconds()
                / 3600.0
            ).alias("action_hours_after_trigger"),
        )
    )


def build_timestamp_states(actions: pl.DataFrame) -> pl.DataFrame:
    """Collapse actions at the same second into one tie-aware visible state."""
    post_burst = actions.filter(
        (pl.col("action_hours_after_trigger") > BURST_MINUTES / 60.0)
        & (pl.col("action_hours_after_trigger") <= WINDOW_HOURS)
    )
    return (
        post_burst.group_by("pr_id", "action_dt")
        .agg(
            pl.len().alias("actions_at_timestamp"),
            pl.col("event_rows_in_action").sum().alias("event_rows_at_timestamp"),
            pl.col("action_owner_token").n_unique().alias("owners_at_timestamp"),
            pl.col("action_state").n_unique().alias("states_at_timestamp"),
            pl.col("action_owner_ambiguous").any().alias(
                "contains_ambiguous_action"
            ),
            pl.col("action_state_priority").min().alias("timestamp_state_priority"),
            pl.col("action_owner_token").first().alias("timestamp_owner_token"),
            pl.col("action_user_login").first().alias("timestamp_user_login"),
            pl.col("action_product").first().alias(
                "timestamp_product"
            ),
            pl.col("action_sources")
            .unique()
            .sort()
            .str.join("|")
            .alias("timestamp_sources"),
        )
        .with_columns(
            pl.col("timestamp_state_priority")
            .replace_strict(PRIORITY_ATOMIC, return_dtype=pl.String)
            .alias("timestamp_state"),
            (
                pl.col("contains_ambiguous_action")
                | (pl.col("owners_at_timestamp") > 1)
                | (pl.col("states_at_timestamp") > 1)
            ).alias("timestamp_owner_ambiguous"),
        )
        .sort(["pr_id", "action_dt"])
    )


def build_sequences(
    chains: pl.DataFrame, timestamp_states: pl.DataFrame
) -> pl.DataFrame:
    """Return one first/next timestamp sequence for every cross-feedback PR."""
    first = timestamp_states.unique("pr_id", keep="first", maintain_order=True)
    later = (
        timestamp_states.join(
            first.select(
                "pr_id", pl.col("action_dt").alias("first_action_dt")
            ),
            on="pr_id",
            how="inner",
        )
        .filter(pl.col("action_dt") > pl.col("first_action_dt"))
        .sort(["pr_id", "action_dt"])
        .unique("pr_id", keep="first", maintain_order=True)
    )
    first = first.rename(
        {
            column: f"first_{column}"
            for column in first.columns
            if column != "pr_id"
        }
    )
    later = later.drop("first_action_dt")
    later = later.rename(
        {
            column: f"next_{column}"
            for column in later.columns
            if column != "pr_id"
        }
    )
    base = chains.select(
        "pr_id",
        "repo_id",
        "repo_url",
        "author_user",
        "author_agent",
        "trigger_reviewer_agent",
        "trigger_source",
        "trigger_dt",
        "closed_dt",
    ).with_columns(
        (
            pl.col("author_agent")
            + pl.lit(" -> ")
            + pl.col("trigger_reviewer_agent")
        ).alias("product_pair"),
        (pl.col("trigger_dt") + pl.duration(hours=WINDOW_HOURS)).alias(
            "window_end_dt"
        ),
    )
    sequence = (
        base.join(first, on="pr_id", how="left")
        .join(later, on="pr_id", how="left")
        .with_columns(
            pl.col("first_timestamp_owner_ambiguous").fill_null(False),
            pl.col("next_timestamp_owner_ambiguous").fill_null(False),
            pl.col("first_timestamp_state").fill_null(
                "no_action_within_48h"
            ),
        )
        .with_columns(
            pl.when(pl.col("first_timestamp_owner_ambiguous"))
            .then(pl.lit("ambiguous_first_owner_tie"))
            .otherwise(pl.col("first_timestamp_state"))
            .alias("first_owner_state"),
            pl.when(pl.col("next_action_dt").is_null())
            .then(pl.lit("no_next_action_within_48h"))
            .when(pl.col("next_timestamp_owner_ambiguous"))
            .then(pl.lit("ambiguous_next_owner_tie"))
            .otherwise(pl.col("next_timestamp_state"))
            .alias("next_owner_state"),
        )
        .with_columns(
            pl.when(pl.col("first_owner_state") == "user_account")
            .then(
                pl.when(
                    pl.col("next_owner_state")
                    == "no_next_action_within_48h"
                )
                .then(pl.lit("no_next_action_within_48h"))
                .when(
                    pl.col("next_owner_state")
                    == "ambiguous_next_owner_tie"
                )
                .then(pl.lit("ambiguous_next_owner_tie"))
                .when(
                    (pl.col("next_owner_state") == "user_account")
                    & (
                        pl.col("next_timestamp_owner_token")
                        == pl.col("first_timestamp_owner_token")
                    )
                )
                .then(pl.lit("same_user"))
                .when(pl.col("next_owner_state") == "user_account")
                .then(pl.lit("another_user"))
                .when(pl.col("next_owner_state") == "mapped_product")
                .then(pl.lit("mapped_product"))
                .when(pl.col("next_owner_state") == "other_bot")
                .then(pl.lit("other_bot"))
                .otherwise(pl.lit("branch_movement_untyped"))
            )
            .when(pl.col("first_owner_state") == "mapped_product")
            .then(
                pl.when(
                    pl.col("next_owner_state")
                    == "no_next_action_within_48h"
                )
                .then(pl.lit("no_next_action_within_48h"))
                .when(
                    pl.col("next_owner_state")
                    == "ambiguous_next_owner_tie"
                )
                .then(pl.lit("ambiguous_next_owner_tie"))
                .when(
                    (pl.col("next_owner_state") == "mapped_product")
                    & (
                        pl.col("next_timestamp_owner_token")
                        == pl.col("first_timestamp_owner_token")
                    )
                )
                .then(pl.lit("same_mapped_product"))
                .when(pl.col("next_owner_state") == "mapped_product")
                .then(pl.lit("another_mapped_product"))
                .when(pl.col("next_owner_state") == "user_account")
                .then(pl.lit("user_account"))
                .when(pl.col("next_owner_state") == "other_bot")
                .then(pl.lit("other_bot"))
                .otherwise(pl.lit("branch_movement_untyped"))
            )
            .otherwise(pl.lit(None, dtype=pl.String))
            .alias("transition_outcome"),
            (
                (pl.col("next_action_dt") - pl.col("first_action_dt"))
                .dt.total_seconds()
                / 60.0
            ).alias("minutes_first_to_next"),
            (
                (pl.col("first_action_dt") - pl.col("trigger_dt"))
                .dt.total_seconds()
                / 60.0
            ).alias("minutes_trigger_to_first"),
        )
        .with_columns(
            pl.when(pl.col("next_owner_state") != "mapped_product")
            .then(pl.lit(None, dtype=pl.String))
            .when(pl.col("next_timestamp_product") == pl.col("author_agent"))
            .then(pl.lit("authoring_product"))
            .when(
                pl.col("next_timestamp_product")
                == pl.col("trigger_reviewer_agent")
            )
            .then(pl.lit("triggering_reviewer_product"))
            .otherwise(pl.lit("other_mapped_product"))
            .alias("next_mapped_product_role"),
            pl.when(
                (pl.col("transition_outcome") == "no_next_action_within_48h")
                & pl.col("closed_dt").is_not_null()
                & (pl.col("closed_dt") >= pl.col("first_action_dt"))
                & (pl.col("closed_dt") <= pl.col("window_end_dt"))
            )
            .then(pl.lit("closed_before_48h_without_next_action"))
            .when(
                pl.col("transition_outcome") == "no_next_action_within_48h"
            )
            .then(pl.lit("open_at_48h_without_next_action"))
            .otherwise(pl.lit("next_action_observed"))
            .alias("next_observation_status"),
        )
    )
    return sequence.sort("pr_id")


def repository_cluster_share_ci(
    frame: pd.DataFrame,
    category_column: str,
    categories: tuple[str, ...],
    draws: int,
    seed: int,
) -> dict[str, tuple[float, float]]:
    counts = pd.crosstab(frame["repo_id"], frame[category_column]).reindex(
        columns=categories, fill_value=0
    )
    matrix = counts.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    samples: list[np.ndarray] = []
    completed = 0
    while completed < draws:
        current = min(250, draws - completed)
        sampled = rng.integers(
            0, len(matrix), size=(current, len(matrix)), dtype=np.int32
        )
        totals = matrix[sampled].sum(axis=1)
        samples.append(totals / totals.sum(axis=1, keepdims=True))
        completed += current
    estimates = np.vstack(samples)
    return {
        category: tuple(
            float(value)
            for value in np.quantile(estimates[:, index], [0.025, 0.975])
        )
        for index, category in enumerate(categories)
    }


def summarize_transitions(
    primary: pd.DataFrame, draws: int
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_index, (start_group, outcomes) in enumerate(OUTCOME_ORDER.items()):
        frame = primary[primary["first_owner_state"] == start_group].copy()
        counts = frame["transition_outcome"].value_counts().reindex(
            outcomes, fill_value=0
        )
        tie_n = int(counts["ambiguous_next_owner_tie"])
        classifiable_n = len(frame) - tie_n
        ci = repository_cluster_share_ci(
            frame,
            "transition_outcome",
            outcomes,
            draws,
            SEED + group_index,
        )
        for outcome in outcomes:
            cell = frame[frame["transition_outcome"] == outcome]
            rows.append(
                {
                    "first_owner_state": start_group,
                    "transition_outcome": outcome,
                    "prs": int(counts[outcome]),
                    "start_group_prs": len(frame),
                    "classifiable_prs_excluding_next_ties": classifiable_n,
                    "share_all_start_prs": counts[outcome] / len(frame),
                    "share_excluding_next_ties": (
                        counts[outcome] / classifiable_n
                        if outcome != "ambiguous_next_owner_tie"
                        and classifiable_n
                        else np.nan
                    ),
                    "repository_cluster_ci_low": ci[outcome][0],
                    "repository_cluster_ci_high": ci[outcome][1],
                    "repositories": int(cell["repo_id"].nunique()),
                    "median_minutes_first_to_next": (
                        cell["minutes_first_to_next"].median()
                        if outcome
                        not in {
                            "no_next_action_within_48h",
                            "ambiguous_next_owner_tie",
                        }
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def add_metric_flags(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    user = out["first_owner_state"] == "user_account"
    mapped = out["first_owner_state"] == "mapped_product"
    outcome = out["transition_outcome"]
    out["exact_owner_persistence"] = np.where(
        user,
        outcome == "same_user",
        outcome == "same_mapped_product",
    ).astype(float)
    out["layer_persistence"] = np.where(
        user,
        outcome.isin(["same_user", "another_user"]),
        outcome.isin(["same_mapped_product", "another_mapped_product"]),
    ).astype(float)
    out["cross_layer_handoff"] = np.where(
        user, outcome == "mapped_product", outcome == "user_account"
    ).astype(float)
    out["no_next_action"] = (
        outcome == "no_next_action_within_48h"
    ).astype(float)
    return out


def repository_cluster_metric_ci(
    frame: pd.DataFrame, metric: str, draws: int, seed: int
) -> tuple[float, float]:
    grouped = frame.groupby("repo_id", sort=False)[metric].agg(["sum", "size"])
    numerators = grouped["sum"].to_numpy(dtype=float)
    denominators = grouped["size"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    samples: list[np.ndarray] = []
    completed = 0
    while completed < draws:
        current = min(250, draws - completed)
        selected = rng.integers(
            0, len(grouped), size=(current, len(grouped)), dtype=np.int32
        )
        samples.append(
            numerators[selected].sum(axis=1)
            / denominators[selected].sum(axis=1)
        )
        completed += current
    low, high = np.quantile(np.concatenate(samples), [0.025, 0.975])
    return float(low), float(high)


def summarize_key_metrics(
    metric_frame: pd.DataFrame,
    draws: int,
    metrics: tuple[str, ...] = KEY_METRICS,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_index, start_group in enumerate(OUTCOME_ORDER):
        frame = metric_frame[
            metric_frame["first_owner_state"] == start_group
        ]
        for metric_index, metric in enumerate(metrics):
            low, high = repository_cluster_metric_ci(
                frame,
                metric,
                draws,
                SEED + 20 + 10 * group_index + metric_index,
            )
            rows.append(
                {
                    "first_owner_state": start_group,
                    "metric": metric,
                    "prs": len(frame),
                    "repositories": int(frame["repo_id"].nunique()),
                    "estimate": float(frame[metric].mean()),
                    "repository_cluster_ci_low": low,
                    "repository_cluster_ci_high": high,
                }
            )
    return pd.DataFrame(rows)


def repository_cluster_contrast_ci(
    frame: pd.DataFrame, metric: str, draws: int, seed: int
) -> tuple[float, float]:
    groups = tuple(OUTCOME_ORDER)
    repositories = frame["repo_id"].drop_duplicates().to_numpy()
    aggregated = (
        frame.groupby(["repo_id", "first_owner_state"], sort=False)[metric]
        .agg(["sum", "size"])
        .reset_index()
    )
    numerator = {
        group: aggregated[aggregated["first_owner_state"] == group]
        .set_index("repo_id")["sum"]
        .reindex(repositories, fill_value=0)
        .to_numpy(dtype=float)
        for group in groups
    }
    denominator = {
        group: aggregated[aggregated["first_owner_state"] == group]
        .set_index("repo_id")["size"]
        .reindex(repositories, fill_value=0)
        .to_numpy(dtype=float)
        for group in groups
    }
    rng = np.random.default_rng(seed)
    samples: list[np.ndarray] = []
    completed = 0
    while completed < draws:
        current = min(250, draws - completed)
        selected = rng.integers(
            0,
            len(repositories),
            size=(current, len(repositories)),
            dtype=np.int32,
        )
        user_rate = numerator[groups[0]][selected].sum(axis=1) / denominator[
            groups[0]
        ][selected].sum(axis=1)
        mapped_rate = numerator[groups[1]][selected].sum(axis=1) / denominator[
            groups[1]
        ][selected].sum(axis=1)
        samples.append(user_rate - mapped_rate)
        completed += current
    low, high = np.quantile(np.concatenate(samples), [0.025, 0.975])
    return float(low), float(high)


def summarize_contrasts(
    metric_frame: pd.DataFrame,
    draws: int,
    metrics: tuple[str, ...] = KEY_METRICS,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for metric_index, metric in enumerate(metrics):
        user = metric_frame[
            metric_frame["first_owner_state"] == "user_account"
        ][metric].mean()
        mapped = metric_frame[
            metric_frame["first_owner_state"] == "mapped_product"
        ][metric].mean()
        low, high = repository_cluster_contrast_ci(
            metric_frame, metric, draws, SEED + 100 + metric_index
        )
        rows.append(
            {
                "metric": metric,
                "user_first_estimate": user,
                "mapped_first_estimate": mapped,
                "user_minus_mapped": user - mapped,
                "repository_cluster_ci_low": low,
                "repository_cluster_ci_high": high,
            }
        )
    return pd.DataFrame(rows)


def concentration_summary(primary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for start_group in OUTCOME_ORDER:
        frame = primary[primary["first_owner_state"] == start_group]
        for unit, column in [
            ("repository", "repo_id"),
            ("product_pair", "product_pair"),
            ("first_exact_owner", "first_timestamp_owner_token"),
        ]:
            counts = frame[column].value_counts(dropna=False)
            shares = counts / counts.sum()
            rows.append(
                {
                    "first_owner_state": start_group,
                    "unit": unit,
                    "units": len(counts),
                    "prs": len(frame),
                    "largest_unit_prs": int(counts.iloc[0]),
                    "largest_unit_share": float(shares.iloc[0]),
                    "top_10_unit_share": float(shares.head(10).sum()),
                    "hhi": float((shares**2).sum()),
                }
            )
    return pd.DataFrame(rows)


def leave_one_product_pair_out(
    metric_frame: pd.DataFrame,
    metrics: tuple[str, ...] = KEY_METRICS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    full: dict[tuple[str, str], float] = {}
    for start_group in OUTCOME_ORDER:
        cell = metric_frame[
            metric_frame["first_owner_state"] == start_group
        ]
        for metric in metrics:
            full[(start_group, metric)] = float(cell[metric].mean())
    rows: list[dict[str, Any]] = []
    for product_pair in sorted(metric_frame["product_pair"].unique()):
        kept = metric_frame[metric_frame["product_pair"] != product_pair]
        for start_group in OUTCOME_ORDER:
            cell = kept[kept["first_owner_state"] == start_group]
            for metric in metrics:
                estimate = float(cell[metric].mean())
                rows.append(
                    {
                        "omitted_product_pair": product_pair,
                        "first_owner_state": start_group,
                        "metric": metric,
                        "prs": len(cell),
                        "repositories": int(cell["repo_id"].nunique()),
                        "estimate": estimate,
                        "full_estimate": full[(start_group, metric)],
                        "change_from_full": estimate
                        - full[(start_group, metric)],
                    }
                )
        for metric in metrics:
            user = kept[kept["first_owner_state"] == "user_account"][
                metric
            ].mean()
            mapped = kept[kept["first_owner_state"] == "mapped_product"][
                metric
            ].mean()
            full_difference = (
                full[("user_account", metric)]
                - full[("mapped_product", metric)]
            )
            rows.append(
                {
                    "omitted_product_pair": product_pair,
                    "first_owner_state": "user_minus_mapped",
                    "metric": metric,
                    "prs": len(kept),
                    "repositories": int(kept["repo_id"].nunique()),
                    "estimate": user - mapped,
                    "full_estimate": full_difference,
                    "change_from_full": user - mapped - full_difference,
                }
            )
    detail = pd.DataFrame(rows)
    summary = (
        detail.groupby(["first_owner_state", "metric"], as_index=False)
        .agg(
            full_estimate=("full_estimate", "first"),
            leave_one_pair_min=("estimate", "min"),
            leave_one_pair_max=("estimate", "max"),
            leave_one_pair_max_abs_change=(
                "change_from_full",
                lambda values: values.abs().max(),
            ),
            product_pairs=("omitted_product_pair", "nunique"),
        )
    )
    return detail, summary


def build_quality_checks(
    raw_events: pl.DataFrame,
    events: pl.DataFrame,
    actions: pl.DataFrame,
    timestamp_states: pl.DataFrame,
    sequences: pl.DataFrame,
    burst_states: pl.DataFrame,
) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []

    def add(
        check: str,
        passed: bool,
        value: Any,
        expected: str,
        severity: str,
        note: str,
    ) -> None:
        checks.append(
            {
                "check": check,
                "status": "PASS" if passed else "FAIL",
                "value": value,
                "expected": expected,
                "severity": severity,
                "note": note,
            }
        )

    duplicate_surplus = raw_events.height - events.height
    add(
        "exact_duplicate_event_rows_removed",
        True,
        duplicate_surplus,
        "reported; exact-deduplicated view used",
        "low",
        "Duplicates are not allowed to create persistence.",
    )
    review_rows = events.filter(pl.col("response_review_id").is_not_null()).height
    review_actions = actions.filter(
        pl.col("action_key").str.starts_with("review:")
    ).height
    add(
        "review_rows_debatched",
        review_actions <= review_rows,
        f"{review_rows} rows -> {review_actions} actions",
        "one action per PR-review ID",
        "high",
        "Prevents a reply and its submitted review from becoming two owners/actions.",
    )
    ambiguous_actions = actions.filter(pl.col("action_owner_ambiguous")).height
    add(
        "ambiguous_review_or_action_batches_flagged",
        True,
        ambiguous_actions,
        "reported and propagated to timestamp ties",
        "medium",
        "No arbitrary owner is used for an ambiguous logical action.",
    )
    add(
        "one_sequence_row_per_pr",
        sequences["pr_id"].n_unique() == sequences.height == 8608,
        sequences.height,
        "8,608 unique PR rows",
        "critical",
        "Locks the denominator to the complete cross-feedback cohort.",
    )
    first_order_fail = sequences.filter(
        pl.col("first_action_dt").is_not_null()
        & (pl.col("minutes_trigger_to_first") <= BURST_MINUTES)
    ).height
    add(
        "first_action_strictly_after_burst",
        first_order_fail == 0,
        first_order_fail,
        "0 first actions at or before five minutes",
        "critical",
        "Protects the burst boundary.",
    )
    first_window_fail = sequences.filter(
        pl.col("first_action_dt").is_not_null()
        & (pl.col("first_action_dt") > pl.col("window_end_dt"))
    ).height
    add(
        "first_action_within_48h",
        first_window_fail == 0,
        first_window_fail,
        "0 actions after landmark",
        "critical",
        "Prevents future-window leakage.",
    )
    next_order_fail = sequences.filter(
        pl.col("next_action_dt").is_not_null()
        & (pl.col("next_action_dt") <= pl.col("first_action_dt"))
    ).height
    add(
        "next_action_strictly_later",
        next_order_fail == 0,
        next_order_fail,
        "0 non-positive action gaps",
        "critical",
        "Same-timestamp rows are ties, not transitions.",
    )
    next_window_fail = sequences.filter(
        pl.col("next_action_dt").is_not_null()
        & (pl.col("next_action_dt") > pl.col("window_end_dt"))
    ).height
    add(
        "next_action_within_48h",
        next_window_fail == 0,
        next_window_fail,
        "0 actions after landmark",
        "critical",
        "Locks the outcome window before any later-merge analysis.",
    )
    primary = sequences.filter(
        pl.col("first_owner_state").is_in(list(OUTCOME_ORDER))
    )
    ambiguous_first = sequences.filter(
        pl.col("first_owner_state") == "ambiguous_first_owner_tie"
    ).height
    ambiguous_next = primary.filter(
        pl.col("transition_outcome") == "ambiguous_next_owner_tie"
    ).height
    add(
        "exact_owner_ties_reported",
        True,
        f"first={ambiguous_first}, next={ambiguous_next}",
        "ties retained separately",
        "medium",
        "Exact account/product persistence is not inferred across mixed-owner ties.",
    )

    reference = burst_states.filter(
        (pl.col("burst_threshold_minutes") == BURST_MINUTES)
        & pl.col("first_post_burst_dt").is_not_null()
        & (pl.col("first_hours_after_trigger") <= WINDOW_HOURS)
    ).select(
        "pr_id",
        pl.col("first_post_burst_state").alias("reference_first_state"),
    )
    compatibility = reference.join(
        sequences.select(
            "pr_id",
            pl.col("first_timestamp_state").alias("debatched_first_state"),
        ),
        on="pr_id",
        how="inner",
    )
    state_mismatches = compatibility.filter(
        pl.col("reference_first_state") != pl.col("debatched_first_state")
    ).height
    add(
        "debatched_first_state_vs_raw_burst_reference",
        True,
        state_mismatches,
        "reported; differences explain review de-batching impact",
        "medium",
        "The extension de-batches cross-source rows sharing a review ID.",
    )
    add(
        "timestamp_state_grain_unique",
        timestamp_states.select(
            pl.struct(["pr_id", "action_dt"]).is_duplicated().sum()
        ).item()
        == 0,
        timestamp_states.height,
        "unique PR-timestamp rows",
        "critical",
        "Protects exact ordering.",
    )
    return pd.DataFrame(checks)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    chains = pl.read_parquet(
        args.cross_dir / "cross_feedback_response_chains.parquet"
    )
    raw_events = pl.read_parquet(
        args.cross_dir / "cross_feedback_response_events.parquet"
    )
    burst_states = pl.read_parquet(
        args.burst_dir / "burst_collapsed_first_state.parquet"
    )
    events = raw_events.unique(maintain_order=True)
    classified = classify_and_key_events(
        events.filter(
            pl.col("response_dt").is_not_null()
            & (pl.col("hours_after_trigger") > 0)
            & (pl.col("hours_after_trigger") <= WINDOW_HOURS)
        )
    )
    actions = build_action_records(classified)
    timestamp_states = build_timestamp_states(actions)
    sequences = build_sequences(chains, timestamp_states)
    primary = sequences.filter(
        pl.col("first_owner_state").is_in(list(OUTCOME_ORDER))
    )
    primary_pd = primary.to_pandas()
    transition_summary = summarize_transitions(primary_pd, args.bootstrap_draws)
    metric_frame = add_metric_flags(
        primary_pd[
            primary_pd["transition_outcome"]
            != "ambiguous_next_owner_tie"
        ].copy()
    )
    key_metrics = summarize_key_metrics(metric_frame, args.bootstrap_draws)
    contrasts = summarize_contrasts(metric_frame, args.bootstrap_draws)
    visible_action_frame = metric_frame[
        metric_frame["no_next_action"] == 0
    ].copy()
    conditional_metrics = summarize_key_metrics(
        visible_action_frame,
        args.bootstrap_draws,
        VISIBLE_ACTION_METRICS,
    )
    conditional_contrasts = summarize_contrasts(
        visible_action_frame,
        args.bootstrap_draws,
        VISIBLE_ACTION_METRICS,
    )
    concentration = concentration_summary(primary_pd)
    loo, loo_summary = leave_one_product_pair_out(metric_frame)
    conditional_loo, conditional_loo_summary = leave_one_product_pair_out(
        visible_action_frame, VISIBLE_ACTION_METRICS
    )
    no_next_breakdown = (
        primary_pd.groupby(
            ["first_owner_state", "next_observation_status"], as_index=False
        )
        .agg(prs=("pr_id", "size"), repositories=("repo_id", "nunique"))
    )
    no_next_breakdown["share_within_start_group"] = no_next_breakdown[
        "prs"
    ] / no_next_breakdown.groupby("first_owner_state")["prs"].transform("sum")
    mapped_return_roles = (
        primary_pd[primary_pd["next_owner_state"] == "mapped_product"]
        .groupby(
            ["first_owner_state", "next_mapped_product_role"],
            as_index=False,
        )
        .agg(prs=("pr_id", "size"), repositories=("repo_id", "nunique"))
    )
    mapped_return_roles["share_within_mapped_next"] = mapped_return_roles[
        "prs"
    ] / mapped_return_roles.groupby("first_owner_state")["prs"].transform(
        "sum"
    )
    checks = build_quality_checks(
        raw_events,
        events,
        actions,
        timestamp_states,
        sequences,
        burst_states,
    )

    sequences.write_parquet(
        args.output_dir / "postburst_ownership_sequences.parquet",
        compression="zstd",
    )
    primary.write_parquet(
        args.output_dir / "primary_ownership_persistence.parquet",
        compression="zstd",
    )
    transition_summary.to_csv(
        args.output_dir / "transition_summary.csv", index=False
    )
    key_metrics.to_csv(args.output_dir / "key_metrics.csv", index=False)
    contrasts.to_csv(args.output_dir / "start_group_contrasts.csv", index=False)
    conditional_metrics.to_csv(
        args.output_dir / "conditional_visible_action_metrics.csv", index=False
    )
    conditional_contrasts.to_csv(
        args.output_dir / "conditional_visible_action_contrasts.csv",
        index=False,
    )
    concentration.to_csv(args.output_dir / "concentration.csv", index=False)
    loo.to_csv(
        args.output_dir / "leave_one_product_pair_out.csv", index=False
    )
    loo_summary.to_csv(
        args.output_dir / "leave_one_product_pair_out_summary.csv", index=False
    )
    conditional_loo.to_csv(
        args.output_dir
        / "conditional_visible_action_leave_one_product_pair_out.csv",
        index=False,
    )
    conditional_loo_summary.to_csv(
        args.output_dir
        / "conditional_visible_action_leave_one_product_pair_out_summary.csv",
        index=False,
    )
    no_next_breakdown.to_csv(
        args.output_dir / "no_next_observation_breakdown.csv", index=False
    )
    mapped_return_roles.to_csv(
        args.output_dir / "mapped_product_return_roles.csv", index=False
    )
    checks.to_csv(args.output_dir / "data_quality_checks.csv", index=False)

    start_counts = (
        sequences.group_by("first_owner_state")
        .agg(pl.len().alias("prs"), pl.col("repo_id").n_unique().alias("repositories"))
        .sort("prs", descending=True)
        .to_dicts()
    )
    conditional_metric_records = {
        f"{row.first_owner_state}:{row.metric}": float(row.estimate)
        for row in conditional_metrics.itertuples(index=False)
    }
    conditional_contrast_records = {
        row.metric: {
            "user_minus_mapped": float(row.user_minus_mapped),
            "repository_cluster_ci_low": float(
                row.repository_cluster_ci_low
            ),
            "repository_cluster_ci_high": float(
                row.repository_cluster_ci_high
            ),
        }
        for row in conditional_contrasts.itertuples(index=False)
    }
    summary = {
        "verdict": "APPENDIX",
        "scope": "cross-product feedback; >5 minutes through 48 hours",
        "base_prs": chains.height,
        "exact_duplicate_surplus_rows": raw_events.height - events.height,
        "logical_actions_48h_including_burst": actions.height,
        "postburst_timestamp_states_48h": timestamp_states.height,
        "primary_user_or_mapped_first_prs": primary.height,
        "start_counts": start_counts,
        "ambiguous_next_owner_prs": int(
            primary.filter(
                pl.col("transition_outcome") == "ambiguous_next_owner_tie"
            ).height
        ),
        "conditional_on_visible_next_action": conditional_metric_records,
        "conditional_user_minus_mapped": conditional_contrast_records,
        "quality_checks_all_pass": bool((checks["status"] == "PASS").all()),
        "later_merge_analyzed": False,
        "interpretation": (
            "descriptive public-state ordering; non-causal; broad reviewer-type "
            "sequence novelty overlaps Zhong et al. (arXiv:2607.13196)"
        ),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))
    print("\nTRANSITIONS\n", transition_summary.to_string(index=False))
    print("\nKEY METRICS\n", key_metrics.to_string(index=False))
    print("\nCONTRASTS\n", contrasts.to_string(index=False))
    print("\nCONDITIONAL VISIBLE ACTION METRICS\n", conditional_metrics.to_string(index=False))
    print("\nCONDITIONAL VISIBLE ACTION CONTRASTS\n", conditional_contrasts.to_string(index=False))
    print("\nLOO SUMMARY\n", loo_summary.to_string(index=False))
    print("\nQUALITY\n", checks.to_string(index=False))


if __name__ == "__main__":
    main()
