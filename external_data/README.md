# External data layer

This directory separates third-party research data from the reproducible paper
sources. Raw archives and cloned source repositories are local evidence only and
are excluded from version control and the public submission package.

Tracked provenance records live in `protocol/external_dataset_registry.csv`,
`protocol/external_acquisition_manifest_20260826.csv`, and the dated audits
under `docs/`. Each downloaded source must record its canonical
URL, revision or DOI, retrieval date, license, checksum, local footprint, grain,
and analytical verdict. Derived aggregates may enter `outputs/external_validation/`
only after uniqueness, temporal, join, and construct-validity checks pass.

The current paper does not pool unrelated datasets. An external source is used in
the manuscript only when it reproduces or triangulates one of the three declared
research questions at a compatible observation level.
