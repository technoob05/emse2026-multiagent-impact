from __future__ import annotations

import argparse
import bisect
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multiagent_impact.cross_agent_review import (  # noqa: E402
    build_agent_feedback_events,
    build_cross_feedback_response_chains,
    build_cross_feedback_response_events,
    build_landmark_cohort,
    INTERACTION_CUTOFF,
    load_pr_backbone,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explore direct cross-agent feedback")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT.parent
        / "Legacy"
        / "AI_Dev_Dataminning"
        / "AIDev-7.6M",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "cross_agent_review",
    )
    return parser.parse_args()


def nearest_pairs_without_replacement(
    frame: pd.DataFrame, strata: list[str]
) -> pd.DataFrame:
    """Pair cross and same-product rows within exact strata by nearest time."""
    pair_rows: list[dict[str, object]] = []
    grouped = {
        key: group.sort_values("trigger_dt")
        for key, group in frame.groupby(strata, dropna=False, sort=False)
    }
    relation_position = strata.index("feedback_relation")
    base_keys = {
        key[:relation_position] + key[relation_position + 1 :]
        for key in grouped
    }
    for base_key in base_keys:
        cross_key = (
            base_key[:relation_position]
            + ("cross_product",)
            + base_key[relation_position:]
        )
        same_key = (
            base_key[:relation_position]
            + ("same_product",)
            + base_key[relation_position:]
        )
        if cross_key not in grouped or same_key not in grouped:
            continue
        cross_group = grouped[cross_key]
        same_group = grouped[same_key]
        available = [
            (timestamp.value, int(row_id))
            for timestamp, row_id in zip(
                same_group["trigger_dt"], same_group["row_id"], strict=True
            )
        ]
        for _, cross_row in cross_group.iterrows():
            if not available:
                break
            target = cross_row["trigger_dt"].value
            position = bisect.bisect_left(available, (target, -1))
            candidates = [position] if position < len(available) else []
            if position:
                candidates.append(position - 1)
            chosen = min(candidates, key=lambda idx: abs(available[idx][0] - target))
            same_time, same_row_id = available.pop(chosen)
            pair_rows.append(
                {
                    "cross_row_id": int(cross_row["row_id"]),
                    "same_row_id": same_row_id,
                    "trigger_gap_hours": abs(same_time - target) / 3.6e12,
                }
            )
    keys = pd.DataFrame(pair_rows)
    if keys.empty:
        return keys
    cross_rows = frame.add_suffix("_cross")
    same_rows = frame.add_suffix("_same")
    return (
        keys.merge(
            cross_rows,
            left_on="cross_row_id",
            right_on="row_id_cross",
            how="inner",
        )
        .merge(
            same_rows,
            left_on="same_row_id",
            right_on="row_id_same",
            how="inner",
        )
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    events = build_agent_feedback_events(args.data_dir)
    prs = load_pr_backbone(args.data_dir)

    coverage = prs.select(pl.len().alias("aidev_pop_prs")).collect()
    event_prs = events.select(
        pl.col("pr_id").n_unique().alias("prs_with_recognized_agent_feedback"),
        pl.col("pr_id").filter(pl.col("cross_agent")).n_unique().alias(
            "prs_with_cross_agent_feedback"
        ),
        pl.len().alias("recognized_agent_feedback_events"),
        pl.col("cross_agent").sum().alias("cross_agent_feedback_events"),
    ).collect()
    coverage = pl.concat([coverage, event_prs], how="horizontal_extend")

    matrix = (
        events.filter(pl.col("cross_agent"))
        .group_by("author_agent", "reviewer_agent")
        .agg(
            pl.col("pr_id").n_unique().alias("prs"),
            pl.len().alias("events"),
            pl.col("hours_since_open").median().alias("median_hours_to_feedback"),
        )
        .sort("prs", descending=True)
        .collect()
    )
    forms = (
        events.group_by("cross_agent", "source", "state")
        .agg(pl.col("pr_id").n_unique().alias("prs"), pl.len().alias("events"))
        .sort(["cross_agent", "prs"], descending=[True, True])
        .collect()
    )
    first_cross = (
        events.filter(pl.col("cross_agent"))
        .group_by("pr_id")
        .agg(pl.col("hours_since_open").min().alias("first_cross_feedback_hours"))
        .select(
            pl.len().alias("prs"),
            pl.col("first_cross_feedback_hours").median().alias("median_hours"),
            pl.col("first_cross_feedback_hours").quantile(0.25).alias("p25_hours"),
            pl.col("first_cross_feedback_hours").quantile(0.75).alias("p75_hours"),
            (pl.col("first_cross_feedback_hours") <= 24).sum().alias("within_24h"),
        )
        .collect()
    )

    cohort = build_landmark_cohort(args.data_dir)
    landmark = (
        cohort.group_by("early_cross_agent_feedback")
        .agg(
            pl.len().alias("prs"),
            pl.col("merged_after_landmark_by_30d").mean().alias("merge_rate"),
        )
        .sort("early_cross_agent_feedback", descending=True)
        .collect()
    )
    response_chains = build_cross_feedback_response_chains(args.data_dir).collect()
    response_events = build_cross_feedback_response_events(args.data_dir).collect()
    same_response_chains = build_cross_feedback_response_chains(
        args.data_dir, cross_agent_only=False
    ).collect()
    response_summary = response_chains.select(
        pl.len().alias("cross_feedback_prs_with_7d_followup"),
        pl.col("any_observable_response").mean().alias("observable_response_rate"),
        (pl.col("direct_inline_replies") > 0).mean().alias("direct_reply_rate"),
        (pl.col("subsequent_reviews") > 0).mean().alias("subsequent_review_rate"),
        (pl.col("subsequent_pr_comments") > 0).mean().alias(
            "subsequent_pr_comment_rate"
        ),
        (pl.col("force_push_events") > 0).mean().alias("force_push_rate"),
        pl.col("merged_within_response_window").mean().alias("merge_within_7d_rate"),
    )
    relation_comparison = (
        pl.concat([response_chains, same_response_chains])
        .group_by("feedback_relation", "trigger_source")
        .agg(
            pl.len().alias("prs"),
            pl.col("any_observable_response").mean().alias("observable_response_rate"),
            (pl.col("direct_inline_replies") > 0).mean().alias("direct_reply_rate"),
            (pl.col("force_push_events") > 0).mean().alias("force_push_rate"),
            pl.col("merged_within_response_window").mean().alias("merge_within_7d_rate"),
        )
        .sort(["trigger_source", "feedback_relation"])
    )
    first_feedback = (
        pl.concat([response_chains, same_response_chains])
        .sort(["pr_id", "trigger_dt", "feedback_relation"])
        .unique("pr_id", keep="first", maintain_order=True)
        .with_columns(pl.col("trigger_dt").dt.strftime("%Y-%m").alias("trigger_month"))
    )
    matched = first_feedback.to_pandas()
    matched["row_id"] = np.arange(len(matched))
    pairs = nearest_pairs_without_replacement(
        matched,
        [
            "repo_url",
            "author_agent",
            "trigger_source",
            "feedback_relation",
            "trigger_month",
        ],
    )
    outcomes = {
        "observable_response": "any_observable_response",
        "direct_reply": "direct_inline_replies",
        "force_push": "force_push_events",
        "merge_within_7d": "merged_within_response_window",
    }
    rng = np.random.default_rng(20260825)
    matched_rows: list[dict[str, object]] = []
    for label, column in outcomes.items():
        left = pairs[f"{column}_cross"]
        right = pairs[f"{column}_same"]
        if column in {"direct_inline_replies", "force_push_events"}:
            left = left > 0
            right = right > 0
        differences = left.astype(float).to_numpy() - right.astype(float).to_numpy()
        if len(differences):
            draws = rng.choice(differences, size=(4000, len(differences)), replace=True).mean(axis=1)
            low, high = np.quantile(draws, [0.025, 0.975])
        else:
            low = high = np.nan
        matched_rows.append(
            {
                "outcome": label,
                "pairs": len(differences),
                "cross_rate": float(left.mean()) if len(left) else np.nan,
                "same_rate": float(right.mean()) if len(right) else np.nan,
                "paired_difference": float(differences.mean()) if len(differences) else np.nan,
                "bootstrap_ci_low": float(low),
                "bootstrap_ci_high": float(high),
            }
        )
    matched_summary = pd.DataFrame(matched_rows)
    response_roles = (
        response_events.group_by("response_source", "response_actor_role")
        .agg(
            pl.col("pr_id").n_unique().alias("prs"),
            pl.len().alias("events"),
            pl.col("hours_after_trigger").median().alias("median_hours_after_trigger"),
        )
        .sort(["response_source", "prs"], descending=[False, True])
    )
    early_response_flags = (
        response_events.filter(pl.col("hours_after_trigger") <= 48)
        .group_by("pr_id")
        .agg(
            (pl.col("response_source") == "force_push").any().alias("early_force_push"),
            (pl.col("response_user_type").str.to_lowercase() == "user")
            .any()
            .alias("early_human_response"),
            pl.col("response_agent").is_not_null().any().alias("early_agent_response"),
            pl.len().alias("early_response_events"),
        )
    )
    outcome_landmark = (
        response_chains.filter(
            pl.col("trigger_dt") <= pl.lit(INTERACTION_CUTOFF - timedelta(days=30))
        )
        .with_columns((pl.col("trigger_dt") + timedelta(hours=48)).alias("outcome_landmark_dt"))
        .filter(
            pl.col("closed_dt").is_null()
            | (pl.col("closed_dt") > pl.col("outcome_landmark_dt"))
        )
        .join(early_response_flags, on="pr_id", how="left")
        .with_columns(
            pl.col("early_force_push").fill_null(False),
            pl.col("early_human_response").fill_null(False),
            pl.col("early_agent_response").fill_null(False),
            pl.col("early_response_events").fill_null(0),
        )
        .with_columns(
            pl.when(pl.col("early_force_push"))
            .then(pl.lit("visible_code_movement"))
            .when(pl.col("early_human_response"))
            .then(pl.lit("human_mediated"))
            .when(pl.col("early_agent_response"))
            .then(pl.lit("agent_only_continuation"))
            .when(pl.col("early_response_events") > 0)
            .then(pl.lit("other_activity"))
            .otherwise(pl.lit("no_observed_response"))
            .alias("early_loop_shape"),
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > pl.col("outcome_landmark_dt"))
                & (pl.col("merged_dt") <= pl.col("trigger_dt") + timedelta(days=30))
            ).alias("merged_from_48h_to_30d"),
        )
    )
    outcome_landmark_summary = (
        outcome_landmark.group_by("early_loop_shape")
        .agg(
            pl.len().alias("prs"),
            pl.col("merged_from_48h_to_30d").mean().alias("later_merge_rate"),
        )
        .sort("prs", descending=True)
    )
    pair_responses = (
        response_chains.group_by(
            "author_agent", "trigger_reviewer_agent", "trigger_source"
        )
        .agg(
            pl.len().alias("prs"),
            pl.col("any_observable_response").mean().alias("response_rate"),
            (pl.col("direct_inline_replies") > 0).mean().alias("direct_reply_rate"),
            (pl.col("force_push_events") > 0).mean().alias("force_push_rate"),
            pl.col("merged_within_response_window").mean().alias("merge_within_7d_rate"),
        )
        .sort("prs", descending=True)
    )

    coverage.write_csv(args.output_dir / "coverage.csv")
    matrix.write_csv(args.output_dir / "cross_agent_matrix.csv")
    forms.write_csv(args.output_dir / "feedback_forms.csv")
    first_cross.write_csv(args.output_dir / "first_cross_feedback_timing.csv")
    landmark.write_csv(args.output_dir / "landmark_descriptive.csv")
    response_chains.write_parquet(args.output_dir / "cross_feedback_response_chains.parquet")
    response_events.write_parquet(args.output_dir / "cross_feedback_response_events.parquet")
    response_summary.write_csv(args.output_dir / "response_chain_summary.csv")
    relation_comparison.write_csv(args.output_dir / "relation_comparison.csv")
    first_feedback.write_parquet(args.output_dir / "first_agent_feedback_cohort.parquet")
    pairs.to_parquet(args.output_dir / "exact_stratum_matched_pairs.parquet", index=False)
    matched_summary.to_csv(args.output_dir / "matched_relation_summary.csv", index=False)
    response_roles.write_csv(args.output_dir / "response_actor_roles.csv")
    pair_responses.write_csv(args.output_dir / "pair_response_rates.csv")
    outcome_landmark.write_parquet(args.output_dir / "feedback_48h_landmark_cohort.parquet")
    outcome_landmark_summary.write_csv(args.output_dir / "feedback_48h_landmark_summary.csv")

    summary = {
        "coverage": coverage.to_dicts()[0],
        "first_cross_timing": first_cross.to_dicts()[0],
        "landmark": landmark.to_dicts(),
        "response_chains": response_summary.to_dicts()[0],
        "scope": "AIDev-pop repositories with more than 100 stars",
        "interpretation": "descriptive exploration; not a causal estimate",
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))
    print("\nTop cross-agent pairs written to cross_agent_matrix.csv")


if __name__ == "__main__":
    main()
