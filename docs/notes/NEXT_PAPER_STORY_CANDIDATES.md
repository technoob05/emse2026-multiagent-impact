# Recommended next EMSE paper story

## Decision

Choose the **cross-agent feedback-response loop** story. It is closer to directly observed multi-agent software work than the handoff, specialization, or adoption stories.

The positive insight is not simply that one agent comments on another agent's PR. That prevalence claim overlaps with recent ESEM work. The useful new question is: **after cross-brand agent feedback appears, which channel carries the response, who acts, and how does the loop reach an observable next state?**

Current status: strong descriptive feasibility, not yet a paper result. The construct and outcome gates below must pass before manuscript promotion.

## Proposed title

**Who Closes the Loop? Human and Agent Roles After Cross-Agent Feedback on Pull Requests**

Alternative: **Beyond Agent-to-Agent Review: Response Channels and Ownership in AI-Authored Pull Requests**

## One-sentence story

Cross-brand review is not a two-agent conversation: reviewer agents often continue the review, while author accounts and other humans provide many direct replies and force-pushes, forming a hybrid feedback-response loop whose structure can be observed and tested.

## Current empirical foothold

The new AIDev-pop exploration gives enough support to continue:

- 9,696 of 361,296 PRs have feedback from a recognized agent brand different from the author-agent brand.
- 8,898 have a complete seven-day post-trigger window.
- 71.1% have at least one timestamped observable response within seven days.
- The channels overlap: 10.4% have a direct inline reply, 60.5% a later review, 35.4% a later PR comment, and 10.8% a force-push.
- Direct inline replies most often come from the author account (688 PRs), then other humans (288). Later reviews often come from the triggering reviewer brand (3,142), other humans (2,186), the author account (1,018), and the author-agent brand (737).
- 64.9% merge within seven days after the first cross-agent trigger. This is descriptive timing, **not** a recovery or causal effect.

Counts by actor or channel overlap and must not be added. A later event may also concern another topic. These issues define the validation work, rather than being small footnotes.

## Three research questions

1. **RQ1 -- Response pathways:** After the first cross-brand agent feedback event on an agent-authored PR, how often does a timestamped response appear, how fast, and through which channel: direct thread reply, later review, PR comment, or force-push?
2. **RQ2 -- Response ownership:** Who performs the first and later responses: the author account, author-agent brand, triggering reviewer brand, another agent, another human, or another bot?
3. **RQ3 -- Loop closure:** Among comparable PRs that remain open at a fixed landmark, how are validated loop shapes linked to later merge or closure, and which patterns remain stable within repository, author-agent, reviewer-agent, trigger-channel, and calendar contexts?

Use “linked to” and “associated with.” Do not use “feedback caused correction” or “agent collaboration improved merging.”

## Insight-first result structure

### 1. Most visible responses are not direct agent dialogue

Lead with the 71.1% response rate, then immediately split it by channel. A direct inline reply is visible on only 10.4% of PRs, while later reviews are much more common. Thus, “a response happened” is not the same as “the author agent answered the reviewer agent.”

### 2. Ownership changes with the channel

Show a simple division of labor. Author accounts dominate direct replies and force-pushes. The triggering reviewer brand dominates later review rounds. Humans also appear often in replies, reviews, and comments. This is a hybrid human-agent loop, not proof that two agents share memory or coordinate autonomously.

### 3. Loop shape, not agent pair, is the actionable unit

Only after temporal and semantic validation, compare patterns such as:

- author action: author reply or author force-push;
- reviewer continuation: triggering reviewer sends another review;
- human mediation: another human replies, reviews, or comments;
- agent continuation: the author agent or another agent responds; and
- no timestamped response.

The practical question is which loops remain active and reach merge or explicit closure, not which brand “wins.”

## Three contributions

1. A time-ordered event design that links the first cross-brand feedback event to later observable actions without using future events to define exposure.
2. A channel-by-actor taxonomy that separates agent continuation, human mediation, author action, reviewer continuation, and silence.
3. A fixed-landmark analysis of loop shape and later PR state, with explicit construct audits and pair/repository influence tests.

