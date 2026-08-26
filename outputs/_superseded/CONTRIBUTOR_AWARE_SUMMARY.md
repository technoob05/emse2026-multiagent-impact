# Contributor-aware impact exploration

## Central insight

The aggregate agent-switch contrast hides opposing transition types. Following
an outcome-known closed-unmerged PR:

- same contributor, different agent: 72.7% merged within 30 days;
- same contributor, same agent: 59.1%;
- different contributor, same agent: 51.9%; and
- different contributor, different agent: 61.5%.

The raw same-contributor brand-change contrast is
13.63 percentage points.
In the within-repository linear probability model adjusting for current/prior
agent, calendar month, and inter-episode gap, the corresponding coefficient is
7.88 percentage points (95% CI
2.08, 13.68).
This is an association, not a causal recovery effect.

## Composition after closed-unmerged outcomes

- same-contributor brand change: 5.2%;
- contributor change with stable agent: 5.6%;
- joint contributor/agent reconfiguration: 26.0%; and
- persistence: 63.1%.

## Interpretation boundary

The same-contributor/different-agent cell is the strongest observable proxy for
a person changing coding-agent brand, but trace data still do not reveal intent,
decision-maker, task equivalence, or account sharing. Different-contributor
cells must not be described as individual tool switching.
