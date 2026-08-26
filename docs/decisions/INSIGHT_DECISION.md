# Insight decision: measurement validity before agent impact

## Selected story

**Working title:** *From Co-Presence to Coordination: Validating Multi-Agent Measures in Software Repositories*

The earlier nearest-PR story mixed unrelated tasks. The later exact-file story improved artifact continuity but still failed a task-identity audit. The paper therefore treats this failure as the main empirical result: different repository proxies measure different constructs and can produce different multi-agent conclusions.

## Observability ladder

1. Brand co-presence: two or more agent brands appear in a repository.
2. Temporal succession: a later PR starts after an earlier PR closes.
3. Exact-file succession: the later PR touches an exact earlier path.
4. Likely task continuation: path evidence plus title or issue evidence.
5. Observed coordination: explicit context transfer or communication.

Levels 1--3 are observable at scale. Level 4 needs human validation. Level 5 is absent from AIDev.

## Strongest current evidence

- 37,110 eligible index PRs.
- 30,343 (81.8%) have any later PR within 30 days.
- 19,405 (52.3%) have an exact-file successor.
- Two independent AI-assisted screens of 109 stratified pairs label 9 and 13 as likely the same task.
- Screen agreement is 86.2% for three labels ($\kappa=0.688$) and 96.3% for same-task versus other ($\kappa=0.799$).
- A strong exploratory title/issue rule retains 4,413 candidates. Only 92 change agent; 81 of those also change contributor. Only 11 keep the contributor and change agent.
- Across title thresholds from 0.05 to 0.40, same-contributor/new-agent candidates range from 26 to 6. The exact count changes, but contributor--agent entanglement remains.

## Main contribution

File overlap is a candidate generator, not a handoff label. A later merged PR is not recovery of an earlier task until same-task continuity is established. Future mining work should validate the unit of analysis before estimating agent impact.

## Claims allowed now

- Exact-file reuse produces 19,405 candidate pairs in the stated cohort.
- The stratified AI-assisted screens expose weak apparent precision of file overlap alone.
- Stronger text/issue rules sharply reduce cross-agent candidates.
- Most observed agent changes also change contributor.
- AIDev does not record intentional coordination.

## Claims not allowed

- True handoff prevalence is 0.8%, 8.3%, 11.9%, or any current candidate share.
- A new agent recovered or took over the earlier task without validated task identity.
- Agent change improves integration, quality, or productivity.
- The AI-assisted screens are human ground truth.
- Same-task continuation proves direct agent-agent communication.

## Submission gate

Two human coders must label a probability-aware sample while blind to agent and merge outcome. The study must report agreement, adjudication, weighted estimates, and held-out proxy performance. If changed-agent positives remain small, RQ3 stays descriptive.
