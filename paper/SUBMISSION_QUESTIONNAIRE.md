# Additional Information questionnaire — answers to paste

Editorial Manager's Additional Information step. The two free-text boxes are
written out below in full; paste them as plain text, since the boxes are not
Markdown. Every number in them is taken from the manuscript, not restated from
memory, and each appears in `main.tex`.

The character limit on both boxes is 20,000.

---

## Q1. Journal first submission: what is new here

*Paste the text between the rules.*

---

This manuscript reports original, previously unpublished research. It has no
prior conference version, and no part of it has appeared elsewhere.

The contribution is a measurement that, to our knowledge, has not been made
before: how often the public record can show one AI coding agent actually
answering another on a pull request, and what follows when it does.

Studies of "multi-agent" software engineering, and the tooling that reports on
it, routinely treat the presence of two coding-agent products on one pull
request as collaboration. Sharing a page is not answering each other. We
separate the two by building an evidence ladder over the public record, from
both products merely being present, through one acting after the other, to one
answering a specific review point that the platform itself links by identifier
rather than by timing.

New empirical results:

1. Cross-product review is common and cross-product answering is not. Across
   8,608 pull requests in which one product reviewed a change another product
   wrote, one product answers another's review point on 74 of them: fewer than
   one in a hundred. Counting products present overstates multi-agent work by
   roughly two orders of magnitude relative to counting connections.

2. What connects the work is a person, not another product. User accounts write
   four in five of the replies GitHub records as answers to a review point. The
   strongest edge in the graph runs through a human, which is the result the
   title names and the one that has the clearest consequence for how "AI
   teammate" work is reported.

3. Crossing the product boundary costs follow-up. Against 546 within-product
   reviews matched exactly on repository, pull-request author account, the
   product that wrote the change, the channel the trigger arrived on, and
   calendar month, review across a product boundary draws about 13 points less
   visible follow-up than its matched twin.

4. An answered review point goes with more later merging, but the exact link
   buys attribution rather than prediction. In a landmark cohort of 1,067 pull
   requests still open two days after the review, an answered review point is
   associated with 11 to 17 points more later merging. The range is not
   hedging: 17.3 points is the landmark estimate, and a landmark-free reading
   of the same data gives 11.2, because conditioning on survival to the
   landmark is itself selective, and we report both rather than the flattering
   one. Crucially, a reply anchored somewhere else does about as well, and
   shuffling the anchors barely moves the estimate. The exact platform link
   tells us who answered what; it does not carry predictive content beyond a
   reply happening at all. We state this against our own headline number.

5. Issue linkage moves the answer rate only across the boundary. Linking an
   issue roughly doubles the raw cross-product answer rate and changes nothing
   inside a single product, which points at coordination cost rather than at a
   general property of linked work.

Methodological contributions:

- An addressed-edge construct tied to GitHub's own reply identifiers rather
  than to temporal proximity, checked release-wide: across all inline replies
  in the release, none names a comment that is itself a reply, so the reply
  graph is one level deep and "a reply in the thread the trigger opened" is
  well defined.
- A landmark design with an explicit selection probe. Rather than assert that
  the hour-48 landmark is innocuous, we measure what it costs and report the
  landmark-free estimate beside the landmark one.
- Deliberately wrong anchors as placebo exposures, off target, permuted, and
  time-shifted, so that a reader can see what the design yields when the signal
  it claims to measure is removed.
- A public artifact carrying the derived cohorts and every analysis and figure
  script, archived at https://doi.org/10.5281/zenodo.22140821, so that each
  number above can be recomputed rather than taken on trust.

The source data are the public AIDev release of AI-agent pull requests, which
is a third-party dataset by other authors and is cited as such. We use it at a
pinned revision. The cohorts, the constructs, the design, the analyses and all
findings above are new in this manuscript.

---

## Q2. Reuse from previous publications

*Paste the text between the rules.*

---

No text, algorithms, proofs, results or findings from any previous publication
by the authors are reused in this manuscript. There is no prior conference
version of this work, and it is not an extension of one. None of the authors'
earlier papers is cited here, because none of them bears on this study.

One external resource is reused and is credited rather than claimed. The source
data are the public AIDev dataset of AI-agent pull requests, published by Li,
Zhang and Hassan (MSR 2026), which we use at a single pinned revision recorded
in the manuscript. AIDev is not our dataset and we make no claim to it. Every
cohort we analyse is derived from it by code written for this study, and both
the derived cohorts and that code are archived at
https://doi.org/10.5281/zenodo.22140821.

The manuscript also uses the Springer sn-jnl class and style files supplied by
the journal for formatting only.

---

## The remaining answers

| Question | Answer | Why |
|---|---|---|
| Does the paper qualify as a journal first submission? | **Yes** | No prior conference version exists. The cover letter states the work has not been published previously and is not under review elsewhere. |
| Research Square author dashboard | **Tick the box** | It is the only selectable response, so the submission cannot proceed without it. Ticking acknowledges that the manuscript and personal data go to Research Square for the dashboard; the services it offers are optional, confidential, and do not reach the editors. |
| Data availability statement included in the main manuscript file? | **Tick to confirm** | It is present, under `Statements and Declarations`, and names both the pinned public source release and the archived derived cohorts. |
| Which statement best describes data accessibility? | **My manuscript has associated data in a data repository** | The derived cohorts and code are deposited at `https://doi.org/10.5281/zenodo.22140821`, and the source data are a public release. Online Resource 1 is a document of tables rather than the data itself, so the electronic-supplementary-material option would describe the submission less accurately. |
| Does this manuscript belong to a special issue? | **Yes** | Agentic Software Engineering: The Rise of AI Teammates. Select that issue when prompted. |
| Publishing terms and conditions | **Tick to agree** | Required to submit. Covers Springer Nature's updated terms on AI usage in the licence to publish. |

## One thing the authors must check, which this file cannot

Q2 asks about reuse from *your* previous publications. The check behind the
answer above is that no author of this manuscript appears in `references.bib`
and that the manuscript makes no self-citation, which is verifiable from the
repository. What the repository cannot see is unpublished or in-press work of
the authors that overlaps this study. If any exists, say so in Q2 rather than
pasting the text unchanged.
