# Skeptical EMSE and causal-design review

Date: 2026-08-26  
Role: hostile-but-constructive reviewer; read-only audit of the current manuscript and generated cohorts

## Verdict

The exact-edge and product-aware ownership work is useful, but the paper should
not promote the current cross-versus-same result as a shift from conversation to
successful artifact work. That attractive result fails two basic reviewer tests:
repository-level dependence and contributor continuity.

The defensible result is narrower:

> Cross-product triggers receive less visible conversational follow-up than
> matched same-product triggers. The data do not show that the missing
> conversation is replaced by more effective code movement or integration.

The strongest feasible next insight is not another merge model. It is to
separate **rapid automation fan-out** from **sequential coordination**, and then
test whether multiple reviewer products expand, duplicate, or conflict at the
same code location. This can be impactful without causal overclaim.

Overall assessment: **needs revision before the matched outcome contrast becomes
a headline; promising as a measurement/topology paper.**

## 1. Audit of the current causal story

### 1.1 The 668-pair uncertainty is too optimistic

The current bootstrap resamples 668 pairs as though they were independent.
They are not: the pairs come from only 165 repositories, one repository supplies
114 pairs and the next supplies 66. A repository-cluster bootstrap gives:

| Outcome, cross minus same product | Estimate | Repository-cluster 95% interval | Repository-level sign-flip p |
|---|---:|---:|---:|
| Any visible follow-up | -10.18 pp | [-17.47, -1.76] | .029 |
| Later PR comment | -13.02 pp | [-29.69, +1.79] | .224 |
| Force-push | +4.79 pp | [-0.21, +10.33] | .126 |
| Merge within seven days | +6.44 pp | [-1.87, +16.52] | .253 |

Only the lower overall follow-up contrast survives repository dependence. The
force-push and merge intervals cross zero. Exact reply (-1.20 pp) and new review
(-1.65 pp) were already near zero under the original pair bootstrap.

### 1.2 Contributor continuity falsifies the artifact/merge interpretation

Only 519/668 pairs use the same PR-author account. In those 519 pairs:

| Outcome | Cross minus same product | Repository-cluster 95% interval |
|---|---:|---:|
| Any visible follow-up | -12.91 pp | [-20.16, -2.97] |
| Later PR comment | -15.80 pp | [-33.90, +2.92] |
| Force-push | +2.31 pp | [-1.08, +5.28] |
| Merge within seven days | +1.54 pp | [-3.93, +9.07] |

The artifact and merge differences nearly disappear when the contributor is
held fixed. The 149 different-contributor pairs show very large but imprecise
positive differences (+13.4 points for force-push and +23.5 for merge), which is
exactly the pattern expected from contributor/workflow selection.

### 1.3 Calipers and coarsened matching do not rescue the claim

The median calendar match gap is 52.4 hours; its 75th percentile is 145.6
hours. There are 227 pairs within one day, 391 within three days, and 515 within
seven days. Repository-cluster intervals by calendar caliper are unstable:

| Caliper | Pairs / repos | Any follow-up | Force-push | Merge in 7d |
|---|---:|---:|---:|---:|
| 1 day | 227 / 80 | -9.25 pp [-22.47,+1.66] | +5.29 [-6.29,+15.72] | +12.33 [+0.54,+23.31] |
| 3 days | 391 / 114 | -11.51 [-20.46,-1.86] | +5.12 [-2.04,+14.08] | +9.72 [-1.10,+22.68] |
| 7 days | 515 / 133 | -12.04 [-20.00,-1.96] | +4.85 [-1.52,+11.58] | +8.35 [-1.72,+20.92] |
| 30 days | 668 / 165 | -10.18 [-17.53,-1.71] | +4.79 [-0.23,+10.36] | +6.44 [-1.80,+16.78] |

The isolated one-day merge interval is not stable across reasonable calipers
and should not be selected after looking at the outcomes.

