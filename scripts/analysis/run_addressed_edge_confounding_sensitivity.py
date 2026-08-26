"""Quantify how fragile the RQ3 addressed-edge association is.

The landmark model reports an adjusted later-merge difference. It is an
observational contrast, so the manuscript needs a measured answer to three
reviewer questions rather than a qualitative caveat:

1. How strong would an unmeasured confounder have to be to explain the
   estimate away (E-value and an explicit bias-factor tipping grid)?
2. Does the same specification produce a spurious association for outcomes
   that were completed strictly before the exposure (negative-control
   outcomes)?
3. Does the estimate survive inference that does not rely on the clustered
   normal approximation with only 109 exposed PRs (repository-stratified
   randomisation inference)?

Nothing here converts the association into a causal effect. It bounds how much
unmeasured structure would be needed to remove it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices


ROOT = Path(__file__).resolve().parents[2]
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
OUTPUT = ROOT / "outputs" / "addressed_edge_sensitivity"

THRESHOLDS = (1, 6, 24, 48)
PRIMARY_THRESHOLD = 48
EXPECTED_COHORT_ROWS = 1_067
PERMUTATIONS = 2000
PERMUTATION_SEED = 20260826

PRETRIGGER_CONTROLS = [
    "log1p_trigger_age_hours",
    "log1p_pre_events",
    "pre_user_events",
    "pre_bot_events",
    "pre_decisive_reviews",
    "pre_force_pushes",
]
BASE_CATEGORICAL = [
    "C(author_agent)",
    "C(trigger_reviewer_agent)",
    "C(trigger_month)",
]

# Outcomes that are complete before the trigger and therefore cannot be
# produced by a reply that happens after it.
NEGATIVE_CONTROL_OUTCOMES = {
    "pre_trigger_decisive_review": "pre_decisive_reviews",
    "pre_trigger_force_push": "pre_force_pushes",
    "pre_trigger_user_event": "pre_user_events",
}


def load_cohort() -> pd.DataFrame:
    path = EDGE / "analysis_cohort.parquet"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing; run scripts/analysis/run_addressed_edge_landmark_analysis.py first"
        )
    frame = pl.read_parquet(path).to_pandas()
    if len(frame) != EXPECTED_COHORT_ROWS:
        raise AssertionError(
            f"Landmark cohort drift: {len(frame)} != {EXPECTED_COHORT_ROWS}"
        )
    frame["merged_from_48h_to_30d"] = frame["merged_from_48h_to_30d"].astype(int)
    # patsy would treat a boolean column as categorical and rename the term.
    for threshold in THRESHOLDS:
        column = f"exact_parent_reply_by_{threshold}h"
        frame[column] = frame[column].astype(int)
    for label, source in NEGATIVE_CONTROL_OUTCOMES.items():
        frame[label] = (frame[source] > 0).astype(int)
    return frame


def formula(outcome: str, exposure: str, controls: list[str]) -> str:
    return f"{outcome} ~ " + " + ".join([exposure, *BASE_CATEGORICAL, *controls])


def fit_clustered(frame: pd.DataFrame, spec: str, exposure: str):
    endog, design = dmatrices(spec, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    model = sm.OLS(endog.iloc[:, 0], design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    if exposure not in model.params.index:
        raise AssertionError(f"Exposure term missing: {exposure}")
    return model, design, endog, groups


def risk_ratio_from_difference(baseline: float, difference: float) -> float:
    """Approximate risk ratio implied by an adjusted risk difference."""
    if baseline <= 0:
        raise ValueError("Baseline risk must be positive to form a risk ratio")
    return float((baseline + difference) / baseline)


def e_value(ratio: float) -> float:
    """VanderWeele--Ding E-value on the risk-ratio scale."""
    if ratio <= 0:
        raise ValueError("Risk ratio must be positive")
    if ratio < 1:
        ratio = 1.0 / ratio
    if ratio == 1:
        return 1.0
    return float(ratio + np.sqrt(ratio * (ratio - 1.0)))


def e_value_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        spec = formula("merged_from_48h_to_30d", exposure, PRETRIGGER_CONTROLS)
        model, _, _, groups = fit_clustered(frame, spec, exposure)
        estimate = float(model.params[exposure])
        interval = model.conf_int().loc[exposure]
        low = float(interval.iloc[0])
        high = float(interval.iloc[1])
        unexposed = frame.loc[~frame[exposure].astype(bool), "merged_from_48h_to_30d"]
        baseline = float(unexposed.mean())
        ratio = risk_ratio_from_difference(baseline, estimate)
        # The confidence limit closer to the null bounds the required strength.
        limit = low if estimate > 0 else high
        ratio_limit = risk_ratio_from_difference(baseline, limit)
        crosses_null = bool(low <= 0 <= high)
        rows.append(
            {
                "threshold_hours": threshold,
                "exposure": exposure,
                "exposed_prs": int(frame[exposure].sum()),
                "unexposed_prs": int((~frame[exposure].astype(bool)).sum()),
                "repositories": int(groups.nunique()),
                "unexposed_merge_rate": baseline,
                "adjusted_risk_difference": estimate,
                "ci_low": low,
                "ci_high": high,
                "approximate_risk_ratio": ratio,
                "approximate_risk_ratio_at_limit": ratio_limit,
                "e_value_point": e_value(ratio),
                "e_value_limit": 1.0 if crosses_null else e_value(ratio_limit),
                "interval_crosses_null": crosses_null,
                "interpretation": (
                    "minimum risk-ratio strength an unmeasured confounder would need with "
                    "both the exact edge and later merge, beyond the measured pre-trigger "
                    "controls, to explain the association away"
                ),
            }
        )
    return pd.DataFrame(rows)


def tipping_grid(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bias-factor grid for one unmeasured binary pre-trigger confounder.

    On the risk-difference scale, an omitted binary U induces a bias of
    ``delta * gamma`` where ``delta`` is the prevalence difference of U between
    exposed and unexposed PRs and ``gamma`` is the later-merge difference that U
    carries. The grid is therefore an exact algebraic statement, not a
    simulation.
    """
    exposure = f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"
    spec = formula("merged_from_48h_to_30d", exposure, PRETRIGGER_CONTROLS)
    model, _, _, _ = fit_clustered(frame, spec, exposure)
    estimate = float(model.params[exposure])
    ci_low = float(model.conf_int().loc[exposure].iloc[0])

    deltas = np.round(np.arange(0.05, 0.85, 0.05), 2)
    gammas = np.round(np.arange(0.05, 0.85, 0.05), 2)
    rows = []
    for delta in deltas:
        for gamma in gammas:
            bias = float(delta * gamma)
            rows.append(
                {
                    "threshold_hours": PRIMARY_THRESHOLD,
                    "prevalence_difference": float(delta),
                    "outcome_difference": float(gamma),
                    "induced_bias": bias,
                    "adjusted_estimate": estimate,
                    "residual_estimate": estimate - bias,
                    "removes_point_estimate": bool(bias >= estimate),
                    "removes_interval": bool(bias >= ci_low),
                }
            )
    grid = pd.DataFrame(rows)

    frontier_rows = []
    for delta in deltas:
        needed_point = estimate / delta
        needed_interval = ci_low / delta
        frontier_rows.append(
            {
                "threshold_hours": PRIMARY_THRESHOLD,
                "prevalence_difference": float(delta),
                "outcome_difference_to_remove_point_estimate": float(needed_point),
                "outcome_difference_to_remove_interval": float(needed_interval),
                "point_estimate_removable_within_unit_interval": bool(
                    needed_point <= 1.0
                ),
                "interval_removable_within_unit_interval": bool(
                    needed_interval <= 1.0
                ),
            }
        )
    return grid, pd.DataFrame(frontier_rows)


