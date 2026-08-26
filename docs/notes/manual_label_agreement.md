# Agreement audit for two AI-assisted task-continuity screens

Inputs:

- `tmp/manual_label_legacy.csv`
- `tmp/manual_label_novelty.csv`

Merged row-level audit:

- `tmp/manual_label_agreement_merged.csv`

Date: 2026-08-25

## Scope and caution

Both inputs are **AI-assisted screening only**, not human validation. Agreement between two AI screens does not prove ground truth, task identity, or an intentional handoff. Neither screen's original label was changed. Reconciliation notes only explain why evidence thresholds or definitions differed.

All 109 episodes matched one-to-one on `(failed_id, successor_id)`; there were no missing or duplicate episode keys.

## Three-class agreement: yes / unclear / no

Raw agreement was **94/109 = 86.24%**. Cohen's kappa was **0.688**.

| Legacy screen \ Novelty screen | No | Unclear | Yes | Total |
|---|---:|---:|---:|---:|
| No | 73 | 7 | 0 | 80 |
| Unclear | 4 | 12 | 0 | 16 |
| Yes | 0 | 4 | 9 | 13 |
| Total | 77 | 23 | 9 | 109 |

There were 15 disagreements:

- 11 were `no` versus `unclear`;
- 4 were `yes` versus `unclear`;
- 0 were direct `yes` versus `no` conflicts.

This pattern matters more than the headline percentage: the screens agreed on all clear endpoint distinctions. Disagreement was confined to the uncertainty boundary.

## Binary agreement: yes versus other

After combining `no` and `unclear` as “other,” raw agreement was **105/109 = 96.33%**. Cohen's kappa was **0.799**.

| Legacy binary \ Novelty binary | Other | Yes | Total |
|---|---:|---:|---:|
| Other | 96 | 0 | 96 |
| Yes | 4 | 9 | 13 |
| Total | 100 | 9 | 109 |

The novelty screen's nine `yes` cases are a subset of the legacy screen's thirteen. Thus, the difference is a stricter threshold for calling broad or potentially subsuming follow-up work the same task, not contradictory positive cases.

## Generic versus non-generic path evidence

Agreement was materially stronger when the shared path was non-generic:

| Path class | N | Three-class raw agreement | Three-class kappa | Binary raw agreement | Binary kappa |
|---|---:|---:|---:|---:|---:|
| Generic-only | 49 | 81.63% | 0.438 | 95.92% | 0.484 |
| Non-generic | 60 | 90.00% | 0.806 | 96.67% | 0.870 |

This supports the earlier warning that a README, lockfile, manifest, or other generic overlap gives weak evidence of task continuity. Kappa is also prevalence-sensitive, so these subgroup values should be treated as diagnostics rather than population reliability estimates.

## Reconciliation of definition conflicts

The merged CSV preserves both labels and adds a reconciliation category and note for every disagreement. The 15 cases fall into these evidence-boundary patterns:

| Boundary pattern | Rows | Meaning |
|---|---:|---|
| Related domain versus same problem | 4 | Both titles concern one broad component, but do not name the same defect or deliverable. |
| Broad documentation theme | 3 | Both edit one documentation area, but describe different documentation needs. |
| Broader successor may subsume prior | 2 | A broad successor could contain the narrow prior task, but the title cannot confirm inclusion. |
| Shared subsystem versus distinct bug | 2 | A specific path is shared, while titles name different behaviors or defects. |
| Opaque successor title | 1 | A branch/sync-style title hides the successor's actual task. |
| Meta-cleanup versus feature work | 1 | Workflow cleanup follows feature work but may not be the same implementation task. |
| Shared example versus distinct API change | 1 | Work occurs in one example area but has different stated deliverables. |
| Sibling features versus one task | 1 | Same path and timing suggest one episode, while titles can also denote sibling features. |

No reconciliation note claims intentional transfer between agents.

## Recommended use in analysis

Use transparent sensitivity sets rather than converting these screens into “human-validated” ground truth:

1. **Strict continuity set:** the 9 consensus-`yes` episodes.
2. **Expanded continuity sensitivity:** add the 4 `yes`/`unclear` boundary episodes, yielding 13.
3. **Consensus negative set:** the 73 consensus-`no` episodes.
4. **Unresolved set:** 12 consensus-`unclear` plus 11 `no`/`unclear` disagreements; exclude these from strict task-recovery estimates or report bounds.

For a submission-ready validation claim, a blinded human coding round with a written codebook is still required. These files can seed that protocol but cannot replace it.

## Calculation details

Cohen's kappa was calculated as:

`kappa = (observed agreement - chance agreement) / (1 - chance agreement)`

using the observed marginal label distributions across the same 109 episode pairs. No weighting was applied to the three classes.
