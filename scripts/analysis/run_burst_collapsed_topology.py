from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "outputs" / "cross_agent_review"
DEFAULT_OUTPUT = ROOT / "outputs" / "burst_topology"
THRESHOLDS_MINUTES = (0, 1, 5, 10, 30)
STATE_ORDER = (
    "user_account",
    "mapped_product",
    "other_bot",
    "branch_movement_untyped",
    "no_action_within_7d",
)
ACTION_STATES = STATE_ORDER[:-1]
STATE_PRIORITY = {state: index + 1 for index, state in enumerate(ACTION_STATES)}
PRIORITY_STATE = {value: key for key, value in STATE_PRIORITY.items()}
SEED = 20260826


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collapse rapid post-trigger bursts and identify the first observable "
            "accountable state in cross-product feedback PRs."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-draws", type=int, default=5_000)
    return parser.parse_args()


def classify_atomic_state(events: pl.DataFrame) -> pl.DataFrame:
    """Map each event to one observable account/product state.

    User-account evidence takes precedence over product mapping. At a tied first
    timestamp, the same ordering is applied across events: user account, mapped
    product, other bot, then branch movement/untyped. This makes the PR state
    mutually exclusive without relying on input row order. Mixed ties are
    retained as a diagnostic rather than silently ignored.
    """
    user_type = pl.col("response_user_type").fill_null("").str.to_lowercase()
    return events.with_columns(
        pl.when(user_type == "user")
        .then(pl.lit("user_account"))
        .when(pl.col("response_agent").is_not_null())
        .then(pl.lit("mapped_product"))
        .when(user_type == "bot")
        .then(pl.lit("other_bot"))
        .otherwise(pl.lit("branch_movement_untyped"))
        .alias("atomic_state")
    ).with_columns(
        pl.col("atomic_state")
        .replace_strict(STATE_PRIORITY, return_dtype=pl.Int8)
        .alias("state_priority")
    )


