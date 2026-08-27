# Pseudo-edge negative-control exposures (RQ3)

Answers the reviewer question "did you explore negative-control exposures
(pseudo-edges assigned to unrelated comments)?". Every row below uses the same
adjusted linear-probability model, the same 48-hour landmark rule, and the same
repository-clustered interval as the headline addressed-edge analysis. Only the
exposure definition changes.

| exposure | PRs | estimate (pp) | 95% interval (pp) | note |
|---|---|---|---|---|
| addressed_edge_observed | 1,067 | 17.3 | 7.3 to 27.4 | reference; 109 exposed PRs; clustered p=7.54e-04 |
| off_target_reply | 958 | 17.5 | 5.0 to 30.1 | activity control on a different support: PRs carrying the real addressed edge are excluded; 75 exposed PRs; clustered p=6.14e-03; joint-model gap to the addressed edge 1.0 pp (95% CI -13.1 to 15.1, p=0.891) |
| permuted_anchor_pseudo_edge | 1,067 | 16.3 | 15.1 to 17.6 | null distribution over 2000 draws (seed 20260827); interval is the 2.5-97.5 percentile of the null, not a clustered CI; observed 17.3 pp sits at percentile 83.70 (two-sided p=0.1634); anchoring permuted inside 9 repository x month strata covering 26 replying PRs, so only 13% of anchored PRs can move; SUPPORT DEGENERATE, read the calendar_month row instead (16.8 pp, 10.3 to 23.5, two-sided p=0.4393) |
| time_shifted_pseudo_edge | 1,067 | -0.2 | -9.7 to 9.9 | null distribution over 2000 draws (seed 20260827); interval is the 2.5-97.5 percentile of the null, not a clustered CI; observed 17.3 pp sits at percentile 99.95 (two-sided p=0.0010); fake edge times resampled from the observed edge-time distribution independently of each PR's own history |

Seed 20260827; 2,000 draws for each permutation-based row. Per-draw estimates
are in `permutation_null.csv`, the tidy table is `contrasts.csv`, and headline
numbers plus the interpretation string are in `summary.json`.

Specificity verdict: **NOT_SPECIFIC_ANCHORING_NULL_REPRODUCES_ESTIMATE**

The observed addressed edge is 17.3 pp (95% CI 7.3 to 27.4). An off-target exact reply, which carries the same liveness but points at a different inline comment, is 17.5 pp (95% CI 5.0 to 30.1) on 958 PRs; in one joint model the addressed edge exceeds it by 1.0 pp (95% CI -13.1 to 15.1, p=0.891). Permuting which replying PR is anchored to its own trigger, inside repository x month strata and holding every reply event fixed, gives a null centred at 16.3 pp (2.5-97.5 percentile 15.1 to 17.6); the observed estimate sits at percentile 83.70, two-sided p=0.1634. Only 13% of anchored PRs are permutable under that stratification, so the readable anchoring null is the calendar_month one (100% permutable): centred at 16.8 pp (10.3 to 23.5), observed at percentile 56.10, two-sided p=0.4393. Assigning each PR an edge time resampled from the observed edge-time distribution but independent of its own history gives a null centred at -0.2 pp (-9.7 to 9.9), two-sided p=0.0010, so the landmark rule alone does not manufacture the contrast. For reference, the coarser exposure 'any inline reply of any anchoring inside the window' (184 PRs exposed) gives 18.4 pp (9.5 to 27.4), which is where the two liveness-preserving controls land. Verdict: NOT_SPECIFIC_ANCHORING_NULL_REPRODUCES_ESTIMATE.

Scope: observational later-merge differences. Nothing here is a causal effect
or a claim that any reply semantically resolved the review point.
