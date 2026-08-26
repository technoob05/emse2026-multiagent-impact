# Novelty memo: cross-product feedback, response ownership, and escalation

**Update date:** 2026-08-25  
**Scope:** bounded primary-source novelty check for the revised mechanism. This is not an exhaustive systematic review.

## Decision

The revised story remains defensible only in a narrow form:

> **After an attributable agent product reviews a PR attributed to another agent product, who owns the next visible response, through which channel, and when does the public workflow move from agent-only activity to human mediation?**

The contribution is **not** the existence or prevalence of AI-to-AI review, developer acceptance of agent comments, generic human-AI review sequences, or the effect of agents on review quality. The remaining gap is the **product-aware ownership and escalation layer after a specific cross-product feedback event**.

This is useful because an AI review event does not show that a feedback loop closed. A repeated reviewer run, a human reply, an author-side action, and a branch update create different accountability and review-burden implications. Maintainers and tool builders need to know which actor carries the next step and where human mediation remains necessary.

## Exact collision boundary

| Closest work | What it already occupies | What it does not establish |
|---|---|---|
| Selvanayagam & Ghaleb, *AI-to-AI Code Reviews of GitHub Pull Requests* (ESEM 2026), [arXiv:2608.21311](https://arxiv.org/abs/2608.21311), [full text](https://arxiv.org/html/2608.21311), DOI `10.48550/arXiv.2608.21311` | Cross-product and same-product review prevalence; author-reviewer product configurations; comment categories and volume; time to first review. | The action after a feedback event, response actor, thread-level reply ownership, human takeover, branch movement, or downstream event topology. Any claim to be the first cross-product-review map collides directly. |
| Cynthia et al., *"Go Home Copilot, You're Drunk": Understanding Developer Responses to Agent-Generated Code Review Comments*, [arXiv:2607.21997](https://arxiv.org/abs/2607.21997), [full text](https://arxiv.org/html/2607.21997), DOI `10.48550/arXiv.2607.21997` | Comment resolution across agents and comment types; core/peripheral developer participation; reasons for unresolved comments; comment properties associated with usefulness. It uses GitHub `isResolved`/`resolvedBy` and excludes agent-only resolutions from its human-usefulness label. | A PR authored by product A and reviewed by product B as the unit; ownership across author product, reviewer product, other agents, and humans; ordered cross-product response channels; escalation from automated activity to human mediation. We cannot claim first developer-response or comment-actionability study. |
| Zhong et al., *From Human-Centric to Agentic Code Review*, [arXiv:2607.13196](https://arxiv.org/abs/2607.13196), [full text](https://arxiv.org/html/2607.13196), DOI `10.48550/arXiv.2607.13196` | Ordered sequences of review comments labeled by coarse reviewer type (human, LLM, agent), clustered into collaboration patterns; associations with decision time and review smells; includes multi-agent and agent-initiated patterns. | Product-specific author-reviewer dyads; anchoring a sequence at one feedback event; direct reply edges; whether the next actor is the author side, triggering reviewer, another agent, or a human; branch-action ownership. We cannot claim first interaction-sequence or first multi-agent-review-pattern study. |
| Lin et al., *Is Agentic Code Review Helpful?*, [arXiv:2607.03316](https://arxiv.org/abs/2607.03316) | Developer feedback and acceptance of CodeRabbit review suggestions. | Cross-product author-reviewer ownership and escalation topology. We should not frame the new result as general review usefulness. |

## Narrow novelty claim

Safe manuscript claim:

> To our knowledge, prior large-scale studies stop at cross-product review prevalence and reviewer behavior, human resolution of agent comments, or coarse human/AI review sequences. We instead anchor each trace at an attributable cross-product feedback event and distinguish the **owner of the next visible response**--author side, triggering reviewer product, another agent, or human--together with the channel and subsequent move to human mediation.

Even safer contribution wording:

> We add a product-aware response-ownership layer to existing measurements of AI-to-AI review.

Use **"human mediation"** as the default term. Use **"escalation"** only as an explicitly operational label, such as "a transition from agent-only post-trigger activity to a user-account reply, review, or PR comment." A timestamped human event does not prove that an agent intentionally requested help.

## Recommended research questions

1. **RQ1 -- Response fate.** After the first attributable cross-product feedback event on an agent-authored PR, what is the first observable next state, through which channel, and after how long?

   Report silence/no observed response, direct thread reply, later review, PR-level comment, and observable branch movement separately. Use fixed follow-up windows and state that channels may overlap.

2. **RQ2 -- Response ownership and mediation.** Who produces the first and later visible responses--the PR author account, author-agent product, triggering reviewer product, another agent, another human, or other automation--and when does an initially agent-only loop become human-mediated?

   This is the central novelty. Compare product pairs only after coverage and concentration checks. Validate that sampled triggers are substantive feedback and that sampled later events address or respond to the trigger.

3. **RQ3 -- Later workflow state.** Among comparable PRs still open at a fixed landmark, how are validated response topologies--no visible response, reviewer-only repetition, author-side response, human mediation, or mixed response--associated with later merge/closure and review burden?

   Treat this as observational. If semantic linkage or time-safe outcome gates fail, remove RQ3 and retain an honest two-RQ measurement paper.

## Claims that are occupied or unsupported

Do not claim:

- first observation, dataset, or prevalence study of cross-product/AI-to-AI review;
- first study of developer responses, resolution, acceptance, usefulness, or comment actionability;
- first study of human-AI or multi-agent review interaction sequences;
- that a later review is a response, resolution, or correction without semantic validation;
- that a force-push fixed the reviewed issue or was performed by an agent when actor/commit evidence is absent;
- that the reviewer product transferred work to a human or deliberately escalated the case;
- that two products shared memory, coordinated intentionally, or formed an autonomous multi-agent team;
- that human mediation or any loop shape caused merge, improved code quality, reduced defects, or saved effort;
- that `merged` means useful, correct, or productive code.

## Minimum evidence gate

The headline survives only if a blinded manual audit shows that (1) trigger events are genuine evaluative/actionable feedback, (2) linked responses refer to that feedback rather than merely occur later, and (3) actor-role mapping is reliable. Ordinary untimestamped commit records cannot establish post-feedback repair. Without these gates, use the weaker label **cross-product event sequence**, not feedback-response or corrective loop.

## Bottom line

The July and August 2026 papers remove the broad novelty. The honest residual is still impactful: **not whether agents review one another, not whether developers like agent comments, and not which reviewer types appear in a sequence—but who visibly takes responsibility after cross-product feedback and where the workflow requires human mediation.**
