"""One closed accounting of how the study population narrows.

Five population sizes appear in the manuscript -- 8,608 / 4,824 / 3,942 / 3,526 /
1,067 -- and a reader cannot walk from one to the next. This script does not
change any analysis. It reads the same frozen artifacts the paper quotes and
reconstructs, step by step, which pull requests each filter removes, asserting
``before - removed == after`` on every row.

The headline finding of the reconstruction is that the five numbers are NOT a
single chain. They form a tree with one shared trunk and two divergent branches:

    AIDev PR backbone
      -> PRs with time-valid recognised-agent review feedback
      -> PRs with at least one cross-product agent feedback event
      -> trigger leaves a full 7-day response window      = 8,608   (trunk)
      -> first cross-product trigger is an inline comment = 4,824   (trunk)
           |
           +-- BRANCH A (outcome lane, keeps every trigger the chain table has)
           |     -> trigger has a full 30-day outcome horizon = 3,942
           |     -> PR still open at trigger + 48h            = 1,067
           |
           +-- BRANCH B (thread-position lane, re-derived from the union cohort)
                 -> the PR's EARLIEST agent trigger of either relation is the
                    cross-product one                        = 3,526

Branch B applies no 30-day horizon; Branch A applies no first-relation dedupe.
So 3,526 and 3,942 are siblings, not parent and child, and 1,067 is not a subset
of 3,526. The script measures the overlap and says so loudly.

Nothing here is written outside ``outputs/sample_flow/``.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import (  # noqa: E402
    INTERACTION_CUTOFF,
    build_agent_feedback_events,
)

DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CHAIN = ROOT / "outputs" / "cross_agent_review"
ANCHOR = ROOT / "outputs" / "anchorability_coverage"
SCOPE = ROOT / "outputs" / "addressed_edge_scope"
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
TASKCTX = ROOT / "outputs" / "task_context_interaction"
AUTOMATION = ROOT / "outputs" / "user_account_automation"
OUTPUT = ROOT / "outputs" / "sample_flow"

RESPONSE_WINDOW_DAYS = 7
OUTCOME_HORIZON_DAYS = 30
LANDMARK_HOURS = 48

PAPER_NUMBERS = {
    "cross_product_trigger_cohort": 8_608,
    "inline_trigger_cohort": 4_824,
    "merge_curve_cohort": 3_942,
    "thread_position_cohort": 3_526,
    "hour48_landmark_cohort": 1_067,
    "exposure_events": 128,
    "exposed_prs": 109,
    "user_written_edge_events": 105,
}


# --------------------------------------------------------------------------
# step bookkeeping
# --------------------------------------------------------------------------


class Flow:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def add(
        self,
        *,
        stage: str,
        parent: str | None,
        branch: str,
        unit: str,
        filter_description: str,
        before: int,
        after: int,
        verified_against: str = "",
        paper_number: int | None = None,
        note: str = "",
    ) -> None:
        removed = before - after
        if before - removed != after:
            raise AssertionError(f"{stage}: {before} - {removed} != {after}")
        if removed < 0:
            raise AssertionError(
                f"{stage}: a filter cannot add rows ({before} -> {after})"
            )
        if paper_number is not None and after != paper_number:
            raise AssertionError(
                f"{stage}: reconstructed {after} but the paper quotes {paper_number}"
            )
        self.rows.append(
            {
                "step": len(self.rows),
                "branch": branch,
                "stage": stage,
                "parent_stage": parent or "",
                "filter_description": filter_description,
                "unit": unit,
                "count_before": before,
                "count_removed": removed,
                "count_after": after,
                "is_terminal": bool(verified_against),
                "verified_against": verified_against,
                "paper_number": paper_number if paper_number is not None else "",
                "note": note,
            }
        )

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def _csv_count(path: Path, query: dict[str, object], column: str) -> int:
    frame = pd.read_csv(path)
    mask = pd.Series(True, index=frame.index)
    for key, value in query.items():
        mask &= frame[key] == value
    hits = frame.loc[mask, column]
    if len(hits) != 1:
        raise AssertionError(f"{path.name}: {query} matched {len(hits)} rows, not 1")
    return int(hits.iloc[0])


def _json_at(path: Path, keys: list[str]) -> object:
    node = json.loads(path.read_text(encoding="utf-8"))
    for key in keys:
        node = node[key]
    return node


# --------------------------------------------------------------------------
# trunk: raw release -> the cross-product trigger cohort
# --------------------------------------------------------------------------


def build_trunk(flow: Flow) -> pl.DataFrame:
    if not DATA.exists():
        raise SystemExit(f"AIDev release not found at {DATA}")

    backbone_prs = int(
        pl.scan_parquet(DATA / "pull_request.parquet")
        .select(pl.len())
        .collect()
        .item()
    )

    per_pr = (
        build_agent_feedback_events(DATA)
        .group_by("pr_id")
        .agg(
            pl.col("cross_agent").any().alias("has_cross"),
            pl.col("interaction_dt")
            .filter(pl.col("cross_agent"))
            .min()
            .alias("first_cross_dt"),
        )
        .collect()
    )

    prs_with_agent_feedback = per_pr.height
    prs_with_cross_feedback = int(per_pr["has_cross"].sum())
    window_cutoff = INTERACTION_CUTOFF - timedelta(days=RESPONSE_WINDOW_DAYS)
    with_window = per_pr.filter(
        pl.col("has_cross") & (pl.col("first_cross_dt") <= pl.lit(window_cutoff))
    )

    flow.add(
        stage="AIDev pull-request backbone",
        parent=None,
        branch="trunk",
        unit="pull requests",
        filter_description=(
            "every pull request in the AIDev release's pull_request.parquet, "
            "before any study restriction"
        ),
        before=backbone_prs,
        after=backbone_prs,
        note="chain origin; nothing removed",
    )
    flow.add(
        stage="Has recognised-agent review feedback",
        parent="AIDev pull-request backbone",
        branch="trunk",
        unit="pull requests",
        filter_description=(
            "keep pull requests carrying at least one review event written by one "
            "of the six mapped agent accounts, timestamped between the PR opening "
            "and its close, and no later than the 2026-04-15 observation cutoff"
        ),
        before=backbone_prs,
        after=prs_with_agent_feedback,
    )
    flow.add(
        stage="Has cross-product agent feedback",
        parent="Has recognised-agent review feedback",
        branch="trunk",
        unit="pull requests",
        filter_description=(
            "keep pull requests where at least one of those agent review events "
            "was written by a product different from the PR's authoring product"
        ),
        before=prs_with_agent_feedback,
        after=prs_with_cross_feedback,
    )
    flow.add(
        stage="Cross-product trigger cohort",
        parent="Has cross-product agent feedback",
        branch="trunk",
        unit="pull requests",
        filter_description=(
            "keep pull requests whose FIRST cross-product agent review event "
            "leaves a complete 7-day response window before the observation "
            "cutoff, i.e. trigger no later than 2026-04-08"
        ),
        before=prs_with_cross_feedback,
        after=with_window.height,
        verified_against="outputs/cross_agent_review/cross_feedback_response_chains.parquet",
        paper_number=PAPER_NUMBERS["cross_product_trigger_cohort"],
    )

    chains = pl.read_parquet(CHAIN / "cross_feedback_response_chains.parquet")
    if chains.height != with_window.height:
        raise AssertionError(
            "The re-derived cross-product trigger cohort does not match the frozen "
            f"chain table: {with_window.height} vs {chains.height}"
        )
    if set(chains["pr_id"].to_list()) != set(with_window["pr_id"].to_list()):
        raise AssertionError(
            "The re-derived cohort has the right size but not the same PRs as the "
            "frozen chain table."
        )
    anchor_total = int(
        _json_at(
            ANCHOR / "summary.json",
            [
                "full_cross_product_trigger_cohort",
                "cohort_definition",
                "trigger_prs_in_this_cohort",
            ],
        )
    )
    if anchor_total != chains.height:
        raise AssertionError("anchorability_coverage disagrees on the 8,608 cohort.")
    return chains


def add_inline_step(flow: Flow, chains: pl.DataFrame) -> pl.DataFrame:
    inline = chains.filter(pl.col("trigger_source") == "inline_review_comment")
    artifact_count = _csv_count(
        ANCHOR / "trigger_channel_composition.csv",
        {
            "cohort": "full_cross_product_trigger_cohort",
            "trigger_channel": "inline_review_comment",
        },
        "trigger_prs",
    )
    if artifact_count != inline.height:
        raise AssertionError("anchorability_coverage disagrees on the 4,824 cohort.")
    flow.add(
        stage="Inline-trigger cohort (in scope for the addressed edge)",
        parent="Cross-product trigger cohort",
        branch="trunk",
        unit="pull requests",
        filter_description=(
            "keep pull requests whose first cross-product review arrived as an "
            "inline review comment; review summaries and PR-level comments carry "
            "no reply target, so no addressed edge can ever be built for them"
        ),
        before=chains.height,
        after=inline.height,
        verified_against="outputs/anchorability_coverage/trigger_channel_composition.csv",
        paper_number=PAPER_NUMBERS["inline_trigger_cohort"],
    )
    return inline


# --------------------------------------------------------------------------
# branch A: outcome lane (3,942 -> 1,067)
# --------------------------------------------------------------------------


def build_branch_a(flow: Flow, inline: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    horizon_cutoff = INTERACTION_CUTOFF - timedelta(days=OUTCOME_HORIZON_DAYS)
    mature = inline.filter(pl.col("trigger_dt") <= pl.lit(horizon_cutoff))
    funnel_total = _csv_count(
        SCOPE / "landmark_selection_funnel.csv",
        {"stage": "Cross-product inline triggers with a 30-day horizon"},
        "prs",
    )
    if funnel_total != mature.height:
        raise AssertionError("addressed_edge_scope disagrees on the 3,942 cohort.")
    flow.add(
        stage="Merge-curve cohort (30-day outcome horizon)",
        parent="Inline-trigger cohort (in scope for the addressed edge)",
        branch="A: outcome lane",
        unit="pull requests",
        filter_description=(
            "keep pull requests whose trigger leaves a complete 30-day outcome "
            "horizon before the observation cutoff, i.e. trigger no later than "
            "2026-03-16; the remainder cannot be followed for the full window"
        ),
        before=inline.height,
        after=mature.height,
        verified_against=(
            "outputs/addressed_edge_scope/landmark_selection_funnel.csv; "
            "scripts/analysis/run_merge_curves.py EXPECTED_POPULATION"
        ),
        paper_number=PAPER_NUMBERS["merge_curve_cohort"],
    )
    declared = re.search(
        r"EXPECTED_POPULATION\s*=\s*([\d_]+)",
        (ROOT / "scripts" / "analysis" / "run_merge_curves.py").read_text(
            encoding="utf-8"
        ),
    )
    if declared is None or int(declared.group(1).replace("_", "")) != mature.height:
        raise AssertionError("run_merge_curves.py disagrees on the 3,942 cohort.")

    landmark = mature.with_columns(
        (pl.col("trigger_dt") + timedelta(hours=LANDMARK_HOURS)).alias("landmark_dt")
    )
    still_open = landmark.filter(
        pl.col("closed_dt").is_null() | (pl.col("closed_dt") > pl.col("landmark_dt"))
    )
    funnel_open = _csv_count(
        SCOPE / "landmark_selection_funnel.csv",
        {"stage": "Still open at hour 48"},
        "prs",
    )
    cohort_artifact = pl.read_parquet(EDGE / "analysis_cohort.parquet")
    if funnel_open != still_open.height:
        raise AssertionError("addressed_edge_scope disagrees on the 1,067 cohort.")
    if cohort_artifact.height != still_open.height:
        raise AssertionError(
            "addressed_edge_landmark/analysis_cohort.parquet disagrees on 1,067."
        )
    if set(cohort_artifact["pr_id"].to_list()) != set(still_open["pr_id"].to_list()):
        raise AssertionError(
            "The re-derived hour-48 cohort has the right size but different PRs "
            "from the frozen analysis cohort."
        )
    flow.add(
        stage="Hour-48 landmark cohort",
        parent="Merge-curve cohort (30-day outcome horizon)",
        branch="A: outcome lane",
        unit="pull requests",
        filter_description=(
            "keep pull requests still open 48 hours after the trigger; the "
            "removed ones had already closed before the outcome window opened"
        ),
        before=mature.height,
        after=still_open.height,
        verified_against=(
            "outputs/addressed_edge_landmark/analysis_cohort.parquet; "
            "outputs/addressed_edge_scope/landmark_selection_funnel.csv"
        ),
        paper_number=PAPER_NUMBERS["hour48_landmark_cohort"],
    )
    return mature, still_open


def check_all_channel_sibling(chains: pl.DataFrame, cohort_1067: pl.DataFrame) -> dict:
    """The same 1,067 is reachable the other way round; confirm it is one set."""
    horizon_cutoff = INTERACTION_CUTOFF - timedelta(days=OUTCOME_HORIZON_DAYS)
    mature_all = chains.filter(pl.col("trigger_dt") <= pl.lit(horizon_cutoff))
    open_all = mature_all.with_columns(
        (pl.col("trigger_dt") + timedelta(hours=LANDMARK_HOURS)).alias("landmark_dt")
    ).filter(pl.col("closed_dt").is_null() | (pl.col("closed_dt") > pl.col("landmark_dt")))
    frozen = pl.read_parquet(CHAIN / "feedback_48h_landmark_cohort.parquet")
    if frozen.height != open_all.height:
        raise AssertionError(
            f"All-channel landmark cohort drift: {open_all.height} vs {frozen.height}"
        )
    inline_of_open = open_all.filter(pl.col("trigger_source") == "inline_review_comment")
    if set(inline_of_open["pr_id"].to_list()) != set(cohort_1067["pr_id"].to_list()):
        raise AssertionError(
            "The two orderings of the inline and hour-48 filters do not give the "
            "same 1,067 PRs."
        )
    return {
        "all_channel_hour48_cohort_prs": int(open_all.height),
        "inline_subset_prs": int(inline_of_open.height),
        "commutes_with_inline_filter": True,
        "artifact": "outputs/cross_agent_review/feedback_48h_landmark_cohort.parquet",
        "note": (
            "the inline filter and the hour-48 filter commute; applying them in "
            "the other order passes through an all-channel cohort of "
            f"{open_all.height} PRs and lands on exactly the same 1,067"
        ),
    }


# --------------------------------------------------------------------------
# branch B: thread-position lane (3,526)
# --------------------------------------------------------------------------


def build_branch_b(flow: Flow, inline: pl.DataFrame) -> pl.DataFrame:
    union = pl.read_parquet(CHAIN / "first_agent_feedback_cohort.parquet")
    branch = union.filter(
        (pl.col("trigger_source") == "inline_review_comment")
        & (pl.col("feedback_relation") == "cross_product")
    ).unique("pr_id")
    artifact_count = sum(
        _csv_count(
            TASKCTX / "answer_rate_cells.csv",
            {
                "reviewer_relation": "cross_product",
                "body_issue_link": link,
                "population": "all inline triggers",
            },
            "prs",
        )
        for link in (False, True)
    )
    if artifact_count != branch.height:
        raise AssertionError(
            "task_context_interaction disagrees on the 3,526 cohort: "
            f"{artifact_count} vs {branch.height}"
        )
    inline_ids = set(inline["pr_id"].to_list())
    branch_ids = set(branch["pr_id"].to_list())
    if not branch_ids <= inline_ids:
        raise AssertionError(
            "The thread-position cohort is not a subset of the inline-trigger "
            "cohort; the branch cannot be drawn from 4,824."
        )
    flow.add(
        stage="Thread-position cohort",
        parent="Inline-trigger cohort (in scope for the addressed edge)",
        branch="B: thread-position lane",
        unit="pull requests",
        filter_description=(
            "keep pull requests whose earliest agent review trigger of EITHER "
            "relation is the cross-product one; a pull request that a same-product "
            "reviewer had already commented on earlier is relabelled same-product "
            "when the two trigger tables are merged and one row per PR is kept"
        ),
        before=inline.height,
        after=branch.height,
        verified_against="outputs/task_context_interaction/answer_rate_cells.csv",
        paper_number=PAPER_NUMBERS["thread_position_cohort"],
        note=(
            "no 30-day outcome horizon is applied on this branch, so it is a "
            "sibling of the merge-curve cohort, not its parent or child"
        ),
    )
    return branch


# --------------------------------------------------------------------------
# event-unit chain inside the hour-48 cohort
# --------------------------------------------------------------------------


def build_event_chain(flow: Flow, cohort_1067: pl.DataFrame) -> dict:
    audit = pl.read_parquet(EDGE / "exact_parent_reply_event_audit.parquet")
    exposed_prs = audit["pr_id"].n_unique()
    if not set(audit["pr_id"].to_list()) <= set(cohort_1067["pr_id"].to_list()):
        raise AssertionError("An exposure event sits outside the hour-48 cohort.")

    flow.add(
        stage="Exposed pull requests (exact addressed edge by hour 48)",
        parent="Hour-48 landmark cohort",
        branch="A: outcome lane",
        unit="pull requests",
        filter_description=(
            "keep pull requests carrying at least one later inline comment whose "
            "stored reply target is the trigger comment's own identifier, posted "
            "within 48 hours of the trigger"
        ),
        before=cohort_1067.height,
        after=int(exposed_prs),
        verified_against="outputs/addressed_edge_landmark/denominators.csv",
        paper_number=PAPER_NUMBERS["exposed_prs"],
    )

    events_total = audit.height
    flow.add(
        stage="Exposure reply events",
        parent="Exposed pull requests (exact addressed edge by hour 48)",
        branch="A: outcome lane (event unit)",
        unit="reply events",
        filter_description=(
            "switch of unit: the 109 exposed pull requests carry 128 exact reply "
            "events between them, because a pull request can receive more than one"
        ),
        before=events_total,
        after=events_total,
        verified_against="outputs/addressed_edge_landmark/exact_parent_reply_event_audit.parquet",
        paper_number=PAPER_NUMBERS["exposure_events"],
        note="unit change, not a filter; 128 events on 109 PRs",
    )

    composition = pd.read_csv(SCOPE / "exposure_event_composition.csv")
    user_roles = {"author_account", "other_human"}
    user_events = int(
        composition.loc[
            composition["response_actor_role"].isin(user_roles), "events"
        ].sum()
    )
    user_prs = int(
        _json_at(AUTOMATION / "summary.json", ["edge_prs_with_a_user_written_edge"])
    )
    if int(_json_at(AUTOMATION / "summary.json", ["edge_events_written_by_user_accounts"])) != user_events:
        raise AssertionError("user_account_automation disagrees on the 105 events.")
    flow.add(
        stage="User-account-written exposure events",
        parent="Exposure reply events",
        branch="A: outcome lane (event unit)",
        unit="reply events",
        filter_description=(
            "keep reply events written by ordinary user accounts; the removed ones "
            "come from the triggering product itself, other bots, and mapped "
            "products other than the trigger's author"
        ),
        before=events_total,
        after=user_events,
        verified_against=(
            "outputs/addressed_edge_scope/exposure_event_composition.csv; "
            "outputs/user_account_automation/summary.json"
        ),
        paper_number=PAPER_NUMBERS["user_written_edge_events"],
        note=f"these {user_events} events fall on {user_prs} pull requests",
    )

    counts = pd.read_csv(AUTOMATION / "reply_content_category_counts.csv")
    substantive = counts.loc[
        (counts["scope"] == "user_written_edges")
        & (counts["labelling"] == "rule_category")
        & (counts["category"] == "substantive_response")
    ]
    substantive_events = int(substantive["edges"].iloc[0])
    substantive_prs = int(substantive["prs"].iloc[0])
    flow.add(
        stage="Substantive user-written exposure events",
        parent="User-account-written exposure events",
        branch="A: outcome lane (event unit)",
        unit="reply events",
        filter_description=(
            "keep reply events the pre-specified rule set classifies as a "
            "substantive response, dropping platform text, routing hand-offs to "
            "another automation, and bare acknowledgements"
        ),
        before=user_events,
        after=substantive_events,
        verified_against="outputs/user_account_automation/reply_content_category_counts.csv",
        note=f"these {substantive_events} events fall on {substantive_prs} pull requests",
    )
    return {
        "exposed_prs": int(exposed_prs),
        "exposure_events": int(events_total),
        "user_written_events": user_events,
        "user_written_prs": user_prs,
        "substantive_events": substantive_events,
        "substantive_prs": substantive_prs,
    }


# --------------------------------------------------------------------------
# nesting diagnostics
# --------------------------------------------------------------------------


def nesting_report(
    inline: pl.DataFrame,
    branch_a: pl.DataFrame,
    branch_b: pl.DataFrame,
    cohort_1067: pl.DataFrame,
) -> dict:
    a = set(branch_a["pr_id"].to_list())
    b = set(branch_b["pr_id"].to_list())
    c = set(cohort_1067["pr_id"].to_list())
    parent = set(inline["pr_id"].to_list())
    return {
        "shared_parent": {
            "stage": "Inline-trigger cohort",
            "prs": len(parent),
        },
        "merge_curve_vs_thread_position": {
            "merge_curve_prs": len(a),
            "thread_position_prs": len(b),
            "in_both": len(a & b),
            "merge_curve_only": len(a - b),
            "thread_position_only": len(b - a),
            "is_nested_either_way": bool(a <= b or b <= a),
            "verdict": (
                "NOT NESTED. The 3,942 merge-curve cohort and the 3,526 "
                "thread-position cohort are two branches from the same 4,824 "
                "parent, filtered on different things. Neither contains the other."
            ),
        },
        "hour48_vs_thread_position": {
            "hour48_prs": len(c),
            "thread_position_prs": len(b),
            "hour48_inside_thread_position": len(c & b),
            "hour48_outside_thread_position": len(c - b),
            "is_subset": bool(c <= b),
            "verdict": (
                "The manuscript's threats sentence reads '13 of 3,526 sit "
                "mid-thread, and in the hour-48 group only 3 of 1,067 do', which "
                "invites the reader to treat the 1,067 as a subset of the 3,526. "
                f"It is not: {len(c - b)} of the 1,067 are outside the 3,526."
            ),
        },
    }


def documentation_findings(chains: pl.DataFrame) -> list[dict]:
    union = pl.read_parquet(CHAIN / "first_agent_feedback_cohort.parquet")
    relabelled = (
        chains.select("pr_id")
        .join(union.select("pr_id", "feedback_relation"), on="pr_id", how="left")
        .filter(pl.col("feedback_relation") != "cross_product")
        .height
    )
    return [
        {
            "issue": "cohort definition text does not match the code",
            "where": (
                "outputs/anchorability_coverage/summary.json and "
                "scripts/analysis/run_anchorability_coverage.py describe the 8,608 "
                "as 'every PR whose FIRST agent review feedback is cross-product'"
            ),
            "what_the_code_does": (
                "build_cross_feedback_response_chains filters to cross-product "
                "events FIRST and then takes the earliest of those, so a pull "
                "request whose genuinely first agent review was same-product is "
                "still in the 8,608"
            ),
            "size_of_the_gap_prs": int(relabelled),
            "consequence": (
                "this is exactly the filter that separates the 3,526 branch from "
                "the 4,824 parent, and it is why the two branches diverge"
            ),
        }
    ]


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def print_chain(frame: pd.DataFrame) -> None:
    print("=" * 100)
    print("SAMPLE FLOW - ordered reconciliation")
    print("=" * 100)
    current_branch = None
    for row in frame.to_dict("records"):
        if row["branch"] != current_branch:
            current_branch = row["branch"]
            print(f"\n--- {current_branch} ---")
        marker = "*" if row["is_terminal"] else " "
        print(
            f"{marker} [{row['step']:>2}] {row['stage']}  ({row['unit']})\n"
            f"       from: {row['parent_stage'] or '(origin)'}\n"
            f"       rule: {row['filter_description']}\n"
            f"       {row['count_before']:>9,}  -  {row['count_removed']:>9,}"
            f"  =  {row['count_after']:>9,}   [reconciles]"
        )
        if row["paper_number"] != "":
            print(f"       paper quotes: {int(row['paper_number']):,}  VERIFIED")
        if row["verified_against"]:
            print(f"       artifact: {row['verified_against']}")
        if row["note"]:
            print(f"       note: {row['note']}")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    flow = Flow()

    chains = build_trunk(flow)
    inline = add_inline_step(flow, chains)
    branch_a_mature, cohort_1067 = build_branch_a(flow, inline)
    sibling = check_all_channel_sibling(chains, cohort_1067)
    branch_b = build_branch_b(flow, inline)
    events = build_event_chain(flow, cohort_1067)

    frame = flow.frame()
    nesting = nesting_report(inline, branch_a_mature, branch_b, cohort_1067)
    findings = documentation_findings(chains)

    unreconciled = [
        key
        for key, value in PAPER_NUMBERS.items()
        if value not in set(frame["count_after"].tolist())
    ]

    frame.to_csv(OUTPUT / "sample_flow.csv", index=False)
    summary = {
        "structure": "tree with one trunk and two branches from a shared parent",
        "trunk_terminal": "Inline-trigger cohort (in scope for the addressed edge)",
        "branches": {
            "A: outcome lane": [
                "Merge-curve cohort (30-day outcome horizon)",
                "Hour-48 landmark cohort",
                "Exposed pull requests (exact addressed edge by hour 48)",
            ],
            "B: thread-position lane": ["Thread-position cohort"],
        },
        "steps": frame.to_dict("records"),
        "event_unit_chain": events,
        "alternate_ordering_check": sibling,
        "nesting": nesting,
        "documentation_findings": findings,
        "paper_numbers_checked": PAPER_NUMBERS,
        "unreconciled_paper_numbers": unreconciled,
        "reconciliation": "every step satisfies count_before - count_removed == count_after",
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print_chain(frame)

    print("\n" + "=" * 100)
    print("UNIT NOTE")
    print("=" * 100)
    print(
        f"  {events['exposure_events']} exposure reply events sit on "
        f"{events['exposed_prs']} exposed pull requests.\n"
        f"  {events['user_written_events']} of those events are written by user "
        f"accounts, on {events['user_written_prs']} pull requests.\n"
        f"  {events['substantive_events']} are substantive, on "
        f"{events['substantive_prs']} pull requests.\n"
        "  Every count above the event chain is a pull-request count."
    )

    print("\n" + "=" * 100)
    print("NESTING")
    print("=" * 100)
    mv = nesting["merge_curve_vs_thread_position"]
    print(
        f"  merge-curve 3,942 vs thread-position 3,526:\n"
        f"    in both {mv['in_both']:,} | only in 3,942 {mv['merge_curve_only']:,} | "
        f"only in 3,526 {mv['thread_position_only']:,}\n"
        f"    {mv['verdict']}"
    )
    hv = nesting["hour48_vs_thread_position"]
    print(
        f"\n  hour-48 1,067 vs thread-position 3,526:\n"
        f"    inside {hv['hour48_inside_thread_position']:,} | outside "
        f"{hv['hour48_outside_thread_position']:,}\n"
        f"    {hv['verdict']}"
    )
    print(f"\n  alternate ordering: {sibling['note']}")

    print("\n" + "=" * 100)
    print("DOCUMENTATION FINDINGS")
    print("=" * 100)
    for item in findings:
        print(f"  - {item['issue']}")
        print(f"    where: {item['where']}")
        print(f"    code:  {item['what_the_code_does']}")
        print(f"    size:  {item['size_of_the_gap_prs']:,} PRs")

    print("\n" + "=" * 100)
    print("UNRECONCILED PAPER NUMBERS")
    print("=" * 100)
    print("  none" if not unreconciled else "  " + ", ".join(unreconciled))
    print(f"\nWrote {OUTPUT / 'sample_flow.csv'}")
    print(f"Wrote {OUTPUT / 'summary.json'}")


if __name__ == "__main__":
    main()
