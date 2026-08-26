# EMSE Agentic Software Engineering venue sign-off

Checked against official pages on 2026-08-26. This audit separates stated
requirements from items that the public pages do not specify.

## Verified requirements

| Item | Official requirement | Project state |
|---|---|---|
| Article route | Select `Research Papers`; answer yes to the special-issue question; select `Agentic Software Engineering` | Ready |
| Schedule | Rolling review; final deadline 2026-09-28; no deadline time zone stated | Record and recheck |
| Review model | Single-blind; author identities remain in the paper | Aligned |
| Abstract and keywords | 150–250 words; 4–6 keywords; structured abstract permitted | Aligned |
| Headings | No more than three heading levels | Aligned |
| Source | Editable source at each round; LaTeX accepted and Springer Nature template recommended; no source subfolders | Aligned in portal staging |
| Cover letter | Explain fit to the special issue; explain added research for any conference extension | Draft ready; extension choice pending |
| Data | Original research must contain a Data Availability Statement; a public repository and persistent data citation are strongly encouraged | Source dataset pinned; artifact DOI pending |
| Declarations | Funding, competing interests, ethics, consent, data/material/code availability, and author contributions | Headings present; author wording pending |
| AI use | LLMs are not authors; substantive use belongs in Methods; humans remain accountable | Aligned; explicit human verification added |
| Supplementary Information | Cite as `Online Resource 1`; supply PDF as a separate, consecutively named item with caption and full title/author/contact metadata | Staged as `ESM_1.pdf`; author metadata pending |

The current official pages do **not** state a maximum manuscript page count,
manuscript word count, SI PDF size limit, deadline time zone, mandatory reviewer
count, exact upload item labels, or a requirement for a standalone title-page
PDF. Record these as “not stated,” never as “unlimited” or “not required.”

## Portal warning

The special-issue call directs authors to Editorial Manager, but the live EMSE
landing page displayed this warning on 2026-08-26: “Site under development. Do
not use for live manuscript submission.” Do not upload while that warning is
present. Recheck close to submission. If it remains, contact the listed guest
editors:

- Ahmed E. Hassan — `ahmed@cs.queensu.ca`
- Hao Li — `hao.li@queensu.ca`
- Haoxiang Zhang — `haoxiang.zhang@queensu.ca`

## Portal staging map

The build creates `build/submission/emse_portal_staging/`:

| Staged file | Intended role |
|---|---|
| `manuscript.pdf` | Reviewer-facing manuscript PDF |
| `manuscript_source.zip` | Flat editable source for `main.tex` only |
| `ESM_1.pdf` | Online Resource 1 / Supplementary Information |
| `CHECKSUMS.sha256` | Local integrity record; retain locally unless the portal asks for it |

The cover letter remains separate until its date, correspondence details,
original-versus-extension choice, and author confirmations are complete.

## Remaining release gates

- Exact affiliation, city, country, corresponding email, and ORCID decisions.
- Funding, competing interests, ethics/consent, acknowledgements, and author contributions.
- Permanent public artifact URL/DOI.
- Conference-extension choice and all-author/not-under-review confirmation.
- Rebuild, page-complete visual QA, and clean portal-bundle smoke test after those values are inserted.
- Live portal warning cleared or an alternative route confirmed by a guest editor.

## Official sources

- [Special-issue call](https://emsejournal.github.io/special_issues/2026_SI_Agentic_SE.html)
- [EMSE submission guidelines](https://link.springer.com/journal/10664/submission-guidelines)
- [Springer Nature LaTeX support](https://www.springernature.com/gp/authors/campaigns/latex-author-support)
- [EMSE Editorial Manager](https://www.editorialmanager.com/emse/)

