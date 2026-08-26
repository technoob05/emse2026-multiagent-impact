# Post-burst ownership persistence

Run date: 2026-08-26

## Verdict: APPENDIX

The analysis passes its data and time-order gates and yields a useful supporting result, but it should not be a headline novelty claim. After a five-minute trigger burst, visible work often moves between the user-account and mapped-product layers instead of settling permanently with either one. When another action is observed, the probability of staying in the same layer is almost identical after a user-first and a product-first start.

The exact same mapped product returns more often than the exact same user account. That contrast is descriptive, not a measure of stronger product control: this cohort contains only six mapped product identities but 944 first user-account identities.

## Question and grain

Starting from 8,608 PRs with cross-product feedback and complete seven-day source observation:

1. Collapse every event at or before five minutes after the trigger.
2. De-batch rows sharing the same PR review ID into one logical action.
3. Keep actions strictly after five minutes and at or before the 48-hour landmark.
4. Identify the first post-burst owner and the next distinct action timestamp.
5. Compare PRs starting with one exact user account against PRs starting with one mapped product.

The full output has one row per PR. The primary denominator has 3,237 PRs: 2,334 user-account-first PRs from 673 repositories and 903 mapped-product-first PRs from 323 repositories.

## Main result

Across all anchors, including those with no next visible action:

| First owner | Same exact owner | Same layer, other identity | Cross-layer handoff | Other bot | Movement | No next action |
|---|---:|---:|---:|---:|---:|---:|
| User account (n=2,334) | 19.6% | 14.6% | 20.2% to mapped product | 6.0% | 2.9% | 36.8% |
| Mapped product (n=903) | 31.7% | 6.3% | 23.5% to user account | 6.1% | 3.7% | 28.8% |

The cleaner comparison conditions on a next visible action, because most “no next action” cases end when the PR closes:

| Metric given a visible next action | User-first | Product-first | User minus product, repository-clustered 95% CI |
|---|---:|---:|---:|
| Same exact identity | 31.0% | 44.5% | -13.5 points [-20.4, -6.8] |
| Same ownership layer | 54.1% | 53.3% | +0.7 points [-6.7, +8.3] |
| Cross-layer handoff | 31.9% | 33.0% | -1.1 points [-7.6, +5.7] |

Thus, **layer persistence and cross-layer handoff are symmetric**, within the uncertainty of this dataset. The useful contrast is within-layer identity: user-layer continuation is distributed across accounts, whereas mapped-product continuation usually returns to the same product identity.

The product-pair leave-one-out range supports this reading:

- Exact-identity difference: -17.1 to -10.6 percentage points.
- Same-layer difference: -4.9 to +3.2 points.
- Cross-layer difference: -3.0 to +6.9 points.

## Bounce-back detail

After a user account becomes first post-burst owner, 471 PRs next return to a mapped product:

- 248/471 (52.7%) return to the triggering reviewer product.
- 204/471 (43.3%) return to the authoring product.
- 19/471 (4.0%) go to another mapped product.

This does not support a one-way “human takeover” story. Observable ownership can bounce back to either product involved in the cross-product episode.

The transitions are often fast. Median time from the first post-burst action is 0.75 minutes for the same user account, 2.38 minutes for user-to-product, 12.93 minutes for the same mapped product, and 16.77 minutes for product-to-user. These are public event timings, not task-duration or labor estimates.

## Why “no next action” is not abandonment

For user-first PRs, 858 have no next action by 48 hours. Of these, 719 (83.8%) close before the landmark and 139 remain open. For product-first PRs, 260 have no next action; 181 (69.6%) close and 79 remain open. Therefore, the raw +8.0-point user-first difference in “no next action” mainly reflects a terminal PR state. It must not be described as user disengagement, product failure, or ownership persistence.

## Concentration and uncertainty

