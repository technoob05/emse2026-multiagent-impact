"""Make the RQ3 exposure and cohort say what they actually are.

Two facts are recoverable from the frozen artifacts but were not reported:

1. **Who writes the addressed edge.** The exposure is "a later comment whose
   parent identifier is the trigger's own identifier". It does not require the
   replier to be another product. This script classifies every exposed reply
   event by actor role and refits the primary model under stricter exposure
   definitions, including one that drops replies written by the triggering
   product itself.

2. **Who the landmark cohort leaves out.** The cohort keeps PRs still open at
   hour 48. Cross-product inline-trigger PRs that closed earlier are outside it.
   This script measures that excluded mass and reports the whole-eligible
   population later-merge contrast that does not condition on being open, so
   the restriction is visible instead of implied.

Neither section changes an existing estimate. Both make the scope of the
reported estimate auditable.
"""

from __future__ import annotations

import json
from datetime import timedelta
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.cross_agent_review import INTERACTION_CUTOFF  # noqa: E402

CHAIN = ROOT / "outputs" / "cross_agent_review"
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
OUTPUT = ROOT / "outputs" / "addressed_edge_scope"

PRIMARY_THRESHOLD = 48
EXPECTED_COHORT_ROWS = 1_067
EXPECTED_EXPOSED_PRS = 109
EXPECTED_EXPOSURE_EVENTS = 128

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

# Actor roles as classified upstream in the response-event table.
HUMAN_ROLES = {"author_account", "other_human"}
TRIGGERING_BRAND = "triggering_reviewer_brand"
DIFFERENT_PRODUCT_ROLES = {"other_agent_brand", "author_agent_brand"}


def load_exposure_events() -> pl.DataFrame:
    audit = pl.read_parquet(EDGE / "exact_parent_reply_event_audit.parquet")
    if audit.height != EXPECTED_EXPOSURE_EVENTS:
        raise AssertionError(
            f"Exposure event drift: {audit.height} != {EXPECTED_EXPOSURE_EVENTS}"
        )
    events = pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet").select(
        "pr_id",
        "response_event_id",
        "response_user_type",
        "response_actor_role",
        "response_dt",
    )
    joined = audit.join(
        events,
        on=["pr_id", "response_event_id"],
        how="left",
        validate="1:1",
    )
    if joined["response_actor_role"].null_count():
        raise AssertionError("An exposure event has no classified actor role.")
    if joined["pr_id"].n_unique() != EXPECTED_EXPOSED_PRS:
        raise AssertionError("Exposed-PR count drift in the exposure event audit.")
    return joined


