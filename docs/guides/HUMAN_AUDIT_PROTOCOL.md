# Human audit protocol for task continuity

## Purpose

Decide whether a later PR continues the same task as an earlier closed-unmerged PR. This judgment is separate from whether a contributor or agent changed and separate from whether the later PR merged.

## Files

- `outputs/human_audit/coder_A_blinded.csv`
- `outputs/human_audit/coder_B_blinded.csv`
- `outputs/human_audit/audit_key_do_not_share_before_coding.csv`
- `outputs/human_audit/sampling_design.csv`

The two coder packets contain the same cases in different random orders. Do not open the key until both first-round files are frozen.

## Labels

### `same_task`

- `yes`: both PRs target the same named bug, feature, test goal, refactor goal, or explicit follow-up/revert of the earlier attempt.
- `no`: the PRs have different goals. A shared lockfile, README, module, test file, configuration file, or broad subsystem is not enough.
- `unclear`: the available title, body, paths, and timing cannot separate same task from related but different work.

### `confidence`

- `high`: direct wording, a shared issue/task reference, or a clear follow-up relation.
- `medium`: several signals agree, but one important fact is missing.
- `low`: the label is mainly a boundary judgment.

### `intentional_handoff`

- `yes`: the evidence explicitly says that work, context, or responsibility moved from an earlier attempt, contributor, session, or agent.
- `no`: the evidence explicitly shows independent work or no transfer.
- `not_observed`: no direct transfer evidence is present. This is the default even when `same_task=yes`.

## Coding order

1. Read the earlier and later titles and bodies.
2. Check the shared path type and timing.
3. Assign `same_task`, confidence, and a one-sentence evidence note.
4. Assign intentional handoff separately. Never infer it only from agent change.
5. Freeze both coder files before opening the key or merge outcomes.
6. Compute raw agreement and Cohen's kappa for three labels and for `yes` versus other.
7. Adjudicate disagreements with the PR URLs and, if needed, issue, discussion, and diff evidence.

## Analysis rules

- Keep `unclear` separate in the main agreement table.
- Report weighted prevalence using `design_weight`; raw sample shares are not population estimates.
- Split the adjudicated data before fitting a continuation rule. Do not choose a threshold and test it on the same cases.
- Report precision, recall, PR-AUC, and calibration on the held-out set.
- Estimate agent effects only if validated changed-agent cells are large enough for repository-aware inference. Otherwise report counts and examples only.

## Blinding limits

The script removes agent names and outcome words from the main text fields and withholds agent, contributor, and merge columns. Free text can still contain indirect identity clues. Record any case where blinding appears broken.
