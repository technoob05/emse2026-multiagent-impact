# Event-chain de-batching audit

## Decision

The current manuscript is **not safe to submit**. Its response tables, figures, and models were produced before two event-chain fixes:

1. A direct reply must point to the **exact first inline trigger**, not only to another cross-product comment on the same PR.
2. A later review must belong to a **new review batch**. The submitted review that contains the trigger comment is not a later response.

The corrected code is newer than all current response outputs. The manuscript must therefore treat every response-derived result as stale until the full pipeline is rerun.

## What changes in the descriptive result

Read-only recomputation with the corrected event-chain code gives the following diagnostic values. These values are audit evidence, not final manuscript values; the official artifacts still need regeneration.

| Measure (8,608 PRs with a full 7-day window) | Current paper | Corrected diagnostic | Change |
|---|---:|---:|---:|
| Any observable activity | 74.23% | 64.51% | -9.72 pp |
| New review round | 63.30% | 49.73% | -13.57 pp |
| Direct reply to the exact trigger | 11.98% | 8.48% | -3.50 pp |
| Later PR comment | 37.08% | 37.08% | no change |
| Force-push | 12.40% | 12.40% | no change |
| Merge within 7 days | 72.84% | 72.84% | no change |
| Direct-reply events | 3,361 | 875 | -2,486 |

The largest error is not a small rounding issue. A review submission was often counted as a response to one of its own inline comments. Unrelated inline replies were also accepted. Together, these rules made the workflow look more conversational and more agent-led than the event chain supports.

## Claims that must be withdrawn or replaced

| Manuscript location | Current claim | Required action | B1-level replacement |
|---|---|---|---|
| Abstract | 74% show activity; 12% show a direct reply | Replace both values after the official rerun | “About two thirds show a later visible action, but fewer than one in ten reply to the exact first comment.” |
| Abstract | User accounts write 81% of direct replies | Withdraw the number pending regenerated actor tables | “User accounts write most exact direct replies.” The corrected role diagnostic is about 88%, but it is not yet an official result. |
| Abstract | Human-mediated and force-push paths have about a +16 pp link to merge | Withdraw all effect sizes and confidence intervals | Do not state an outcome link until the corrected landmark models are rerun. |
| Introduction, contributions | Human mediation is more strongly linked to integration than agent-only continuation | Mark as pending, not a finding | “We study who takes the next visible action and how the PR escalates.” |
| Methods, response construction | A direct child points to a cross-product parent on the same PR | Tighten the definition | “A direct reply has `parent_id` equal to the event ID of the exact first trigger.” |
| Methods, later review | Any later review submission counts | Correct the definition | “A later review must have a different `pull_request_review_id` from the trigger’s review batch.” |
| RQ1 text and Figure 1 | 74%, 63%, and 12%; current response-channel plot | Replace and rebuild | Use 64.51%, 49.73%, and 8.48% only after the official rerun reproduces them. Rebuild both panels from the corrected parquet. |
| RQ1 interpretation | The feedback often starts a visible two-message conversation | Withdraw | “A direct two-message exchange is uncommon. Follow-up is more often visible through another channel.” |
| RQ2 | 3,361 direct-reply events | Replace | Corrected diagnostic: 875 exact direct-reply events. |
| RQ2 | 81% user accounts and 19% bots | Withdraw pending regenerated user-type table | Safer: “Human-role accounts dominate exact direct replies.” Corrected role counts are 773 of 875 events for author or other-human accounts. |
| RQ2 | 274 strict bot-to-bot events on 126 PRs | Withdraw | Recompute the strict bot-to-bot subset from exact replies only. |
| RQ2 | The triggering reviewer often runs another review | Withdraw | “After removing same-batch echoes, later review is distributed across actors. Other humans lead by PR count and event count.” |
| RQ2 interpretation | Agents produce feedback and repeated review, while people connect it to decisions | Reword | “An agent can open the feedback path, but visible ownership often passes to an author account or another human.” |
| RQ3 cohort table | 468 no-response, 425 agent-only, and 115 other-activity PRs | Replace all group counts | Corrected diagnostic: 659 no observed response, 185 agent-only continuation, and 164 other activity. Human-mediated remains 529; visible code movement remains 196. |
| RQ3 models | Human +15.81 pp; visible movement +15.77 pp; agent-only +6.65 pp; other +10.81 pp | Withdraw all coefficients and intervals | No adjusted claim until the corrected exposure groups and repository fixed-effect model are rerun. |
| RQ3 matched analysis | 668 pairs and all four reported differences | Withdraw the complete matched result | Rebuild treatment/exposure fields, rematch, and report only the corrected analysis. |
| Discussion | Reviewer apps often continue the review | Withdraw | “The earlier reviewer-continuation result was inflated by same-batch review events.” |
| Discussion | People close the loop | Reword because semantic task closure was not audited | “User accounts often take the next visible action.” |
| Discussion and implications | Inline feedback is linked to more replies or force-pushes; human-visible response is linked to integration | Withdraw causal-sounding and stale associations | Describe channels and ownership first. Add outcome associations only after corrected models pass validation. |
| Novelty boundary | Early loop shape is linked to later state | Mark as untested after correction | “The paper adds an ownership view: who takes over after one agent comments on another agent’s PR.” |
| Conclusion | Human-mediated loops are more strongly linked to later integration | Withdraw pending rerun | “Direct dialogue is rare, and visible follow-up often changes owner or channel.” |

