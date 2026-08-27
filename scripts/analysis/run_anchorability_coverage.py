"""Quantify how much review activity the addressed edge can and cannot see.

The addressed edge fires only when a later inline review comment carries an
`in_reply_to_id` equal to the trigger comment's own identifier. Two other review
modalities in the release carry no reply anchor at all: review submission bodies
(`pr_reviews`) and PR-level issue comments (`pr_comments`). This script measures
the resulting coverage gap on the paper's own cross-product trigger cohort:

1. reviewer-side interaction volume by channel across the trigger PRs;
2. inside inline review comments, the root/reply split that bounds what an exact
   parent edge can ever attach to;
3. the channel composition of the cross-product review *triggers* themselves,
   which is what decides whether a PR is inside the estimation cohort at all;
4. a deliberately coarse, unanchored proxy for the out-of-scope channels.

Section 4 is reported to show the reader roughly how much activity sits outside
the precise measurement. It is not evidence of addressed feedback and is not
used for estimation anywhere in the paper.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import polars as pl


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import (  # noqa: E402
    INTERACTION_CUTOFF,
    classify_agent_account,
    parse_timestamp,
)
from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402

CHAIN = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "anchorability_coverage"

EXPECTED_INLINE_COHORT_ROWS = 1_067
PROXY_WINDOW_HOURS = 48

CHANNEL_ORDER = ["inline_review_comment", "submitted_review", "pr_comment"]
CHANNEL_LABELS = {
    "inline_review_comment": "Inline review comment (pr_review_comments)",
    "submitted_review": "Review submission body (pr_reviews)",
    "pr_comment": "PR-level comment (pr_comments)",
}
ANCHORABLE_CHANNELS = {"inline_review_comment"}


def load_trigger_cohort() -> pl.DataFrame:
    """The paper's cross-product 48-hour landmark cohort, all trigger channels."""
    cohort = pl.read_parquet(CHAIN / "feedback_48h_landmark_cohort.parquet").select(
        "pr_id",
        "repo_id",
        "author_user",
        "author_agent",
        "trigger_dt",
        "trigger_source",
        "trigger_event_id",
        "trigger_reviewer_agent",
        "feedback_relation",
        "closed_dt",
    )
    if cohort["pr_id"].n_unique() != cohort.height:
        raise AssertionError("Trigger cohort is not one row per PR.")
    if cohort.filter(pl.col("feedback_relation") != "cross_product").height:
        raise AssertionError("A same-product trigger entered the cross-product cohort.")
    inline_rows = cohort.filter(
        pl.col("trigger_source") == "inline_review_comment"
    ).height
    if inline_rows != EXPECTED_INLINE_COHORT_ROWS:
        raise AssertionError(
            f"Inline landmark cohort drift: {inline_rows} != {EXPECTED_INLINE_COHORT_ROWS}"
        )
    if set(cohort["trigger_source"].unique()) - set(CHANNEL_ORDER):
        raise AssertionError("Unexpected trigger channel in the cohort.")
    return cohort.sort("pr_id")


def load_channel_events(data_dir: Path, cohort: pl.DataFrame) -> pl.DataFrame:
    """Every event of the three review channels observed on the trigger PRs."""
    keys = cohort.select("pr_id", "author_user", "trigger_dt").lazy()
    reviews_raw = pl.scan_parquet(data_dir / "pr_reviews.parquet")
    review_key = reviews_raw.select("pull_request_review_id", "pr_id").unique(
        "pull_request_review_id"
    )
    reviews = reviews_raw.select(
        "pr_id",
        pl.col("id").alias("event_id"),
        "user",
        "user_type",
        pl.col("body"),
        pl.lit(None, dtype=pl.Int64).alias("in_reply_to_id"),
        parse_timestamp("submitted_at", "event_dt"),
        pl.lit("submitted_review").alias("channel"),
    )
    comments = pl.scan_parquet(data_dir / "pr_comments.parquet").select(
        "pr_id",
        pl.col("id").alias("event_id"),
        "user",
        "user_type",
        pl.col("body"),
        pl.lit(None, dtype=pl.Int64).alias("in_reply_to_id"),
        parse_timestamp("created_at", "event_dt"),
        pl.lit("pr_comment").alias("channel"),
    )
    inline = (
        pl.scan_parquet(data_dir / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            "pr_id",
            pl.col("id").alias("event_id"),
            "user",
            "user_type",
            pl.col("body"),
            pl.col("in_reply_to_id").cast(pl.Int64, strict=False),
            parse_timestamp("created_at", "event_dt"),
            pl.lit("inline_review_comment").alias("channel"),
        )
    )
    events = (
        pl.concat([reviews, comments, inline])
        .join(keys, on="pr_id", how="inner")
        .filter(
            pl.col("event_dt").is_not_null()
            & (pl.col("event_dt") <= pl.lit(INTERACTION_CUTOFF))
        )
        .with_columns(
            classify_agent_account("user"),
            (
                pl.col("user").str.to_lowercase()
                != pl.col("author_user").str.to_lowercase()
            ).alias("reviewer_side"),
            pl.col("body").fill_null("").str.strip_chars().str.len_chars().gt(0).alias(
                "has_body"
            ),
            pl.col("in_reply_to_id").is_null().alias("is_thread_root"),
        )
        .rename({"reviewer_agent": "actor_agent"})
        .collect()
    )
    if events.filter(~pl.col("channel").is_in(CHANNEL_ORDER)).height:
        raise AssertionError("Unexpected channel label in the event table.")
    return events


