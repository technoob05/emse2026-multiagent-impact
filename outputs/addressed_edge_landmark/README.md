# Addressed-edge landmark analysis

## Packaging decision: MAIN_CANDIDATE

This result is eligible as a **main-result candidate only in observational,
structural language**. It should replace, not stack on top of, another
route-to-merge headline. Model A is the primary specification. Model B is a
secondary decomposition because `ownership_route_48h` is post-trigger and can
partly mediate or proxy the exact reply; it is not a safer causal adjustment.

At 48 hours, 109/1,067 PRs have an inline reply whose raw
`in_reply_to_id` equals the exact cross-product trigger id. Later merge is
55.0% with this edge and
37.9% without it. The
repository-clustered pretrigger-adjusted LPM difference is
17.3 percentage points (95% CI
7.3 to 27.4). The repository-FE
sensitivity is 18.6 points (95% CI
3.7 to 33.5). Adding the 48-hour
ownership route gives 11.6 points (95% CI
0.9 to 22.3); this is decomposition,
not a direct effect. The largest ordered product pair supplies
35.8% of exposed PRs and the
largest repository supplies 5.5%.

Pre-specified packaging gates failed: none.

## Exact question and grain

- **Grain:** one PR's first recognized cross-product inline-review trigger,
  restricted to PRs still open 48 hours after that trigger and to triggers with
  a complete 30-day horizon.
- **Exposure:** any raw inline reply with `in_reply_to_id == trigger_event_id`
  by 1, 6, 24, or 48 hours. This proves a public parent edge only.
- **Outcome:** merge strictly after trigger + 48 hours and no later than trigger
  + 30 days.
- **Model A:** exact-edge indicator, author product, reviewer product, trigger
  month, trigger age, pretrigger interaction counts, pretrigger decisive reviews,
  and pretrigger force pushes; repository-clustered uncertainty.
- **Model B:** Model A plus the 48-hour ownership route as a secondary
  post-trigger decomposition.
- **Sensitivity:** repository fixed effects and leave-one-ordered-product-pair-out.

The exact column schema is in `schema.json`; denominators are in
`denominators.csv`; temporal assertions are in
`temporal_leakage_validation.json`.

## Novelty boundary

[Zhong et al. (2026)](https://arxiv.org/abs/2607.13196) model broad sequences of
human, LLM, and agent reviewer types and relate those sequences to review
efficiency and quality. This analysis is narrower: it starts from one
cross-product inline trigger and requires the raw GitHub parent id to point back
to that exact trigger. It does not claim the first study of multi-agent review
sequences.

[Cynthia et al. (2026)](https://arxiv.org/abs/2607.21997) study developer
responses and resolution of agent-generated review comments, including content
and developer roles. This analysis does **not** label response semantics,
actionability, resolution, or developer intent. A direct parent edge may
acknowledge, reject, question, or merely mention the trigger. Later merge does
not prove that feedback was correct or resolved.

## Allowed and forbidden interpretation

Allowed:

> Among inline-trigger PRs still open at 48 hours, an observed exact-parent
> reply by the landmark is associated with a higher probability of later public
> merge after adjustment for measured pretrigger activity. The association is
> stable to the reported pair and repository sensitivities.

Forbidden:

- direct replies cause merge;
- the reply resolved, fixed, accepted, or correctly addressed the feedback;
- a user account necessarily represents manual human reasoning;
- later merge validates either review comment;
- the estimate is an interoperability effect between products.

Unmeasured maintainer attention, task difficulty, private coordination, product
policy, and reply content can select both exposure and outcome. The analysis is
therefore associational even when the interval excludes zero.
