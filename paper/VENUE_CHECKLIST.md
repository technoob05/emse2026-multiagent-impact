# EMSE Agentic Software Engineering venue checklist

Verified from official pages on 2026-08-26, and re-verified against the local
copy of the official template on 2026-08-27.

- Journal: Empirical Software Engineering.
- Article type: Research Papers.
- Special issue selection: Agentic Software Engineering.
- Review: single-blind; include author identities.
- Final deadline: 2026-09-28; rolling review.
- Abstract: 150 to 250 words; structured abstract permitted.
- Keywords: 4 to 6.
- References: author-year.
- LaTeX: Springer Nature `sn-jnl`, December 2024 release. The version marker is
  `%Version 3.1 December 2024` on line 1 of the template's own `sn-article.tex`;
  the `\ProvidesClass` date inside `sn-jnl.cls` is stale in every release and is
  not a version signal. Our copies of `sn-jnl.cls` and `sn-basic.bst` are
  byte-identical to that release.
- Class options: `sn-basic` is correct for computer science and gives author-year
  citations. Do not add `Numbered`.
- Peer-review copy: the user manual offers a `referee` option that sets double
  line spacing. The wording is a request, not a requirement, and it doubles the
  page count, so we submit single-spaced. Add it only if an editor asks.
- Structure: `\backmatter` must precede the declarations and the bibliography.
  Back-matter headings use `\bmhead`.
- Declarations: eight headings are expected, each present even when the answer is
  "Not applicable": Funding; Competing interests; Ethics approval and consent to
  participate; Consent for publication; Data availability; Materials
  availability; Code availability; Author contributions.
- Title page: corresponding author needs an active email; ORCID where available;
  affiliation needs department, institution, city, and country.
- Figures: lettering 8 to 12 pt at final size in a sans face. Our figures are
  exported at exactly the 372 pt text width and placed at `\linewidth`, so the
  point size in the code is the point size on the page. The render gate enforces
  an 8 pt floor over every text object including tick labels and legends.
- Figures: Springer lists EPS for vector art and TIFF for halftones. We submit
  PDF, which the `pdflatex` class option exists to support and which is near
  universal in practice. This is a judgement call, not a verified requirement.
- Figures: no subfolders, no subfigure packages, one input file per figure.
- Packages: the manual discourages adding any beyond the class list, and
  discourages manual spacing commands.
- Required: editable sources at every round.
- Generative AI beyond copy editing: disclose in Methods; an LLM is not an author.
- Cover letter: explain special-issue fit and disclose any conference extension.
- No Research Paper page or word limit was stated in the call or journal guide.
- Supplementary Information: cite it as `Online Resource 1`, upload it separately
  as `ESM_1.pdf`, and include title, journal, authors, affiliation, and active
  corresponding email in the file.
- Public code release is encouraged but not expressly mandatory; the current
  manuscript promises a public artifact, so its permanent URL/DOI is a project
  release gate.

## Live portal caveat

On 2026-08-26 the official Editorial Manager landing page displayed `Site under
development. Do not use for live manuscript submission.` Recheck immediately
before upload. If the warning remains, contact the guest editors listed in the
special-issue call. Do not assume a different submission route.

Details and a requirement-to-file map are in
`../docs/decisions/VENUE_SIGNOFF_20260826.md`.

Official sources:

- <https://emsejournal.github.io/special_issues/2026_SI_Agentic_SE.html>
- <https://link.springer.com/journal/10664/submission-guidelines>
- <https://www.springernature.com/gp/authors/campaigns/latex-author-support>
- <https://www.editorialmanager.com/emse/>
