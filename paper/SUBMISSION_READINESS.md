# EMSE submission readiness

Last checked: 2026-08-28.

## Current state

The four-RQ analysis, its figures, the Supplementary Information, the validation gates, the LaTeX manuscript, and the fixed-allowlist source package are technically ready. The full public-data build was last run on 2026-08-28, against a 37-page article and a 37-page Online Resource 1; the counts in this file are written from those PDFs by the page-count sync step, not by hand. The package is not ready to upload because author metadata, declarations, and the public artifact link are still missing. Semantic coding is not a blocker for the current core claims; it becomes mandatory only if semantic-overlap claims are added.

## Completed

- [x] Paper has exactly four RQs — handoff, who bridges, who writes the connection and whether it marks a later state, and what goes with an answer across the boundary — and one connected ownership-topology story.
- [x] Five supplied authors are present in the requested order.
- [x] Springer Nature `sn-jnl` template and author-year bibliography are used.
- [x] Abstract is within the journal's 150 to 250 word range.
- [x] AIDev revision, cohort boundary, and analysis windows are pinned.
- [x] Exact parent edges and distinct review batches prevent self-response inflation.
- [x] Burst sensitivity covers 0, 1, 5, 10, and 30 minutes.
- [x] Exact-author cross/same comparison uses repository-cluster uncertainty.
- [x] Prior public history excludes the focal PR and future reviews.
- [x] Exact-edge analysis uses a fixed landmark, pre-trigger controls, reply-window sensitivity, repository fixed effects, product-pair exclusions, and a generic-discussion specificity control.
- [x] The exact-edge association is bounded against unmeasured structure: E-value, tipping grid, three pre-trigger placebo outcomes, and repository-stratified randomisation inference. The one-hour placebo failure is reported, not dropped.
- [x] The RQ3 exposure is described by who actually writes it: 105 of 128 exposure events are user accounts, 13 are the triggering product replying to itself, and 3 are a different mapped product. The estimate is refit under stricter edge definitions and stays positive.
- [x] The hour-48 landmark restriction is quantified in the paper: the cohort is the 27 percent of cross-product inline triggers still open at the landmark, so the estimate describes slower-resolving PRs.
- [x] Randomisation inference is reported conditionally, on the 46 repositories that can be re-randomised and with repository fixed effects, so its reference distribution is centred; the uncentred unconditional version is retained in the appendix with an explanation.
- [x] Hybrid route analysis is secondary triangulation rather than a second headline.
- [x] Attractive persistence, escalation, one-way takeover, routing, memory-to-merge, task-breadth, and exact-file claims that failed stronger checks are rejected or moved to the appendix.
- [x] Structural overlap covers the full 167-locus population and remains semantically unlabeled.
- [x] 6 answer-first figures are exported at the journal's exact 372 pt text width, embed non-Type-3 fonts (verified 2026-08-28 with `pdffonts`: every face in Fig2 to Fig6 is a CID TrueType, and the compiled manuscript reports no Type 3 font either), and pass an automated geometry gate for clipping, overlap, and the 8 pt type floor Springer states. Each carries a different visual form; none is a forest plot. Colour-vision and greyscale proofs are regenerated with every build.
- [x] 3 appendix figures explain dataset layers, joins, and feature-specific denominators.
- [x] A separate generated appendix contains data contracts, joins, all estimates, robustness checks, falsification tests, quality gates, and experiment decisions.
- [x] Fifteen external candidates were compatibility-screened; 11 acquisitions were pinned with revision, license, integrity, and release-boundary records.
- [x] The complete SWE-Review-Chat topology audit was fail-closed after AIDev overlap removal; incompatible sources were not pooled into the RQs.
- [x] AI use, coverage limits, and non-causal scope are disclosed.
- [x] Build and package scripts compile both PDFs, scan logs, make a complete archival source bundle, and stage a main-only flat source ZIP plus `ESM_1.pdf` for the portal.
- [ ] Page-complete visual QA covers all 37 manuscript pages and all 37 Supplementary Information pages, which carry 13 tables. The 2026-08-28 pass cleared the 36-page article and 33-page appendix; the four appendix pages added by the hour-48 landmark-selection probe compile with no error, no overfull box and no undefined reference, and the new table was inspected, but the document has not been re-read page by page since.
- [x] Official venue requirements were rechecked on 2026-08-26 and mapped to project files.

## Scientific and production gates before upload

- [x] Keep "later visible action," "exact addressed edge," and observational wording; do not call the edge a fix or resolution.
- [x] Keep collision, duplication, complementarity, and contradiction outside the core claims while semantic labels remain pending.
- [ ] Re-run the full build and final PDF visual QA after author metadata is inserted (the placeholder build has already passed).
- [x] Archive the public artifact and add a permanent URL/DOI. Published
      2026-08-28 at `https://doi.org/10.5281/zenodo.22140821`; verified to
      resolve and to be reachable without authentication.
- [ ] Recheck that the live Editorial Manager “site under development” warning has been removed, or obtain an alternative route from a guest editor.

## Optional semantic extension

- [ ] Only if adding a semantic-overlap result: two independent coders complete the full 167-locus blinded population.
- [ ] Freeze both coder files before opening the private key; report agreement and adjudication.
- [ ] Do not add duplication, complementarity, or contradiction claims unless the frozen reliability and product-pair generality rules are met.

## Required author input

- [ ] Affiliation, department, city, and country.
- [ ] Corresponding-author email and confirmation of corresponding author.
- [ ] Final name spelling, order, and ORCIDs.
- [ ] CRediT roles.
- [ ] Funding and competing-interests statements.
- [ ] Institutional ethics wording for public GitHub metadata.
- [ ] Acknowledgements or confirmation to remove them.
- [ ] Confirmation that the manuscript is not under review elsewhere.
- [x] Conference-extension statement: no prior conference version is recorded anywhere in this repository, so the cover letter keeps the original-work branch and the extension branch was deleted. Authors should contradict this if a conference version exists.

## Submission route

The special issue uses rolling review. The final deadline is September 28, 2026. In Editorial Manager, select `Research Papers`, answer yes to the special-issue question, and select `Agentic Software Engineering`.

The official Editorial Manager landing page displayed `Site under development. Do not use for live manuscript submission.` on 2026-08-26. This is a live portal gate, not a paper-format failure. See `../docs/decisions/VENUE_SIGNOFF_20260826.md` for the verified requirement map and editor contacts.

- <https://emsejournal.github.io/special_issues/2026_SI_Agentic_SE.html>
- <https://link.springer.com/journal/10664/submission-guidelines>
- <https://www.editorialmanager.com/emse/>
