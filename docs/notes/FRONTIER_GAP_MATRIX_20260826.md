# Frontier gap matrix: multi-agent code review and response ownership

> **Historical record.** This document was written when the study had three
> research questions. RQ4, on issue linkage across the product boundary, was
> added later. Read it as a record of a decision at the time, not as a
> description of the current paper.

**Scan date:** 2026-08-26 (Asia/Bangkok)  
**Scope:** targeted frontier scan, not an exhaustive systematic review. I checked
primary paper/preprint pages and the official MSR 2026, AIware 2026, and EMSE
special-issue pages. The purpose is novelty collision detection for the current
AIDev-7.6M study, not prevalence estimation over the literature.

## Bottom line

The broad claims are occupied. Recent work already studies AI-to-AI review
prevalence, developer response to agent comments, human/agent review sequences,
PR-lifecycle initiative and approval, suggestion adoption, explicit multi-agent
coordination traces, and cross-agent handoff/portability.

The defensible remaining gap is narrower and stronger:

> **An event-anchored, product-aware account of public coordination after one
> heterogeneous agent product gives feedback on another product's PR: the exact
> feedback edge, the first visible owner, the response channel, the presence of a
> user-account bridge, and whether the trace reaches semantic closure rather than
> merely showing later activity.**

This supports a simple conceptual distinction:

> **Two agent products on one PR show participation, not collaboration. A visible
> handoff needs an addressed feedback edge, a next owner, and an observable state
> change.**

That distinction is the best “wow” story in the current evidence. It is more
defensible than a brand ranking, a generic merge-prediction model, or a claim that
human mediation causes success.

## Closest-work gap matrix

