"""One real pull request, traced end to end, so Figure 1 is not a drawing.

Readers new to this kind of mining cannot check a rule they have only seen
stated. This script picks a single pull request from the landmark cohort that
exercises every rule at once --- a cross-product trigger, a sibling comment from
the same submitted review batch, at least one event inside the burst window, an
exact reply anchored to the trigger, and a merge after the hour-48 check point
--- and writes its timeline out as the figure's input.

Accounts are reported by role, not by login. The pull requests are public, but
naming the individuals who happened to reply adds nothing to the argument.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402

CHAIN = ROOT / "outputs" / "cross_agent_review"
OUTPUT = ROOT / "outputs" / "worked_example"
BURST_MINUTES = 5
LANDMARK_HOURS = 48


def role_for(login: str | None, author: str | None, trigger_login: str | None) -> str:
    if login is None:
        return "unknown account"
    if login == trigger_login:
        return "reviewing product"
    if login == author:
        return "authoring product"
    if login.endswith("[bot]"):
        return "other automation"
    return "a person"


def main() -> None:
    config = AnalysisConfig.from_paths(ROOT)
    data = config.data_dir

    chains = pl.read_parquet(CHAIN / "cross_feedback_response_chains.parquet").filter(
        (pl.col("trigger_source") == "inline_review_comment")
        & (pl.col("author_agent") != pl.col("trigger_reviewer_agent"))
        & (pl.col("direct_inline_replies") > 0)
        & pl.col("merged_dt").is_not_null()
    )

    review_key = (
        pl.read_parquet(data / "pr_reviews.parquet", columns=["pull_request_review_id", "pr_id"])
        .unique("pull_request_review_id")
    )
    comments = (
        pl.read_parquet(
            data / "pr_review_comments.parquet",
            columns=["id", "pull_request_review_id", "user", "created_at", "in_reply_to_id"],
        )
        .join(review_key, on="pull_request_review_id", how="inner")
        .rename({"user": "user_login"})
        .with_columns(
            pl.col("created_at")
            .str.to_datetime("%Y-%m-%dT%H:%M:%SZ", time_zone="UTC", strict=False)
            .alias("created_dt")
        )
    )

    candidates = chains.join(
        comments.group_by("pr_id").agg(pl.len().alias("comment_rows")),
        on="pr_id",
        how="inner",
    )

    chosen = None
    for row in candidates.sort("pr_id").iter_rows(named=True):
        events = comments.filter(pl.col("pr_id") == row["pr_id"]).sort("created_dt")
        trigger = events.filter(pl.col("id") == row["trigger_event_id"])
        if trigger.height != 1:
            continue
        trigger_row = trigger.row(0, named=True)
        trigger_dt = trigger_row["created_dt"]
        burst_end = trigger_dt + timedelta(minutes=BURST_MINUTES)
        landmark = trigger_dt + timedelta(hours=LANDMARK_HOURS)

        sibling = events.filter(
            (pl.col("pull_request_review_id") == trigger_row["pull_request_review_id"])
            & (pl.col("id") != trigger_row["id"])
        )
        burst = events.filter(
            (pl.col("created_dt") > trigger_dt) & (pl.col("created_dt") <= burst_end)
        )
        reply = events.filter(
            (pl.col("in_reply_to_id") == trigger_row["id"])
            & (pl.col("created_dt") > trigger_dt)
        )
        if not (sibling.height and burst.height and reply.height):
            continue
        # The three excluded or accepted events must be distinct, or the drawn
        # timeline shows one dot wearing two labels.
        reply_row = reply.sort("created_dt").row(0, named=True)
        burst_ids = set(burst["id"].to_list()) - {reply_row["id"]}
        if not burst_ids:
            continue
        burst = burst.filter(pl.col("id").is_in(list(burst_ids)))
        # The reply must land after the burst window, so each rule bites once and
        # the reader can follow the timeline left to right.
        if reply_row["created_dt"] <= burst_end:
            continue
        # The outcome must fall inside the 30-day horizon the paper actually uses.
        if not (landmark < row["merged_dt"] <= trigger_dt + timedelta(days=30)):
            continue
        chosen = (row, trigger_row, sibling, burst, reply, landmark)
        break

    if chosen is None:
        raise SystemExit("No pull request exercises every rule; relax a condition.")

    row, trigger_row, sibling, burst, reply, landmark = chosen
    trigger_dt = trigger_row["created_dt"]
    author = row["author_user"]
    trigger_login = trigger_row["user_login"]

    def minutes(when) -> float:
        return round((when - trigger_dt).total_seconds() / 60.0, 1)

    timeline = [
        {
            "order": 0,
            "minutes_after_trigger": 0.0,
            "actor_role": "reviewing product",
            "event": "inline review comment on one line of the change",
            "verdict": "this is the trigger",
            "rule": "trigger",
        }
    ]
    sibling_row = sibling.sort("created_dt").row(0, named=True)
    timeline.append(
        {
            "order": 1,
            "minutes_after_trigger": minutes(sibling_row["created_dt"]),
            "actor_role": role_for(sibling_row["user_login"], author, trigger_login),
            "event": "another inline comment from the same submitted review",
            "verdict": "not an answer: same review batch",
            "rule": "same-batch exclusion",
        }
    )
    burst_row = burst.sort("created_dt").row(0, named=True)
    timeline.append(
        {
            "order": 2,
            "minutes_after_trigger": minutes(burst_row["created_dt"]),
            "actor_role": role_for(burst_row["user_login"], author, trigger_login),
            "event": "inline comment inside the first five minutes",
            "verdict": "does not decide the next owner: inside the burst",
            "rule": "burst exclusion",
        }
    )
    reply_row = reply.sort("created_dt").row(0, named=True)
    timeline.append(
        {
            "order": 3,
            "minutes_after_trigger": minutes(reply_row["created_dt"]),
            "actor_role": role_for(reply_row["user_login"], author, trigger_login),
            "event": "reply whose stored reply target is the trigger comment",
            "verdict": "this is the addressed edge",
            "rule": "addressed edge",
        }
    )
    timeline.append(
        {
            "order": 4,
            "minutes_after_trigger": float(LANDMARK_HOURS * 60),
            "actor_role": "--",
            "event": "hour-48 check point; the PR is still open here",
            "verdict": "outcome counting starts now",
            "rule": "landmark",
        }
    )
    timeline.append(
        {
            "order": 5,
            "minutes_after_trigger": minutes(row["merged_dt"]),
            "actor_role": "--",
            "event": "the change is merged",
            "verdict": "counts as the outcome: after the check point",
            "rule": "outcome",
        }
    )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(timeline).write_csv(OUTPUT / "timeline.csv")
    (OUTPUT / "summary.json").write_text(
        json.dumps(
            {
                "repository": row["repo_url"],
                "author_product": row["author_agent"],
                "reviewing_product": row["trigger_reviewer_agent"],
                "burst_minutes": BURST_MINUTES,
                "landmark_hours": LANDMARK_HOURS,
                "reply_written_by": timeline[3]["actor_role"],
                "hours_trigger_to_reply": round(
                    timeline[3]["minutes_after_trigger"] / 60.0, 1
                ),
                "days_trigger_to_merge": round(
                    timeline[5]["minutes_after_trigger"] / 1440.0, 1
                ),
                "selection": (
                    "first pull request by identifier in the landmark cohort that "
                    "exercises every rule: cross-product inline trigger, a sibling "
                    "comment from the same submitted review, an event inside the burst "
                    "window, an exact reply to the trigger, and a merge after hour 48"
                ),
                "note": (
                    "accounts are reported by role rather than by login; the pull "
                    "request is public but naming individuals adds nothing"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Worked example: {row['repo_url']} ({len(timeline)} steps)")
    for step in timeline:
        print(
            f"  +{step['minutes_after_trigger']:>8.1f} min  "
            f"{step['actor_role']:<20} {step['verdict']}"
        )


if __name__ == "__main__":
    main()
