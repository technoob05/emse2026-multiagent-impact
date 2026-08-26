# Novelty position for the submitted paper

Date: 26 August 2026.
Scope: this file describes the novelty of the **current** manuscript,
"Participation Is Not Collaboration". It replaces `NOVELTY_AUDIT.md`, which
describes the pre-pivot study and is kept only as a record.

Every competing paper below was checked by fetching its page. Claims about what
a competitor does are taken from its own abstract or full text, not from
memory.

## The claim, in one sentence

When you stop counting products on a pull request and instead demand a
machine-checkable link — a reply whose parent identifier is the trigger comment
itself — the multi-agent story collapses into a human one, and that link behaves
differently from ordinary discussion.

## Contribution-by-contribution standing

| # | Contribution | Standing | Closest occupant |
|---|---|---|---|
| 1 | Evidence ladder: co-presence → addressed edge → next owner → later state, with an hour-48 check point that keeps exposure before outcome | **Partly open.** No paper combines these. Components are occupied separately. We found no software-engineering paper using a landmark design on PR merge. | Selvanayagam and Ghaleb do co-presence and latency, and explicitly do not do reply-parent edges, review de-batching, burst washout, next actor, or merge |
| 2 | Cross-product review almost never becomes a different-product relay | **Largely pre-empted.** Report it as a refinement, not a discovery. | Selvanayagam and Ghaleb already publish cross-product review at 1.6% of agent-authored PRs with a 1.2-minute median latency, on the same data family |
| 3 | Matched cross- versus same-product follow-up | **Open.** The matched-pair idiom exists; this contrast does not. | Duma et al. use matched repositories, but for AI versus human PRs |
| 4 | Addressed edge and later merge | **Direction occupied, identification not.** | Chowdhury et al. report agent-only PRs merging at 45.2% against 68.4% for human-only. Zhong et al. and Duma et al. reach the same "people carry the review" conclusion. What is not occupied: the exact parent-identifier exposure, the landmark, the E-value, and the within-repository shuffle test |
| 5 | Within-PR order shuffle as a null model for sequence claims | **Open. Nothing found.** | Bouraffa et al. are the only prior work on whether review order is meaningful, and they benchmark against alphabetical order, not a permuted null |

## What a reviewer will say is not novel

That the *findings* are public and only the plumbing is new. Cross-product
review being rare and fast is already published on the same data family. "People
still do the real work" is the conclusion of at least three papers from the last
eight months. "Engagement relates to merge" is Chowdhury et al.'s headline.

The honest answer is that we agree, and that this is the point: the paper's
contribution is measurement discipline that changes the conclusion, not a new
phenomenon. We therefore frame contribution 2 as a refinement of a published
result, and we state in the article that we do not claim the first observation
of AI-to-AI review.

A reviewer will also press on power and scope, and the article now says all of
it in the body rather than the appendix: the outcome group is the 27% of
cross-product inline-trigger PRs still open at hour 48, only 109 PRs carry the
exposure, three of the exposure events are agent-to-agent, and one
before-the-fact control is not centred on zero.

## Where contribution 5 needs work

The order shuffle is correct and, as far as we can find, unpublished for
reviewer or agent sequences. But permutation nulls are standard in temporal
network and ecological analysis, so a methods-literate reviewer will call it
correct rather than new. It is now named as a contribution in the introduction
and anchored to the review-order literature. The stronger version, not done
here, would apply it to a published sequence claim rather than only to our own.

## Verified competing work added to the bibliography

- Chowdhury et al., MSR 2026, arXiv:2604.03196 — code review agents in PRs.
- Fatima et al., MSR 2026, arXiv:2604.24450 — reviewer-bot feedback quality
  shows no clear link to workflow outcomes. Held next to our result as a
  tension, not omitted.
- Zhong et al., arXiv:2603.15911 — human-AI synergy over 278,790 conversations.
- Duma et al., EASE 2026, arXiv:2605.02273 — most AI-generated PRs get no
  review; uses AIDev.
- Bouraffa et al., EASE 2025, arXiv:2506.10654 — meaningful code review orders.

## Not cited, and why

Two further candidates surfaced during the search but their arXiv identifiers
could not be confirmed by fetching the page. They are deliberately left out. A
missing citation is recoverable; a fabricated one is not.
