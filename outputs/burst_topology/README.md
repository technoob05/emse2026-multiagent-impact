# Burst-collapsed response topology

This analysis asks how the first observable post-feedback state changes when
events in a rapid trigger-adjacent burst are collapsed with the trigger. It is
a sensitivity analysis of public traces, not an estimate of a treatment effect,
semantic resolution, or verified manual work.

## Main result

At zero minutes, a mapped product is the first state on
1,305/8,608 PRs
(15.16%). After collapsing the first five
minutes, that count is 924
(10.73%; repository-cluster bootstrap
95% interval 9.08% to
12.42%). The user-account state is then
2,526 PRs (29.34%)
and 52.94% of PRs with any
post-burst action. The largest state is no later visible action:
3,837 PRs
(44.57%).

Within the 1,305
PRs initially classified as mapped-product-first,
547
(41.92%)
are assigned a different first state after the five-minute collapse. The mapped
state retention estimate is
58.08%
(repository-cluster bootstrap 95% interval
52.56% to
63.97%).

At 30 minutes, mapped-product first state falls to
653 PRs
(7.59%). The result supports a narrow
measurement claim: part of apparent multi-product continuation is concentrated
inside a rapid fan-out window, while later visible ownership is more often a
user-account event or no visible action. Account type does not prove who wrote
the content, and later activity does not prove that it addressed the trigger.

## State rule

For each threshold (0, 1, 5, 10, and 30 minutes), all events at or before the
threshold are collapsed into the trigger burst. At the first later timestamp,
the mutually exclusive priority is user account, mapped product, other bot,
then branch movement/untyped. Mixed simultaneous states are counted in
`tie_diagnostics.csv`; the priority prevents arbitrary input-row ordering.

## Files

- `burst_collapsed_first_state.parquet`: one row per PR and threshold.
- `burst_topology_summary.csv`: counts, shares, medians, and repository-cluster
  bootstrap intervals.
- `burst_collapse_profile.csv` and `tie_diagnostics.csv`: burst and tie checks.
- `state_transition_from_zero.csv`, `threshold_change_from_zero.csv`, and
  `mapped_product_retention.csv`: paired state sensitivity and clustered
  uncertainty.
- `leave_one_product_pair_out.csv`, `leave_one_repository_out.csv`, and
  `leave_one_out_ranges.csv`: sensitivity to concentrated groups.
- `ordering_robustness.csv`: whether the headline ordering survives each
  deletion.
- `data_quality_checks.csv`: grain, time, join, de-batching, and duplicate
  invariants.
- `summary.json`: compact machine-readable headline results.

## Data-quality note

The input event ledger contains 9
surplus exact duplicate rows, all from force-push traces and limited to
2 PRs. The analysis uses an
exact-deduplicated view. No PR-threshold first-state assignment changes when the
raw rows are retained.
