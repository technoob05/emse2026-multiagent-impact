> **>>> BEFORE SENDING, REPLACE EVERY `[[ ... ]]` MARKER IN THIS LETTER. <<<**
> There are two, and the letter is not sendable while either remains: the
> submission date below, and the artifact DOI in the penultimate paragraph.
> Search this file for `[[` to find them. Everything else the manuscript
> settles is already filled in.

[[SUBMISSION DATE]]

Dear Guest Editors of the Special Issue on "Agentic Software Engineering: The Rise of AI Teammates,"

Please consider our manuscript, "Participation Is Not Collaboration: When One LLM Coding Agent Reviews Another on GitHub, a Person Answers," for publication as a Research Paper in Empirical Software Engineering.

**In plain terms.** When one AI coding tool writes a pull request and a different AI tool reviews it, it looks like two agents working together. We checked whether that is true. Using a large public set of GitHub pull requests, we followed each cross-tool review comment and asked what happened next. One tool almost never answers the other. Once we set aside the quick burst of automatic events, a person is usually the one who acts next, and that person has often reviewed code in the same project before. The one connection that goes together with a later merge is a direct reply to the review comment, and four times in five a person writes it. That is a link we observed, not proof of cause. Counting tools on a pull request does not measure teamwork.

The paper studies a basic measurement problem in agentic software engineering. When two agent products appear on one pull request, the trace looks multi-agent, but it may be a fast automation burst rather than a connected handoff. Using a pinned AIDev-7.6M revision, we reconstruct the public path after one cross-product review trigger: the exact parent edge, the de-batched review round, burst sensitivity, the next visible owner, earlier public repository-review history, and the later state after a fixed hour-48 check point.

Four results motivate the paper, one per research question. First, direct different-product dialogue is rare once the fast burst of events is set aside. Second, user accounts form the main visible bridge across the product boundary, and most of these accounts have earlier public review history in the repository. Third, an exact reply to the trigger is associated with more later integration after adjustment for measured pre-trigger context. Fourth, an observable property of the change interacts with who is reviewing: linking an issue in the pull request body leaves the answer rate flat within a product, 21.3% against 19.8%, but more than doubles it across a product boundary, 12.7% against 28.3%. That is a raw contrast of 17.1 percentage points, and 13.3 points when the comparison is held inside the same repository and the same month.

We report the scope of the third result rather than only its size. The outcome group is the 27% of cross-product inline-trigger PRs still open at hour 48, so it describes slower-moving PRs. The exposure is written by a user account in 105 of 128 events, by the triggering product answering itself in 13, and by a different mapped product in 3. The estimate survives two stricter definitions of the edge, a specificity control against PRs that already carry public discussion, an E-value of 2.27, and a within-repository shuffle test. One before-the-fact control is not centred on zero, and we report its estimate rather than treating it as a pass. We also state plainly that the hour-48 landmark measures the exposure inside the same window that decides cohort membership, and we bound that with a landmark-free whole-population estimate of 11.2 points and a sequential-landmark design in which the cohort gate closes before the exposure window opens. All later-state analyses are explicitly observational; the paper does not call an exact edge a resolution or a causal effect.

The paper fits the special issue's themes of human-agent collaboration, mining agent-generated artifacts, multi-agent coordination, and review dynamics. It does not claim the first study of AI-to-AI review, developer response, or reviewer sequences. Its contribution is a stricter evidence ladder that separates participation from a public connection and from ownership transfer, together with a reusable falsification check: shuffling the order of events inside one pull request reproduces apparent product persistence almost exactly, so order-based coordination claims need a shuffled baseline rather than a fixed one.

The reproducibility bundle pins data and time boundaries, stores PR-grain cohorts, uses repository-aware uncertainty, runs leave-product-pair and fixed-effect sensitivities, quantifies how much unmeasured structure would be needed to remove the headline result, and records rejected claims as falsification results. Online Resource 1 contains the full data contracts, joins, estimates, robustness checks, structural-overlap gate, and experiment disposition ledger. The public artifact will be available at [[ARTIFACT DOI]].

This manuscript is original and is not an extension of a conference paper.

[AUTHOR CONFIRMATION REQUIRED: All authors have approved the manuscript and Online Resource 1. The work has not been published and is not under review or submitted elsewhere.]

Thank you for your consideration.

Sincerely,

Duy Minh Dao Sy  
Faculty of Information Technology, Ho Chi Minh City University of Science (HCMUS), and Vietnam National University Ho Chi Minh City (VNU-HCM)  
Ho Chi Minh City, Vietnam  
23122041@student.hcmus.edu.vn

On behalf of Trung Kiet Huynh, Chi Nguyen Tran, Phu Hoa Pham, and Lam Phu Quy Nguyen
