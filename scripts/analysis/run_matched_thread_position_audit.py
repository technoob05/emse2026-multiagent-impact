"""Audit thread position inside the 546 exact-author matched pairs.

The addressed edge (`exact_trigger_reply`) counts an inline review comment whose
raw `in_reply_to_id` equals the trigger comment's own identifier. GitHub stores a
reply's target as the *opening* comment of the inline thread, so the outcome can
only ever fire when the trigger comment is itself a thread root, and only when
the trigger arrived through the `inline_review_comment` channel at all.

Figure 3 Panel A contrasts cross-product against matched same-product triggers on
six outcomes, one of which is that exact edge. This script asks whether the
matched population was ever restricted to triggers that *could* produce the
outcome, counts how many triggers on each arm are structurally unable to, and
recomputes the contrast on the restricted population beside the published one.

Inputs (frozen artifacts, not rebuilt here):
  outputs/coordination_topology/exact_author_stratum_matched_pairs.parquet
  outputs/coordination_topology/matched_visibility_contrasts.csv
  AIDev-7.6M pr_review_comments.parquet / pr_reviews.parquet

Outputs: outputs/matched_thread_position/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DATA = ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M"
TOPOLOGY_DIR = ROOT / "outputs" / "coordination_topology"
OUTPUT_DIR = ROOT / "outputs" / "matched_thread_position"

SEED = 20260826
EXPECTED_PAIRS = 546
EXPECTED_REPOSITORIES = 149

METRICS = {
    "any_visible_followup": "any_observable_response",
    "later_pr_comment": "subsequent_pr_comments",
    "new_review_round": "subsequent_reviews",
    "exact_trigger_reply": "direct_inline_replies",
    "visible_force_push": "force_push_events",
    "merge_within_7d": "merged_within_response_window",
}

# Outcome -> does its definition read `in_reply_to_id` / the trigger's own id?
# Verified against build_cross_feedback_response_chains in
# src/multiagent_impact/cross_agent_review.py.
OUTCOME_ANCHOR_DEPENDENCE = {
    "any_visible_followup": "partial",
    "later_pr_comment": "none",
    "new_review_round": "none",
    "exact_trigger_reply": "full",
    "visible_force_push": "none",
    "merge_within_7d": "none",
}

OUTCOME_DEPENDENCE_NOTE = {
    "any_visible_followup": (
        "OR of the four response counters, one of which is direct_inline_replies; "
        "a mid-thread trigger loses that disjunct, so the OR can only be deflated, "
        "never inflated."
    ),
    "later_pr_comment": "pr_comments rows in the window; no reply anchor is read.",
    "new_review_round": "pr_reviews submissions in the window; no reply anchor is read.",
    "exact_trigger_reply": (
        "requires in_reply_to_id == trigger_event_id; structurally 0 whenever the "
        "trigger is not the opening comment of its own inline thread."
    ),
    "visible_force_push": "pr_timeline head_ref_force_pushed events; no reply anchor is read.",
    "merge_within_7d": "merged_at vs the response window; no reply anchor is read.",
}


def _cluster_bootstrap(
    differences: np.ndarray, clusters: np.ndarray, draws: int = 10_000
) -> tuple[float, float]:
    """Identical to the estimator used in run_coordination_topology_analysis."""
    frame = pd.DataFrame({"difference": differences, "cluster": clusters})
    grouped = frame.groupby("cluster", sort=True)["difference"].agg(["sum", "size"])
    sums = grouped["sum"].to_numpy(dtype=float)
    sizes = grouped["size"].to_numpy(dtype=float)
    rng = np.random.default_rng(SEED)
    sampled = rng.integers(0, len(grouped), size=(draws, len(grouped)))
    estimates = sums[sampled].sum(axis=1) / sizes[sampled].sum(axis=1)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def _pair_bootstrap(differences: np.ndarray, draws: int = 10_000) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    sampled = rng.choice(differences, size=(draws, len(differences)), replace=True).mean(
        axis=1
    )
    low, high = np.quantile(sampled, [0.025, 0.975])
    return float(low), float(high)


def _binary_pair_values(pairs: pd.DataFrame, column: str) -> tuple[pd.Series, pd.Series]:
    cross = pairs[f"{column}_cross"]
    same = pairs[f"{column}_same"]
    if column not in {"any_observable_response", "merged_within_response_window"}:
        cross = cross > 0
        same = same > 0
    return cross.astype(float), same.astype(float)


def load_matched_pairs() -> pd.DataFrame:
    pairs = pd.read_parquet(TOPOLOGY_DIR / "exact_author_stratum_matched_pairs.parquet")
    if len(pairs) != EXPECTED_PAIRS:
        raise AssertionError(
            f"Matched-pair drift: {len(pairs)} != {EXPECTED_PAIRS}. "
            "The audit is pinned to the frozen matched population."
        )
    if pairs["repo_url_cross"].nunique() != EXPECTED_REPOSITORIES:
        raise AssertionError(
            f"Repository drift: {pairs['repo_url_cross'].nunique()} != "
            f"{EXPECTED_REPOSITORIES}"
        )
    if not (pairs["trigger_source_cross"] == pairs["trigger_source_same"]).all():
        raise AssertionError("Trigger channel is assumed to be an exact stratum.")
    return pairs


def load_inline_thread_position() -> pl.DataFrame:
    """event_id -> whether that inline review comment opens its own thread."""
    review_key = (
        pl.scan_parquet(DATA / "pr_reviews.parquet")
        .select("pull_request_review_id", "pr_id")
        .unique("pull_request_review_id")
    )
    return (
        pl.scan_parquet(DATA / "pr_review_comments.parquet")
        .join(review_key, on="pull_request_review_id", how="inner")
        .select(
            pl.col("id").cast(pl.Int64).alias("trigger_event_id"),
            pl.col("in_reply_to_id").cast(pl.Int64, strict=False),
        )
        .unique("trigger_event_id")
        .with_columns(pl.col("in_reply_to_id").is_null().alias("is_thread_root"))
        .collect()
    )


def annotate_thread_position(pairs: pd.DataFrame) -> pd.DataFrame:
    position = load_inline_thread_position().to_pandas().set_index("trigger_event_id")
    root = position["is_thread_root"]
    out = pairs.copy()
    for arm in ("cross", "same"):
        inline = out[f"trigger_source_{arm}"] == "inline_review_comment"
        ids = pd.to_numeric(out[f"trigger_event_id_{arm}"], errors="coerce")
        mapped = ids.map(root)
        out[f"trigger_inline_{arm}"] = inline
        out[f"trigger_found_in_inline_table_{arm}"] = inline & mapped.notna()
        out[f"trigger_is_thread_root_{arm}"] = inline & mapped.fillna(False).astype(bool)
        out[f"trigger_is_mid_thread_{arm}"] = inline & (mapped == False)  # noqa: E712
        out[f"outcome_reachable_{arm}"] = out[f"trigger_is_thread_root_{arm}"]
        out[f"trigger_position_{arm}"] = np.where(
            ~inline,
            "not_inline_channel",
            np.where(
                mapped.isna(),
                "inline_but_unresolved",
                np.where(mapped.fillna(False), "thread_root", "mid_thread"),
            ),
        )
    out["both_reachable"] = out["outcome_reachable_cross"] & out["outcome_reachable_same"]
    out["both_inline"] = out["trigger_inline_cross"] & out["trigger_inline_same"]
    return out


def arm_position_table(pairs: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total = len(pairs)
    inline_totals = {
        arm: int(pairs[f"trigger_inline_{arm}"].sum()) for arm in ("cross", "same")
    }
    for arm in ("cross", "same"):
        counts = pairs[f"trigger_position_{arm}"].value_counts()
        for position in (
            "thread_root",
            "mid_thread",
            "inline_but_unresolved",
            "not_inline_channel",
        ):
            count = int(counts.get(position, 0))
            rows.append(
                {
                    "arm": f"{arm}_product",
                    "trigger_position": position,
                    "can_ever_fire_exact_trigger_reply": position == "thread_root",
                    "pairs": count,
                    "share_of_546_matched_pairs": count / total,
                    "share_of_inline_triggers_on_this_arm": (
                        count / inline_totals[arm]
                        if inline_totals[arm] and position != "not_inline_channel"
                        else float("nan")
                    ),
                    "observed_exact_trigger_reply_positive": int(
                        (
                            (pairs[f"trigger_position_{arm}"] == position)
                            & (pairs[f"direct_inline_replies_{arm}"] > 0)
                        ).sum()
                    ),
                }
            )
    return pd.DataFrame(rows)


def pair_reachability_table(pairs: pd.DataFrame) -> pd.DataFrame:
    grid = (
        pairs.groupby(["trigger_position_cross", "trigger_position_same"])
        .size()
        .reset_index(name="pairs")
        .sort_values("pairs", ascending=False)
    )
    grid["both_can_ever_fire"] = (grid["trigger_position_cross"] == "thread_root") & (
        grid["trigger_position_same"] == "thread_root"
    )
    grid["share_of_546_matched_pairs"] = grid["pairs"] / len(pairs)
    return grid.reset_index(drop=True)


def contrast_rows(
    frame: pd.DataFrame, specification: str, population: str
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, column in METRICS.items():
        cross, same = _binary_pair_values(frame, column)
        differences = (cross - same).to_numpy()
        if not len(differences):
            continue
        pair_low, pair_high = _pair_bootstrap(differences)
        cluster_low, cluster_high = _cluster_bootstrap(
            differences, frame["repo_url_cross"].to_numpy()
        )
        rows.append(
            {
                "specification": specification,
                "population": population,
                "outcome": label,
                "anchor_dependence": OUTCOME_ANCHOR_DEPENDENCE[label],
                "pairs": len(frame),
                "repositories": frame["repo_url_cross"].nunique(),
                "cross_rate": float(cross.mean()),
                "same_rate": float(same.mean()),
                "paired_difference": float(differences.mean()),
                "pair_bootstrap_ci_low": pair_low,
                "pair_bootstrap_ci_high": pair_high,
                "repository_cluster_bootstrap_ci_low": cluster_low,
                "repository_cluster_bootstrap_ci_high": cluster_high,
            }
        )
    return rows


def verify_reproduction(recomputed: pd.DataFrame) -> None:
    published = pd.read_csv(TOPOLOGY_DIR / "matched_visibility_contrasts.csv")
    published = published[published["specification"] == "exact_author_user"]
    mine = recomputed[recomputed["population"] == "all_matched_pairs"]
    merged = published.merge(mine, on="outcome", suffixes=("_pub", "_mine"))
    if len(merged) != len(METRICS):
        raise AssertionError("Could not align every published outcome for replication.")
    for field in (
        "paired_difference",
        "cross_rate",
        "same_rate",
        "repository_cluster_bootstrap_ci_low",
        "repository_cluster_bootstrap_ci_high",
    ):
        delta = np.abs(merged[f"{field}_pub"] - merged[f"{field}_mine"]).max()
        if delta > 1e-9:
            raise AssertionError(
                f"Replication of the published contrast failed on {field} "
                f"(max abs delta {delta})."
            )


def outcome_safety_table(pairs: pd.DataFrame) -> pd.DataFrame:
    """Does removing the anchor-dependent disjunct change each outcome?"""
    rows: list[dict[str, object]] = []
    for label, column in METRICS.items():
        arms: dict[str, int] = {}
        for arm in ("cross", "same"):
            values = pairs[f"{column}_{arm}"]
            positive = values if values.dtype == bool else values > 0
            arms[arm] = int((positive & pairs[f"trigger_is_mid_thread_{arm}"]).sum())
        # For any_visible_followup, isolate rows whose ONLY evidence was the
        # anchored reply; those are the rows a mid-thread trigger could lose.
        only_anchor = {}
        for arm in ("cross", "same"):
            others = (
                (pairs[f"subsequent_pr_comments_{arm}"] > 0)
                | (pairs[f"subsequent_reviews_{arm}"] > 0)
                | (pairs[f"force_push_events_{arm}"] > 0)
            )
            only_anchor[arm] = int(
                ((pairs[f"direct_inline_replies_{arm}"] > 0) & ~others).sum()
            )
        rows.append(
            {
                "outcome": label,
                "anchor_dependence": OUTCOME_ANCHOR_DEPENDENCE[label],
                "definition_note": OUTCOME_DEPENDENCE_NOTE[label],
                "positives_on_mid_thread_cross_triggers": arms["cross"],
                "positives_on_mid_thread_same_triggers": arms["same"],
                "cross_pairs_where_only_evidence_is_the_anchored_reply": (
                    only_anchor["cross"] if label == "any_visible_followup" else None
                ),
                "same_pairs_where_only_evidence_is_the_anchored_reply": (
                    only_anchor["same"] if label == "any_visible_followup" else None
                ),
                "safe_from_thread_position": OUTCOME_ANCHOR_DEPENDENCE[label] == "none",
                "verdict": _verdict(label, only_anchor),
            }
        )
    return pd.DataFrame(rows)


def _verdict(label: str, only_anchor: dict[str, int]) -> str:
    dependence = OUTCOME_ANCHOR_DEPENDENCE[label]
    if dependence == "none":
        return "safe by definition: the outcome never reads a reply anchor"
    if dependence == "full":
        return "broken by definition: structurally zero off thread roots"
    exposed = only_anchor["cross"] + only_anchor["same"]
    if exposed == 0:
        return (
            "safe empirically: the anchored reply is never the sole evidence in any "
            "matched pair, so removing the disjunct changes no row"
        )
    return f"exposed: {exposed} matched rows rest on the anchored reply alone"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pairs = annotate_thread_position(load_matched_pairs())

    positions = arm_position_table(pairs)
    grid = pair_reachability_table(pairs)

    populations = {
        "all_matched_pairs": pairs,
        "both_triggers_inline_channel": pairs[pairs["both_inline"]],
        "both_triggers_open_their_own_thread": pairs[pairs["both_reachable"]],
    }
    rows: list[dict[str, object]] = []
    for population, frame in populations.items():
        rows.extend(contrast_rows(frame, "exact_author_user", population))
    contrasts = pd.DataFrame(rows)
    verify_reproduction(contrasts)

    safety = outcome_safety_table(pairs)

    positions.to_csv(OUTPUT_DIR / "trigger_position_by_arm.csv", index=False)
    grid.to_csv(OUTPUT_DIR / "pair_position_grid.csv", index=False)
    contrasts.to_csv(OUTPUT_DIR / "restricted_visibility_contrasts.csv", index=False)
    safety.to_csv(OUTPUT_DIR / "outcome_anchor_dependence.csv", index=False)
    pairs[
        [
            "pr_id_cross",
            "pr_id_same",
            "repo_url_cross",
            "trigger_source_cross",
            "trigger_position_cross",
            "trigger_position_same",
            "direct_inline_replies_cross",
            "direct_inline_replies_same",
            "both_reachable",
        ]
    ].to_parquet(OUTPUT_DIR / "matched_pair_thread_positions.parquet", index=False)

    def _pick(population: str, outcome: str) -> dict[str, object]:
        row = contrasts[
            (contrasts["population"] == population) & (contrasts["outcome"] == outcome)
        ].iloc[0]
        return {
            "pairs": int(row["pairs"]),
            "repositories": int(row["repositories"]),
            "cross_rate": float(row["cross_rate"]),
            "same_rate": float(row["same_rate"]),
            "paired_difference": float(row["paired_difference"]),
            "repository_cluster_ci": [
                float(row["repository_cluster_bootstrap_ci_low"]),
                float(row["repository_cluster_bootstrap_ci_high"]),
            ],
            "pair_bootstrap_ci": [
                float(row["pair_bootstrap_ci_low"]),
                float(row["pair_bootstrap_ci_high"]),
            ],
        }

    mid_cross = int(pairs["trigger_is_mid_thread_cross"].sum())
    mid_same = int(pairs["trigger_is_mid_thread_same"].sum())
    inline_cross = int(pairs["trigger_inline_cross"].sum())
    inline_same = int(pairs["trigger_inline_same"].sum())

    summary = {
        "matched_pairs": len(pairs),
        "restriction_applied_in_pipeline": False,
        "restriction_note": (
            "build_matched_visibility_contrasts reads "
            "first_agent_feedback_cohort.parquet and applies no filter on trigger "
            "channel or thread position on either arm; direct_inline_replies is "
            "defined by parent_id == trigger_event_id in "
            "build_cross_feedback_response_chains."
        ),
        "inline_channel_triggers": {"cross": inline_cross, "same": inline_same},
        "mid_thread_triggers": {
            "cross": mid_cross,
            "same": mid_same,
            "cross_share_of_all_pairs": mid_cross / len(pairs),
            "same_share_of_all_pairs": mid_same / len(pairs),
            "cross_share_of_inline_triggers": (
                mid_cross / inline_cross if inline_cross else float("nan")
            ),
            "same_share_of_inline_triggers": (
                mid_same / inline_same if inline_same else float("nan")
            ),
        },
        "pairs_where_outcome_is_structurally_impossible": {
            "cross_arm": int((~pairs["outcome_reachable_cross"]).sum()),
            "same_arm": int((~pairs["outcome_reachable_same"]).sum()),
            "either_arm": int((~pairs["both_reachable"]).sum()),
            "asymmetric_only_same_arm_impossible": int(
                (pairs["outcome_reachable_cross"] & ~pairs["outcome_reachable_same"]).sum()
            ),
            "asymmetric_only_cross_arm_impossible": int(
                (~pairs["outcome_reachable_cross"] & pairs["outcome_reachable_same"]).sum()
            ),
        },
        "exact_trigger_reply": {
            population: _pick(population, "exact_trigger_reply")
            for population in populations
        },
        "outcomes_safe_from_thread_position": sorted(
            safety.loc[safety["safe_from_thread_position"], "outcome"]
        ),
        "outcomes_affected_by_thread_position": sorted(
            safety.loc[~safety["safe_from_thread_position"], "outcome"]
        ),
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