- User-first PRs span 673 repositories. The largest repository contributes 7.7% and the top ten 25.9%.
- Product-first PRs span 323 repositories. The largest repository contributes 2.5% and the top ten 21.4%.
- The largest product pair contributes 32.8% of user-first PRs and 16.3% of product-first PRs. Product-pair concentration is material, so all headline contrasts include leave-one-pair-out ranges.
- First user ownership spans 944 exact accounts; the largest supplies 3.4%. Mapped ownership spans six products; the largest supplies 29.8%.
- Confidence intervals resample whole repositories and retain PR weighting. They describe sampling sensitivity, not causal uncertainty.

## Data-quality and leakage gates

All checks pass:

- Nine surplus exact duplicate event rows are removed before sequencing.
- 16,559 review-linked rows are collapsed into 13,879 logical PR-review actions.
- One ambiguous action batch is flagged; it is not a first or next primary owner.
- There are zero ambiguous first-owner and zero ambiguous next-owner ties in the primary cohort.
- Every first action is strictly after five minutes and no later than 48 hours.
- Every next action is strictly later than the first and no later than 48 hours.
- The PR key is unique for all 8,608 sequence rows.
- The de-batched first state has zero disagreements with the existing five-minute burst state at the atomic user/product/bot/movement level.
- Later merge is not analyzed.

## Relation to Zhong et al.

[Zhong et al., “From Human-Centric to Agentic Code Review”](https://arxiv.org/abs/2607.13196) already model timestamp-ordered review-comment sequences by reviewer type, preserve repeated reviewer-type participation, cluster sequences with Markov chains, and associate the resulting patterns with review efficiency and smells. Therefore, a broad claim that this work is the first to study human/agent reviewer sequences is not defensible.

This extension is narrower and operationally different:

- it anchors sequences on an observed cross-product feedback event;
- removes a five-minute trigger-adjacent burst;
- preserves exact account or product identity for the next action;
- includes PR comments, inline replies, submitted reviews, and force-push movement;
- uses a fixed 48-hour window, exact tie checks, repository-cluster bootstrap, and product-pair leave-one-out;
- does not cluster whole review histories or claim review-quality effects.

These differences make it useful as an ownership-mechanism appendix, not a replacement for or duplication of Zhong et al.'s reviewer-type sequence study.

## Paper-safe wording

> After the trigger-adjacent burst, visible ownership did not move in only one direction. Conditional on another action within 48 hours, about one third of sequences crossed between a user account and a mapped product, while just over half stayed in the same ownership layer. Same-layer and cross-layer rates were similar for user-first and product-first sequences. Exact product identities recurred more often than exact user accounts, but the product identity set was much smaller. These patterns describe public GitHub actions and do not identify unaided human work or causal handoffs.

Do not say that agents “hand control to humans,” that user intervention causes closure or merge, or that product persistence is intrinsically stronger than user persistence.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\run_legacy_extension_ownership_persistence.py
```

Main outputs:

- `postburst_ownership_sequences.parquet`: one row for each of 8,608 PRs, including first/next timestamps, exact owner tokens, tie fields, timing, and terminal observation status.
- `primary_ownership_persistence.parquet`: the 3,237 unambiguous user-first or mapped-product-first sequences.
- `transition_summary.csv`: requested next-owner categories, counts, shares, timing, and repository-cluster intervals.
- `conditional_visible_action_metrics.csv`: exact-owner, same-layer, and cross-layer rates among PRs with a next action.
- `conditional_visible_action_contrasts.csv`: user-first minus product-first contrasts with repository-cluster intervals.
- `mapped_product_return_roles.csv`: authoring, triggering-reviewer, and other-product returns.
- `no_next_observation_breakdown.csv`: terminal closure versus open-at-48h no-action cases.
- `conditional_visible_action_leave_one_product_pair_out_summary.csv`: generalization ranges.
- `concentration.csv`: repository, product-pair, and exact-owner concentration.
- `data_quality_checks.csv` and `summary.json`: validation and machine-readable headline results.
