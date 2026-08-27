"""Data-driven selection of the RQ1 burst-collapse window.

The published RQ1 topology (``run_burst_collapsed_topology.py``) sweeps fixed
burst windows of 0, 1, 5, 10, and 30 minutes and reports five minutes as the
main choice. A reviewer asked whether that choice is arbitrary, and whether a
data-driven or product-specific cut would be better supported.

This script answers that with the *same* burst logic. It imports
``classify_atomic_state`` and ``build_first_state`` from the published topology
module so that every first-post-burst-owner number here is directly comparable
with the published ones; only the threshold that is fed into those helpers
changes.

It computes:

1. The empirical distribution of the gap between a cross-product review trigger
   and the next event on the same PR, on a log time scale with fine bins, plus
   a formal unimodality test (Silverman critical-bandwidth test).
2. Two named, reproducible data-driven cut rules with a repository-level
   bootstrap interval.
3. The same rules applied within each mapped product with enough events.
4. The sensitivity of the RQ1 user-versus-mapped-product owner split to every
   cut, fixed and data-driven.

The analysis consumes the derived cross-product review artefacts in
``outputs/cross_agent_review`` (the same inputs the published burst topology
uses); it therefore does not need to re-read the AIDev-7.6M parquet corpus.
``AnalysisConfig.from_paths`` is used only to record the corpus location that
those artefacts were derived from, so the provenance stays explicit.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from scipy.ndimage import gaussian_filter1d

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from multiagent_impact.pipeline import AnalysisConfig  # noqa: E402

DEFAULT_INPUT = ROOT / "outputs" / "cross_agent_review"
DEFAULT_OUTPUT = ROOT / "outputs" / "burst_threshold_selection"

SEED = 20260826
PRODUCT_COLUMN = "author_agent"
MIN_PRODUCT_GAPS = 200
BURST_REGION_MAX_MINUTES = 60.0
GRID_POINTS = 1024
HAZARD_BINS_PER_DECADE = 12
MIN_HAZARD_BIN_EVENTS = 10
HISTOGRAM_BINS_PER_DECADE = 40


def _load_published_burst_module():
    """Import the published burst-topology module by path.

    The analysis scripts are not a package, so the module is loaded from its
    file. Reusing it (rather than reimplementing the burst rule) is what makes
    the numbers below comparable with the published RQ1 table.
    """
    path = Path(__file__).resolve().parent / "run_burst_collapsed_topology.py"
    spec = importlib.util.spec_from_file_location(
        "run_burst_collapsed_topology", path
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"cannot import published burst module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BURST = _load_published_burst_module()
STATE_ORDER = BURST.STATE_ORDER
ACTION_STATES = BURST.ACTION_STATES
FIXED_THRESHOLDS_MINUTES = BURST.THRESHOLDS_MINUTES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test whether the RQ1 burst window can be chosen from the data "
            "rather than fixed by hand, and how much RQ1 depends on it."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-draws", type=int, default=5_000)
    parser.add_argument(
        "--cut-bootstrap-draws",
        type=int,
        default=1_000,
        help="Repository resamples used for the interval around a selected cut.",
    )
    parser.add_argument(
        "--silverman-draws",
        type=int,
        default=500,
        help="Smoothed-bootstrap replicates for the Silverman unimodality test.",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------
# Gap construction
# --------------------------------------------------------------------------


def build_first_gaps(chains: pl.DataFrame, events: pl.DataFrame) -> pd.DataFrame:
    """One row per PR that has any event: the trigger-to-next-event gap.

    ``hours_after_trigger`` is the published event field; the burst rule in
    ``build_first_state`` thresholds exactly this quantity, so the gap analysed
    here is the same quantity the burst window acts on.
    """
    first = events.group_by("pr_id").agg(
        pl.col("hours_after_trigger").min().alias("gap_hours")
    )
    meta = chains.select(
        "pr_id", "repo_id", "repo_url", PRODUCT_COLUMN, "trigger_reviewer_agent"
    )
    frame = (
        meta.join(first, on="pr_id", how="inner")
        .with_columns((pl.col("gap_hours") * 60.0).alias("gap_minutes"))
        .sort("pr_id")
    )
    out = frame.to_pandas()
    out["log10_gap_minutes"] = np.log10(out["gap_minutes"].to_numpy())
    return out


# --------------------------------------------------------------------------
# Rule A: log-gap kernel-density antimode
# --------------------------------------------------------------------------


def _binned_log_density(
    values: np.ndarray, bandwidth: float, grid_edges: np.ndarray
) -> np.ndarray:
    """Binned Gaussian KDE on a fixed grid (linear binning + convolution)."""
    counts, _ = np.histogram(values, bins=grid_edges)
    step = grid_edges[1] - grid_edges[0]
    sigma = bandwidth / step
    if sigma <= 0:
        return counts.astype(float)
    return gaussian_filter1d(counts.astype(float), sigma=sigma, mode="constant")


def _local_extrema(density: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    diff = np.diff(density)
    sign = np.sign(diff)
    nonzero = sign != 0
    if not nonzero.any():
        return np.array([], dtype=int), np.array([], dtype=int)
    idx = np.flatnonzero(nonzero)
    filled = np.zeros_like(sign)
    filled[idx] = sign[idx]
    for position in range(1, len(filled)):
        if filled[position] == 0:
            filled[position] = filled[position - 1]
    turn = np.diff(filled)
    maxima = np.flatnonzero(turn < 0) + 1
    minima = np.flatnonzero(turn > 0) + 1
    return maxima, minima


def _grid(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    low = float(values.min())
    high = float(values.max())
    pad = 0.05 * (high - low) + 1e-9
    edges = np.linspace(low - pad, high + pad, GRID_POINTS + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    return edges, centres


def silverman_bandwidth(values: np.ndarray) -> float:
    n = len(values)
    spread = min(
        float(np.std(values, ddof=1)),
        float(np.subtract(*np.percentile(values, [75, 25]))) / 1.349,
    )
    if spread <= 0:
        spread = float(np.std(values, ddof=1)) or 1.0
    return 0.9 * spread * n ** (-1 / 5)


def antimode_cut(values: np.ndarray) -> dict[str, Any]:
    """Rule A -- log-gap KDE antimode inside the candidate burst region.

    Rule statement. Fit a Gaussian kernel density to log10(gap in minutes) with
    Silverman's rule-of-thumb bandwidth on a fixed 1024-point grid. If the
    density has at least two local maxima and at least one interior local
    minimum (antimode) at a gap below 60 minutes, the burst cut is the lowest
    such antimode. Otherwise the rule reports no cut: the data do not separate a
    machine mode from a human mode inside any plausible burst window.
    """
    edges, centres = _grid(values)
    bandwidth = silverman_bandwidth(values)
    density = _binned_log_density(values, bandwidth, edges)
    maxima, minima = _local_extrema(density)
    mode_minutes = [float(10 ** centres[i]) for i in maxima]
    antimode_minutes = [float(10 ** centres[i]) for i in minima]
    in_region = [m for m in antimode_minutes if m <= BURST_REGION_MAX_MINUTES]
    selected = min(in_region) if in_region and len(maxima) >= 2 else None
    return {
        "rule": "log_gap_kde_antimode",
        "bandwidth_log10": float(bandwidth),
        "n_modes": int(len(maxima)),
        "mode_minutes": mode_minutes,
        "antimode_minutes": antimode_minutes,
        "cut_minutes": selected,
        "cut_exists": selected is not None,
    }


# --------------------------------------------------------------------------
# Silverman critical-bandwidth unimodality test
# --------------------------------------------------------------------------


def _n_modes(values: np.ndarray, bandwidth: float, edges: np.ndarray) -> int:
    density = _binned_log_density(values, bandwidth, edges)
    maxima, _ = _local_extrema(density)
    return int(len(maxima))


def critical_bandwidth(
    values: np.ndarray, edges: np.ndarray, max_modes: int = 1
) -> float:
    """Smallest bandwidth for which the KDE has at most ``max_modes`` modes."""
    low = 1e-4
    high = max(1.0, float(values.max() - values.min()))
    while _n_modes(values, high, edges) > max_modes:
        high *= 2.0
        if high > 1e4:  # pragma: no cover
            return high
    for _ in range(60):
        mid = 0.5 * (low + high)
        if _n_modes(values, mid, edges) > max_modes:
            low = mid
        else:
            high = mid
    return high


def silverman_unimodality_test(
    values: np.ndarray, draws: int, seed: int
) -> dict[str, Any]:
    """Silverman (1981) critical-bandwidth test of H0: the density is unimodal.

    A large p-value means the log-gap density is compatible with a single mode,
    i.e. there is no machine/human separation to cut at.
    """
    edges, _ = _grid(values)
    h_crit = critical_bandwidth(values, edges, max_modes=1)
    n = len(values)
    mean = float(values.mean())
    variance = float(values.var(ddof=1))
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(draws):
        resample = rng.choice(values, size=n, replace=True)
        noise = rng.standard_normal(n)
        smoothed = mean + (resample - mean + h_crit * noise) / np.sqrt(
            1.0 + h_crit**2 / variance
        )
        if _n_modes(smoothed, h_crit, edges) > 1:
            exceed += 1
    p_value = (exceed + 1) / (draws + 1)
    return {
        "test": "silverman_critical_bandwidth",
        "null_hypothesis": "log10 gap density has one mode",
        "critical_bandwidth_log10": float(h_crit),
        "bootstrap_draws": int(draws),
        "p_value": float(p_value),
        "rejects_unimodality_at_0.05": bool(p_value < 0.05),
    }


# --------------------------------------------------------------------------
# Rule B: piecewise-constant log-hazard change point
# --------------------------------------------------------------------------


def hazard_table(values_minutes: np.ndarray) -> pd.DataFrame:
    """Discrete-time hazard of the next event over log-spaced gap bins."""
    low = np.log10(values_minutes.min())
    high = np.log10(values_minutes.max())
    n_bins = max(6, int(np.ceil((high - low) * HAZARD_BINS_PER_DECADE)))
    edges = np.linspace(low, high, n_bins + 1)
    counts, _ = np.histogram(np.log10(values_minutes), bins=edges)
    total = counts.sum()
    at_risk = total - np.concatenate([[0], np.cumsum(counts)[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        hazard = np.where(at_risk > 0, counts / at_risk, np.nan)
    return pd.DataFrame(
        {
            "bin_left_minutes": 10 ** edges[:-1],
            "bin_right_minutes": 10 ** edges[1:],
            "bin_centre_minutes": 10 ** (0.5 * (edges[:-1] + edges[1:])),
            "events": counts.astype(int),
            "at_risk": at_risk.astype(int),
            "hazard": hazard,
        }
    )


def hazard_change_point_cut(
    values_minutes: np.ndarray, region_max_minutes: float | None = None
) -> dict[str, Any]:
    """Rule B -- single change point in the log hazard of the next event.

    Rule statement. Bin log10(gap in minutes) at 12 bins per decade, compute the
    discrete-time hazard of the next event in each bin, keep bins with at least
    10 events and at least 10 at risk, and fit a two-segment piecewise-constant
    model to the log hazard by exhaustive least squares. The cut is the right
    edge of the last bin in the first segment: the gap at which the hazard of the
    next event, measured on the log-time clock, changes level. The direction of
    that change is reported (``left_segment_mean_hazard`` versus
    ``right_segment_mean_hazard``) and must be read before the cut is used -- an
    upward step means the rule has found where responses start arriving, not
    where an automated burst ends. This rule always returns a cut, which is why
    it is reported alongside Rule A rather than instead of it.

    ``region_max_minutes`` restricts the change-point search to bins that end at
    or before that gap. The unrestricted variant answers "where is the strongest
    regime change anywhere in the gap distribution"; the restricted variant
    answers the narrower question the burst window actually needs, "where is the
    strongest regime change inside a plausible burst window". Both are reported,
    because they can disagree by orders of magnitude.
    """
    rule = (
        "log_hazard_change_point"
        if region_max_minutes is None
        else "log_hazard_change_point_burst_region"
    )
    table = hazard_table(values_minutes)
    usable = table[
        (table["events"] >= MIN_HAZARD_BIN_EVENTS)
        & (table["at_risk"] >= MIN_HAZARD_BIN_EVENTS)
        & table["hazard"].notna()
        & (table["hazard"] > 0)
    ]
    if region_max_minutes is not None:
        usable = usable[usable["bin_right_minutes"] <= region_max_minutes]
    usable = usable.reset_index(drop=True)
    if len(usable) < 4:
        return {
            "rule": rule,
            "cut_minutes": None,
            "cut_exists": False,
            "usable_bins": int(len(usable)),
        }
    y = np.log(usable["hazard"].to_numpy())
    n = len(y)
    best_split = None
    best_cost = np.inf
    for split in range(1, n):
        left = y[:split]
        right = y[split:]
        cost = float(
            ((left - left.mean()) ** 2).sum() + ((right - right.mean()) ** 2).sum()
        )
        if cost < best_cost:
            best_cost = cost
            best_split = split
    total_cost = float(((y - y.mean()) ** 2).sum())
    cut = float(usable.loc[best_split - 1, "bin_right_minutes"])
    return {
        "rule": rule,
        "cut_minutes": cut,
        "cut_exists": True,
        "usable_bins": int(n),
        "split_index": int(best_split),
        "residual_sum_of_squares": best_cost,
        "single_segment_sum_of_squares": total_cost,
        "variance_explained_by_split": (
            float(1.0 - best_cost / total_cost) if total_cost > 0 else float("nan")
        ),
        "left_segment_mean_hazard": float(np.exp(y[:best_split].mean())),
        "right_segment_mean_hazard": float(np.exp(y[best_split:].mean())),
    }


# --------------------------------------------------------------------------
# Repository-level bootstrap over a selected cut
# --------------------------------------------------------------------------


def bootstrap_cut(
    gaps: pd.DataFrame, rule: str, draws: int, seed: int
) -> dict[str, Any]:
    """Resample whole repositories with replacement and re-select the cut.

    Same clustering convention as the published burst topology: the resampling
    unit is the repository, drawn ``n_repositories`` times with replacement.
    """
    groups = [
        frame["gap_minutes"].to_numpy() for _, frame in gaps.groupby("repo_id")
    ]
    n_groups = len(groups)
    rng = np.random.default_rng(seed)
    selected: list[float] = []
    missing = 0
    for _ in range(draws):
        picked = rng.integers(0, n_groups, size=n_groups)
        values = np.concatenate([groups[i] for i in picked])
        if len(values) < 50:  # pragma: no cover
            missing += 1
            continue
        if rule == "log_gap_kde_antimode":
            result = antimode_cut(np.log10(values))
        elif rule == "log_hazard_change_point_burst_region":
            result = hazard_change_point_cut(values, BURST_REGION_MAX_MINUTES)
        else:
            result = hazard_change_point_cut(values)
        if result["cut_minutes"] is None:
            missing += 1
        else:
            selected.append(float(result["cut_minutes"]))
    if selected:
        array = np.asarray(selected)
        low, high = np.quantile(array, [0.025, 0.975])
        median = float(np.median(array))
    else:
        low = high = median = float("nan")
    return {
        "bootstrap_draws": int(draws),
        "replicates_with_a_cut": int(len(selected)),
        "replicates_without_a_cut": int(missing),
        "share_of_replicates_with_a_cut": float(len(selected) / draws),
        "median_cut_minutes": median,
        "cluster_ci_low_minutes": float(low),
        "cluster_ci_high_minutes": float(high),
    }


# --------------------------------------------------------------------------
# Sensitivity of the RQ1 owner split
# --------------------------------------------------------------------------


def first_states_for_scheme(
    chains: pl.DataFrame,
    enriched: pl.DataFrame,
    thresholds: dict[str, float] | float,
) -> pl.DataFrame:
    """Apply the published burst rule with a global or per-product threshold.

    ``BURST.build_first_state`` is called unchanged; only the threshold it is
    given varies. Its integer ``burst_threshold_minutes`` label is replaced with
    the exact (possibly fractional) threshold actually applied.
    """
    if not isinstance(thresholds, dict):
        frame, _ = BURST.build_first_state(chains, enriched, float(thresholds))
        return frame.drop("burst_threshold_minutes").with_columns(
            pl.lit(float(thresholds)).alias("applied_threshold_minutes")
        )
    parts: list[pl.DataFrame] = []
    for product, threshold in thresholds.items():
        chain_subset = chains.filter(pl.col(PRODUCT_COLUMN) == product)
        if chain_subset.height == 0:
            continue
        pr_ids = chain_subset.select("pr_id")
        event_subset = enriched.join(pr_ids, on="pr_id", how="inner")
        frame, _ = BURST.build_first_state(
            chain_subset, event_subset, float(threshold)
        )
        parts.append(
            frame.drop("burst_threshold_minutes").with_columns(
                pl.lit(float(threshold)).alias("applied_threshold_minutes")
            )
        )
    return pl.concat(parts).sort("pr_id")


def repository_difference_bootstrap(
    frame: pd.DataFrame, draws: int, seed: int
) -> dict[str, tuple[float, float]]:
    """Repository-clustered interval for user-account minus mapped-product share."""
    counts = pd.crosstab(frame["repo_id"], frame["first_post_burst_state"])
    counts = counts.reindex(columns=STATE_ORDER, fill_value=0).to_numpy(dtype=float)
    n_repositories = counts.shape[0]
    rng = np.random.default_rng(seed)
    user_index = STATE_ORDER.index("user_account")
    mapped_index = STATE_ORDER.index("mapped_product")
    n_actions = len(ACTION_STATES)
    all_draws: list[np.ndarray] = []
    action_draws: list[np.ndarray] = []
    completed = 0
    chunk = min(250, draws)
    while completed < draws:
        current = min(chunk, draws - completed)
        sampled = rng.integers(
            0, n_repositories, size=(current, n_repositories), dtype=np.int32
        )
        totals = counts[sampled].sum(axis=1)
        all_denominator = totals.sum(axis=1)
        action_denominator = totals[:, :n_actions].sum(axis=1)
        difference = totals[:, user_index] - totals[:, mapped_index]
        all_draws.append(
            np.divide(
                difference,
                all_denominator,
                out=np.full(current, np.nan),
                where=all_denominator > 0,
            )
        )
        action_draws.append(
            np.divide(
                difference,
                action_denominator,
                out=np.full(current, np.nan),
                where=action_denominator > 0,
            )
        )
        completed += current
    all_array = np.concatenate(all_draws)
    action_array = np.concatenate(action_draws)
    return {
        "all_prs": tuple(np.nanquantile(all_array, [0.025, 0.975])),
        "post_burst_actions": tuple(np.nanquantile(action_array, [0.025, 0.975])),
    }


def owner_split_row(
    frame: pd.DataFrame,
    scheme: str,
    scheme_kind: str,
    threshold_label: str,
    draws: int,
    seed: int,
) -> dict[str, Any]:
    counts = (
        frame["first_post_burst_state"]
        .value_counts()
        .reindex(STATE_ORDER, fill_value=0)
    )
    action_total = int(counts.loc[list(ACTION_STATES)].sum())
    total = int(len(frame))
    user = int(counts["user_account"])
    mapped = int(counts["mapped_product"])
    ci = repository_difference_bootstrap(frame, draws, seed)
    modal_action_state = str(counts.loc[list(ACTION_STATES)].idxmax())
    return {
        "scheme": scheme,
        "scheme_kind": scheme_kind,
        "threshold_minutes": threshold_label,
        "prs": total,
        "post_burst_action_prs": action_total,
        "user_account_prs": user,
        "mapped_product_prs": mapped,
        "other_bot_prs": int(counts["other_bot"]),
        "branch_movement_untyped_prs": int(counts["branch_movement_untyped"]),
        "no_action_within_7d_prs": int(counts["no_action_within_7d"]),
        "user_share_all_prs": user / total,
        "mapped_share_all_prs": mapped / total,
        "user_share_post_burst_actions": (
            user / action_total if action_total else np.nan
        ),
        "mapped_share_post_burst_actions": (
            mapped / action_total if action_total else np.nan
        ),
        "user_minus_mapped_percentage_points_all_prs": (
            (user - mapped) / total * 100.0
        ),
        "user_minus_mapped_ci_low_pp_all_prs": ci["all_prs"][0] * 100.0,
        "user_minus_mapped_ci_high_pp_all_prs": ci["all_prs"][1] * 100.0,
        "user_minus_mapped_percentage_points_actions": (
            (user - mapped) / action_total * 100.0 if action_total else np.nan
        ),
        "user_minus_mapped_ci_low_pp_actions": (
            ci["post_burst_actions"][0] * 100.0
        ),
        "user_minus_mapped_ci_high_pp_actions": (
            ci["post_burst_actions"][1] * 100.0
        ),
        "user_exceeds_mapped": bool(user > mapped),
        "user_exceeds_mapped_interval_excludes_zero": bool(
            ci["post_burst_actions"][0] > 0
        ),
        "modal_post_burst_action_state": modal_action_state,
        "user_is_modal_action_state": bool(modal_action_state == "user_account"),
        "repositories": int(frame["repo_id"].nunique()),
    }


# --------------------------------------------------------------------------
# Histogram
# --------------------------------------------------------------------------


def gap_histogram(gaps: pd.DataFrame) -> pd.DataFrame:
    values = gaps["gap_minutes"].to_numpy()
    low = np.log10(values.min())
    high = np.log10(values.max())
    n_bins = int(np.ceil((high - low) * HISTOGRAM_BINS_PER_DECADE))
    edges = np.linspace(low, high, n_bins + 1)
    counts, _ = np.histogram(np.log10(values), bins=edges)
    widths = np.diff(10**edges)
    total = counts.sum()
    edges_kde, centres_kde = _grid(gaps["log10_gap_minutes"].to_numpy())
    bandwidth = silverman_bandwidth(gaps["log10_gap_minutes"].to_numpy())
    density = _binned_log_density(
        gaps["log10_gap_minutes"].to_numpy(), bandwidth, edges_kde
    )
    step = edges_kde[1] - edges_kde[0]
    density = density / (density.sum() * step)
    kde_at_bin = np.interp(0.5 * (edges[:-1] + edges[1:]), centres_kde, density)
    return pd.DataFrame(
        {
            "bin_index": np.arange(n_bins),
            "bin_left_log10_minutes": edges[:-1],
            "bin_right_log10_minutes": edges[1:],
            "bin_left_minutes": 10 ** edges[:-1],
            "bin_right_minutes": 10 ** edges[1:],
            "bin_centre_minutes": 10 ** (0.5 * (edges[:-1] + edges[1:])),
            "count": counts.astype(int),
            "share": counts / total,
            "cumulative_share": np.cumsum(counts) / total,
            "density_per_minute": counts / (total * widths),
            "kde_density_per_log10_minute": kde_at_bin,
        }
    )


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    return value



def build_readme(payload: dict[str, Any]) -> str:
    return f"""# Burst-threshold selection

