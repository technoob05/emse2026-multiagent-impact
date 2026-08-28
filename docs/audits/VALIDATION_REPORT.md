# Validation report

Last checked: 2026-08-28.

## Verdict

The four-RQ artifact is technically ready for author review. The complete analysis, test, notebook, LaTeX, figure, and packaging pipeline passes. The manuscript remains blocked from journal upload only by author-supplied metadata, declarations, and a permanent artifact URL/DOI.

The paper does not depend on semantic same-locus labels or exact-file task-continuity claims. Those exploratory branches remain outside the core story unless their separate human-validation gates are completed.

## Load-bearing data and time-order checks

- All 7,685,281 full-corpus PR identifiers are unique.
- Follow-up events resolve to known PRs; the reported event joins have zero orphan PR identifiers.
- The seven-day topology cohort contains 8,608 PRs at every burst threshold.
- Nine exact duplicate event rows are removed; the first-state assignment changes for zero PRs.
- Later events are strictly after the trigger and inside the declared observation window.
- The fixed-landmark cohort contains one row for each of 1,067 PRs. All 423 positive outcomes occur after hour 48 and within day 30.
- Prior-history matches exclude the focal PR, future rows, and equal-time rows.
- Exact replies use the trigger's parent-comment identifier, and later reviews use a distinct review-batch identifier.

## Result robustness

- The post-burst user-over-product ordering survives every leave-one-repository-out and leave-one-product-pair-out check.
- The exact-author matched cross/same visibility contrast remains negative under repository resampling and a tighter time caliper.
- Prior public review history is common across first bridges, decisive reviewers, and the wider responder layer; the paper therefore avoids a preferential-selection claim.
- The exact-edge association remains positive across 1, 6, 24, and 48-hour reply windows, repository fixed effects, product-pair exclusions, overlap weighting, and a comparison restricted to PRs with other public discussion.
- The automation-to-user route gives a same-direction secondary check in a separate fixed-landmark cohort.
- All outcome models remain observational; no estimate is reported as a causal effect, repair rate, or review-quality score.

## Cross-dataset evidence gate

- Fifteen public candidates were screened against the same PR, event-time, actor, review-batch, exact-parent, and later-state contract.
- Eleven local acquisitions have frozen revision, license, size, integrity, and release-boundary records.
- The complete SWE-Review-Chat scan covers 1,082,529 public PR rows. Seven exact-edge candidate PRs were found before overlap removal, but all seven already occur in AIDev; zero disjoint landmark rows remain. The independent replication gate is therefore rejected rather than reported as a null result.
- The independently packaged AI-to-AI cohort agrees on product pair and trigger timing for nearly all overlapping PRs, but only nine exposed PRs remain. It is used for attribution sensitivity, not outcome replication.
- SWE-PRBench and AIReviewAction inform semantic measurement only. Their row topology or label provenance is not compatible with the paper's four RQs.
- No third-party raw data enters the manuscript source archive.

## Reproducibility and production checks

- Automated tests: 48 passed; one non-failing sortedness warning.
- The executable notebook completed successfully.
- Both LaTeX logs contain no errors, overfull boxes, undefined citations/references, or rerun warnings.
- Manuscript: 37 A4 pages. Supplementary Information: 36 A4 pages. Both counts are read from the built PDFs on the date of this report; re-measure rather than trusting them after any edit.
- Page-complete visual QA inspected all 36 manuscript pages and all 33 Supplementary Information pages of the 2026-08-28 build. No clipping, unreadable figure text, float-order error, duplicate caption, or blank page was found. The article is now 37 pages and the Supplementary Information 37, after the hour-48 landmark-selection probe was wired into the appendix; both recompile with no error, no overfull box and no undefined reference, and the new table was inspected, but a page-by-page re-read is still outstanding.
- All PDF fonts are embedded, and `pdffonts` reports no Type 3 font in either document. This is worth re-running rather than trusting: an intermediate build on 2026-08-28 did carry one Type 3 font in the manuscript, and the current build does not. The six manuscript figures have never carried one; every glyph in them is a CID TrueType face.
- PDF text and packaged source contain no local drive, user-profile, cache, or external-raw-data path.
- The flat source ZIP contains 20 allowlisted manuscript, bibliography, class, figure, and icon files, and no checksum manifest of its own. `SUBMIT/README.md` lists the 20 by name, and `SUBMIT/CHECKSUMS.sha256` covers the ZIP as a whole alongside every other file in the bundle.

## Rejected or deferred exploratory claims

- Product co-presence is collaboration: rejected.
- Repeated automation naturally escalates to a user: rejected by an order-permutation placebo.
- Post-burst ownership is a one-way user takeover: rejected; transitions move in both directions.
- Prior review history causes later merge: rejected by stronger within-repository comparisons.
- Review-request events prove intentional routing: rejected because target-account coverage is zero.
- Exact-file succession proves task handoff: rejected because file reuse does not establish task identity.
- Same-locus comments are redundant, complementary, or contradictory: deferred to independent dual coding and product-pair generality gates; not needed by the current paper.

## Remaining upload blockers

1. Affiliation, department, city, and country.
2. Corresponding author and email; final name spelling/order and ORCIDs.
3. CRediT roles, funding, competing interests, ethics wording, and acknowledgements.
4. Confirmation that the manuscript is not under review elsewhere and the cover-letter extension statement.
5. Public artifact archive and permanent URL/DOI.
