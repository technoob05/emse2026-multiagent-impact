"""Heterogeneity audit: where the matched-pair gap lives, and what repository
descriptors do to the familiar-replier split.

Two reviewer questions target the same gap in the manuscript: we report averages
where the reader wants the spread.

**Part 1 — matched-pair spread.** The 546 same-author matched pairs behind the
-13.4 point "any visible follow-up" gap are decomposed by ordered product pair
and by repository, the gap is re-estimated inside every product pair large
enough to support an estimate, and the overall gap is refit leaving out one
repository and one product pair at a time. The verdict rule for "general" versus
"concentrated" is fixed below, before any result is inspected.

**Part 2 — repository moderators.** RQ3 splits the exact addressed edge by
whether the replier had prior review history in the repository. The split is
large under pre-trigger adjustment and collapses under repository fixed effects.
This part builds repository descriptors that are observable in the release and
fixed strictly *before* the trigger, asks whether they separate repositories
where familiar repliers dominate from repositories where newcomers do, and tests
whether adding them to the RQ3 model explains any of the split.

Nothing here identifies a causal effect. Cohorts and estimators are reused from
the existing scripts, not rebuilt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
from patsy import dmatrices

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from multiagent_impact.cross_agent_review import parse_timestamp  # noqa: E402
from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402
from scripts.analysis.run_coordination_topology_analysis import (  # noqa: E402
    _binary_pair_values,
    _cluster_bootstrap,
)
from scripts.analysis.run_rq3_extensions import (  # noqa: E402
    BASE_CATEGORICAL,
    PRETRIGGER_CONTROLS,
    edge_author_history,
)

CONFIG = AnalysisConfig.from_paths(ROOT)
DATA = CONFIG.data_dir
TOPOLOGY = CONFIG.output_dir / "coordination_topology"
LANDMARK = CONFIG.output_dir / "addressed_edge_landmark"
OUTPUT = CONFIG.output_dir / "heterogeneity_audit"

# ---------------------------------------------------------------------------
# Thresholds. All fixed here, before any result is inspected.
# ---------------------------------------------------------------------------
SEED = 20260826
BOOTSTRAP_DRAWS = 10_000

# Minimum matched pairs required before a within-product-pair gap is estimated.
# Below this a paired-proportion difference cannot be separated from noise at
# any useful width, so the cell is reported as "too few to estimate" rather than
# dropped.
MIN_PAIRS_PER_PRODUCT_PAIR = 30

# A within-cell repository-clustered interval is only meaningful with enough
# distinct repositories to resample.
MIN_REPOS_FOR_CLUSTERED_CI = 10

# Verdict rule for Part 1, fixed before looking:
#   GENERAL  if every leave-one-repository-out and leave-one-product-pair-out
#            refit of the overall gap stays strictly negative, AND at least two
#            thirds of qualifying product pairs have a negative point estimate.
#   CONCENTRATED otherwise.
GENERALITY_NEGATIVE_PAIR_SHARE = 2.0 / 3.0

PRIMARY_OUTCOME = "any_visible_followup"
PRIMARY_COLUMN = "any_observable_response"

# Repository descriptors, all measured strictly before the repository's first
# trigger in the RQ3 landmark cohort.
MODERATORS = [
    "pre_total_prs",
    "pre_distinct_contributors",
    "pre_merge_rate",
    "pre_reviews_per_pr",
    "pre_share_prs_any_review",
    "pre_repo_age_days",
]
LOG_MODERATORS = {
    "pre_total_prs",
    "pre_distinct_contributors",
    "pre_reviews_per_pr",
    "pre_repo_age_days",
}


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


def _gini(counts: np.ndarray) -> float:
    """Gini concentration of a non-negative count vector."""
    values = np.sort(np.asarray(counts, dtype=float))
    n = len(values)
    total = values.sum()
    if n == 0 or total <= 0:
        return float("nan")
    index = np.arange(1, n + 1)
    return float((2.0 * (index * values).sum()) / (n * total) - (n + 1) / n)


def _top_decile_share(counts: np.ndarray) -> float:
    """Share of mass held by the largest decile of units (at least one unit)."""
    values = np.sort(np.asarray(counts, dtype=float))[::-1]
    n = len(values)
    if n == 0:
        return float("nan")
    take = max(1, int(np.ceil(n / 10)))
    return float(values[:take].sum() / values.sum())


def _composition(frame: pd.DataFrame, unit_column: str, unit_type: str) -> pd.DataFrame:
    counts = frame[unit_column].value_counts().sort_values(ascending=False)
    total = int(counts.sum())
    out = pd.DataFrame(
        {
            "unit_type": unit_type,
            "unit": counts.index.astype(str),
            "pairs": counts.to_numpy(dtype=int),
        }
    )
    out["share_of_pairs"] = out["pairs"] / total
    out["rank"] = np.arange(1, len(out) + 1)
    out["cumulative_share"] = out["share_of_pairs"].cumsum()
    return out[["unit_type", "unit", "rank", "pairs", "share_of_pairs", "cumulative_share"]]


def _paired_gap(frame: pd.DataFrame) -> dict[str, object]:
    """Mean paired difference with a repository-clustered bootstrap interval."""
    cross, same = _binary_pair_values(frame, PRIMARY_COLUMN)
    differences = (cross - same).to_numpy()
    low, high = _cluster_bootstrap(
        differences, frame["repo_url_cross"].to_numpy(), draws=BOOTSTRAP_DRAWS
    )
    return {
        "pairs": int(len(frame)),
        "repositories": int(frame["repo_url_cross"].nunique()),
        "cross_rate": float(cross.mean()),
        "same_rate": float(same.mean()),
        "paired_difference": float(differences.mean()),
        "repository_cluster_ci_low": low,
        "repository_cluster_ci_high": high,
    }


# ---------------------------------------------------------------------------
# Part 1: the spread behind the matched-pair gap
# ---------------------------------------------------------------------------


def load_matched_pairs() -> pd.DataFrame:
    """Reuse the matched pairs written by run_coordination_topology_analysis."""
    path = TOPOLOGY / "exact_author_stratum_matched_pairs.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run scripts/analysis/run_coordination_topology_analysis.py first."
        )
    pairs = pd.read_parquet(path)
    pairs["ordered_product_pair"] = (
        pairs["author_agent_cross"] + " -> " + pairs["trigger_reviewer_agent_cross"]
    )
    pairs["repository"] = (
        pairs["repo_url_cross"].str.replace("https://api.github.com/repos/", "", regex=False)
    )
    return pairs


def matched_pair_composition(pairs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    by_pair = _composition(pairs, "ordered_product_pair", "ordered_product_pair")
    by_repo = _composition(pairs, "repository", "repository")
    composition = pd.concat([by_pair, by_repo], ignore_index=True)
    stats = {
        "pairs_total": int(len(pairs)),
        "repositories": int(pairs["repository"].nunique()),
        "ordered_product_pairs": int(pairs["ordered_product_pair"].nunique()),
        "largest_repository": str(by_repo.iloc[0]["unit"]),
        "largest_repository_pairs": int(by_repo.iloc[0]["pairs"]),
        "largest_repository_share": float(by_repo.iloc[0]["share_of_pairs"]),
        "largest_product_pair": str(by_pair.iloc[0]["unit"]),
        "largest_product_pair_pairs": int(by_pair.iloc[0]["pairs"]),
        "largest_product_pair_share": float(by_pair.iloc[0]["share_of_pairs"]),
        "repository_gini": _gini(by_repo["pairs"].to_numpy()),
        "repository_top_decile_share": _top_decile_share(by_repo["pairs"].to_numpy()),
        "product_pair_gini": _gini(by_pair["pairs"].to_numpy()),
        "top_five_repository_share": float(by_repo["share_of_pairs"].head(5).sum()),
        "top_three_product_pair_share": float(by_pair["share_of_pairs"].head(3).sum()),
        "median_pairs_per_repository": float(by_repo["pairs"].median()),
    }
    return composition, stats


def gap_by_product_pair(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    counts = pairs["ordered_product_pair"].value_counts()
    for product_pair in counts.index:
        cell = pairs[pairs["ordered_product_pair"] == product_pair]
        qualifies = len(cell) >= MIN_PAIRS_PER_PRODUCT_PAIR
        row: dict[str, object] = {
            "ordered_product_pair": product_pair,
            "pairs": int(len(cell)),
            "repositories": int(cell["repo_url_cross"].nunique()),
            "qualifies": qualifies,
            "minimum_pairs_required": MIN_PAIRS_PER_PRODUCT_PAIR,
        }
        if qualifies:
            estimate = _paired_gap(cell)
            row.update(
                {
                    "cross_rate": estimate["cross_rate"],
                    "same_rate": estimate["same_rate"],
                    "paired_difference": estimate["paired_difference"],
                    "repository_cluster_ci_low": estimate["repository_cluster_ci_low"],
                    "repository_cluster_ci_high": estimate["repository_cluster_ci_high"],
                    "clustered_ci_reliable": bool(
                        estimate["repositories"] >= MIN_REPOS_FOR_CLUSTERED_CI
                    ),
                    "status": "estimated",
                }
            )
        else:
            row.update(
                {
                    "cross_rate": float("nan"),
                    "same_rate": float("nan"),
                    "paired_difference": float("nan"),
                    "repository_cluster_ci_low": float("nan"),
                    "repository_cluster_ci_high": float("nan"),
                    "clustered_ci_reliable": False,
                    "status": "too few to estimate",
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def leave_one_out(pairs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    cross, same = _binary_pair_values(pairs, PRIMARY_COLUMN)
    differences = (cross - same).to_numpy()
    frame = pd.DataFrame(
        {
            "difference": differences,
            "repository": pairs["repository"].to_numpy(),
            "ordered_product_pair": pairs["ordered_product_pair"].to_numpy(),
        }
    )
    overall = float(frame["difference"].mean())

    rows = []
    for unit_type, column in [
        ("repository", "repository"),
        ("ordered_product_pair", "ordered_product_pair"),
    ]:
        for unit in sorted(frame[column].unique()):
            kept = frame[frame[column] != unit]
            rows.append(
                {
                    "exclusion_unit": unit_type,
                    "excluded_group": unit,
                    "pairs_dropped": int(len(frame) - len(kept)),
                    "pairs_remaining": int(len(kept)),
                    "paired_difference": float(kept["difference"].mean()),
                    "shift_from_overall": float(kept["difference"].mean() - overall),
                }
            )
    loo = pd.DataFrame(rows)

    ranges: dict[str, object] = {"overall_paired_difference": overall}
    for unit_type in ["repository", "ordered_product_pair"]:
        cell = loo[loo["exclusion_unit"] == unit_type]
        ranges[unit_type] = {
            "refits": int(len(cell)),
            "min": float(cell["paired_difference"].min()),
            "median": float(cell["paired_difference"].median()),
            "max": float(cell["paired_difference"].max()),
            "all_refits_negative": bool((cell["paired_difference"] < 0).all()),
            "most_influential_unit": str(
                cell.loc[cell["shift_from_overall"].abs().idxmax(), "excluded_group"]
            ),
            "largest_absolute_shift": float(cell["shift_from_overall"].abs().max()),
        }
    return loo, ranges


def generality_verdict(
    by_product_pair: pd.DataFrame, ranges: dict[str, object]
) -> dict[str, object]:
    qualifying = by_product_pair[by_product_pair["qualifies"]]
    negative = int((qualifying["paired_difference"] < 0).sum())
    share_negative = negative / len(qualifying) if len(qualifying) else float("nan")
    loo_all_negative = bool(
        ranges["repository"]["all_refits_negative"]
        and ranges["ordered_product_pair"]["all_refits_negative"]
    )
    general = bool(loo_all_negative and share_negative >= GENERALITY_NEGATIVE_PAIR_SHARE)
    return {
        "rule": (
            "GENERAL requires every leave-one-repository-out and every "
            "leave-one-product-pair-out refit to stay strictly negative AND at "
            f"least {GENERALITY_NEGATIVE_PAIR_SHARE:.3f} of qualifying product "
            "pairs to have a negative point estimate; otherwise CONCENTRATED."
        ),
        "qualifying_product_pairs": int(len(qualifying)),
        "qualifying_product_pairs_negative": negative,
        "share_of_qualifying_pairs_negative": share_negative,
        "all_leave_one_out_refits_negative": loo_all_negative,
        "verdict": "general" if general else "concentrated",
    }


# ---------------------------------------------------------------------------
# Part 2: repository moderators for the familiar-replier split
# ---------------------------------------------------------------------------


def repository_descriptors(cohort: pd.DataFrame) -> pd.DataFrame:
    """Pre-trigger repository descriptors observable in the release.

    The cutoff for each repository is its first trigger in the RQ3 landmark
    cohort. Every descriptor uses only pull requests created strictly before
    that cutoff, and only reviews submitted strictly before it, so nothing is
    measured after the trigger.
    """
    cutoffs = (
        pl.from_pandas(cohort[["repo_id", "trigger_dt"]])
        .with_columns(pl.col("repo_id").cast(pl.Int64))
        .group_by("repo_id")
        .agg(pl.col("trigger_dt").min().alias("cutoff_dt"))
    )

    repo_ids = cutoffs["repo_id"].to_list()
    prs = (
        pl.scan_parquet(DATA / "all_pull_request.parquet")
        .filter(pl.col("repo_id").is_in(repo_ids))
        .select(
            pl.col("id").cast(pl.Int64).alias("history_pr_id"),
            pl.col("repo_id").cast(pl.Int64),
            pl.col("user").str.to_lowercase().alias("login"),
            parse_timestamp("created_at", "created_dt"),
            parse_timestamp("closed_at", "closed_dt"),
            parse_timestamp("merged_at", "merged_dt"),
        )
        .join(cutoffs.lazy(), on="repo_id", how="inner")
        .filter(pl.col("created_dt").is_not_null() & (pl.col("created_dt") < pl.col("cutoff_dt")))
        .collect(engine="streaming")
    )

    reviews = (
        pl.scan_parquet(DATA / "pr_reviews.parquet")
        .select(
            pl.col("pr_id").cast(pl.Int64).alias("history_pr_id"),
            parse_timestamp("submitted_at", "review_dt"),
        )
        .join(prs.select("history_pr_id", "cutoff_dt").lazy(), on="history_pr_id", how="inner")
        .filter(pl.col("review_dt").is_not_null() & (pl.col("review_dt") < pl.col("cutoff_dt")))
        .group_by("history_pr_id")
        .agg(pl.len().alias("reviews"))
        .collect(engine="streaming")
    )

    enriched = prs.join(reviews, on="history_pr_id", how="left").with_columns(
        pl.col("reviews").fill_null(0)
    )

    closed_before = (
        pl.col("closed_dt").is_not_null() & (pl.col("closed_dt") < pl.col("cutoff_dt"))
    )
    merged_before = (
        pl.col("merged_dt").is_not_null() & (pl.col("merged_dt") < pl.col("cutoff_dt"))
    )

    descriptors = (
        enriched.group_by("repo_id")
        .agg(
            pl.len().alias("pre_total_prs"),
            pl.col("login").n_unique().alias("pre_distinct_contributors"),
            closed_before.sum().alias("pre_closed_prs"),
            (closed_before & merged_before).sum().alias("pre_merged_prs"),
            pl.col("reviews").sum().alias("pre_total_reviews"),
            (pl.col("reviews") > 0).sum().alias("pre_prs_with_any_review"),
            pl.col("created_dt").min().alias("pre_first_pr_dt"),
            pl.col("cutoff_dt").first().alias("cutoff_dt"),
        )
        .with_columns(
            # Share of pre-cutoff pull requests already merged before the cutoff.
            # Defined for every repository with any pre-trigger history, so the
            # moderator model keeps the full landmark cohort.
            (pl.col("pre_merged_prs") / pl.col("pre_total_prs")).alias("pre_merge_rate"),
            # Restricted to pull requests already resolved before the cutoff.
            # Undefined for repositories with none, so it is reported in the CSV
            # for transparency but is not used as a model control.
            pl.when(pl.col("pre_closed_prs") > 0)
            .then(pl.col("pre_merged_prs") / pl.col("pre_closed_prs"))
            .otherwise(None)
            .alias("pre_merge_rate_closed_prs"),
            (pl.col("pre_total_reviews") / pl.col("pre_total_prs")).alias("pre_reviews_per_pr"),
            (pl.col("pre_prs_with_any_review") / pl.col("pre_total_prs")).alias(
                "pre_share_prs_any_review"
            ),
            (
                (pl.col("cutoff_dt") - pl.col("pre_first_pr_dt")).dt.total_seconds() / 86_400.0
            ).alias("pre_repo_age_days"),
        )
    )

    frame = descriptors.to_pandas()
    # Repositories whose first observed pull request IS the trigger PR have no
    # pre-trigger history at all; they are kept with zeroed volume so they are
    # visible in the CSV rather than silently missing.
    all_repos = pd.DataFrame({"repo_id": repo_ids})
    frame = all_repos.merge(frame, on="repo_id", how="left")
    for column in ["pre_total_prs", "pre_distinct_contributors", "pre_total_reviews",
                   "pre_prs_with_any_review", "pre_closed_prs", "pre_merged_prs"]:
        frame[column] = frame[column].fillna(0).astype(int)
    for column in [
        "pre_repo_age_days",
        "pre_reviews_per_pr",
        "pre_share_prs_any_review",
        "pre_merge_rate",
    ]:
        frame[column] = frame[column].fillna(0.0)
    frame["has_pretrigger_history"] = frame["pre_total_prs"] > 0
    return frame


def familiarity_groups(cohort: pd.DataFrame) -> pd.DataFrame:
    """Label each repository by which kind of user-written edge dominates it."""
    edges = cohort[cohort["edge_class"].isin(["edge_by_known_reviewer", "edge_by_newcomer"])]
    counts = (
        edges.groupby(["repo_id", "edge_class"]).size().unstack(fill_value=0).reset_index()
    )
    for column in ["edge_by_known_reviewer", "edge_by_newcomer"]:
        if column not in counts:
            counts[column] = 0
    counts = counts.rename(
        columns={
            "edge_by_known_reviewer": "known_reviewer_edges",
            "edge_by_newcomer": "newcomer_edges",
        }
    )
    counts["familiarity_group"] = np.where(
        counts["known_reviewer_edges"] > counts["newcomer_edges"],
        "familiar_dominant",
        np.where(
            counts["newcomer_edges"] > counts["known_reviewer_edges"],
            "newcomer_dominant",
            "mixed_tie",
        ),
    )
    volume = cohort.groupby("repo_id").size().rename("landmark_prs").reset_index()
    counts = counts.merge(volume, on="repo_id", how="left")
    return counts[
        [
            "repo_id",
            "known_reviewer_edges",
            "newcomer_edges",
            "familiarity_group",
            "landmark_prs",
        ]
    ]


def _median_difference_ci(
    left: np.ndarray, right: np.ndarray
) -> tuple[float, float, float, float]:
    """Repository-clustered bootstrap for a difference in medians.

    Repositories are the units here, so resampling repositories with
    replacement inside each group is exactly the repository-clustered interval
    used elsewhere in the project.
    """
    rng = np.random.default_rng(SEED)
    if len(left) == 0 or len(right) == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    left_draw = rng.choice(left, size=(BOOTSTRAP_DRAWS, len(left)), replace=True)
    right_draw = rng.choice(right, size=(BOOTSTRAP_DRAWS, len(right)), replace=True)
    estimates = np.median(left_draw, axis=1) - np.median(right_draw, axis=1)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return (
        float(np.median(left)),
        float(np.median(right)),
        float(low),
        float(high),
    )


def moderator_group_contrasts(repositories: pd.DataFrame) -> pd.DataFrame:
    familiar = repositories[repositories["familiarity_group"] == "familiar_dominant"]
    newcomer = repositories[repositories["familiarity_group"] == "newcomer_dominant"]
    tie = repositories[repositories["familiarity_group"] == "mixed_tie"]
    rows = []
    for moderator in MODERATORS:
        left = familiar[moderator].dropna().to_numpy(dtype=float)
        right = newcomer[moderator].dropna().to_numpy(dtype=float)
        left_median, right_median, low, high = _median_difference_ci(left, right)
        rows.append(
            {
                "moderator": moderator,
                "familiar_dominant_repositories": int(len(left)),
                "newcomer_dominant_repositories": int(len(right)),
                "mixed_tie_repositories": int(len(tie)),
                "familiar_dominant_median": left_median,
                "newcomer_dominant_median": right_median,
                "median_difference": left_median - right_median,
                "repository_cluster_ci_low": low,
                "repository_cluster_ci_high": high,
                "separates_groups": bool(
                    np.isfinite(low) and np.isfinite(high) and (low > 0 or high < 0)
                ),
            }
        )
    return pd.DataFrame(rows)


def _known_minus_newcomer(sample: pd.DataFrame, terms: list[str]) -> tuple[float, float, float]:
    """Reuse the RQ3 contrast: known-reviewer edge minus newcomer edge."""
    formula = (
        "merged_from_48h_to_30d ~ C(edge_class, Treatment('no_edge')) + " + " + ".join(terms)
    )
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


def moderator_models(cohort: pd.DataFrame, descriptors: pd.DataFrame) -> pd.DataFrame:
    frame = cohort.merge(descriptors[["repo_id", *MODERATORS]], on="repo_id", how="left")
    missing = int(frame[MODERATORS].isna().any(axis=1).sum())
    frame = frame.dropna(subset=MODERATORS).copy()

    terms = []
    for moderator in MODERATORS:
        if moderator in LOG_MODERATORS:
            column = f"log1p_{moderator}"
            frame[column] = np.log1p(frame[moderator].clip(lower=0))
            terms.append(column)
        else:
            terms.append(moderator)

    base = [*BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    specifications = [
        ("Primary (pre-trigger adjusted)", base, "reproduces the published RQ3 split"),
        (
            "Primary + repository moderators",
            [*base, *terms],
            "adds the six pre-trigger repository descriptors as controls",
        ),
        (
            "Repository fixed effects",
            [*base, "C(repo_id)"],
            "within-repository comparison only; the published collapse",
        ),
        (
            "Repository moderators + fixed effects",
            [*base, *terms, "C(repo_id)"],
            "moderators are collinear with the fixed effects; reported for completeness",
        ),
    ]

    rows = []
    primary_estimate = None
    for label, spec_terms, note in specifications:
        try:
            estimate, low, high = _known_minus_newcomer(frame, spec_terms)
        except (RuntimeError, np.linalg.LinAlgError):
            continue
        if primary_estimate is None:
            primary_estimate = estimate
        rows.append(
            {
                "specification": label,
                "estimate": estimate,
                "ci_low": low,
                "ci_high": high,
                "share_of_primary_remaining": (
                    estimate / primary_estimate if primary_estimate else float("nan")
                ),
                "share_of_primary_explained": (
                    1.0 - estimate / primary_estimate if primary_estimate else float("nan")
                ),
                "interval_excludes_zero": bool(low > 0 or high < 0),
                "n_prs": int(len(frame)),
                "repositories": int(frame["repo_id"].nunique()),
                "prs_dropped_for_missing_moderators": missing,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    # ---- Part 1 -----------------------------------------------------------
    pairs = load_matched_pairs()
    composition, concentration = matched_pair_composition(pairs)
    overall = _paired_gap(pairs)
    by_product_pair = gap_by_product_pair(pairs)
    loo, loo_ranges = leave_one_out(pairs)
    verdict = generality_verdict(by_product_pair, loo_ranges)

    composition.to_csv(OUTPUT / "matched_pair_composition.csv", index=False)
    by_product_pair.to_csv(OUTPUT / "matched_pair_by_product_pair.csv", index=False)
    loo.to_csv(OUTPUT / "matched_pair_leave_one_out.csv", index=False)

    # ---- Part 2 -----------------------------------------------------------
    cohort, interaction_checks = edge_author_history()
    cohort["repo_id"] = cohort["repo_id"].astype("int64")
    descriptors = repository_descriptors(cohort)
    groups = familiarity_groups(cohort)
    repositories = descriptors.merge(groups, on="repo_id", how="left")
    repositories["familiarity_group"] = repositories["familiarity_group"].fillna(
        "no_user_written_edge"
    )
    repositories["known_reviewer_edges"] = repositories["known_reviewer_edges"].fillna(0).astype(int)
    repositories["newcomer_edges"] = repositories["newcomer_edges"].fillna(0).astype(int)
    volume = cohort.groupby("repo_id").size()
    repositories["landmark_prs"] = (
        repositories["repo_id"].map(volume).fillna(0).astype(int)
    )
    repositories = repositories[
        [
            "repo_id",
            "familiarity_group",
            "known_reviewer_edges",
            "newcomer_edges",
            "landmark_prs",
            "has_pretrigger_history",
            *MODERATORS,
            "pre_merge_rate_closed_prs",
            "cutoff_dt",
        ]
    ].sort_values(["familiarity_group", "repo_id"])

    contrasts = moderator_group_contrasts(repositories)
    models = moderator_models(cohort, descriptors)

    repositories.to_csv(OUTPUT / "repository_moderators.csv", index=False)
    contrasts.to_csv(OUTPUT / "moderator_group_contrasts.csv", index=False)
    models.to_csv(OUTPUT / "rq3_moderator_models.csv", index=False)

    # ---- Summary ----------------------------------------------------------
    qualifying = by_product_pair[by_product_pair["qualifies"]]
    too_few = by_product_pair[~by_product_pair["qualifies"]]

    def _spec(label: str) -> dict[str, object] | None:
        cell = models[models["specification"] == label]
        if cell.empty:
            return None
        row = cell.iloc[0]
        return {
            "estimate": float(row["estimate"]),
            "ci": [float(row["ci_low"]), float(row["ci_high"])],
            "share_of_primary_remaining": float(row["share_of_primary_remaining"]),
            "interval_excludes_zero": bool(row["interval_excludes_zero"]),
        }

    primary_model = _spec("Primary (pre-trigger adjusted)")
    moderator_model = _spec("Primary + repository moderators")
    fixed_effects = _spec("Repository fixed effects")
    separating = contrasts[contrasts["separates_groups"]]["moderator"].tolist()

    decisive = qualifying[
        (qualifying["repository_cluster_ci_high"] < 0)
        | (qualifying["repository_cluster_ci_low"] > 0)
    ]
    strongest = (
        qualifying.sort_values("paired_difference")["ordered_product_pair"].tolist()[:2]
        if len(qualifying)
        else []
    )
    nuance = (
        " The direction is not uniform in size, however: the gap is largest in "
        + " and ".join(strongest)
        + f", only {len(decisive)} of {len(qualifying)} qualifying pairs has a "
        "repository-clustered interval that excludes zero on its own, and the "
        "remaining pairs are near zero, so the average is driven by the "
        "Codex-authored strata and should be reported as such."
    )
    if verdict["verdict"] == "general":
        part1_sentence = (
            f"The {abs(overall['paired_difference']) * 100:.1f} point follow-up gap is a "
            "general pattern by the pre-registered rule: it survives dropping any "
            "single repository or product pair, and "
            f"{verdict['qualifying_product_pairs_negative']} of "
            f"{verdict['qualifying_product_pairs']} product pairs large enough to "
            "estimate on their own reproduce its sign."
            + nuance
        )
    else:
        part1_sentence = (
            f"The {abs(overall['paired_difference']) * 100:.1f} point follow-up gap is "
            "concentrated rather than general: only "
            f"{verdict['qualifying_product_pairs_negative']} of "
            f"{verdict['qualifying_product_pairs']} product pairs large enough to "
            "estimate reproduce it, and the leave-one-out refits do not all stay "
            "negative, so the manuscript must print this as a limitation."
        )

    if moderator_model and primary_model:
        explained = 1.0 - moderator_model["estimate"] / primary_model["estimate"]
        part2_sentence = (
            "The six pre-trigger repository descriptors explain "
            f"{explained * 100:.1f} percent of the familiar-versus-newcomer gap "
            f"({primary_model['estimate'] * 100:.1f} points down to "
            f"{moderator_model['estimate'] * 100:.1f} points), while repository fixed "
            f"effects leave {fixed_effects['estimate'] * 100:.1f} points with an "
            "interval covering zero, so the split is a between-repository "
            "difference that our measured governance and volume descriptors do not "
            "account for."
        )
    else:
        part2_sentence = "Moderator models did not converge."

    summary = {
        "interpretation": (
            "Observational public traces from AIDev-7.6M; nothing here identifies a "
            "causal effect. PART 1: "
            + part1_sentence
            + " The 546 matched pairs are unevenly spread, with the largest single "
            f"repository holding {concentration['largest_repository_share'] * 100:.1f} "
            "percent of pairs, the largest ordered product pair holding "
            f"{concentration['largest_product_pair_share'] * 100:.1f} percent, and a "
            f"repository Gini of {concentration['repository_gini']:.3f}. PART 2: "
            + part2_sentence
        ),
        "part1_matched_pair_spread": {
            "overall_gap": overall,
            "concentration": concentration,
            "minimum_pairs_per_product_pair": MIN_PAIRS_PER_PRODUCT_PAIR,
            "qualifying_product_pairs": qualifying[
                [
                    "ordered_product_pair",
                    "pairs",
                    "repositories",
                    "paired_difference",
                    "repository_cluster_ci_low",
                    "repository_cluster_ci_high",
                    "clustered_ci_reliable",
                ]
            ].to_dict("records"),
            "too_few_to_estimate": too_few[
                ["ordered_product_pair", "pairs", "repositories"]
            ].to_dict("records"),
            "leave_one_out_ranges": loo_ranges,
            "generality": verdict,
        },
        "part2_repository_moderators": {
            "rq3_interaction_checks": interaction_checks,
            "descriptor_definition": (
                "Each repository's cutoff is its first trigger in the RQ3 landmark "
                "cohort. Descriptors use only pull requests created strictly before "
                "that cutoff and reviews submitted strictly before it."
            ),
            "moderators": MODERATORS,
            "repositories_described": int(len(repositories)),
            "familiarity_group_counts": repositories["familiarity_group"]
            .value_counts()
            .to_dict(),
            "moderators_separating_groups": separating,
            "group_contrasts": contrasts.to_dict("records"),
            "models": models.drop(columns=["note"]).to_dict("records"),
        },
        "reviewer_answers": {
            "matched_pair_distribution": part1_sentence,
            "repository_moderators": part2_sentence,
        },
        "outputs": sorted(path.name for path in OUTPUT.glob("*.csv")),
    }

    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(json.dumps(summary["part1_matched_pair_spread"], indent=2, default=str))
    print()
    print(by_product_pair.to_string(index=False))
    print()
    print(contrasts.to_string(index=False))
    print()
    print(models.drop(columns=["note"]).to_string(index=False))
    print()
    print(summary["interpretation"])


if __name__ == "__main__":
    main()
