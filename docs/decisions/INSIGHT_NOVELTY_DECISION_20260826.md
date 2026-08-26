# Insight and novelty decision

Date: 2026-08-26  
Target: EMSE Special Issue, “Agentic Software Engineering: The Rise of AI Teammates”  
Decision: build the current paper around **public coordination topology**, not a product ranking or a causal merge claim.

## One-line story

> Two agent products on one PR show participation, not collaboration; a visible handoff needs an addressed edge, a next owner, and an observable later state.

## Why this is a defensible gap

The broad topics are already occupied:

| Frontier work | What it already covers | What remains for this paper |
|---|---|---|
| [AI-to-AI Code Reviews of GitHub Pull Requests](https://arxiv.org/abs/2608.21311) | Cross- versus same-product prevalence, output, and latency | The exact public topology after one trigger |
| [From Human-Centric to Agentic Code Review](https://arxiv.org/abs/2607.13196) | Broad human/LLM/agent review sequences and quality | Product-aware addressed edges and next-owner changes |
| [Developer Responses to Agent-Generated Code Review Comments](https://arxiv.org/abs/2607.21997) | Developer response and comment actionability | The heterogeneous-agent boundary and repository-history bridge |
| [When Agents Coordinate](https://arxiv.org/abs/2608.16801) | Temporal message/file networks inside controlled multi-agent runs | Natural public repository traces with no private network access |
| [SWE-Review](https://arxiv.org/abs/2607.06065) | A designed generate--review--revise loop | Whether such a connected loop is visible in the wild |
| [Handoff Debt](https://arxiv.org/abs/2606.02875) | Rediscovery cost when agents take over benchmark tasks | Observable ownership at a cross-product review boundary |

The novelty is therefore a **combination claim**, not a “first handoff study” claim:

> We reconstruct the public ownership topology after one exact heterogeneous-product feedback event using review de-batching, exact reply edges, rapid-burst sensitivity, same-author boundary matching, user-account repository history, and a fixed later-state landmark.

## Final three-RQ story

1. **Participation or handoff?** After review de-batching and rapid-burst collapse, how much cross-product activity forms a sequential public edge, and who appears next?
2. **Who bridges the boundary?** How visible is follow-up across a product boundary, and do first user-account mediators carry earlier public review history from the repository?
3. **What follows a hybrid relay?** Among PRs still open at 48 hours, how are automation-only and automation-then-user routes linked to later merge?

## Headline insights that survived falsification

| Insight | Evidence | Paper-safe meaning | Action for builders |
|---|---|---|---|
| Presence rarely becomes an exact different-product edge | 74/8,608 PRs; 74/4,824 inline-eligible PRs | Product co-presence is not connected public dialogue | Store exact acknowledgement links, not only reviewer counts |
| Rapid fan-out inflates mapped-product ownership | Five-minute threshold changes mapped-first from 15.2% to 10.7% of all PRs, a 29% relative drop | A short automation burst is not reliable evidence of a handoff | Group one automation run before assigning the next owner |
| The public product boundary is quieter | Same-author matched visibility: cross 68%, same 82%, difference -13.4 points; repository interval excludes zero | Cross-product feedback has less visible follow-up | Expose boundary status and route unacknowledged triggers |
| User accounts carry observable repository memory | 71% of 3,603 first user-account mediators reviewed another PR in the repository before the trigger | The visible bridge is usually repository-experienced, not a newcomer | Show relevant review history when assigning ownership |
| The hybrid relay marks a different later state | Automation-then-user versus automation-only: +12.9 later-merge points after measured pre-trigger controls | Hybrid ownership is a workflow marker, not a causal treatment | Monitor transition to a named user-account owner |

## Attractive result that was rejected

The earlier phrase **“quieter but more action-oriented”** must not return. The apparent force-push and merge gains for cross-product feedback did not survive repository-cluster uncertainty and same-contributor checks. The stable result is lower public follow-up. There is no evidence that the missing conversation is replaced by more effective branch movement or integration.

## Highest-wow next extension: coverage or collision

A frozen, blinded audit packet now covers the full strict same-snapshot/same-locus population:

- 167 collision loci on 159 PRs and 98 repositories;
- 133 loci where both comments occur while the PR is open;
- 86.8% of product pairs at a locus arrive within five minutes;
- the largest repository supplies only 5.4%; but
- Copilot + OpenAI Codex supplies 65.3%, so product-pair generalization fails the pre-set 50% gate.

This packet can answer whether a second product repeats, complements, or contradicts the first. It cannot yet support any semantic claim. Two independent coders must complete all 167 rows, Cohen’s kappa must reach 0.70, unclear/boilerplate must remain at or below 30%, and each headline category needs at least 30 cases. Report a dominant-pair-excluded sensitivity even if all gates pass.

## Other next experiment

Dynamic escalation after repeated automation is feasible and genuinely multi-agent: estimate the next observed state after 1, 2, 3, and 4+ post-burst automation rounds using a multi-state risk set. Treat event count as time-varying; do not group PRs by their eventual number of rounds. This can motivate an acknowledgement/escalation policy without claiming that escalation causes merge.

## Venue fit and timing

The official call asks for human-agent collaboration, mining agent-generated artifacts, multi-agent coordination, and review dynamics. The paper fits all four through a real-world artifact-mining design. The special issue uses rolling review and has a final deadline of **September 28, 2026**: <https://emsejournal.github.io/special_issues/2026_SI_Agentic_SE.html>.
