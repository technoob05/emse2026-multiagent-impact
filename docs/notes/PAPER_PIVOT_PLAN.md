# Manuscript pivot plan: direct artifact succession

## Proposed title

**Co-Presence Is Not Coordination: Artifact-Level Handoff Scarcity in Multi-Agent Software Repositories**

Use *exact-file successor* as the measured term in the paper. Use *handoff* only as the higher-level problem and always state that file reuse does not prove an intentional transfer.

## Structured abstract (238 words; B1 English)

**Context:** A repository can contain pull requests (PRs) made with several coding-agent brands. This shows that many agents are present, but it does not show that one agent continues another agent's work. **Objective:** We study what happens to code files after an agent PR closes without merge. We ask whether the files return, who returns to them, and whether a new agent is linked to better recovery. **Method:** We use the AIDev-pop part of AIDev-7.6M. It contains 361,296 PRs from popular GitHub repositories. File paths are available for 188,768 PRs. We identify 37,110 closed-unmerged PRs with file data and follow each exact path for 30 days. We keep the first later agent PR that touches any of those paths. We separate contributor change from agent change and use repository-aware uncertainty checks. **Results:** An exact-file successor appears for 19,405 PRs (52.3%). Most successors keep both the same contributor and the same agent (88.7%). Only 162 successors (0.8%) keep the contributor but use a new agent. Among all 1,279 agent changes, 87.3% also change contributor. A raw recovery gap for new contributors becomes small and uncertain in comparable repository and prior-agent settings (+1.9 percentage points; 95% interval -8.8 to +12.3). **Conclusion:** Multi-agent presence is common, but clear cross-agent artifact handoff is rare. Repositories need explicit records of prior attempts, open review points, and stopping reasons. The results describe public traces; they do not prove agent communication, intent, or causal benefit.

## Three research questions

1. **RQ1 -- Artifact return:** Among file-covered closed-unmerged coding-agent PRs, how often does the first later coding-agent PR that touches any exact path start within 30 days?
2. **RQ2 -- Handoff composition:** When an exact-file successor appears, how often do contributor identity and agent brand stay or change?
3. **RQ3 -- Recovery and context:** How is agent change linked to merge by day 30 after the earlier PR closed, and does the observed difference remain under repository-aware, within-context, and stricter-link checks?

## Section-by-section replacement plan

### Title and abstract

Replace the current “When Coding Agents Change” framing and the adaptation-gap result. Make the unit an earlier closed-unmerged PR plus its first exact-file successor. Lead with the scarcity result, not a switch benefit.

### Introduction

Replace the nearest-PR motivation with one clear problem: counting agent brands shows co-presence, while coordination requires evidence that work returns to the same artifact. Define an exact-file successor in plain language. State the practical question: does another agent continue work on the same files, or does the same contributor-agent pair return? End with the three RQs above and three contributions:

1. a time-safe exact-file successor design;
2. a 2x2 contributor/agent composition of artifact return; and
3. repository-aware evidence that the apparent recovery benefit is not stable.

Do not present the former “adaptation gap” as a main contribution.

### Related work

Organize around three boundaries:

- **Coding-agent PR ecosystems:** AIDev and studies of merge, review, task, and failure patterns explain why closed-unmerged is a neutral outcome, not proof of agent failure.
- **Designed multi-agent systems and concurrent conflict:** ChatDev/MetaGPT study planned communication; concurrent-PR work studies overlap before resolution. This paper studies a later PR that starts only after the earlier PR closes.
- **Agent takeover and Handoff Debt:** *Handoff Debt* already defines takeover of interrupted coding tasks and tests context-bearing handoff views in a controlled setting. It shows that transferred context can reduce rediscovery cost. Do **not** claim to introduce coding-agent handoff or to be the first handoff study. The safe boundary is: this paper measures real-repository prevalence, contributor/agent composition, and outcome uncertainty for exact-file successors. It cannot observe the context that was transferred or whether transfer was intended.

End the section with a bounded novelty statement: no work in the current evidence map combines resolved-before-successor ordering, exact-path reuse, contributor continuity, agent-brand continuity, and repository-aware outcome uncertainty in public repositories.

### Data and method

Keep the dataset map, but make AIDev-pop the primary analysis layer. State that 188,768 of 361,296 PRs have usable file paths (52.2%); do not imply that all 7.69 million PRs support the handoff analysis.

Replace the full-corpus episode and streak method with this flow:

1. Select file-covered PRs that closed without merge by 1 March 2026.
2. For every exact path in each earlier PR, find the first later PR in the same repository whose opening time is strictly after the earlier close.
3. Keep the earliest successor across all shared paths and require it to start within 30 days.
4. Record shared-file count, generic-path status, contributor continuity, agent continuity, and successor reuse.
5. Define recovery as the successor merging by day 30 after the earlier PR closed. Use this exact wording; it is not a full 30-day window after successor opening.

Explain the four contributor/agent cells once in a small taxonomy. For inference, report repository-clustered contrasts, a comparison within repository-by-prior-agent strata, and sensitivities for non-generic paths, two or more paths, 7/14-day starts, unique links, and the nearest failed PR per successor.

Move the old nearest-resolved transition and streak designs to a short appendix as motivation/sensitivity, or remove them if page pressure is high.

### Results

Use three short subsections that match the RQs:

- **RQ1:** 19,405 of 37,110 eligible PRs have an exact-file successor within 30 days (52.3%). Report the denominator and the 52.2% upstream file-coverage limit beside this result.
- **RQ2:** 17,209 successors keep contributor and agent (88.7%); 162 keep the contributor but change agent (0.8%); 917 change contributor but keep agent (4.7%); 1,117 change both (5.8%). Of 1,279 agent-changing successors, 87.3% also change contributor.
- **RQ3:** Raw recovery rates are 55.4%, 57.4%, 43.8%, and 51.6% for the four cells above. The same-contributor new-agent contrast is +2.05 pp (95% CI -10.33 to +14.43). For different contributors, the raw contrast is +7.73 pp (-2.89 to +18.35), but the comparable repository-by-prior-agent estimate is +1.91 pp (-8.81 to +12.29). The correct result is uncertainty and context sensitivity, not a benefit from agent change.

### Discussion

Lead with one sentence: **many repositories contain several agent brands, but the observed trace usually returns to the same contributor-agent pair.** Explain why this matters for empirical studies: agent diversity is not a measure of coordination. Then give one practical implication: handoff tools should store the earlier goal, changed files, test state, open review points, and reason for stopping. Treat the wide intervals as a useful negative result, not a failed hypothesis.

### Threats to validity

Replace the current emphasis on generic sequential episodes with five direct threats: incomplete file coverage; common paths can create false continuity; exact-path reuse does not prove the same task; one successor may link to several earlier PRs; and the outcome window ends 30 days after the earlier close. Keep label-version, contributor-ID, public-GitHub, and observational limits. State that a manual audit is still required before any claim about same-task or intentional handoff.

### Conclusion

Use three claims only: exact-file return is common in the observed cohort; same-contributor/new-agent succession is rare; and no stable recovery benefit is supported after context-aware uncertainty checks. End with the need for explicit handoff records.

## Exact table and figure plan

### Figure 1 -- Data layers and analysis cohort

Retain a simplified dataset map. The caption must say that the main cohort comes from AIDev-pop, not the full 7.6M PR table. Show: 361,296 rich PRs; 188,768 file-covered PRs (52.2%); 37,110 eligible closed-unmerged index PRs; 19,405 exact-file successor episodes from 2,649 repositories.

### Figure 2 -- Main story

Use `outputs/figures/direct_handoff_story.pdf` as the core result figure.

- Panel A supports the scarcity claim: 88.7% same contributor/same agent, 0.8% same contributor/new agent, 4.7% new contributor/same agent, and 5.8% new contributor/new agent.
- Panel B shows raw recovery rates only as description; do not mark a “winner.”
- Panel C supports the uncertainty claim: cross-contributor new-agent minus same-agent is +7.7 pp with repository-clustered CI [-2.9, +18.4], and +1.9 pp within comparable repository/prior-agent strata with interval [-8.8, +12.3].
- Revise the y-axis/caption from “merged within 30 days” to “merged by day 30 after the earlier PR closed.”

### Table 1 -- Cohort construction and data quality

Build from `direct_handoff_quality.csv`: 361,296 rich PRs; 4,616,736 unique PR-path rows; 188,768 file-covered PRs; 37,110 eligible index PRs; 19,405 successor episodes; 14,450 unique successors; 2,649 repositories; 15 ambiguous earliest ties; 7,695 episode rows whose successor is linked to more than one earlier PR. This table makes censoring, coverage, and dependence visible.

### Table 2 -- Recovery contrasts

Keep only the two contributor strata from `direct_handoff_clustered_contrasts.csv`, plus the `ALL` row from `direct_handoff_within_context.csv`. Report estimate, 95% interval, episode count, and repository/stratum count. The text should interpret interval width, not p-values.

### Supplementary table -- Robustness

Move all rows of `direct_handoff_sensitivity.csv` to the supplement. State that every listed interval crosses zero, including non-generic paths (+7.06 pp, [-4.74, +18.87]), two or more paths (+6.60 pp, [-5.53, +18.72]), and nearest failed PR per successor (+5.87 pp, [-2.27, +14.01]). Do not turn these repeated estimates into many main-text claims.

Remove the current adaptation-gap figure and adjusted nearest-episode model table from the main paper.

## Safe claims and caveats

### Claims the paper can make

- In the file-covered AIDev-pop cohort, 52.3% of eligible closed-unmerged PRs have a later agent PR touching at least one exact path within 30 days.
- Observable same-contributor/new-agent artifact succession is rare (0.8% of exact-file successor episodes).
- Most agent-brand changes in these episodes also change contributor (87.3%).
- Raw recovery differences are imprecise and shrink in comparable repository/prior-agent contexts.
- Multi-agent brand co-presence should not be used as evidence of coordination.

### Claims the paper must not make

- The second agent received context, communicated, or intentionally took over.
- Exact-file reuse proves the same task, goal, or causal chain.
- A closed-unmerged PR is an agent failure.
- Changing agent improves recovery, quality, or productivity.
- The findings cover all 7.6M PRs or all coding-agent use.
- This is the first paper on coding-agent handoff; *Handoff Debt* already studies that concept.

### Remaining gate before manuscript rewrite is submission-ready

Complete the stratified manual audit in `outputs/manual_audit/direct_handoff_manual_audit.csv`. Report same-task and intentional-handoff agreement separately for generic-only and non-generic links. Until that audit is complete, keep “exact-file successor” as the empirical term and “handoff scarcity” as a careful interpretation.