## Exact falsification gates

### Gate A -- Is the trigger real feedback?

Draw at least 500 trigger events, stratified by source, author-reviewer pair, month, and repository. Two human coders, blinded to outcome, label: actionable feedback, non-actionable information, boilerplate/status output, or unclear.

Pass only if:

- exact brand attribution precision is at least 95%;
- at least 70% of sampled triggers are actionable or clearly evaluative feedback;
- Cohen's kappa for actionable versus other is at least 0.70; and
- no major trigger channel with at least 10% of the cohort has actionable-feedback precision below 60%.

If this fails, do not call the events review or corrective feedback. Reframe as cross-brand interaction, or stop.

### Gate B -- Does the response belong to the trigger?

The current “later review/comment” rule is temporal, not semantic. Audit at least 400 trigger-response pairs, oversampling later reviews and PR comments. Direct replies must point to the selected trigger thread, not merely to any later cross-agent inline comment.

Pass only if:

- at least 70% of sampled responses are related to the trigger topic;
- coder kappa for related versus unrelated is at least 0.70;
- the related-response share is at least 60% in every headline channel; and
- removing same-timestamp ties and duplicated/batched events changes each headline rate by less than 3 percentage points.

If this fails, use “subsequent PR activity,” not “response loop” or “correction.”

### Gate C -- Is actor ownership reliable?

Audit account aliases and role assignment on at least 300 response events, stratified by role and channel.

Pass only if:

- at least 95% of audited recognized-agent accounts map to the correct brand;
- at least 90% of headline response events receive a non-unknown actor role;
- author-account matching precision is at least 95%; and
- the ordering of the two largest actor roles in each headline channel survives removal of the top ten repositories.

If this fails, keep channel results but withdraw the ownership claim.

### Gate D -- Does the pattern generalize beyond dominant pairs?

The current author-reviewer matrix is concentrated: OpenAI Codex authored/Copilot reviewed is the largest pair, and the top three directed pairs contribute over half of pair-tagged PR counts.

Pass only if:

- no single repository contributes more than 10% of unique PRs after cohort construction;
- removing the largest directed pair changes the overall observable-response rate by less than 5 points;
- at least five directed pairs with 200 or more PRs show the same qualitative channel/ownership pattern; and
- leave-one-agent, leave-one-month, and leave-top-ten-repository analyses do not reverse the main ordering.

If this fails, make the paper a named-pair case study rather than an ecosystem claim.

### Gate E -- Is RQ3 time-safe and not an immortal-time comparison?

Use a trigger-relative landmark. A recommended primary design is:

1. take the first validated cross-brand feedback event at time zero;
2. classify responses observed in the next 48 hours;
3. include only PRs still open and unmerged at 48 hours; and
4. observe merge or closure from hour 48 through day 30 after the trigger.

Use one PR once. Fit within-repository models with author agent, reviewer agent, trigger source, calendar month, and pre-trigger history. Do not control for final change size because the file tables have no time-valid snapshot at the trigger.

Pass the outcome headline only if:

- every PR has a complete 30-day post-trigger window;
- at least 500 PRs remain in each headline loop category, or categories are merged before looking at outcomes;
- the adjusted loop-shape estimate has the same sign under repository fixed effects, repository clustering, and a time-to-event model;
- its 95% interval excludes zero in the primary specification;
- the result survives exclusion of PRs with feedback in the first ten minutes and exclusion of repeated automated review batches; and
- a negative-control outcome measured before the trigger shows no association.

If this fails, retain RQ1 and RQ2 as a descriptive coordination-measurement paper and remove any claim about closure benefit.

### Gate F -- Is “corrective” justified?

Commits and file-detail rows do not contain usable timestamps, and ordinary `committed` timeline events cannot order code changes around the trigger. A force-push is observable, but it does not prove that feedback was addressed.

