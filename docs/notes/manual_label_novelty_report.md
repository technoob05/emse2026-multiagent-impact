# Conservative pre-audit of direct-handoff candidates

This is AI-assisted screening for human follow-up, not final manual validation or ground truth. I reviewed 109 sampled PR pairs using the two titles, shared-path type and example, timing, contributor/agent transition, and PR URLs available in the audit file. I did not infer intent, communication, or deliberate handoff.

## Screening result

| Label | Count | Share |
|---|---:|---:|
| Likely same task | 9 | 8.3% |
| Unclear | 23 | 21.1% |
| Likely different task | 77 | 70.6% |

Confidence breakdown: 5 high-confidence and 4 medium-confidence `yes`; 16 low-confidence and 7 medium-confidence `unclear`; 39 high-confidence and 38 medium-confidence `no`.

Only 8 of 60 pairs with a non-generic shared path were labelled likely same task (13.3%). Only 1 of 49 generic-only pairs was labelled likely same task (2.0%), based on unusually strong title and temporal continuity rather than the generic path. This confirms that file overlap alone is a weak task-continuity measure.

The 9 likely-same-task cases comprise:

- 3 different-contributor/different-agent pairs;
- 2 same-contributor/different-agent pairs;
- 4 same-contributor/same-agent pairs; and
- 0 different-contributor/same-agent pairs.

These counts are descriptive only because the audit sample is stratified by transition and path type. They must not be treated as population prevalence.

## Strongest examples

- BoxModule type-alias-to-wrapper refactor followed within 25 minutes by the same wrapper refactor, with nine shared non-generic files (`3539231229 -> 3541495583`).
- Frameless-window gallery transparency fix followed within 29 minutes by another transparent-gallery repair in the same UI controller (`3799760043 -> 3799949025`).
- A WIP curve-handle display repair followed almost immediately by a broader edit-sidebar stabilization that explicitly includes curve handles (`3911652169 -> 3911662132`).
- Pascal compiler checklist work followed by Pascal compiler tests and outputs (`3209648331 -> 3211937335`).
- Android sample/emulator test workflow followed by Android instrumentation-test execution in the same workflow (`3506639193 -> 3507198249`).

## Implication for the paper

The simple `shared file after closed-unmerged PR` construct is not strong enough to call a handoff: most audited pairs concern different work, even when a non-generic file is shared. A defensible continuation construct needs strong title/body similarity, issue-reference agreement where available, inverse-frequency-weighted path overlap, timing, and human validation. The paper should use `likely task continuation` or `continuation candidate`, not `handoff`, unless the PR discussion explicitly establishes takeover.

The current audit also suggests that real cross-agent continuation is observable but sparse. It is better suited to a focused mechanism subset or qualitative validation layer than as an unqualified population-wide handoff measure.

Detailed labels are in `tmp/manual_label_novelty.csv`.
