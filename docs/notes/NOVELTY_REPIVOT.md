# Novelty re-pivot after the same-file construct audit

Date: 2026-08-25

## Executive decision

The paper should no longer use **artifact-level handoff scarcity** as its main empirical claim. An exact-file successor is a useful trace relation, but the independent screens show that it often links different tasks. The stronger contribution is a construct-validity result:

> Multi-agent presence, temporal succession, artifact reuse, task continuation, and coordination are different constructs. Treating them as interchangeable changes both the population being counted and the apparent outcome story.

This is not merely a limitation. It is an empirical measurement contribution for mining agentic software repositories. The current project already contains the ingredients for a strong **coordination observability ladder**, but the task-continuity layer needs final human validation before it can support population estimates.

## Critical evidence that changes the story

The available proxies form a ladder:

1. **Brand co-presence:** a repository contains at least two observed agent brands.
2. **Temporal succession:** a later coding-agent PR follows an earlier known outcome without overlap.
3. **Artifact succession:** a later PR touches at least one exact file from a closed-unmerged PR.
4. **Task continuation:** title, body, issue, and artifact evidence indicate that the later PR continues the same work.
5. **Coordination:** the trace records an intentional transfer, shared context, or agent-agent communication.

Only levels 1--3 are directly computable at scale from AIDev. Level 4 requires validated inference. Level 5 is not observed in the dataset.

The empirical results already show why the levels cannot be collapsed:

