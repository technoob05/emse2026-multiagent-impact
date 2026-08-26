# Cross-corpus attribution sensitivity

This check joins the paper's fixed AIDev landmark cohort to the independently
released AI-to-AI cross-product cohort derived from CodAGE. The join uses only
public repository name, PR number, and product labels. It does not import an
outcome or post-trigger feature from CodAGE.

Of 123 landmark PRs that appear in the external cross-product cohort,
119 agree on the exact author-reviewer product pair. The median absolute
difference between the two sources' trigger timestamps is 0.00 hours.

The exact-pair overlap is too small for a new headline: only 9 PRs
contain an exact edge. The raw later-merge difference is +14.6
percentage points, and the pre-trigger-adjusted difference is
+11.1 points with a wide interval
[-23.9, +46.1]. The direction
is a useful attribution sensitivity, but this is not an independent outcome
replication because both corpora observe public GitHub activity and overlap only
partly.

Safe use: appendix measurement check. Unsafe use: claiming external replication,
causality, semantic resolution, or product-general impact.
