# Paper-safe memo: burst-collapsed topology

## Result that survives the checks

The complete cohort contains 8,608 cross-product trigger PRs from 1,416
repositories and 25 author-product/reviewer-product pairs. With no burst
collapse, the first observable state is a mapped product on 1,305 PRs (15.16%)
and a user account on 2,381 PRs (27.66%). Mapped-product events are much closer
to the trigger: their median is 4.47 minutes, compared with 26.83 minutes for a
user-account event.

After collapsing every event in the first five minutes with the trigger, the
mapped-product-first state falls to 924 PRs (10.73%; repository-cluster
bootstrap 95% interval 9.08%--12.42%). This is a paired change of -4.43
percentage points (repository-cluster interval -6.03 to -2.99). The
user-account state is 2,526 PRs (29.34%; 25.35%--33.82%) and accounts for 52.94%
of PRs that have any later action. No visible post-burst action is the largest
state: 3,837 PRs (44.57%; 40.07%--49.10%).

Of the 1,305 PRs initially classified as mapped-product-first, only 758 retain
that state after the five-minute collapse. The other 547 (41.92%) move to a
different first-state category. Mapped-state retention is 58.08%
(repository-cluster interval 52.56%--63.97%). At 30 minutes, mapped-product
first state is 653 PRs (7.59%) and no later visible action is 4,930 PRs (57.27%).

The five-minute ordering is not driven by one group. User-account share exceeds
mapped-product share after every leave-one-product-pair deletion (minimum gap
16.55 points) and every leave-one-repository deletion (minimum gap 16.87
points). No-action remains the largest state in all 25 pair deletions and all
1,416 repository deletions.

## Suggested wording

> Product presence is not the same as sequential ownership. When we collapsed
> the first five minutes of activity with the trigger, mapped-product first
> states fell from 15.2% to 10.7%, while 44.6% of PRs had no later visible
> action. Among PRs with a post-burst action, a user account was the first state
> in 52.9%. This pattern survived every leave-one-product-pair and
> leave-one-repository check. We interpret it as evidence that rapid public
> fan-out can inflate apparent product-to-product continuation, not as evidence
> about semantic resolution or manual work.

## Limits that must travel with the result

- Five minutes is a sensitivity threshold, not a known orchestration boundary;
  the analysis therefore reports 0, 1, 5, 10, and 30 minutes.
- `user_account` is an API account-type observation, not proof that a person
  authored the content.
- A later event is temporally ordered but is not yet validated as semantically
  related to the trigger.
- Public GitHub traces omit private coordination and tool-internal state.
- These are observed transition shares. They do not estimate an intervention
  effect and do not establish repair, resolution, or successful collaboration.

## Validation status

All 8,608 PRs receive exactly one state at each of five thresholds (43,040
unique PR-threshold rows). All timestamps are strictly after the trigger and
inside the seven-day window; review batches are unique by PR-review ID; event
metadata match the chain parent; and threshold zero reconciles to 5,553 PRs
with a visible response. The source event ledger contains nine surplus exact
duplicate force-push rows across two PRs. The analysis removes these duplicates,
and no first-state assignment changes when the raw rows are retained. There are
no failed invariants and one documented low-severity warning.

Recommendation: this result is strong enough for a main-text measurement
finding if framed as **concurrency is not necessarily sequential coordination**.
Keep the full threshold sweep, transition matrix, and concentration checks in
the appendix.
