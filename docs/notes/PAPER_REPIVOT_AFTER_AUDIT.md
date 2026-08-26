# Re-pivot after the task-continuity screen

## Decision

The exact-file design must no longer be presented as a population measure of handoff or recovery. It is a **candidate generator for task-continuity review**.

Two independent AI-assisted screens of the same 109 stratified pairs found only 9 (8.3%) and 13 (11.9%) likely same-task pairs. Both found five likely same-task cases among the 49 changed-agent pairs (10.2%). Even among 60 pairs with a non-generic shared path, only 8 (13.3%) and 10 (16.7%) were likely same task. The two screens agree on 94 of 109 three-level labels (86.2%, Cohen's kappa 0.688) and on 105 of 109 binary `likely same task` decisions (96.3%, kappa 0.799).

These are diagnostic results, not population estimates. The sample was stratified by the four contributor/agent modes and by generic versus non-generic paths, and the labels are AI-assisted rather than human ground truth. Still, the conclusion is strong enough to invalidate the old construct: **an exact shared path is usually not enough evidence that a later PR continues the earlier task**.

## Safe working title

**File Overlap Is a Weak Handoff Signal: A Measurement Audit of Multi-Agent Software Repositories**

Alternative, more neutral title:

**From Shared Files to Task Continuity: Auditing Multi-Agent Handoff Measures in Software Repositories**

Do not use *Artifact-Level Handoff Scarcity* in the title. The current data do not estimate true handoff prevalence.

## Safe paper story

Many mining studies need a scalable way to link a closed coding-agent PR to later work. Exact-path reuse looks direct, but it can join unrelated tasks through lockfiles, configuration files, shared modules, and repository hotspots. In AIDev-pop, the rule produces 19,405 successor candidates, yet two independent screens of a stratified sample find that only a small minority are clearly the same task. The mismatch remains even for non-generic files. It also breaks the old outcome story: in one screen, only 3 of 13 likely same-task pairs have the current success flag, while 49 of 80 likely different-task pairs have it. Thus, the flag mainly records whether a later PR merged; it does not show that the earlier task recovered.

The defensible contribution is a construct-validity study: audit common continuity proxies, build and validate a stronger task-continuation measure, and show how proxy choice changes claims about multi-agent work. Actual cross-agent continuation can remain a small descriptive or qualitative subset. No agent-effect estimate should be a headline unless human validation yields enough comparable positive cases.

## Three revised research questions

1. **RQ1 -- Proxy validity:** How well does exact-path reuse identify likely continuation of the same task after a closed-unmerged coding-agent PR?
2. **RQ2 -- Better continuity evidence:** Which observable signals---informative path overlap, title/body similarity, shared issue references, timing, and PR discussion---best separate task continuation from unrelated work?
3. **RQ3 -- Multi-agent composition and outcome boundary:** Among human-validated task continuations, how often do contributor identity and agent brand stay or change, and what can these cases safely show about later integration?

RQ3 must remain descriptive if the validated changed-agent cells are small. Do not promise a causal or well-powered agent comparison in advance.

## Exact manuscript withdrawals and rewrites

The locations below refer to the current `paper/manuscript/main.tex` inspected on 25 August 2026.

### Title, abstract, and keywords

- **Withdraw the current title and the phrase `artifact handoff`.** Exact-file reuse is only a candidate signal.
- **Rewrite the entire abstract (currently line 24).** Remove “we measure observable artifact handoff,” “linked to recovery,” “observable same-contributor handoff is rare,” and “general recovery benefit.”
- The numbers 19,405, 0.8%, and 87.3% may appear only as properties of the **exact-file candidate set**, not handoffs.
- Replace the conclusion with: the screen exposes low construct validity; a validated multi-signal measure is needed before estimating cross-agent continuation or outcomes.
- Replace the keyword `artifact handoff` with `task continuity` and `construct validity`.

### Introduction

- **Reword lines 36--46.** A later PR sharing a path does not establish “same work” or “same artifact” at task level. Present this ambiguity as the research problem.
- **Replace the current RQs at lines 54--61** with the three revised RQs above. In particular, withdraw `RQ3 -- Recovery and context`.
- **Withdraw the three contribution claims at lines 64--70.** The `<1%` cell is not a handoff rate, and the recovery contrast has no valid failed-task outcome.
- New contributions should be: a construct audit of exact-file matching; a human-validated, multi-signal continuation protocol; and a demonstration of how proxy error changes multi-agent claims.

### Related work

- Keep the neutral treatment of closed-unmerged PRs.
- **Reword lines 87--92 on Handoff Debt.** *Handoff Debt* studies known interrupted-task takeovers and the cost of missing context in a controlled setting. This paper cannot yet add field prevalence of takeover. Its distinct role is to test whether repository-trace proxies can identify candidate takeovers reliably.
- Keep the concurrent-versus-sequential boundary, but change “This paper measures that boundary” to “This paper audits whether the available trace can measure that boundary.”
- Replace the residual novelty claim at lines 109--111. Safe novelty: no study in the bounded map validates exact-path reuse against task-continuity judgments while separating contributor and agent continuity. Do not claim first-ever priority.

### Data and method

- Keep the AIDev-pop coverage and exact successor algorithm, but rename the output **exact-file successor candidates** throughout.
- **Reword lines 156--162.** The caveat must become a tested central result, not a minor threat. Remove the AUC 0.728 claim from the main paper because it predicts file overlap, not task continuity; it cannot validate the construct under study.
- Add a primary validation protocol: two independent human annotators, blinded to agent label and merge outcome; evidence from titles, bodies, linked issues, discussions, changed-file summaries, and timing; labels `same task`, `different task`, and `unclear`; adjudication and agreement statistics.
- Retain the stratified sampling design but record inclusion probabilities and use weights before any population prevalence estimate. The present unweighted 8.3% and 11.9% must not be generalized.
- Build the improved continuity rule only on a training split and report precision, recall, PR-AUC, and calibration on a held-out human-labelled split. Candidate signals should include inverse-frequency-weighted paths so common project hotspots count less.
- The four contributor/agent modes can remain as trace labels, but analyze them as multi-agent continuation only after a pair is human-validated or receives a validated continuation probability.
- **Withdraw lines 184--203 as a recovery analysis.** Rename `recovered_within_30d` to `successor_integrated_by_index_day_30`. Explain that it reports the later PR's merge under a common deadline and says nothing by itself about the earlier task.

### Results

- **Reword RQ1 at lines 217--223.** Safe statement: 19,405 of 37,110 eligible index PRs have a later PR touching an exact path within 30 days. Do not say “the same file often returns” as evidence that work or an artifact returns. Follow immediately with the screen result and sampling caveat.
- **Withdraw the heading `same-contributor agent handoff is rare` at line 225.** Replace it with `Composition of exact-file candidates`. The 88.7%, 0.8%, 4.7%, and 5.8% cells describe candidate pairs only.
- **Do not infer handoff scarcity from the 0.8% cell.** The audit shows most candidates are different tasks; therefore the denominator is not the handoff population.
- **Withdraw all of current RQ3 at lines 247--267 as a recovery result.** The 55.4%, 57.4%, 43.8%, and 51.6% values are later-successor integration rates. The +7.73 pp and +1.91 pp contrasts do not measure recovery of the earlier task.
- If retained, move those contrasts to a methodological diagnostic: “This is the misleading result obtained before task-continuity validation.” Do not interpret sign, p-value, or context shrinkage as an agent-impact finding.
- Main results should instead report human agreement, precision of exact-file matching, precision by generic/non-generic and other signals, and the number of validated continuation cases in each contributor/agent mode.

### Figures and tables

- **Withdraw the current Figure 2 headline `exact-file handoffs are scarce`.** Panel A can survive only in the supplement as candidate composition.
- **Remove or rebuild Panels B and C.** Rename “raw recovery rates” to `later-successor integration in unvalidated candidates` if shown as a cautionary example. They cannot support agent recovery.
- Replace the main figure with a measurement pipeline: eligible PRs -> exact-file candidates -> stratified audited sample -> human same-task/unclear/different labels -> validated contributor/agent modes. Do not draw the audit sample as a population-proportional funnel unless sampling weights are applied.
- Add a validation figure or table comparing exact-file-only precision with non-generic paths, weighted path overlap, title/body similarity, issue links, and the combined held-out rule.
- **Withdraw the current sensitivity table title `recovery contrast` at lines 269--285.** Move it to the supplement as an invalid-proxy diagnostic or remove it.

### Discussion

- **Withdraw lines 292--301 as an empirical handoff-scarcity claim.** The safe lesson is narrower: repository agent counts and raw exact-file overlap are both insufficient to establish coordination or task continuation.
- Keep “co-presence alone cannot establish coordination.” Do not state the stronger empirical conclusion “co-presence is not coordination” for individual pairs without evidence of intent or communication.
- **Withdraw the claimed agent-change policy result at lines 303--309.** The analysis did not observe recovery of the same task.
- Reframe the portable handoff record at lines 311--317 as a design implication from *Handoff Debt* plus the measurement gap, not as a direct effect supported by this dataset.
- Add the main research implication: mining work must validate task identity before comparing agents across sequential PRs.

### Threats to validity

- **Update lines 329--333 immediately.** The sample is now screened twice by AI, but it is still not human-labelled. Report both screen results and their agreement as pre-audit evidence, not ground truth.
- Add spectrum/sampling bias: the 109 pairs were deliberately stratified by transition mode and path type.
- Add evidence limits: titles and one example path can miss continuity visible in bodies, issues, diffs, and discussion.
- **Remove the definition `Recovery is ...` at lines 335--338.** Use `later-successor integration by a common deadline` and state that it is invalid as task recovery until continuity is established.
- Keep coverage, contributor-ID, label, dependence, temporal, public-repository, and causal limits.

### Conclusion

- **Withdraw the entire current conclusion at lines 357--365.** It turns exact-file candidates into handoffs and later-successor merges into recovery.
- Safe replacement: exact-path reuse creates many continuation candidates but has low apparent precision in two independent screens; shared files alone cannot support claims about multi-agent handoff or recovery; human-validated multi-signal task continuity is required before agent impact can be estimated.

## Claims permitted now

- The deterministic rule finds 19,405 later PRs that touch at least one exact path from 37,110 eligible closed-unmerged PRs within 30 days.
- In the 109-pair stratified sample, two AI-assisted screens label 8.3% and 11.9% as likely same task, with substantial three-level agreement and strong binary agreement.
- Both screens identify only five likely same-task cases among 49 changed-agent candidates.
- Exact-path overlap, including non-generic overlap, is a weak stand-alone task-continuity signal in this pre-audit.
- The current merge flag is a later-successor outcome, not a failed-task recovery measure.
- Co-presence and path overlap alone cannot establish multi-agent coordination.

## Claims prohibited now

- True handoff prevalence is 0.8%, 8.3%, 11.9%, or any other current percentage.
- Same-contributor or cross-agent handoff is rare in the population.
- A later agent recovered, retried, took over, or continued the earlier task without validated task identity.
- Changing agent improves or fails to improve recovery.
- The +7.73 pp or +1.91 pp estimates measure agent impact on the failed task.
- A shared non-generic path proves task continuity.
- The AI-assisted labels are human validation or ground truth.
- Same-task continuation proves intentional handoff, communication, or shared context.

## Submission gate and go/no-go rule

1. Complete independent human annotation with a written codebook and adjudication. Annotators should be blinded to agent and merge outcome during task-identity judgment.
2. Use a probability sample or preserve stratum weights. Report weighted prevalence only after this step.
3. Validate a multi-signal continuation rule on held-out human labels.
4. Count validated positives by contributor/agent mode before keeping RQ3. If changed-agent continuation remains too small for repository-aware inference, make it qualitative/descriptive and keep the paper as a measurement-validity study.
5. Only use *handoff* when PR text or linked evidence shows a deliberate takeover. Otherwise use *task continuation candidate* or *validated same-task successor*.

The current evidence supports a strong measurement paper. It does **not** support a handoff-impact or recovery-effect paper yet.