A second profile matched on information available at the trigger. The original
pairs have material imbalance in trigger text length (SMD +0.914), suggestion
syntax (SMD +0.482), and prior user activity (SMD -0.130). Coarsened exact
matching on trigger age and pre-trigger activity gives 494 pairs: -11.54 points
for any follow-up, +6.68 for force-push, and +5.87 for merge. Once author account
is also exact-matched, 397 pairs remain: -15.62 for any follow-up, +2.52 for
force-push, and **-0.50 for merge**. Clustered intervals still need to be
calculated for this re-matched cohort, so these point estimates are a
falsification screen, not final inference.

### 1.4 The ownership-to-merge model is selected, not causal

Ownership route is post-trigger behavior, not an assigned intervention. The
routes already differ before the trigger. In the 48-hour cohort, a prior
user-account event is visible on 45.8% of later `human_first` PRs, 30.2% of
`automation_then_human`, 28.1% of silent PRs, and only 17.2% of
`automation_no_human`. Median trigger age also differs (0.365 hours for
`human_first`, 0.080 for `automation_no_human`). These are direct signatures of
maintainer attention and PR maturity.

At minimum, any adjusted route model needs log trigger age, de-batched
pre-trigger user/bot/review activity, contributor identity or history, and a
repository effect. Even then, the estimand remains associational because task
difficulty, installation policy, private orchestration, and maintainer intent
are unobserved.

### Paper-safe wording for the current RQ2 contrast

Use:

> Within repository-, author-product-, channel-, and month-matched PRs,
> cross-product triggers were followed by less visible activity than
> same-product triggers. This quieter pattern remained when we required the
> same contributor and balanced trigger age and prior activity. Differences in
> exact replies and new review rounds were small. Apparent force-push and merge
> differences attenuated under contributor-continuity checks and did not survive
> repository-clustered uncertainty. We therefore interpret the result as
> reduced public conversational follow-up, not as evidence of more effective
> artifact coordination.

Do not use `more action-oriented`, `cross-product feedback improves merge`,
`artifact substitution`, `interoperability effect`, or causal verbs.

## 2. Strongest next designs

### Design A -- Concurrency is not collaboration (highest immediate priority)

**Question.** How much apparent multi-agent response remains after collapsing
the rapid automation burst surrounding the trigger?

**Why this is promising.** The first cross-product trigger arrives a median of
5.9 minutes after PR opening; 60.3% arrive within ten minutes and 75.3% within
one hour. Among 1,305 PRs whose naively selected first later actor is a mapped
product, 52.1% of those actions arrive within five minutes. In a preliminary
delay sensitivity, removing the first five minutes reduces mapped-agent first
ownership from 15.2% to 10.7%, while user-account ownership is 29.3%. This
screen must be reimplemented with the paper's tie-aware owner rule, but it is a
large enough shift to test properly.

**Estimands.** For burst threshold delta in {0, 1, 5, 10, 30} minutes:

1. the cumulative incidence by time t of first post-burst user-account event,
   mapped-product event, other-bot event, branch movement, merge, or
   closed-unmerged;
2. the share of PRs whose raw `multi-agent` topology becomes parallel fan-out,
   sequential mapped-agent continuation, user bridge, or silence after burst
   collapse; and
3. median time from burst end to the first accountable owner.

These are observed transition probabilities, not treatment effects.

**Analysis.** De-batch by review ID; collapse tied timestamps; treat merge,
closed-unmerged, and censoring as competing outcomes; estimate Aalen--Johansen
cumulative incidence; cluster/bootstrap whole repositories. Report all delta
values rather than choosing the best-looking threshold.

**Assumptions.** Event timestamps are comparable; a short burst is a useful
sensitivity proxy for one automation run; table capture does not differ by
route in an unmeasured way. The burst assumption is explicitly varied, not
asserted as fact.

**Falsifiers.** The story fails if mapped-agent ownership remains dominant after
30 minutes, if human/mapped ordering reverses under leave-one-pair/repository,
or if the same pattern is fully explained by pre-trigger event intensity.

**Minimum support.** At least 100 PRs in every displayed state and at least 30
repositories per interval. The 8,608-PR cohort is sufficient for the main
states; sparse direct-dialogue states should remain counts only.

**Story change.** `Several products are present` becomes `most public
multi-agent traces are rapid fan-out; accountable coordination begins only
after the burst`. This is more useful to system builders because it says where
an explicit owner/acknowledgement protocol is missing.

