# Feedback-routing model decision

Date: 2026-08-26

## Decision

Do not make the text model a main-paper contribution. Keep it as a reproducible diagnostic.

The model predicts four directly observed 48-hour outcomes from information available at the trigger: product pair, channel, month, trigger age, simple wording flags, and TF--IDF text. Evaluation uses five folds grouped by repository, so a test repository is never present in training.

## Cross-repository results

| Outcome | Metadata/flags AUC | + text AUC | Change |
|---|---:|---:|---:|
| User-account mediation | 0.570 | 0.596 | +0.025 |
| Author-agent response | 0.732 | 0.738 | +0.006 |
| Triggering-reviewer continuation | 0.683 | 0.696 | +0.013 |
| Force-push | 0.700 | 0.685 | -0.015 |

Text adds little out-of-repository information and hurts force-push ranking. The largest coefficients also include repository/topic vocabulary, so they are not safe mechanisms. Exact-stratum comparisons of simple wording flags are mostly small or uncertain. Training a larger model would increase complexity without a validated construct or a clear scientific gain.

## What the model did contribute

The diagnostic exposed a measurement error: an inline trigger and its enclosing submitted review could be counted as a feedback event followed by a new review. After review-batch de-duplication and exact-parent reply matching, the apparent later-review rate fell from 63.3% to 49.7%, and direct replies fell from 3,361 to 875 events. This construct correction is more valuable than the predictive score.

## Next model gate

The prepared 600-case blinded audit must be completed first. A semantic model may be trained only after human labels meet the declared agreement and prevalence gates in `protocol/feedback_response_label_schema.json`. AI-assisted or ensemble labels must remain separate from human gold.
