"""Two extensions that answer the strongest objections to RQ3.

**A. Whole-population timing.** The landmark cohort keeps only PRs still open at
hour 48, which is most of the population removed. This part drops that
restriction. It follows every cross-product inline-trigger PR from its trigger
and models the hazard of merge in discrete time, with the exact addressed edge
entering as a time-varying covariate: a PR contributes unexposed person-time
until its first exact reply and exposed person-time afterwards. That is the
standard way to avoid crediting the exposure with time that elapsed before it
happened.

**B. Does the bridge's history matter?** RQ2 finds that visible human bridges
usually have earlier review history in the repository. RQ3 finds that an exact
reply marks later merge. The obvious joint question is whether the edge behaves
differently when the person who writes it already knows the repository. This
part splits the exposure by the replier's strict prior review history and refits
the primary model.

Neither part identifies a causal effect.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from multiagent_impact.cross_agent_review import (  # noqa: E402
    AGENT_ACCOUNT_ALIASES,
    INTERACTION_CUTOFF,
    parse_timestamp,
)
from scripts.analysis.run_addressed_edge_landmark_analysis import (  # noqa: E402
    add_pretrigger_features,
)

DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
CHAIN = ROOT / "outputs" / "cross_agent_review"
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
OUTPUT = ROOT / "outputs" / "rq3_extensions"

HORIZON_DAYS = 30
EXPECTED_WHOLE_POPULATION = 3_942
EXPECTED_LANDMARK_ROWS = 1_067

# Day boundaries for the discrete-time hazard. Early bins are short because most
# pull requests resolve quickly.
BIN_EDGES = (0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 14.0, 21.0, 30.0)

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


# ---------------------------------------------------------------------------
# Shared inputs
# ---------------------------------------------------------------------------


def whole_population() -> pl.DataFrame:
    """Every cross-product inline trigger with a complete 30-day horizon."""
    chains = pl.read_parquet(CHAIN / "cross_feedback_response_chains.parquet")
    cohort = (
        chains.filter(
            (pl.col("trigger_source") == "inline_review_comment")
            & (pl.col("author_agent") != pl.col("trigger_reviewer_agent"))
            & (
                pl.col("trigger_dt")
                <= pl.lit(INTERACTION_CUTOFF - timedelta(days=HORIZON_DAYS))
            )
        )
        .select(
            "pr_id",
            "repo_id",
            "trigger_dt",
            "trigger_event_id",
            "author_agent",
            "trigger_reviewer_agent",
            "closed_dt",
            "merged_dt",
        )
        .with_columns(pl.col("trigger_dt").dt.strftime("%Y-%m").alias("trigger_month"))
        .unique("pr_id")
        .sort("pr_id")
    )
    if cohort.height != EXPECTED_WHOLE_POPULATION:
        raise AssertionError(
            f"Whole-population drift: {cohort.height} != {EXPECTED_WHOLE_POPULATION}"
        )
    return cohort


def first_exact_reply(cohort: pl.DataFrame) -> pl.DataFrame:
    """First exact-parent reply per PR, with no time restriction."""
    events = pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet")
    direct = (
        events.filter(pl.col("response_source") == "direct_inline_reply")
        .join(
            cohort.select("pr_id", "trigger_event_id", "trigger_dt"),
            on=["pr_id", "trigger_event_id", "trigger_dt"],
            how="inner",
        )
        .filter(pl.col("hours_after_trigger") > 0)
    )
    return (
        direct.sort(["pr_id", "response_dt", "response_event_id"])
        .group_by("pr_id")
        .agg(
            pl.col("response_dt").min().alias("first_edge_dt"),
            pl.col("hours_after_trigger").min().alias("first_edge_hours"),
        )
    )


# ---------------------------------------------------------------------------
# Part A: discrete-time hazard on the whole population
# ---------------------------------------------------------------------------


def build_person_period(cohort: pl.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    edges = first_exact_reply(cohort)
    frame = cohort.join(edges, on="pr_id", how="left")

    horizon = pl.col("trigger_dt") + timedelta(days=HORIZON_DAYS)
    frame = frame.with_columns(
        pl.min_horizontal(
            pl.coalesce([pl.col("closed_dt"), horizon]),
            horizon,
            pl.lit(INTERACTION_CUTOFF),
        ).alias("exit_dt")
    ).with_columns(
        (
            (pl.col("exit_dt") - pl.col("trigger_dt")).dt.total_seconds() / 86400.0
        ).alias("exit_days"),
        (
            pl.col("merged_dt").is_not_null()
            & (pl.col("merged_dt") > pl.col("trigger_dt"))
            & (pl.col("merged_dt") <= horizon)
        ).alias("merged_in_horizon"),
    ).with_columns(
        pl.when(pl.col("merged_in_horizon"))
        .then(
            (pl.col("merged_dt") - pl.col("trigger_dt")).dt.total_seconds() / 86400.0
        )
        .otherwise(None)
        .alias("merge_days"),
        pl.when(pl.col("first_edge_dt").is_not_null())
        .then(
            (pl.col("first_edge_dt") - pl.col("trigger_dt")).dt.total_seconds() / 86400.0
        )
        .otherwise(None)
        .alias("edge_days"),
    )

    # A merge ends follow-up. Anything that leaves earlier is censored there.
    frame = frame.with_columns(
        pl.when(pl.col("merged_in_horizon"))
        .then(pl.col("merge_days"))
        .otherwise(pl.col("exit_days"))
        .clip(0.0, float(HORIZON_DAYS))
        .alias("follow_up_days")
    )

    pandas_frame = frame.to_pandas()
    rows = []
    for record in pandas_frame.itertuples(index=False):
        end = float(record.follow_up_days)
        if end <= 0:
            continue
        merged = bool(record.merged_in_horizon)
        edge_days = record.edge_days
        for index in range(len(BIN_EDGES) - 1):
            low, high = BIN_EDGES[index], BIN_EDGES[index + 1]
            if low >= end:
                break
            # The PR is at risk in this bin; it experiences the event only if it
            # merged inside the bin.
            event = int(merged and low < end <= high)
            exposed = int(
                edge_days is not None
                and not pd.isna(edge_days)
                and float(edge_days) <= low
            )
            rows.append(
                {
                    "pr_id": record.pr_id,
                    "repo_id": record.repo_id,
                    "author_agent": record.author_agent,
                    "trigger_reviewer_agent": record.trigger_reviewer_agent,
                    "trigger_month": record.trigger_month,
                    "bin_index": index,
                    "edge_active": exposed,
                    "merged_in_bin": event,
                }
            )
            if event:
                break
    person_period = pd.DataFrame(rows)

    checks = {
        "prs": int(len(pandas_frame)),
        "prs_with_any_exact_edge": int(pandas_frame["edge_days"].notna().sum()),
        "prs_merged_within_horizon": int(pandas_frame["merged_in_horizon"].sum()),
        "person_period_rows": int(len(person_period)),
        "exposed_person_period_rows": int(person_period["edge_active"].sum()),
        "events": int(person_period["merged_in_bin"].sum()),
        "edges_observed_after_hour_48": int(
            (pandas_frame["edge_days"] > 2.0).sum()
        ),
        "exposure_is_time_varying": True,
    }
    if checks["events"] != checks["prs_merged_within_horizon"]:
        raise AssertionError("Every merge inside the horizon must appear exactly once.")
    return person_period, checks


def fit_hazard(person_period: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    merged = person_period.merge(controls, on="pr_id", how="left", validate="m:1")
    if merged[PRETRIGGER_CONTROLS].isna().any().any():
        raise AssertionError("A pre-trigger control is missing on the whole population.")

    rows = []
    specifications = [
        ("A_baseline_hazard_only", ["C(bin_index)"]),
        ("B_products_and_month", ["C(bin_index)", *BASE_CATEGORICAL]),
        (
            "C_full_pretrigger",
            ["C(bin_index)", *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS],
        ),
    ]
    for name, terms in specifications:
        formula = "merged_in_bin ~ " + " + ".join(["edge_active", *terms])
        endog, design = dmatrices(formula, merged, return_type="dataframe")
        groups = merged.loc[design.index, "repo_id"]
        model = sm.GLM(
            endog.iloc[:, 0], design, family=sm.families.Binomial()
        ).fit(cov_type="cluster", cov_kwds={"groups": groups})
        interval = model.conf_int().loc["edge_active"]
        rows.append(
            {
                "specification": name,
                "term": "edge_active",
                "log_odds": float(model.params["edge_active"]),
                "hazard_odds_ratio": float(np.exp(model.params["edge_active"])),
                "or_ci_low": float(np.exp(interval.iloc[0])),
                "or_ci_high": float(np.exp(interval.iloc[1])),
                "p_value": float(model.pvalues["edge_active"]),
                "person_period_rows": int(model.nobs),
                "prs": int(merged["pr_id"].nunique()),
                "repositories": int(groups.nunique()),
                "formula": formula,
                "interpretation": (
                    "discrete-time hazard of merge within 30 days of the trigger; the "
                    "exposure is time-varying, so no pre-edge time is credited to the "
                    "edge; observational, not a causal effect"
                ),
            }
        )
    return pd.DataFrame(rows)


def landmark_comparison(person_period: pd.DataFrame) -> pd.DataFrame:
    """Descriptive bridge between the landmark cohort and the whole population."""
    by_bin = (
        person_period.groupby(["bin_index", "edge_active"], observed=True)
        .agg(
            person_periods=("merged_in_bin", "size"),
            merges=("merged_in_bin", "sum"),
        )
        .reset_index()
    )
    by_bin["bin_start_days"] = by_bin["bin_index"].map(
        {index: BIN_EDGES[index] for index in range(len(BIN_EDGES) - 1)}
    )
    by_bin["bin_end_days"] = by_bin["bin_index"].map(
        {index: BIN_EDGES[index + 1] for index in range(len(BIN_EDGES) - 1)}
    )
    by_bin["merge_hazard"] = by_bin["merges"] / by_bin["person_periods"]
    return by_bin


# ---------------------------------------------------------------------------
# Part B: does the bridge's repository history change the edge?
# ---------------------------------------------------------------------------


def edge_author_history() -> tuple[pd.DataFrame, dict[str, object]]:
    cohort = pl.read_parquet(EDGE / "analysis_cohort.parquet")
    if cohort.height != EXPECTED_LANDMARK_ROWS:
        raise AssertionError("Landmark cohort drift in the interaction analysis.")

    audit = pl.read_parquet(EDGE / "exact_parent_reply_event_audit.parquet")
    events = pl.read_parquet(CHAIN / "cross_feedback_response_events.parquet").select(
        "pr_id",
        "response_event_id",
        "response_user",
        "response_user_type",
        "response_actor_role",
        "response_dt",
    )
    first_edge = (
        audit.join(events, on=["pr_id", "response_event_id"], how="left", validate="1:1")
        .sort(["pr_id", "response_dt", "response_event_id"])
        .group_by("pr_id")
        .first()
        .select(
            "pr_id",
            "response_user",
            "response_user_type",
            "response_actor_role",
        )
        .with_columns(pl.col("response_user").str.to_lowercase().alias("login"))
    )

    pr_repo = cohort.select(
        pl.col("pr_id").alias("history_pr_id"), "repo_id"
    )
    all_pr_repo = (
        pl.read_parquet(DATA / "pull_request.parquet", columns=["id", "repo_id"])
        .rename({"id": "history_pr_id"})
    )
    history = (
        pl.read_parquet(
            DATA / "pr_reviews.parquet",
            columns=["pr_id", "user", "user_type", "submitted_at"],
        )
        .with_columns(
            parse_timestamp("submitted_at", "review_dt"),
            pl.col("user").str.to_lowercase().alias("login"),
        )
        .with_columns(
            pl.col("login")
            .replace_strict(AGENT_ACCOUNT_ALIASES, default=None)
            .alias("mapped_agent")
        )
        .filter(
            (pl.col("user_type").str.to_lowercase() == "user")
            & pl.col("mapped_agent").is_null()
            & pl.col("review_dt").is_not_null()
            & pl.col("login").is_not_null()
        )
        .rename({"pr_id": "history_pr_id"})
        .join(all_pr_repo, on="history_pr_id", how="inner")
        .select("history_pr_id", "repo_id", "login", "review_dt")
    )

    targets = (
        cohort.select("pr_id", "repo_id", "trigger_dt")
        .join(first_edge, on="pr_id", how="inner")
    )
    candidates = targets.join(history, on=["repo_id", "login"], how="inner")
    valid = candidates.filter(
        (pl.col("history_pr_id") != pl.col("pr_id"))
        & (pl.col("review_dt") < pl.col("trigger_dt"))
    )
    prior = valid.group_by("pr_id").agg(
        pl.col("history_pr_id").n_unique().alias("prior_review_prs")
    )
    enriched = (
        targets.join(prior, on="pr_id", how="left")
        .with_columns(pl.col("prior_review_prs").fill_null(0))
        .with_columns(
            (pl.col("prior_review_prs") > 0).alias("edge_author_prior_reviewer")
        )
    )

    is_user = pl.col("response_user_type").str.to_lowercase() == "user"
    labelled = enriched.with_columns(
        pl.when(~is_user)
        .then(pl.lit("edge_by_automation"))
        .when(pl.col("edge_author_prior_reviewer"))
        .then(pl.lit("edge_by_known_reviewer"))
        .otherwise(pl.lit("edge_by_newcomer"))
        .alias("edge_class")
    )

    frame = (
        cohort.join(
            labelled.select("pr_id", "edge_class", "prior_review_prs"),
            on="pr_id",
            how="left",
        )
        .with_columns(
            pl.col("edge_class").fill_null("no_edge"),
            pl.col("prior_review_prs").fill_null(0),
        )
        .to_pandas()
    )
    frame["merged_from_48h_to_30d"] = frame["merged_from_48h_to_30d"].astype(int)

    counts = frame["edge_class"].value_counts().to_dict()
    checks = {
        "landmark_prs": int(len(frame)),
        "exposed_prs": int((frame["edge_class"] != "no_edge").sum()),
        "class_counts": {key: int(value) for key, value in counts.items()},
        "history_rule": (
            "same repository, different PR, user-account submitted review strictly "
            "before the trigger"
        ),
    }
    if checks["exposed_prs"] != 109:
        raise AssertionError("Edge-class assignment lost or gained an exposed PR.")
    return frame, checks


def fit_interaction(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    formula = (
        "merged_from_48h_to_30d ~ C(edge_class, Treatment('no_edge')) + "
        + " + ".join([*BASE_CATEGORICAL, *PRETRIGGER_CONTROLS])
    )
    endog, design = dmatrices(formula, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    model = sm.OLS(endog.iloc[:, 0], design).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True}
    )

    rows = []
    intervals = model.conf_int()
    for term in model.params.index:
        if not term.startswith("C(edge_class"):
            continue
        label = term.split("T.")[-1].rstrip("]")
        cell = frame[frame["edge_class"] == label]
        rows.append(
            {
                "edge_class": label,
                "reference": "no_edge",
                "prs": int(len(cell)),
                "raw_later_merge_rate": float(cell["merged_from_48h_to_30d"].mean()),
                "estimate": float(model.params[term]),
                "ci_low": float(intervals.loc[term, 0]),
                "ci_high": float(intervals.loc[term, 1]),
                "p_value": float(model.pvalues[term]),
            }
        )
    contrasts = pd.DataFrame(rows)

    known = [t for t in model.params.index if "edge_by_known_reviewer" in t]
    newcomer = [t for t in model.params.index if "edge_by_newcomer" in t]
    if len(known) != 1 or len(newcomer) != 1:
        raise AssertionError("Expected exactly one term per user-written edge class.")
    difference = np.zeros(len(model.params))
    difference[list(model.params.index).index(known[0])] = 1.0
    difference[list(model.params.index).index(newcomer[0])] = -1.0
    test = model.t_test(difference)
    moderation = pd.DataFrame(
        [
            {
                "comparison": "edge_by_known_reviewer minus edge_by_newcomer",
                "estimate": float(np.ravel(test.effect)[0]),
                "standard_error": float(np.ravel(test.sd)[0]),
                "ci_low": float(np.ravel(test.conf_int())[0]),
                "ci_high": float(np.ravel(test.conf_int())[1]),
                "p_value": float(np.ravel(test.pvalue)[0]),
                "n_prs": int(model.nobs),
                "repositories": int(groups.nunique()),
                "interpretation": (
                    "difference between two adjusted contrasts, both against the "
                    "no-edge reference; a null result means the trace does not show "
                    "that repository familiarity changes what the edge marks"
                ),
            }
        ]
    )
    contrasts["formula"] = formula
    return contrasts, moderation


def moderation_robustness(frame: pd.DataFrame) -> pd.DataFrame:
    """Is the history split carried by one repository, one pair, or the model?

    A large split on 96 user-written edges needs to be shown to be stable before
    it is reported, so this refits it with repository fixed effects, drops each
    ordered product pair in turn, and drops each repository in turn.
    """
    base = [*BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    exposure = "C(edge_class, Treatment('no_edge'))"

    def difference(sample: pd.DataFrame, terms: list[str]) -> tuple[float, float, float]:
        formula = f"merged_from_48h_to_30d ~ {exposure} + " + " + ".join(terms)
        endog, design = dmatrices(formula, sample, return_type="dataframe")
        groups = sample.loc[design.index, "repo_id"]
        model = sm.OLS(endog.iloc[:, 0], design).fit(
            cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True}
        )
        names = list(model.params.index)
        known = [t for t in names if "edge_by_known_reviewer" in t]
        newcomer = [t for t in names if "edge_by_newcomer" in t]
        if len(known) != 1 or len(newcomer) != 1:
            raise RuntimeError("edge-class terms missing")
        contrast = np.zeros(len(names))
        contrast[names.index(known[0])] = 1.0
        contrast[names.index(newcomer[0])] = -1.0
        test = model.t_test(contrast)
        bounds = np.ravel(test.conf_int())
        return float(np.ravel(test.effect)[0]), float(bounds[0]), float(bounds[1])

    rows = []
    estimate, low, high = difference(frame, base)
    rows.append(
        {
            "check": "Primary",
            "detail": "pre-trigger adjusted",
            "estimate": estimate,
            "ci_low": low,
            "ci_high": high,
            "n_prs": int(len(frame)),
        }
    )
    estimate, low, high = difference(frame, [*base, "C(repo_id)"])
    rows.append(
        {
            "check": "Repository fixed effects",
            "detail": "within-repository comparison only",
            "estimate": estimate,
            "ci_low": low,
            "ci_high": high,
            "n_prs": int(len(frame)),
        }
    )

    pair_results = []
    for pair in sorted(frame["ordered_product_pair"].unique()):
        sample = frame[frame["ordered_product_pair"] != pair]
        if sample["edge_class"].nunique() < 4:
            continue
        try:
            pair_results.append(difference(sample, base)[0])
        except RuntimeError:
            continue
    rows.append(
        {
            "check": "Leave one ordered product pair out",
            "detail": f"{len(pair_results)} refits",
            "estimate": float(np.median(pair_results)),
            "ci_low": float(np.min(pair_results)),
            "ci_high": float(np.max(pair_results)),
            "n_prs": int(len(frame)),
        }
    )

    repo_results = []
    exposed_repos = sorted(
        frame.loc[frame["edge_class"] != "no_edge", "repo_id"].unique()
    )
    for repo in exposed_repos:
        sample = frame[frame["repo_id"] != repo]
        if sample["edge_class"].nunique() < 4:
            continue
        try:
            repo_results.append(difference(sample, base)[0])
        except RuntimeError:
            continue
    rows.append(
        {
            "check": "Leave one exposed repository out",
            "detail": f"{len(repo_results)} refits",
            "estimate": float(np.median(repo_results)),
            "ci_low": float(np.min(repo_results)),
            "ci_high": float(np.max(repo_results)),
            "n_prs": int(len(frame)),
        }
    )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    cohort = whole_population()
    person_period, hazard_checks = build_person_period(cohort)
    controls = add_pretrigger_features(cohort)[0].to_pandas()[
        ["pr_id", *PRETRIGGER_CONTROLS]
    ]
    hazard = fit_hazard(person_period, controls)
    hazard_profile = landmark_comparison(person_period)

    interaction_frame, interaction_checks = edge_author_history()
    contrasts, moderation = fit_interaction(interaction_frame)
    robustness = moderation_robustness(interaction_frame)

    hazard.to_csv(OUTPUT / "whole_population_hazard.csv", index=False)
    hazard_profile.to_csv(OUTPUT / "hazard_profile_by_bin.csv", index=False)
    contrasts.to_csv(OUTPUT / "edge_class_contrasts.csv", index=False)
    moderation.to_csv(OUTPUT / "history_moderation_test.csv", index=False)
    robustness.to_csv(OUTPUT / "history_moderation_robustness.csv", index=False)

    primary = hazard[hazard["specification"] == "C_full_pretrigger"].iloc[0]
    summary = {
        "whole_population": hazard_checks,
        "hazard_primary": {
            "odds_ratio": float(primary["hazard_odds_ratio"]),
            "ci_low": float(primary["or_ci_low"]),
            "ci_high": float(primary["or_ci_high"]),
            "p_value": float(primary["p_value"]),
        },
        "interaction": interaction_checks,
        "moderation": moderation.iloc[0].to_dict(),
        "moderation_robustness": robustness.to_dict("records"),
        "scope": "observational extensions to RQ3; no causal claim",
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))
    print()
    print(hazard[["specification", "hazard_odds_ratio", "or_ci_low", "or_ci_high", "p_value"]].to_string(index=False))
    print()
    print(contrasts[["edge_class", "prs", "raw_later_merge_rate", "estimate", "ci_low", "ci_high"]].to_string(index=False))


if __name__ == "__main__":
    main()
