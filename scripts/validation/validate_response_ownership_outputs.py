"""Fail fast when response-ownership artifacts violate the paper's constructs.

This validator checks both relational invariants and the frozen counts for the
AIDev-7.6M revision used by the manuscript.  It deliberately does not validate
semantic labels: those remain a blinded two-coder task.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import polars as pl


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs"
DATA = Path(
    os.environ.get(
        "AIDEV_DATA_DIR",
        ROOT.parent / "Legacy" / "AI_Dev_Dataminning" / "AIDev-7.6M",
    )
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    chain_dir = OUTPUT / "cross_agent_review"
    owner_dir = OUTPUT / "response_ownership"
    topology_dir = OUTPUT / "coordination_topology"
    audit_dir = OUTPUT / "feedback_response_audit"

    chains = pl.read_parquet(chain_dir / "cross_feedback_response_chains.parquet")
    events = pl.read_parquet(chain_dir / "cross_feedback_response_events.parquet")
    first = pl.read_parquet(owner_dir / "first_response_ownership.parquet")
    routes = pl.read_parquet(owner_dir / "ownership_route_48h.parquet")

    require(chains.height == 8_608, "Unexpected seven-day cohort size")
    require(chains["pr_id"].n_unique() == chains.height, "Duplicate PR in chain cohort")
    require(int(chains["any_observable_response"].sum()) == 5_553, "Response count drift")
    require(int(chains["direct_inline_replies"].gt(0).sum()) == 730, "Direct-reply PR count drift")

    outside_window = events.filter(
        (pl.col("response_dt") <= pl.col("trigger_dt"))
        | (pl.col("response_dt") > pl.col("response_end_dt"))
    )
    require(outside_window.is_empty(), "Response event outside its seven-day window")

    direct = events.filter(pl.col("response_source") == "direct_inline_reply")
    require(direct.height == 875, "Exact direct-reply event count drift")
    require(
        direct.filter(pl.col("response_user_type").str.to_lowercase() == "user").height
        == 701,
        "Direct-reply user-event count drift",
    )
    require(
        direct.filter(
            pl.col("response_agent").is_not_null()
            & (pl.col("response_agent") != pl.col("trigger_reviewer_agent"))
        )["pr_id"].n_unique()
        == 74,
        "Strict cross-product dialogue PR count drift",
    )

    raw_reply_links = (
        pl.scan_parquet(DATA / "pr_review_comments.parquet")
        .select(
            pl.col("id").alias("response_event_id"),
            pl.col("in_reply_to_id"),
        )
        .collect()
    )
    direct_check = direct.join(raw_reply_links, on="response_event_id", how="left")
    require(
        direct_check["in_reply_to_id"].null_count() == 0,
        "A direct-reply event is absent from the source table",
    )
    require(
        direct_check.filter(
            pl.col("in_reply_to_id").cast(pl.Int64) != pl.col("trigger_event_id")
        ).is_empty(),
        "A direct reply does not point to the exact trigger parent",
    )
    require(
        direct_check.filter(pl.col("trigger_source") != "inline_review_comment").is_empty(),
        "A direct reply has a non-inline trigger",
    )

    later_reviews = events.filter(pl.col("response_source") == "subsequent_review")
    require(
        later_reviews.filter(
            pl.col("response_review_id") == pl.col("trigger_review_id")
        ).is_empty(),
        "A trigger's enclosing review batch was counted as a later review",
    )

    require(first.height == chains.height, "First-owner table lost or duplicated PRs")
    require(first["pr_id"].n_unique() == first.height, "Duplicate PR in first-owner table")
    known_human = first.filter(pl.col("first_owner").is_in(["author_human", "other_human"]))
    mapped_agent = first.filter(
        pl.col("first_owner").is_in(
            ["author_agent", "triggering_reviewer", "other_agent"]
        )
    )
    require(known_human.height == 2_380, "Known-human first-owner count drift")
    require(mapped_agent.height == 1_304, "Mapped-agent first-owner count drift")

    require(routes.height == 1_733, "Unexpected 48-hour landmark cohort size")
    require(routes["pr_id"].n_unique() == routes.height, "Duplicate PR in route cohort")
    require(
        routes.filter(pl.col("ownership_route_48h") == "no_observed_action").height
        == 659,
        "No-action route count drift",
    )

    model = pl.read_csv(owner_dir / "ownership_route_clustered_model.csv")
    require(model.height == 5, "Unexpected number of ownership-route contrasts")
    numeric = model.select(["estimate", "ci_low", "ci_high", "p_value"]).to_numpy()
    require(bool(np.isfinite(numeric).all()), "Non-finite ownership-model result")
    require(bool((model["ci_low"] <= model["estimate"]).all()), "Estimate below CI")
    require(bool((model["estimate"] <= model["ci_high"]).all()), "Estimate above CI")

    owner_loo = pl.read_csv(owner_dir / "ownership_descriptive_leave_one_out.csv")
    require(owner_loo.height == 1_441, "Unexpected descriptive LOO row count")
    require(
        owner_loo.filter(
            pl.col("known_human_first_share")
            <= pl.col("mapped_agent_first_share")
        ).is_empty(),
        "Mapped-agent ownership overtakes known-human ownership in a LOO case",
    )
    require(
        float(owner_loo["strict_cross_product_dialogue_share"].max()) < 0.013,
        "Strict dialogue is no longer below 1.3% in all LOO cases",
    )
    route_loo_summary = pl.read_csv(
        owner_dir / "ownership_route_leave_one_out_summary.csv"
    )
    common_routes = route_loo_summary.filter(
        pl.col("route").is_in(
            ["automation_no_human", "human_first", "automation_then_human"]
        )
    )
    require(common_routes.height == 6, "Missing common-route LOO summaries")
    require(
        bool(common_routes["all_positive"].all()),
        "A common ownership-route LOO point estimate is not positive",
    )

    funnel = pl.read_csv(topology_dir / "participation_funnel.csv")
    require(
        funnel["prs"].to_list() == [8_608, 5_553, 730, 74],
        "Participation funnel count drift",
    )
    continuity = pl.read_csv(topology_dir / "thread_continuity_summary.csv")
    off_thread = continuity.filter(
        pl.col("visible_followup_location") == "only_elsewhere_in_public_trace"
    )
    require(off_thread.height == 1, "Missing off-thread continuity row")
    require(
        float(off_thread["share_among_responsive_prs"][0]) > 0.86,
        "Off-thread-only follow-up is no longer above 86%",
    )

    visibility = pl.read_csv(topology_dir / "matched_visibility_contrasts.csv")
    primary_visibility = visibility.filter(
        (pl.col("specification") == "exact_author_user")
        & (pl.col("outcome") == "any_visible_followup")
    )
    require(primary_visibility.height == 1, "Missing primary visibility contrast")
    require(int(primary_visibility["pairs"][0]) == 546, "Same-author pair count drift")
    require(
        float(primary_visibility["paired_difference"][0]) < 0,
        "Cross-product visibility gap changed direction",
    )
    require(
        float(primary_visibility["repository_cluster_bootstrap_ci_high"][0]) < 0,
        "Repository-clustered visibility interval now includes zero",
    )
    match_quality = pl.read_csv(topology_dir / "matched_visibility_quality.csv")
    quality = dict(zip(match_quality["check"], match_quality["value"], strict=True))
    for check in [
        "exact_repo_match",
        "exact_author_product_match",
        "exact_trigger_source_match",
        "exact_trigger_month_match",
        "exact_author_user_match",
        "unique_cross_prs",
        "unique_same_prs",
    ]:
        require(str(quality[check]).lower() == "true", f"Failed matching check: {check}")

    direct_contrasts = pl.read_csv(topology_dir / "route_direct_contrasts.csv")
    hybrid = direct_contrasts.filter(
        (pl.col("compared_route") == "automation_then_human")
        & (pl.col("specification") == "pretrigger_adjusted")
    )
    require(hybrid.height == 1, "Missing hybrid-versus-automation contrast")
    require(
        float(hybrid["ci_low"][0]) > 0,
        "Hybrid-versus-automation clustered interval now includes zero",
    )
    direct_loo = pl.read_csv(
        topology_dir / "route_direct_contrasts_leave_one_out.csv"
    )
    require(
        bool((direct_loo["automation_then_user_vs_automation_only"] > 0).all()),
        "Hybrid-versus-automation point contrast reversed in a LOO case",
    )

    coder_a = pl.read_csv(audit_dir / "coder_A_blinded.csv")
    coder_b = pl.read_csv(audit_dir / "coder_B_blinded.csv")
    key = pl.read_csv(audit_dir / "private_record_key.csv")
    require(coder_a.height == coder_b.height == key.height == 600, "Audit packet size drift")
    require(coder_a["record_id"].n_unique() == 600, "Duplicate blinded audit record")
    require(
        coder_a["record_id"].to_list() == coder_b["record_id"].to_list(),
        "Coder packets are not identically ordered",
    )
    require(
        set(coder_a.columns).isdisjoint({"pr_id", "repo_id", "merged", "outcome"}),
        "Blinded packet leaks an identifier or outcome",
    )
    label_columns = [
        "trigger_substance",
        "response_relation",
        "resolution_signal",
        "owner_mapping_valid",
        "confidence",
        "evidence_note",
    ]
    for column in label_columns:
        require(
            coder_a[column].fill_null("").str.strip_chars().eq("").all(),
            f"Coder A label column is not blank: {column}",
        )
        require(
            coder_b[column].fill_null("").str.strip_chars().eq("").all(),
            f"Coder B label column is not blank: {column}",
        )

    summary = json.loads((chain_dir / "summary.json").read_text(encoding="utf-8"))
    require(
        summary["response_chains"]["cross_feedback_prs_with_7d_followup"]
        == chains.height,
        "JSON summary and chain cohort disagree",
    )

    print("Response-ownership validation passed")
    print("cohort_prs=8608 observable_prs=5553 direct_reply_events=875")
    print("known_human_first=2380 mapped_agent_first=1304 landmark_prs=1733")
    print("same_author_visibility_pairs=546 cluster_interval=negative")
    print("hybrid_vs_automation_only=positive cluster_interval=positive")
    print("leave_one_out=pass pair_and_repository_directions_stable")
    print("audit_records=600 labels_status=pending_human_coding")


if __name__ == "__main__":
    main()
