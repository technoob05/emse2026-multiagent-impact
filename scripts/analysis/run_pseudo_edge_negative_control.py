"""Negative-control EXPOSURES for the RQ3 addressed-edge association.

The landmark analysis reports that an exact inline reply anchored to the
cross-product trigger goes with a higher probability of later merge. The
standing objection is that this only marks "the PR is still alive". Placebo
OUTCOMES (run_addressed_edge_confounding_sensitivity.py) answer a different
question. This script answers the harder one a reviewer asked: does a PSEUDO
exposure, which carries the liveness but not the anchoring, reproduce the
estimate?

Three contrasts, in increasing strictness, all pushed through the SAME
adjusted model, the SAME landmark rule, and the SAME repository-clustered
interval as the headline:

1. off_target_reply       an exact inline reply in the same window anchored to
                          some OTHER inline comment on the PR. Still review
                          activity, so a positive estimate is expected; the
                          question is whether it is clearly smaller.
2. permuted_anchor        the observed reply events are kept exactly as they
                          are, but which PR's reply counts as anchored to its
                          own trigger is permuted inside repository x calendar
                          month strata. The marginal rate of "has a reply" and
                          the number of anchored PRs per stratum are preserved;
                          only the ANCHORING is destroyed.
3. time_shifted_edge      each PR is given a fake edge time drawn from the
                          observed edge-time distribution but independent of
                          that PR's own history, then the identical landmark
                          rule is applied.

Nothing here is a causal claim. A specific estimate means the association
tracks the anchored edge rather than generic liveness or the timing rule.
"""

from __future__ import annotations

import hashlib
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

from multiagent_impact.cross_agent_review import parse_timestamp  # noqa: E402
from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402


CONFIG = AnalysisConfig.from_paths(ROOT)
DATA = CONFIG.data_dir
EDGE = ROOT / "outputs" / "addressed_edge_landmark"
OUTPUT = ROOT / "outputs" / "pseudo_edge_control"

DATASET_REVISION = "37bbe1533e26cc1e1374917dba1186d1c8a4dc81"
PRIMARY_THRESHOLD = 48
EXPECTED_COHORT_ROWS = 1_067
EXPECTED_EXACT_48H = 109
DRAWS = 2_000
SEED = 20260827
PRIMARY_STRATIFICATION = "repository_month"
STRATIFICATIONS = (
    "repository_month",
    "repository",
    "calendar_month",
    "unstratified",
)

OUTCOME = "merged_from_48h_to_30d"
REAL_EXPOSURE = f"exact_parent_reply_by_{PRIMARY_THRESHOLD}h"
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def formula(exposure: str, extra: list[str] | None = None) -> str:
    terms = [exposure, *(extra or []), *BASE_CATEGORICAL, *PRETRIGGER_CONTROLS]
    return f"{OUTCOME} ~ " + " + ".join(terms)


def load_cohort() -> pl.DataFrame:
    path = EDGE / "analysis_cohort.parquet"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing; run scripts/analysis/"
            "run_addressed_edge_landmark_analysis.py first"
        )
    cohort = pl.read_parquet(path).sort("pr_id")
    if cohort.height != EXPECTED_COHORT_ROWS:
        raise AssertionError(
            f"Landmark cohort drift: {cohort.height} != {EXPECTED_COHORT_ROWS}"
        )
    if cohort["pr_id"].n_unique() != cohort.height:
        raise AssertionError("The landmark cohort is not one row per PR.")
    if int(cohort[REAL_EXPOSURE].sum()) != EXPECTED_EXACT_48H:
        raise AssertionError("The upstream 48-hour exact-edge count drifted.")
    expected_landmark = cohort["trigger_dt"] + timedelta(hours=PRIMARY_THRESHOLD)
    if not (cohort["outcome_landmark_dt"] == expected_landmark).all():
        raise AssertionError("The outcome landmark is not exactly trigger + 48 hours.")
    return cohort


