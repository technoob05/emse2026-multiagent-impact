# Deep coordination: persistence and escalation falsification

## Question 1 -- Does mapped-product ownership persist or relay?

The index population is the 924 PRs whose first
observable state after the initial five-minute trigger burst is a mapped
product. We then require an additional five-minute washout after that anchor and
classify the next observable state. The design is temporal and descriptive; it
does not use merge or any later success outcome.

The next state is the same mapped product on
284 PRs
(30.74%), a different mapped product
on only 43
(4.65%), and a user account on
217
(23.48%). Another
305 PRs
(33.01%) have no later visible state.

Among PRs with a later mapped-product event, the observed next product is the
same product 84.44% of the time. However,
a within-PR random-order benchmark that preserves the complete later product
mix expects 83.58%; the observed-minus-null
difference is +0.87 points
(repository-cluster 95% interval
-1.08 to
+3.15). Product persistence is
therefore high, but the ordering test does not show extra temporal persistence
beyond which products dominate each PR's event pool.

**Disposition:** the rare different-product next state is useful as a compact
main-text or appendix topology result. Keep the random-order check beside it.
Do not claim a special persistence mechanism.

## Question 2 -- Does repeated automation naturally escalate?

Post-burst events are sessionized into public episodes; the primary rule starts
a new episode after more than five minutes. Before the first user-account
episode, each PR enters automation state k when it reaches its k-th mapped-
product/other-bot episode. The outcome is the immediate next episode, so k is
not defined from the eventual number of events.

Observed user-account-next share falls from
25.77% at k=1 to
9.76% at k=4, while another-automation-next rises
from 35.88% to
62.93%. This tempting dose story fails the
order placebo: randomly permuting episode order within each PR, while preserving
its state composition, reproduces the pattern. At k=4 the permuted mean
user-account-next share is 10.17%
(6.42%--
14.00%).

**Disposition:** reject a natural-escalation or automation-suppression headline.
The result is valuable as an appendix falsification: repeated public automation
does not by itself reveal an escalation threshold. An explicit escalation
policy would need an intervention or richer state telemetry to evaluate.

## Design safeguards and limitations

- Inputs are the complete seven-day, de-batched cross-response chains. Nine
  exact duplicate force-push rows are removed; no ordering construct uses them.
- Repository-cluster bootstraps retain whole repositories. Primary results also
  have leave-one-repository and leave-one-product-pair ranges.
- Washouts (0, 5, 30, 60 minutes) and episode gaps (0, 1, 5, 10 minutes) are
  reported rather than selected after seeing one result.
- `user_account` is an API type, not verified manual authorship. Temporal
  succession is not semantic response or resolution.
- The random-order benchmarks use future state composition only as explicit
  falsification nulls. They are not predictive features or causal controls.
- Public traces omit private orchestration and installation policy.

## Artifacts

- `mapped_first_next_owner.parquet` and `mapped_first_next_owner_summary.csv`
- `mapped_product_order_placebo_detail.parquet` and
  `mapped_product_order_placebo_summary.csv`
- `automation_episode_transitions.parquet` and
  `automation_episode_transition_summary.csv`
- `automation_order_permutation_placebo.csv`
- `next_owner_leave_one_out_ranges.csv` and
  `automation_leave_one_out_ranges.csv`
- `product_placebo_leave_one_out_ranges.csv`,
  `episode_sessionization_summary.csv`, `concentration_summary.csv`,
  `data_quality_checks.csv`, and `summary.json`
