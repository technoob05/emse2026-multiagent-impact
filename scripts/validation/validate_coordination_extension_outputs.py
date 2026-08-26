from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_burst() -> list[str]:
    directory = OUTPUTS / "burst_topology"
    summary = pd.read_csv(directory / "burst_topology_summary.csv")
    quality = pd.read_csv(directory / "data_quality_checks.csv")
    profile = pd.read_csv(directory / "burst_collapse_profile.csv")
    payload = json.loads((directory / "summary.json").read_text(encoding="utf-8"))

    expected_thresholds = {0, 1, 5, 10, 30}
    expected_states = {
        "user_account",
        "mapped_product",
        "other_bot",
        "branch_movement_untyped",
        "no_action_within_7d",
    }
    require(set(summary["burst_threshold_minutes"]) == expected_thresholds,
            "Burst thresholds changed or are incomplete")
    require(set(summary["first_post_burst_state"]) == expected_states,
            "Burst states changed or are incomplete")
    totals = summary.groupby("burst_threshold_minutes")["prs"].sum()
    require((totals == 8_608).all(), "Every burst threshold must retain 8,608 PRs")
    shares = summary.groupby("burst_threshold_minutes")["share_all_prs"].sum()
    require(np.allclose(shares, 1.0), "All-PR burst shares must sum to one")
    action = summary[summary["first_post_burst_state"] != "no_action_within_7d"]
    conditional = action.groupby("burst_threshold_minutes")["share_post_burst_actions"].sum()
    require(np.allclose(conditional, 1.0), "Conditional burst shares must sum to one")
    require(not (quality["status"] == "FAIL").any(), "Burst data quality has a failed check")
    require((profile.sort_values("burst_threshold_minutes")["no_post_burst_action_prs"].diff().dropna() >= 0).all(),
            "No-action count must be monotone as the threshold grows")

    change = payload["five_minute_mapped_product_change_from_zero"]
    require(change["relative_change"] < 0, "Five-minute mapped-product change must be negative")
    require(change["paired_repository_cluster_ci_percentage_points"][1] < 0,
            "Five-minute mapped-product interval must remain below zero")
    for row in payload["five_minute_ordering_robustness"]:
        require(row["user_exceeds_mapped_in_every_exclusion"],
                "User/mapped ordering failed a leave-one-out check")

    return [
        "burst: 8,608 PRs at every threshold",
        "burst: no failed data-quality checks",
        "burst: mapped-product five-minute change and leave-one-out ordering validated",
    ]


def validate_memory() -> list[str]:
    directory = OUTPUTS / "human_memory_bridge"
    validation = json.loads((directory / "validation.json").read_text(encoding="utf-8"))
    roles = pd.read_csv(directory / "first_mediator_role_summary.csv").set_index("account_role")
    decisive = pd.read_csv(directory / "first_decisive_reviewer_role_summary.csv").set_index("account_role")
    concentration = pd.read_csv(directory / "repo_concentration.csv").iloc[0]
    loo = pd.read_csv(directory / "leave_one_repo_out_summary.csv").iloc[0]

    require(validation["no_same_pr_history_in_valid_matches"], "Same-PR history leakage detected")
    require(validation["no_future_or_equal_history_in_valid_matches"], "Future history leakage detected")
    require(validation["single_account_first_human_mediator_prs"] == 3_603,
            "First user-account mediator cohort changed")
    require(int(roles.loc["author_account", "prs"] + roles.loc["other_user", "prs"]) == 3_603,
            "Mediator role counts do not reconcile")
    require(0 < roles.loc["all_first_mediators", "prior_reviewer_share"] < 1,
            "Mediator history share is invalid")
    require(int(decisive.loc["all_first_decisive_reviewers", "prs"]) == 2_020,
            "First decisive user-reviewer cohort changed")
    require(concentration["largest_repo_share"] < 0.10,
            "Repository concentration is too high for the memory headline")
    require(loo["leave_one_repo_min"] <= loo["full_share"] <= loo["leave_one_repo_max"],
            "Full memory share falls outside leave-one-repository range")

    return [
        "memory: strict different-PR, pre-trigger history has no temporal leakage",
        "memory: 3,603 first user-account mediators reconcile across roles",
        "memory: repository concentration and leave-one-out range validated",
    ]


def validate_collision_packet() -> list[str]:
    directory = OUTPUTS / "review_collision"
    payload = json.loads(
        (directory / "quality_and_sampling_summary.json").read_text(encoding="utf-8")
    )
    support = payload["support"]
    gates = payload["falsification_gates"]
    population = int(support["canonical_collision_loci"])
    coder_a = pd.read_csv(directory / "audit_packets" / "coder_A_blinded.csv")
    coder_b = pd.read_csv(directory / "audit_packets" / "coder_B_blinded.csv")
    label_columns = [
        "comment_A_substance",
        "comment_B_substance",
        "pair_relation",
        "confidence",
        "evidence_note",
    ]

    require(population >= 100, "Collision population is below the frozen support gate")
    require(len(coder_a) == population and len(coder_b) == population,
            "Collision coder packets do not cover the full population")
    require(set(coder_a["record_id"]) == set(coder_b["record_id"]),
            "Collision coder packets contain different records")
    require(coder_a[label_columns].isna().all().all() and coder_b[label_columns].isna().all().all(),
            "Collision packet contains labels before independent coding")
    require(not payload["semantic_labels_assigned"],
            "Collision summary must remain unlabeled before dual coding")
    require(gates["largest_product_pair_supplies_at_most_half"]["status"] == "fail",
            "Expected product-pair concentration warning is missing")
    require(gates["cohen_kappa_at_least_0_70"]["status"] == "pending_dual_coding",
            "Collision reliability gate must remain pending")

    return [
        f"collision: full blinded population packet validated ({population} loci)",
        "collision: dominant-pair warning and semantic-coding gates remain explicit",
    ]


def main() -> None:
    checks = validate_burst() + validate_memory() + validate_collision_packet()
    print("Coordination extension validation passed")
    for check in checks:
        print(f"- {check}")


if __name__ == "__main__":
    main()