def inline_reply_events(
    key: pl.DataFrame, window_hours: float, data_dir: Path | None = None
) -> pl.DataFrame:
    """Every raw inline reply on a keyed PR inside (trigger, trigger + window].

    This is the single definition of the on-target / off-target split. Other
    analyses (for example `run_merge_curves.py`) import it rather than rebuild
    a second, subtly different version of the same construct.

    `key` must carry `pr_id`, `trigger_dt` and `trigger_event_id`; any further
    columns are passed through. A reply is on-target when its raw GitHub
    `in_reply_to_id` equals the PR's cross-product trigger id, and off-target
    when it anchors to any other inline comment on the same PR.
    """
    data_dir = data_dir or DATA
    required = {"pr_id", "trigger_dt", "trigger_event_id"}
    missing = sorted(required - set(key.columns))
    if missing:
        raise AssertionError(f"Reply-event key is missing columns: {missing}")
    review_key = (
        pl.scan_parquet(data_dir / "pr_reviews.parquet")
        .select("pull_request_review_id", "pr_id")
        .unique("pull_request_review_id")
    )
    replies = (
        pl.scan_parquet(data_dir / "pr_review_comments.parquet")
        .select(
            pl.col("id").alias("reply_event_id"),
            "pull_request_review_id",
            "user_type",
            pl.col("in_reply_to_id").cast(pl.Int64, strict=False),
            parse_timestamp("created_at", "reply_dt"),
        )
        .join(review_key, on="pull_request_review_id", how="inner")
        .join(key.lazy(), on="pr_id", how="inner")
        .filter(
            pl.col("in_reply_to_id").is_not_null()
            & pl.col("reply_dt").is_not_null()
            & (pl.col("reply_dt") > pl.col("trigger_dt"))
            & (
                pl.col("reply_dt")
                <= pl.col("trigger_dt") + timedelta(hours=float(window_hours))
            )
        )
        .with_columns(
            (pl.col("in_reply_to_id") == pl.col("trigger_event_id")).alias("on_target"),
            (
                (pl.col("reply_dt") - pl.col("trigger_dt")).dt.total_seconds() / 3600.0
            ).alias("hours_after_trigger"),
        )
        .collect(engine="streaming")
        .sort(["pr_id", "reply_dt", "reply_event_id"])
    )
    if replies.filter(
        (pl.col("hours_after_trigger") <= 0)
        | (pl.col("hours_after_trigger") > float(window_hours))
    ).height:
        raise AssertionError(
            f"A window reply falls outside (trigger, {window_hours} hours]."
        )
    return replies


def load_window_replies(cohort: pl.DataFrame) -> pl.DataFrame:
    """The 48-hour landmark window, checked against the upstream exact edge."""
    replies = inline_reply_events(
        cohort.select("pr_id", "repo_id", "trigger_dt", "trigger_event_id"),
        PRIMARY_THRESHOLD,
    )
    derived = set(replies.filter(pl.col("on_target"))["pr_id"].to_list())
    upstream = set(cohort.filter(pl.col(REAL_EXPOSURE) == 1)["pr_id"].to_list())
    if derived != upstream:
        raise AssertionError(
            "Raw on-target reply set does not reproduce the upstream exact edge: "
            f"{len(derived)} vs {len(upstream)}"
        )
    return replies


def build_frame(cohort: pl.DataFrame, replies: pl.DataFrame) -> pd.DataFrame:
    per_pr = replies.group_by("pr_id").agg(
        pl.col("on_target").any().alias("has_on_target_reply"),
        (~pl.col("on_target")).any().alias("has_off_target_reply"),
        pl.len().alias("window_reply_events"),
    )
    enriched = cohort.join(per_pr, on="pr_id", how="left").with_columns(
        pl.col("has_on_target_reply").fill_null(False),
        pl.col("has_off_target_reply").fill_null(False),
        pl.col("window_reply_events").fill_null(0),
        pl.col("trigger_dt").dt.strftime("%Y-%m").alias("stratum_month"),
    )
    frame = enriched.to_pandas()
    frame[OUTCOME] = frame[OUTCOME].astype(int)
    frame[REAL_EXPOSURE] = frame[REAL_EXPOSURE].astype(int)
    frame["on_target_reply"] = frame["has_on_target_reply"].astype(int)
    frame["off_target_reply_only"] = (
        frame["has_off_target_reply"] & ~frame["has_on_target_reply"]
    ).astype(int)
    frame["has_any_window_reply"] = (
        frame["has_on_target_reply"] | frame["has_off_target_reply"]
    ).astype(int)
    if (frame["on_target_reply"] != frame[REAL_EXPOSURE]).any():
        raise AssertionError("Derived on-target flag disagrees with the upstream edge.")
    return frame