The headline cohort sizes (8,622 cross-product-feedback PRs and 8,608 full-window PRs) appear unchanged because the fixes affect responses, not trigger selection. They must still be reproduced by the official run before reuse. PR-comment, force-push, and merge rates also remain unchanged in the diagnostic recomputation, but their tables and figures should be regenerated for consistent provenance.

## Replacement paper story: ownership and escalation

### Suggested title

**Who Takes Over After Cross-Agent Feedback? Ownership and Escalation in Agent-Authored Pull Requests**

### Three RQs

- **RQ1 — Follow-up:** What exact visible actions follow the first cross-product feedback event?
- **RQ2 — Ownership:** Who takes the next action: the author, the first reviewer, another agent, or another human?
- **RQ3 — Escalation:** Which verified paths—exact reply, new review round, PR comment, force-push, or no observed response—are associated with later PR state?

### Simple B1 story

Cross-agent feedback does not usually become a direct conversation. After exact parent matching and review-batch removal, fewer than one in ten PRs contain a direct reply to the first trigger. About half receive a genuinely new review round. The actor also changes: other humans lead later review activity, while author and other-human accounts write most exact replies. The useful unit is therefore not a “closed loop.” It is an **ownership change** or an **escalation path**. This framing tells tool builders where agent-to-agent coordination stops being visible and where people take over.

The outcome part must remain secondary. It should report adjusted associations only if the corrected models are stable. If they are not stable, RQ3 should remain descriptive: where the action moves next and where the trace ends.

## Falsification and release gates

1. Rerun the response-chain pipeline, landmark models, matched analysis, all tables, and all figures from the corrected code.
2. Store a code hash and generation timestamp with each final artifact; reject any artifact older than the event-chain code.
3. Confirm that every direct reply has `parent_id = trigger_event_id` and that every new review has `response_review_id != trigger_review_id`.
4. Manually audit samples from exact replies, new review rounds, and agent-only paths. Do not use “same task,” “corrective loop,” “recovery,” or “closed loop” without semantic validation.
5. Recompute strict bot-to-bot counts and actor shares. Report both event-level and PR-level denominators.
6. Rerun the landmark and matching diagnostics. If the direction, interval, or overlap is unstable, remove the outcome claim and keep the ownership/escalation paper descriptive.

## Required manuscript threat statement

GitHub records comments, reviews, and branch events as separate objects. Time order alone does not prove that one event answers another. A submitted review may contain the trigger comment and is not a later response. A reply to another inline comment on the same PR is also not a reply to the trigger. We prevent these errors with exact parent matching and review-batch IDs, but observable actions still do not prove shared task intent or semantic resolution.