def channel_volume_table(events: pl.DataFrame, cohort: pl.DataFrame) -> pd.DataFrame:
    """Headline denominator: reviewer-side interactions by channel."""
    reviewer_side = events.filter(pl.col("reviewer_side"))
    total_events = reviewer_side.height
    total_with_body = int(reviewer_side["has_body"].sum())
    rows = []
    for channel in CHANNEL_ORDER:
        subset = reviewer_side.filter(pl.col("channel") == channel)
        with_body = subset.filter(pl.col("has_body"))
        rows.append(
            {
                "channel": channel,
                "channel_label": CHANNEL_LABELS[channel],
                "carries_reply_anchor": channel in ANCHORABLE_CHANNELS,
                "reviewer_side_events": subset.height,
                "share_of_reviewer_side_events": subset.height / total_events
                if total_events
                else float("nan"),
                "reviewer_side_events_with_body": with_body.height,
                "share_of_reviewer_side_events_with_body": with_body.height
                / total_with_body
                if total_with_body
                else float("nan"),
                "prs_touched": subset["pr_id"].n_unique(),
                "share_of_trigger_prs_touched": subset["pr_id"].n_unique()
                / cohort.height,
                "all_channel_events_including_author_side": events.filter(
                    pl.col("channel") == channel
                ).height,
            }
        )
    return pd.DataFrame(rows)


