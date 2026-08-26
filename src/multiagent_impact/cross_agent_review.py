from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATASET_CUTOFF = datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc)
# PR creation stops on March 31, while rich interaction tables continue into
# April. Use a conservative common observation boundary for response windows.
INTERACTION_CUTOFF = datetime(2026, 4, 15, 0, 0, 0, tzinfo=timezone.utc)

# Exact account aliases only. Similar products (for example CodeRabbit or Gemini
# Code Assist) are kept outside the six AIDev author-agent brands.
AGENT_ACCOUNT_ALIASES = {
    "claude[bot]": "Claude_Code",
    "copilot": "Copilot",
    "copilot-swe-agent[bot]": "Copilot",
    "copilot-pull-request-reviewer[bot]": "Copilot",
    "cursor[bot]": "Cursor",
    "devin-ai-integration[bot]": "Devin",
    "google-labs-jules[bot]": "Google_Jules",
    "chatgpt-codex-connector[bot]": "OpenAI_Codex",
}


def classify_agent_account(column: str = "user") -> pl.Expr:
    """Map an exact GitHub account login to one of the six AIDev brands."""
    return (
        pl.col(column)
        .str.to_lowercase()
        .replace_strict(AGENT_ACCOUNT_ALIASES, default=None)
        .alias("reviewer_agent")
    )


def parse_timestamp(column: str, alias: str) -> pl.Expr:
    return (
        pl.col(column)
        .str.to_datetime(TIMESTAMP_FORMAT, time_zone="UTC", strict=False)
        .alias(alias)
    )


def load_pr_backbone(data_dir: Path) -> pl.LazyFrame:
    """Load the AIDev-pop PR backbone used by the rich interaction tables."""
    return (
        pl.scan_parquet(data_dir / "pull_request.parquet")
        .select(
            "id",
            "number",
            "repo_id",
            "repo_url",
            "agent",
            pl.col("user").alias("author_user"),
            "created_at",
            "closed_at",
            "merged_at",
        )
        .with_columns(
            parse_timestamp("created_at", "created_dt"),
            parse_timestamp("closed_at", "closed_dt"),
            parse_timestamp("merged_at", "merged_dt"),
        )
        .drop("created_at", "closed_at", "merged_at")
    )


def load_interactions(data_dir: Path) -> pl.LazyFrame:
    """Unify submitted reviews, PR comments, and inline review comments."""
    reviews_raw = pl.scan_parquet(data_dir / "pr_reviews.parquet")
    review_key = reviews_raw.select("pull_request_review_id", "pr_id").unique(
        "pull_request_review_id"
    )
    reviews = reviews_raw.select(
        "pr_id",
        pl.col("id").alias("event_id"),
        pl.col("pull_request_review_id").alias("review_id"),
        "user",
        "user_type",
        pl.col("state").cast(pl.String),
        parse_timestamp("submitted_at", "interaction_dt"),
        pl.lit("submitted_review").alias("source"),
    )
    comments = pl.scan_parquet(data_dir / "pr_comments.parquet").select(
        "pr_id",
        pl.col("id").alias("event_id"),
        pl.lit(None, dtype=pl.Int64).alias("review_id"),
        "user",
        "user_type",
        pl.lit(None, dtype=pl.String).alias("state"),
        parse_timestamp("created_at", "interaction_dt"),
        pl.lit("pr_comment").alias("source"),
    )
    inline = (
        pl.scan_parquet(data_dir / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            "pr_id",
            pl.col("id").alias("event_id"),
            pl.col("pull_request_review_id").alias("review_id"),
            "user",
            "user_type",
            pl.lit(None, dtype=pl.String).alias("state"),
            parse_timestamp("created_at", "interaction_dt"),
            pl.lit("inline_review_comment").alias("source"),
        )
    )
    return pl.concat([reviews, comments, inline]).with_columns(
        classify_agent_account("user")
    )


