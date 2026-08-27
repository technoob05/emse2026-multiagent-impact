# Burst-threshold selection

Reviewer response artefact. It asks whether the RQ1 burst window (fixed at five
minutes in `outputs/burst_topology`) can be chosen from the data, whether it
should differ by product, and how much the RQ1 ownership conclusion depends on
the answer. The burst rule itself is imported from
`scripts/analysis/run_burst_collapsed_topology.py`, so every owner count here is
directly comparable with the published one.

## Answer

The trigger-to-next-event gap is NOT bimodal in the way the burst argument needs. On a log time scale the density rises smoothly and monotonically from the one-second timestamp floor to a single dominant mode at 4.25 minutes -- there is no separate near-zero machine spike and no valley between a machine mode and a human mode. The density does have a second, far-away mode at 981.3 minutes with an antimode at 404.8 minutes, but that is the overnight / next-working-day boundary at several hours, not a machine/human boundary, and it is far outside any burst window anyone would defend. The data therefore do not support a natural burst cut: any burst window in this analysis is a modelling convention rather than a discovered feature of the data. A Silverman critical-bandwidth test of unimodality on the log gap returns p = 0.002 (unimodality rejected), which reflects that far-apart second mode rather than anything at burst scale. Because the antimode rule declines to select a cut, the reported data-driven cut comes from the log-hazard change-point rule, which always returns a value: 0.9 minutes globally (repository bootstrap 95% interval 0.896 to 1.32 minutes), and the change it marks is an increase in the log-time hazard (0.00792 to 0.0797 per log-time bin), that is, the point where responses start arriving rather than the point where an automated burst ends. Per-product cuts from the same rule span 1.59 to 458 minutes, so product-specific windows are not better supported than a single global one. Restricting the same change-point search to gaps below 60 minutes tightens the per-product cuts to 0.612 to 8.6 minutes, a range that brackets the fixed five-minute window. The antimode rule finds a burst-region antimode in only 16.8% of repository bootstrap replicates, and in none of the products. The RQ1 conclusion that a person is usually the one who acts next survives every cut examined here -- fixed 0/1/5/10/30 minutes, the global data-driven cut, and product-specific cuts -- with the repository-clustered interval on the user-minus-mapped-product difference excluding zero in every case. Observed public response topology; no causal, semantic-resolution, or verified-manual-work claim.

## Rules

- **Rule A, `log_gap_kde_antimode`.** Gaussian KDE of log10(gap in minutes) with
  Silverman's rule-of-thumb bandwidth on a fixed 1024-point grid; the cut is the
  lowest interior antimode at or below 60
  minutes, and the rule declines to select a cut when there is none.
- **Rule B, `log_hazard_change_point`.** Discrete-time hazard of the next event
  over log-spaced bins (12 per decade, at least 10 events and 10 at risk per
  bin); a two-segment piecewise-constant fit to the log hazard by exhaustive
  least squares; the cut is the right edge of the first segment. Reported both
  unrestricted and restricted to the burst region.
- **Unimodality test.** Silverman critical-bandwidth test with a smoothed
  bootstrap.
- **Intervals.** Whole repositories resampled with replacement, the same
  clustering convention as the published burst topology.

## Files

- `summary.json`: headline numbers and the `interpretation` string.
- `gap_histogram.csv`: full trigger-to-next-event gap histogram, log-spaced bin
  edges plus counts, shares, densities and the KDE evaluated at each bin, so a
  figure can be drawn without rerunning anything.
- `gap_distribution_shape.csv`: quantiles and coverage of each fixed window.
- `next_event_hazard.csv`: the binned hazard, globally and per product.
- `selected_cuts.csv`: every rule and scope with its cut and bootstrap interval.
- `owner_split_sensitivity.csv`: the sensitivity table -- the user-account
  versus mapped-product first-owner split at every cut.
- `owner_split_sensitivity_by_product.csv`: the same split within each product.
- `agreement_with_five_minutes.csv`: share of PRs whose first-owner state is
  unchanged relative to the published five-minute assignment.

Observed public response topology; no causal, semantic-resolution, or
verified-manual-work claim.