def inline_root_reply_table(events: pl.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """The anchoring ceiling inside the only channel that carries an anchor."""
    inline = events.filter(pl.col("channel") == "inline_review_comment")
    reviewer_side = inline.filter(pl.col("reviewer_side"))
    roots = inline.filter(pl.col("is_thread_root"))
    replies = inline.filter(~pl.col("is_thread_root"))
    unresolved_parents = replies.join(
        inline.select(pl.col("event_id").alias("in_reply_to_id")),
        on="in_reply_to_id",
        how="anti",
    ).height
    nested = replies.join(
        inline.filter(~pl.col("is_thread_root")).select(
            pl.col("event_id").alias("in_reply_to_id")
        ),
        on="in_reply_to_id",
        how="semi",
    ).height
    rows = [
        {
            "position": "thread_root",
            "can_receive_an_exact_parent_edge": True,
            "inline_events": roots.height,
            "share_of_inline_events": roots.height / inline.height,
            "reviewer_side_inline_events": roots.filter(
                pl.col("reviewer_side")
            ).height,
            "share_of_reviewer_side_inline_events": roots.filter(
                pl.col("reviewer_side")
            ).height
            / reviewer_side.height,
        },
        {
            "position": "reply_in_thread",
            "can_receive_an_exact_parent_edge": False,
            "inline_events": replies.height,
            "share_of_inline_events": replies.height / inline.height,
            "reviewer_side_inline_events": replies.filter(
                pl.col("reviewer_side")
            ).height,
            "share_of_reviewer_side_inline_events": replies.filter(
                pl.col("reviewer_side")
            ).height
            / reviewer_side.height,
        },
    ]
    checks = {
        "inline_events_on_trigger_prs": inline.height,
        "reviewer_side_inline_events_on_trigger_prs": reviewer_side.height,
        "replies_whose_parent_is_absent_from_the_release": unresolved_parents,
        "replies_pointing_at_another_reply": nested,
        "anchor_target_is_always_a_thread_root": nested == 0,
    }
    return pd.DataFrame(rows), checks


def trigger_channel_table(cohort: pl.DataFrame) -> pd.DataFrame:
    """Channel composition of the cross-product review triggers themselves."""
    rows = []
    for channel in CHANNEL_ORDER:
        subset = cohort.filter(pl.col("trigger_source") == channel)
        rows.append(
            {
                "trigger_channel": channel,
                "channel_label": CHANNEL_LABELS[channel],
                "in_scope_for_the_addressed_edge": channel in ANCHORABLE_CHANNELS,
                "trigger_prs": subset.height,
                "share_of_trigger_prs": subset.height / cohort.height,
                "repositories": subset["repo_id"].n_unique(),
                "ordered_product_pairs": subset.select(
                    pl.concat_str(
                        ["author_agent", "trigger_reviewer_agent"], separator=" -> "
                    )
                ).n_unique(),
            }
        )
    return pd.DataFrame(rows)


def coarse_unanchored_proxy(
    events: pl.DataFrame, cohort: pl.DataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    """COARSE proxy only: any later PR-level comment by a different account.

    This is not an addressed-feedback measurement. There is no anchor tying the
    later comment to the trigger, so it cannot separate a reply from unrelated
    concurrent chatter. It is reported to size the activity outside the precise
    measurement, and is used nowhere in estimation.
    """
    trigger_actor = events.select(
        pl.col("pr_id"),
        pl.col("event_id").alias("trigger_event_id"),
        pl.col("user").alias("trigger_user"),
    )
    labelled = cohort.join(
        trigger_actor, on=["pr_id", "trigger_event_id"], how="left"
    )
    if labelled["trigger_user"].null_count():
        raise AssertionError("A trigger event does not resolve to a channel event.")
    window = timedelta(hours=PROXY_WINDOW_HOURS)
    pr_comments = events.filter(pl.col("channel") == "pr_comment").select(
        "pr_id", "user", "event_dt"
    )
    followups = (
        labelled.select("pr_id", "trigger_dt", "trigger_user")
        .join(pr_comments, on="pr_id", how="inner")
        .filter(
            (pl.col("event_dt") > pl.col("trigger_dt"))
            & (pl.col("event_dt") <= pl.col("trigger_dt") + window)
            & (
                pl.col("user").str.to_lowercase()
                != pl.col("trigger_user").str.to_lowercase()
            )
        )
        .group_by("pr_id")
        .agg(pl.len().alias("proxy_pr_comment_events"))
    )
    flagged = labelled.join(followups, on="pr_id", how="left").with_columns(
        pl.col("proxy_pr_comment_events").fill_null(0)
    )
    rows = []
    for channel in CHANNEL_ORDER:
        subset = flagged.filter(pl.col("trigger_source") == channel)
        if not subset.height:
            continue
        hits = subset.filter(pl.col("proxy_pr_comment_events") > 0)
        rows.append(
            {
                "trigger_channel": channel,
                "channel_label": CHANNEL_LABELS[channel],
                "in_scope_for_the_addressed_edge": channel in ANCHORABLE_CHANNELS,
                "trigger_prs": subset.height,
                "prs_with_coarse_proxy_activity": hits.height,
                "coarse_proxy_rate": hits.height / subset.height,
                "median_proxy_events_when_present": float(
                    hits["proxy_pr_comment_events"].median()
                )
                if hits.height
                else float("nan"),
                "measurement_status": "COARSE UNANCHORED PROXY - NOT USED FOR ESTIMATION",
            }
        )
    out_of_scope = flagged.filter(
        ~pl.col("trigger_source").is_in(list(ANCHORABLE_CHANNELS))
    )
    out_hits = out_of_scope.filter(pl.col("proxy_pr_comment_events") > 0)
    in_scope = flagged.filter(
        pl.col("trigger_source").is_in(list(ANCHORABLE_CHANNELS))
    )
    checks = {
        "window_hours": PROXY_WINDOW_HOURS,
        "out_of_scope_trigger_prs": out_of_scope.height,
        "out_of_scope_prs_with_coarse_proxy_activity": out_hits.height,
        "out_of_scope_coarse_proxy_rate": out_hits.height / out_of_scope.height
        if out_of_scope.height
        else float("nan"),
        "in_scope_trigger_prs": in_scope.height,
        "in_scope_coarse_proxy_rate": in_scope.filter(
            pl.col("proxy_pr_comment_events") > 0
        ).height
        / in_scope.height
        if in_scope.height
        else float("nan"),
        "caveat": (
            "PR-level comments carry no reply anchor. This rate counts any later "
            "comment by a different account inside the window and cannot "
            "distinguish an answer to the review from unrelated concurrent "
            "activity. It is an upper bound on visible follow-up, not a measure "
            "of addressed feedback, and no estimate in the paper uses it."
        ),
    }
    return pd.DataFrame(rows), checks


def main() -> None:
    config = AnalysisConfig.from_paths(ROOT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    cohort = load_trigger_cohort()
    events = load_channel_events(config.data_dir, cohort)
    volume = channel_volume_table(events, cohort)
    inline_split, inline_checks = inline_root_reply_table(events)
    triggers = trigger_channel_table(cohort)
    proxy, proxy_checks = coarse_unanchored_proxy(events, cohort)

    volume.to_csv(OUTPUT / "channel_interaction_volume.csv", index=False)
    inline_split.to_csv(OUTPUT / "inline_root_reply_split.csv", index=False)
    triggers.to_csv(OUTPUT / "trigger_channel_composition.csv", index=False)
    proxy.to_csv(OUTPUT / "coarse_unanchored_proxy.csv", index=False)

    reviewer_side_events = int(events["reviewer_side"].sum())
    inline_row = volume.loc[volume["channel"] == "inline_review_comment"].iloc[0]
    inline_trigger_row = triggers.loc[
        triggers["trigger_channel"] == "inline_review_comment"
    ].iloc[0]
    root_row = inline_split.loc[inline_split["position"] == "thread_root"].iloc[0]

    summary = {
        "cohort": {
            "source_artifact": "outputs/cross_agent_review/feedback_48h_landmark_cohort.parquet",
            "definition": (
                "cross-product first agent review trigger, PR still open at the "
                "48-hour landmark, fixed 30-day outcome horizon"
            ),
            "trigger_prs": int(cohort.height),
            "repositories": int(cohort["repo_id"].n_unique()),
            "inline_trigger_prs": int(inline_trigger_row["trigger_prs"]),
            "observation_cutoff": INTERACTION_CUTOFF.isoformat(),
        },
        "reviewer_side_interaction_volume": {
            "total_reviewer_side_events": reviewer_side_events,
            "total_events_including_author_side": int(events.height),
            "inline_review_comment_events": int(inline_row["reviewer_side_events"]),
            "inline_share_of_reviewer_side_events": float(
                inline_row["share_of_reviewer_side_events"]
            ),
            "non_anchorable_events": reviewer_side_events
            - int(inline_row["reviewer_side_events"]),
            "non_anchorable_share_of_reviewer_side_events": 1.0
            - float(inline_row["share_of_reviewer_side_events"]),
            "by_channel": volume.to_dict(orient="records"),
        },
        "inline_anchoring_ceiling": {
            "thread_root_events": int(root_row["inline_events"]),
            "thread_root_share_of_inline_events": float(
                root_row["share_of_inline_events"]
            ),
            **inline_checks,
        },
        "trigger_channel_composition": {
            "inline_trigger_share": float(inline_trigger_row["share_of_trigger_prs"]),
            "out_of_scope_trigger_prs": int(
                cohort.filter(
                    ~pl.col("trigger_source").is_in(list(ANCHORABLE_CHANNELS))
                ).height
            ),
            "out_of_scope_trigger_share": 1.0
            - float(inline_trigger_row["share_of_trigger_prs"]),
            "by_channel": triggers.to_dict(orient="records"),
        },
        "coarse_unanchored_proxy": {
            **proxy_checks,
            "by_channel": proxy.to_dict(orient="records"),
        },
        "not_computable_from_the_release": [
            "Review submission bodies and PR-level comments carry no parent "
            "identifier, so no exact addressed edge can be constructed for them "
            "at any threshold. The out-of-scope share is a hard measurement "
            "boundary of the release, not a tuning choice.",
            "GitHub review threads are one level deep in this release, so a "
            "reply anchor always names a thread root; the reply-to-a-reply case "
            "does not exist here and cannot be studied.",
        ],
        "interpretation": (
            f"Across the {int(cohort.height)} cross-product trigger PRs, "
            f"{int(inline_row['reviewer_side_events'])} of "
            f"{reviewer_side_events} reviewer-side review interactions "
            f"({float(inline_row['share_of_reviewer_side_events']):.1%}) are "
            "inline review comments, the only modality carrying a reply anchor; "
            "the remaining "
            f"{reviewer_side_events - int(inline_row['reviewer_side_events'])} "
            "events are review submission bodies or PR-level comments and admit "
            "no exact parent edge. Within inline comments, "
            f"{float(root_row['share_of_inline_events']):.1%} are thread roots, "
            "which is the ceiling on what an exact edge can attach to. At the "
            "cohort level, "
            f"{int(inline_trigger_row['trigger_prs'])} of {int(cohort.height)} "
            f"({float(inline_trigger_row['share_of_trigger_prs']):.1%}) "
            "cross-product review triggers are inline and therefore in scope; "
            "the rest are structurally invisible to the addressed edge. The "
            "coarse PR-level proxy is descriptive only and supports no estimate."
        ),
        "scope": "descriptive coverage audit; no causal claim and no estimate",
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))
    print()
    print(volume.to_string(index=False))
    print()
    print(triggers.to_string(index=False))
    print()
    print(proxy.to_string(index=False))


if __name__ == "__main__":
    main()