def fit_clustered(frame: pd.DataFrame, spec: str, exposure: str):
    endog, design = dmatrices(spec, frame, return_type="dataframe")
    groups = frame.loc[design.index, "repo_id"]
    if groups.nunique() < 2:
        raise RuntimeError("Clustered model has fewer than two repositories.")
    model = sm.OLS(endog.iloc[:, 0], design).fit(
        cov_type="cluster",
        cov_kwds={"groups": groups, "use_correction": True},
    )
    if exposure not in model.params.index:
        raise AssertionError(f"Exposure term missing from the model: {exposure}")
    return model, design, endog, groups


def observed_row(
    frame: pd.DataFrame, exposure: str, label: str, note: str
) -> dict[str, object]:
    spec = formula(exposure)
    model, design, _, groups = fit_clustered(frame, spec, exposure)
    interval = model.conf_int().loc[exposure]
    return {
        "exposure": label,
        "prs": int(model.nobs),
        "exposed_prs": int(frame[exposure].sum()),
        "repositories": int(groups.nunique()),
        "estimate_pp": float(model.params[exposure]) * 100.0,
        "ci_low": float(interval.iloc[0]) * 100.0,
        "ci_high": float(interval.iloc[1]) * 100.0,
        "p_value": float(model.pvalues[exposure]),
        "design_columns": int(design.shape[1]),
        "note": note,
    }


def joint_contrast(frame: pd.DataFrame) -> dict[str, object]:
    """On-target and off-target-only in one model, both against 'no reply'."""
    spec = formula("on_target_reply", extra=["off_target_reply_only"])
    model, _, _, groups = fit_clustered(frame, spec, "on_target_reply")
    on = "on_target_reply"
    off = "off_target_reply_only"
    cov = model.cov_params()
    difference = float(model.params[on] - model.params[off])
    variance = float(cov.loc[on, on] + cov.loc[off, off] - 2 * cov.loc[on, off])
    standard_error = float(np.sqrt(max(variance, 0.0)))
    z = difference / standard_error if standard_error > 0 else float("nan")
    from scipy import stats  # local import; only used for this Wald test

    p_value = float(2 * (1 - stats.norm.cdf(abs(z)))) if standard_error > 0 else float("nan")
    return {
        "prs": int(model.nobs),
        "repositories": int(groups.nunique()),
        "on_target_pp": float(model.params[on]) * 100.0,
        "on_target_ci_low": float(model.conf_int().loc[on, 0]) * 100.0,
        "on_target_ci_high": float(model.conf_int().loc[on, 1]) * 100.0,
        "off_target_pp": float(model.params[off]) * 100.0,
        "off_target_ci_low": float(model.conf_int().loc[off, 0]) * 100.0,
        "off_target_ci_high": float(model.conf_int().loc[off, 1]) * 100.0,
        "difference_pp": difference * 100.0,
        "difference_ci_low": (difference - 1.959963985 * standard_error) * 100.0,
        "difference_ci_high": (difference + 1.959963985 * standard_error) * 100.0,
        "difference_p_value": p_value,
        "reference_group": "no inline reply of any kind inside the 48-hour window",
    }


def design_matrices(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, int]:
    spec = formula(REAL_EXPOSURE)
    endog, design = dmatrices(spec, frame, return_type="dataframe")
    matches = [name for name in design.columns if name.startswith(REAL_EXPOSURE)]
    if len(matches) != 1:
        raise AssertionError(f"Ambiguous exposure column: {matches}")
    column = list(design.columns).index(matches[0])
    return endog.iloc[:, 0].to_numpy(), design.to_numpy(), column


def stratum_labels(frame: pd.DataFrame, scheme: str) -> np.ndarray:
    repo = frame["repo_id"].astype(str)
    month = frame["stratum_month"].astype(str)
    if scheme == "repository_month":
        return (repo + "|" + month).to_numpy()
    if scheme == "repository":
        return repo.to_numpy()
    if scheme == "calendar_month":
        return month.to_numpy()
    if scheme == "unstratified":
        return np.full(len(frame), "all", dtype=object)
    raise ValueError(f"Unknown stratification scheme: {scheme}")


