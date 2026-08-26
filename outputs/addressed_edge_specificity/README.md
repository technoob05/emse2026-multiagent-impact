# Addressed-edge specificity falsification

## Paper-safe decision: SUPPORTS_EDGE_SPECIFICITY_WITH_BOUNDARIES

This extension asks whether the addressed-edge result merely separates public
activity from silence. It uses the same frozen landmark cohort as the main
addressed-edge analysis: one first cross-product inline trigger per PR, the PR
must still be open at 48 hours, exposure is observed only by 48 hours, and a
later merge must occur strictly after 48 hours and no later than 30 days.

The fields support a valid **structural** specificity control. Among the
615 PRs with public discussion by 48 hours,
109 have an exact raw parent edge and
506 have a later submitted review or PR comment but
no exact edge. Their raw later-merge rates are
55.0% and
41.7%. The pretrigger-only,
repository-clustered contrast is 12.5 percentage
points (95% CI 1.4 to
23.5). Overlap weighting gives
11.5 points (95% CI
0.3 to
22.8). All leave-one-product-pair-out estimates
remain positive.

The result also has important boundaries. Repository fixed effects keep the
positive sign (15.6 points) but are imprecise (95% CI
-4.4 to 35.6); only
37 repositories contain
both exposure states. Against **any** other visible activity, including the
small movement-only group, the estimate is 10.8
points (95% CI -0.4 to
22.1). Holding the responding account type to a
GitHub `User` gives 11.2 points (95% CI
-0.6 to 23.0). These two
intervals include zero.

Therefore this extension **strengthens but narrows** the main story: an exact
parent edge is a more informative public structural marker than generic later
discussion, and the main result is not only a silence-versus-activity contrast.
It does not establish that exact edges are different from every form of visible
activity, and it does not establish semantic resolution, developer intent,
correctness, or a causal effect.

Packaging gates that did not pass: repository_fe_interval_excludes_zero, any_activity_interval_excludes_zero, user_actor_control_interval_excludes_zero.

## Primary contrast

- **Exposed:** any inline reply with raw `in_reply_to_id == trigger_event_id` by
  the threshold.
- **Control:** a later submitted review or PR-level comment is public by the
  threshold, but no exact-parent reply is public by then.
- **Why it is comparable:** both groups have a visible discussion response.
- **Why it is limited:** conditioning on visible discussion is itself
  post-trigger selection. The contrast is a falsification/specificity check,
  not a causal estimand.

Force pushes are kept out of the primary discussion control because they show
code movement, not discussion. The secondary any-activity contrast adds them.
The user-actor sensitivity excludes PRs whose exact edge was written only by a
non-`User` account from its control group.

## Allowed manuscript sentence

> Among PRs with public discussion by 48 hours, an exact raw parent edge was
> associated with more later merges than discussion without that edge after
> adjustment for measured pretrigger activity. The direction survived overlap,
> time-window, product-pair, and repository checks, although within-repository
> and user-only estimates were imprecise.

## Forbidden interpretations

- the reply caused the later merge;
- the reply accepted, fixed, or resolved the trigger;
- a GitHub `User` row proves manual human reasoning;
- later merge validates the feedback;
- exact-parent routing is superior for correctness or review quality.

Unmeasured attention, difficulty, private discussion, product policy, and
response content can influence both the edge and the outcome.
