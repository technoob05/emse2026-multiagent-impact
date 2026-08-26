# Research brief

## Proposed paper

**Working title:** *Co-Presence Is Not Coordination: Artifact-Level Handoff
Scarcity in Multi-Agent Software Repositories*

## Three-RQ narrative

- **RQ1 — Return:** After a closed-unmerged coding-agent PR, how often does the
  same exact file appear in a later coding-agent PR within 30 days?
- **RQ2 — Reconfiguration:** For the first exact-file successor, how often do
  the contributor and named agent remain the same or change?
- **RQ3 — Recovery and context:** How are the four reconfiguration modes linked
  to 30-day recovery, and does the result survive repository clustering,
  stricter file links, unique-successor checks, and within-context comparison?

## Novelty boundary

The paper does not introduce agent handoff as a concept. *Handoff Debt* already
studies context transfer in controlled coding-agent takeovers. Our residual
novelty is ecosystem evidence: how often an observable exact-file successor
uses a new agent in real repositories, who changes with it, and whether any raw
recovery difference is stable across project contexts.

The paper is also not a concurrent-conflict study, product ranking, or claim
that agents communicate. Exact path reuse is an artifact-continuity signal, not
proof of intent.

## Go/no-go criteria

Proceed if:

1. exact-file successor construction remains deterministic and leakage-free;
2. denominators, censoring, path coverage, ties, and successor reuse are visible;
3. manual audit shows that the primary link is useful beyond generic files;
4. repository-aware and unique-successor sensitivities are reported; and
5. causal and anthropomorphic wording is removed.

## Practical contribution

Repositories need explicit handoff records: the failed attempt, touched files,
open review points, tests, and reason for stopping. Multiple agent labels in a
repository do not provide this context by themselves.