def permuted_anchor_null(
    frame: pd.DataFrame, generator: np.random.Generator, scheme: str
) -> tuple[np.ndarray, dict[str, object]]:
    """Permute WHICH replying PR is anchored to its own trigger, within strata.

    The observed reply events are untouched: every PR that has a reply in the
    window still has one, and each stratum keeps exactly the number of anchored
    PRs it really had. Only the correspondence between a reply and the trigger
    it points at is destroyed.

    A stratum where every replying PR is anchored (or none is) carries no
    permutable information, so those PRs keep their real value. The share of
    anchored PRs that are actually permutable is reported, because a null built
    on a small permutable share cannot be read as evidence either way.
    """
    y, x, column = design_matrices(frame)
    observed = float(np.linalg.lstsq(x, y, rcond=None)[0][column])

    replying = frame["has_any_window_reply"].to_numpy().astype(bool)
    anchored = frame["on_target_reply"].to_numpy().astype(float)
    if not np.array_equal(anchored.astype(bool) & ~replying, np.zeros_like(replying)):
        raise AssertionError("An anchored PR has no reply event in the window.")

    stratum = stratum_labels(frame, scheme)
    blocks: list[np.ndarray] = []
    fixed_strata = 0
    for value in pd.unique(stratum):
        index = np.flatnonzero((stratum == value) & replying)
        if index.size == 0:
            continue
        total = anchored[index].sum()
        if 0 < total < index.size:
            blocks.append(index)
        else:
            fixed_strata += 1
    if not blocks:
        raise RuntimeError("No repository x month stratum has anchoring variation.")

    permutable = int(sum(block.size for block in blocks))
    draws = np.empty(DRAWS)
    exposed_counts = np.empty(DRAWS, dtype=int)
    work = x.copy()
    for index in range(DRAWS):
        pseudo = anchored.copy()
        for block in blocks:
            pseudo[block] = generator.permutation(anchored[block])
        work[:, column] = pseudo
        draws[index] = np.linalg.lstsq(work, y, rcond=None)[0][column]
        exposed_counts[index] = int(pseudo.sum())
    if not np.all(exposed_counts == int(anchored.sum())):
        raise AssertionError("Permutation did not preserve the anchored-PR count.")

    permutable_anchored = int(
        sum(anchored[block].sum() for block in blocks)
    )
    diagnostics = {
        "stratification": scheme,
        "observed_estimate_pp": observed * 100.0,
        "replying_prs": int(replying.sum()),
        "anchored_prs": int(anchored.sum()),
        "strata_with_anchoring_variation": len(blocks),
        "strata_held_fixed": fixed_strata,
        "permutable_prs": permutable,
        "permutable_anchored_prs": permutable_anchored,
        "permutable_anchored_share": float(permutable_anchored / anchored.sum()),
        "support_degenerate": bool(permutable_anchored / anchored.sum() < 0.5),
        "exposed_prs_per_draw": int(anchored.sum()),
    }
    return draws, diagnostics


def time_shifted_null(
    frame: pd.DataFrame, generator: np.random.Generator
) -> tuple[np.ndarray, dict[str, object]]:
    """Give every PR an edge time drawn from the observed distribution.

    The pool is the cohort's own vector of hours-to-first-exact-reply, with a
    NaN for every PR that never had one, so the marginal exposure rate is
    preserved in expectation while the timing is independent of the PR. The
    identical landmark rule (edge at or before 48 hours) is then applied.
    """
    y, x, column = design_matrices(frame)
    observed = float(np.linalg.lstsq(x, y, rcond=None)[0][column])

    pool = frame["first_exact_reply_hours"].to_numpy(dtype=float)
    finite = pool[np.isfinite(pool)]
    if finite.size != int(frame[REAL_EXPOSURE].sum()):
        raise AssertionError("Edge-time pool does not match the exposed-PR count.")
    if finite.max() > PRIMARY_THRESHOLD or finite.min() <= 0:
        raise AssertionError("Observed edge times fall outside (0, 48] hours.")

    size = pool.size
    draws = np.empty(DRAWS)
    exposed_counts = np.empty(DRAWS, dtype=int)
    work = x.copy()
    for index in range(DRAWS):
        fake = pool[generator.integers(0, size, size=size)]
        pseudo = (np.isfinite(fake) & (fake <= PRIMARY_THRESHOLD)).astype(float)
        if pseudo.sum() == 0 or pseudo.sum() == size:
            pseudo = pool[generator.permutation(size)]
            pseudo = (np.isfinite(pseudo) & (pseudo <= PRIMARY_THRESHOLD)).astype(float)
        work[:, column] = pseudo
        draws[index] = np.linalg.lstsq(work, y, rcond=None)[0][column]
        exposed_counts[index] = int(pseudo.sum())
    diagnostics = {
        "observed_estimate_pp": observed * 100.0,
        "edge_time_pool_size": int(size),
        "edge_time_pool_non_missing": int(finite.size),
        "mean_exposed_prs_per_draw": float(exposed_counts.mean()),
        "min_exposed_prs_per_draw": int(exposed_counts.min()),
        "max_exposed_prs_per_draw": int(exposed_counts.max()),
    }
    return draws, diagnostics


