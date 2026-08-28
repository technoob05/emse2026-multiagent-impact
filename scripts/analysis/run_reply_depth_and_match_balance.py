"""Two claims the paper makes that a reader could not check.

The article says Online Resource 1 carries "the pre-trigger balance after
matching" for the RQ2 matched pairs. It does not: the only balance block in the
appendix belongs to the RQ3 exact-edge cohort. Matching here is exact on five
keys, so balance on those is true by construction rather than by luck, and the
one dimension nearest-time matching only approximates is the gap between the two
triggers. That is what a balance report should show, so this computes it.

The article also states that across all 88,907 inline replies in the release,
none names a comment that is itself a reply. That is the sentence the whole
addressed-edge construct rests on, and until now it was traceable only to a
working note. This recomputes it from the release and writes the counts out,
including the 29 replies whose parent is absent from the release, which the
article did not mention and which bound the claim.

Neither analysis feeds an estimate. Both exist so a reader can check a sentence.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd
import polars as pl

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs" / "reply_depth_and_match_balance"

# The five keys the matching fixes exactly, as `<name>_cross` / `<name>_same`
# column pairs in the matched-pair product.
EXACT_KEYS = (
    ("repository", "repo_id"),
    ("pull request author account", "author_user_norm"),
    ("product that wrote the change", "author_agent"),
    ("channel the trigger arrived on", "trigger_source"),
    ("calendar month", "trigger_month"),
)


def release_dir() -> pathlib.Path:
    """Where the pinned AIDev release lives, by the same rule the pipeline uses."""
    import os

    env = os.environ.get("AIDEV_DATA_DIR")
    if env:
        return pathlib.Path(env).resolve()
    return (ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M").resolve()


def reply_depth() -> dict[str, object]:
    """Is any inline reply itself replied to? The edge rule depends on the answer."""
    path = release_dir() / "pr_review_comments.parquet"
    if not path.is_file():
        raise SystemExit(
            f"{path} not found. Set AIDEV_DATA_DIR to the pinned release directory."
        )

    frame = pl.scan_parquet(path).select(["id", "in_reply_to_id"]).collect()
    total = frame.height
    replies = frame.filter(pl.col("in_reply_to_id").is_not_null())

    known_ids = set(frame["id"].to_list())
    parents = replies["in_reply_to_id"].to_list()

    # A reply whose parent is itself a reply would make the graph deeper than one
    # level, and would break "a reply in the thread the trigger opened".
    reply_ids = set(replies["id"].to_list())
    parent_is_reply = sum(1 for parent in parents if parent in reply_ids)
    parent_absent = sum(1 for parent in parents if parent not in known_ids)

    return {
        "inline_comment_rows": total,
        "inline_replies": len(parents),
        "replies_whose_parent_is_itself_a_reply": parent_is_reply,
        "replies_whose_parent_is_absent_from_the_release": parent_absent,
        "replies_with_a_resolvable_parent": len(parents) - parent_absent,
        "reply_graph_is_depth_one": parent_is_reply == 0,
        "note": (
            "Checked over every inline review comment in the release, not only "
            "the study cohorts. The absent parents are comments the release does "
            "not carry, so depth is verified on the resolvable remainder; none of "
            "them can make the graph deeper than one level unless the missing "
            "comment is itself a reply, which the release cannot tell us."
        ),
    }


def match_balance() -> tuple[pd.DataFrame, dict[str, object]]:
    """What matching fixed exactly, and how close it got on the one loose axis."""
    pairs = pd.read_parquet(
        ROOT / "outputs" / "coordination_topology" / "exact_author_stratum_matched_pairs.parquet"
    )

    rows = []
    for label, column in EXACT_KEYS:
        left, right = pairs[f"{column}_cross"], pairs[f"{column}_same"]
        identical = int((left.astype(str) == right.astype(str)).sum())
        rows.append(
            {
                "covariate": label,
                "how_it_is_handled": "matched exactly",
                "pairs_identical": identical,
                "pairs": len(pairs),
                "share_identical": identical / len(pairs),
                "detail": "balance holds by construction, not by chance",
            }
        )

    gap = pairs["trigger_gap_hours"].astype(float)
    rows.append(
        {
            "covariate": "hours between the two triggers",
            "how_it_is_handled": "nearest in time, without replacement",
            "pairs_identical": "",
            "pairs": len(pairs),
            "share_identical": "",
            "detail": (
                f"median {gap.median():.1f} h; quartiles {gap.quantile(0.25):.1f} "
                f"and {gap.quantile(0.75):.1f} h; {(gap <= 24).mean() * 100:.1f} per "
                f"cent within a day; largest {gap.max():.1f} h"
            ),
        }
    )

    summary = {
        "pairs": len(pairs),
        "repositories": int(pairs["repo_id_cross"].nunique()),
        "exact_keys": [label for label, _ in EXACT_KEYS],
        "all_exact_keys_identical_in_every_pair": all(
            row["pairs_identical"] == len(pairs)
            for row in rows
            if row["how_it_is_handled"] == "matched exactly"
        ),
        "trigger_gap_hours": {
            "median": float(gap.median()),
            "q1": float(gap.quantile(0.25)),
            "q3": float(gap.quantile(0.75)),
            "max": float(gap.max()),
            "share_within_24h": float((gap <= 24).mean()),
        },
        "note": (
            "This is a post-matching balance report, not a covariate adjustment. "
            "Five keys are matched exactly, so a standardised mean difference on "
            "them is zero by construction and is not reported as though it were a "
            "finding. The gap between the two triggers is the only dimension the "
            "design approximates rather than fixes."
        ),
    }
    return pd.DataFrame(rows), summary


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    balance, balance_summary = match_balance()
    balance.to_csv(OUTPUT / "matched_pair_balance.csv", index=False)

    depth = reply_depth()

    (OUTPUT / "summary.json").write_text(
        json.dumps(
            {"matched_pair_balance": balance_summary, "reply_depth": depth},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("matched-pair balance")
    print(f"  pairs                     : {balance_summary['pairs']}")
    print(f"  five keys identical always: {balance_summary['all_exact_keys_identical_in_every_pair']}")
    gaps = balance_summary["trigger_gap_hours"]
    print(f"  trigger gap median        : {gaps['median']:.1f} h")
    print(f"  within a day              : {gaps['share_within_24h'] * 100:.1f} per cent")
    print()
    print("reply depth, over the whole release")
    print(f"  inline comments           : {depth['inline_comment_rows']:,}")
    print(f"  inline replies            : {depth['inline_replies']:,}")
    print(f"  parent is itself a reply  : {depth['replies_whose_parent_is_itself_a_reply']}")
    print(f"  parent absent from release: {depth['replies_whose_parent_is_absent_from_the_release']}")
    print(f"  depth one                 : {depth['reply_graph_is_depth_one']}")


if __name__ == "__main__":
    main()
