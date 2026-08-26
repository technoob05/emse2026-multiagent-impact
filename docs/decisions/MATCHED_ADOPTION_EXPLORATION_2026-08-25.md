# Matched adoption exploration

Date: 2026-08-25

## Question

Does repository activity change after the first observed pull request from a
second coding-agent brand?

## Design

Each treated repository is matched to a repository with the same first agent
brand that has not adopted a second brand by the end of the three-month outcome
window. Matching uses the mean and slope of `log(1 + monthly PRs)` and the
30-day merge rate during months -3 to -1. Repositories that receive a third
brand during the outcome window are excluded. Outcomes are measured relative
to month -1.

This is an observational matched event study. Second-brand entry is endogenous,
and passing a short pre-trend check does not create random assignment.

## Initial three-month-history cohort

- 43 matched repository pairs.
- Covariate standardized differences range from 0.046 to 0.104.
- Neither month -3 nor month -2 has a log-PR interval excluding zero.
- Mean post-entry contrast: +0.375 log-PR.
- Mean count contrasts: +3.38 PRs and +1.93 merged-within-30-day PRs per month.
- The median pair-level log-PR contrast is +0.288; 62.8% of pairs are positive.
- Leave-one-pair-out mean estimates range from +0.312 to +0.423.

Across calipers and replacement rules, the mean post log-PR contrast remains
positive (+0.302 to +0.411). However, two of seven specifications fail the
short pre-trend gate and the sample contains only 26 to 43 pairs.

## Longer-history falsification

Requiring four months of prior repository agent activity leaves 23 pairs. The
mean post-entry contrast becomes -0.053 log-PR and the count contrasts become
-1.39 PRs and -2.17 merged PRs per month. Requiring six months destroys common
support and leaves only one pair.

Therefore the positive result is not robust to repository-history eligibility.
It may describe young repositories whose agent use and workload are still
growing, not an impact of adding another brand.

## Decision

Do not use the matched adoption estimate as a causal or headline paper result.
Keep it as a lifecycle diagnostic and motivation for a better design with:

1. explicit assignment events;
2. longer pre-treatment histories;
3. cohort-specific not-yet-treated estimators;
4. repository-age stratification defined before outcome inspection;
5. contributor and task-demand controls;
6. enough common support for established repositories.

The current evidence supports one narrow statement: **second-brand entry and
activity growth occur together in a selected group of young repositories, but
the relationship does not persist under a longer-history eligibility rule.**
