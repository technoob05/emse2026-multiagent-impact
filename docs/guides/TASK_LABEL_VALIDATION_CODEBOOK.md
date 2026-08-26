# Human validation codebook for later-period task labels

## Goal

Validate task labels for pull requests opened from August 2025 through March
2026. This period is outside the supplied task-label table. The validation is
required before model-filled task labels can support a paper claim.

## Blinding

Coders see the title, shortened body, public PR URL, and a random case ID. They
do not see the agent brand, period, title-prefix flag, model prediction, model
margin, merge outcome, or the other coder's label.

Do not search for agent identity or merge outcome. Open the URL only when the
title and provided body are not enough to understand the intended change.

## Choose one task label

- `feat`: adds a user-visible or developer-facing capability.
- `fix`: corrects faulty behavior, a defect, regression, or crash.
- `docs`: mainly changes explanation, examples, guides, or reference text.
- `test`: mainly adds or changes tests without a larger production change.
- `maintenance`: refactor, build, CI, performance, style, chore, dependency,
  cleanup, or revert work whose main goal is maintaining the system.
- `unclear`: the available evidence does not support one label.

Choose the main intent, not every file touched. For example, tests added to
support a bug fix remain `fix` when correcting behavior is the main goal.

## Confidence

- `5`: direct and explicit evidence.
- `4`: clear intent with minor ambiguity.
- `3`: best label, but another label is plausible.
- `2`: weak evidence; use `unclear` if no label is defensible.
- `1`: insufficient evidence; normally pair with `unclear`.

Copy a short phrase into `evidence_from_title_or_body`. Do not infer intent from
the agent brand or whether the PR merged.

## Process

1. Each coder completes and locks their CSV independently.
2. Compute raw agreement, Cohen's kappa, per-class precision/recall for the
   model, and results by agent, period, and prefix status using the private key.
3. Discuss disagreements and create a separate adjudicated file. Never replace
   the original coder files.
4. Report both pre-adjudication agreement and adjudicated model performance.

The validation result is acceptable for confirmatory analysis only if each
major agent-period stratum has support and selective performance is reported
for prefix and non-prefix titles separately. Google Jules must be reported even
if its sample is smaller.
