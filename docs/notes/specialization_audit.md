# Audit of specialization, task classifier, and task-fit experiments

Audit date: 2026-08-25  
Code reviewed: `src/multiagent_impact/specialization.py`, `task_classifier.py`, and `task_fit.py`  
Outputs reviewed: `outputs/specialization/`  
Assessment: **Needs revision before citation or manuscript promotion**

This was a read-only code and output audit. No analysis code was edited.

## Executive result

The explicit-prefix study is useful as an exploratory, selected-subpopulation analysis, and the adjusted task-fit result is an informative null. However, the current specialization/gap-filling evidence is not submission-ready. The main blockers are stale and mutually inconsistent outputs, a non-exchangeable PR-level permutation, large agent/time differences in label availability, a volume-confounded breadth metric, and unvalidated classifier extrapolation beyond July 2025.

The current task-fit result should be described as: the raw 8.2-point gap disappears with repository fixed effects (`+0.12 pp`, 95% CI `-1.34` to `+1.58`). It does not support a claim that repositories improve integration by assigning a task to the historically best agent.

## Must-fix findings

### 1. Output provenance is broken and the saved sensitivity result contradicts the baseline

Severity: **Critical**

`specialization.py` was last modified at 15:30, after the saved outputs were produced at 15:15–15:28. Therefore none of the current specialization artifacts can be asserted to come from the code being audited.

More importantly, `sensitivity.json` reports 142 eligible repositories for the 90-day, 5/5/3 specification, while `specialization_summary.json` reports 41 repositories for the same nominal specification. The associated counts also disagree: 4,279/13,543 versus 1,054/2,232 labelled pre/post PRs.

Impact: all reported sensitivity, confidence intervals, and permutation p-values have unknown provenance. The sensitivity table cannot be cited.

Required fix: run from a clean environment after code freeze; delete or archive stale outputs; save code commit/hash, dataset revision, full config, execution time, package lock hash, and input/output row checks. Add a test requiring the baseline row in sensitivity to exactly match the standalone baseline artifact.

### 2. The PR-level permutation is not valid for the claimed role-specialization test

Severity: **High**

In `permutation_test_role_rarity()` (`specialization.py:291-324`), entrant labels are reassigned independently across PR rows within each repository while preserving only the number of entrant rows. This breaks:

- the intact bundle of PRs authored by each agent;
- within-agent/topic dependence and repeated work;
- the temporal design constraint that the onset PR is from the entrant; and
- any burst or lifecycle structure within the post period.

The observed entrant role was not randomly assigned, so row exchangeability is not credible. The resulting null variance can be too small and the p-value too optimistic. This directly invalidates promotion of the permutation result as inferential support for “gap filling.”

Required fix: make the repository the inferential unit. Report the paired repository contrasts with a repository bootstrap and Wilcoxon result. A sign-flip/random-swap test of whole role bundles can be shown as a sensitivity test, with the explicit caveat that entrant/incumbent assignment is observational. Do not shuffle individual PRs across agent roles.

### 3. Task-label selection is strongly related to agent and calendar time

Severity: **High**

The explicit-prefix rule labels 147,036/361,296 PRs (40.7%), but coverage is highly nonuniform:

| Agent | Prefix coverage |
|---|---:|
| Claude Code | 62.6% |
| Devin | 62.4% |
| Cursor | 22.4% |
| OpenAI Codex | 22.1% |
| Google Jules | 19.4% |
| Copilot | 14.8% |

Coverage also changes from 15.6% in May 2025 to 55.4% in March 2026. In the saved 41-repository cohort, 81.2% of incumbent post PRs but 70.8% of entrant post PRs have an explicit prefix.

This is not ordinary missing-at-random sparsity: label availability is itself an agent communication/style behavior. Entrant versus incumbent task distributions can therefore reflect title convention rather than task allocation.

The reported 99.5% agreement does not solve this. It compares explicit prefixes with an automatically supplied label that was also derived from title/commit text, on only 4,457 overlapping rows. It supports prefix precision inside that selected overlap, not recall, representativeness, or independent construct validity.

Required fix: either scope every claim to “explicitly prefixed PR titles,” or add a stratified human validation sample covering agents, months, prefix/non-prefix titles, and task types. Report coverage and results by entrant/incumbent agent pair and month. A model-filled analysis may be sensitivity evidence only after the classifier validation blockers below are resolved.

