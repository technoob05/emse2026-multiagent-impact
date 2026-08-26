# Exploratory findings

**Dataset revision:** `37bbe1533e26cc1e1374917dba1186d1c8a4dc81`  
**Generated from:** `D:\PhD_LetGoo\PhD_Farming\Legacy\AI_Dev_Dataminning\AIDev-7.6M`  
**Status:** exploratory associations; not causal estimates.

## Headline signals

- Data profile: 7,685,281 PRs across 961,168 repositories; 44,822 repositories contain at least two agents.
- Primary ledger: 466,467 post-onset episodes, one current PR per prior outcome, each with 30 days of follow-up.
- Switching follows 31.2% of prior closed-unmerged episodes versus 14.2% of prior merged episodes.
- After a prior closed-unmerged outcome, 30-day merge rates are 58.5% for the same agent (`n=34,198`) and 63.4% after an observed switch (`n=15,535`).
- After a prior merged outcome, 30-day merge rates are 90.2% for the same agent (`n=357,710`) and 76.9% after an observed switch (`n=59,024`).
- Among repositories with at least two stay and two switch episodes after closed-unmerged outcomes, the median within-repository switch-minus-stay difference is 0.00 percentage points.
- In the exploratory repository-demeaned model, switching is associated with 6.48 pp after a prior closed-unmerged outcome (95% CI 5.00 to 7.95) and -4.29 pp after a prior merged outcome (95% CI -4.77 to -3.81).

## Interpretation

The behavioral and outcome crossover supports continued investigation of outcome-conditioned switching rather than a generic claim that switching is beneficial. Repository fixed effects and controls reduce—but do not eliminate—selection concerns. The star-stratified analysis is a boundary-condition check, especially because the association is weak in mature repositories.

## Required caveats

- Agent changes are observed author-label transitions, not verified maintainer procurement decisions.
- Repository activity, task mix, PR complexity, contributor identity, and automation policy can confound both switching and merge outcomes.
- The full corpus does not provide complete change-size and review-depth features; mechanism analyses require AIDev-pop joins.
- Multiple-testing correction and manual episode validation remain pending.

## RQ recommendation

Keep the three-RQ structure. Treat the RQ1 event curve as an endogenous-onset diagnostic, not impact. Promote RQ2–RQ3 only if the signal survives agent-pair, contributor, activity, complexity, and common-support checks.