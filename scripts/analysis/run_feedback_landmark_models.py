from __future__ import annotations

from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT = (
    PROJECT_ROOT
    / "outputs"
    / "cross_agent_review"
    / "feedback_48h_landmark_cohort.parquet"
)
OUTPUT = PROJECT_ROOT / "outputs" / "cross_agent_review"


def fit_lpm(frame: pd.DataFrame, repository_fixed_effects: bool) -> pd.DataFrame:
    loop_term = "C(early_loop_shape, Treatment('no_observed_response'))"
    controls = [
        "C(author_agent)",
        "C(trigger_reviewer_agent)",
        "C(trigger_source)",
        "C(trigger_month)",
    ]
    if repository_fixed_effects:
        controls.append("C(repo_url)")
    formula = "merged_from_48h_to_30d ~ " + " + ".join([loop_term, *controls])
    model = smf.ols(formula, data=frame).fit(
        cov_type="cluster", cov_kwds={"groups": frame["repo_url"]}
    )
    intervals = model.conf_int()
    result = pd.DataFrame(
        {
            "term": model.params.index,
            "estimate": model.params.values,
            "ci_low": intervals[0].values,
            "ci_high": intervals[1].values,
            "p_value": model.pvalues.values,
        }
    )
    result = result[result["term"].str.contains("early_loop_shape")].copy()
    result["specification"] = (
        "repository_fixed_effects"
        if repository_fixed_effects
        else "repo_clustered_controls"
    )
    result["n_prs"] = int(model.nobs)
    result["n_repositories"] = frame["repo_url"].nunique()
    return result


def main() -> None:
    frame = pd.read_parquet(INPUT)
    frame["merged_from_48h_to_30d"] = frame[
        "merged_from_48h_to_30d"
    ].astype(int)
    frame["trigger_month"] = (
        pd.to_datetime(frame["trigger_dt"], utc=True)
        .dt.tz_localize(None)
        .dt.to_period("M")
        .astype(str)
    )
    results = pd.concat(
        [fit_lpm(frame, False), fit_lpm(frame, True)], ignore_index=True
    )
    results.to_csv(OUTPUT / "feedback_48h_landmark_models.csv", index=False)
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()
