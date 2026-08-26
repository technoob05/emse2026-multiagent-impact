# Frontier novelty audit: public cross-product review topology and review overlap

**Audit date:** 2026-08-26 (Asia/Bangkok)  
**Evidence boundary:** targeted current-frontier check of primary paper/preprint
pages through the audit date. This is a novelty-collision audit, not an
exhaustive systematic review.  
**Manuscript audited:** `paper/manuscript/main.tex` (read only).  
**Dataset artifact audited:** the frozen structural population under
`outputs/review_collision/`.

## Headline verdict

The broad novelty space is occupied. It is not safe to claim the first study of
AI-to-AI code review, multiple-agent review sequences, developer response,
human involvement, handoff, repository memory, agent disagreement, or
multi-agent coordination measurement.

The current paper still has a defensible narrow contribution:

> It reconstructs an event-level **public ownership topology** after one exact
> heterogeneous-product review trigger, using GitHub parent-comment and review
> batch identifiers to separate an addressed edge, rapid fan-out, the next
> visible owner, and a later public state.

This is a combination and measurement claim, not a safe “first.” The proposed
same-locus review study has high question-level novelty, but it is **not yet a
result**: 167 structural overlaps are audit-ready, while semantic relation is
unknown and one product pair supplies 65.3% of the population. The product-pair
generality gate therefore fails before coding begins.

The exact-edge update reached the same boundary from a second direction. A full
pinned SWE-Review-Chat scan found no disjoint landmark cohort after applying the
same product, parent, and AIDev-overlap rules. CodAGE's released cross-product
cohort agrees closely on product-pair attribution and trigger time where PRs
overlap, but it is not independent outcome evidence. The resulting novelty is
the strict topology and its falsifiable data contract, not extra scale or an
external causal claim.

## Claim-collision matrix