def build_first_state(
    chains: pl.DataFrame,
    events: pl.DataFrame,
    threshold_minutes: int,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Return one tie-aware first post-burst state per PR."""
    threshold_hours = threshold_minutes / 60.0
    post_burst = events.filter(pl.col("hours_after_trigger") > threshold_hours)
    first_times = post_burst.group_by("pr_id").agg(
        pl.col("response_dt").min().alias("first_post_burst_dt")
    )
    candidates = post_burst.join(first_times, on="pr_id", how="inner").filter(
        pl.col("response_dt") == pl.col("first_post_burst_dt")
    )
    first = (
        candidates.group_by("pr_id")
        .agg(
            pl.col("state_priority").min().alias("first_state_priority"),
            pl.col("first_post_burst_dt").first(),
            pl.col("hours_after_trigger").min().alias("first_hours_after_trigger"),
            pl.len().alias("n_events_at_first_timestamp"),
            pl.col("atomic_state")
            .n_unique()
            .alias("n_states_at_first_timestamp"),
        )
        .with_columns(
            pl.col("first_state_priority")
            .replace_strict(PRIORITY_STATE, return_dtype=pl.String)
            .alias("first_post_burst_state"),
            (
                (pl.col("first_hours_after_trigger") - threshold_hours) * 60.0
            ).alias("minutes_from_burst_end"),
            (pl.col("first_hours_after_trigger") * 60.0).alias(
                "minutes_from_trigger"
            ),
        )
    )
    base = chains.select(
        "pr_id",
        "repo_id",
        "repo_url",
        "author_agent",
        "trigger_reviewer_agent",
        "trigger_source",
        "trigger_dt",
        "response_end_dt",
    )
    output = (
        base.join(first, on="pr_id", how="left")
        .with_columns(
            pl.lit(threshold_minutes).cast(pl.Int16).alias("burst_threshold_minutes"),
            pl.col("first_post_burst_state").fill_null("no_action_within_7d"),
            pl.col("n_events_at_first_timestamp").fill_null(0),
            pl.col("n_states_at_first_timestamp").fill_null(0),
        )
        .select(
            "burst_threshold_minutes",
            "pr_id",
            "repo_id",
            "repo_url",
            "author_agent",
            "trigger_reviewer_agent",
            "trigger_source",
            "trigger_dt",
            "response_end_dt",
            "first_post_burst_state",
            "first_post_burst_dt",
            "first_hours_after_trigger",
            "minutes_from_trigger",
            "minutes_from_burst_end",
            "n_events_at_first_timestamp",
            "n_states_at_first_timestamp",
        )
    )
    collapsed = events.filter(pl.col("hours_after_trigger") <= threshold_hours)
    diagnostics = {
        "burst_threshold_minutes": threshold_minutes,
        "collapsed_event_rows": collapsed.height,
        "collapsed_prs": collapsed["pr_id"].n_unique() if collapsed.height else 0,
        "post_burst_event_rows": post_burst.height,
        "post_burst_action_prs": first.height,
        "no_post_burst_action_prs": chains.height - first.height,
        "first_timestamp_tie_prs": (
            first.filter(pl.col("n_events_at_first_timestamp") > 1).height
        ),
        "mixed_state_tie_prs": (
            first.filter(pl.col("n_states_at_first_timestamp") > 1).height
        ),
        "maximum_events_at_first_timestamp": (
            int(first["n_events_at_first_timestamp"].max()) if first.height else 0
        ),
    }
    return output, diagnostics


def repository_cluster_bootstrap(
    frame: pd.DataFrame,
    draws: int,
    threshold_minutes: int,
) -> dict[str, dict[str, tuple[float, float]]]:
    """Bootstrap PR-weighted state shares by resampling whole repositories."""
    counts = pd.crosstab(frame["repo_id"], frame["first_post_burst_state"])
    counts = counts.reindex(columns=STATE_ORDER, fill_value=0).to_numpy(dtype=float)
    n_repositories = counts.shape[0]
    rng = np.random.default_rng(SEED + threshold_minutes)
    all_share_draws: list[np.ndarray] = []
    action_share_draws: list[np.ndarray] = []
    completed = 0
    chunk_size = min(250, draws)
    while completed < draws:
        current = min(chunk_size, draws - completed)
        sampled_repositories = rng.integers(
            0,
            n_repositories,
            size=(current, n_repositories),
            dtype=np.int32,
        )
        sampled_counts = counts[sampled_repositories].sum(axis=1)
        all_denominator = sampled_counts.sum(axis=1, keepdims=True)
        all_share_draws.append(sampled_counts / all_denominator)
        action_denominator = sampled_counts[:, : len(ACTION_STATES)].sum(
            axis=1, keepdims=True
        )
        action_share_draws.append(
            np.divide(
                sampled_counts[:, : len(ACTION_STATES)],
                action_denominator,
                out=np.full(
                    (current, len(ACTION_STATES)), np.nan, dtype=float
                ),
                where=action_denominator > 0,
            )
        )
        completed += current
    all_draws = np.vstack(all_share_draws)
    action_draws = np.vstack(action_share_draws)
    result: dict[str, dict[str, tuple[float, float]]] = {}
    for state_index, state in enumerate(STATE_ORDER):
        all_low, all_high = np.nanquantile(
            all_draws[:, state_index], [0.025, 0.975]
        )
        if state in ACTION_STATES:
            action_index = ACTION_STATES.index(state)
            action_low, action_high = np.nanquantile(
                action_draws[:, action_index], [0.025, 0.975]
            )
        else:
            action_low = action_high = np.nan
        result[state] = {
            "all_prs": (float(all_low), float(all_high)),
            "post_burst_actions": (float(action_low), float(action_high)),
        }
    return result


def summarize_states(
    first_states: pl.DataFrame, bootstrap_draws: int
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    frame = first_states.to_pandas()
    for threshold in THRESHOLDS_MINUTES:
        subset = frame[frame["burst_threshold_minutes"] == threshold].copy()
        counts = subset["first_post_burst_state"].value_counts().reindex(
            STATE_ORDER, fill_value=0
        )
        action_denominator = int(counts.loc[list(ACTION_STATES)].sum())
        ci = repository_cluster_bootstrap(subset, bootstrap_draws, threshold)
        for state in STATE_ORDER:
            state_rows = subset[subset["first_post_burst_state"] == state]
            count = int(counts[state])
            timed_rows = state_rows[state_rows["minutes_from_trigger"].notna()]
            if state in ACTION_STATES and action_denominator:
                conditional_share = count / action_denominator
            else:
                conditional_share = np.nan
            rows.append(
                {
                    "burst_threshold_minutes": threshold,
                    "first_post_burst_state": state,
                    "prs": count,
                    "share_all_prs": count / len(subset),
                    "repository_cluster_ci_low": ci[state]["all_prs"][0],
                    "repository_cluster_ci_high": ci[state]["all_prs"][1],
                    "share_post_burst_actions": conditional_share,
                    "conditional_cluster_ci_low": ci[state][
                        "post_burst_actions"
                    ][0],
                    "conditional_cluster_ci_high": ci[state][
                        "post_burst_actions"
                    ][1],
                    "median_minutes_from_trigger": (
                        timed_rows["minutes_from_trigger"].median()
                        if not timed_rows.empty
                        else np.nan
                    ),
                    "median_minutes_from_burst_end": (
                        timed_rows["minutes_from_burst_end"].median()
                        if not timed_rows.empty
                        else np.nan
                    ),
                    "repositories": int(state_rows["repo_id"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def build_threshold_transitions(
    first_states: pd.DataFrame, draws: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compare each burst threshold with the zero-minute PR state.

    The change interval is paired at PR level and resamples whole repositories.
    Mapped-product retention is also calculated within the PRs classified as
    mapped-product-first at threshold zero.
    """
    baseline = first_states[
        first_states["burst_threshold_minutes"] == 0
    ][["pr_id", "repo_id", "first_post_burst_state"]].rename(
        columns={"first_post_burst_state": "zero_minute_state"}
    )
    transition_rows: list[dict[str, Any]] = []
    change_rows: list[dict[str, Any]] = []
    retention_rows: list[dict[str, Any]] = []
    for threshold in THRESHOLDS_MINUTES[1:]:
        current = first_states[
            first_states["burst_threshold_minutes"] == threshold
        ][["pr_id", "first_post_burst_state"]].rename(
            columns={"first_post_burst_state": "threshold_state"}
        )
        joined = baseline.merge(current, on="pr_id", how="inner", validate="1:1")
        transition = (
            joined.groupby(
                ["zero_minute_state", "threshold_state"], sort=False
            )
            .agg(prs=("pr_id", "size"), repositories=("repo_id", "nunique"))
            .reset_index()
        )
        baseline_counts = joined["zero_minute_state"].value_counts()
        for row in transition.itertuples(index=False):
            transition_rows.append(
                {
                    "burst_threshold_minutes": threshold,
                    "zero_minute_state": row.zero_minute_state,
                    "threshold_state": row.threshold_state,
                    "prs": int(row.prs),
                    "share_all_prs": row.prs / len(joined),
                    "share_within_zero_minute_state": (
                        row.prs / baseline_counts[row.zero_minute_state]
                    ),
                    "repositories": int(row.repositories),
                }
            )

        difference_columns: list[str] = []
        for state in STATE_ORDER:
            column = f"difference__{state}"
            joined[column] = (
                (joined["threshold_state"] == state).astype(int)
                - (joined["zero_minute_state"] == state).astype(int)
            )
            difference_columns.append(column)
        joined["zero_mapped_denominator"] = (
            joined["zero_minute_state"] == "mapped_product"
        ).astype(int)
        joined["mapped_retained_numerator"] = (
            (joined["zero_minute_state"] == "mapped_product")
            & (joined["threshold_state"] == "mapped_product")
        ).astype(int)
        repository = joined.groupby("repo_id", sort=False).agg(
            **{column: (column, "sum") for column in difference_columns},
            repository_prs=("pr_id", "size"),
            zero_mapped_denominator=("zero_mapped_denominator", "sum"),
            mapped_retained_numerator=("mapped_retained_numerator", "sum"),
        )
        diff_matrix = repository[difference_columns].to_numpy(dtype=float)
        sizes = repository["repository_prs"].to_numpy(dtype=float)
        mapped_denominator = repository["zero_mapped_denominator"].to_numpy(
            dtype=float
        )
        mapped_numerator = repository["mapped_retained_numerator"].to_numpy(
            dtype=float
        )
        n_repositories = len(repository)
        rng = np.random.default_rng(SEED + 1_000 + threshold)
        difference_draws: list[np.ndarray] = []
        retention_draws: list[np.ndarray] = []
        completed = 0
        chunk_size = min(250, draws)
        while completed < draws:
            current_draws = min(chunk_size, draws - completed)
            sampled = rng.integers(
                0,
                n_repositories,
                size=(current_draws, n_repositories),
                dtype=np.int32,
            )
            denominator = sizes[sampled].sum(axis=1, keepdims=True)
            difference_draws.append(
                diff_matrix[sampled].sum(axis=1) / denominator
            )
            retention_denominator = mapped_denominator[sampled].sum(axis=1)
            retention_draws.append(
                np.divide(
                    mapped_numerator[sampled].sum(axis=1),
                    retention_denominator,
                    out=np.full(current_draws, np.nan, dtype=float),
                    where=retention_denominator > 0,
                )
            )
            completed += current_draws
        boot_differences = np.vstack(difference_draws)
        for state_index, state in enumerate(STATE_ORDER):
            low, high = np.nanquantile(
                boot_differences[:, state_index], [0.025, 0.975]
            )
            estimate = float(joined[difference_columns[state_index]].mean())
            change_rows.append(
                {
                    "burst_threshold_minutes": threshold,
                    "first_post_burst_state": state,
                    "paired_share_change_from_zero": estimate,
                    "paired_change_percentage_points": estimate * 100.0,
                    "repository_cluster_ci_low": float(low),
                    "repository_cluster_ci_high": float(high),
                    "repository_cluster_ci_low_percentage_points": float(
                        low * 100.0
                    ),
                    "repository_cluster_ci_high_percentage_points": float(
                        high * 100.0
                    ),
                    "prs": len(joined),
                    "repositories": n_repositories,
                }
            )
        retention_array = np.concatenate(retention_draws)
        retention_low, retention_high = np.nanquantile(
            retention_array, [0.025, 0.975]
        )
        zero_mapped = int(joined["zero_mapped_denominator"].sum())
        retained = int(joined["mapped_retained_numerator"].sum())
        retention_rows.append(
            {
                "burst_threshold_minutes": threshold,
                "zero_minute_mapped_product_prs": zero_mapped,
                "mapped_product_state_retained_prs": retained,
                "mapped_product_state_reclassified_prs": zero_mapped - retained,
                "retention_share": retained / zero_mapped,
                "reclassified_share": 1.0 - retained / zero_mapped,
                "repository_cluster_retention_ci_low": float(retention_low),
                "repository_cluster_retention_ci_high": float(retention_high),
                "repositories_with_zero_minute_mapped_state": int(
                    (repository["zero_mapped_denominator"] > 0).sum()
                ),
            }
        )
    return (
        pd.DataFrame(transition_rows),
        pd.DataFrame(change_rows),
        pd.DataFrame(retention_rows),
    )


def leave_one_group_out(
    first_states: pd.DataFrame,
    unit_column: str,
    unit_label: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for threshold in THRESHOLDS_MINUTES:
        frame = first_states[
            first_states["burst_threshold_minutes"] == threshold
        ].copy()
        full_counts = (
            frame["first_post_burst_state"]
            .value_counts()
            .reindex(STATE_ORDER, fill_value=0)
        )
        full_n = len(frame)
        grouped_counts = pd.crosstab(
            frame[unit_column], frame["first_post_burst_state"]
        ).reindex(columns=STATE_ORDER, fill_value=0)
        group_sizes = grouped_counts.sum(axis=1)
        for excluded_group, excluded_counts in grouped_counts.iterrows():
            remaining_n = full_n - int(group_sizes.loc[excluded_group])
            remaining_counts = full_counts - excluded_counts
            remaining_action_n = int(
                remaining_counts.loc[list(ACTION_STATES)].sum()
            )
            for state in STATE_ORDER:
                count = int(remaining_counts[state])
                rows.append(
                    {
                        "burst_threshold_minutes": threshold,
                        "exclusion_unit": unit_label,
                        "excluded_group": str(excluded_group),
                        "excluded_group_prs": int(group_sizes.loc[excluded_group]),
                        "remaining_prs": remaining_n,
                        "first_post_burst_state": state,
                        "remaining_state_prs": count,
                        "share_all_prs": count / remaining_n,
                        "share_post_burst_actions": (
                            count / remaining_action_n
                            if state in ACTION_STATES and remaining_action_n
                            else np.nan
                        ),
                    }
                )
    return pd.DataFrame(rows)


def summarize_leave_one_out(
    loo_frames: list[pd.DataFrame], summary: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    combined = pd.concat(loo_frames, ignore_index=True)
    rows: list[dict[str, Any]] = []
    ordering_rows: list[dict[str, Any]] = []
    for (threshold, unit, state), frame in combined.groupby(
        [
            "burst_threshold_minutes",
            "exclusion_unit",
            "first_post_burst_state",
        ],
        sort=False,
    ):
        full_share = float(
            summary.loc[
                (summary["burst_threshold_minutes"] == threshold)
                & (summary["first_post_burst_state"] == state),
                "share_all_prs",
            ].iloc[0]
        )
        minimum = frame.loc[frame["share_all_prs"].idxmin()]
        maximum = frame.loc[frame["share_all_prs"].idxmax()]
        rows.append(
            {
                "burst_threshold_minutes": threshold,
                "exclusion_unit": unit,
                "first_post_burst_state": state,
                "full_share": full_share,
                "minimum_loo_share": float(minimum["share_all_prs"]),
                "minimum_excluded_group": minimum["excluded_group"],
                "maximum_loo_share": float(maximum["share_all_prs"]),
                "maximum_excluded_group": maximum["excluded_group"],
                "maximum_absolute_shift_percentage_points": float(
                    (frame["share_all_prs"] - full_share).abs().max() * 100.0
                ),
                "exclusions": len(frame),
            }
        )
    for (threshold, unit), frame in combined.groupby(
        ["burst_threshold_minutes", "exclusion_unit"], sort=False
    ):
        wide = frame.pivot(
            index="excluded_group",
            columns="first_post_burst_state",
            values="share_all_prs",
        )
        difference = wide["user_account"] - wide["mapped_product"]
        state_columns = list(STATE_ORDER)
        largest = wide[state_columns].idxmax(axis=1)
        ordering_rows.append(
            {
                "burst_threshold_minutes": threshold,
                "exclusion_unit": unit,
                "exclusions": len(wide),
                "minimum_user_minus_mapped_percentage_points": float(
                    difference.min() * 100.0
                ),
                "maximum_user_minus_mapped_percentage_points": float(
                    difference.max() * 100.0
                ),
                "user_exceeds_mapped_in_every_exclusion": bool(
                    (difference > 0).all()
                ),
                "no_action_is_largest_in_every_exclusion": bool(
                    (largest == "no_action_within_7d").all()
                ),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(ordering_rows)


def build_quality_checks(
    raw_events: pl.DataFrame,
    events: pl.DataFrame,
    chains: pl.DataFrame,
    first_states: pl.DataFrame,
    raw_first_states: pl.DataFrame,
    diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    checks: list[dict[str, Any]] = []

    def add(
        check: str,
        status: str,
        value: Any,
        expected: str,
        severity: str,
        note: str,
    ) -> None:
        checks.append(
            {
                "check": check,
                "status": status,
                "value": value,
                "expected": expected,
                "severity": severity,
                "note": note,
            }
        )

    chain_unique = chains["pr_id"].n_unique() == chains.height
    add(
        "chain_pr_id_unique",
        "PASS" if chain_unique else "FAIL",
        chains["pr_id"].n_unique(),
        f"{chains.height} unique PR IDs",
        "critical",
        "Required for one PR per topology state.",
    )
    relation_ok = bool((chains["feedback_relation"] == "cross_product").all())
    add(
        "cross_product_cohort_only",
        "PASS" if relation_ok else "FAIL",
        relation_ok,
        "True",
        "critical",
        "Prevents mixing the same-product comparison cohort into this analysis.",
    )
    window_seconds = (
        chains["response_end_dt"] - chains["trigger_dt"]
    ).dt.total_seconds()
    window_ok = bool((window_seconds == 7 * 24 * 3600).all())
    add(
        "complete_seven_day_window",
        "PASS" if window_ok else "FAIL",
        window_ok,
        "True",
        "critical",
        "All PRs must have the same observable follow-up horizon.",
    )
    chain_ids = set(chains["pr_id"].to_list())
    event_ids = set(raw_events["pr_id"].to_list())
    orphan_prs = len(event_ids - chain_ids)
    add(
        "event_prs_have_chain_parent",
        "PASS" if orphan_prs == 0 else "FAIL",
        orphan_prs,
        "0 orphan PR IDs",
        "critical",
        "Checks event-to-PR referential integrity.",
    )
    before_or_equal = raw_events.filter(
        pl.col("response_dt") <= pl.col("trigger_dt")
    ).height
    add(
        "events_strictly_after_trigger",
        "PASS" if before_or_equal == 0 else "FAIL",
        before_or_equal,
        "0 violations",
        "critical",
        "Needed for temporal ordering.",
    )
    after_window = raw_events.filter(
        pl.col("response_dt") > pl.col("response_end_dt")
    ).height
    add(
        "events_inside_response_window",
        "PASS" if after_window == 0 else "FAIL",
        after_window,
        "0 violations",
        "critical",
        "Prevents follow-up leakage beyond seven days.",
    )
    derived_hours = (
        (raw_events["response_dt"] - raw_events["trigger_dt"]).dt.total_seconds()
        / 3600.0
    )
    max_hour_error = float(
        (derived_hours - raw_events["hours_after_trigger"]).abs().max()
    )
    add(
        "hours_after_trigger_matches_timestamps",
        "PASS" if max_hour_error < 1e-9 else "FAIL",
        max_hour_error,
        "< 1e-9 hours",
        "high",
        "Protects threshold assignment from a stale derived field.",
    )
    surplus_duplicates = raw_events.height - events.height
    duplicate_rows = raw_events.filter(raw_events.is_duplicated())
    duplicate_sources = sorted(
        duplicate_rows["response_source"].unique().drop_nulls().to_list()
    )
    duplicate_prs = duplicate_rows["pr_id"].n_unique()
    add(
        "exact_duplicate_event_surplus",
        "WARN" if surplus_duplicates else "PASS",
        surplus_duplicates,
        "0 preferred; exact-deduplicated analytical view used",
        "low",
        (
            f"Duplicates involve {duplicate_prs} PRs and sources "
            f"{duplicate_sources}; first-state invariance is checked below."
        ),
    )
    later_reviews = events.filter(pl.col("response_source") == "subsequent_review")
    duplicate_review_batches = (
        later_reviews.select(
            pl.struct(["pr_id", "response_review_id"]).is_duplicated().sum()
        ).item()
        if later_reviews.height
        else 0
    )
    add(
        "later_reviews_debatched_by_review_id",
        "PASS" if duplicate_review_batches == 0 else "FAIL",
        duplicate_review_batches,
        "0 duplicated PR-review IDs",
        "high",
        "A review batch is counted once even if it contains many inline comments.",
    )
    metadata = raw_events.join(
        chains.select(
            "pr_id",
            pl.col("trigger_dt").alias("chain_trigger_dt"),
            pl.col("response_end_dt").alias("chain_response_end_dt"),
            pl.col("author_agent").alias("chain_author_agent"),
            pl.col("trigger_reviewer_agent").alias(
                "chain_trigger_reviewer_agent"
            ),
        ),
        on="pr_id",
        how="left",
    )
    metadata_mismatches = metadata.filter(
        (pl.col("trigger_dt") != pl.col("chain_trigger_dt"))
        | (pl.col("response_end_dt") != pl.col("chain_response_end_dt"))
        | (pl.col("author_agent") != pl.col("chain_author_agent"))
        | (
            pl.col("trigger_reviewer_agent")
            != pl.col("chain_trigger_reviewer_agent")
        )
    ).height
    add(
        "event_chain_trigger_metadata_consistent",
        "PASS" if metadata_mismatches == 0 else "FAIL",
        metadata_mismatches,
        "0 mismatched event rows",
        "high",
        "Protects product-pair and time-window joins.",
    )
    expected_rows = chains.height * len(THRESHOLDS_MINUTES)
    add(
        "one_state_row_per_pr_threshold",
        "PASS" if first_states.height == expected_rows else "FAIL",
        first_states.height,
        str(expected_rows),
        "critical",
        "The analysis grain is PR by burst threshold.",
    )
    duplicate_grain = first_states.select(
        pl.struct(["burst_threshold_minutes", "pr_id"]).is_duplicated().sum()
    ).item()
    add(
        "pr_threshold_key_unique",
        "PASS" if duplicate_grain == 0 else "FAIL",
        duplicate_grain,
        "0 duplicated keys",
        "critical",
        "Ensures mutually exclusive assignment.",
    )
    allowed_states = set(STATE_ORDER)
    observed_states = set(first_states["first_post_burst_state"].unique().to_list())
    invalid_states = sorted(observed_states - allowed_states)
    add(
        "accepted_state_values_only",
        "PASS" if not invalid_states else "FAIL",
        invalid_states,
        str(list(STATE_ORDER)),
        "critical",
        "Keeps state labels exhaustive and mutually exclusive.",
    )
    negative_lag = first_states.filter(
        pl.col("minutes_from_burst_end").is_not_null()
        & (pl.col("minutes_from_burst_end") <= 0)
    ).height
    add(
        "first_state_occurs_after_burst_end",
        "PASS" if negative_lag == 0 else "FAIL",
        negative_lag,
        "0 non-positive lags",
        "critical",
        "Confirms that collapsed events are excluded from ownership.",
    )
    no_action_counts = diagnostics.sort_values("burst_threshold_minutes")[
        "no_post_burst_action_prs"
    ].to_numpy()
    monotone_silence = bool(np.all(np.diff(no_action_counts) >= 0))
    add(
        "no_action_count_monotone_with_threshold",
        "PASS" if monotone_silence else "FAIL",
        no_action_counts.tolist(),
        "nondecreasing",
        "high",
        "A wider collapsed window cannot create a new later event.",
    )
    compare = first_states.select(
        "burst_threshold_minutes", "pr_id", "first_post_burst_state"
    ).join(
        raw_first_states.select(
            "burst_threshold_minutes",
            "pr_id",
            pl.col("first_post_burst_state").alias("raw_first_state"),
        ),
        on=["burst_threshold_minutes", "pr_id"],
        how="inner",
    )
    changed_by_dedup = compare.filter(
        pl.col("first_post_burst_state") != pl.col("raw_first_state")
    ).height
    add(
        "first_state_invariant_to_exact_deduplication",
        "PASS" if changed_by_dedup == 0 else "FAIL",
        changed_by_dedup,
        "0 changed PR-threshold states",
        "high",
        "Shows whether the small duplicate issue affects the estimand.",
    )
    raw_action_prs = int(chains["any_observable_response"].sum())
    threshold_zero_actions = int(
        diagnostics.loc[
            diagnostics["burst_threshold_minutes"] == 0,
            "post_burst_action_prs",
        ].iloc[0]
    )
    add(
        "threshold_zero_reconciles_chain_response_flag",
        "PASS" if raw_action_prs == threshold_zero_actions else "FAIL",
        threshold_zero_actions,
        str(raw_action_prs),
        "high",
        "Connects the topology denominator to the published response chain.",
    )
    return pd.DataFrame(checks)


def _state_row(summary: pd.DataFrame, threshold: int, state: str) -> pd.Series:
    return summary.loc[
        (summary["burst_threshold_minutes"] == threshold)
        & (summary["first_post_burst_state"] == state)
    ].iloc[0]


def build_readme(summary_payload: dict[str, Any]) -> str:
    five = summary_payload["five_minute_landmark"]
    raw = summary_payload["zero_minute_landmark"]
    thirty = summary_payload["thirty_minute_landmark"]
    return f"""# Burst-collapsed response topology

This analysis asks how the first observable post-feedback state changes when
events in a rapid trigger-adjacent burst are collapsed with the trigger. It is
a sensitivity analysis of public traces, not an estimate of a treatment effect,
semantic resolution, or verified manual work.

## Main result

At zero minutes, a mapped product is the first state on
{raw['mapped_product']['prs']:,}/{summary_payload['cohort_prs']:,} PRs
({raw['mapped_product']['share_all_prs']:.2%}). After collapsing the first five
minutes, that count is {five['mapped_product']['prs']:,}
({five['mapped_product']['share_all_prs']:.2%}; repository-cluster bootstrap
95% interval {five['mapped_product']['cluster_ci'][0]:.2%} to
{five['mapped_product']['cluster_ci'][1]:.2%}). The user-account state is then
{five['user_account']['prs']:,} PRs ({five['user_account']['share_all_prs']:.2%})
and {five['user_account']['share_post_burst_actions']:.2%} of PRs with any
post-burst action. The largest state is no later visible action:
{five['no_action_within_7d']['prs']:,} PRs
({five['no_action_within_7d']['share_all_prs']:.2%}).

Within the {summary_payload['five_minute_mapped_retention']['zero_minute_mapped_product_prs']:,}
PRs initially classified as mapped-product-first,
{summary_payload['five_minute_mapped_retention']['mapped_product_state_reclassified_prs']:,}
({summary_payload['five_minute_mapped_retention']['reclassified_share']:.2%})
are assigned a different first state after the five-minute collapse. The mapped
state retention estimate is
{summary_payload['five_minute_mapped_retention']['retention_share']:.2%}
(repository-cluster bootstrap 95% interval
{summary_payload['five_minute_mapped_retention']['cluster_ci'][0]:.2%} to
{summary_payload['five_minute_mapped_retention']['cluster_ci'][1]:.2%}).

At 30 minutes, mapped-product first state falls to
{thirty['mapped_product']['prs']:,} PRs
({thirty['mapped_product']['share_all_prs']:.2%}). The result supports a narrow
measurement claim: part of apparent multi-product continuation is concentrated
inside a rapid fan-out window, while later visible ownership is more often a
user-account event or no visible action. Account type does not prove who wrote
the content, and later activity does not prove that it addressed the trigger.

## State rule

For each threshold (0, 1, 5, 10, and 30 minutes), all events at or before the
threshold are collapsed into the trigger burst. At the first later timestamp,
the mutually exclusive priority is user account, mapped product, other bot,
then branch movement/untyped. Mixed simultaneous states are counted in
`tie_diagnostics.csv`; the priority prevents arbitrary input-row ordering.

## Files

- `burst_collapsed_first_state.parquet`: one row per PR and threshold.
- `burst_topology_summary.csv`: counts, shares, medians, and repository-cluster
  bootstrap intervals.
- `burst_collapse_profile.csv` and `tie_diagnostics.csv`: burst and tie checks.
- `state_transition_from_zero.csv`, `threshold_change_from_zero.csv`, and
  `mapped_product_retention.csv`: paired state sensitivity and clustered
  uncertainty.
- `leave_one_product_pair_out.csv`, `leave_one_repository_out.csv`, and
  `leave_one_out_ranges.csv`: sensitivity to concentrated groups.
- `ordering_robustness.csv`: whether the headline ordering survives each
  deletion.
- `data_quality_checks.csv`: grain, time, join, de-batching, and duplicate
  invariants.
- `summary.json`: compact machine-readable headline results.

## Data-quality note

The input event ledger contains {summary_payload['data_quality']['surplus_exact_duplicates']}
surplus exact duplicate rows, all from force-push traces and limited to
{summary_payload['data_quality']['duplicate_prs']} PRs. The analysis uses an
exact-deduplicated view. No PR-threshold first-state assignment changes when the
raw rows are retained.
"""


def main() -> None:
    args = parse_args()
    if args.bootstrap_draws < 100:
        raise ValueError("--bootstrap-draws must be at least 100")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    chains = pl.read_parquet(args.input_dir / "cross_feedback_response_chains.parquet")
    raw_events = pl.read_parquet(
        args.input_dir / "cross_feedback_response_events.parquet"
    )
    # A tiny number of force-push rows are exact duplicates in the source table.
    # Preserve the raw frame for diagnostics and use a stable deduplicated view.
    events = raw_events.unique(maintain_order=True)
    raw_enriched = classify_atomic_state(raw_events)
    enriched = classify_atomic_state(events)

    first_frames: list[pl.DataFrame] = []
    raw_first_frames: list[pl.DataFrame] = []
    diagnostic_rows: list[dict[str, Any]] = []
    for threshold in THRESHOLDS_MINUTES:
        first, diagnostics = build_first_state(chains, enriched, threshold)
        raw_first, _ = build_first_state(chains, raw_enriched, threshold)
        first_frames.append(first)
        raw_first_frames.append(raw_first)
        diagnostic_rows.append(diagnostics)
    first_states = pl.concat(first_frames).sort(
        ["burst_threshold_minutes", "pr_id"]
    )
    raw_first_states = pl.concat(raw_first_frames).sort(
        ["burst_threshold_minutes", "pr_id"]
    )
    diagnostics = pd.DataFrame(diagnostic_rows)
    diagnostics["share_prs_with_collapsed_event"] = (
        diagnostics["collapsed_prs"] / chains.height
    )
    diagnostics["share_prs_with_post_burst_action"] = (
        diagnostics["post_burst_action_prs"] / chains.height
    )
    diagnostics["share_prs_without_post_burst_action"] = (
        diagnostics["no_post_burst_action_prs"] / chains.height
    )

    topology_summary = summarize_states(first_states, args.bootstrap_draws)
    first_pd = first_states.to_pandas()
    transitions, threshold_changes, mapped_retention = build_threshold_transitions(
        first_pd, args.bootstrap_draws
    )
    first_pd["product_pair"] = (
        first_pd["author_agent"].astype(str)
        + " -> "
        + first_pd["trigger_reviewer_agent"].astype(str)
    )
    loo_pair = leave_one_group_out(first_pd, "product_pair", "product_pair")
    loo_repo = leave_one_group_out(first_pd, "repo_id", "repository")
    loo_ranges, ordering = summarize_leave_one_out(
        [loo_pair, loo_repo], topology_summary
    )
    quality = build_quality_checks(
        raw_events,
        events,
        chains,
        first_states,
        raw_first_states,
        diagnostics,
    )
    failed = quality[quality["status"] == "FAIL"]
    if not failed.empty:
        raise RuntimeError(
            "Burst topology quality checks failed: "
            + ", ".join(failed["check"].tolist())
        )

    first_states.write_parquet(
        args.output_dir / "burst_collapsed_first_state.parquet"
    )
    topology_summary.to_csv(
        args.output_dir / "burst_topology_summary.csv", index=False
    )
    transitions.to_csv(
        args.output_dir / "state_transition_from_zero.csv", index=False
    )
    threshold_changes.to_csv(
        args.output_dir / "threshold_change_from_zero.csv", index=False
    )
    mapped_retention.to_csv(
        args.output_dir / "mapped_product_retention.csv", index=False
    )
    diagnostics.to_csv(args.output_dir / "burst_collapse_profile.csv", index=False)
    diagnostics[
        [
            "burst_threshold_minutes",
            "post_burst_action_prs",
            "first_timestamp_tie_prs",
            "mixed_state_tie_prs",
            "maximum_events_at_first_timestamp",
        ]
    ].to_csv(args.output_dir / "tie_diagnostics.csv", index=False)
    loo_pair.to_csv(
        args.output_dir / "leave_one_product_pair_out.csv", index=False
    )
    loo_repo.to_csv(args.output_dir / "leave_one_repository_out.csv", index=False)
    loo_ranges.to_csv(args.output_dir / "leave_one_out_ranges.csv", index=False)
    ordering.to_csv(args.output_dir / "ordering_robustness.csv", index=False)
    quality.to_csv(args.output_dir / "data_quality_checks.csv", index=False)

    def landmark(threshold: int) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for state in STATE_ORDER:
            row = _state_row(topology_summary, threshold, state)
            payload[state] = {
                "prs": int(row["prs"]),
                "share_all_prs": float(row["share_all_prs"]),
                "cluster_ci": [
                    float(row["repository_cluster_ci_low"]),
                    float(row["repository_cluster_ci_high"]),
                ],
                "share_post_burst_actions": (
                    None
                    if pd.isna(row["share_post_burst_actions"])
                    else float(row["share_post_burst_actions"])
                ),
                "median_minutes_from_burst_end": (
                    None
                    if pd.isna(row["median_minutes_from_burst_end"])
                    else float(row["median_minutes_from_burst_end"])
                ),
            }
        return payload

    duplicate_rows = raw_events.filter(raw_events.is_duplicated())
    zero = landmark(0)
    five = landmark(5)
    thirty = landmark(30)
    five_ordering = ordering[ordering["burst_threshold_minutes"] == 5]
    five_retention_row = mapped_retention.loc[
        mapped_retention["burst_threshold_minutes"] == 5
    ].iloc[0]
    five_mapped_change_row = threshold_changes.loc[
        (threshold_changes["burst_threshold_minutes"] == 5)
        & (
            threshold_changes["first_post_burst_state"]
            == "mapped_product"
        )
    ].iloc[0]
    summary_payload: dict[str, Any] = {
        "interpretation": (
            "Observed public response topology; no causal, semantic-resolution, "
            "or verified-manual-work claim."
        ),
        "cohort_prs": chains.height,
        "repositories": chains["repo_id"].n_unique(),
        "product_pairs": chains.select(
            pl.struct(["author_agent", "trigger_reviewer_agent"]).n_unique()
        ).item(),
        "raw_event_rows": raw_events.height,
        "deduplicated_event_rows": events.height,
        "bootstrap_draws": args.bootstrap_draws,
        "zero_minute_landmark": zero,
        "five_minute_landmark": five,
        "thirty_minute_landmark": thirty,
        "five_minute_mapped_product_change_from_zero": {
            "prs": five["mapped_product"]["prs"]
            - zero["mapped_product"]["prs"],
            "percentage_points": (
                five["mapped_product"]["share_all_prs"]
                - zero["mapped_product"]["share_all_prs"]
            )
            * 100.0,
            "relative_change": (
                five["mapped_product"]["share_all_prs"]
                / zero["mapped_product"]["share_all_prs"]
                - 1.0
            ),
            "paired_repository_cluster_ci_percentage_points": [
                float(
                    five_mapped_change_row[
                        "repository_cluster_ci_low_percentage_points"
                    ]
                ),
                float(
                    five_mapped_change_row[
                        "repository_cluster_ci_high_percentage_points"
                    ]
                ),
            ],
        },
        "five_minute_mapped_retention": {
            "zero_minute_mapped_product_prs": int(
                five_retention_row["zero_minute_mapped_product_prs"]
            ),
            "mapped_product_state_retained_prs": int(
                five_retention_row["mapped_product_state_retained_prs"]
            ),
            "mapped_product_state_reclassified_prs": int(
                five_retention_row["mapped_product_state_reclassified_prs"]
            ),
            "retention_share": float(five_retention_row["retention_share"]),
            "reclassified_share": float(
                five_retention_row["reclassified_share"]
            ),
            "cluster_ci": [
                float(
                    five_retention_row[
                        "repository_cluster_retention_ci_low"
                    ]
                ),
                float(
                    five_retention_row[
                        "repository_cluster_retention_ci_high"
                    ]
                ),
            ],
        },
        "five_minute_user_to_mapped_ratio": (
            five["user_account"]["share_all_prs"]
            / five["mapped_product"]["share_all_prs"]
        ),
        "five_minute_ordering_robustness": five_ordering.to_dict(
            orient="records"
        ),
        "data_quality": {
            "surplus_exact_duplicates": raw_events.height - events.height,
            "duplicate_prs": duplicate_rows["pr_id"].n_unique(),
            "failed_checks": int((quality["status"] == "FAIL").sum()),
            "warning_checks": int((quality["status"] == "WARN").sum()),
        },
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary_payload, indent=2), encoding="utf-8"
    )
    (args.output_dir / "README.md").write_text(
        build_readme(summary_payload), encoding="utf-8"
    )
    print(json.dumps(summary_payload, indent=2))


if __name__ == "__main__":
    main()