def build_agent_feedback_events(data_dir: Path) -> pl.LazyFrame:
    """Return time-valid feedback events made by a recognized AIDev agent."""
    prs = load_pr_backbone(data_dir).select(
        pl.col("id").alias("pr_id"),
        "repo_id",
        "repo_url",
        pl.col("agent").alias("author_agent"),
        "created_dt",
        "closed_dt",
        "merged_dt",
    )
    return (
        load_interactions(data_dir)
        .filter(pl.col("reviewer_agent").is_not_null())
        .join(prs, on="pr_id", how="inner")
        .filter(
            pl.col("interaction_dt").is_not_null()
            & (pl.col("interaction_dt") >= pl.col("created_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("interaction_dt") <= pl.col("closed_dt"))
            )
            & (pl.col("interaction_dt") <= pl.lit(INTERACTION_CUTOFF))
        )
        .with_columns(
            (pl.col("reviewer_agent") != pl.col("author_agent")).alias(
                "cross_agent"
            ),
            (
                (pl.col("interaction_dt") - pl.col("created_dt")).dt.total_seconds()
                / 3600.0
            ).alias("hours_since_open"),
        )
    )


def build_landmark_cohort(
    data_dir: Path,
    landmark_hours: int = 24,
    followup_days: int = 30,
) -> pl.LazyFrame:
    """Build a 24-hour risk-set cohort without immortal-time leakage.

    PRs must still be unresolved at the landmark. Exposure is based only on
    recognized agent feedback observed by that time. Outcome is merge after the
    landmark and no later than the fixed follow-up horizon from PR creation.
    """
    landmark_delta = timedelta(hours=landmark_hours)
    mature_cutoff = DATASET_CUTOFF - timedelta(days=followup_days)
    prs = (
        load_pr_backbone(data_dir)
        .filter(pl.col("created_dt") <= pl.lit(mature_cutoff))
        .with_columns(
            (pl.col("created_dt") + landmark_delta).alias("landmark_dt"),
            (pl.col("created_dt") + timedelta(days=followup_days)).alias(
                "followup_end_dt"
            ),
        )
        .filter(
            (pl.col("closed_dt").is_null() | (pl.col("closed_dt") > pl.col("landmark_dt")))
            & (
                pl.col("merged_dt").is_null()
                | (pl.col("merged_dt") > pl.col("landmark_dt"))
            )
        )
    )
    early = (
        build_agent_feedback_events(data_dir)
        .filter(pl.col("hours_since_open") <= landmark_hours)
        .group_by("pr_id")
        .agg(
            pl.col("cross_agent").any().alias("early_cross_agent_feedback"),
            (~pl.col("cross_agent")).any().alias("early_same_agent_feedback"),
            pl.col("reviewer_agent")
            .filter(pl.col("cross_agent"))
            .n_unique()
            .alias("n_cross_reviewer_agents"),
            pl.len().alias("n_early_agent_feedback_events"),
        )
    )
    return (
        prs.join(early, left_on="id", right_on="pr_id", how="left")
        .with_columns(
            pl.col("early_cross_agent_feedback").fill_null(False),
            pl.col("early_same_agent_feedback").fill_null(False),
            pl.col("n_cross_reviewer_agents").fill_null(0),
            pl.col("n_early_agent_feedback_events").fill_null(0),
        )
        .with_columns(
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > pl.col("landmark_dt"))
                & (pl.col("merged_dt") <= pl.col("followup_end_dt"))
            ).alias("merged_after_landmark_by_30d")
        )
    )