### Design B -- Review collision versus complementary coverage (highest “wow” potential)

**Question.** When two mapped reviewer products examine the same PR, does the
second product expand review coverage, repeat the same concern, add a different
concern at the same locus, or contradict the first product?

**Feasibility screen.** After removing inline replies and retaining top-level
comments, 886 PRs contain comments from at least two mapped reviewer products
(6,212 comments). There are 214 cross-product top-level comment pairs on the
same path and line across 197 PRs; 167 collision loci on 159 PRs also share the
same `original_commit_id`. About 70% of same-locus pairs occur within five
minutes. This is a bounded population that can be completely dual-coded rather
than sampled weakly.

**Estimands.** Among same-snapshot/same-locus pairs, estimate the prevalence of
semantic redundancy/agreement, complementary concerns, contradiction, and
unclear relation. At PR level, estimate the second product's incremental file
and locus coverage conditional on both products' comment counts. Secondary
estimands are exact user reply and acknowledged/fixed-claim rates by semantic
relation.

**Analysis.** Require top-level comments, identical original commit, path, and
position. Dual-code all feasible collision pairs, blinded to product and PR
outcome; Cohen kappa >= .70. Compare with a matched same-file/different-locus
sample. For file coverage, compare observed overlap with a within-PR
volume-conditioned random baseline and bootstrap repositories. Do not infer
semantic duplication from token similarity or location alone.

**Assumptions.** `original_commit_id + path + original_position` identifies the
same reviewed code state/locus; exact identity mapping is valid; coders can
distinguish agreement, complementarity, and contradiction from visible text.

**Falsifiers.** Stop if fewer than 100 valid pairs survive trace audit, kappa is
below .70, more than 30% are boilerplate/unclear, the result disappears when
requiring the same original commit, or one repository/product pair supplies
more than half of valid cases.

**Minimum support.** At least 100 adjudicated same-snapshot pairs for prevalence;
at least 30 cases per semantic category for a category contrast. The current
159-PR screen is adequate for the main prevalence question but not a product
league table.

**Story change.** The paper asks whether agent diversity produces extra review
coverage or a coordination collision. This is a direct, actionable multi-agent
question that the current ownership percentages cannot answer.

### Design C -- Dynamic escalation after repeated automation

**Question.** After a cross-product trigger, when does another automated event
remain useful continuation and when does it become an escalation signal for a
user-account handoff?

**Feasibility screen.** In the seven-day ledger, 1,496 PRs have one mapped/other
bot event before the first user event or censoring, 574 have two, 304 have
three, and 452 have four or more. Raw latency among PRs eventually reaching a
user event rises from 0.79 hours after one prior automation event to 3.91 hours
after four or more. That raw pattern is partly mechanical and must not be
reported as a dose effect.

**Estimands.** At each automation state k in {1, 2, 3, 4+}, estimate the
probability that the next observed transition is a user-account event, another
automation event, branch movement, merge, closed-unmerged, or censoring. A
secondary estimand is the cause-specific hazard of user-account takeover as a
function of k, explicitly associational.

**Analysis.** Construct a PWP/multi-state risk set at each event; do not define
groups using the eventual number of events. Collapse five-minute bursts first.
Use repository-clustered intervals and product-pair strata. Include trigger age
and de-batched pre-trigger activity.

**Assumptions.** Events are ordered correctly; review batches are distinct;
visible user accounts are an account-type signal, not verified manual work;
unobserved events remain a coverage limitation.

**Falsifiers.** No monotonic or threshold pattern after burst collapse;
pre-trigger bot density predicts the same transition pattern; estimates change
sign after leaving out the largest repository or pair; semantic audit shows
later automation is usually unrelated to the trigger.

**Minimum support.** At least 200 at-risk PRs at k=3 and 100 at k=4+; current
screen appears sufficient. Collapse higher k rather than fitting a long dose
curve.

**Story change.** This yields an operational escalation policy: after a
measured number of public automation rounds, the system should request an
owner/acknowledgement instead of silently adding another reviewer run. It does
not claim that requesting a user would cause merge.

### Design D -- Versioned re-review cycle (conditional, not yet headline-safe)

