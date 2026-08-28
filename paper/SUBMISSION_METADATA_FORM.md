# Author and submission metadata form

Complete this file before replacing any placeholder in the manuscript. Do not
infer names, affiliations, ORCIDs, funding, ethics decisions, or contribution
roles from web profiles. Every author should approve the final entry.

## Manuscript identity

- Title: *Participation Is Not Collaboration: When One LLM Coding Agent Reviews Another on GitHub, a Person Answers*
- Journal: *Empirical Software Engineering*
- Article type: `Research Papers`
- Special issue: `Agentic Software Engineering`
- Corresponding author: Dao Sy Duy Minh, 23122041@student.hcmus.edu.vn
- Joint first authors: Dao Sy Duy Minh and Huynh Trung Kiet contributed
  equally; the manuscript carries an equal-contribution footnote on both.

## Author records

| Order | Name exactly as it should appear | Given name (portal field) | Family name (portal field) | Department | Institution | City | Country | ORCID | Corresponding? | Email if corresponding |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | Duy Minh Dao Sy | Duy Minh | Dao Sy | Faculty of Information Technology | Ho Chi Minh City University of Science (HCMUS), and Vietnam National University Ho Chi Minh City (VNU-HCM) | Ho Chi Minh City | Vietnam | 0009-0002-4501-2788 | yes | 23122041@student.hcmus.edu.vn |
| 2 | Trung Kiet Huynh | Trung Kiet | Huynh | Faculty of Information Technology | HCMUS, and VNU-HCM | Ho Chi Minh City | Vietnam | 0009-0000-5463-754X | no | --- |
| 3 | Chi Nguyen Tran | Chi Nguyen | Tran | Faculty of Information Technology | HCMUS, and VNU-HCM | Ho Chi Minh City | Vietnam | 0009-0007-6716-7269 | no | --- |
| 4 | Phu Hoa Pham | Phu Hoa | Pham | Faculty of Information Technology | HCMUS, and VNU-HCM | Ho Chi Minh City | Vietnam | 0009-0001-5471-2578 | no | --- |
| 5 | Lam Phu Quy Nguyen | Lam Phu Quy | Nguyen | Faculty of Information Technology | HCMUS, and VNU-HCM | Ho Chi Minh City | Vietnam | 0009-0002-9694-8105 | no | --- |

Both affiliations apply to all five authors: affiliation 1 is the Faculty of
Information Technology at HCMUS, affiliation 2 is VNU-HCM. This matches
`\affil` in main.tex and technical_appendix.tex.

The five ORCIDs are filled in. They were not matched by name, which for
Vietnamese family names would be worthless: they come from the Crossref
records of two published papers, 10.1145/3793302.3793609 (MSR 2026) and
10.1145/3803437.3808242 (FSE 2026), which carry this exact five-person
author set at this faculty with ORCIDs deposited by the publisher. Each was
then cross-checked against the ORCID record's own HCMUS or VNU-HCM
affiliation. Confirm them anyway before submitting: they are the authors'
to own.

All five authors carry both affiliations, so no per-author mapping is needed.

### Candidate values found in prior author material (confirm before use)

- Four authors (Dao Sy Duy Minh, Huynh Trung Kiet, Pham Phu Hoa, and Nguyen Lam
  Phu Quy) consistently appear with `Faculty of Information Technology,
  University of Science, Vietnam National University Ho Chi Minh City, Ho Chi
  Minh City, Vietnam` in prior local author material.
- Tran Chi Nguyen appears with that affiliation in the earlier AIDev paper but
  with HCMUT/VNU-HCM in another manuscript. His current affiliation is not safe
  to infer.
- Candidate institutional emails are recorded in the private audit at
  `../docs/audits/AUTHOR_METADATA_AUDIT_20260826.md`.
- Structured family names are ambiguous. Prior sources alternate between forms
  such as `Dao-Sy Duy-Minh` and `Duy-Minh Dao-Sy`; the current Springer fields
  instead treat the final token as the family name. Confirm the indexed
  given/family-name split for every author, not only the display string.

## Statements and Declarations

Replace each bracket with author-approved wording.

- Funding: No funding was received for this work.
- Competing interests: None. No author is affiliated with, employed by, or
  funded by any of the coding-agent vendors whose products this study measures.
- Ethics approval: Not required. The study analyses pull-request records that
  GitHub already publishes, gathered through a public research dataset, with no
  intervention and no interaction with any person.
- Consent to participate: Not applicable. No participants were recruited.
- Consent for publication: Not applicable. No individual-level identifying
  information is reproduced; accounts are reported by role and in aggregate.
- Data availability: Source data is the public AIDev-7.6M release at the
  pinned revision given in the Method. Derived cohorts are archived at
  `https://doi.org/10.5281/zenodo.22140821`, which is published, open and
  resolving. Paste that DOI verbatim into the portal's data-availability field
  rather than the GitHub URL.
- Code availability: https://github.com/technoob05/emse2026-multiagent-impact,
  archived with the derived cohorts at the same artifact DOI.
- Acknowledgements: None; the manuscript has no acknowledgements section.
- Permissions: Every figure and table is original and generated by the code in
  the artifact. No third-party material is reproduced.

## Author contributions

Use only roles that each author confirms. Suggested CRediT vocabulary:
Conceptualization; Data curation; Formal analysis; Funding acquisition;
Investigation; Methodology; Project administration; Resources; Software;
Supervision; Validation; Visualization; Writing—original draft;
Writing—review and editing.

The two `Writing` roles are spelled with a dash because that is the CRediT
taxonomy's own wording, not this project's prose style. Copy both strings into
Editorial Manager exactly as they appear above.

| Author | Roles as declared in the manuscript |
|---|---|
| Duy Minh Dao Sy | Conceptualization; Methodology; Formal analysis; Software; Visualization; Writing---original draft |
| Trung Kiet Huynh | Conceptualization; Methodology; Data curation; Software; Validation; Writing---review and editing |
| Chi Nguyen Tran | Investigation; Data curation; Validation |
| Phu Hoa Pham | Investigation; Software; Validation |
| Lam Phu Quy Nguyen | Investigation; Validation; Writing---review and editing |

Duy Minh Dao Sy and Trung Kiet Huynh contributed equally. All authors read and
approved the final manuscript.

## Required confirmations

- [ ] Every author approved the exact name spelling, order, affiliations, and corresponding-author choice.
- [ ] Every author approved the manuscript and Supplementary Information.
- [ ] The work is not published, submitted, or under review elsewhere.
- [ ] Choose one cover-letter path: this is not a conference extension; or identify the conference paper and state the added research and overlap.
- [ ] All statements and declarations above are author-approved.
- [ ] The artifact DOI resolves without authentication and contains the released code, environment lock, derived cohorts, and documentation promised in the paper.
- [ ] Recheck the live Editorial Manager warning before upload.

## Optional portal information

Suggested reviewers are optional in the public EMSE instructions. If the portal
asks for them, record independent candidates with institutional emails and a
homepage, publication profile, or researcher ID. Do not nominate close
collaborators, recent co-authors, or anyone with a conflict of interest.
