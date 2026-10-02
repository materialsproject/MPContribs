# CoRE MOF data and table schemas

One CoRE MOF Contribution represents one final release structure. A distinct
release structure ID is a distinct contribution, including ASR/FSR/ION variants.

## Native mapping

| MPContribs component | CoRE MOF input / model |
| --- | --- |
| Contribution.identifier | CoRE MOF structureId, unchanged |
| Contribution.formula | Release chemical formula, checked against the structure |
| Contribution.structures | list[pymatgen.Structure], parsed from the release CIF |
| Contribution.data | CoreMofData from schemas/data.py |
| Table named zeoFeatures | One ZeoFeatures row from schemas/zeo_features.py |
| Table named rac5Features | One optional RacFeatures row from schemas/rac_features.py |
| Table named topologySubnets | One Topology row per subnet from schemas/topology.py |
| Contribution.attachments | Native optional component; no initial attachment is prescribed |

The project does not redefine the native Contribution, Structure, or Table
envelope. There is no CoreMofContribution or FinalContribution class.
Identifier, formula, CIF text, lattice, sites, and charge are not duplicated
in CoreMofData. Atomic partial charges in a CIF are not assumed equivalent
to Structure.charge. Local preprocessing explicitly matches CIF charge rows
to atom labels, elements, and periodic coordinates, and attaches the values
as Structure.site_properties["charge"]. Local dictionary and explicit CIF
export checks cover nine samples. Deployed storage and CIF download still
require integration testing and maintainer confirmation.

The three table models are siblings of CoreMofData, not nested data fields.
They validate rows, not DataFrames or complete contributions. At upload time
the caller creates a list of named DataFrames, setting attrs["name"] to the
table names above. Importing a schema does not attach or upload a table.

## Fields and constraints

CoreMofData has 39 fields (15 required, 24 optional): dataset release,
source and references, optional MOFids, searchable structural and metal
summaries, completed checker outcomes and consensus, optional topology
details, and seven searchable Zeo++ summaries.

The seven Zeo++ summaries intentionally appear in data for project-level
search and filtering, while zeoFeatures retains the detailed results.
Preprocessing must keep shared values consistent and omit unavailable
summary values. This does not redefine the native Structure component.

- Fields are camelCase and contain no units.
- Optional fields default to None. Omit absent data keys with
  model_dump(exclude_none=True).
- Source IDs remain strings, including numeric-looking IDs. sourceId is
  limited to 1-64 characters (the observed release maximum is 39).
- Existing proposed limits are retained: commonName 512, doi 128, year
  1000-9999, space group 1-230, and dimensions 0-3.
- MOFid strings have no invented length limit and are not truncated.
- Pydantic built-in positive/nonnegative numeric types are used directly.
  Strict validation rejects booleans as numbers and numeric strings;
  CSV conversion belongs to preprocessing, not custom model validators.
- All numeric results must be finite. Valid scientific zero and false are
  preserved. Signed RAC descriptors are allowed.
- ccdcUrl validates HTTP(S) syntax, not ownership or record identity. Add a
  link only after checking that it refers to the correct CCDC record.

ZeoFeatures has 27 columns: three required availability flags and 24 optional
results. Topology has 10 columns: six required and four optional name/genome
fields. RacFeatures has 264 required numeric descriptors when a row exists.
The RAC table as a whole is optional; missing RAC does not mean 264 zeroes
or a partially populated row. Raw descriptor scales are retained without
assuming a common physical unit.

Register data units separately with client.init_columns. Table unit metadata
must be configured separately; init_columns does not define table columns.
No unit conversion, MOFSimplify renaming, or CIF-header modification is
performed by these models.

## Final-result selection

Only final scientific results belong in contributions. ERROR, TIMEOUT,
PROCESS_ERROR, INPUT_ERROR, retry, runtime, logs, and incomplete pipeline
results are excluded from scientific fields. A completed scientific FAIL
is distinct from an execution failure.

Selection and cross-artifact checks are outside this schema package.
The current project proposal requires all five checkers to complete with
PASS or FAIL outcomes and verifies their recorded consensus. CR, NCR, and
AMBIGUOUS remain scientific outcomes. UNCHECKED/NOT_AVAILABLE are not valid
submitted outcomes. Optional fields alone do not establish finality.

For an otherwise eligible structure, the local proposal omits failed Zeo++
result groups, topology ERROR/PARTIAL details and tables, and unavailable
RAC tables. Verified availability flags and other successful results remain.
Maintainer acceptance of this optional-result policy is still pending.

The v26.0.2 selection additionally excludes these entire contributions for
negative largestFreePathDiameter: FSR-COD-1990-0003, FSR-COD-1998-0013, and
FSR-CSD-2026-0630. This release-specific preprocessing policy does not alter
source values or impose a nonnegative constraint on RAC descriptors.

## Scope of this PR

This is a schema, test, and documentation change. It does not upload the
dataset, add raw CIF/CSV files, or grant publication permissions. Assembly,
ID matching, final selection, unit registration, and submission belong to
the separate preprocessing/upload workflow after review and access approval.

Tests cover field/type/constraint validation, optional defaults, native
component separation, JSON round-trips, and emmet Arrow compatibility.
Live API storage, retrieval, table rendering, and partial-charge/CIF-header
round-trips require separate integration checks.
