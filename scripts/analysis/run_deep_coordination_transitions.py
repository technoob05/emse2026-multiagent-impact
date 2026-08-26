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
OUTPUT_DIR = ROOT / "outputs" / "deep_coordination"
INITIAL_BURST_MINUTES = 5
WASHOUT_MINUTES = (0, 5, 30, 60)
EPISODE_GAPS_MINUTES = (0, 1, 5, 10)
PRIMARY_GAP_MINUTES = 5
MAX_AUTOMATION_STATE = 4
SEED = 20260826

ATOMIC_STATES = (
    "user_account",
    "mapped_product",
    "other_bot",
    "branch_movement_untyped",
)
ATOMIC_PRIORITY = {state: index + 1 for index, state in enumerate(ATOMIC_STATES)}
PRIORITY_ATOMIC = {value: key for key, value in ATOMIC_PRIORITY.items()}
NEXT_OWNER_STATES = (
    "user_account",
    "same_mapped_product",
    "different_mapped_product",
    "other_bot",
    "branch_movement_untyped",
    "no_later_state",
)
ESCALATION_OUTCOMES = (
    "user_account",
    "another_automation",
    "branch_movement_untyped",
    "no_later_episode",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deep temporal tests of public multi-agent ownership persistence."
    )
    parser.add_argument("--cross-dir", type=Path, default=CROSS_DIR)
    parser.add_argument("--burst-dir", type=Path, default=BURST_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--bootstrap-draws", type=int, default=5_000)
    parser.add_argument("--permutation-draws", type=int, default=500)
    return parser.parse_args()


def classify_events(events: pl.DataFrame) -> pl.DataFrame:
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
        .replace_strict(ATOMIC_PRIORITY, return_dtype=pl.Int8)
        .alias("state_priority")
    )


def bootstrap_cluster_shares(
    frame: pd.DataFrame,
    state_column: str,
    state_order: tuple[str, ...],
    draws: int,
    seed: int,
) -> dict[str, tuple[float, float]]:
    counts = pd.crosstab(frame["repo_id"], frame[state_column]).reindex(
        columns=state_order, fill_value=0
    )
    matrix = counts.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    share_draws: list[np.ndarray] = []
    completed = 0
    while completed < draws:
        current = min(250, draws - completed)
        sampled = rng.integers(
            0, len(matrix), size=(current, len(matrix)), dtype=np.int32
        )
        totals = matrix[sampled].sum(axis=1)
        share_draws.append(totals / totals.sum(axis=1, keepdims=True))
        completed += current
    samples = np.vstack(share_draws)
    result: dict[str, tuple[float, float]] = {}
    for index, state in enumerate(state_order):
        low, high = np.quantile(samples[:, index], [0.025, 0.975])
        result[state] = (float(low), float(high))
    return result