def build_cross_feedback_response_chains(
    data_dir: Path, response_days: int = 7, cross_agent_only: bool = True
) -> pl.LazyFrame:
    """Trace timestamped actions after first cross- or same-agent feedback.

    AIDev's ordinary ``committed`` timeline rows have no timestamps, so they
    cannot establish whether code changed before or after a review. This function
    instead uses only temporally ordered signals: direct inline replies,
    subsequent submitted reviews, later PR comments, and force-push events.
    """
    window = timedelta(days=response_days)
    parent_relation = (
        pl.col("parent_agent") != pl.col("author_agent")
        if cross_agent_only
        else pl.col("parent_agent") == pl.col("author_agent")
    )
    prs = load_pr_backbone(data_dir).select(
        pl.col("id").alias("pr_id"),
        "author_user",
        pl.col("agent").alias("author_agent"),
        "closed_dt",
        "merged_dt",
    )
    triggers = (
        build_agent_feedback_events(data_dir)
        .filter(pl.col("cross_agent") == cross_agent_only)
        .sort(["pr_id", "interaction_dt", "source"])
        .unique("pr_id", keep="first", maintain_order=True)
        .select(
            "pr_id",
            "repo_id",
            "repo_url",
            pl.col("interaction_dt").alias("trigger_dt"),
            pl.col("reviewer_agent").alias("trigger_reviewer_agent"),
            pl.col("source").alias("trigger_source"),
            pl.col("event_id").alias("trigger_event_id"),
            pl.col("review_id").alias("trigger_review_id"),
        )
        .join(prs, on="pr_id", how="inner")
        .filter(pl.col("trigger_dt") <= pl.lit(INTERACTION_CUTOFF - window))
        .with_columns((pl.col("trigger_dt") + window).alias("response_end_dt"))
    )

    review_key = (
        pl.scan_parquet(data_dir / "pr_reviews.parquet")
        .select("pull_request_review_id", "pr_id")
        .unique("pull_request_review_id")
    )
    inline = (
        pl.scan_parquet(data_dir / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            "id",
            "pr_id",
            "in_reply_to_id",
            "user",
            "user_type",
            parse_timestamp("created_at", "response_dt"),
        )
    )
    parent_ids = (
        inline.select(
            pl.col("id").alias("parent_id"),
            pl.col("pr_id").alias("parent_pr_id"),
            pl.col("user").alias("parent_user"),
            pl.col("response_dt").alias("parent_dt"),
        )
        .with_columns(classify_agent_account("parent_user"))
        .rename({"reviewer_agent": "parent_agent"})
    )
    direct_replies = (
        inline.filter(pl.col("in_reply_to_id").is_not_null())
        .with_columns(pl.col("in_reply_to_id").cast(pl.Int64).alias("parent_id"))
        .join(parent_ids, on="parent_id", how="inner")
        .filter(
            (pl.col("pr_id") == pl.col("parent_pr_id"))
            & pl.col("parent_agent").is_not_null()
        )
        .join(triggers, on="pr_id", how="inner")
        .filter(
            parent_relation
            & (pl.col("trigger_source") == "inline_review_comment")
            & (pl.col("parent_id") == pl.col("trigger_event_id"))
            & (pl.col("parent_dt") >= pl.col("trigger_dt"))
            & (pl.col("response_dt") > pl.col("parent_dt"))
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .group_by("pr_id")
        .agg(pl.len().alias("direct_inline_replies"))
    )

    subsequent_reviews = (
        pl.scan_parquet(data_dir / "pr_reviews.parquet")
        .select(
            "pr_id",
            pl.col("pull_request_review_id").alias("response_review_id"),
            parse_timestamp("submitted_at", "response_dt"),
        )
        .join(triggers, on="pr_id", how="inner")
        .filter(
            (pl.col("response_dt") > pl.col("trigger_dt"))
            & (
                pl.col("trigger_review_id").is_null()
                | (pl.col("response_review_id") != pl.col("trigger_review_id"))
            )
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .group_by("pr_id")
        .agg(pl.len().alias("subsequent_reviews"))
    )
    subsequent_comments = (
        pl.scan_parquet(data_dir / "pr_comments.parquet")
        .select("pr_id", parse_timestamp("created_at", "response_dt"))
        .join(triggers, on="pr_id", how="inner")
        .filter(
            (pl.col("response_dt") > pl.col("trigger_dt"))
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .group_by("pr_id")
        .agg(pl.len().alias("subsequent_pr_comments"))
    )
    force_pushes = (
        pl.scan_parquet(data_dir / "pr_timeline.parquet")
        .filter(pl.col("event") == "head_ref_force_pushed")
        .select("pr_id", parse_timestamp("created_at", "response_dt"))
        .join(triggers, on="pr_id", how="inner")
        .filter(
            (pl.col("response_dt") > pl.col("trigger_dt"))
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .group_by("pr_id")
        .agg(pl.len().alias("force_push_events"))
    )
    return (
        triggers.join(direct_replies, on="pr_id", how="left")
        .join(subsequent_reviews, on="pr_id", how="left")
        .join(subsequent_comments, on="pr_id", how="left")
        .join(force_pushes, on="pr_id", how="left")
        .with_columns(
            pl.col("direct_inline_replies").fill_null(0),
            pl.col("subsequent_reviews").fill_null(0),
            pl.col("subsequent_pr_comments").fill_null(0),
            pl.col("force_push_events").fill_null(0),
        )
        .with_columns(
            (
                (pl.col("direct_inline_replies") > 0)
                | (pl.col("subsequent_reviews") > 0)
                | (pl.col("subsequent_pr_comments") > 0)
                | (pl.col("force_push_events") > 0)
            ).alias("any_observable_response"),
            (
                pl.col("merged_dt").is_not_null()
                & (pl.col("merged_dt") > pl.col("trigger_dt"))
                & (pl.col("merged_dt") <= pl.col("response_end_dt"))
            ).alias("merged_within_response_window"),
            pl.lit("cross_product" if cross_agent_only else "same_product").alias(
                "feedback_relation"
            ),
        )
    )


def response_actor_role_expression() -> pl.Expr:
    """Classify who produced a timestamped post-feedback action."""
    responder = pl.col("response_user").str.to_lowercase()
    author = pl.col("author_user").str.to_lowercase()
    return (
        pl.when(
            (pl.col("response_user_type").str.to_lowercase() == "user")
            & (responder == author)
        )
        .then(pl.lit("author_account"))
        .when(pl.col("response_agent") == pl.col("author_agent"))
        .then(pl.lit("author_agent_brand"))
        .when(pl.col("response_agent") == pl.col("trigger_reviewer_agent"))
        .then(pl.lit("triggering_reviewer_brand"))
        .when(pl.col("response_agent").is_not_null())
        .then(pl.lit("other_agent_brand"))
        .when(pl.col("response_user_type").str.to_lowercase() == "bot")
        .then(pl.lit("other_bot"))
        .when(pl.col("response_user_type").str.to_lowercase() == "user")
        .then(pl.lit("other_human"))
        .otherwise(pl.lit("unknown_actor"))
        .alias("response_actor_role")
    )


def build_cross_feedback_response_events(
    data_dir: Path, response_days: int = 7, cross_agent_only: bool = True
) -> pl.LazyFrame:
    """Return actor-attributed actions after first cross- or same-agent feedback."""
    window = timedelta(days=response_days)
    parent_relation = (
        pl.col("parent_agent") != pl.col("author_agent")
        if cross_agent_only
        else pl.col("parent_agent") == pl.col("author_agent")
    )
    prs = load_pr_backbone(data_dir).select(
        pl.col("id").alias("pr_id"),
        "author_user",
        pl.col("agent").alias("author_agent"),
        "closed_dt",
    )
    triggers = (
        build_agent_feedback_events(data_dir)
        .filter(pl.col("cross_agent") == cross_agent_only)
        .sort(["pr_id", "interaction_dt", "source"])
        .unique("pr_id", keep="first", maintain_order=True)
        .select(
            "pr_id",
            "repo_id",
            "repo_url",
            pl.col("interaction_dt").alias("trigger_dt"),
            pl.col("reviewer_agent").alias("trigger_reviewer_agent"),
            pl.col("source").alias("trigger_source"),
            pl.col("event_id").alias("trigger_event_id"),
            pl.col("review_id").alias("trigger_review_id"),
        )
        .join(prs, on="pr_id", how="inner")
        .filter(pl.col("trigger_dt") <= pl.lit(INTERACTION_CUTOFF - window))
        .with_columns((pl.col("trigger_dt") + window).alias("response_end_dt"))
    )

    review_key = (
        pl.scan_parquet(data_dir / "pr_reviews.parquet")
        .select("pull_request_review_id", "pr_id")
        .unique("pull_request_review_id")
    )
    inline = (
        pl.scan_parquet(data_dir / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            "id",
            "pr_id",
            "pull_request_review_id",
            "in_reply_to_id",
            pl.col("user").alias("response_user"),
            pl.col("user_type").alias("response_user_type"),
            parse_timestamp("created_at", "response_dt"),
        )
    )
    parents = (
        inline.select(
            pl.col("id").alias("parent_id"),
            pl.col("pr_id").alias("parent_pr_id"),
            pl.col("response_user").alias("parent_user"),
            pl.col("response_dt").alias("parent_dt"),
        )
        .with_columns(classify_agent_account("parent_user"))
        .rename({"reviewer_agent": "parent_agent"})
    )
    direct_replies = (
        inline.filter(pl.col("in_reply_to_id").is_not_null())
        .with_columns(pl.col("in_reply_to_id").cast(pl.Int64).alias("parent_id"))
        .join(parents, on="parent_id", how="inner")
        .filter(
            (pl.col("pr_id") == pl.col("parent_pr_id"))
            & pl.col("parent_agent").is_not_null()
        )
        .join(triggers, on="pr_id", how="inner")
        .filter(
            parent_relation
            & (pl.col("trigger_source") == "inline_review_comment")
            & (pl.col("parent_id") == pl.col("trigger_event_id"))
            & (pl.col("parent_dt") >= pl.col("trigger_dt"))
            & (pl.col("response_dt") > pl.col("parent_dt"))
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .select(
            "pr_id",
            "author_user",
            "author_agent",
            "trigger_reviewer_agent",
            "trigger_source",
            "trigger_event_id",
            "trigger_review_id",
            "trigger_dt",
            "response_end_dt",
            "response_dt",
            "response_user",
            "response_user_type",
            pl.col("id").alias("response_event_id"),
            pl.col("pull_request_review_id").alias("response_review_id"),
            pl.lit("direct_inline_reply").alias("response_source"),
        )
    )
    later_reviews = (
        pl.scan_parquet(data_dir / "pr_reviews.parquet")
        .select(
            "pr_id",
            pl.col("id").alias("response_event_id"),
            pl.col("user").alias("response_user"),
            pl.col("user_type").alias("response_user_type"),
            pl.col("pull_request_review_id").alias("response_review_id"),
            parse_timestamp("submitted_at", "response_dt"),
        )
        .join(triggers, on="pr_id", how="inner")
        .filter(
            (pl.col("response_dt") > pl.col("trigger_dt"))
            & (
                pl.col("trigger_review_id").is_null()
                | (pl.col("response_review_id") != pl.col("trigger_review_id"))
            )
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .with_columns(pl.lit("subsequent_review").alias("response_source"))
    )
    later_comments = (
        pl.scan_parquet(data_dir / "pr_comments.parquet")
        .select(
            "pr_id",
            pl.col("id").alias("response_event_id"),
            pl.col("user").alias("response_user"),
            pl.col("user_type").alias("response_user_type"),
            pl.lit(None, dtype=pl.Int64).alias("response_review_id"),
            parse_timestamp("created_at", "response_dt"),
        )
        .join(triggers, on="pr_id", how="inner")
        .filter(
            (pl.col("response_dt") > pl.col("trigger_dt"))
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .with_columns(pl.lit("subsequent_pr_comment").alias("response_source"))
    )
    force_pushes = (
        pl.scan_parquet(data_dir / "pr_timeline.parquet")
        .filter(pl.col("event") == "head_ref_force_pushed")
        .select(
            "pr_id",
            pl.lit(None, dtype=pl.Int64).alias("response_event_id"),
            pl.col("actor").alias("response_user"),
            pl.lit(None, dtype=pl.String).alias("response_user_type"),
            pl.lit(None, dtype=pl.Int64).alias("response_review_id"),
            parse_timestamp("created_at", "response_dt"),
        )
        .join(triggers, on="pr_id", how="inner")
        .filter(
            (pl.col("response_dt") > pl.col("trigger_dt"))
            & (pl.col("response_dt") <= pl.col("response_end_dt"))
            & (
                pl.col("closed_dt").is_null()
                | (pl.col("response_dt") <= pl.col("closed_dt"))
            )
        )
        .with_columns(pl.lit("force_push").alias("response_source"))
    )
    common = [
        "pr_id",
        "author_user",
        "author_agent",
        "trigger_reviewer_agent",
        "trigger_source",
        "trigger_event_id",
        "trigger_review_id",
        "trigger_dt",
        "response_end_dt",
        "response_dt",
        "response_user",
        "response_user_type",
        "response_event_id",
        "response_review_id",
        "response_source",
    ]
    return (
        pl.concat(
            [
                direct_replies.select(common),
                later_reviews.select(common),
                later_comments.select(common),
                force_pushes.select(common),
            ]
        )
        .with_columns(classify_agent_account("response_user"))
        .rename({"reviewer_agent": "response_agent"})
        .with_columns(response_actor_role_expression())
        .with_columns(
            (
                (pl.col("response_dt") - pl.col("trigger_dt")).dt.total_seconds()
                / 3600.0
            ).alias("hours_after_trigger")
            ,pl.lit("cross_product" if cross_agent_only else "same_product").alias(
                "feedback_relation"
            )
        )
    )
