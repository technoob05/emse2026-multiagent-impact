# Sensitivity sweeps for four load-bearing constants

Produced by `scripts/analysis/run_constant_sensitivity_sweeps.py` and
`scripts/analysis/summarize_bootstrap_draw_sweep.py`.

Every primary path is unchanged. The primary settings are re-derived by the same
code as the sweep and checked against the published artifacts before any sweep
row is written; the scripts raise rather than report if that check fails.

Seed for every sweep is `20260826`, matching the rest of the repository.
(`scripts/analysis/run_pseudo_edge_negative_control.py` uses `20260827` and was
deliberately left alone.)

| File | What it holds |
|---|---|
| `landmark_sweep.csv` | Primary RQ3 model (specification A) at landmark 24/48/72/96 hours, horizon fixed at 30 days |
| `horizon_sweep.csv` | Same model at horizon 14/30/60 days, landmark fixed at 48 hours |
| `response_window_sweep.csv` | RQ1 first post-burst owner at follow-up window 1/3/7/14 days, burst fixed at 5 minutes |
| `merge_curves_draws_{400,1000,2000,4000}/` | `run_merge_curves.py` re-run at each draw count |
| `bootstrap_draws_band_shift.csv` | Per-arm, per-band-edge shift against the 2,000-draw reference |
| `bootstrap_draws_band_width.csv` | Band widths at each draw count |
| `bootstrap_draws_conclusions.csv` | Whether each qualitative Figure 4 claim survives each draw count |
| `summary.json`, `bootstrap_draws_summary.json` | Machine-readable versions of the above |

## What the sweeps show

**Landmark.** The sign is positive at all four landmarks and the point estimate
moves monotonically down as the landmark moves out (+16.7, +17.3, +14.3, +11.3
percentage points). The repository-clustered interval excludes zero at 24, 48 and
72 hours and *includes* zero at 96 hours (p = 0.054). The cohort shrinks from
1,264 to 857 pull requests across that range, so the loss of significance at 96
hours is at least partly a loss of power, not necessarily a change of sign.

**Horizon.** The sign is positive at 14, 30 and 60 days. Sixty days is estimable
but the cohort falls to 693 pull requests with 46 exposed, and the interval
includes zero (p = 0.093). Thirty days is the maximum of the three, so the
published estimate is the largest value in the sweep rather than a middling one.

**Follow-up window.** `user_account` is the modal first post-burst owner at
every window tested, and the user-minus-mapped-product difference excludes zero
at every window. The difference grows with the window (+15.7, +17.4, +18.6,
+18.9 pp), so seven days is conservative rather than favourable.

**Bootstrap draws.** The curve point estimates are deterministic and byte-identical
across draw counts. Only the bands move: at 400 draws a band edge sits up to
1.70 pp (mean 0.29 pp) from its 2,000-draw value. No qualitative conclusion
changes at any draw count. `run_merge_curves.py` now defaults to 2,000 draws;
the 400-draw artifacts are preserved here for comparison.

Interpretation is unchanged from the primary analyses: these are observational
later-merge probability differences and observable public response topology, not
causal effects and not semantic resolution rates.
