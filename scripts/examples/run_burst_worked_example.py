"""One real burst, so the five-minute rule stops being an assertion.

RQ1's whole design rests on setting aside a rapid burst of automated events
before asking who owns the next action. The article states that rule, sweeps it
over five windows, and reports that the conclusion survives all of them --- but
a reader has never actually seen a burst. This script picks one real pull
request whose first minutes contain a burst and writes its event timeline out
as a figure input, exactly the way ``run_worked_example.py`` does for Figure 1.

The pull request is chosen by a rule fixed here, not by eye:

1. Setting the burst aside must *change the answer* on this pull request. At a
   zero-minute window the first later owner is a mapped product; at the
   five-minute window it is a user account. Both readings are taken from
   ``outputs/burst_topology/burst_collapsed_first_state.parquet``, the same
   artifact the article's Panel B is drawn from, so the example cannot drift
   away from the analysis it illustrates.
2. The burst must be a burst: at least four events strictly inside the first
   five minutes, and not one of them from a user account. A "burst" containing
   a person is a conversation, and would teach the reader the wrong thing.
3. Among the pull requests that satisfy both, take the one with the most burst
   events, breaking ties on the pull request identifier. Most burst events is
   the clearest instance rather than the most flattering one: the rule
   discards more evidence here than on almost any other pull request in the
   cohort, which is the cost of the convention, not a hidden benefit of it.

Accounts are reported by role and by product, never by login, which is the
convention Figure 1 already uses. The pull request is public; naming the
individual who happened to act adds nothing to the argument.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
CHAIN = ROOT / "outputs" / "cross_agent_review"
BURST = ROOT / "outputs" / "burst_topology"
OUTPUT = ROOT / "outputs" / "worked_example_burst"

BURST_MINUTES = 5
NAIVE_MINUTES = 0
MIN_BURST_EVENTS = 4

# The four owner kinds the article's Panel B uses, so the example and the bars
# above it speak the same vocabulary.
STATE_LABEL = {
    "user_account": "user account",
    "mapped_product": "mapped product",
    "other_bot": "other bot",
    "branch_movement_untyped": "branch movement",
}


def owner_kind(user_type: str | None, agent: str | None) -> str:
    """The article's own precedence: a user account outranks a product label."""
    if (user_type or "").lower() == "user":
        return "user_account"
    if agent is not None:
        return "mapped_product"
    if (user_type or "").lower() == "bot":
        return "other_bot"
    return "branch_movement_untyped"


CHANNEL = {
    "subsequent_review": "a new review round",
    "subsequent_pr_comment": "a pull request comment",
    "direct_inline_reply": "a reply on the trigger's thread",
    "force_push": "the branch is rewritten",
}