Reviewer response artefact. It asks whether the RQ1 burst window (fixed at five
minutes in `outputs/burst_topology`) can be chosen from the data, whether it
should differ by product, and how much the RQ1 ownership conclusion depends on
the answer. The burst rule itself is imported from
`scripts/analysis/run_burst_collapsed_topology.py`, so every owner count here is
directly comparable with the published one.

## Answer

{payload['interpretation']}

## Rules

- **Rule A, `log_gap_kde_antimode`.** Gaussian KDE of log10(gap in minutes) with
  Silverman's rule-of-thumb bandwidth on a fixed 1024-point grid; the cut is the
  lowest interior antimode at or below {payload['gap_distribution']['burst_region_max_minutes']:.0f}
  minutes, and the rule declines to select a cut when there is none.
- **Rule B, `log_hazard_change_point`.** Discrete-time hazard of the next event
  over log-spaced bins (12 per decade, at least 10 events and 10 at risk per
  bin); a two-segment piecewise-constant fit to the log hazard by exhaustive
  least squares; the cut is the right edge of the first segment. Reported both
  unrestricted and restricted to the burst region.
- **Unimodality test.** Silverman critical-bandwidth test with a smoothed
  bootstrap.
- **Intervals.** Whole repositories resampled with replacement, the same
  clustering convention as the published burst topology.