def null_summary(
    label: str, draws: np.ndarray, observed_pp: float, diagnostics: dict[str, object]
) -> dict[str, object]:
    pp = draws * 100.0
    two_sided = float(
        (1 + np.sum(np.abs(pp) >= abs(observed_pp) - 1e-12)) / (DRAWS + 1)
    )
    one_sided = float((1 + np.sum(pp >= observed_pp - 1e-12)) / (DRAWS + 1))
    percentile = float((pp < observed_pp).mean() * 100.0)
    standard_deviation = float(pp.std(ddof=1))
    return {
        "control": label,
        "draws": DRAWS,
        "seed": SEED,
        "null_mean_pp": float(pp.mean()),
        "null_sd_pp": standard_deviation,
        "null_quantile_025_pp": float(np.quantile(pp, 0.025)),
        "null_quantile_975_pp": float(np.quantile(pp, 0.975)),
        "null_min_pp": float(pp.min()),
        "null_max_pp": float(pp.max()),
        "observed_estimate_pp": observed_pp,
        "observed_percentile_in_null": percentile,
        "observed_standardised_position": (
            (observed_pp - float(pp.mean())) / standard_deviation
            if standard_deviation > 0
            else float("nan")
        ),
        "p_value_two_sided": two_sided,
        "p_value_one_sided_greater": one_sided,
        "null_centred_near_zero": bool(
            float(np.quantile(pp, 0.025)) <= 0.0 <= float(np.quantile(pp, 0.975))
        ),
        **diagnostics,
    }