### 4. Breadth expansion is confounded by the number of observed PRs

Severity: **High**

`post_breadth - pre_breadth` compares equal calendar windows, not equal observation counts. In the saved baseline there are 2,232 labelled post PRs versus 1,054 pre PRs, a 2.12x volume difference. The median repository post/pre count ratio is 1.56. Observing more PRs mechanically raises the chance of seeing an additional category.

Likewise, with `min_pre=5`, a task can appear “new” simply because a rare incumbent task was absent from a small pre sample.

Impact: the positive mean breadth change and share of repositories with a new type cannot be attributed to the second agent or portfolio complementarity.

Required fix: use PR-count rarefaction/equal-count subsampling, coverage-based richness estimators, and an incumbent-only post comparator. Report the expected number of unseen types given pre sample size. Keep duration-window results as descriptive volume-plus-breadth outcomes only.

### 5. “Integrated entrant expansion” can be credited to the wrong role

Severity: **High definition bug; small observed numerical impact in the current 41-repo file**

For each new task type, `specialization.py:224-234` sets `integrated` if **any** incumbent or entrant PR of that task merges within 30 days, then credits the type to whichever role first introduced it. Thus an entrant can receive an integrated-type credit when only the incumbent's later PR merged.

Independent reconstruction found this occurs for 1 of the 34 entrant-introduced types in the saved cohort. The current reported entrant integration count is 24; requiring a merge by the introducing role yields 23. Requiring the actual introducing PR to merge yields 20.

Required fix: save and report three explicit metrics separately: introducing PR integrated; any later PR by introducing role integrated; any role later integrated. Do not call the third “entrant-integrated expansion.”

### 6. Third-agent entry contaminates the two-role post window

Severity: **High for the current small cohort**

The code ignores later agents in task counts but allows them to enter and alter repository work during the post window. In the saved 41-repository baseline, 17 repositories (41.5%) receive a third agent within 90 days.

Required fix: primary sensitivity should censor the post window at third-agent entry or exclude repositories with third-agent entry during the window. A separate portfolio-size analysis can include all roles.

### 7. The classifier does not validate the period or agent population it predicts

Severity: **High if classifier-filled results are used; otherwise a limitation of an unused exploratory artifact**

`pr_task_type.parquet` contains 32,702 labels only through 30 July 2025. Coverage is zero from August 2025 through March 2026 and zero for Google Jules. Training-label coverage also varies sharply: 38.6% for Devin, 34.3% for Codex, 5.0% for Copilot, 0.26% for Claude Code, and 0% for Jules.

The reported “temporal holdout” covers only 15–30 July 2025, not the following eight months to which the model is applied. Its macro-F1 is 0.770 overall; an independent split check found macro-F1 0.967 on explicit-prefix titles but 0.750 on non-prefix titles. The SVC margin is not calibrated, so thresholds 0.5 and 1.0 do not have a demonstrated error rate.

`train_and_predict()` also trains one model on all labelled dates and predicts both earlier and later PRs. For a longitudinal specialization analysis this uses future vocabulary to classify earlier periods and gives in-sample predictions to labelled PRs but out-of-sample predictions to others.

Required fix: obtain a manually labelled out-of-time sample from August 2025–March 2026, stratified by agent and including Jules; report per-agent/class precision, recall, confusion, and selective accuracy versus margin. Use rolling-origin or cross-fitted predictions, and never mix in-sample and out-of-sample predictions in one inferential cohort without a flag/sensitivity analysis.

### 8. Task-fit is predictive persistence, not evidence of optimal assignment

Severity: **High for interpretation; the adjusted null itself is usable after a clean rerun**

The fit score is constructed from an agent-task pair's historical 30-day merge rate and then related to the same outcome in later PRs. Persistence is expected even without repositories deliberately choosing the right agent. “Available agent” means ever previously observed in the repository, even if that agent has not participated recently.

The raw result is 73.9% for best-fit versus 65.8% otherwise. After repository fixed effects it becomes `+0.12 pp` (95% CI `-1.34` to `+1.58`, p=.871); the continuous margin is also null. This is evidence that cross-repository selection explains the raw gap, not evidence that matching improves integration.

The sample is concentrated: the top 1% of its 1,705 repositories contribute 28.5% of 39,442 PRs; Claude Code contributes 70.8% of rows. Repository-clustered SE handles dependence but not influence or generalizability.

