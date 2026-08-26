# E1 canonical decision-chain results

**Design:** latest outcome strictly known before each successor PR opened; resolution time is `max(closed_at, merged_at)`; tied resolution times are excluded.

- Prior-non-integration anchors: 50,211.
- Exact, non-left-censored streak episodes: 44,692.
- Current PRs are post-multi-agent-onset and have 30 complete follow-up days.
- Confidence intervals are repository-clustered; contrasts are observational, not causal.

## Exact streak estimates

| Streak | Stay n | Switch n | Stay merge | Switch merge | Contrast | Switch rate |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 21,741 | 7,984 | 69.7% | 71.8% | 2.04 pp [0.44, 3.64] | 26.9% |
| 2 | 5,153 | 1,680 | 55.9% | 62.3% | 6.43 pp [2.99, 9.88] | 24.6% |
| 3+ | 6,585 | 1,549 | 25.3% | 43.3% | 17.98 pp [6.97, 28.99] | 19.0% |

## Censoring

Episodes without enough observed predecessor history are excluded from the main dose-response analysis and retained in `e1_streak_censoring.csv`.

## Interpretation boundary

The right-panel contrasts compare observed switching with observed persistence. They can motivate common-support and fixed-effect models, but do not identify a causal effect of switching.