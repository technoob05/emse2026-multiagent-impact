from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.formula.api as smf


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "response_ownership"


def add_owner(events: pl.DataFrame) -> pl.DataFrame:
    """Assign an observable owner without treating bot author accounts as humans."""
    response = pl.col("response_user").str.to_lowercase()
    author = pl.col("author_user").str.to_lowercase()
    return events.with_columns(
        pl.when(
            (pl.col("response_user_type").str.to_lowercase() == "user")
            & (response == author)
        )
        .then(pl.lit("author_human"))
        .when(pl.col("response_user_type").str.to_lowercase() == "user")
        .then(pl.lit("other_human"))
        .when(pl.col("response_agent") == pl.col("author_agent"))
        .then(pl.lit("author_agent"))
        .when(pl.col("response_agent") == pl.col("trigger_reviewer_agent"))
        .then(pl.lit("triggering_reviewer"))
        .when(pl.col("response_agent").is_not_null())
        .then(pl.lit("other_agent"))
        .when(pl.col("response_user_type").str.to_lowercase() == "bot")
        .then(pl.lit("other_bot"))
        .when(
            (pl.col("response_source") == "force_push")
            & (response == author)
        )
        .then(pl.lit("author_account_untyped"))
        .when(pl.col("response_source") == "force_push")
        .then(pl.lit("branch_actor_untyped"))
        .otherwise(pl.lit("unknown"))
        .alias("response_owner")
    )


