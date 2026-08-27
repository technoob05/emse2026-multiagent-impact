"""Quantify how much review activity the addressed edge can and cannot see.

The addressed edge fires only when a later inline review comment carries an
`in_reply_to_id` equal to the trigger comment's own identifier. Two other review
modalities in the release carry no reply anchor at all: review submission bodies
(`pr_reviews`) and PR-level issue comments (`pr_comments`). This script measures
the resulting coverage gap on TWO nested cohorts and labels every number with
the cohort it belongs to:

* PRIMARY - the complete cross-product trigger cohort
  (`outputs/cross_agent_review/cross_feedback_response_chains.parquet`,
  8,608 PRs). This is the study population the Method section describes, and
  the same denominator the coordination-topology funnel starts from.
* SECONDARY - the subset still open at the 48-hour landmark
  (`outputs/cross_agent_review/feedback_48h_landmark_cohort.parquet`,
  1,733 PRs). The RQ3 landmark result lives in this cohort, so its coverage
  figures are kept alongside, clearly labelled.

For each cohort the script reports:

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

FULL_COHORT_KEY = "full_cross_product_trigger_cohort"
LANDMARK_COHORT_KEY = "open_at_48h_landmark_cohort"

EXPECTED_FULL_COHORT_ROWS = 8_608
EXPECTED_LANDMARK_COHORT_ROWS = 1_733
EXPECTED_LANDMARK_INLINE_COHORT_ROWS = 1_067

PROXY_WINDOW_HOURS = 48

COHORT_SOURCES = {
    FULL_COHORT_KEY: "outputs/cross_agent_review/cross_feedback_response_chains.parquet",
    LANDMARK_COHORT_KEY: "outputs/cross_agent_review/feedback_48h_landmark_cohort.parquet",
}
COHORT_DEFINITIONS = {
    FULL_COHORT_KEY: (
        "complete cross-product trigger cohort: every PR whose first agent "
        "review feedback is cross-product and whose trigger leaves a full "
        "7-day response window before the observation cutoff; no landmark "
        "survival requirement"
    ),
    LANDMARK_COHORT_KEY: (
        "subset of the complete cross-product trigger cohort still open at the "
        "48-hour landmark, with a fixed 30-day outcome horizon; this is the "
        "RQ3 estimation cohort, not the study population"
    ),
}
COHORT_ROLES = {
    FULL_COHORT_KEY: "PRIMARY - study population reported in the Method section",
    LANDMARK_COHORT_KEY: "SECONDARY - RQ3 landmark estimation cohort",
}

COHORT_COLUMNS = [
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
]

CHANNEL_ORDER = ["inline_review_comment", "submitted_review", "pr_comment"]
CHANNEL_LABELS = {
    "inline_review_comment": "Inline review comment (pr_review_comments)",
    "submitted_review": "Review submission body (pr_reviews)",
    "pr_comment": "PR-level comment (pr_comments)",
}
ANCHORABLE_CHANNELS = {"inline_review_comment"}


def _validate_cohort(cohort: pl.DataFrame, name: str, expected_rows: int) -> pl.DataFrame:
    if cohort["pr_id"].n_unique() != cohort.height:
        raise AssertionError(f"{name}: trigger cohort is not one row per PR.")
    if cohort.filter(pl.col("feedback_relation") != "cross_product").height:
        raise AssertionError(
            f"{name}: a same-product trigger entered the cross-product cohort."
        )
    if cohort.height != expected_rows:
        raise AssertionError(
            f"{name}: cohort drift: {cohort.height} != {expected_rows}"
        )
    if set(cohort["trigger_source"].unique()) - set(CHANNEL_ORDER):
        raise AssertionError(f"{name}: unexpected trigger channel in the cohort.")
    return cohort.sort("pr_id")


def load_full_trigger_cohort() -> pl.DataFrame:
    """PRIMARY cohort: the complete cross-product trigger cohort (8,608 PRs).

    This is the artifact the coordination-topology funnel opens with, so the
    coverage audit and the funnel share one denominator by construction.
    """
    cohort = pl.read_parquet(
        CHAIN / "cross_feedback_response_chains.parquet"
    ).select(COHORT_COLUMNS)
    return _validate_cohort(cohort, FULL_COHORT_KEY, EXPECTED_FULL_COHORT_ROWS)


def load_landmark_trigger_cohort(full: pl.DataFrame) -> pl.DataFrame:
    """SECONDARY cohort: the subset still open at the 48-hour landmark."""
    cohort = pl.read_parquet(
        CHAIN / "feedback_48h_landmark_cohort.parquet"
    ).select(COHORT_COLUMNS)
    cohort = _validate_cohort(
        cohort, LANDMARK_COHORT_KEY, EXPECTED_LANDMARK_COHORT_ROWS
    )
    inline_rows = cohort.filter(
        pl.col("trigger_source") == "inline_review_comment"
    ).height
    if inline_rows != EXPECTED_LANDMARK_INLINE_COHORT_ROWS:
        raise AssertionError(
            f"Inline landmark cohort drift: {inline_rows} != "
            f"{EXPECTED_LANDMARK_INLINE_COHORT_ROWS}"
        )
    if cohort.join(full.select("pr_id"), on="pr_id", how="semi").height != cohort.height:
        raise AssertionError(
            "The landmark cohort is not a subset of the complete trigger cohort."
        )
    return cohort


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


def channel_volume_table(
    events: pl.DataFrame, cohort: pl.DataFrame, cohort_key: str
) -> pd.DataFrame:
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
                "cohort": cohort_key,
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


def inline_root_reply_table(
    events: pl.DataFrame, cohort_key: str
) -> tuple[pd.DataFrame, dict[str, object]]:
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
            "cohort": cohort_key,
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
            "cohort": cohort_key,
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


def trigger_channel_table(cohort: pl.DataFrame, cohort_key: str) -> pd.DataFrame:
    """Channel composition of the cross-product review triggers themselves."""
    rows = []
    for channel in CHANNEL_ORDER:
        subset = cohort.filter(pl.col("trigger_source") == channel)
        rows.append(
            {
                "cohort": cohort_key,
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
    events: pl.DataFrame, cohort: pl.DataFrame, cohort_key: str
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
                "cohort": cohort_key,
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


def analyse_cohort(
    data_dir: Path, cohort: pl.DataFrame, cohort_key: str
) -> dict[str, object]:
    """Every coverage quantity, computed on one cohort and labelled with it."""
    events = load_channel_events(data_dir, cohort)
    volume = channel_volume_table(events, cohort, cohort_key)
    inline_split, inline_checks = inline_root_reply_table(events, cohort_key)
    triggers = trigger_channel_table(cohort, cohort_key)
    proxy, proxy_checks = coarse_unanchored_proxy(events, cohort, cohort_key)

    reviewer_side_events = int(events["reviewer_side"].sum())
    inline_row = volume.loc[volume["channel"] == "inline_review_comment"].iloc[0]
    inline_trigger_row = triggers.loc[
        triggers["trigger_channel"] == "inline_review_comment"
    ].iloc[0]
    root_row = inline_split.loc[inline_split["position"] == "thread_root"].iloc[0]

    block = {
        "cohort_key": cohort_key,
        "cohort_role": COHORT_ROLES[cohort_key],
        "cohort_definition": {
            "source_artifact": COHORT_SOURCES[cohort_key],
            "definition": COHORT_DEFINITIONS[cohort_key],
            "trigger_prs_in_this_cohort": int(cohort.height),
            "repositories_in_this_cohort": int(cohort["repo_id"].n_unique()),
            "inline_trigger_prs_in_this_cohort": int(inline_trigger_row["trigger_prs"]),
            "observation_cutoff": INTERACTION_CUTOFF.isoformat(),
        },
        "reviewer_side_interaction_volume": {
            "total_reviewer_side_events_in_this_cohort": reviewer_side_events,
            "total_events_including_author_side_in_this_cohort": int(events.height),
            "inline_review_comment_events_in_this_cohort": int(
                inline_row["reviewer_side_events"]
            ),
            "inline_share_of_reviewer_side_events_in_this_cohort": float(
                inline_row["share_of_reviewer_side_events"]
            ),
            "non_anchorable_events_in_this_cohort": reviewer_side_events
            - int(inline_row["reviewer_side_events"]),
            "non_anchorable_share_of_reviewer_side_events_in_this_cohort": 1.0
            - float(inline_row["share_of_reviewer_side_events"]),
            "by_channel_in_this_cohort": volume.to_dict(orient="records"),
        },
        "inline_anchoring_ceiling": {
            "thread_root_events_in_this_cohort": int(root_row["inline_events"]),
            "thread_root_share_of_inline_events_in_this_cohort": float(
                root_row["share_of_inline_events"]
            ),
            "reply_in_thread_events_in_this_cohort": int(
                inline_split.loc[
                    inline_split["position"] == "reply_in_thread"
                ].iloc[0]["inline_events"]
            ),
            "reply_in_thread_share_of_inline_events_in_this_cohort": float(
                inline_split.loc[
                    inline_split["position"] == "reply_in_thread"
                ].iloc[0]["share_of_inline_events"]
            ),
            **{f"{k}_in_this_cohort": v for k, v in inline_checks.items()},
            "by_position_in_this_cohort": inline_split.to_dict(orient="records"),
        },
        "trigger_channel_composition": {
            "inline_trigger_prs_in_this_cohort": int(inline_trigger_row["trigger_prs"]),
            "inline_trigger_share_in_this_cohort": float(
                inline_trigger_row["share_of_trigger_prs"]
            ),
            "out_of_scope_trigger_prs_in_this_cohort": int(
                cohort.filter(
                    ~pl.col("trigger_source").is_in(list(ANCHORABLE_CHANNELS))
                ).height
            ),
            "out_of_scope_trigger_share_in_this_cohort": 1.0
            - float(inline_trigger_row["share_of_trigger_prs"]),
            "by_channel_in_this_cohort": triggers.to_dict(orient="records"),
        },
        "coarse_unanchored_proxy": {
            "measurement_status": (
                "DESCRIPTIVE UPPER BOUND - supports no estimate anywhere in the paper"
            ),
            **{
                k if k in {"window_hours", "caveat"} else f"{k}_in_this_cohort": v
                for k, v in proxy_checks.items()
            },
            "by_channel_in_this_cohort": proxy.to_dict(orient="records"),
        },
    }
    tables = {
        "volume": volume,
        "inline_split": inline_split,
        "triggers": triggers,
        "proxy": proxy,
    }
    return {"block": block, "tables": tables}


def _headline(block: dict[str, object]) -> dict[str, object]:
    volume = block["reviewer_side_interaction_volume"]
    ceiling = block["inline_anchoring_ceiling"]
    trigger = block["trigger_channel_composition"]
    return {
        "trigger_prs": block["cohort_definition"]["trigger_prs_in_this_cohort"],
        "reviewer_side_events": volume["total_reviewer_side_events_in_this_cohort"],
        "inline_reviewer_side_events": volume[
            "inline_review_comment_events_in_this_cohort"
        ],
        "inline_share_of_reviewer_side_events": volume[
            "inline_share_of_reviewer_side_events_in_this_cohort"
        ],
        "non_anchorable_share_of_reviewer_side_events": volume[
            "non_anchorable_share_of_reviewer_side_events_in_this_cohort"
        ],
        "thread_root_share_of_inline_events": ceiling[
            "thread_root_share_of_inline_events_in_this_cohort"
        ],
        "inline_trigger_prs": trigger["inline_trigger_prs_in_this_cohort"],
        "inline_trigger_share": trigger["inline_trigger_share_in_this_cohort"],
        "out_of_scope_trigger_share": trigger[
            "out_of_scope_trigger_share_in_this_cohort"
        ],
    }


HEADLINE_ROWS = [
    ("Trigger PRs", "trigger_prs", "count"),
    ("Reviewer-side review interactions", "reviewer_side_events", "count"),
    ("  of which inline (anchorable)", "inline_reviewer_side_events", "count"),
    ("Inline share of reviewer-side events", "inline_share_of_reviewer_side_events", "pct"),
    (
        "Non-anchorable share of reviewer-side events",
        "non_anchorable_share_of_reviewer_side_events",
        "pct",
    ),
    ("Thread-root share of inline events", "thread_root_share_of_inline_events", "pct"),
    ("Inline (in-scope) trigger PRs", "inline_trigger_prs", "count"),
    ("Inline share of triggers (in scope)", "inline_trigger_share", "pct"),
    ("Out-of-scope trigger share", "out_of_scope_trigger_share", "pct"),
]


def main() -> None:
    config = AnalysisConfig.from_paths(ROOT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    full_cohort = load_full_trigger_cohort()
    landmark_cohort = load_landmark_trigger_cohort(full_cohort)

    full = analyse_cohort(config.data_dir, full_cohort, FULL_COHORT_KEY)
    landmark = analyse_cohort(config.data_dir, landmark_cohort, LANDMARK_COHORT_KEY)

    for filename, table_key in (
        ("channel_interaction_volume.csv", "volume"),
        ("inline_root_reply_split.csv", "inline_split"),
        ("trigger_channel_composition.csv", "triggers"),
        ("coarse_unanchored_proxy.csv", "proxy"),
    ):
        pd.concat(
            [full["tables"][table_key], landmark["tables"][table_key]],
            ignore_index=True,
        ).to_csv(OUTPUT / filename, index=False)

    full_block = full["block"]
    landmark_block = landmark["block"]
    full_head = _headline(full_block)
    landmark_head = _headline(landmark_block)

    comparison = pd.DataFrame(
        [
            {
                "quantity": label,
                "full_cross_product_trigger_cohort": full_head[key],
                "open_at_48h_landmark_cohort": landmark_head[key],
                "landmark_minus_full": landmark_head[key] - full_head[key],
                "unit": unit,
            }
            for label, key, unit in HEADLINE_ROWS
        ]
    )
    comparison.to_csv(OUTPUT / "cohort_headline_comparison.csv", index=False)

    summary = {
        "primary_cohort": FULL_COHORT_KEY,
        "secondary_cohort": LANDMARK_COHORT_KEY,
        "cohort_relationship": (
            f"The {LANDMARK_COHORT_KEY} is a strict subset of the "
            f"{FULL_COHORT_KEY}: "
            f"{landmark_head['trigger_prs']} of {full_head['trigger_prs']} "
            "cross-product trigger PRs were still open at the 48-hour landmark. "
            "Every figure below is tagged with the cohort it describes; no key "
            "is shared between the two."
        ),
        FULL_COHORT_KEY: full_block,
        LANDMARK_COHORT_KEY: landmark_block,
        "headline_comparison": {
            FULL_COHORT_KEY: full_head,
            LANDMARK_COHORT_KEY: landmark_head,
            "table": comparison.to_dict(orient="records"),
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
            "On the complete cross-product trigger cohort "
            f"({full_head['trigger_prs']} PRs, "
            "outputs/cross_agent_review/cross_feedback_response_chains.parquet), "
            f"{full_head['inline_reviewer_side_events']} of "
            f"{full_head['reviewer_side_events']} reviewer-side review "
            f"interactions "
            f"({full_head['inline_share_of_reviewer_side_events']:.1%}) are "
            "inline review comments, the only modality carrying a reply anchor; "
            "the remaining "
            f"{full_head['reviewer_side_events'] - full_head['inline_reviewer_side_events']} "
            "events are review submission bodies or PR-level comments and admit "
            "no exact parent edge. Within inline comments, "
            f"{full_head['thread_root_share_of_inline_events']:.1%} are thread "
            "roots, which is the ceiling on what an exact edge can attach to. "
            "At the cohort level, "
            f"{full_head['inline_trigger_prs']} of {full_head['trigger_prs']} "
            f"({full_head['inline_trigger_share']:.1%}) cross-product review "
            "triggers are inline and therefore in scope; the remaining "
            f"{full_head['out_of_scope_trigger_share']:.1%} are structurally "
            "invisible to the addressed edge. Restricting to the RQ3 estimation "
            "cohort of PRs still open at the 48-hour landmark "
            f"({landmark_head['trigger_prs']} PRs), the same quantities are "
            f"{landmark_head['inline_share_of_reviewer_side_events']:.1%} inline "
            "reviewer-side events, "
            f"{landmark_head['thread_root_share_of_inline_events']:.1%} thread "
            f"roots, and {landmark_head['inline_trigger_share']:.1%} inline "
            "triggers in scope; that cohort is more inline-heavy and must not be "
            "quoted as a property of the study population. The coarse PR-level "
            "proxy is a descriptive upper bound in both cohorts and supports no "
            "estimate."
        ),
        "scope": "descriptive coverage audit; no causal claim and no estimate",
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(json.dumps(summary, indent=2, default=str))
    print()
    print("HEADLINE COMPARISON (full cross-product cohort vs 48h-landmark subset)")
    print(comparison.to_string(index=False))
    for name, payload in (
        (FULL_COHORT_KEY, full),
        (LANDMARK_COHORT_KEY, landmark),
    ):
        print()
        print(f"=== {name} ===")
        print(payload["tables"]["volume"].to_string(index=False))
        print()
        print(payload["tables"]["triggers"].to_string(index=False))
        print()
        print(payload["tables"]["proxy"].to_string(index=False))


if __name__ == "__main__":
    main()
