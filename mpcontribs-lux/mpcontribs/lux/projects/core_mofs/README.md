# CoRE MOF Lux schema

## Contribution definition

A CoRE MOF contribution is one final, release-preserved structure identified
by a unique `structureId`. ASR, FSR, and ION representations are separate
contributions when they have distinct identifiers.

Only final, publication-authorized structures with five successfully completed
PASS checker outcomes (the strict five-checker CR subset) are selected before
submission. Pipeline failures, non-CR structures, non-final intermediate
results, diagnostics, logs, runtimes, file paths, manifests, and retry
information are filtered out before submission. The Pydantic model validates
the shape of a selected record; it does not reproduce pipeline aggregation
rules.

Raw release artifacts such as metadata CSV, checker findings, Zeo++ features,
topology output, and calculation diagnostics do not independently define a
contribution. They are source artifacts associated through `structureId`.

## Initial schema scope

The initial `CoreMofContribution` contains:

- the release-preserved structure identifier;
- the original CIF text;
- a pymatgen `Structure` containing lattice, sites, and charge;
- source database, source identifier, and structure variant;
- optional formula, common name, DOI, and publication year.

Checker findings and topology are deferred until their user-facing shape and
final-data policy are agreed in a later review round. Zeo++ features are
deferred because they are likely to become an MPContribs Table.

All field names use camelCase. Units are not encoded in field names and are
assigned through `client.init_columns` during upload. Optional fields default
to `None`.
