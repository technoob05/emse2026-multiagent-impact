# Legacy experiment audit — 2026-08-26

Full reproducible memo: `outputs/legacy_extensions/README.md`.

## Final recommendation

Keep one main new mechanism: **repository-memory bridge**. Of 3,603 cross-product-feedback PRs with a first observable `User`-type responder within 48 hours, 2,567 (71.2%) responders had reviewed a different PR in the same repository before the trigger. This includes 920/1,372 (67.1%) author accounts and 1,647/2,231 (73.8%) other user accounts. Among 2,020 cases where the first later decisive review overall belonged to a user account, 1,580 (78.2%) had strict prior repository review history.

The strict join is same repository, same login, different PR, and review time strictly before trigger. All valid history matches pass the no-same-PR and no-future/equal checks. Repository leave-one-out gives 69.4%-72.0%; product-pair leave-one-out gives 69.4%-73.8%. The largest repository contributes 6.1%; the largest product pair 31.3%.

Use the all-responder baseline honestly: 3,381/4,814 (70.2%) distinct PR-account responders have prior review history. Thus repository experience is common in the response layer, but the data do not show strong preferential selection of experienced accounts as the first responder.

Reject intentional-routing inference. Although 6,343/8,608 (73.7%) PRs have a valid review request before the trigger, requested-account coverage is 0/10,402 request events. Last requester roles are author account 4,545, other user-like 1,162, mapped agent 546, and other bot 90. The safe statement is only that a review request existed; the triggering product cannot be identified as its target.

Ranked cards, schema audit, legacy-method reuse/reject decisions, exact output paths, and paper-safe wording are in `outputs/legacy_extensions/README.md`. No manuscript file was edited.
