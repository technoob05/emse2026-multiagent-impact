# outputs/ — analysis results

Each directory is written by one script under `scripts/analysis/` and read by
the appendix table generator, the figure code, or both. These are the numbers
the paper stands on.

This is not the same thing as `build/`, which holds generated deliverables
(PDFs, rendered figures, the submission bundle).

## Current

One directory per analysis, written by the script of the matching name under
`scripts/analysis/`. This list is regenerated from the directory itself, so it
cannot drift from what is here.

- `addressed_edge_landmark/`
- `addressed_edge_scope/`
- `addressed_edge_sensitivity/`
- `addressed_edge_specificity/`
- `anchorability_coverage/`
- `burst_threshold_selection/`
- `burst_topology/`
- `cache/`
- `confounder_benchmarks/`
- `coordination_topology/`
- `cross_agent_review/`
- `deep_coordination/`
- `external_validation/`
- `feedback_response_audit/`
- `feedback_routing/`
- `figures/`
- `heterogeneity_audit/`
- `human_audit/`
- `human_memory_bridge/`
- `manual_audit/`
- `merge_curves/`
- `novelty_collision_extension/`
- `ownership_persistence/`
- `pseudo_edge_control/`
- `response_ownership/`
- `review_collision/`
- `review_request_context/`
- `rq3_extensions/`
- `rq3_landmark_selection/`
- `tables/`
- `task_context_interaction/`
- `task_label_validation/`
- `user_account_automation/`
- `worked_example/`

## Superseded

`_superseded/` holds results from the pre-pivot study, including files named
`rq1_*`, `rq2_*` and `rq3_*` that answer **different** research questions from
the paper's RQ1, RQ2 and RQ3. Nothing there feeds the manuscript. See
`_superseded/README.md`.