def negative_control_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        for outcome, source in NEGATIVE_CONTROL_OUTCOMES.items():
            controls = [item for item in PRETRIGGER_CONTROLS if item != source]
            if source == "pre_user_events":
                controls = [item for item in controls if item != "log1p_pre_events"]
            spec = formula(outcome, exposure, controls)
            model, _, _, groups = fit_clustered(frame, spec, exposure)
            interval = model.conf_int().loc[exposure]
            low = float(interval.iloc[0])
            high = float(interval.iloc[1])
            rows.append(
                {
                    "threshold_hours": threshold,
                    "exposure": exposure,
                    "negative_control_outcome": outcome,
                    "outcome_prevalence": float(frame[outcome].mean()),
                    "dropped_controls": ";".join(
                        sorted(set(PRETRIGGER_CONTROLS) - set(controls))
                    ),
                    "estimate": float(model.params[exposure]),
                    "ci_low": low,
                    "ci_high": high,
                    "p_value": float(model.pvalues[exposure]),
                    "n_prs": int(model.nobs),
                    "repositories": int(groups.nunique()),
                    "passes_null_expectation": bool(low <= 0 <= high),
                    "interpretation": (
                        "outcome completed strictly before the trigger; a non-null estimate "
                        "would indicate residual pre-trigger confounding rather than an effect"
                    ),
                }
            )
    return pd.DataFrame(rows)


