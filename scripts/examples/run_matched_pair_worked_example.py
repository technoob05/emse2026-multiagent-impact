"""One real matched pair, so RQ2's matching stops being an abstraction.

RQ2's estimate is a paired difference over 546 pairs. A pair is built by holding
five things fixed --- repository, the pull request author's account, the author's
product, the channel the review arrived on, and the calendar month --- and
letting only the reviewer's product differ. The article states that rule and
reports the difference. It never shows a pair, so the reader has no picture of
what "matched" bought.

This script writes out one real pair and the tally the paired difference is
computed from. The pair is chosen by a rule fixed here:

1. Both triggers must be inline review comments, so the two sides are on the
   same channel and a reader is not comparing a review summary with a comment.
2. The cross-product side must have no visible follow-up and the same-product
   side must have some, which is the discordant configuration the paired
   difference is actually made of.
3. Among those, take the pair whose two triggers are closest in time, breaking
   ties on the cross-product pull request identifier. Closest in time is the
   tightest match the data offers, not the largest gap.

Point 2 selects on the outcome, and that would be dishonest if the panel showed
only the pair. So the tally of all 546 pairs is written out beside it: how many
pairs run the way the drawn one does, how many run the opposite way, and how
many are concordant. The paired difference is the first two of those divided by
546, and the artifact recomputes it and checks it against the analysis output
rather than trusting the drawing.

Accounts are reported by role, never by login, which is the convention Figure 1
already uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY = ROOT / "outputs" / "coordination_topology"
OUTPUT = ROOT / "outputs" / "worked_example_matched_pair"

SPECIFICATION = "exact_author_user"
OUTCOME = "any_visible_followup"
TOLERANCE = 5e-4

# The five things held fixed when a pair is built. Named here so the panel can
# print them and the guard below can check that they really are equal.
MATCH_KEYS = (
    ("repo_url", "repository"),
    ("author_user_norm", "the pull request author's account"),
    ("author_agent", "the product that wrote the change"),
    ("trigger_source", "the channel the review arrived on"),
    ("trigger_month", "the calendar month"),
)


def short_repo(url: str) -> str:
    return url.split("/repos/")[-1]


def main() -> None:
    pairs = pl.read_parquet(TOPOLOGY / "exact_author_stratum_matched_pairs.parquet")
    contrasts = pl.read_csv(TOPOLOGY / "matched_visibility_contrasts.csv").filter(
        (pl.col("specification") == SPECIFICATION) & (pl.col("outcome") == OUTCOME)
    )
    if contrasts.height != 1:
        raise SystemExit(
            f"matched_visibility_contrasts.csv no longer carries exactly one "
            f"{SPECIFICATION}/{OUTCOME} row"
        )
    contrast = contrasts.row(0, named=True)

    # The tally the paired difference is made of. Concordant pairs cancel; the
    # estimate is the difference between the two discordant counts.
    cross = pl.col("any_observable_response_cross")
    same = pl.col("any_observable_response_same")
    tally = {
        "both_sides_answered": int(pairs.filter(cross & same).height),
        "only_the_same_product_side_answered": int(pairs.filter(~cross & same).height),
        "only_the_cross_product_side_answered": int(pairs.filter(cross & ~same).height),
        "neither_side_answered": int(pairs.filter(~cross & ~same).height),
    }
    if sum(tally.values()) != pairs.height:
        raise SystemExit("The four cells of the tally do not sum to the pair count")
    recomputed = (
        tally["only_the_cross_product_side_answered"]
        - tally["only_the_same_product_side_answered"]
    ) / pairs.height
    if abs(recomputed - float(contrast["paired_difference"])) > TOLERANCE:
        raise SystemExit(
            "The tally does not reproduce the published paired difference: "
            f"{recomputed:.5f} against {float(contrast['paired_difference']):.5f}"
        )

    candidates = pairs.filter(
        (~cross)
        & same
        & (pl.col("trigger_source_cross") == "inline_review_comment")
        & (pl.col("trigger_source_same") == "inline_review_comment")
    ).sort(["trigger_gap_hours", "pr_id_cross"])
    if candidates.height == 0:
        raise SystemExit(
            "No inline-channel pair is discordant in the illustrated direction"
        )
    chosen = candidates.row(0, named=True)

    # A pair is only a pair if the five keys really match. Checked here rather
    # than assumed, because the panel prints them as the reason the comparison
    # is fair.
    for column, _label in MATCH_KEYS:
        left, right = chosen[f"{column}_cross"], chosen[f"{column}_same"]
        if left != right:
            raise SystemExit(
                f"The chosen pair does not match on {column}: {left!r} against {right!r}"
            )

    def side(suffix: str) -> dict[str, object]:
        events = {
            "a reply on the trigger's thread": int(
                chosen[f"direct_inline_replies_{suffix}"]
            ),
            "a new review round": int(chosen[f"subsequent_reviews_{suffix}"]),
            "a pull request comment": int(chosen[f"subsequent_pr_comments_{suffix}"]),
            "the branch is rewritten": int(chosen[f"force_push_events_{suffix}"]),
        }
        return {
            "pr_id": int(chosen[f"pr_id_{suffix}"]),
            "reviewing_product": str(chosen[f"trigger_reviewer_agent_{suffix}"]),
            "relation": str(chosen[f"feedback_relation_{suffix}"]),
            "trigger_dt": str(chosen[f"trigger_dt_{suffix}"]),
            "visible_followup": bool(chosen[f"any_observable_response_{suffix}"]),
            "followup_events": events,
            "followup_event_total": sum(events.values()),
        }

    cross_side, same_side = side("cross"), side("same")
    if cross_side["relation"] != "cross_product":
        raise SystemExit("The cross side is not labelled cross_product")
    if same_side["relation"] != "same_product":
        raise SystemExit("The same side is not labelled same_product")
    if cross_side["followup_event_total"] != 0:
        raise SystemExit("The cross side records follow-up events after all")
    if same_side["followup_event_total"] == 0:
        raise SystemExit("The same side records no follow-up events")

    rows = []
    for arm, payload in (("cross_product", cross_side), ("same_product", same_side)):
        for channel, count in payload["followup_events"].items():  # type: ignore[union-attr]
            rows.append(
                {
                    "arm": arm,
                    "pr_id": payload["pr_id"],
                    "reviewing_product": payload["reviewing_product"],
                    "channel": channel,
                    "events": count,
                }
            )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(OUTPUT / "pair_followup.csv")
    summary = {
        "repository": short_repo(str(chosen["repo_url_cross"])),
        "author_product": str(chosen["author_agent_cross"]),
        "trigger_channel": str(chosen["trigger_source_cross"]),
        "trigger_month": str(chosen["trigger_month_cross"]),
        "minutes_between_the_two_triggers": round(
            float(chosen["trigger_gap_hours"]) * 60.0, 1
        ),
        "matched_on": [label for _column, label in MATCH_KEYS],
        "cross_product_side": cross_side,
        "same_product_side": same_side,
        "pairs": int(pairs.height),
        "repositories": int(contrast["repositories"]),
        "tally": tally,
        "cross_rate": float(contrast["cross_rate"]),
        "same_rate": float(contrast["same_rate"]),
        "paired_difference": float(contrast["paired_difference"]),
        "ci_low": float(contrast["repository_cluster_bootstrap_ci_low"]),
        "ci_high": float(contrast["repository_cluster_bootstrap_ci_high"]),
        "candidates_satisfying_the_rule": int(candidates.height),
        "selection": (
            "the inline-channel pair with the smallest gap between its two "
            "triggers, among pairs where the cross-product side records no "
            "visible follow-up and the same-product side records some; ties "
            "broken on the cross-product pull request identifier"
        ),
        "note": (
            "the drawn pair is one of the discordant pairs the estimate is made "
            "of, so it is selected on its outcome; the tally beside it gives all "
            "four cells over the whole set of pairs"
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Matched-pair example: {summary['repository']}")
    print(
        f"  same account, same product ({summary['author_product']}), same channel, "
        f"same month; triggers {summary['minutes_between_the_two_triggers']} min apart"
    )
    for arm, payload in (("cross", cross_side), ("same", same_side)):
        print(
            f"  {arm:<6} reviewed by {payload['reviewing_product']:<14} "
            f"follow-up events: {payload['followup_event_total']}"
        )
    print(f"  tally over {summary['pairs']} pairs: {tally}")
    print(f"  paired difference: {summary['paired_difference'] * 100:.1f} pp")


if __name__ == "__main__":
    main()
