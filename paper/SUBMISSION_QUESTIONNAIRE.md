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

We have one earlier five-page paper on the same public dataset, on the
different question of predicting a single pull request's review effort from its
shape at creation time (MSR 2026,
https://doi.org/10.1145/3793302.3793609). This manuscript is not an extension
of it: it shares no cohort, no construct, no method and no result, and the
earlier paper does not study interaction between two products at all. It is
cited in the related work here. The next answer sets the relationship out in
detail.

---

## Q2. Reuse from previous publications

*Paste the text between the rules.*

---

No text, algorithms, proofs, results or findings from any previous publication
by the authors are reused in this manuscript. One dataset is shared with an
earlier paper of ours, and we set that out in full below, because the question
asks about datasets and the honest answer is not simply "none".

The shared dataset. Both this manuscript and our earlier short paper draw on
AIDev, a public dataset of AI-agent pull requests on GitHub published by Li,
Zhang and Hassan (MSR 2026). AIDev is not our dataset; it is a third-party
resource, we make no claim to it, and it is cited as such in both papers. This
manuscript uses it at a single pinned revision, recorded in the manuscript, and
draws on the subset of repositories above one hundred stars.

The earlier paper. Duy Minh Dao Sy, Trung Kiet Huynh, Lam Phu Quy Nguyen, Phu
Hoa Pham, Chi Nguyen Tran, Ha Duong Nguyen Dinh and Bao Tran Truong,
"Early-Stage Prediction of Review Effort in AI-Generated Pull Requests", MSR
2026, pages 954 to 958, https://doi.org/10.1145/3793302.3793609. It is a
five-page short paper. It is cited in the related work of this manuscript, in
the paragraph on agent work in public repositories, and the manuscript states
there that it shares the source dataset and nothing else.

What is not shared. The two papers ask different questions, of different
cohorts, by different methods, and report no finding in common.

- Question. The earlier paper predicts, from a pull request's shape at creation
  time, how much review effort it will draw, and characterises abandonment
  after human feedback. This manuscript measures whether one coding-agent
  product ever answers another product's review point on the public record, and
  what follows when it does. Nothing in the earlier paper concerns interaction
  between two products: it does not analyse review comments, replies to review
  comments, or one agent reviewing another agent's work.
- Cohort. The earlier paper analyses 33,707 agent-authored pull requests from
  2,807 repositories. This manuscript works from a later and larger AIDev
  revision, and its analysis cohorts are constructed for this study alone:
  8,608 pull requests in which one product reviewed another product's change,
  546 matched pairs, and a landmark cohort of 1,067.
- Method. The earlier paper is a supervised classification study reporting area
  under the ROC curve. This manuscript uses exact matching, a landmark design
  with an explicit selection probe, linear probability models with
  repository-clustered standard errors, and placebo exposures.
- Results. No number, table, figure or finding from the earlier paper appears
  in this manuscript, and none of this manuscript's results appeared there.

This manuscript is therefore not an extension of that conference paper, and
none of its content has been published before.

Every cohort analysed here is derived from AIDev by code written for this
study; the derived cohorts and that code are archived at
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

## How the Q2 answer was checked

The prior paper was read rather than recalled. What was compared:

| | MSR 2026 short paper | This manuscript |
|---|---|---|
| Question | Predict a pull request's review effort from its shape at creation time; characterise abandonment after human feedback | Whether one product ever answers another product's review point, and what follows |
| Dataset | AIDev v1.0 | AIDev at a later pinned revision |
| Cohort | 33,707 agent-authored PRs, 2,807 repositories | 8,608 cross-product reviews, 546 matched pairs, 1,067 landmark cohort |
| Method | LightGBM classification, area under the ROC curve | Exact matching, landmark design with a selection probe, linear probability models, placebo exposures |
| Two-product interaction | Not studied. The text contains no occurrence of review comment, reply, cross-agent, or one agent reviewing another | The entire subject |
| Shared results | None | None |

So the dataset is shared and nothing else is. That is what the Q2 answer says.

Two consequences were acted on rather than noted. The manuscript now cites the
earlier paper in its related work, in the paragraph on agent work in public
repositories, which already listed six other AIDev-based studies; leaving our
own out of that list would have read as concealment, and review here is
single-blind so it raises no anonymity question. And the Q1 answer names the
earlier paper too, so a reader who meets it in Q2 has already been told.

What this check still cannot see is unpublished or in-press work. If any exists
that overlaps this study, add it to Q2 before pasting.