Required fix: write the result as a null/boundary finding. If retained, recompute historical scores leaving the current repository out; define candidate availability using a recent 90/180-day window; cap or reweight repository contributions; and run leave-top-repositories-out and leave-one-agent-out checks.

## Censoring and leakage assessment

### Acceptable / correctly handled

- The 30-day outcome is defined using merges between creation and creation plus 30 days.
- The specialization code requires the onset plus post window plus 30 days to fall before the observed creation endpoint. With this dataset, maximum creation is 31 March 2026, close to the official cutoff.
- Task-fit histories use PRs created before `month_start - 30 days`, so their 30-day outcome is observable before the scored month. This is a conservative and broadly time-safe cutoff.
- Task fit also removes current PRs in the last 30 days.
- Repository-disjoint and temporal classifier evaluations are more informative than the random split, although the temporal test period is too short and early.

### Minor code/definition issues

- Observation endpoints should use the pinned official dataset cutoff rather than `max(created_at)`, and the cutoff should be stored in each artifact.
- `seen_agents` is updated row by row. Two eligible task-fit rows occur at timestamps shared by two agent brands, so ID ordering can make a simultaneously arriving agent appear previously available. Update availability after processing timestamp ties or require `first_seen < current_created_at`.
- Third-agent and agent-inactivity rules must be explicit in the estimand.
- The temporal split uses sorted index labels as `iloc` positions. It works because the current merged frame has a clean RangeIndex, but resetting the index explicitly would make it safe.

## Permutation and uncertainty recommendation

For the role-rarity contrast, use:

1. one repository-level entrant-minus-incumbent contrast per cohort;
2. a repository bootstrap CI and median/IQR;
3. Wilcoxon signed-rank as a nonparametric association test;
4. whole-role sign-flip as a clearly labelled sensitivity test, not randomization-based causal inference;
5. agent-pair stratification or pair fixed effects where sample size permits;
6. leave-one-repository-out influence and leave-one-agent-pair-out results.

Do not use individual-PR label permutations as the primary p-value.

## Recommended robustness tests, in priority order

1. **Clean provenance rerun:** enforce exact baseline/sensitivity equality for identical configs.
2. **Strict label audit:** human-code a stratified sample across agent, month, prefix status, and later period; include Jules.
3. **Richness control:** equal-count rarefaction and incumbent-only post comparison.
4. **Strict integration:** introducing PR versus introducing role versus any-role integration.
5. **Third-agent sensitivity:** exclude or censor at third entry.
6. **Role-bundle inference:** repository bootstrap/Wilcoxon/sign-flip; remove PR-row permutation.
7. **Pair heterogeneity:** agent-pair and calendar strata; leave-one-pair-out. The saved 41 cohorts have many cells with only 1–6 repositories.
8. **Classifier transport:** rolling-origin and later-period human test; selective accuracy by margin; cross-fitted predictions.
9. **Task-fit target isolation:** leave-current-repository-out historical scores and recent-availability candidate sets.
10. **Influence:** remove the top 1% repositories, cap PRs per repo, and leave-one-agent-out.
11. **Placebos:** future-derived fit should not predict past outcomes; random task labels should yield no fit signal.
12. **Automated tests:** key uniqueness, no right-censored outcome rows, no simultaneous availability leakage, integration credited to the correct role, third-agent status, and identical-output checks for identical configs.

## Acceptable limitations if stated clearly

- Explicit-prefix labels prioritize precision over coverage, provided claims are restricted to those titles.
- AIDev-pop (>100 stars) is a selected subset and does not represent the full 7.6M corpus.
- Agent identity is an observed dataset label, not proof of a repository procurement or deliberate assignment decision.
- Repository onset is endogenous; estimates are descriptive associations rather than causal effects.
- With only 41 baseline repositories, pair-level heterogeneity is underpowered and should be exploratory.
- Five broad classifier classes, especially pooled “maintenance,” trade detail for support and must not be presented as a complete task ontology.

## Shareability decision

- **Specialization/gap filling:** not ready; must fix provenance, permutation, selection, richness, integration attribution, and third-agent contamination.
- **Classifier-filled specialization:** not ready; later-period and Jules transport are unvalidated.
- **Task fit:** shareable only as an adjusted null after a clean rerun and with the interpretation narrowed to historical predictive fit, not beneficial assignment.