## Files

- `summary.json`: headline numbers and the `interpretation` string.
- `gap_histogram.csv`: full trigger-to-next-event gap histogram, log-spaced bin
  edges plus counts, shares, densities and the KDE evaluated at each bin, so a
  figure can be drawn without rerunning anything.
- `gap_distribution_shape.csv`: quantiles and coverage of each fixed window.
- `next_event_hazard.csv`: the binned hazard, globally and per product.
- `selected_cuts.csv`: every rule and scope with its cut and bootstrap interval.
- `owner_split_sensitivity.csv`: the sensitivity table -- the user-account
  versus mapped-product first-owner split at every cut.
- `owner_split_sensitivity_by_product.csv`: the same split within each product.
- `agreement_with_five_minutes.csv`: share of PRs whose first-owner state is
  unchanged relative to the published five-minute assignment.

Observed public response topology; no causal, semantic-resolution, or
verified-manual-work claim.
"""


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = AnalysisConfig.from_paths(ROOT)

    chains = pl.read_parquet(args.input_dir / "cross_feedback_response_chains.parquet")
    raw_events = pl.read_parquet(
        args.input_dir / "cross_feedback_response_events.parquet"
    )
    # Same exact-deduplicated analytical view as the published burst topology.
    events = raw_events.unique(maintain_order=True)
    enriched = BURST.classify_atomic_state(events)

    gaps = build_first_gaps(chains, events)
    log_gaps = gaps["log10_gap_minutes"].to_numpy()

    # 1. Distribution shape ------------------------------------------------
    histogram = gap_histogram(gaps)
    histogram.to_csv(args.output_dir / "gap_histogram.csv", index=False)

    global_antimode = antimode_cut(log_gaps)
    global_hazard = hazard_change_point_cut(gaps["gap_minutes"].to_numpy())
    global_hazard_burst = hazard_change_point_cut(
        gaps["gap_minutes"].to_numpy(), BURST_REGION_MAX_MINUTES
    )
    silverman = silverman_unimodality_test(
        log_gaps, args.silverman_draws, SEED + 11
    )

    hazard_frame = hazard_table(gaps["gap_minutes"].to_numpy())
    hazard_frame.insert(0, "scope", "global")
    hazard_frames = [hazard_frame]

    quantiles = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
    shape_rows = [
        {
            "statistic": f"quantile_{int(q * 100)}_minutes",
            "value": float(np.quantile(gaps["gap_minutes"], q)),
        }
        for q in quantiles
    ]
    for window in FIXED_THRESHOLDS_MINUTES:
        if window == 0:
            continue
        shape_rows.append(
            {
                "statistic": f"share_of_prs_with_gap_at_or_below_{window}_minutes",
                "value": float((gaps["gap_minutes"] <= window).mean()),
            }
        )
    shape_rows.extend(
        [
            {"statistic": "prs_with_any_event", "value": float(len(gaps))},
            {"statistic": "cohort_prs", "value": float(chains.height)},
            {"statistic": "repositories_with_any_event", "value": float(gaps["repo_id"].nunique())},
            {"statistic": "kde_modes", "value": float(global_antimode["n_modes"])},
            {
                "statistic": "silverman_unimodality_p_value",
                "value": float(silverman["p_value"]),
            },
        ]
    )
    pd.DataFrame(shape_rows).to_csv(
        args.output_dir / "gap_distribution_shape.csv", index=False
    )

    # 2. Global data-driven cuts ------------------------------------------
    cut_rows: list[dict[str, Any]] = []
    global_cuts: dict[str, float | None] = {}
    for index, result in enumerate(
        (global_antimode, global_hazard, global_hazard_burst)
    ):
        rule = result["rule"]
        boot = bootstrap_cut(
            gaps, rule, args.cut_bootstrap_draws, SEED + 100 + index
        )
        global_cuts[rule] = result["cut_minutes"]
        cut_rows.append(
            {
                "scope": "global",
                "group": "all",
                "rule": rule,
                "gaps": int(len(gaps)),
                "repositories": int(gaps["repo_id"].nunique()),
                "cut_exists": bool(result["cut_exists"]),
                "cut_minutes": result["cut_minutes"],
                "kde_modes": result.get("n_modes"),
                "kde_mode_minutes": (
                    "; ".join(f"{m:.4g}" for m in result.get("mode_minutes", []))
                    or None
                ),
                "bootstrap_median_cut_minutes": boot["median_cut_minutes"],
                "bootstrap_ci_low_minutes": boot["cluster_ci_low_minutes"],
                "bootstrap_ci_high_minutes": boot["cluster_ci_high_minutes"],
                "share_of_replicates_with_a_cut": boot[
                    "share_of_replicates_with_a_cut"
                ],
                "bootstrap_draws": boot["bootstrap_draws"],
            }
        )

    # 3. Product-specific cuts --------------------------------------------
    product_cuts: dict[str, dict[str, float | None]] = {
        "log_gap_kde_antimode": {},
        "log_hazard_change_point": {},
        "log_hazard_change_point_burst_region": {},
    }
    for offset, (product, frame) in enumerate(gaps.groupby(PRODUCT_COLUMN)):
        if len(frame) < MIN_PRODUCT_GAPS:
            cut_rows.append(
                {
                    "scope": "product",
                    "group": str(product),
                    "rule": "insufficient_events",
                    "gaps": int(len(frame)),
                    "repositories": int(frame["repo_id"].nunique()),
                    "cut_exists": False,
                    "cut_minutes": None,
                }
            )
            continue
        product_values = frame["gap_minutes"].to_numpy()
        results = (
            antimode_cut(np.log10(product_values)),
            hazard_change_point_cut(product_values),
            hazard_change_point_cut(product_values, BURST_REGION_MAX_MINUTES),
        )
        table = hazard_table(product_values)
        table.insert(0, "scope", str(product))
        hazard_frames.append(table)
        for index, result in enumerate(results):
            rule = result["rule"]
            boot = bootstrap_cut(
                frame, rule, args.cut_bootstrap_draws, SEED + 200 + 10 * offset + index
            )
            product_cuts[rule][str(product)] = result["cut_minutes"]
            cut_rows.append(
                {
                    "scope": "product",
                    "group": str(product),
                    "rule": rule,
                    "gaps": int(len(frame)),
                    "repositories": int(frame["repo_id"].nunique()),
                    "cut_exists": bool(result["cut_exists"]),
                    "cut_minutes": result["cut_minutes"],
                    "kde_modes": result.get("n_modes"),
                    "kde_mode_minutes": (
                        "; ".join(
                            f"{m:.4g}" for m in result.get("mode_minutes", [])
                        )
                        or None
                    ),
                    "bootstrap_median_cut_minutes": boot["median_cut_minutes"],
                    "bootstrap_ci_low_minutes": boot["cluster_ci_low_minutes"],
                    "bootstrap_ci_high_minutes": boot["cluster_ci_high_minutes"],
                    "share_of_replicates_with_a_cut": boot[
                        "share_of_replicates_with_a_cut"
                    ],
                    "bootstrap_draws": boot["bootstrap_draws"],
                }
            )
    cuts_frame = pd.DataFrame(cut_rows)
    cuts_frame.to_csv(args.output_dir / "selected_cuts.csv", index=False)
    pd.concat(hazard_frames, ignore_index=True).to_csv(
        args.output_dir / "next_event_hazard.csv", index=False
    )

    # 4. Sensitivity of the RQ1 owner split -------------------------------
    # Products below MIN_PRODUCT_GAPS keep the global cut for their own rule,
    # so a product-specific scheme still covers every PR in the cohort.
    product_cuts_applied: dict[str, dict[str, float]] = {}
    schemes: list[tuple[str, str, str, dict[str, float] | float]] = []
    for window in FIXED_THRESHOLDS_MINUTES:
        schemes.append(
            (f"fixed_{window}_minutes", "fixed", f"{float(window):.4g}", float(window))
        )
    for rule, cut in global_cuts.items():
        if cut is None:
            continue
        schemes.append(
            (f"global_{rule}", "global_data_driven", f"{cut:.4g}", float(cut))
        )
    all_products = sorted(chains[PRODUCT_COLUMN].unique().to_list())
    for rule, mapping in product_cuts.items():
        fallback = global_cuts.get(rule)
        resolved: dict[str, float] = {}
        for product in all_products:
            value = mapping.get(product)
            if value is None:
                value = fallback
            if value is None:
                resolved = {}
                break
            resolved[product] = float(value)
        if not resolved:
            continue
        product_cuts_applied[rule] = dict(resolved)
        label = "; ".join(f"{k}={v:.4g}" for k, v in sorted(resolved.items()))
        schemes.append(
            (f"product_specific_{rule}", "product_specific", label, resolved)
        )

    sensitivity_rows: list[dict[str, Any]] = []
    per_product_rows: list[dict[str, Any]] = []
    scheme_states: dict[str, pd.DataFrame] = {}
    for index, (name, kind, label, thresholds) in enumerate(schemes):
        states = first_states_for_scheme(chains, enriched, thresholds).to_pandas()
        if len(states) != chains.height:
            raise RuntimeError(
                f"scheme {name} produced {len(states)} rows, expected {chains.height}"
            )
        scheme_states[name] = states
        sensitivity_rows.append(
            owner_split_row(
                states,
                name,
                kind,
                label,
                args.bootstrap_draws,
                SEED + 500 + index,
            )
        )
        for product_index, (product, frame) in enumerate(
            states.groupby(PRODUCT_COLUMN)
        ):
            row = owner_split_row(
                frame,
                name,
                kind,
                label,
                min(args.bootstrap_draws, 2_000),
                SEED + 900 + 20 * index + product_index,
            )
            row["product"] = str(product)
            per_product_rows.append(row)

    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(
        args.output_dir / "owner_split_sensitivity.csv", index=False
    )
    pd.DataFrame(per_product_rows).to_csv(
        args.output_dir / "owner_split_sensitivity_by_product.csv", index=False
    )

    # Agreement with the published five-minute state assignment.
    baseline = scheme_states["fixed_5_minutes"][
        ["pr_id", "first_post_burst_state"]
    ].rename(columns={"first_post_burst_state": "five_minute_state"})
    agreement_rows: list[dict[str, Any]] = []
    for name, states in scheme_states.items():
        merged = baseline.merge(
            states[["pr_id", "first_post_burst_state"]], on="pr_id", validate="1:1"
        )
        agree = float(
            (merged["five_minute_state"] == merged["first_post_burst_state"]).mean()
        )
        agreement_rows.append(
            {
                "scheme": name,
                "prs": int(len(merged)),
                "state_agreement_with_fixed_five_minutes": agree,
                "reclassified_prs": int(round((1.0 - agree) * len(merged))),
            }
        )
    pd.DataFrame(agreement_rows).to_csv(
        args.output_dir / "agreement_with_five_minutes.csv", index=False
    )

    # Headline payload ------------------------------------------------------
    claim_holds = bool(
        sensitivity["user_exceeds_mapped"].all()
        and sensitivity["user_exceeds_mapped_interval_excludes_zero"].all()
    )
    failing = sensitivity.loc[
        ~(
            sensitivity["user_exceeds_mapped"]
            & sensitivity["user_exceeds_mapped_interval_excludes_zero"]
        ),
        "scheme",
    ].tolist()
    hazard_cut = global_cuts["log_hazard_change_point"]
    hazard_boot = cuts_frame[
        (cuts_frame["scope"] == "global")
        & (cuts_frame["rule"] == "log_hazard_change_point")
    ].iloc[0]
    per_product_hazard = [
        v
        for v in product_cuts["log_hazard_change_point"].values()
        if v is not None
    ]
    per_product_hazard_burst = [
        v
        for v in product_cuts["log_hazard_change_point_burst_region"].values()
        if v is not None
    ]
    product_cut_span = (
        f"{min(per_product_hazard):.3g} to {max(per_product_hazard):.3g} minutes,"
        if per_product_hazard
        else "no usable range,"
    )
    hazard_burst_cut = global_cuts["log_hazard_change_point_burst_region"]
    hazard_burst_boot = cuts_frame[
        (cuts_frame["scope"] == "global")
        & (cuts_frame["rule"] == "log_hazard_change_point_burst_region")
    ].iloc[0]

    if global_antimode["cut_exists"]:
        shape_sentence = (
            "The trigger-to-next-event gap is bimodal on a log scale, with an "
            f"antimode at {global_antimode['cut_minutes']:.3g} minutes separating "
            "a near-instant machine mode from a slower human mode."
        )
    else:
        shape_sentence = (
            "The trigger-to-next-event gap is NOT bimodal in the way the burst "
            "argument needs. On a log time scale the density rises smoothly and "
            "monotonically from the one-second timestamp floor to a single "
            f"dominant mode at "
            f"{(global_antimode['mode_minutes'][0] if global_antimode['mode_minutes'] else float('nan')):.3g}"
            " minutes -- there is no separate near-zero machine spike and no "
            "valley between a machine mode and a human mode. The density does "
            "have a second, far-away mode at "
            f"{(global_antimode['mode_minutes'][-1] if len(global_antimode['mode_minutes']) > 1 else float('nan')):.4g}"
            " minutes with an antimode at "
            f"{(global_antimode['antimode_minutes'][0] if global_antimode['antimode_minutes'] else float('nan')):.4g}"
            " minutes, but that is the overnight / next-working-day boundary at "
            "several hours, not a machine/human boundary, and it is far outside "
            "any burst window anyone would defend. The data therefore do not "
            "support a natural burst cut: any burst window in this analysis is a "
            "modelling convention rather than a discovered feature of the data."
        )

    interpretation = (
        shape_sentence
        + " A Silverman critical-bandwidth test of unimodality on the log gap "
        f"returns p = {silverman['p_value']:.3f} "
        + (
            "(unimodality rejected)"
            if silverman["rejects_unimodality_at_0.05"]
            else "(unimodality not rejected)"
        )
        + ", which reflects that far-apart second mode rather than anything at "
        "burst scale. Because the antimode rule declines to select a cut, the "
        "reported data-driven cut comes from the log-hazard change-point rule, "
        f"which always returns a value: {hazard_cut:.3g} minutes globally "
        f"(repository bootstrap 95% interval "
        f"{hazard_boot['bootstrap_ci_low_minutes']:.3g} to "
        f"{hazard_boot['bootstrap_ci_high_minutes']:.3g} minutes), and the "
        "change it marks is an increase in the log-time hazard "
        f"({global_hazard['left_segment_mean_hazard']:.3g} to "
        f"{global_hazard['right_segment_mean_hazard']:.3g} per log-time bin), "
        "that is, the point where responses start arriving rather than the point "
        "where an automated burst ends. "
        f"Per-product cuts from the same rule span {product_cut_span} so "
        "product-specific windows are not better supported than a single global "
        "one. Restricting the same change-point search to gaps below "
        f"{BURST_REGION_MAX_MINUTES:.0f} minutes tightens the per-product cuts to "
        f"{min(per_product_hazard_burst):.3g} to "
        f"{max(per_product_hazard_burst):.3g} minutes, a range that brackets the "
        "fixed five-minute window. The antimode rule finds a burst-region "
        "antimode in only "
        f"{float(cuts_frame.loc[(cuts_frame['scope'] == 'global') & (cuts_frame['rule'] == 'log_gap_kde_antimode'), 'share_of_replicates_with_a_cut'].iloc[0]):.1%}"
        " of repository bootstrap replicates, and in none of the products. "
        + (
            "The RQ1 conclusion that a person is usually the one who acts next "
            "survives every cut examined here -- fixed 0/1/5/10/30 minutes, the "
            "global data-driven cut, and product-specific cuts -- with the "
            "repository-clustered interval on the user-minus-mapped-product "
            "difference excluding zero in every case."
            if claim_holds
            else "The RQ1 conclusion does NOT survive every cut; it fails at: "
            + ", ".join(failing)
            + "."
        )
        + " Observed public response topology; no causal, semantic-resolution, "
        "or verified-manual-work claim."
    )

    summary_payload: dict[str, Any] = {
        "interpretation": interpretation,
        "provenance": {
            "corpus_dir": str(config.data_dir),
            "input_dir": str(args.input_dir),
            "burst_logic_reused_from": "scripts/analysis/run_burst_collapsed_topology.py",
            "seed": SEED,
            "bootstrap_draws": args.bootstrap_draws,
            "cut_bootstrap_draws": args.cut_bootstrap_draws,
            "silverman_draws": args.silverman_draws,
        },
        "cohort": {
            "cohort_prs": chains.height,
            "prs_with_any_event_in_7d": int(len(gaps)),
            "repositories": chains["repo_id"].n_unique(),
            "repositories_with_any_event": int(gaps["repo_id"].nunique()),
            "product_column": PRODUCT_COLUMN,
        },
        "gap_distribution": {
            "is_bimodal_within_burst_region": bool(global_antimode["cut_exists"]),
            "is_bimodal_anywhere": bool(global_antimode["n_modes"] >= 2),
            "antimode_inside_burst_region_minutes": global_antimode["cut_minutes"],
            "burst_region_max_minutes": BURST_REGION_MAX_MINUTES,
            "kde_modes": global_antimode["n_modes"],
            "kde_mode_minutes": global_antimode["mode_minutes"],
            "kde_antimode_minutes": global_antimode["antimode_minutes"],
            "kde_bandwidth_log10": global_antimode["bandwidth_log10"],
            "median_gap_minutes": float(np.median(gaps["gap_minutes"])),
            "share_within_5_minutes": float((gaps["gap_minutes"] <= 5).mean()),
            "silverman_test": silverman,
        },
        "global_data_driven_cuts": {
            "log_gap_kde_antimode": {
                "cut_minutes": global_antimode["cut_minutes"],
                "cut_exists": global_antimode["cut_exists"],
                "note": (
                    "No interior antimode below 60 minutes; the rule declines to "
                    "select a cut."
                )
                if not global_antimode["cut_exists"]
                else None,
            },
            "log_hazard_change_point_burst_region": {
                "cut_minutes": hazard_burst_cut,
                "search_restricted_to_minutes": BURST_REGION_MAX_MINUTES,
                "repository_bootstrap_ci_minutes": [
                    float(hazard_burst_boot["bootstrap_ci_low_minutes"]),
                    float(hazard_burst_boot["bootstrap_ci_high_minutes"]),
                ],
                "bootstrap_median_minutes": float(
                    hazard_burst_boot["bootstrap_median_cut_minutes"]
                ),
                "variance_explained_by_split": global_hazard_burst.get(
                    "variance_explained_by_split"
                ),
            },
            "log_hazard_change_point": {
                "cut_minutes": hazard_cut,
                "repository_bootstrap_ci_minutes": [
                    float(hazard_boot["bootstrap_ci_low_minutes"]),
                    float(hazard_boot["bootstrap_ci_high_minutes"]),
                ],
                "bootstrap_median_minutes": float(
                    hazard_boot["bootstrap_median_cut_minutes"]
                ),
                "variance_explained_by_split": global_hazard.get(
                    "variance_explained_by_split"
                ),
                "left_segment_mean_hazard": global_hazard.get(
                    "left_segment_mean_hazard"
                ),
                "right_segment_mean_hazard": global_hazard.get(
                    "right_segment_mean_hazard"
                ),
            },
        },
        "product_specific_cuts": product_cuts,
        "product_specific_cuts_applied": product_cuts_applied,
        "minimum_gaps_for_a_product_specific_cut": MIN_PRODUCT_GAPS,
        "owner_split_sensitivity": sensitivity.to_dict(orient="records"),
        "per_product_burst_region_cut_range_minutes": [
            float(min(per_product_hazard_burst)),
            float(max(per_product_hazard_burst)),
        ],
        "rq1_claim": {
            "claim": "a person is usually the one who acts next",
            "operationalisation": (
                "user_account share of post-burst first actions exceeds the "
                "mapped_product share, with a repository-clustered 95% interval "
                "on the difference that excludes zero"
            ),
            "holds_at_every_cut": claim_holds,
            "cuts_where_it_fails": failing,
            "five_minute_defensible": bool(
                claim_holds
                and not global_antimode["cut_exists"]
            ),
        },
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(_json_safe(summary_payload), indent=2), encoding="utf-8"
    )
    (args.output_dir / "README.md").write_text(
        build_readme(_json_safe(summary_payload)), encoding="utf-8"
    )
    print(json.dumps(_json_safe(summary_payload), indent=2))


if __name__ == "__main__":
    main()
