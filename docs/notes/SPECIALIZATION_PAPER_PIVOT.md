# Specialization paper pivot

## Recommendation

Pivot from handoff and recovery to **task-role expansion after a second coding-agent brand enters a repository**. The simple story is: repositories may add another agent because it brings a different work role, not because it replaces the first agent.

The evidence is promising but not final. In the corrected full-window, explicit-prefix cohort, task breadth rises, but the entrant-versus-incumbent rarity estimate is imprecise. The classifier has useful held-out scores, but the predicted-label specialization sensitivity has not run. Therefore, write the paper as an **ecosystem specialization study with a pending confirmatory gate**, not as proof that a second agent causes broader work.

## Proposed title

**More Than Another Tool? Task-Role Expansion When a Second Coding Agent Enters a Repository**

Short alternative: **Do New Coding Agents Expand Repository Task Roles?**

## Abstract skeleton (180 words)

**Context:** Software repositories use several coding-agent brands. A new agent may repeat work done by the first agent, or it may add a new task role. **Objective:** We study whether the second agent brand expands repository work. **Method:** We use AIDev-pop and identify the first two agent brands in each repository. We compare task types in equal periods before and after the second agent enters. A title-prefix rule gives high-precision task labels but covers only 40.7% of PRs. The 90-day cohort contains 41 repositories, 1,054 pre-entry PRs, and 2,232 post-entry PRs. **Results:** Task breadth rises by 0.85 types, with a 95% interval from 0.22 to 1.47. New task types appear in 68.3% of repositories. The entrant introduces a new type in 53.7%, and such a type is integrated in 39.0%. However, the entrant's rarity advantage is small and uncertain: 0.05, with an interval from -0.05 to 0.14. **Conclusion:** A second agent often appears with wider task coverage, but current evidence does not prove agent specialization or causal expansion. A title classifier performs well on held-out data; classifier-based sensitivity remains pending.

## Three research questions

1. **RQ1 -- Role difference:** After a second coding-agent brand enters, how different are the task mixes of the entrant and incumbent?
2. **RQ2 -- Portfolio expansion:** Does the repository cover more task types after entry, and which agent first introduces the new types?
3. **RQ3 -- Useful expansion:** How often are entrant-introduced task types integrated within 30 days, and are the patterns stable across label methods, windows, and cohort rules?

RQ3 is descriptive. “Integrated” means at least one PR in that entrant-introduced type merges within 30 days of its own opening. It does not mean the entrant caused integration or that the task type is high quality.

## Three contributions

1. **A repository-onset design.** We define the second-agent entry event and compare equal pre/post windows with complete 30-day outcome exposure. This makes the repository task portfolio, not an agent leaderboard, the unit of interest.
2. **A role-expansion measurement.** We separate three ideas that are easy to mix: task-mix distance, repository task breadth, and which agent first introduces a new task type.
3. **A transparent evidence ladder.** We report the high-precision prefix cohort as discovery evidence, repository-level uncertainty, held-out classifier quality, and classifier/window/cohort sensitivities as a required confirmation before the final claim.

## Two useful figures

### Figure 1 -- A second agent often arrives with wider task coverage

Use one insight-first figure with three panels:

- **A: onset design.** A simple timeline shows the incumbent, second-agent entry, equal 90-day pre/post windows, and the full 30-day merge window. This explains the unit without many numbers.
- **B: paired task breadth.** For each of the 41 repositories, connect pre-entry and post-entry task breadth. Add the mean change: **+0.85 types, 95% CI +0.22 to +1.47**.
- **C: who adds the new role?** Show repository shares: **68.3%** have any new type; **53.7%** have an entrant-introduced type; **39.0%** have an integrated entrant-introduced type. Label all values “prefix-labelled, corrected full-window cohort.”

Do not call Panel C an impact funnel. The three shares are nested descriptions of repositories, not causal stages.

### Figure 2 -- Different roles are plausible, but not yet precise

Use a repository-level dot/forest plot:

- plot each repository's entrant-minus-incumbent rarity difference;
- show the mean **+0.050** and 95% CI **[-0.046, +0.142]**;
- show **63.4%** of repositories above zero only as a descriptive annotation;
- state that the permutation result is **p=0.091** and the Wilcoxon result is **p=0.111**;
- optionally add mean entrant-incumbent task-mix distance (**Jensen-Shannon distance 0.458**) as a descriptive side panel.

The title should read: “Entrants may take different roles, but the current prefix cohort is underpowered.” After classifier sensitivity is complete, add estimates for confidence-margin thresholds to this figure. Until then, leave no classifier result placeholder in a submission PDF.

## Two tables

### Table 1 -- Task labels and analysis cohort

Report:

| Item | Current value | Meaning |
|---|---:|---|
| AIDev-pop PRs | 361,296 | Rich-layer population |
| Explicit-prefix labels | 147,036 (40.7%) | Discovery label coverage |
| Prefix/supplied-label overlap | 4,457 | Validation overlap |
| Agreement on overlap | 99.5% | Agreement, not independent human accuracy |
| Corrected 90-day repositories | 41 | Full pre, post, and outcome windows |
| Prefix-labelled pre/post PRs | 1,054 / 2,232 | Main discovery cohort |
| Classifier training labels | 32,702 | Supplied task-label subset |
| Classifier macro-F1 | 0.844 / 0.800 / 0.770 | Random / repository-disjoint / temporal splits |

Add a note that the supplied labels may share title cues with the prefix rule. The 99.5% agreement does not prove external validity.

### Table 2 -- Repository-level findings and evidence status

| Finding | Estimate | 95% interval/status |
|---|---:|---|
| Entrant-minus-incumbent rarity | +0.050 | [-0.046, +0.142]; underpowered |
| Repositories with positive rarity difference | 63.4% | descriptive |
| Mean breadth change | +0.854 task types | [+0.220, +1.467] |
| Repositories with any new type | 68.3% | descriptive |
| Entrant introduces a new type | 53.7% | descriptive |
| Entrant-introduced type integrates | 39.0% | descriptive |
| Entrant-introduced types | 34 | 24 have a merged PR within 30 days (70.6%) |
| Mean entrant-incumbent role distance | 0.458 | descriptive Jensen-Shannon distance |

Do not put results from `sensitivity.json` in the main table yet. That file predates the corrected complete-outcome-window run and is not the current confirmatory evidence.

## Insight-first result story

Use this order in Results:

1. **Repositories broaden after entry.** The clearest current result is the increase in task breadth, not the rarity contrast.
2. **The entrant often helps open a new task category.** More than half of the corrected cohort has an entrant-introduced type, but the same repository may also receive incumbent expansion.
3. **Role specialization remains plausible, not confirmed.** Entrants work on somewhat rarer task types on average, but only 41 repositories meet the corrected rules and the CI crosses zero.
4. **The conclusion must survive a second label route.** Held-out classifier scores are encouraging, especially the repository-disjoint macro-F1 of 0.800, but predicted-label specialization estimates across confidence thresholds are still pending.

Plain-language takeaway: **A second agent often arrives when the repository's work becomes broader. We do not yet know whether the new agent creates that breadth or is selected because the work has already changed.**

## Manuscript claims and material to remove

Remove or fully replace these parts of the current handoff manuscript:

- the title **“Co-Presence Is Not Coordination”** and all title/abstract claims about handoff scarcity;
- all three exact-file successor RQs;
- the claim that 19,405 exact-file successors measure returned work;
- the claim that **0.8%** is the rate of same-contributor agent handoff;
- the claim that **87.3%** of handoffs are contributor turnover;
- all “recovery” rates and the **+7.73 pp** and **+1.91 pp** contrasts;
- the direct-handoff story figure and recovery sensitivity table;
- the conclusion that the data show no general recovery benefit from changing agents;
- the portable handoff-record recommendation as the paper's main practical result;
- any remaining adaptation-gap or switch-after-failure claim from older drafts.

The exact-file audit may remain in the supplement as a **negative measurement lesson**: shared paths do not reliably identify the same task. It should not compete with the specialization story in the main paper.

## Claims that are safe now

- In the corrected prefix-labelled cohort, task breadth is higher after the second-agent entry event.
- New task types appear in many eligible repositories, and entrants introduce some of them.
- Entrant and incumbent task mixes show role separation, but the entrant rarity contrast is imprecise with 41 repositories.
- The prefix rule is reproducible and precise-looking on its overlap, but partial coverage can select repositories and task styles.
- The classifier generalizes reasonably across held-out repositories and time, but the specialization conclusion still needs classifier-margin sensitivity.

## Claims that are not safe

- The second agent causes task expansion.
- New agents are more specialized, more innovative, or better than incumbents.
- The current prefix result is statistically confirmed across label methods.
- A 70.6% integration rate is an agent success rate or a comparison against incumbents.
- Prefix/supplied-label agreement is independent human validation.
- The corrected 41-repository cohort represents all AIDev repositories.

## Required gate before rewriting `main.tex`

1. Run predicted-label specialization for the 30/60/90/120-day windows and confidence-margin thresholds already defined in `scripts/run_predicted_specialization.py`.
2. Check whether breadth expansion and entrant rarity keep the same sign and useful magnitude under repository-disjoint and temporal classifier limitations.
3. Re-run the explicit-prefix window/minimum sensitivity with the corrected full outcome window; the current `sensitivity.json` is stale for that rule.
4. Add repository bootstrap intervals for the three descriptive shares used in Figure 1C.
5. If classifier sensitivity reverses the breadth story, stop the pivot. If breadth is stable but rarity remains imprecise, keep RQ1 descriptive and make portfolio expansion the headline.

**Validation status: Needs revision before external sharing as a result paper. Directionally strong enough to guide the manuscript pivot.**