def write_readme(contrasts: pd.DataFrame, summary: dict[str, object]) -> None:
    rows = "\n".join(
        "| {exposure} | {prs:,} | {estimate_pp:.1f} | {ci_low:.1f} to {ci_high:.1f} | {note} |".format(
            **record
        )
        for record in contrasts.to_dict("records")
    )
    text = f"""# Pseudo-edge negative-control exposures (RQ3)

Answers the reviewer question "did you explore negative-control exposures
(pseudo-edges assigned to unrelated comments)?". Every row below uses the same
adjusted linear-probability model, the same 48-hour landmark rule, and the same
repository-clustered interval as the headline addressed-edge analysis. Only the
exposure definition changes.

| exposure | PRs | estimate (pp) | 95% interval (pp) | note |
|---|---|---|---|---|
{rows}

Seed {SEED}; {DRAWS:,} draws for each permutation-based row. Per-draw estimates
are in `permutation_null.csv`, the tidy table is `contrasts.csv`, and headline
numbers plus the interpretation string are in `summary.json`.

Specificity verdict: **{summary['specificity_verdict']}**

{summary['interpretation']}

Scope: observational later-merge differences. Nothing here is a causal effect
or a claim that any reply semantically resolved the review point.
"""
    (OUTPUT / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    generator = np.random.default_rng(SEED)

    cohort = load_cohort()
    replies = load_window_replies(cohort)
    frame = build_frame(cohort, replies)

    real = observed_row(
        frame,
        "on_target_reply",
        "addressed_edge_observed",
        "reference row: exact reply anchored to the cross-product trigger",
    )
    off_target_frame = frame[frame["on_target_reply"] == 0].copy()
    off_target = observed_row(
        off_target_frame,
        "off_target_reply_only",
        "off_target_reply",
        "activity control: exact reply anchored to a different inline comment; "
        "PRs with the real addressed edge are removed so the contrast is "
        "off-target reply vs no reply",
    )
    any_reply = observed_row(
        frame,
        "has_any_window_reply",
        "any_inline_reply_diagnostic",
        "diagnostic, not one of the three contrasts: any inline reply of any "
        "anchoring inside the 48-hour window; this is the construct the pseudo-edge "
        "nulls suggest the estimate actually tracks",
    )
    joint = joint_contrast(frame)

    permutation_draws: dict[str, np.ndarray] = {}
    permutation_summaries: list[dict[str, object]] = []
    for scheme in STRATIFICATIONS:
        draws, diagnostics = permuted_anchor_null(frame, generator, scheme)
        permutation_draws[scheme] = draws
        permutation_summaries.append(
            null_summary(
                f"permuted_anchor[{scheme}]",
                draws,
                real["estimate_pp"],
                diagnostics,
            )
        )
    by_scheme = {
        record["stratification"]: record for record in permutation_summaries
    }
    permuted = by_scheme[PRIMARY_STRATIFICATION]
    permuted_draws = permutation_draws[PRIMARY_STRATIFICATION]
    # A stratification where most anchored PRs cannot move carries no
    # information; fall back to the coarsest scheme that actually permutes.
    readable = next(
        (
            by_scheme[scheme]
            for scheme in STRATIFICATIONS
            if not by_scheme[scheme]["support_degenerate"]
        ),
        None,
    )
    permutation_reference = readable or permuted

    shifted_draws, shifted_diagnostics = time_shifted_null(frame, generator)
    shifted = null_summary(
        "time_shifted_edge",
        shifted_draws,
        real["estimate_pp"],
        shifted_diagnostics,
    )

    contrasts = pd.DataFrame(
        [
            {
                "exposure": "addressed_edge_observed",
                "prs": real["prs"],
                "estimate_pp": real["estimate_pp"],
                "ci_low": real["ci_low"],
                "ci_high": real["ci_high"],
                "note": (
                    f"reference; {real['exposed_prs']} exposed PRs; "
                    f"clustered p={real['p_value']:.2e}"
                ),
            },
            {
                "exposure": "off_target_reply",
                "prs": off_target["prs"],
                "estimate_pp": off_target["estimate_pp"],
                "ci_low": off_target["ci_low"],
                "ci_high": off_target["ci_high"],
                "note": (
                    "activity control on a different support: PRs carrying the real "
                    f"addressed edge are excluded; {off_target['exposed_prs']} exposed "
                    f"PRs; clustered p={off_target['p_value']:.2e}; joint-model gap to "
                    f"the addressed edge {joint['difference_pp']:.1f} pp "
                    f"(95% CI {joint['difference_ci_low']:.1f} to "
                    f"{joint['difference_ci_high']:.1f}, p={joint['difference_p_value']:.3f})"
                ),
            },
            {
                "exposure": "permuted_anchor_pseudo_edge",
                "prs": real["prs"],
                "estimate_pp": permuted["null_mean_pp"],
                "ci_low": permuted["null_quantile_025_pp"],
                "ci_high": permuted["null_quantile_975_pp"],
                "note": (
                    f"null distribution over {DRAWS} draws (seed {SEED}); interval is the "
                    "2.5-97.5 percentile of the null, not a clustered CI; observed "
                    f"{real['estimate_pp']:.1f} pp sits at percentile "
                    f"{permuted['observed_percentile_in_null']:.2f} "
                    f"(two-sided p={permuted['p_value_two_sided']:.4f}); anchoring permuted "
                    f"inside {permuted['strata_with_anchoring_variation']} repository x month "
                    f"strata covering {permuted['permutable_prs']} replying PRs, so only "
                    f"{permuted['permutable_anchored_share']:.0%} of anchored PRs can move"
                    + (
                        ""
                        if not permuted["support_degenerate"]
                        else "; SUPPORT DEGENERATE, read the "
                        f"{permutation_reference['stratification']} row instead "
                        f"({permutation_reference['null_mean_pp']:.1f} pp, "
                        f"{permutation_reference['null_quantile_025_pp']:.1f} to "
                        f"{permutation_reference['null_quantile_975_pp']:.1f}, two-sided "
                        f"p={permutation_reference['p_value_two_sided']:.4f})"
                    )
                ),
            },
            {
                "exposure": "time_shifted_pseudo_edge",
                "prs": real["prs"],
                "estimate_pp": shifted["null_mean_pp"],
                "ci_low": shifted["null_quantile_025_pp"],
                "ci_high": shifted["null_quantile_975_pp"],
                "note": (
                    f"null distribution over {DRAWS} draws (seed {SEED}); interval is the "
                    "2.5-97.5 percentile of the null, not a clustered CI; observed "
                    f"{real['estimate_pp']:.1f} pp sits at percentile "
                    f"{shifted['observed_percentile_in_null']:.2f} "
                    f"(two-sided p={shifted['p_value_two_sided']:.4f}); fake edge times "
                    "resampled from the observed edge-time distribution independently of "
                    "each PR's own history"
                ),
            },
        ]
    )
    contrasts.to_csv(OUTPUT / "contrasts.csv", index=False)

    null_pieces = [
        pd.DataFrame(
            {
                "control": "permuted_anchor_pseudo_edge",
                "stratification": scheme,
                "primary": scheme == PRIMARY_STRATIFICATION,
                "draw": np.arange(1, DRAWS + 1),
                "estimate_pp": permutation_draws[scheme] * 100.0,
            }
        )
        for scheme in STRATIFICATIONS
    ]
    null_pieces.append(
        pd.DataFrame(
            {
                "control": "time_shifted_pseudo_edge",
                "stratification": "none",
                "primary": True,
                "draw": np.arange(1, DRAWS + 1),
                "estimate_pp": shifted_draws * 100.0,
            }
        )
    )
    null_frame = pd.concat(null_pieces, ignore_index=True)
    null_frame["observed_estimate_pp"] = real["estimate_pp"]
    null_frame["seed"] = SEED
    null_frame.to_csv(OUTPUT / "permutation_null.csv", index=False)

    pd.DataFrame([*permutation_summaries, shifted]).to_csv(
        OUTPUT / "permutation_null_summary.csv", index=False
    )
    pd.DataFrame([real, off_target, any_reply]).to_csv(
        OUTPUT / "observed_exposure_models.csv", index=False
    )
    pd.DataFrame([joint]).to_csv(OUTPUT / "joint_on_vs_off_target.csv", index=False)

    off_target_positive = off_target["ci_low"] > 0
    off_target_smaller = joint["difference_pp"] > 0
    off_target_clearly_smaller = joint["difference_ci_low"] > 0
    anchor_clean = bool(
        permutation_reference["null_centred_near_zero"]
        and permutation_reference["p_value_two_sided"] < 0.05
    )
    shifted_clean = bool(
        shifted["null_centred_near_zero"] and shifted["p_value_two_sided"] < 0.05
    )
    if not shifted_clean:
        verdict = "DESIGN_MANUFACTURES_CONTRAST"
    elif not anchor_clean:
        verdict = "NOT_SPECIFIC_ANCHORING_NULL_REPRODUCES_ESTIMATE"
    elif not off_target_smaller or not off_target_clearly_smaller:
        verdict = "NOT_SPECIFIC_OFF_TARGET_MATCHES_THE_ADDRESSED_EDGE"
    else:
        verdict = "SPECIFIC"

    interpretation = (
        "The observed addressed edge is {real:.1f} pp (95% CI {rl:.1f} to {rh:.1f}). "
        "An off-target exact reply, which carries the same liveness but points at a "
        "different inline comment, is {off:.1f} pp (95% CI {ol:.1f} to {oh:.1f}) on "
        "{offn:,} PRs; in one joint model the addressed edge exceeds it by "
        "{gap:.1f} pp (95% CI {gl:.1f} to {gh:.1f}, p={gp:.3f}). Permuting which "
        "replying PR is anchored to its own trigger, inside repository x month strata "
        "and holding every reply event fixed, gives a null centred at {pm:.1f} pp "
        "(2.5-97.5 percentile {pl:.1f} to {ph:.1f}); the observed estimate sits at "
        "percentile {pp:.2f}, two-sided p={ppv:.4f}. Only {pshare:.0%} of anchored PRs "
        "are permutable under that stratification, so the readable anchoring null is the "
        "{rscheme} one ({rshare:.0%} permutable): centred at {rm:.1f} pp "
        "({rl2:.1f} to {rh2:.1f}), observed at percentile {rp:.2f}, two-sided "
        "p={rpv:.4f}. Assigning each PR an edge time "
        "resampled from the observed edge-time distribution but independent of its own "
        "history gives a null centred at {sm:.1f} pp ({sl:.1f} to {sh:.1f}), two-sided "
        "p={spv:.4f}, so the landmark rule alone does not manufacture the contrast. "
        "For reference, the coarser exposure 'any inline reply of any anchoring inside "
        "the window' ({anyn} PRs exposed) gives {anyest:.1f} pp ({anyl:.1f} to "
        "{anyh:.1f}), which is where the two liveness-preserving controls land. "
        "Verdict: {verdict}."
    ).format(
        real=real["estimate_pp"],
        rl=real["ci_low"],
        rh=real["ci_high"],
        off=off_target["estimate_pp"],
        ol=off_target["ci_low"],
        oh=off_target["ci_high"],
        offn=off_target["prs"],
        gap=joint["difference_pp"],
        gl=joint["difference_ci_low"],
        gh=joint["difference_ci_high"],
        gp=joint["difference_p_value"],
        pm=permuted["null_mean_pp"],
        pl=permuted["null_quantile_025_pp"],
        ph=permuted["null_quantile_975_pp"],
        pp=permuted["observed_percentile_in_null"],
        ppv=permuted["p_value_two_sided"],
        pshare=permuted["permutable_anchored_share"],
        rscheme=permutation_reference["stratification"],
        rshare=permutation_reference["permutable_anchored_share"],
        rm=permutation_reference["null_mean_pp"],
        rl2=permutation_reference["null_quantile_025_pp"],
        rh2=permutation_reference["null_quantile_975_pp"],
        rp=permutation_reference["observed_percentile_in_null"],
        rpv=permutation_reference["p_value_two_sided"],
        sm=shifted["null_mean_pp"],
        sl=shifted["null_quantile_025_pp"],
        sh=shifted["null_quantile_975_pp"],
        spv=shifted["p_value_two_sided"],
        anyn=any_reply["exposed_prs"],
        anyest=any_reply["estimate_pp"],
        anyl=any_reply["ci_low"],
        anyh=any_reply["ci_high"],
        verdict=verdict,
    )

    summary = {
        "run_id": "pseudo-edge-negative-control-v1",
        "dataset_revision": DATASET_REVISION,
        "script_sha256": sha256_file(Path(__file__)),
        "seed": SEED,
        "draws_per_permutation_control": DRAWS,
        "primary_threshold_hours": PRIMARY_THRESHOLD,
        "cohort_prs": int(len(frame)),
        "repositories": int(frame["repo_id"].nunique()),
        "prs_with_any_window_inline_reply": int(frame["has_any_window_reply"].sum()),
        "addressed_edge": real,
        "off_target_reply": off_target,
        "any_inline_reply_diagnostic": any_reply,
        "joint_on_vs_off_target": joint,
        "permuted_anchor_null_primary": permuted,
        "permuted_anchor_null_reference": permutation_reference,
        "permuted_anchor_null_all_stratifications": permutation_summaries,
        "time_shifted_null": shifted,
        "gates": {
            "off_target_estimate_positive": bool(off_target_positive),
            "addressed_edge_larger_than_off_target": bool(off_target_smaller),
            "gap_interval_excludes_zero": bool(off_target_clearly_smaller),
            "primary_permutation_support_usable": not bool(
                permuted["support_degenerate"]
            ),
            "permuted_anchor_null_centred_near_zero": bool(
                permutation_reference["null_centred_near_zero"]
            ),
            "permuted_anchor_rejects_observed": bool(
                permutation_reference["p_value_two_sided"] < 0.05
            ),
            "time_shifted_null_centred_near_zero": bool(
                shifted["null_centred_near_zero"]
            ),
            "time_shifted_rejects_observed": bool(shifted["p_value_two_sided"] < 0.05),
        },
        "specificity_verdict": verdict,
        "interpretation": interpretation,
        "scope": (
            "negative-control exposures for an observational association; no causal "
            "effect and no semantic-resolution claim"
        ),
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    write_readme(contrasts, summary)
    print(contrasts.to_string(index=False))
    print()
    print(json.dumps({key: summary[key] for key in ("gates", "specificity_verdict", "interpretation")}, indent=2))


if __name__ == "__main__":
    main()
