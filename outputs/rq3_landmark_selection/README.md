# Is the hour-48 landmark itself post-exposure?

Produced by `scripts/analysis/run_rq3_landmark_selection_probe.py`.

The published RQ3 design keeps pull requests still open at hour 48, asks whether
an exact reply arrived *by* hour 48, and counts merges only *after* hour 48. The
exposure is therefore measured inside the same window that decides cohort
membership, so "still open at hour 48" can be a collider on the path from
exposure to outcome. This directory answers that objection with three analyses.
None of them replaces the published estimate, and none identifies a causal
effect.

The published reference the three are read against is +17.3 percentage points
(95% interval: +7.3 to +27.4), on 109 exposed pull requests of 1,067. That
reference is re-derived by this script and checked against the published
artifact before any row is written; the script raises rather than reports if the
check fails.

Seed is `20260826` and every permutation test uses 2,000 draws, matching the
rest of the repository.

| File | What it holds |
|---|---|
| `selection_ordered_landmarks.csv` | Part 3. Exposure read at hour 1, 6 or 24; outcome is closure before hour 48, so the exposure strictly precedes it |
| `selection_raw_contingency.csv` | Part 3 companion. The unordered reply-by-closure contingency, and the exact-reply prevalence in the whole population against the survivors |
| `whole_population_hazards.csv` | Part 2. Discrete-time hazard models with no landmark at all, the reply entering as a time-varying covariate |
| `standardised_risk_difference.csv` | Part 2. G-computation of the 30-day merge risk under always-answered against never-answered, on the percentage-point scale the article uses |
| `sequential_landmark_estimates.csv` | Part 1. Cohort fixed at hour 48, exposure read only in hours 48 to 96, outcome read afterwards |
| `summary.json` | Machine-readable version of all of the above, plus the published reference |

## What the three analyses show

**The landmark gate is not independent of the exposure.** With the exposure read
at hour 1 and the outcome being closure by hour 48, an exact reply is +10.7
points more likely to be followed by closure (95% interval: +3.2 to +18.2), and
any user-account reply +11.9 points (+5.4 to +18.4). The gap shrinks as the
exposure landmark moves out and is −0.2 points (−6.6 to +6.3) for the exact
reply read at hour 24. Consistently, exact-reply prevalence falls from 12.8% in
the 3,942-PR whole population to 10.2% among the 1,067 survivors. So the
surviving cohort is not a random slice: replies push pull requests out of it.

**Dropping the landmark keeps the direction and shrinks the size.** Following
every cross-product inline-trigger pull request with a complete 30-day horizon
from its trigger, with the reply as a time-varying covariate, the merge-hazard
odds ratio is 1.74 (1.38 to 2.18) for the exact edge and 2.14 (1.76 to 2.60) for
any user-account reply. Standardised over the whole population, the 30-day merge
risk is +11.2 points higher under always-answered than under never-answered,
against the +17.3 the landmark cohort gives. The reply also moves the closure
hazard on its own (odds ratio 1.46, 1.19 to 1.79), which is the same selection
Part 3 measures. Restricted to post-hour-48 person-time with the exposure
counted only when the reply arrives after hour 48, the odds ratio is 2.52 on an
interval from 0.91 to 6.97: only 47 exposed person-periods, so underpowered
rather than null.

**A design where the landmark genuinely precedes the exposure has too little to
work with.** Holding the 1,067 fixed at hour 48 and reading the exposure only in
hours 48 to 96, just 17 receive an exact reply in that window. On the 958 that
were still unanswered at hour 48, widening the exposure to any user-account
reply gives 160 exposed and +0.7 points (−9.3 to +10.7), a null on a slower and
smaller subgroup rather than a refutation. The rows labelled `still_open_at_96h`
are secondary and carry `selection_free = False`: they condition on survival past
the exposure window and so re-introduce exactly the structure being tested.

Read together, the three place the effect above zero and below +17.3 points,
with +11.2 as the landmark-free reading. Interpretation is unchanged from the
primary analyses: these are observational later-merge probability differences,
not causal effects and not semantic resolution rates.