| Closest primary work | Unit and data | Main empirical/design claim | Territory it already occupies | Defensible remaining gap |
|---|---|---|---|---|
| [Selvanayagam & Ghaleb, *AI-to-AI Code Reviews of GitHub Pull Requests* (2026)](https://arxiv.org/abs/2608.21311) | PR/review pairs in CodAGE; 248,641 AI-attributed reviewed PRs, including 45,269 cross-product-reviewed PRs | Cross-product review is growing but remains a minority; output and latency differ across configurations | AI-to-AI and cross-product **prevalence**, review volume, composition, and latency | What happens **after** the cross-product review: exact reply, next owner, human bridge, distinct review round, artifact movement, and closure |
| [Zhong et al., *From Human-Centric to Agentic Code Review* (2026)](https://arxiv.org/abs/2607.13196) | 1.02M reviewed PRs in 207 GitHub projects; review-era and interaction sequences | Agent-involved and multiple-agent sequences are associated with faster decisions, but not better review quality | Coarse human/LLM/agent **interaction sequences** and era-level efficiency/quality | Trigger-specific, product-aware handoff edges; first response owner; exact-parent replies; removal of the trigger review's own batch |
| [Zhong et al., *Human-AI Synergy in Agentic Code Review* (2026)](https://arxiv.org/abs/2603.15911) | 278,790 review conversations in 300 projects | Human and AI feedback differ; AI suggestions have lower adoption and adopted AI suggestions can increase complexity/size | Human-versus-AI feedback, discussion rounds, suggestion adoption, and code-quality change | Heterogeneous author-agent/reviewer-agent roles and who takes responsibility after a cross-product trigger |
| [Cynthia et al., *Understanding Developer Responses to Agent-Generated Code Review Comments* (2026)](https://arxiv.org/abs/2607.21997) | 54,791 comments from five agents in 342 Python repositories | Resolution varies by agent/comment type; core/peripheral developers differ; inline suggestions predict resolution | Large-scale **developer response and comment resolution** | Do not claim the first response study. Remaining gap: product-aware cross-agent trigger, actor/channel ownership, and human mediation between two agent products |
| [Lin et al., *Is Agentic Code Review Helpful?* (2026)](https://arxiv.org/abs/2607.03316) | 31,073 review-feedback pairs, 10,191 PRs, 239 repositories; CodeRabbit case | Agent comments are accepted, discussed, or rejected; rejection has learnable content patterns | Single-product feedback acceptance/rejection and prediction | Cross-product handoff topology and whether an agent, user account, or artifact channel carries the response |
| [Fatima et al., *On the Footprints of Reviewer Bots' Feedback on Agentic Pull Requests* (2026)](https://arxiv.org/abs/2604.24450) | 7,416 reviewer-bot comments on 4,532 AIDev PRs | More bot activity is linked to longer resolution; average feedback quality is not meaningfully linked to workflow outcomes | Bot feedback type/quality/volume and PR-level outcomes | Exact response edge and owner; it does not reconstruct which participant accepts the handoff or whether a later event addresses the trigger |
| [Chung & Hassan, *Collaborator or Assistant?* (AIware 2026)](https://doi.org/10.1145/3805760.3814893) | 29,585 complete PR lifecycles across five tools; Initiator x Approver taxonomy and state machines | Operational initiative and terminal merge governance decouple; merge authority remains mostly human | PR-lifecycle **role partitioning, initiative, approval, and governance** | Do not claim the first ownership/lifecycle study. Remaining gap: ownership **after one specific cross-product feedback event**, including intermediate owner and response channel rather than only lifecycle endpoints |
| [Khemissi et al., *Humans Integrate, Agents Fix* (MSR 2026)](https://arxiv.org/abs/2604.04059) | Referencing and referenced PRs in AIDev; Human-to-Agent and Agent-to-Agent reference taxonomy | Humans make most references; human and agent references have different intents; referenced workflows take longer | Cross-PR references and meta-collaboration between humans and agents | Within-PR review-response handoffs, exact reply relations, first owner, and user mediation after heterogeneous feedback |
| [Nachuma & Zibran, *When AI Teammates Meet Code Review* (MSR 2026)](https://arxiv.org/abs/2602.19441) | Agent-authored PRs in AIDev; repository-clustered models plus qualitative cases | Reviewer engagement is associated with integration; force pushes are associated with lower merge likelihood | Review-time collaboration signals, integration, and actionable-loop narratives | Exact product-aware trigger-response chains and mutually exclusive ownership routes; no causal interpretation of route-to-merge associations |
| [Peralta et al., *Why Are Agentic Pull Requests Merged or Rejected?* (MSR 2026)](https://arxiv.org/abs/2605.22534) | 11,048 closed PRs, 9,799 human-reviewed PRs, 717 manually inspected cases | Merge/rejection alone misstates capability; many decisions reflect workflow constraints or reviewer involvement | Interaction-aware decision rationale and visible reviewer intervention | Ordered product-pair handoffs and the timing/channel of first takeover after an agent-review trigger |
| [Agarwal et al., *3100 Opinions on Code Review in an AI World* (2026)](https://arxiv.org/abs/2607.07980) | 38,709 practitioner documents; 3,100 coded sample; plus motivating GitHub analysis | Review is proposed as the control point; team expertise/process may set the sign of AI impact; repository trends are analytically unstable | Human/process **causal theory**, review governance, and warnings about construct sensitivity | Empirically operationalize one narrow part of that theory—visible response ownership after heterogeneous feedback—but call it an observational test/signature, not validation of the whole causal theory |
| [Wang et al., *SWE-Review: Closing the Loop on Issue Resolution with Agentic Code Review* (2026)](https://arxiv.org/abs/2607.06065) | Controlled issue–PR reviewer/reviser framework, benchmark, and trajectory dataset | A structured generate-review-revise loop can improve issue resolution | Designed autonomous review-revision loops and downstream usefulness | Whether independent products in public repositories actually close such loops, when users take over, and where the public loop breaks |
| [KC & Budathoki, *Handoff Debt* (2026)](https://arxiv.org/abs/2606.02875) | 75 source tasks, 181 handoff points, 724 takeover runs per successor model | Context-bearing handoffs reduce rediscovery events and tokens; solved-rate effects are smaller/model-dependent | Controlled agent-to-agent takeover and **handoff cost** | A field signature of heterogeneous review handoffs in repositories: ownership, delay, extra rounds, and user mediation; public traces cannot measure hidden token/rediscovery cost |
| [Destefanis & Aste, *When Agents Coordinate* (2026)](https://arxiv.org/abs/2608.16801) | 1,902 controlled multi-agent coding runs plus 244 sealed runs; temporal agent/file/message networks | Coordination topology changes with team size/task; files can replace messages; named coordinators need not become hubs | A measurement instrument for explicit multi-agent message/file coordination | Real-world heterogeneous products plus users on GitHub; public feedback ownership and artifact-mediated coordination after a review trigger |
| [Grynets et al., *Specification Portability Across LLM Development Agents* (2026)](https://arxiv.org/abs/2608.21208) | 1,006-file migration stage and 1,802-script cross-agent experiments with several products | “Neutral” specifications can degrade sharply across agents; portability is agent-dependent | Controlled cross-agent artifact transfer and compatibility | Whether heterogeneous products show an analogous **field coordination burden** after review, without pretending product-pair associations prove protocol incompatibility |
| [Predoaia et al., *A Comparative Study of MCP and A2A for Inter-Agent Coordination* (2026)](https://arxiv.org/abs/2607.23884) | MCP and A2A implementations of the same SE coordination scenario | MCP is lighter but leaves lifecycle/state management to the application; A2A provides richer task state at greater complexity | Protocol-level lifecycle, state, interoperability, and observability trade-offs | Evidence of what today's independent GitHub apps expose in practice: acknowledgement, ownership, escalation, and lifecycle continuity are not directly measured by the protocols paper |

## What is saturated versus still open

### Saturated or high-collision claims

- “AI agents review other AI agents.”
- “This is the first large-scale study of developer response to AI review.”
- “Humans remain important in agentic code review.”
- “We are the first to study ownership/roles over the PR lifecycle.”
- “Multi-agent conversations or interaction sequences affect outcomes.”
- “Closing an agent review–revision loop improves performance.”
- “Cross-agent handoffs/compatibility are unexplored.”

### Open, data-compatible claim

The literature has not yet occupied the exact combination of:

1. a **specific cross-product review trigger**;
2. an **exact reply edge** when GitHub exposes one;
3. removal of the trigger review's **own submitted batch**;
4. a **product-aware first owner** rather than only human/AI counts;
5. dialogue, review, comment, and artifact-movement channels;
6. a fixed later-state landmark; and
7. a semantic audit separating “later activity” from “feedback addressed.”

This is a combination claim, not a safe basis for the phrase “the first study.” A
careful wording is:

> “We contribute an event-anchored, product-aware coordination topology for
> studying public responses to cross-product agent feedback.”

## Recommended three-RQ paper

| RQ | Falsifiable question | Minimum test and what would falsify the story |
|---|---|---|
| **RQ1 — Coordination topology** | After one exact cross-product feedback trigger, which public topology appears within seven days: direct dialogue, user-account mediation, automation-only continuation, artifact movement, or no observed action? | Mutually exclusive state/route reconstruction using exact parent IDs and distinct review batches. The “human bridge / artifact channel” story is falsified if exact mapped-agent dialogue dominates and the result is stable across repositories and product pairs. |
| **RQ2 — Heterogeneous handoff burden** | Compared with otherwise similar same-product feedback, is cross-product feedback more often followed by user-account mediation, more steps, or a longer path before the next code-changing/terminal event? | Within-repository/time/source matching plus a hierarchical or fixed-effects model; report overlap and pair support. The interoperability-burden story is falsified if matched differences are near zero, reverse, or depend on one pair/repository. Use “associated with” or “observed burden,” not “causes.” |
| **RQ3 — Semantic closure and later state** | Which early ownership topologies are followed by human-verified resolution of the triggering feedback and by later integration among PRs still open at a fixed landmark? | Blinded semantic audit linking trigger, response, and change plus landmark analysis. The reliability/escalation story is falsified if routes mostly show unrelated activity, or human-mediated and automation-only paths have indistinguishable verified closure after robust adjustment. |

These RQs form one story rather than three separate metric inventories:

`cross-product trigger -> coordination topology -> verified closure / later state`

## Highest-impact empirical extension to run next

1. **Build an ordered-product interoperability contrast.** For each cross-product
   trigger, construct a same-product comparison with the same repository,
   trigger source, calendar period, and similar pre-trigger PR state. Compare
   user-first mediation, exact mapped-agent reply, time/steps to first code-changing
   event, and no-observed-action. Use partial pooling; do not publish a league table.
2. **Separate conversation from artifact coordination.** Treat an exact reply as
   dialogue, a distinct review as another assessment round, and a force-push/commit
   as artifact movement. A later event is not automatically a response. This makes
   the paper connect directly to coordination-network research without claiming
   access to private agent messages.
3. **Use the 600-case blinded audit to validate semantic closure.** The crucial
   qualitative labels are: addresses trigger, rejects/explains trigger, unrelated,
   unclear, and no visible evidence. This is what can turn the current route counts
   into a meaningful coordination result.
4. **Add a topology stability panel, not another prediction model.** Report the
   main topology shares under leave-one-repository, leave-one-product-pair, exact
   versus relaxed identity, 24/48/72-hour windows, and user-account versus verified
   human coding. Stability is more valuable here than a small AUC gain.

## Overclaim risks and red lines

- **No causal human-benefit claim.** Human mediation is selected after feedback and
  likely reflects task difficulty, maintainer attention, and project policy. A
  landmark, matching, weighting, or clustered model does not by itself create an
  exogenous treatment.
- **Do not equate `User` with a verified human.** GitHub account type can hide
  automation and delegated actions. Use “user-account event” until identity/manual
  validation supports “human.”
- **Do not equate a later push/review/comment with feedback resolution.** Only an
  exact reply edge or semantic trigger-response-change audit can support an
  addressed-feedback claim.
- **Do not call public co-occurrence private agent communication.** The dataset
  cannot see prompts, vendor-side orchestration, model identity, or off-platform
  messages.
- **Do not call product-pair differences interoperability effects.** Product,
  repository, task, installation policy, and time are entangled. “Field signature”
  or “observed coordination burden” is safer.
- **Do not claim first ownership, first response, first sequence, first handoff, or
  first coordination-measurement study.** The collision rows above already occupy
  each broad version.
- **Do not rank products from sparse ordered pairs.** Require overlap, minimum
  support, partial pooling, and leave-one-pair/repository checks.
- **Avoid “autonomous dialogue” as a measured fact.** Exact mapped-agent replies are
  public account events; autonomy and intent remain unobserved.

## Venue fit

The official [EMSE special-issue call](https://emsejournal.github.io/special_issues/2026_SI_Agentic_SE.html)
explicitly asks how agents collaborate with developers, how developers respond,
what collaboration patterns emerge, how review speed balances with depth, and how
multi-agent coordination works. The proposed trigger-to-topology-to-closure design
fits those themes directly. Its venue value is the empirical bridge between two
currently separate literatures: designed multi-agent coordination traces and mined
human-agent repository traces.

## Recommended one-sentence novelty claim

> Prior studies count cross-product reviews, model broad review sequences, study
> developer resolution, or evaluate designed multi-agent handoffs; we instead
> reconstruct the public ownership topology after one exact heterogeneous-agent
> feedback event and test when that handoff becomes user-mediated, artifact-mediated,
> or semantically closed.

