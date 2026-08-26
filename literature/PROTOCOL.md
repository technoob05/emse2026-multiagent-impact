# Bounded novelty-update protocol

## Purpose and scope

This is a targeted scoping search for the novelty and claim boundaries of a
paper on sequential coding-agent participation. It is not an exhaustive
systematic literature review: it has no database-grade deduplication, dual
screening, or complete Scopus/Web of Science export. The defensible conclusion
is therefore "no direct study identified in the searched sources," not proof
that no such study exists.

- Search/update date: 2026-08-25
- Corpus of interest: empirical studies of coding-agent pull requests,
  longitudinal tool adoption, contributor effects, agentic code review, and
  multi-agent software-engineering workflows.
- Primary evidence routes: official AIDev paper ledger; MSR 2026 Mining
  Challenge programme; ACM, SAGE, and Springer publisher pages; arXiv title,
  abstract, and full-text pages; the EMSE Agentic Software Engineering call.
- Language: English.
- Evidence status: bibliographic metadata and the specific overlap-relevant
  claim must be verifiable from a publisher page, paper abstract, or full text.

## Eligibility

Include a work when it contains empirical or conceptual evidence relevant to
at least one of: coding-agent adoption, PR integration/rejection, sequential or
concurrent agent participation, contributor identity/role, review dynamics, or
multi-agent software engineering. Exclude generic LLM coding benchmarks with no
longitudinal software-evolution or multi-agent implication.

## Target unit and novelty test

The target observational unit is a pair of non-overlapping PR episodes in the
same repository where the earlier PR's outcome is known before the later PR is
opened. A direct novelty collision would additionally distinguish:

1. same versus different coding-agent brand; and
2. same versus different contributor identity.

## Claim boundaries

- `closed-unmerged` is an observed integration outcome, not verified agent
  failure.
- A brand transition is not evidence that a maintainer deliberately replaced a
  tool.
- Merge within 30 days is integration, not software quality or trust.
- Repository traces show sequential ecosystem participation, not agent-agent
  coordination.
- All effect language is associational unless a later identification strategy
  warrants a causal claim.

## Update rule

Re-run the logged queries before submission, add forward/backward citation
chasing for the closest overlaps, and freeze an updated evidence map. A claim of
systematic or exhaustive coverage requires a separate protocol, database
exports, deduplication, and dual screening.