**Question.** Does a later review inspect a genuinely newer code state after
cross-product feedback, and who performs that re-review?

**Feasibility screen.** Among 4,824 inline-trigger PRs, 1,608 have a later
top-level inline comment in a distinct review batch. On 941 PRs, a later comment
references a different `commit_id`. The first such re-review is by the
triggering reviewer product on 421 PRs, author product on 148, another mapped
product on 43, a user account on 151, and another bot on 178.

**Critical construct risk.** A different comment `commit_id` is a different
reviewed snapshot, but the local tables do not prove that this commit was
created after the trigger. Reviewers can comment on an older snapshot, and
`pr_commits` has no documented chronological order.

**Required validation and estimand.** Validate commit ancestry/order through a
documented GitHub source or repository history. Then estimate the share of
triggers followed by a descendant head snapshot and re-review, plus the actor
who performs it. Report time to verified descendant snapshot/re-review with
merge/close as competing states.

**Falsifiers.** Later SHA is not a descendant in more than 10% of audited
chains; fewer than 300 chains can be validated; GitHub data availability is
selective by outcome; same-path semantic audit shows the re-review is unrelated.

**Minimum support.** At least 300 ancestry-validated chains overall and 80 per
headline actor route. Until then use `different reviewed snapshot`, never
`revision caused by feedback` or `repair`.

**Story change.** If validated, this supplies the missing artifact state change
between review rounds and is stronger than force-push alone. If it fails, it
becomes evidence that public repository traces cannot establish closed-loop
repair.

## 3. Natural experiments considered and rejected

No credible causal assignment is currently visible in AIDev.

- **Weekend/time-of-day as an instrument:** invalid exclusion restriction;
  maintainer availability directly affects comment, push, and merge timing.
- **A 48-hour regression discontinuity:** 48 hours is an analyst-chosen
  landmark, not a treatment threshold.
- **First second-brand adoption DiD:** the earlier matched-adoption screen has
  only 43 pairs and reverses from +0.375 log monthly PRs to -0.053 when four
  months of prehistory are required (23 pairs). Parallel trends/common support
  are inadequate.
- **Within-PR cross-versus-same case crossover:** 2,927 PRs contain both
  relations, but cross-product feedback occurs first on only 19.7%; the median
  cross event follows the same-product event by 7.35 minutes. Carryover and
  workflow-order confounding make a causal interpretation implausible. Use this
  only as a self-controlled falsification.

The right methodological move is a strong descriptive estimand with competing
risks, negative controls, semantic validation, and cluster-aware uncertainty,
not a causal label attached to an endogenous route.

## 4. Recommended compact three-RQ story

1. **RQ1 -- Participation or coordination?** How much cross-product activity
   remains sequential after review-batch and rapid-burst collapse?
2. **RQ2 -- Coverage or collision?** When products inspect the same code state,
   does the second reviewer add coverage, repeat a concern, or disagree?
3. **RQ3 -- Closure or escalation?** Which validated topologies reach an
   addressed feedback edge, a versioned re-review, a user-account handoff, or
   an unresolved terminal state?

This story is more novel than a merge association, stays genuinely
multi-agent, and gives builders a concrete protocol requirement: distinguish
parallel outputs from a handoff, expose one accountable owner, and record
semantic acknowledgement/state change.

## 5. Required gates before changing the manuscript headline

1. Complete the existing two-coder 600-case audit; do not treat later activity
   as response until the channel-specific relatedness gate passes.
2. Replace pair-level bootstrap with repository-cluster bootstrap or
   repository-level randomization inference everywhere.
3. Remove the `quieter but more action-oriented` sentence now; it is falsified
   by contributor continuity and cluster-aware uncertainty.
4. Add burst-threshold topology sensitivity and pre-trigger activity negative
   controls.
5. If pursuing collision/complementarity, freeze a new label schema before
   reading product/outcome labels and dual-code the complete same-snapshot
   collision population.
6. Keep `user-account event`, `mapped-product event`, `different reviewed
   snapshot`, and `later integration` as the evidence-level terms. Reserve
   `human work`, `repair`, `resolution`, `coordination`, and `causal effect` for
   validated evidence.