def main() -> None:
    events = pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet")
    chains = pl.read_parquet(CHAIN / "cross_feedback_response_chains.parquet")
    states = pl.read_parquet(BURST / "burst_collapsed_first_state.parquet")

    def state_at(threshold: int) -> pl.DataFrame:
        subset = states.filter(pl.col("burst_threshold_minutes") == threshold)
        if subset.height == 0:
            raise SystemExit(
                f"burst_collapsed_first_state.parquet carries no {threshold}-minute "
                "window; the example cannot be tied back to the analysis"
            )
        return subset.select(
            "pr_id",
            pl.col("first_post_burst_state").alias(f"state_{threshold}"),
            pl.col("minutes_from_trigger").alias(f"minutes_{threshold}"),
        )

    flip = (
        state_at(NAIVE_MINUTES)
        .join(state_at(BURST_MINUTES), on="pr_id", how="inner")
        .filter(
            (pl.col(f"state_{NAIVE_MINUTES}") == "mapped_product")
            & (pl.col(f"state_{BURST_MINUTES}") == "user_account")
        )
    )

    burst_events = events.filter(
        pl.col("hours_after_trigger") <= BURST_MINUTES / 60.0
    )
    burst_profile = burst_events.group_by("pr_id").agg(
        pl.len().alias("burst_events"),
        pl.col("response_user_type")
        .str.to_lowercase()
        .eq("user")
        .any()
        .alias("burst_has_user_account"),
    )

    candidates = (
        flip.join(burst_profile, on="pr_id", how="inner")
        .filter(
            (~pl.col("burst_has_user_account"))
            & (pl.col("burst_events") >= MIN_BURST_EVENTS)
        )
        .sort(["burst_events", "pr_id"], descending=[True, False])
    )
    if candidates.height == 0:
        raise SystemExit(
            "No pull request both flips owner across the five-minute rule and "
            f"carries {MIN_BURST_EVENTS} machine-only burst events; relax a condition "
            "rather than hand-picking one."
        )
    chosen = candidates.row(0, named=True)
    pr_id = int(chosen["pr_id"])

    chain = chains.filter(pl.col("pr_id") == pr_id).row(0, named=True)
    timeline = events.filter(pl.col("pr_id") == pr_id).sort(
        ["hours_after_trigger", "response_event_id"]
    )
    burst = timeline.filter(pl.col("hours_after_trigger") <= BURST_MINUTES / 60.0)
    after = timeline.filter(pl.col("hours_after_trigger") > BURST_MINUTES / 60.0)
    if after.height == 0:
        raise SystemExit("The chosen pull request has nothing after the burst")
    first_after = after.row(0, named=True)

    reviewer = str(chain["trigger_reviewer_agent"]).replace("_", " ")
    author_product = str(chain["author_agent"]).replace("_", " ")

    rows = [
        {
            "order": 0,
            "minutes_after_trigger": 0.0,
            "owner_kind": "mapped_product",
            "actor": reviewer,
            "event": "inline review comment on one line of the change",
            "verdict": "this is the trigger",
            "rule": "trigger",
        }
    ]
    for index, event in enumerate(burst.iter_rows(named=True)):
        kind = owner_kind(event["response_user_type"], event["response_agent"])
        actor = (
            str(event["response_agent"]).replace("_", " ")
            if event["response_agent"] is not None
            else STATE_LABEL[kind]
        )
        rows.append(
            {
                "order": 1 + index,
                "minutes_after_trigger": round(
                    float(event["hours_after_trigger"]) * 60.0, 2
                ),
                "owner_kind": kind,
                "actor": actor,
                "event": CHANNEL.get(
                    str(event["response_source"]), str(event["response_source"])
                ),
                "verdict": "inside the burst: does not decide the next owner",
                "rule": "burst exclusion",
            }
        )
    first_kind = owner_kind(
        first_after["response_user_type"], first_after["response_agent"]
    )
    rows.append(
        {
            "order": len(rows),
            "minutes_after_trigger": round(
                float(first_after["hours_after_trigger"]) * 60.0, 2
            ),
            "owner_kind": first_kind,
            "actor": STATE_LABEL[first_kind],
            "event": CHANNEL.get(
                str(first_after["response_source"]), str(first_after["response_source"])
            ),
            "verdict": "the first post-burst action: this decides the owner",
            "rule": "first post-burst owner",
        }
    )

    # The drawn timeline has to reproduce the analysis, or the example is an
    # illustration of something else. Both readings are recomputed here from the
    # raw event stream and checked against the artifact the figure's bars use.
    naive_kind = owner_kind(
        timeline.row(0, named=True)["response_user_type"],
        timeline.row(0, named=True)["response_agent"],
    )
    if naive_kind != chosen[f"state_{NAIVE_MINUTES}"]:
        raise SystemExit(
            "The first raw event's owner kind disagrees with the zero-minute "
            f"artifact: {naive_kind} against {chosen[f'state_{NAIVE_MINUTES}']}"
        )
    if first_kind != chosen[f"state_{BURST_MINUTES}"]:
        raise SystemExit(
            "The first post-burst owner kind disagrees with the five-minute "
            f"artifact: {first_kind} against {chosen[f'state_{BURST_MINUTES}']}"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(OUTPUT / "timeline.csv")
    summary = {
        "pr_id": pr_id,
        "repository": str(chain["repo_url"]),
        "author_product": str(chain["author_agent"]),
        "reviewing_product": str(chain["trigger_reviewer_agent"]),
        "trigger_dt": str(chain["trigger_dt"]),
        "burst_minutes": BURST_MINUTES,
        "burst_events": int(chosen["burst_events"]),
        "burst_span_minutes": round(
            float(burst["hours_after_trigger"].max()) * 60.0, 2
        ),
        "burst_products": sorted(
            {
                str(value)
                for value in burst["response_agent"].to_list()
                if value is not None
            }
        ),
        "owner_without_the_rule": str(chosen[f"state_{NAIVE_MINUTES}"]),
        "owner_with_the_rule": str(chosen[f"state_{BURST_MINUTES}"]),
        "first_post_burst_minutes": round(
            float(first_after["hours_after_trigger"]) * 60.0, 2
        ),
        "candidates_satisfying_the_rule": int(candidates.height),
        "selection": (
            "the pull request with the most burst events among those where the "
            "five-minute rule changes the first later owner from a mapped product "
            "to a user account and no burst event comes from a user account; ties "
            "broken on the pull request identifier"
        ),
        "note": (
            "accounts are reported by role and product rather than by login; the "
            "pull request is public but naming individuals adds nothing"
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Burst example: {chain['repo_url']} (PR {pr_id})")
    print(
        f"  {reviewer} reviews a change written by {author_product}; "
        f"{summary['burst_events']} automated events in the next "
        f"{summary['burst_span_minutes']:.1f} min"
    )
    for row in rows:
        print(
            f"  +{row['minutes_after_trigger']:>7.2f} min  "
            f"{row['actor']:<18} {row['verdict']}"
        )


if __name__ == "__main__":
    main()
