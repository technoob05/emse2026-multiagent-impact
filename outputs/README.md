# outputs/ — analysis results

Each directory is written by one script under `scripts/analysis/` and read by
the appendix table generator, the figure code, or both. These are the numbers
the paper stands on.

This is not the same thing as `build/`, which holds generated deliverables
(PDFs, rendered figures, the submission bundle).

## Current

- `addressed_edge_landmark/`
- `addressed_edge_scope/`
- `addressed_edge_sensitivity/`
- `addressed_edge_specificity/`
- `burst_topology/`
- `cache/`
- `coordination_topology/`
- `cross_agent_review/`
- `deep_coordination/`
- `external_validation/`
- `feedback_response_audit/`
- `feedback_routing/`
- `figures/`
- `human_audit/`
- `human_memory_bridge/`
- `manual_audit/`
- `novelty_collision_extension/`
- `ownership_persistence/`
- `response_ownership/`
- `review_collision/`
- `review_request_context/`
- `rq3_extensions/`
- `tables/`
- `task_label_validation/`

## Superseded

`_superseded/` holds results from the pre-pivot study, including files named
`rq1_*`, `rq2_*` and `rq3_*` that answer **different** research questions from
the paper's RQ1, RQ2 and RQ3. Nothing there feeds the manuscript. See
`_superseded/README.md`.