def composition_tables(events: pl.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    by_event = (
        events.group_by("response_actor_role")
        .agg(pl.len().alias("events"), pl.col("pr_id").n_unique().alias("prs"))
        .sort("events", descending=True)
        .with_columns(
            (pl.col("events") / events.height).alias("share_of_exposure_events")
        )
        .to_pandas()
    )
    first = (
        events.sort(["pr_id", "response_dt", "response_event_id"])
        .group_by("pr_id")
        .first()
    )
    by_pr = (
        first.group_by("response_actor_role")
        .agg(pl.len().alias("prs"))
        .sort("prs", descending=True)
        .with_columns((pl.col("prs") / first.height).alias("share_of_exposed_prs"))
        .to_pandas()
    )
    return by_event, by_pr


def build_alternative_exposures(events: pl.DataFrame) -> pd.DataFrame:
    """One row per PR with a nested family of stricter exposure flags."""
    flagged = events.with_columns(
        pl.col("response_actor_role").is_in(list(HUMAN_ROLES)).alias("is_human"),
        pl.col("response_actor_role").ne(TRIGGERING_BRAND).alias("is_not_self_brand"),
        pl.col("response_actor_role")
        .is_in(list(DIFFERENT_PRODUCT_ROLES))
        .alias("is_different_product"),
    )
    per_pr = flagged.group_by("pr_id").agg(
        pl.lit(True).alias("edge_any"),
        pl.col("is_not_self_brand").any().alias("edge_excluding_self_brand"),
        pl.col("is_human").any().alias("edge_human_reply"),
        pl.col("is_different_product").any().alias("edge_different_product"),
    )
    return per_pr.to_pandas()


def load_cohort(alternatives: pd.DataFrame) -> pd.DataFrame:
    frame = pl.read_parquet(EDGE / "analysis_cohort.parquet").to_pandas()
    if len(frame) != EXPECTED_COHORT_ROWS:
        raise AssertionError(f"Landmark cohort drift: {len(frame)}")
    frame = frame.merge(alternatives, on="pr_id", how="left")
    for column in (
        "edge_any",
        "edge_excluding_self_brand",
        "edge_human_reply",
        "edge_different_product",
    ):
        frame[column] = frame[column].fillna(False).astype(int)
    frame["merged_from_48h_to_30d"] = frame["merged_from_48h_to_30d"].astype(int)
    primary = frame[f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"].astype(int)
    if not (frame["edge_any"] == primary).all():
        raise AssertionError(
            "Reconstructed exposure disagrees with the frozen 48-hour exposure flag."
        )
    return frame


def fit(frame: pd.DataFrame, exposure: str) -> dict[str, object]:
    formula = f"merged_from_48h_to_30d ~ " + " + ".join(
        [exposure, *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    )
    endog, design = dmatrices(formula, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    model = sm.OLS(endog.iloc[:, 0], design).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True}
    )
    interval = model.conf_int().loc[exposure]
    exposed = frame[frame[exposure].astype(bool)]
    unexposed = frame[~frame[exposure].astype(bool)]
    return {
        "exposure": exposure,
        "exposed_prs": int(len(exposed)),
        "unexposed_prs": int(len(unexposed)),
        "exposed_raw_merge_rate": float(exposed["merged_from_48h_to_30d"].mean()),
        "unexposed_raw_merge_rate": float(unexposed["merged_from_48h_to_30d"].mean()),
        "estimate": float(model.params[exposure]),
        "ci_low": float(interval.iloc[0]),
        "ci_high": float(interval.iloc[1]),
        "p_value": float(model.pvalues[exposure]),
        "n_prs": int(model.nobs),
        "repositories": int(groups.nunique()),
    }


def exposure_definition_models(frame: pd.DataFrame) -> pd.DataFrame:
    definitions = [
        (
            "edge_any",
            "Any exact parent reply (primary)",
            "the reported exposure; it does not require the replier to be another product",
        ),
        (
            "edge_excluding_self_brand",
            "Exact reply, excluding the triggering product's own reply",
            "removes replies written by the same product that wrote the trigger",
        ),
        (
            "edge_human_reply",
            "Exact reply written by a user account",
            "restricts the edge to a human acknowledgement",
        ),
    ]
    rows = []
    for column, label, note in definitions:
        row = fit(frame, column)
        row["definition"] = label
        row["definition_note"] = note
        rows.append(row)

    different = int(frame["edge_different_product"].sum())
    rows.append(
        {
            "exposure": "edge_different_product",
            "definition": "Exact reply written by a different mapped product",
            "definition_note": (
                "not modelled: too few exposed PRs to support a clustered estimate; "
                "the count is the result"
            ),
            "exposed_prs": different,
            "unexposed_prs": int(len(frame) - different),
            "exposed_raw_merge_rate": float(
                frame.loc[frame["edge_different_product"].astype(bool), "merged_from_48h_to_30d"].mean()
            )
            if different
            else float("nan"),
            "unexposed_raw_merge_rate": float(
                frame.loc[~frame["edge_different_product"].astype(bool), "merged_from_48h_to_30d"].mean()
            ),
            "estimate": None,
            "ci_low": None,
            "ci_high": None,
            "p_value": None,
            "n_prs": int(len(frame)),
            "repositories": int(frame["repo_id"].nunique()),
        }
    )
    return pd.DataFrame(rows)


def cohort_selection_audit() -> tuple[pd.DataFrame, dict[str, object]]:
    """Measure what the hour-48 landmark restriction removes."""
    # The landmark builder starts from the response-chain table and keeps only
    # triggers with a complete 30-day outcome horizon, so the funnel has to use
    # the same base or its stages will not reconcile with the cohort.
    chains = pl.read_parquet(CHAIN / "cross_feedback_response_chains.parquet")
    inline_cross = (
        chains.filter(
            (pl.col("trigger_source") == "inline_review_comment")
            & (pl.col("author_agent") != pl.col("trigger_reviewer_agent"))
            & (pl.col("trigger_dt") <= pl.lit(INTERACTION_CUTOFF - timedelta(days=30)))
        )
        .with_columns((pl.col("trigger_dt") + timedelta(hours=48)).alias("landmark_dt"))
    )

    closed_early = inline_cross.filter(
        pl.col("closed_dt").is_not_null()
        & (pl.col("closed_dt") <= pl.col("landmark_dt"))
    )
    merged_early = inline_cross.filter(
        pl.col("merged_dt").is_not_null()
        & (pl.col("merged_dt") <= pl.col("landmark_dt"))
    )
    open_at_landmark = inline_cross.height - closed_early.height

    if open_at_landmark != EXPECTED_COHORT_ROWS:
        raise AssertionError(
            "Landmark funnel does not reconcile with the analysis cohort: "
            f"{open_at_landmark} open at hour 48 but {EXPECTED_COHORT_ROWS} analysed"
        )

    rows = [
        {
            "stage": "Cross-product inline triggers with a 30-day horizon",
            "prs": inline_cross.height,
            "share_of_inline_triggers": 1.0,
        },
        {
            "stage": "Closed at or before hour 48",
            "prs": closed_early.height,
            "share_of_inline_triggers": closed_early.height / inline_cross.height,
        },
        {
            "stage": "Merged at or before hour 48",
            "prs": merged_early.height,
            "share_of_inline_triggers": merged_early.height / inline_cross.height,
        },
        {
            "stage": "Still open at hour 48",
            "prs": open_at_landmark,
            "share_of_inline_triggers": open_at_landmark / inline_cross.height,
        },
    ]
    summary = {
        "inline_cross_product_triggers": int(inline_cross.height),
        "closed_by_hour_48": int(closed_early.height),
        "merged_by_hour_48": int(merged_early.height),
        "still_open_at_hour_48": int(open_at_landmark),
        "landmark_cohort_prs": EXPECTED_COHORT_ROWS,
        "landmark_cohort_share_of_inline_triggers": float(
            EXPECTED_COHORT_ROWS / inline_cross.height
        ),
        "interpretation": (
            "the landmark cohort is the slower-resolving remainder of the cross-product "
            "inline-trigger population; most such PRs close before the outcome window opens"
        ),
    }
    return pd.DataFrame(rows), summary


def conditional_randomisation(frame: pd.DataFrame, permutations: int = 2000) -> dict[str, object]:
    """Randomisation inference restricted to repositories that can be permuted.

    Permuting inside repositories that have no exposure variation leaves their
    contribution fixed in every draw, so an unconditional permutation of a
    model without repository fixed effects has a reference distribution that is
    not centred at zero: the between-repository part of the coefficient is
    invariant to a within-repository permutation. This test therefore restricts
    the fit to repositories that can actually be re-randomised and identifies
    the coefficient from within-repository variation only.
    """
    exposure = f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"
    varying = frame.groupby("repo_id")[exposure].nunique().gt(1)
    keep = frame["repo_id"].isin(varying[varying].index)
    subset = frame.loc[keep].copy()
    subset[exposure] = subset[exposure].astype(int)

    formula = f"merged_from_48h_to_30d ~ " + " + ".join(
        [exposure, *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS, "C(repo_id)"]
    )
    endog, design = dmatrices(formula, subset, return_type="dataframe")
    y = endog.iloc[:, 0].to_numpy()
    x = design.to_numpy()
    column = list(design.columns).index(exposure)
    observed = float(np.linalg.lstsq(x, y, rcond=None)[0][column])

    repo = subset.loc[design.index, "repo_id"].to_numpy()
    values = x[:, column].copy()
    order = np.argsort(repo, kind="stable")
    blocks = np.split(order, np.flatnonzero(np.diff(repo[order])) + 1)
    generator = np.random.default_rng(20260826)
    draws = np.empty(permutations)
    permuted_design = x.copy()
    for index in range(permutations):
        permuted = values.copy()
        for block in blocks:
            permuted[block] = generator.permutation(values[block])
        permuted_design[:, column] = permuted
        draws[index] = np.linalg.lstsq(permuted_design, y, rcond=None)[0][column]

    return {
        "threshold_hours": PRIMARY_THRESHOLD,
        "scope": (
            "repositories with within-repository exposure variation, with repository "
            "fixed effects so the coefficient uses within-repository variation only"
        ),
        "repositories": int(subset["repo_id"].nunique()),
        "n_prs": int(len(subset)),
        "exposed_prs": int(subset[exposure].sum()),
        "observed_estimate": observed,
        "permutations": permutations,
        "permutation_mean": float(draws.mean()),
        "permutation_sd": float(draws.std(ddof=1)),
        "permutation_p_value_two_sided": float(
            (1 + np.sum(np.abs(draws - draws.mean()) >= abs(observed - draws.mean()) - 1e-12))
            / (permutations + 1)
        ),
        "interpretation": (
            "conditional randomisation test; the reference distribution is centred because "
            "every retained repository can actually be re-randomised"
        ),
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    events = load_exposure_events()
    by_event, by_pr = composition_tables(events)
    alternatives = build_alternative_exposures(events)
    frame = load_cohort(alternatives)
    definitions = exposure_definition_models(frame)
    selection, selection_summary = cohort_selection_audit()
    conditional = conditional_randomisation(frame)

    by_event.to_csv(OUTPUT / "exposure_event_composition.csv", index=False)
    by_pr.to_csv(OUTPUT / "exposure_first_reply_composition.csv", index=False)
    definitions.to_csv(OUTPUT / "exposure_definition_models.csv", index=False)
    selection.to_csv(OUTPUT / "landmark_selection_funnel.csv", index=False)
    pd.DataFrame([conditional]).to_csv(
        OUTPUT / "conditional_randomisation_inference.csv", index=False
    )

    human_events = int(
        events.filter(pl.col("response_user_type") == "User").height
    )
    summary = {
        "exposure_events": int(events.height),
        "exposed_prs": int(events["pr_id"].n_unique()),
        "exposure_events_written_by_user_accounts": human_events,
        "exposure_events_written_by_the_triggering_product": int(
            events.filter(pl.col("response_actor_role") == TRIGGERING_BRAND).height
        ),
        "exposure_events_written_by_a_different_mapped_product": int(
            events.filter(
                pl.col("response_actor_role").is_in(list(DIFFERENT_PRODUCT_ROLES))
            ).height
        ),
        "landmark_selection": selection_summary,
        "conditional_randomisation": conditional,
        "scope": (
            "descriptive scope audit and exposure-definition sensitivity; no causal claim"
        ),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print()
    print(
        definitions[
            [
                "definition",
                "exposed_prs",
                "exposed_raw_merge_rate",
                "estimate",
                "ci_low",
                "ci_high",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