def first_action_table(chains: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    first_time = events.group_by("pr_id").agg(
        pl.col("response_dt").min().alias("first_response_dt")
    )
    first_events = events.join(first_time, on="pr_id").filter(
        pl.col("response_dt") == pl.col("first_response_dt")
    )
    first = first_events.group_by("pr_id").agg(
        pl.col("response_source").n_unique().alias("n_first_channels"),
        pl.col("response_owner").n_unique().alias("n_first_owners"),
        pl.col("response_source").first().alias("first_channel_value"),
        pl.col("response_owner").first().alias("first_owner_value"),
        pl.col("hours_after_trigger").min().alias("first_action_hours"),
    ).with_columns(
        pl.when(pl.col("n_first_channels") == 1)
        .then(pl.col("first_channel_value"))
        .otherwise(pl.lit("simultaneous_channels"))
        .alias("first_channel"),
        pl.when(pl.col("n_first_owners") == 1)
        .then(pl.col("first_owner_value"))
        .otherwise(pl.lit("simultaneous_owners"))
        .alias("first_owner"),
    )
    return (
        chains.select("pr_id", "repo_id", "author_agent", "trigger_reviewer_agent", "trigger_source", "trigger_dt")
        .join(first, on="pr_id", how="left")
        .with_columns(
            pl.col("first_channel").fill_null("no_observed_action"),
            pl.col("first_owner").fill_null("no_observed_action"),
        )
    )


def route_table(events: pl.DataFrame, landmark: pl.DataFrame) -> pl.DataFrame:
    early = events.filter(pl.col("hours_after_trigger") <= 48).with_columns(
        pl.col("response_owner").is_in(["author_human", "other_human"]).alias("is_human"),
        pl.col("response_owner").is_in(
            ["author_agent", "triggering_reviewer", "other_agent", "other_bot"]
        ).alias("is_automation"),
        (pl.col("response_source") == "force_push").alias("is_movement"),
    )
    per_pr = early.group_by("pr_id").agg(
        pl.col("response_dt").filter(pl.col("is_human")).min().alias("first_human_dt"),
        pl.col("response_dt").filter(pl.col("is_automation")).min().alias("first_automation_dt"),
        pl.col("response_dt").filter(pl.col("is_movement")).min().alias("first_movement_dt"),
        pl.col("is_automation").sum().alias("automation_events_48h"),
        pl.col("is_human").sum().alias("human_events_48h"),
        pl.len().alias("all_events_48h"),
    ).with_columns(
        pl.when(
            pl.col("first_human_dt").is_not_null()
            & (
                pl.col("first_automation_dt").is_null()
                | (pl.col("first_human_dt") <= pl.col("first_automation_dt"))
            )
        )
        .then(pl.lit("human_first"))
        .when(
            pl.col("first_human_dt").is_not_null()
            & pl.col("first_automation_dt").is_not_null()
        )
        .then(pl.lit("automation_then_human"))
        .when(pl.col("first_automation_dt").is_not_null())
        .then(pl.lit("automation_no_human"))
        .when(pl.col("first_movement_dt").is_not_null())
        .then(pl.lit("movement_only"))
        .otherwise(pl.lit("other_activity"))
        .alias("ownership_route_48h")
    )
    return (
        landmark.join(per_pr, on="pr_id", how="left")
        .with_columns(
            pl.col("ownership_route_48h").fill_null("no_observed_action"),
            pl.col("automation_events_48h").fill_null(0),
            pl.col("human_events_48h").fill_null(0),
            pl.col("all_events_48h").fill_null(0),
        )
    )


def clustered_route_model(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["merged_from_48h_to_30d"] = frame["merged_from_48h_to_30d"].astype(int)
    frame["trigger_month"] = pd.to_datetime(frame["trigger_dt"], utc=True).dt.strftime("%Y-%m")
    route = "C(ownership_route_48h, Treatment('no_observed_action'))"
    formula = (
        "merged_from_48h_to_30d ~ " + route
        + " + C(author_agent) + C(trigger_reviewer_agent) + C(trigger_source) + C(trigger_month)"
    )
    model = smf.ols(formula, data=frame).fit(
        cov_type="cluster", cov_kwds={"groups": frame["repo_id"]}
    )
    intervals = model.conf_int()
    output = pd.DataFrame(
        {
            "term": model.params.index,
            "estimate": model.params.values,
            "ci_low": intervals[0].values,
            "ci_high": intervals[1].values,
            "p_value": model.pvalues.values,
        }
    )
    return output[output["term"].str.contains("ownership_route")].copy()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    chains = pl.read_parquet(INPUT / "cross_feedback_response_chains.parquet")
    events = add_owner(pl.read_parquet(INPUT / "cross_feedback_response_events.parquet"))
    landmark = pl.read_parquet(INPUT / "feedback_48h_landmark_cohort.parquet")

    first = first_action_table(chains, events)
    route = route_table(events, landmark)
    first_owner = first.group_by("first_owner").agg(
        pl.len().alias("prs"),
        pl.col("first_action_hours").median().alias("median_hours"),
    ).with_columns((pl.col("prs") / first.height).alias("share_all_prs")).sort("prs", descending=True)
    first_channel = first.group_by("first_channel").agg(
        pl.len().alias("prs"),
        pl.col("first_action_hours").median().alias("median_hours"),
    ).with_columns((pl.col("prs") / first.height).alias("share_all_prs")).sort("prs", descending=True)
    route_summary = route.group_by("ownership_route_48h").agg(
        pl.len().alias("prs"),
        pl.col("merged_from_48h_to_30d").mean().alias("later_merge_rate"),
        pl.col("automation_events_48h").median().alias("median_automation_events"),
        pl.col("human_events_48h").median().alias("median_human_events"),
    ).sort("prs", descending=True)

    first.write_parquet(OUTPUT / "first_response_ownership.parquet")
    route.write_parquet(OUTPUT / "ownership_route_48h.parquet")
    first_owner.write_csv(OUTPUT / "first_owner_summary.csv")
    first_channel.write_csv(OUTPUT / "first_channel_summary.csv")
    route_summary.write_csv(OUTPUT / "ownership_route_48h_summary.csv")
    clustered_route_model(route.to_pandas()).to_csv(
        OUTPUT / "ownership_route_clustered_model.csv", index=False
    )
    # Plain dictionaries avoid Unicode table-border failures on Windows cp1252.
    print("FIRST OWNER", first_owner.to_dicts())
    print("FIRST CHANNEL", first_channel.to_dicts())
    print("48H ROUTE", route_summary.to_dicts())


if __name__ == "__main__":
    main()
