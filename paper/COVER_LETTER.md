[SUBMISSION DATE]

Dear Guest Editors of the Special Issue on "Agentic Software Engineering: The Rise of AI Teammates,"

Please consider our manuscript, "Participation Is Not Collaboration: Tracing Public Ownership After Cross-Product Agent Review," for publication as a Research Paper in Empirical Software Engineering.

**In plain terms.** When one AI coding tool writes a pull request and a different AI tool reviews it, it looks like two agents working together. We checked whether that is true. Using a large public set of GitHub pull requests, we followed each cross-tool review comment and asked what happened next. One tool almost never answers the other. Once we set aside the quick burst of automatic events, a person is usually the one who acts next, and that person has often reviewed code in the same project before. The one connection that goes together with a later merge is a direct reply to the review comment, and four times in five a person writes it. That is a link we observed, not proof of cause. Counting tools on a pull request does not measure teamwork.

The paper studies a basic measurement problem in agentic software engineering. When two agent products appear on one pull request, the trace looks multi-agent, but it may be a fast automation burst rather than a connected handoff. Using a pinned AIDev-7.6M revision, we reconstruct the public path after one cross-product review trigger: the exact parent edge, the de-batched review round, burst sensitivity, the next visible owner, earlier public repository-review history, and the later state after a fixed hour-48 check point.

Three results motivate the paper. First, direct different-product dialogue is rare once the fast burst of events is set aside. Second, user accounts form the main visible bridge across the product boundary, and most of these accounts have earlier public review history in the repository. Third, an exact reply to the trigger is associated with more later integration after adjustment for measured pre-trigger context.

We report the scope of that third result rather than only its size. The outcome group is the 27% of cross-product inline-trigger PRs still open at hour 48, so it describes slower-moving PRs. The exposure is written by a user account in 105 of 128 events, by the triggering product answering itself in 13, and by a different mapped product in 3. The estimate survives two stricter definitions of the edge, a specificity control against PRs that already carry public discussion, an E-value of 2.27, and a within-repository shuffle test. One before-the-fact control is not centred on zero, and we report its estimate rather than treating it as a pass. All later-state analyses are explicitly observational; the paper does not call an exact edge a resolution or a causal effect.

The paper fits the special issue's themes of human-agent collaboration, mining agent-generated artifacts, multi-agent coordination, and review dynamics. It does not claim the first study of AI-to-AI review, developer response, or reviewer sequences. Its contribution is a stricter evidence ladder that separates participation from a public connection and from ownership transfer, together with a reusable falsification check: shuffling the order of events inside one pull request reproduces apparent product persistence almost exactly, so order-based coordination claims need a shuffled baseline rather than a fixed one.

The reproducibility bundle pins data and time boundaries, stores PR-grain cohorts, uses repository-aware uncertainty, runs leave-product-pair and fixed-effect sensitivities, quantifies how much unmeasured structure would be needed to remove the headline result, and records rejected claims as falsification results. Online Resource 1 contains the full data contracts, joins, estimates, robustness checks, structural-overlap gate, and experiment disposition ledger. The public artifact will be available at [ARTIFACT DOI].

[KEEP EXACTLY ONE OF THE FOLLOWING AFTER AUTHOR CONFIRMATION]

This manuscript is original and is not an extension of a conference paper.

OR

This manuscript extends [FULL CONFERENCE CITATION]. The journal paper adds [NEW DATA / METHODS / RESULTS], and the overlap is [CLEAR DESCRIPTION]. These additions provide the significant new contribution described in the manuscript introduction.

[AUTHOR CONFIRMATION REQUIRED: All authors have approved the manuscript and Online Resource 1. The work has not been published and is not under review or submitted elsewhere.]

Thank you for your consideration.

Sincerely,

[CONFIRMED CORRESPONDING-AUTHOR NAME]  
[Department and institution]  
[City, country]  
[Active email]

On behalf of Huynh Trung Kiet, Tran Chi Nguyen, Pham Phu Hoa, and Nguyen Lam Phu Quy
