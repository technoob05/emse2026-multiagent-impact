# Cross-product feedback paper pivot

## Decision

The paper now studies **who closes the visible loop after cross-product agent feedback**. It does not claim novelty for counting AI-to-AI review. A paper posted on 21 August 2026 already covers prevalence, author-reviewer composition, review output, and latency.

## Three RQs

1. After the first cross-product feedback event, which visible actions follow, and through which channel?
2. Who produces the visible response: a user account, the author-agent product, the reviewer product, or other automation?
3. For PRs still open at a 48-hour landmark, how are early loop shapes linked to later merge?

## Current insight

- The strict event map finds 8,622 PRs with cross-product feedback in AIDev-pop.
- 8,608 have a complete seven-day response window; 74.2% have later visible activity.
- Later review appears on 63.3%, later PR comments on 37.1%, force-push on 12.4%, and direct thread reply on 12.0%. Channels overlap.
- User accounts produce 2,712 of 3,361 direct-reply events (80.7%). The visible loop is therefore often hybrid rather than autonomous bot-to-bot dialogue.
- The strict bot-to-bot mechanism set is much smaller: 274 reply events on 126 PRs.
- In the 48-hour landmark cohort, repository fixed-effects estimates relative to no observed response are +15.8 percentage points for human mediation (95% CI 5.0 to 26.6), +15.8 points for visible force-push activity (2.7 to 28.9), and +6.6 points for agent-only continuation (-1.9 to 15.2).
- In 668 exact repository/author/source/month pairs, cross-product first feedback is followed by +4.8 points more visible force-push activity and +6.4 points more seven-day merge than same-product first feedback. These are associations, not causal effects.

## Story in plain language

An AI review does not close the work. The next step often belongs to a person. Reviewer apps tend to run more reviews, while user accounts write most direct replies. Human mediation is linked to later integration more clearly than agent-only continuation.

## Claims that remain unsafe

- Cross-product feedback caused a merge.
- A force-push fixed the review point.
- The mapped apps formed an autonomous multi-agent team.
- Missing review or comment rows mean no event occurred.
- Raw differences between author-agent products are behavioral differences; rich-table coverage is highly uneven.

## Submission gates still open

1. Blinded human audit of trigger semantics and response-topic linkage.
2. Human validation of account-role mapping.
3. Leave-top-pair, leave-agent, leave-month, and leave-top-repository sensitivity.
4. Complete author affiliation, corresponding email, funding, conflicts, and contribution declarations.

The manuscript is a compiled working paper, not a final submission until these gates close.