Use “corrective loop” only if a separate human audit of at least 300 complete chains finds that at least 60% contain a response that addresses the feedback, with kappa at least 0.70. Otherwise the safe term is **feedback-response loop**.

## Required data tables

### Required for the main study

| Table | Required fields/use |
|---|---|
| `pull_request.parquet` | PR ID, repository, author agent, author account, created/closed/merged times; backbone, censoring, and outcomes |
| `pr_reviews.parquet` | PR ID, review ID, reviewer account/type, state, submitted time, body; trigger and later-review events |
| `pr_review_comments.parquet` | Review ID, comment ID, parent-reply ID, account/type, path, created time, body; inline triggers and direct threaded replies |
| `pr_comments.parquet` | PR ID, account/type, created time, body; PR-level feedback and later discussion |
| `pr_timeline.parquet` | PR ID, event, actor, created time; timestamped force-push and explicit lifecycle events |
| `repository.parquet` | Repository ID, language, fork status, stars/forks; context and influence checks |

The review-comment join is two-step: `pr_review_comments.pull_request_review_id -> pr_reviews.pull_request_review_id -> pr_reviews.pr_id`.

### Secondary only

| Table | Safe role |
|---|---|
| `pr_commit_details.parquet` | Final changed paths and size as descriptive context only; not proof of a post-feedback edit |
| `pr_commits.parquet` | Commit author/message for qualitative audit; no timestamped correction claim |
| `pr_task_type.parquet` | Small labelled subset for sensitivity only, not primary adjustment |

Do not join rich tables to `all_pull_request.parquet`; they are built around the 361,296-row AIDev-pop `pull_request` backbone.

## Two main figures and two tables

### Figure 1 -- A hybrid feedback-response loop

A flow diagram with observed counts: first cross-brand trigger -> four overlapping channels -> actor roles. Use distinct colors for human, author account, author agent, triggering reviewer agent, and other automation. State that channels overlap.

### Figure 2 -- Which loop shapes reach a later PR state?

A 48-hour landmark forest plot of adjusted day-30 merge/closure differences for pre-defined mutually exclusive loop shapes. Show only after Gate E passes. Otherwise replace it with channel-specific response-time distributions.

### Table 1 -- Construct, coverage, and audit quality

Report all denominators, source coverage, full-follow-up count, alias audit precision, semantic-feedback precision, response-link precision, coder agreement, ties, duplicates, and repository/pair concentration.

### Table 2 -- Actor ownership by channel

For each response channel, report unique PRs, first-response actor, any-response actor, median time, and repository-clustered intervals. Keep pair-specific rates in the supplement.

## Novelty boundary

Do not claim the first observation or prevalence study of cross-agent review; the August 2026 ESEM work must be added and verified in the evidence map. The residual novelty is narrower and stronger:

- time-ordered post-feedback chains;
- response ownership across humans and agent brands;
- channel-specific loop structure; and
- a landmark-safe link between validated loop shape and later PR state.

This paper studies public workflow traces. It does not show shared memory, private messages, intentional orchestration, or autonomous agent-agent collaboration.

## Claims to remove from the current manuscript

- exact-file handoff scarcity and all handoff-prevalence claims;
- failed-task “recovery” and agent-switch benefit claims;
- the adaptation-gap story;
- task specialization, portfolio expansion, or optimal routing claims;
- matched-adoption activity growth as a causal effect; and
- generic “co-presence is not coordination” as the headline.

The earlier failed constructs can appear in a short motivation paragraph: repository co-presence and sequential file overlap are too weak, so this paper uses direct feedback events and timestamped responses.

## Final go/no-go decision

This is the best current candidate because the interaction and response actors are directly observed. Promote it to the manuscript only after Gates A--D pass. Promote the outcome/impact part only after Gate E passes. Use “corrective” only after Gate F passes.

If Gates A--D pass but Gate E fails, the paper can still make a useful EMSE contribution about **how hybrid human-agent feedback loops operate**. If the semantic-link gate fails, stop this story rather than turning later activity into coordination.