| Primary work and date | What it establishes | Collision with the current story | Remaining defensible gap |
|---|---|---|---|
| [Selvanayagam & Ghaleb, *AI-to-AI Code Reviews of GitHub Pull Requests*](https://arxiv.org/abs/2608.21311), submitted 2026-08-21; ESEM 2026 accepted | 248,641 AI-attributed PRs with AI review, including 45,269 cross-product-reviewed PRs; composition, volume, and latency | Occupies AI-to-AI/cross-product prevalence and rapid-latency territory. A broad closed-loop or first cross-product-review claim is unavailable. | What happens after one exact trigger: exact-parent response, de-batched continuation, next public owner, and later state. |
| [Zhong et al., *From Human-Centric to Agentic Code Review*](https://arxiv.org/abs/2607.13196), 2026-07-14 | Models human/LLM/agent review interaction sequences over 1.02M reviewed PRs; multiple-agent patterns are associated with faster decisions but not better quality | Occupies broad sequence, multi-agent participation, efficiency, and quality comparisons. | Product-aware event anchoring and exact response ownership after one heterogeneous trigger. |
| [Qiu & Gill, *Adversarial Review: Structured Disagreement for Grounded Agentic Code Review*](https://arxiv.org/abs/2608.18167), 2026-08-16 | Designed reviewer/critic protocol; identifies false consensus and tests structured disagreement | Occupies the designed-system claim that disagreement among reviewer agents matters. | Field evidence on whether independent products at the same public code locus repeat, complement, or contradict one another. This requires human semantic coding. |
| [Zhang, *RepoReviewer*](https://arxiv.org/abs/2603.16107), 2026-03-17 | Multi-agent repository-review architecture motivated partly by duplication and weak prioritization | Occupies “multi-agent architecture avoids review duplication” as a system-design motivation. It does not benchmark semantic duplication in public PRs. | A frozen field cohort of heterogeneous products inspecting the exact same original commit/path/position, followed by dual coding. |
| [Destefanis & Aste, *When Agents Coordinate*](https://arxiv.org/abs/2608.16801), 2026-08-17 | Temporal message/file networks in 1,902 controlled runs plus sealed replications; early introduction bursts and file-mediated coordination | Occupies explicit multi-agent coordination-network measurement and burst-like communication in controlled systems. | Public GitHub field traces across independent products and user accounts, where hidden messages and plans are unavailable. |
| [Cynthia et al., *Understanding Developer Responses to Agent-Generated Code Review Comments*](https://arxiv.org/abs/2607.21997), 2026-07-24 | 54,791 agent comments; response/resolution, developer roles, unresolved patterns, and content predictors | Occupies large-scale developer response and resolution. | Actor-product boundary plus exact response edge and next owner. Do not claim the first response or resolution study. |
| [Lin et al., *Is Agentic Code Review Helpful?*](https://arxiv.org/abs/2607.03316), 2026-07-03 | 31,073 CodeRabbit review-feedback pairs; acceptance, discussion, rejection, and invalid/redundant feedback | Occupies agent-review usefulness, rejection, and redundancy within a single-product case. | Cross-product same-snapshot/same-locus semantic relation and product-aware handoff topology. |
| [Zhong et al., *Human-AI Synergy in Agentic Code Review*](https://arxiv.org/abs/2603.15911), 2026-03-16 | 278,790 conversations; human/agent feedback differences, discussion rounds, suggestion adoption, and downstream code characteristics | Occupies broad human-AI synergy and the claim that human oversight remains important. | Which public account/product takes the next step specifically after a cross-product trigger. |
| [KC & Budathoki, *Handoff Debt*](https://arxiv.org/abs/2606.02875), 2026-06-01 | Controlled interrupted-task takeovers; context-bearing handoffs reduce successor events and tokens | Occupies agent handoff cost and context transfer in controlled tasks. | Field-visible handoff edges and owners. Public GitHub data cannot measure rediscovery cost, prompts, or private context. |
| [Watanabe et al., *How AI Coding Agents Communicate*](https://arxiv.org/abs/2602.17084), 2026-02-19 | PR-description characteristics and human review response across five agents | Occupies general agent communication style and human response. | Post-review, cross-product trigger-response topology rather than PR-description effects. |
| [Wang et al., *SWE-Review*](https://arxiv.org/abs/2607.06065), 2026-07-07 | Designed generate-review-revise loop and downstream issue-resolution usefulness | Occupies closed-loop agentic review as a designed and benchmarked workflow. | Whether public independent products expose an addressed loop at all; a later event alone is not a verified revision. |
| [Fatima et al., *On the Footprints of Reviewer Bots’ Feedback on Agentic Pull Requests*](https://arxiv.org/abs/2604.24450), 2026-04-27 | Reviewer-bot feedback type/quality/volume and PR outcomes on AIDev | Occupies bot feedback volume/quality and outcome associations. | Exact product pair, response edge, and same-locus relation. |
| [Nachuma & Zibran, *When AI Teammates Meet Code Review*](https://arxiv.org/abs/2602.19441), 2026-02-23 | Review-time collaboration signals and integration outcomes on AIDev | Occupies general collaboration-signal/merge associations and actionable-loop narratives. | Exact trigger anchoring, de-batching, first owner, and explicit falsification of unrelated follow-up. |
| [Khemissi et al., *Humans Integrate, Agents Fix*](https://arxiv.org/abs/2604.04059), 2026-04-05 | Human-to-agent and agent-to-agent cross-PR references; intent taxonomy and workflow time | Occupies meta-collaboration and cross-PR coordination. | Within-PR review-response topology at one exact trigger. |
| [Grynets et al., *Specification Portability Across LLM Development Agents*](https://arxiv.org/abs/2608.21208), 2026-08-21 | Controlled cross-agent specification transfer shows agent-dependent compatibility loss | Occupies broad heterogeneous-agent compatibility as a controlled effect. | Public review overlap may show a field coordination signature, but product-pair differences cannot be called interoperability effects. |
| [Gao et al., *SWE-MeM*](https://arxiv.org/abs/2606.28434), 2026-06-26 | Adaptive memory management for long-horizon coding agents | Occupies coding-agent memory as an internal system mechanism. | Prior public repository-review history carried by a user account is observable history, not proof of memory retrieval or transfer. |

## Audit of the manuscript's present novelty language

### Defensible

- The manuscript explicitly says it does **not** claim the first cross-product
  review map, developer-response study, or handoff study.
- “Event-anchored public topology” is a defensible contribution label when it is
  tied to exact parent ids, de-batched review ids, burst sensitivity, and a stated
  observation window.
- “User-account event” and “prior public review history” respect the available
  evidence better than “human reasoning” or “repository memory.”
- The threats section correctly prevents semantic words such as duplication,
  contradiction, repair, and resolution before audit.

### Needs caution in the next revision

- “Our novelty starts at one such event” is acceptable only as a scoped
  contribution statement. It should not become “the first event-level study.”
- “Public coordination” must remain a defined trace construct. It cannot imply
  vendor-side communication, a shared plan, or autonomy.
- “User accounts form the main visible bridge” is descriptive. It must not become
  “humans cause better outcomes.”
- Prior repository-review history must not be renamed “repository memory” unless
  memory access or transfer is directly observed.
- A same-locus pair is a **structural overlap**, not a collision, duplicate,
  complement, disagreement, or false consensus until dual coding passes its
  reliability and clarity gates.

## Safe automated extension before semantic coding

The reproducible extension is in
`outputs/novelty_collision_extension/`. It uses no semantic model, assigns no
labels, and edits no manuscript file.

### Structural support

- 886 PRs have top-level inline comments from at least two exactly mapped
  reviewer products.
- 159/886 PRs (17.95%) contain at least one structural overlap at the same
  `original_commit_id + path + original_position`.
- These 159 PRs yield 167 canonical loci across 98 repositories and eight
  product pairs. Each coder packet contains all 167 loci.
- 154/167 loci contain exactly two source comments; one PR contributes at most
  three canonical loci.

### Timing and sensitivity

- The median gap between the first product and the first different product at
  the same locus is 1.37 minutes.
- 145/167 (86.83%) occur within five minutes; a repository-cluster bootstrap
  gives a descriptive 95% interval of 80.86%--92.57%.
- The short-gap pattern remains 85.71% in the 133-locus open-PR sensitivity and
  82.76% after removing the dominant product pair.
- This is compatible with rapid parallel fan-out. Timing cannot show whether the
  second product read, understood, or responded to the first.

### Exact-format checks

- All 167 pairs have exactly matching normalized diff context, as expected from
  the strict locus key.
- Zero pairs have exactly identical normalized comment bodies. This rules out
  only literal text duplication, not semantic redundancy.
- A suggestion block appears in exactly one of the two comments at 83 loci, in
  both at one locus, and in neither at 83 loci. This is a format observation,
  not evidence of quality or complementarity.

### Decisive falsification gate

The `Copilot + OpenAI_Codex` pair contributes 109/167 loci (65.27%). The frozen
gate requires no repository or product pair to supply more than half. Repository
concentration passes (largest repository: 9/167, 5.39%), but the product-pair
gate fails. Therefore:

1. do not make a product-general semantic headline;
2. report the dominant pair explicitly;
3. treat non-dominant pairs as a sensitivity set, not a league table; and
4. require dual coding of the complete population before deciding whether this
   becomes an RQ, a bounded case study, or a null feasibility result.

## One recommended novelty sentence

> We reconstruct, from public GitHub identifiers, whether one cross-product
> review event becomes an addressed edge, a next visible owner, or rapid fan-out;
> this event-level field topology complements prior prevalence, broad-sequence,
> developer-response, and designed multi-agent protocol studies.

## Unsafe “first” claims to reject

- “the first study of AI-to-AI code review”;
- “the first empirical study of cross-product agent review”;
- “the first study of multiple AI agents in code review”;
- “the first study of developer or human response to agent reviews”;
- “the first study showing that humans remain important”;
- “the first handoff or response-ownership study”;
- “the first measurement of multi-agent coordination”;
- “the first study of agent disagreement or false consensus”;
- “the first study of duplicate/redundant AI review comments”;
- “the first study of repository memory in coding agents”;
- “the first evidence that cross-product review causes coordination, fixes, or
  merge”;
- “the first product interoperability effect in public repositories.”

The safe formulation is contribution-based (“we contribute an event-anchored,
product-aware public topology”), not priority-based (“we are the first”).
