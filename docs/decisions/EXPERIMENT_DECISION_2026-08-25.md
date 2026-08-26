# Experiment decision: multi-brand task complementarity

Date: 2026-08-25

## Decision

Do not pivot the main manuscript to the claim that a second coding-agent brand
expands a repository's task portfolio. The first exploratory result looked
positive, but it did not survive the strongest validity checks.

## What initially looked promising

- A reproducible title-prefix rule labelled 147,036 of 361,296 rich-layer PRs.
- On its overlap with the supplied task labels, agreement was 99.5%.
- Entrants appeared to work on task categories that were less common in the
  incumbent's pre-entry portfolio.
- A five-class title model reached macro-F1 0.800 on repository-disjoint data
  and 0.770 on a short temporal holdout.

These results justified further testing. They did not justify a paper claim.

## What the audit changed

1. The original PR-level permutation broke agent-role bundles. Repository-level
   bootstrap, Wilcoxon, and whole-contrast sign flips are the valid sensitivity
   tools for this observational design.
2. Raw task breadth was higher after entry partly because there were more PRs.
   After equal-count rarefaction, the classifier-filled 90-day estimate was
   close to zero: +0.048 task types, with a 95% interval from -0.084 to +0.180.
3. In the classifier-filled cohort, the entrant rarity contrast was +0.027,
   with a 95% interval that touched zero. After excluding repositories where a
   third agent entered during the window, it fell to +0.009 with a 95% interval
   from -0.024 to +0.039.
4. Explicit-prefix coverage differs strongly by agent and calendar month. The
   later-period classifier extrapolates beyond the supplied labels and has no
   labelled examples for Google Jules.
5. The integration definition was corrected so an entrant receives credit only
   when an entrant-authored PR in the introduced category merges within 30 days.

## Strong result that remains

The historical task-fit experiment is an adjusted null. The raw merge gap
between historically best-fit and other assignments was 8.2 percentage points,
but it collapsed to +0.12 points after repository fixed effects (95% interval
-1.34 to +1.58). Cross-repository selection explains the attractive raw gap;
the data do not show that routing to the historically best agent improves
integration.

## Novelty boundary from the literature audit

A bounded search current to 2026-08-25 found no direct study that treats the
first appearance of a second coding-agent brand as a repository-level event and
tests portfolio expansion versus overlap. This is still a real research gap.
However, current AIDev evidence is not yet strong enough to fill it.

Closest work already covers longitudinal task mix, agent-by-task comparisons,
PR lifecycle roles, adoption, and cross-agent concurrency/conflict. A future
paper must therefore center the entry event and entrant/incumbent decomposition.

## Next evidence gate

The specialization paper can resume only after:

1. a later-period human task-label audit stratified by agent, month, and title
   prefix status, including Google Jules;
2. a rolling-origin or cross-fitted classifier with selective accuracy by
   confidence band;
3. a clean second-agent cohort that censors at third-agent entry;
4. rarefied richness, entrant-versus-incumbent gap filling, and repository-level
   uncertainty;
5. contributor-aware strata that distinguish a tool change from a new person;
6. a pseudo-entry or not-yet-treated comparison before any causal wording.

Until those gates pass, the safe terms are **observed multi-brand adoption** and
**task allocation patterns**. Do not use coordination, handoff, causal
expansion, intrinsic specialization, or optimal routing.
