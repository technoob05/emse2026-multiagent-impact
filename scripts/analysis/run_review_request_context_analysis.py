"""Profile review-request context before cross-product feedback triggers.

The timeline export records that a review was requested but may not preserve
the requested account.  This script therefore separates the observable fact
(`a request happened`) from the stronger, usually unobservable claim
(`the triggering reviewer was explicitly requested`).
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
INPUT = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "review_request_context"

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


def parse_utc(column: str, alias: str) -> pl.Expr:
    return (
        pl.col(column)
        .str.to_datetime("%Y-%m-%dT%H:%M:%SZ", time_zone="UTC", strict=False)
        .alias(alias)
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cohort = pl.read_parquet(INPUT / "cross_feedback_response_chains.parquet")
    created = (
        pl.read_parquet(DATA / "pull_request.parquet", columns=["id", "created_at"])
        .rename({"id": "pr_id"})
        .with_columns(parse_utc("created_at", "pr_created_dt"))
        .select("pr_id", "pr_created_dt")
    )
    requests = (
        pl.read_parquet(
            DATA / "pr_timeline.parquet",
            columns=[
                "pr_id", "event", "created_at", "actor", "assignee",
                "label", "message",
            ],
        )
        .filter(pl.col("event") == "review_requested")
        .with_columns(
            parse_utc("created_at", "request_dt"),
            pl.col("actor").str.to_lowercase().alias("actor_login"),
            pl.col("assignee").str.to_lowercase().alias("assignee_login"),
        )
        .with_columns(
            pl.col("actor_login")
            .replace_strict(AGENT_ACCOUNT_ALIASES, default=None)
            .alias("requester_agent"),
            pl.col("assignee_login")
            .replace_strict(AGENT_ACCOUNT_ALIASES, default=None)
            .alias("requested_agent"),
        )
        .join(cohort, on="pr_id", how="inner")
        .join(created, on="pr_id", how="left")
        .with_columns(
            pl.when(pl.col("requester_agent").is_not_null())
            .then(pl.lit("mapped_agent"))
            .when(
                pl.col("actor_login")
                == pl.col("author_user").str.to_lowercase()
            )
            .then(pl.lit("author_account"))
            .when(pl.col("actor_login").str.contains(r"\[bot\]$"))
            .then(pl.lit("other_bot"))
            .when(pl.col("actor_login").is_not_null())
            .then(pl.lit("other_user_like"))
            .otherwise(pl.lit("unknown"))
            .alias("requester_role")
        )
    )

    valid_pretrigger = requests.filter(
        pl.col("request_dt").is_not_null()
        & pl.col("pr_created_dt").is_not_null()
        & (pl.col("request_dt") >= pl.col("pr_created_dt"))
        & (pl.col("request_dt") <= pl.col("trigger_dt"))
    ).with_columns(
        (
            (pl.col("trigger_dt") - pl.col("request_dt")).dt.total_seconds()
            / 3600.0
        ).alias("hours_before_trigger")
    )
    last_request = (
        valid_pretrigger.sort(["pr_id", "request_dt"])
        .unique("pr_id", keep="last", maintain_order=True)
    )

    event_roles = (
        valid_pretrigger.group_by("requester_role")
        .agg(
            pl.len().alias("request_events"),
            pl.col("pr_id").n_unique().alias("prs"),
            pl.col("actor").is_not_null().sum().alias("events_with_actor"),
        )
        .sort("request_events", descending=True)
    )
    last_roles = (
        last_request.group_by("requester_role")
        .agg(
            pl.len().alias("prs"),
            pl.col("repo_id").n_unique().alias("repositories"),
            pl.col("hours_before_trigger").median().alias(
                "median_hours_before_trigger"
            ),
        )
        .sort("prs", descending=True)
    )
    source_summary = (
        last_request.group_by("trigger_source", "requester_role")
        .agg(pl.len().alias("prs"))
        .sort(["trigger_source", "prs"], descending=[False, True])
    )

    target_nonnull = valid_pretrigger.filter(
        pl.col("assignee_login").is_not_null()
    ).height
    target_exact = valid_pretrigger.filter(
        pl.col("requested_agent") == pl.col("trigger_reviewer_agent")
    ).height
    validation = {
        "cross_feedback_prs": cohort.height,
        "review_request_rows_in_cohort": requests.height,
        "review_request_prs_in_cohort": requests["pr_id"].n_unique(),
        "timestamped_rows": requests["request_dt"].is_not_null().sum(),
        "rows_before_pr_creation": requests.filter(
            pl.col("request_dt").is_not_null()
            & pl.col("pr_created_dt").is_not_null()
            & (pl.col("request_dt") < pl.col("pr_created_dt"))
        ).height,
        "valid_pretrigger_request_rows": valid_pretrigger.height,
        "prs_with_any_valid_pretrigger_request": last_request.height,
        "share_cross_feedback_prs_with_any_pretrigger_request": (
            last_request.height / cohort.height
        ),
        "actor_nonnull_rows": valid_pretrigger["actor"].is_not_null().sum(),
        "assignee_nonnull_rows": target_nonnull,
        "assignee_coverage": (
            target_nonnull / valid_pretrigger.height if valid_pretrigger.height else 0.0
        ),
        "exact_triggering_product_request_rows": target_exact,
        "exact_triggering_product_request_prs": valid_pretrigger.filter(
            pl.col("requested_agent") == pl.col("trigger_reviewer_agent")
        )["pr_id"].n_unique(),
        "message_nonnull_rows": valid_pretrigger["message"].is_not_null().sum(),
        "label_nonnull_rows": valid_pretrigger["label"].is_not_null().sum(),
        "inference_gate": (
            "Target identity is absent when assignee coverage is zero; infer only "
            "that some review was requested, not that the triggering product was requested."
        ),
    }

    last_request.select(
        "pr_id", "repo_id", "author_agent", "trigger_reviewer_agent",
        "trigger_source", "trigger_dt", "request_dt", "hours_before_trigger",
        "actor", "requester_role", "assignee", "requested_agent",
    ).write_parquet(OUTPUT / "last_pretrigger_review_request.parquet", compression="zstd")
    event_roles.write_csv(OUTPUT / "pretrigger_request_event_roles.csv")
    last_roles.write_csv(OUTPUT / "last_requester_role_summary.csv")
    source_summary.write_csv(OUTPUT / "last_requester_by_trigger_source.csv")
    (OUTPUT / "validation.json").write_text(
        json.dumps(validation, indent=2, default=str), encoding="utf-8"
    )

    print("VALIDATION", validation)
    print("LAST REQUESTER ROLES", last_roles.to_dicts())
    print("BY TRIGGER SOURCE", source_summary.to_dicts())


if __name__ == "__main__":
    main()
