from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from scripts.analysis.run_addressed_edge_scope_audit import (
    DIFFERENT_PRODUCT_ROLES,
    HUMAN_ROLES,
    TRIGGERING_BRAND,
    build_alternative_exposures,
)

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "outputs" / "addressed_edge_scope"


def test_alternative_exposures_are_nested_and_role_aware() -> None:
    events = pl.DataFrame(
        {
            "pr_id": [1, 1, 2, 3, 4],
            "response_actor_role": [
                TRIGGERING_BRAND,
                "author_account",
                TRIGGERING_BRAND,
                "other_human",
                "other_agent_brand",
            ],
        }
    )
    frame = build_alternative_exposures(events).set_index("pr_id").sort_index()

    # PR 1 has a self-reply and a human reply, so it survives every definition
    # except the different-product one.
    assert bool(frame.loc[1, "edge_excluding_self_brand"])
    assert bool(frame.loc[1, "edge_human_reply"])
    assert not bool(frame.loc[1, "edge_different_product"])
    # PR 2 has only the triggering product replying to itself.
    assert not bool(frame.loc[2, "edge_excluding_self_brand"])
    assert not bool(frame.loc[2, "edge_human_reply"])
    # PR 4's replier is another product, so it is not a human edge but it does
    # count as not-self-brand.
    assert bool(frame.loc[4, "edge_different_product"])
    assert bool(frame.loc[4, "edge_excluding_self_brand"])
    assert not bool(frame.loc[4, "edge_human_reply"])
    # Every PR with any event carries the primary flag.
    assert frame["edge_any"].all()


def test_role_sets_do_not_overlap() -> None:
    assert TRIGGERING_BRAND not in HUMAN_ROLES
    assert TRIGGERING_BRAND not in DIFFERENT_PRODUCT_ROLES
    assert not HUMAN_ROLES & DIFFERENT_PRODUCT_ROLES


@pytest.mark.skipif(
    not (SCOPE / "summary.json").is_file(),
    reason="scope audit has not been run in this checkout",
)
def test_landmark_funnel_reconciles_with_the_analysis_cohort() -> None:
    summary = json.loads((SCOPE / "summary.json").read_text(encoding="utf-8"))
    selection = summary["landmark_selection"]
    assert selection["still_open_at_hour_48"] == selection["landmark_cohort_prs"]
    assert selection["merged_by_hour_48"] <= selection["closed_by_hour_48"]
    assert (
        selection["closed_by_hour_48"] + selection["still_open_at_hour_48"]
        == selection["inline_cross_product_triggers"]
    )


@pytest.mark.skipif(
    not (SCOPE / "exposure_event_composition.csv").is_file(),
    reason="scope audit has not been run in this checkout",
)
def test_exposure_composition_sums_to_the_audited_event_total() -> None:
    summary = json.loads((SCOPE / "summary.json").read_text(encoding="utf-8"))
    composition = pd.read_csv(SCOPE / "exposure_event_composition.csv")
    assert int(composition["events"].sum()) == summary["exposure_events"]
    assert composition["share_of_exposure_events"].sum() == pytest.approx(1.0)


@pytest.mark.skipif(
    not (SCOPE / "conditional_randomisation_inference.csv").is_file(),
    reason="scope audit has not been run in this checkout",
)
def test_conditional_randomisation_reference_is_centred() -> None:
    """The point of the conditional test is a reference distribution at zero."""
    row = pd.read_csv(SCOPE / "conditional_randomisation_inference.csv").iloc[0]
    assert abs(float(row["permutation_mean"])) < 0.02