def randomisation_inference(frame: pd.DataFrame) -> pd.DataFrame:
    """Repository-stratified permutation test of the exposure label.

    Only 109 PRs carry the 48-hour exposure, so the clustered normal
    approximation is checked against a design-based reference distribution
    that keeps each repository's exposed count fixed.
    """
    rows = []
    generator = np.random.default_rng(PERMUTATION_SEED)
    for threshold in THRESHOLDS:
        exposure = f"exact_parent_reply_by_{threshold}h"
        spec = formula("merged_from_48h_to_30d", exposure, PRETRIGGER_CONTROLS)
        endog, design = dmatrices(spec, frame, return_type="dataframe")
        y = endog.iloc[:, 0].to_numpy()
        x = design.to_numpy()
        matches = [name for name in design.columns if name.startswith(exposure)]
        if len(matches) != 1:
            raise AssertionError(f"Ambiguous exposure column for {exposure}: {matches}")
        column = list(design.columns).index(matches[0])
        observed = float(np.linalg.lstsq(x, y, rcond=None)[0][column])

        repo = frame.loc[design.index, "repo_id"].to_numpy()
        exposure_values = x[:, column].copy()
        order = np.argsort(repo, kind="stable")
        boundaries = np.flatnonzero(np.diff(repo[order])) + 1
        blocks = np.split(order, boundaries)
        eligible = [
            block for block in blocks if 0 < exposure_values[block].sum() < len(block)
        ]
        if not eligible:
            raise RuntimeError("No repository has within-cluster exposure variation")

        draws = np.empty(PERMUTATIONS)
        design_permuted = x.copy()
        for index in range(PERMUTATIONS):
            permuted = exposure_values.copy()
            for block in eligible:
                permuted[block] = generator.permutation(exposure_values[block])
            design_permuted[:, column] = permuted
            draws[index] = np.linalg.lstsq(design_permuted, y, rcond=None)[0][column]

        two_sided = float(
            (1 + np.sum(np.abs(draws) >= abs(observed) - 1e-12)) / (PERMUTATIONS + 1)
        )
        rows.append(
            {
                "threshold_hours": threshold,
                "exposure": exposure,
                "observed_estimate": observed,
                "permutations": PERMUTATIONS,
                "seed": PERMUTATION_SEED,
                "repositories_with_within_exposure_variation": len(eligible),
                "permutation_mean": float(draws.mean()),
                "permutation_sd": float(draws.std(ddof=1)),
                "permutation_p_value_two_sided": two_sided,
                "permutation_quantile_025": float(np.quantile(draws, 0.025)),
                "permutation_quantile_975": float(np.quantile(draws, 0.975)),
                "interpretation": (
                    "design-based reference distribution holding each repository's exposed "
                    "count fixed; it checks the clustered approximation, not causality"
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = load_cohort()

    evalues = e_value_table(frame)
    grid, frontier = tipping_grid(frame)
    negative = negative_control_table(frame)
    permutation = randomisation_inference(frame)

    evalues.to_csv(OUTPUT / "e_values.csv", index=False)
    grid.to_csv(OUTPUT / "unmeasured_confounder_grid.csv", index=False)
    frontier.to_csv(OUTPUT / "unmeasured_confounder_frontier.csv", index=False)
    negative.to_csv(OUTPUT / "negative_control_outcomes.csv", index=False)
    permutation.to_csv(OUTPUT / "randomisation_inference.csv", index=False)

    primary = evalues[evalues["threshold_hours"] == PRIMARY_THRESHOLD].iloc[0]
    primary_permutation = permutation[
        permutation["threshold_hours"] == PRIMARY_THRESHOLD
    ].iloc[0]
    failed = negative[~negative["passes_null_expectation"]]
    summary = {
        "cohort_prs": int(len(frame)),
        "primary_threshold_hours": PRIMARY_THRESHOLD,
        "adjusted_risk_difference": float(primary["adjusted_risk_difference"]),
        "approximate_risk_ratio": float(primary["approximate_risk_ratio"]),
        "e_value_point": float(primary["e_value_point"]),
        "e_value_limit": float(primary["e_value_limit"]),
        "permutation_p_value_two_sided": float(
            primary_permutation["permutation_p_value_two_sided"]
        ),
        "negative_control_models": int(len(negative)),
        "negative_control_models_failing_null": int(len(failed)),
        "negative_control_failures": failed[
            ["threshold_hours", "negative_control_outcome", "estimate"]
        ].to_dict("records"),
        "all_thresholds_e_value_above_two": bool((evalues["e_value_point"] > 2.0).all()),
        "scope": (
            "sensitivity bounds for an observational association; no causal claim, "
            "no semantic resolution claim"
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