- The full corpus contains 44,822 repositories with at least two brands.
- The outcome-known ledger contains 49,733 episodes after a closed-unmerged PR; 31.2% change agent brand.
- In the exact-file cohort, 19,405 of 37,110 eligible index PRs have a same-file successor within 30 days, but only 1,279 successors change agent and only 162 keep the contributor while changing agent.
- The same-file relation is not the same-task relation. In two independent AI-assisted screens of the same 109 sampled pairs, only 9 and 13 pairs were labelled likely same task. The stricter screen labelled 77 pairs as different work and 23 as unclear.
- The two screens agree on 86.2% of three-way labels (Cohen's kappa 0.688). For `same task` versus all other labels, agreement is 96.3% (kappa 0.799). All nine strict positive labels are also positive in the second screen. These are useful pre-audit diagnostics, not human ground truth.
- A non-generic shared path is still weak evidence: the strict screen marked only 8 of 60 such pairs likely same task.
- The outcome story changes with the proxy. The nearest-episode analysis reports a positive same-contributor brand-change association. The exact-file analysis yields wide repository-clustered intervals and a much smaller within-context contrast. The manually screened same-task subset is too small and selected to estimate a recovery effect.

The honest conclusion is not that handoffs are rare in the population. It is that **repository traces can make unrelated work look like succession or recovery unless the coordination construct is validated**.

## Ranked paper stories

| Rank | Story | Empirical support now | Residual novelty | EMSE fit | Decision |
|---|---|---:|---:|---:|---|
| 1 | From co-presence to coordination: a construct-validity audit | 4.5/5 | 4.5/5 | 5/5 | Recommended main paper |
| 2 | Whose switch is it? Contributor-agent entanglement after non-integration | 5/5 | 3.5/5 | 4.5/5 | Strong fallback or one layer of Story 1 |
| 3 | Coordination observability debt and a provenance contract | 3/5 | 4.5/5 | 5/5 | High-impact extension; needs stronger validation |

### Story 1 -- From co-presence to coordination

**Possible title:** *From Co-Presence to Coordination: Validating Multi-Agent Measures in Software Repositories*

**Core contribution:** define and empirically compare the observability ladder above. Show how counts, contributor composition, and integration associations change as the operational definition moves from brand presence to task continuation. The primary result is construct sensitivity, not a product ranking or switching benefit.

**Three RQs**

1. **RQ1 -- Measurement funnel:** How many repository events satisfy brand co-presence, outcome-known succession, exact-file succession, and validated task continuation?
2. **RQ2 -- Proxy validity:** How well do timing, title/body similarity, issue references, and exact-path features identify manually validated task continuation?
3. **RQ3 -- Conclusion sensitivity:** How do contributor/agent composition and subsequent integration associations change across these measurement levels?

**Why it is novel:** AIDev maps the ecosystem; Xu et al. study concurrent co-activity and conflict; Shastry et al. construct dependent benchmark sequences; Handoff Debt experimentally studies known takeovers. The residual gap is a real-repository validation of what common mining proxies do and do not measure, with the downstream effect on substantive conclusions.

**Why it matters:** It gives future Agentic SE work a defensible unit of analysis and prevents brand diversity, temporal adjacency, or file reuse from being reported as coordination. This fits the EMSE call's focus on mining agent-generated artifacts, multi-agent coordination, failure attribution, and trustworthy human-agent collaboration.

**Required gate:** draw a documented, representative stratified sample; use at least two human coders; define `yes/no/unclear` rules before coding; report agreement and adjudication; calibrate a high-precision continuation classifier; then recompute RQ3 only on validated or conservatively predicted continuation cases.

### Story 2 -- Contributor-agent entanglement

**Possible title:** *Whose Switch Is It? Human and Agent Reconfiguration After Non-Integrated Pull Requests*

**Core contribution:** show that an observed agent-brand change is usually also a contributor change. Treat the repository transition as joint social-and-tool reconfiguration rather than an individual's choice of another agent.

**Three RQs**

1. **RQ1 -- Composition:** When an agent brand changes, how often does the contributor stay or change?
2. **RQ2 -- Outcome conditioning:** How do the four contributor/agent transition modes differ after merged and closed-unmerged prior outcomes?
3. **RQ3 -- History and outcome:** How are these modes associated with later integration across repeated histories and repository contexts?

**Support:** this uses the full 7.69M backbone and the leakage-safe 466,467-episode ledger. The central composition result is stable: 83.3% of brand changes after a closed-unmerged episode also change contributor. The exact-file cohort independently gives the same qualitative warning: 87.3% of agent-changing successors also change contributor.

**Novelty boundary:** Chung and Hassan already separate initiator from approver within PR lifecycles, while developer-role and submitter studies show that people shape agent use and integration. The residual contribution is cross-PR, outcome-known contributor-agent reconfiguration. This is empirically strong but less directly about coordination than Story 1.

**Main risk:** without task continuity it still cannot call the later outcome recovery. Use `subsequent integration`, not `recovery`, and make this the robust fallback if the human task-continuity audit does not pass.

### Story 3 -- Coordination observability debt

**Possible title:** *GitHub Cannot Show the Handoff: Evidence Gaps in Coding-Agent Provenance*

**Core contribution:** catalogue the failure modes that prevent public PR traces from distinguishing co-presence, continuation, and coordination, then propose a minimal machine-readable coordination receipt.

The empirical error taxonomy already includes:

- generic lock, manifest, changelog, README, CI, and configuration paths creating incidental links;
- non-generic files reused by distinct tasks in the same subsystem;
- one successor linked to several earlier closed-unmerged PRs;
- missing issue, task, review, and file data;
- agent brand without model/session/version identity;
- contributor ID without decision-maker or account-sharing evidence;
- closure outcome without stopping reason;
- no predecessor-task pointer, transferred context, open-review state, or explicit handoff event.

**Three RQs**

1. **RQ1 -- Observability:** Which multi-agent claims can each AIDev table support directly, indirectly, or not at all?
2. **RQ2 -- Error modes:** How often do temporal, file, and text proxies produce ambiguous or false task-continuation candidates?
3. **RQ3 -- Provenance contract:** What minimum metadata would distinguish independent work, human-mediated reassignment, and coordinated agent takeover?

**Suggested coordination receipt:** predecessor PR/task ID; stable agent and model version; human initiator; task goal; files and tests attempted; unresolved review items; stopping reason; successor session/agent; context artifacts transferred; and explicit transfer timestamp.

**Why it fits EMSE:** the call explicitly highlights new agent-generated artifacts, attribution, multi-agent coordination, trust, and governance. Handoff Debt shows why transferred context matters in controlled tasks; this story explains why current repository records cannot measure whether that transfer occurred.

**Main risk:** a provenance proposal alone may look like a position paper. Strengthen it with dual human coding, a released annotated benchmark, proxy precision/recall, and, if feasible, interviews or validation with repository maintainers/tool builders.

## Primary-literature boundary

- **AIDev** establishes large-scale agent PR ecology; dataset scale is not novelty.
- **Xu et al.** study concurrent cross-agent PR pairs and merge conflicts. Their co-activity construct is not the sequential task-continuation construct here: <https://arxiv.org/abs/2607.04697>.
- **Shastry et al.** evaluate known dependent task chains in a generated benchmark and show isolated-task evaluation can overstate performance. They do not validate coordination proxies in mined public histories: <https://arxiv.org/abs/2604.03035>.
- **Handoff Debt** owns the controlled takeover and handoff-context concept. This project must not claim to introduce agent handoff: <https://arxiv.org/abs/2606.02875>.
- **Chung and Hassan** separate operational initiative from merge governance and explicitly note that execution logs need not reveal the decision-maker. This supports, rather than replaces, the cross-PR observability audit: <https://arxiv.org/abs/2605.08017>.
- **Nachuma and Zibran**, Zhong et al., and Yu et al. make generic review-dynamics novelty crowded. Review should be a secondary validation/mechanism, not the headline.
- The EMSE special issue explicitly invites mining agent-generated artifacts, human-agent collaboration, multi-agent coordination, review dynamics, and failure attribution: <https://emsejournal.github.io/special_issues/2026_SI_Agentic_SE.html>.

## Claims that are no longer safe

- `Exact-file handoffs are rare.` The audit measures exact-file successors, not a representative population of verified handoffs.
- `52.3% of failed work returns.` It shows that a later PR touches one of the same paths, not that the task returns.
- `The successor recovers the failed task.` Use `later PR integration` unless same-task continuation is validated.
- `Changing agents improves recovery.` Repository-clustered and within-context intervals do not support this.
- `Multi-agent repositories coordinate work.` Brand co-presence is only the lowest observability level.
- `The agents communicated or shared context.` AIDev does not record this.
- `Closed-unmerged is failure.` It is an integration outcome with many possible causes.
- `The AI-assisted screens are manual ground truth.` They are pre-audit evidence for designing human validation.
- `This is the first coding-agent handoff study.` Handoff Debt already studies known takeovers.

## Recommended paper decision

**Choose Story 1.** It converts the negative manual-audit result into the paper's most useful insight: measurement choices create different versions of “multi-agent impact.” Keep contributor-agent entanglement as the central example within the ladder. Treat provenance debt as the practical design implication.

If dual human validation cannot be completed, submit **Story 2** instead. It has the strongest current empirical foundation and can honestly claim contributor-aware reconfiguration, but it should avoid the terms handoff, same task, and recovery.

Do not proceed with the current direct-handoff title or abstract until the construct language is changed and the human validation gate is complete.