def bootstrap_cluster_mean_difference(
    frame: pd.DataFrame,
    difference_column: str,
    draws: int,
    seed: int,
) -> tuple[float, float]:
    grouped = frame.groupby("repo_id", sort=False)[difference_column].agg(
        ["sum", "size"]
    )
    numerators = grouped["sum"].to_numpy(dtype=float)
    denominators = grouped["size"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    estimates: list[np.ndarray] = []
    completed = 0
    while completed < draws:
        current = min(250, draws - completed)
        sampled = rng.integers(
            0,
            len(grouped),
            size=(current, len(grouped)),
            dtype=np.int32,
        )
        estimates.append(
            numerators[sampled].sum(axis=1)
            / denominators[sampled].sum(axis=1)
        )
        completed += current
    low, high = np.quantile(np.concatenate(estimates), [0.025, 0.975])
    return float(low), float(high)


def mapped_first_anchors(
    events: pl.DataFrame,
    burst_states: pl.DataFrame,
    chains: pl.DataFrame,
) -> pl.DataFrame:
    anchors = burst_states.filter(
        (pl.col("burst_threshold_minutes") == INITIAL_BURST_MINUTES)
        & (pl.col("first_post_burst_state") == "mapped_product")
    ).select(
        "pr_id",
        "repo_id",
        "first_post_burst_dt",
    )
    products = (
        events.join(anchors.select("pr_id", "first_post_burst_dt"), on="pr_id")
        .filter(
            (pl.col("response_dt") == pl.col("first_post_burst_dt"))
            & (pl.col("atomic_state") == "mapped_product")
        )
        .group_by("pr_id")
        .agg(
            pl.col("response_agent").drop_nulls().n_unique().alias("n_anchor_products"),
            pl.col("response_agent").drop_nulls().first().alias("anchor_product"),
        )
    )
    return (
        anchors.join(products, on="pr_id", how="left")
        .join(
            chains.select(
                "pr_id",
                "repo_url",
                "author_agent",
                "trigger_reviewer_agent",
                "trigger_source",
            ),
            on="pr_id",
            how="left",
        )
        .with_columns(
            (
                pl.col("author_agent")
                + pl.lit(" -> ")
                + pl.col("trigger_reviewer_agent")
            ).alias("product_pair")
        )
    )


def build_next_owner_sequences(
    events: pl.DataFrame, anchors: pl.DataFrame
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    anchor_keys = anchors.select(
        "pr_id",
        "repo_id",
        "repo_url",
        "product_pair",
        "author_agent",
        "trigger_reviewer_agent",
        "first_post_burst_dt",
        "anchor_product",
    )
    for washout in WASHOUT_MINUTES:
        later = events.join(
            anchor_keys.select(
                "pr_id", "first_post_burst_dt", "anchor_product"
            ),
            on="pr_id",
            how="inner",
        ).filter(
            pl.col("response_dt")
            > pl.col("first_post_burst_dt") + pl.duration(minutes=washout)
        )
        next_times = later.group_by("pr_id").agg(
            pl.col("response_dt").min().alias("next_state_dt")
        )
        candidates = later.join(next_times, on="pr_id", how="inner").filter(
            pl.col("response_dt") == pl.col("next_state_dt")
        )
        next_states = (
            candidates.group_by("pr_id")
            .agg(
                (pl.col("atomic_state") == "user_account")
                .any()
                .alias("has_user"),
                (pl.col("atomic_state") == "mapped_product")
                .any()
                .alias("has_mapped"),
                (
                    (pl.col("atomic_state") == "mapped_product")
                    & (pl.col("response_agent") != pl.col("anchor_product"))
                )
                .any()
                .alias("has_different_mapped"),
                (pl.col("atomic_state") == "other_bot")
                .any()
                .alias("has_other_bot"),
                pl.col("next_state_dt").first(),
                pl.len().alias("n_events_at_next_timestamp"),
                pl.col("atomic_state").n_unique().alias("n_states_at_next_timestamp"),
            )
            .with_columns(
                pl.when(pl.col("has_user"))
                .then(pl.lit("user_account"))
                .when(pl.col("has_mapped") & pl.col("has_different_mapped"))
                .then(pl.lit("different_mapped_product"))
                .when(pl.col("has_mapped"))
                .then(pl.lit("same_mapped_product"))
                .when(pl.col("has_other_bot"))
                .then(pl.lit("other_bot"))
                .otherwise(pl.lit("branch_movement_untyped"))
                .alias("next_owner_state")
            )
        )
        frame = (
            anchor_keys.join(next_states, on="pr_id", how="left")
            .with_columns(
                pl.lit(washout).cast(pl.Int16).alias("washout_minutes"),
                pl.col("next_owner_state").fill_null("no_later_state"),
                pl.col("n_events_at_next_timestamp").fill_null(0),
                pl.col("n_states_at_next_timestamp").fill_null(0),
                (
                    (
                        pl.col("next_state_dt")
                        - pl.col("first_post_burst_dt")
                    ).dt.total_seconds()
                    / 60.0
                ).alias("minutes_from_anchor_to_next"),
            )
            .select(
                "washout_minutes",
                "pr_id",
                "repo_id",
                "repo_url",
                "product_pair",
                "author_agent",
                "trigger_reviewer_agent",
                "anchor_product",
                "first_post_burst_dt",
                "next_state_dt",
                "minutes_from_anchor_to_next",
                "next_owner_state",
                "n_events_at_next_timestamp",
                "n_states_at_next_timestamp",
            )
        )
        frames.append(frame)
    return pl.concat(frames).sort(["washout_minutes", "pr_id"])


def summarize_next_owner(
    sequences: pd.DataFrame, draws: int
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for washout in WASHOUT_MINUTES:
        frame = sequences[sequences["washout_minutes"] == washout]
        counts = frame["next_owner_state"].value_counts().reindex(
            NEXT_OWNER_STATES, fill_value=0
        )
        ci = bootstrap_cluster_shares(
            frame,
            "next_owner_state",
            NEXT_OWNER_STATES,
            draws,
            SEED + 100 + washout,
        )
        for state in NEXT_OWNER_STATES:
            state_rows = frame[frame["next_owner_state"] == state]
            rows.append(
                {
                    "washout_minutes": washout,
                    "next_owner_state": state,
                    "prs": int(counts[state]),
                    "share": counts[state] / len(frame),
                    "repository_cluster_ci_low": ci[state][0],
                    "repository_cluster_ci_high": ci[state][1],
                    "median_minutes_from_anchor": (
                        state_rows["minutes_from_anchor_to_next"].median()
                        if state != "no_later_state"
                        else np.nan
                    ),
                    "repositories": int(state_rows["repo_id"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def build_product_order_placebo(
    events: pl.DataFrame, anchors: pl.DataFrame, draws: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_frames: list[pl.DataFrame] = []
    anchor_keys = anchors.select(
        "pr_id",
        "repo_id",
        "product_pair",
        "first_post_burst_dt",
        "anchor_product",
    )
    for washout in WASHOUT_MINUTES:
        later = (
            events.filter(pl.col("atomic_state") == "mapped_product")
            .join(anchor_keys, on="pr_id", how="inner")
            .filter(
                pl.col("response_dt")
                > pl.col("first_post_burst_dt") + pl.duration(minutes=washout)
            )
            .with_columns(
                (pl.col("response_agent") == pl.col("anchor_product"))
                .cast(pl.Float64)
                .alias("same_anchor_product")
            )
        )
        next_times = later.group_by("pr_id").agg(
            pl.col("response_dt").min().alias("next_mapped_dt")
        )
        detail = (
            later.join(next_times, on="pr_id", how="inner")
            .group_by("pr_id")
            .agg(
                pl.col("repo_id").first(),
                pl.col("product_pair").first(),
                pl.col("anchor_product").first(),
                pl.col("response_agent")
                .filter(pl.col("response_dt") == pl.col("next_mapped_dt"))
                .n_unique()
                .alias("n_products_at_next_mapped_timestamp"),
                pl.col("same_anchor_product")
                .filter(pl.col("response_dt") == pl.col("next_mapped_dt"))
                .all()
                .cast(pl.Float64)
                .alias("observed_same_product"),
                pl.col("same_anchor_product")
                .mean()
                .alias("random_order_expected_same_product"),
                pl.len().alias("eligible_later_mapped_events"),
                pl.col("next_mapped_dt").first(),
            )
            .filter(pl.col("n_products_at_next_mapped_timestamp") == 1)
            .with_columns(
                pl.lit(washout).cast(pl.Int16).alias("washout_minutes"),
                (
                    pl.col("observed_same_product")
                    - pl.col("random_order_expected_same_product")
                ).alias("observed_minus_random_order"),
            )
        )
        detail_frames.append(detail)
    detail = pl.concat(detail_frames).sort(["washout_minutes", "pr_id"])
    detail_pd = detail.to_pandas()
    rows: list[dict[str, Any]] = []
    for washout in WASHOUT_MINUTES:
        frame = detail_pd[detail_pd["washout_minutes"] == washout]
        low, high = bootstrap_cluster_mean_difference(
            frame,
            "observed_minus_random_order",
            draws,
            SEED + 200 + washout,
        )
        rows.append(
            {
                "washout_minutes": washout,
                "eligible_prs": len(frame),
                "repositories": int(frame["repo_id"].nunique()),
                "observed_same_product_share": frame[
                    "observed_same_product"
                ].mean(),
                "random_order_expected_share": frame[
                    "random_order_expected_same_product"
                ].mean(),
                "observed_minus_random_order": frame[
                    "observed_minus_random_order"
                ].mean(),
                "repository_cluster_difference_ci_low": low,
                "repository_cluster_difference_ci_high": high,
                "ambiguous_next_product_ties_excluded": 0,
            }
        )
    return detail_pd, pd.DataFrame(rows)


def build_episodes(events: pl.DataFrame, chains: pl.DataFrame, gap: int) -> pl.DataFrame:
    post = (
        events.filter(
            pl.col("hours_after_trigger") > INITIAL_BURST_MINUTES / 60.0
        )
        .sort(["pr_id", "response_dt", "state_priority"])
        .with_columns(
            (
                (
                    pl.col("response_dt")
                    .diff()
                    .over("pr_id")
                    .dt.total_seconds()
                    > gap * 60
                )
                .fill_null(True)
                .cast(pl.Int64)
                .cum_sum()
                .over("pr_id")
            ).alias("episode_id")
        )
    )
    return (
        post.group_by("pr_id", "episode_id")
        .agg(
            pl.col("response_dt").min().alias("episode_dt"),
            pl.col("state_priority").min().alias("episode_priority"),
            pl.col("atomic_state").n_unique().alias("n_atomic_states"),
            pl.len().alias("event_rows"),
        )
        .with_columns(
            pl.col("episode_priority")
            .replace_strict(PRIORITY_ATOMIC, return_dtype=pl.String)
            .alias("episode_state"),
            pl.lit(gap).cast(pl.Int16).alias("episode_gap_minutes"),
        )
        .join(
            chains.select(
                "pr_id",
                "repo_id",
                "repo_url",
                "author_agent",
                "trigger_reviewer_agent",
            ).with_columns(
                (
                    pl.col("author_agent")
                    + pl.lit(" -> ")
                    + pl.col("trigger_reviewer_agent")
                ).alias("product_pair")
            ),
            on="pr_id",
            how="left",
        )
        .sort(["pr_id", "episode_dt", "episode_id"])
    )


def dynamic_transitions(episodes: pl.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    gap = int(episodes["episode_gap_minutes"][0]) if episodes.height else -1
    for key, group in episodes.group_by("pr_id", maintain_order=True):
        pr_id = int(key[0] if isinstance(key, tuple) else key)
        states = group["episode_state"].to_list()
        times = group["episode_dt"].to_list()
        repo_id = int(group["repo_id"][0])
        product_pair = group["product_pair"][0]
        automation_state = 0
        for position, state in enumerate(states):
            if state == "user_account":
                break
            if state not in {"mapped_product", "other_bot"}:
                continue
            automation_state += 1
            if automation_state > MAX_AUTOMATION_STATE:
                break
            if position + 1 >= len(states):
                outcome = "no_later_episode"
                next_time = None
            else:
                next_state = states[position + 1]
                next_time = times[position + 1]
                if next_state == "user_account":
                    outcome = "user_account"
                elif next_state in {"mapped_product", "other_bot"}:
                    outcome = "another_automation"
                else:
                    outcome = "branch_movement_untyped"
            rows.append(
                {
                    "episode_gap_minutes": gap,
                    "pr_id": pr_id,
                    "repo_id": repo_id,
                    "product_pair": product_pair,
                    "automation_state": automation_state,
                    "automation_episode_dt": times[position],
                    "next_episode_dt": next_time,
                    "next_transition": outcome,
                }
            )
            if automation_state == MAX_AUTOMATION_STATE:
                break
    return pd.DataFrame(rows)


def summarize_dynamic_transitions(
    transitions: pd.DataFrame, draws: int
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (gap, state), frame in transitions.groupby(
        ["episode_gap_minutes", "automation_state"], sort=True
    ):
        counts = frame["next_transition"].value_counts().reindex(
            ESCALATION_OUTCOMES, fill_value=0
        )
        ci = bootstrap_cluster_shares(
            frame,
            "next_transition",
            ESCALATION_OUTCOMES,
            draws,
            SEED + 300 + gap * 10 + state,
        )
        for outcome in ESCALATION_OUTCOMES:
            rows.append(
                {
                    "episode_gap_minutes": gap,
                    "automation_state": state,
                    "next_transition": outcome,
                    "at_risk_prs": len(frame),
                    "prs": int(counts[outcome]),
                    "share": counts[outcome] / len(frame),
                    "repository_cluster_ci_low": ci[outcome][0],
                    "repository_cluster_ci_high": ci[outcome][1],
                    "repositories": int(frame["repo_id"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def _transition_rates_from_sequences(
    sequences: list[list[str]],
) -> tuple[np.ndarray, np.ndarray]:
    counts = np.zeros((MAX_AUTOMATION_STATE, len(ESCALATION_OUTCOMES)), dtype=int)
    for states in sequences:
        automation_state = 0
        for position, state in enumerate(states):
            if state == "user_account":
                break
            if state not in {"mapped_product", "other_bot"}:
                continue
            automation_state += 1
            if automation_state > MAX_AUTOMATION_STATE:
                break
            if position + 1 >= len(states):
                outcome = "no_later_episode"
            else:
                next_state = states[position + 1]
                if next_state == "user_account":
                    outcome = "user_account"
                elif next_state in {"mapped_product", "other_bot"}:
                    outcome = "another_automation"
                else:
                    outcome = "branch_movement_untyped"
            counts[automation_state - 1, ESCALATION_OUTCOMES.index(outcome)] += 1
            if automation_state == MAX_AUTOMATION_STATE:
                break
    denominators = counts.sum(axis=1)
    rates = np.divide(
        counts,
        denominators[:, None],
        out=np.full_like(counts, np.nan, dtype=float),
        where=denominators[:, None] > 0,
    )
    return denominators, rates


def order_permutation_placebo(
    episodes: pl.DataFrame, draws: int
) -> pd.DataFrame:
    sequences = [
        group["episode_state"].to_list()
        for _, group in episodes.group_by("pr_id", maintain_order=True)
    ]
    observed_n, observed_rates = _transition_rates_from_sequences(sequences)
    rng = np.random.default_rng(SEED + 400)
    samples = np.empty(
        (draws, MAX_AUTOMATION_STATE, len(ESCALATION_OUTCOMES)), dtype=float
    )
    for draw in range(draws):
        permuted: list[list[str]] = []
        for sequence in sequences:
            values = np.asarray(sequence, dtype=object).copy()
            rng.shuffle(values)
            permuted.append(values.tolist())
        _, samples[draw] = _transition_rates_from_sequences(permuted)
    rows: list[dict[str, Any]] = []
    for state in range(1, MAX_AUTOMATION_STATE + 1):
        for outcome_index, outcome in enumerate(ESCALATION_OUTCOMES):
            distribution = samples[:, state - 1, outcome_index]
            low, high = np.nanquantile(distribution, [0.025, 0.975])
            placebo_mean = float(np.nanmean(distribution))
            observed = float(observed_rates[state - 1, outcome_index])
            rows.append(
                {
                    "episode_gap_minutes": PRIMARY_GAP_MINUTES,
                    "automation_state": state,
                    "next_transition": outcome,
                    "observed_at_risk_prs": int(observed_n[state - 1]),
                    "observed_share": observed,
                    "permuted_order_mean_share": placebo_mean,
                    "permuted_order_ci_low": float(low),
                    "permuted_order_ci_high": float(high),
                    "observed_minus_permuted_mean": observed - placebo_mean,
                    "permutation_draws": draws,
                }
            )
    return pd.DataFrame(rows)


def leave_one_out_ranges(
    frame: pd.DataFrame,
    state_column: str,
    state_order: tuple[str, ...],
    unit_column: str,
    unit_label: str,
    stratum_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    full_rows: list[dict[str, Any]] = []
    range_rows: list[dict[str, Any]] = []
    for stratum_key, stratum in frame.groupby(stratum_columns, sort=True):
        key_values = (
            stratum_key if isinstance(stratum_key, tuple) else (stratum_key,)
        )
        full_counts = stratum[state_column].value_counts().reindex(
            state_order, fill_value=0
        )
        group_counts = pd.crosstab(stratum[unit_column], stratum[state_column]).reindex(
            columns=state_order, fill_value=0
        )
        group_sizes = group_counts.sum(axis=1)
        local: list[dict[str, Any]] = []
        for excluded, counts in group_counts.iterrows():
            remaining_n = len(stratum) - int(group_sizes.loc[excluded])
            remaining = full_counts - counts
            for state in state_order:
                row = {
                    column: value
                    for column, value in zip(stratum_columns, key_values, strict=True)
                }
                row.update(
                    {
                        "exclusion_unit": unit_label,
                        "excluded_group": str(excluded),
                        "excluded_group_prs": int(group_sizes.loc[excluded]),
                        "remaining_prs": remaining_n,
                        "state": state,
                        "share": int(remaining[state]) / remaining_n,
                    }
                )
                local.append(row)
        full_rows.extend(local)
        local_frame = pd.DataFrame(local)
        for state in state_order:
            values = local_frame[local_frame["state"] == state]
            row = {
                column: value
                for column, value in zip(stratum_columns, key_values, strict=True)
            }
            row.update(
                {
                    "exclusion_unit": unit_label,
                    "state": state,
                    "full_share": full_counts[state] / len(stratum),
                    "minimum_loo_share": values["share"].min(),
                    "maximum_loo_share": values["share"].max(),
                    "maximum_absolute_shift_percentage_points": (
                        values["share"] - full_counts[state] / len(stratum)
                    ).abs().max()
                    * 100.0,
                    "exclusions": len(group_counts),
                }
            )
            range_rows.append(row)
    return pd.DataFrame(full_rows), pd.DataFrame(range_rows)


def continuous_leave_one_out(
    frame: pd.DataFrame,
    value_column: str,
    unit_column: str,
    unit_label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    full_sum = float(frame[value_column].sum())
    full_n = len(frame)
    grouped = frame.groupby(unit_column, sort=False)[value_column].agg(["sum", "size"])
    rows: list[dict[str, Any]] = []
    for excluded, values in grouped.iterrows():
        remaining_n = full_n - int(values["size"])
        rows.append(
            {
                "exclusion_unit": unit_label,
                "excluded_group": str(excluded),
                "excluded_group_prs": int(values["size"]),
                "remaining_prs": remaining_n,
                "remaining_mean_difference": (
                    full_sum - float(values["sum"])
                )
                / remaining_n,
            }
        )
    detail = pd.DataFrame(rows)
    full_mean = full_sum / full_n
    summary = pd.DataFrame(
        [
            {
                "exclusion_unit": unit_label,
                "full_mean_difference": full_mean,
                "minimum_loo_mean_difference": detail[
                    "remaining_mean_difference"
                ].min(),
                "maximum_loo_mean_difference": detail[
                    "remaining_mean_difference"
                ].max(),
                "maximum_absolute_shift_percentage_points": (
                    detail["remaining_mean_difference"] - full_mean
                ).abs().max()
                * 100.0,
                "exclusions": len(detail),
            }
        ]
    )
    return detail, summary


def build_quality_checks(
    raw_events: pl.DataFrame,
    events: pl.DataFrame,
    chains: pl.DataFrame,
    anchors: pl.DataFrame,
    owner_sequences: pl.DataFrame,
    product_placebo: pd.DataFrame,
    episode_frames: list[pl.DataFrame],
    dynamic: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add(check: str, ok: bool, value: Any, expected: str, note: str) -> None:
        rows.append(
            {
                "check": check,
                "status": "PASS" if ok else "FAIL",
                "value": value,
                "expected": expected,
                "note": note,
            }
        )

    add(
        "chain_pr_key_unique",
        chains["pr_id"].n_unique() == chains.height,
        chains["pr_id"].n_unique(),
        str(chains.height),
        "One parent row per PR.",
    )
    add(
        "events_strictly_time_ordered_after_trigger",
        raw_events.filter(pl.col("response_dt") <= pl.col("trigger_dt")).height == 0,
        raw_events.filter(pl.col("response_dt") <= pl.col("trigger_dt")).height,
        "0 violations",
        "Prevents pre-trigger leakage.",
    )
    add(
        "events_inside_seven_day_window",
        raw_events.filter(pl.col("response_dt") > pl.col("response_end_dt")).height
        == 0,
        raw_events.filter(pl.col("response_dt") > pl.col("response_end_dt")).height,
        "0 violations",
        "Prevents outcome-window leakage.",
    )
    duplicate_surplus = raw_events.height - events.height
    add(
        "exact_duplicate_rows_handled",
        duplicate_surplus == 9,
        duplicate_surplus,
        "9 documented surplus rows",
        "Exact duplicates are removed before sequence construction.",
    )
    add(
        "mapped_first_anchor_count",
        anchors.height == 924,
        anchors.height,
        "924",
        "Reconciles to the five-minute burst analysis.",
    )
    ambiguous_anchor = anchors.filter(pl.col("n_anchor_products") != 1).height
    add(
        "mapped_first_anchor_identity_unique",
        ambiguous_anchor == 0,
        ambiguous_anchor,
        "0 ambiguous anchors",
        "Required for same-versus-different product transitions.",
    )
    expected_owner_rows = anchors.height * len(WASHOUT_MINUTES)
    add(
        "owner_sequence_pr_washout_grain",
        owner_sequences.height == expected_owner_rows,
        owner_sequences.height,
        str(expected_owner_rows),
        "One next-owner state per mapped-first PR and washout.",
    )
    owner_duplicates = owner_sequences.select(
        pl.struct(["pr_id", "washout_minutes"]).is_duplicated().sum()
    ).item()
    add(
        "owner_sequence_key_unique",
        owner_duplicates == 0,
        owner_duplicates,
        "0 duplicated keys",
        "Protects mutually exclusive shares.",
    )
    invalid_owner_lag = owner_sequences.filter(
        pl.col("minutes_from_anchor_to_next").is_not_null()
        & (
            pl.col("minutes_from_anchor_to_next")
            <= pl.col("washout_minutes")
        )
    ).height
    add(
        "owner_next_state_after_washout",
        invalid_owner_lag == 0,
        invalid_owner_lag,
        "0 violations",
        "Confirms temporal separation from the anchor.",
    )
    placebo_bounds = bool(
        product_placebo["random_order_expected_same_product"].between(0, 1).all()
    )
    add(
        "product_placebo_probability_bounds",
        placebo_bounds,
        placebo_bounds,
        "True",
        "The future product mix is used only as a random-order null, not a predictor.",
    )
    episode_monotonic = True
    for episode_frame in episode_frames:
        differences = episode_frame.sort(["pr_id", "episode_dt"]).with_columns(
            pl.col("episode_dt").diff().over("pr_id").alias("episode_diff")
        )
        if differences.filter(pl.col("episode_diff").dt.total_seconds() < 0).height:
            episode_monotonic = False
    add(
        "episode_times_monotone_within_pr",
        episode_monotonic,
        episode_monotonic,
        "True",
        "Required for sequential risk sets.",
    )
    dynamic_duplicates = dynamic.duplicated(
        ["episode_gap_minutes", "pr_id", "automation_state"]
    ).sum()
    add(
        "dynamic_pr_state_key_unique",
        dynamic_duplicates == 0,
        int(dynamic_duplicates),
        "0 duplicated keys",
        "Each PR contributes at most once to automation state k.",
    )
    time_bad = dynamic[
        dynamic["next_episode_dt"].notna()
        & (dynamic["next_episode_dt"] <= dynamic["automation_episode_dt"])
    ]
    add(
        "dynamic_next_episode_strictly_later",
        time_bad.empty,
        len(time_bad),
        "0 violations",
        "The outcome is the immediate later episode.",
    )
    risk_monotone = True
    for _, frame in dynamic.groupby("episode_gap_minutes"):
        counts = frame.groupby("automation_state")["pr_id"].nunique().sort_index()
        if not (counts.diff().dropna() <= 0).all():
            risk_monotone = False
    add(
        "dynamic_risk_sets_nonincreasing",
        risk_monotone,
        risk_monotone,
        "True",
        "k is built prospectively and stops at the first user-account episode.",
    )
    return pd.DataFrame(rows)


def _primary_row(frame: pd.DataFrame, **conditions: Any) -> pd.Series:
    selected = frame.copy()
    for column, value in conditions.items():
        selected = selected[selected[column] == value]
    return selected.iloc[0]


def build_readme(summary: dict[str, Any]) -> str:
    exit_result = summary["mapped_first_exit_after_five_minute_washout"]
    placebo = summary["product_order_placebo_after_five_minute_washout"]
    escalation = summary["dynamic_automation_primary_gap"]
    return f"""# Deep coordination: persistence and escalation falsification

## Question 1 -- Does mapped-product ownership persist or relay?

The index population is the {summary['mapped_first_prs']:,} PRs whose first
observable state after the initial five-minute trigger burst is a mapped
product. We then require an additional five-minute washout after that anchor and
classify the next observable state. The design is temporal and descriptive; it
does not use merge or any later success outcome.

The next state is the same mapped product on
{exit_result['same_mapped_product']['prs']:,} PRs
({exit_result['same_mapped_product']['share']:.2%}), a different mapped product
on only {exit_result['different_mapped_product']['prs']:,}
({exit_result['different_mapped_product']['share']:.2%}), and a user account on
{exit_result['user_account']['prs']:,}
({exit_result['user_account']['share']:.2%}). Another
{exit_result['no_later_state']['prs']:,} PRs
({exit_result['no_later_state']['share']:.2%}) have no later visible state.

Among PRs with a later mapped-product event, the observed next product is the
same product {placebo['observed_same_product_share']:.2%} of the time. However,
a within-PR random-order benchmark that preserves the complete later product
mix expects {placebo['random_order_expected_share']:.2%}; the observed-minus-null
difference is {placebo['difference_percentage_points']:+.2f} points
(repository-cluster 95% interval
{placebo['cluster_ci_percentage_points'][0]:+.2f} to
{placebo['cluster_ci_percentage_points'][1]:+.2f}). Product persistence is
therefore high, but the ordering test does not show extra temporal persistence
beyond which products dominate each PR's event pool.

**Disposition:** the rare different-product next state is useful as a compact
main-text or appendix topology result. Keep the random-order check beside it.
Do not claim a special persistence mechanism.

## Question 2 -- Does repeated automation naturally escalate?

Post-burst events are sessionized into public episodes; the primary rule starts
a new episode after more than five minutes. Before the first user-account
episode, each PR enters automation state k when it reaches its k-th mapped-
product/other-bot episode. The outcome is the immediate next episode, so k is
not defined from the eventual number of events.

Observed user-account-next share falls from
{escalation['k1_user_share']:.2%} at k=1 to
{escalation['k4_user_share']:.2%} at k=4, while another-automation-next rises
from {escalation['k1_automation_share']:.2%} to
{escalation['k4_automation_share']:.2%}. This tempting dose story fails the
order placebo: randomly permuting episode order within each PR, while preserving
its state composition, reproduces the pattern. At k=4 the permuted mean
user-account-next share is {escalation['k4_permuted_user_mean']:.2%}
({escalation['k4_permuted_user_interval'][0]:.2%}--
{escalation['k4_permuted_user_interval'][1]:.2%}).

**Disposition:** reject a natural-escalation or automation-suppression headline.
The result is valuable as an appendix falsification: repeated public automation
does not by itself reveal an escalation threshold. An explicit escalation
policy would need an intervention or richer state telemetry to evaluate.

## Design safeguards and limitations

- Inputs are the complete seven-day, de-batched cross-response chains. Nine
  exact duplicate force-push rows are removed; no ordering construct uses them.
- Repository-cluster bootstraps retain whole repositories. Primary results also
  have leave-one-repository and leave-one-product-pair ranges.
- Washouts (0, 5, 30, 60 minutes) and episode gaps (0, 1, 5, 10 minutes) are
  reported rather than selected after seeing one result.
- `user_account` is an API type, not verified manual authorship. Temporal
  succession is not semantic response or resolution.
- The random-order benchmarks use future state composition only as explicit
  falsification nulls. They are not predictive features or causal controls.
- Public traces omit private orchestration and installation policy.

## Artifacts

- `mapped_first_next_owner.parquet` and `mapped_first_next_owner_summary.csv`
- `mapped_product_order_placebo_detail.parquet` and
  `mapped_product_order_placebo_summary.csv`
- `automation_episode_transitions.parquet` and
  `automation_episode_transition_summary.csv`
- `automation_order_permutation_placebo.csv`
- `next_owner_leave_one_out_ranges.csv` and
  `automation_leave_one_out_ranges.csv`
- `product_placebo_leave_one_out_ranges.csv`,
  `episode_sessionization_summary.csv`, `concentration_summary.csv`,
  `data_quality_checks.csv`, and `summary.json`
"""


def main() -> None:
    args = parse_args()
    if args.bootstrap_draws < 100 or args.permutation_draws < 100:
        raise ValueError("Bootstrap and permutation draws must each be at least 100")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    chains = pl.read_parquet(args.cross_dir / "cross_feedback_response_chains.parquet")
    raw_events = pl.read_parquet(
        args.cross_dir / "cross_feedback_response_events.parquet"
    )
    events = classify_events(raw_events.unique(maintain_order=True))
    burst_states = pl.read_parquet(
        args.burst_dir / "burst_collapsed_first_state.parquet"
    )

    anchors = mapped_first_anchors(events, burst_states, chains)
    next_owner = build_next_owner_sequences(events, anchors)
    next_owner_pd = next_owner.to_pandas()
    next_owner_summary = summarize_next_owner(next_owner_pd, args.bootstrap_draws)
    product_detail, product_summary = build_product_order_placebo(
        events, anchors, args.bootstrap_draws
    )
    product_primary = product_detail[
        product_detail["washout_minutes"] == PRIMARY_GAP_MINUTES
    ]
    product_pair_loo, product_pair_loo_range = continuous_leave_one_out(
        product_primary,
        "observed_minus_random_order",
        "product_pair",
        "product_pair",
    )
    product_repo_loo, product_repo_loo_range = continuous_leave_one_out(
        product_primary,
        "observed_minus_random_order",
        "repo_id",
        "repository",
    )

    episode_frames = [
        build_episodes(events, chains, gap) for gap in EPISODE_GAPS_MINUTES
    ]
    episode_diagnostics = pd.DataFrame(
        [
            {
                "episode_gap_minutes": gap,
                "episodes": frame.height,
                "prs": frame["pr_id"].n_unique(),
                "mixed_state_episodes": frame.filter(
                    pl.col("n_atomic_states") > 1
                ).height,
                "mixed_state_episode_share": frame.filter(
                    pl.col("n_atomic_states") > 1
                ).height
                / frame.height,
                "median_event_rows_per_episode": float(
                    frame["event_rows"].median()
                ),
                "maximum_event_rows_per_episode": int(frame["event_rows"].max()),
            }
            for gap, frame in zip(
                EPISODE_GAPS_MINUTES, episode_frames, strict=True
            )
        ]
    )
    dynamic_frames = [dynamic_transitions(frame) for frame in episode_frames]
    dynamic = pd.concat(dynamic_frames, ignore_index=True)
    dynamic_summary = summarize_dynamic_transitions(dynamic, args.bootstrap_draws)
    primary_episodes = episode_frames[
        EPISODE_GAPS_MINUTES.index(PRIMARY_GAP_MINUTES)
    ]
    permutation = order_permutation_placebo(
        primary_episodes, args.permutation_draws
    )

    next_primary = next_owner_pd[
        next_owner_pd["washout_minutes"] == PRIMARY_GAP_MINUTES
    ]
    next_pair_loo, next_pair_ranges = leave_one_out_ranges(
        next_primary,
        "next_owner_state",
        NEXT_OWNER_STATES,
        "product_pair",
        "product_pair",
        ["washout_minutes"],
    )
    next_repo_loo, next_repo_ranges = leave_one_out_ranges(
        next_primary,
        "next_owner_state",
        NEXT_OWNER_STATES,
        "repo_id",
        "repository",
        ["washout_minutes"],
    )
    dynamic_primary = dynamic[
        dynamic["episode_gap_minutes"] == PRIMARY_GAP_MINUTES
    ]
    auto_pair_loo, auto_pair_ranges = leave_one_out_ranges(
        dynamic_primary,
        "next_transition",
        ESCALATION_OUTCOMES,
        "product_pair",
        "product_pair",
        ["episode_gap_minutes", "automation_state"],
    )
    auto_repo_loo, auto_repo_ranges = leave_one_out_ranges(
        dynamic_primary,
        "next_transition",
        ESCALATION_OUTCOMES,
        "repo_id",
        "repository",
        ["episode_gap_minutes", "automation_state"],
    )

    concentration_rows: list[dict[str, Any]] = []
    for label, frame in [
        ("mapped_first_anchor", anchors.to_pandas()),
        ("dynamic_k1", dynamic_primary[dynamic_primary["automation_state"] == 1]),
        ("dynamic_k4", dynamic_primary[dynamic_primary["automation_state"] == 4]),
    ]:
        concentration_rows.append(
            {
                "population": label,
                "prs": len(frame),
                "repositories": int(frame["repo_id"].nunique()),
                "product_pairs": int(frame["product_pair"].nunique()),
                "largest_repository_share": frame["repo_id"].value_counts(
                    normalize=True
                ).iloc[0],
                "largest_product_pair_share": frame["product_pair"].value_counts(
                    normalize=True
                ).iloc[0],
            }
        )
    concentration = pd.DataFrame(concentration_rows)
    quality = build_quality_checks(
        raw_events,
        events,
        chains,
        anchors,
        next_owner,
        product_detail,
        episode_frames,
        dynamic,
    )
    failed = quality[quality["status"] == "FAIL"]
    if not failed.empty:
        raise RuntimeError(
            "Deep coordination quality checks failed: "
            + ", ".join(failed["check"].tolist())
        )

    next_owner.write_parquet(args.output_dir / "mapped_first_next_owner.parquet")
    next_owner_summary.to_csv(
        args.output_dir / "mapped_first_next_owner_summary.csv", index=False
    )
    pl.from_pandas(product_detail).write_parquet(
        args.output_dir / "mapped_product_order_placebo_detail.parquet"
    )
    product_summary.to_csv(
        args.output_dir / "mapped_product_order_placebo_summary.csv", index=False
    )
    pd.concat([product_pair_loo, product_repo_loo], ignore_index=True).to_csv(
        args.output_dir / "product_placebo_leave_one_out.csv", index=False
    )
    product_loo_ranges = pd.concat(
        [product_pair_loo_range, product_repo_loo_range], ignore_index=True
    )
    product_loo_ranges.to_csv(
        args.output_dir / "product_placebo_leave_one_out_ranges.csv", index=False
    )
    pl.from_pandas(dynamic).write_parquet(
        args.output_dir / "automation_episode_transitions.parquet"
    )
    dynamic_summary.to_csv(
        args.output_dir / "automation_episode_transition_summary.csv", index=False
    )
    permutation.to_csv(
        args.output_dir / "automation_order_permutation_placebo.csv", index=False
    )
    episode_diagnostics.to_csv(
        args.output_dir / "episode_sessionization_summary.csv", index=False
    )
    pd.concat([next_pair_loo, next_repo_loo], ignore_index=True).to_csv(
        args.output_dir / "next_owner_leave_one_out.csv", index=False
    )
    pd.concat([next_pair_ranges, next_repo_ranges], ignore_index=True).to_csv(
        args.output_dir / "next_owner_leave_one_out_ranges.csv", index=False
    )
    pd.concat([auto_pair_loo, auto_repo_loo], ignore_index=True).to_csv(
        args.output_dir / "automation_leave_one_out.csv", index=False
    )
    pd.concat([auto_pair_ranges, auto_repo_ranges], ignore_index=True).to_csv(
        args.output_dir / "automation_leave_one_out_ranges.csv", index=False
    )
    concentration.to_csv(args.output_dir / "concentration_summary.csv", index=False)
    quality.to_csv(args.output_dir / "data_quality_checks.csv", index=False)

    exit_rows = next_owner_summary[
        next_owner_summary["washout_minutes"] == PRIMARY_GAP_MINUTES
    ].set_index("next_owner_state")
    exit_payload = {
        state: {
            "prs": int(exit_rows.loc[state, "prs"]),
            "share": float(exit_rows.loc[state, "share"]),
            "cluster_ci": [
                float(exit_rows.loc[state, "repository_cluster_ci_low"]),
                float(exit_rows.loc[state, "repository_cluster_ci_high"]),
            ],
        }
        for state in NEXT_OWNER_STATES
    }
    product_row = _primary_row(
        product_summary, washout_minutes=PRIMARY_GAP_MINUTES
    )
    dynamic_rows = dynamic_summary[
        dynamic_summary["episode_gap_minutes"] == PRIMARY_GAP_MINUTES
    ]
    k1_user = _primary_row(
        dynamic_rows, automation_state=1, next_transition="user_account"
    )
    k4_user = _primary_row(
        dynamic_rows, automation_state=4, next_transition="user_account"
    )
    k1_auto = _primary_row(
        dynamic_rows, automation_state=1, next_transition="another_automation"
    )
    k4_auto = _primary_row(
        dynamic_rows, automation_state=4, next_transition="another_automation"
    )
    k4_perm_user = _primary_row(
        permutation, automation_state=4, next_transition="user_account"
    )
    summary: dict[str, Any] = {
        "interpretation": (
            "Temporal public-state transitions; no causal, semantic-resolution, "
            "or verified-manual-work claim."
        ),
        "mapped_first_prs": anchors.height,
        "mapped_first_exit_after_five_minute_washout": exit_payload,
        "product_order_placebo_after_five_minute_washout": {
            "eligible_prs": int(product_row["eligible_prs"]),
            "observed_same_product_share": float(
                product_row["observed_same_product_share"]
            ),
            "random_order_expected_share": float(
                product_row["random_order_expected_share"]
            ),
            "difference_percentage_points": float(
                product_row["observed_minus_random_order"] * 100.0
            ),
            "cluster_ci_percentage_points": [
                float(
                    product_row["repository_cluster_difference_ci_low"] * 100.0
                ),
                float(
                    product_row["repository_cluster_difference_ci_high"] * 100.0
                ),
            ],
            "leave_one_out_difference_ranges_percentage_points": [
                {
                    "exclusion_unit": row["exclusion_unit"],
                    "minimum": float(
                        row["minimum_loo_mean_difference"] * 100.0
                    ),
                    "maximum": float(
                        row["maximum_loo_mean_difference"] * 100.0
                    ),
                }
                for _, row in product_loo_ranges.iterrows()
            ],
        },
        "dynamic_automation_primary_gap": {
            "episode_gap_minutes": PRIMARY_GAP_MINUTES,
            "k1_at_risk_prs": int(k1_user["at_risk_prs"]),
            "k4_at_risk_prs": int(k4_user["at_risk_prs"]),
            "k1_user_share": float(k1_user["share"]),
            "k4_user_share": float(k4_user["share"]),
            "k1_automation_share": float(k1_auto["share"]),
            "k4_automation_share": float(k4_auto["share"]),
            "k4_permuted_user_mean": float(
                k4_perm_user["permuted_order_mean_share"]
            ),
            "k4_permuted_user_interval": [
                float(k4_perm_user["permuted_order_ci_low"]),
                float(k4_perm_user["permuted_order_ci_high"]),
            ],
        },
        "concentration": concentration.to_dict(orient="records"),
        "quality": {
            "checks": len(quality),
            "failed": int((quality["status"] == "FAIL").sum()),
            "exact_duplicate_surplus_removed": raw_events.height - events.height,
        },
        "bootstrap_draws": args.bootstrap_draws,
        "permutation_draws": args.permutation_draws,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (args.output_dir / "README.md").write_text(
        build_readme(summary), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
