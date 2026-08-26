from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.analysis.run_addressed_edge_confounding_sensitivity import (
    e_value,
    negative_control_table,
    randomisation_inference,
    risk_ratio_from_difference,
    tipping_grid,
)


def synthetic_cohort(seed: int = 7) -> pd.DataFrame:
    """A small cohort with the columns the sensitivity models require."""
    generator = np.random.default_rng(seed)
    size = 400
    frame = pd.DataFrame(
        {
            "repo_id": generator.integers(0, 20, size),
            "author_agent": generator.choice(["a", "b"], size),
            "trigger_reviewer_agent": generator.choice(["c", "d"], size),
            "trigger_month": generator.choice(["2026-01", "2026-02"], size),
            "log1p_trigger_age_hours": generator.normal(1.0, 0.3, size),
            "log1p_pre_events": generator.normal(0.9, 0.3, size),
            "pre_user_events": generator.integers(0, 3, size),
            "pre_bot_events": generator.integers(0, 4, size),
            "pre_decisive_reviews": generator.integers(0, 2, size),
            "pre_force_pushes": generator.integers(0, 2, size),
        }
    )
    for threshold in (1, 6, 24, 48):
        frame[f"exact_parent_reply_by_{threshold}h"] = (
            generator.random(size) < 0.1 * threshold / 48 + 0.05
        ).astype(int)
    frame["merged_from_48h_to_30d"] = (generator.random(size) < 0.4).astype(int)
    frame["pre_trigger_decisive_review"] = (frame["pre_decisive_reviews"] > 0).astype(int)
    frame["pre_trigger_force_push"] = (frame["pre_force_pushes"] > 0).astype(int)
    frame["pre_trigger_user_event"] = (frame["pre_user_events"] > 0).astype(int)
    return frame


def test_e_value_is_symmetric_under_inversion() -> None:
    assert e_value(2.0) == pytest.approx(e_value(0.5))
    assert e_value(1.0) == pytest.approx(1.0)


def test_e_value_matches_the_published_formula() -> None:
    ratio = 1.4577953061577362
    assert e_value(ratio) == pytest.approx(ratio + np.sqrt(ratio * (ratio - 1.0)))


def test_risk_ratio_rescales_a_risk_difference() -> None:
    assert risk_ratio_from_difference(0.4, 0.2) == pytest.approx(1.5)
    with pytest.raises(ValueError):
        risk_ratio_from_difference(0.0, 0.2)


def test_tipping_grid_bias_is_the_product_of_its_two_axes() -> None:
    grid, frontier = tipping_grid(synthetic_cohort())
    product = grid["prevalence_difference"] * grid["outcome_difference"]
    assert np.allclose(grid["induced_bias"], product)
    assert np.allclose(
        grid["residual_estimate"], grid["adjusted_estimate"] - grid["induced_bias"]
    )
    # The frontier must invert the same algebra.
    needed = frontier["outcome_difference_to_remove_point_estimate"]
    estimate = grid["adjusted_estimate"].iloc[0]
    assert np.allclose(needed * frontier["prevalence_difference"], estimate)


def test_negative_controls_never_condition_on_their_own_outcome() -> None:
    table = negative_control_table(synthetic_cohort())
    assert len(table) == 12
    for _, row in table.iterrows():
        dropped = set(row["dropped_controls"].split(";"))
        if row["negative_control_outcome"] == "pre_trigger_decisive_review":
            assert "pre_decisive_reviews" in dropped
        if row["negative_control_outcome"] == "pre_trigger_force_push":
            assert "pre_force_pushes" in dropped
        if row["negative_control_outcome"] == "pre_trigger_user_event":
            assert {"pre_user_events", "log1p_pre_events"} <= dropped


def test_randomisation_inference_is_deterministic_and_null_on_noise() -> None:
    frame = synthetic_cohort()
    first = randomisation_inference(frame)
    second = randomisation_inference(frame)
    assert np.allclose(
        first["permutation_p_value_two_sided"],
        second["permutation_p_value_two_sided"],
    )
    # The synthetic outcome is independent of the exposure, so the permutation
    # reference distribution must be centred on zero.
    assert first["permutation_mean"].abs().max() < 0.05
    assert (first["permutation_p_value_two_sided"] > 0.01).all()
