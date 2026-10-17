# CoRE MOF contribution schemas

Each Contribution represents one CoRE MOF structure, identified by `structure_id`.
ASR, FSR, and ION records with different identifiers are separate Contributions.
These Pydantic models describe typed scientific results before MPContribs
client serialization.

| Module / model | Component | Shape |
|---|---|---|
| `data.py` / `Data` | `Contribution.data` | 9 groups, 45 leaf fields |
| `zeo_features.py` / `ZeoFeatures` | `zeoFeatures` Table row | 1 row, 27 columns |
| `topology.py` / `Topology` | `topologySubnets` Table row | 1 row per successful subnet, 10 columns |
| `rac_features.py` / `RacFeatures` | `rac5Features` Table row | Optional Table; exactly 1 complete row, 264 numeric columns |

The containing Contribution supplies the native `identifier`, `formula`,
`structures`, and `tables`. Its formula is the metadata
`chemical_formula`. Upload preparation reads the corresponding CIF with
`pymatgen.core.Structure.from_file` and supplies the resulting object in
`structures`. A CIF path is not itself a Structure. Each Table is a pandas
DataFrame named using `attrs["name"]`; its rows are validated with the
corresponding model above. The parent Contribution supplies the association,
so `structure_id` is not repeated as a Table column.

## Searchable data

| Group | Required group? | Required / optional leaves |
|---|---|---|
| `release` | Yes | 1 / 0 |
| `source` | Yes | 3 / 1 |
| `reference` | No | 0 / 3 |
| `mofid` | No | 0 / 2 |
| `crystallography` | No | 0 / 2 |
| `metal` | Yes | 2 / 3 |
| `checker` | Yes | 8 / 0 |
| `topology` | Yes | 1 / 5 |
| `geometry` | No | 0 / 14 |
| **Total** | **5 required, 4 optional** | **15 / 30** |

All supplied values must meet their declared types and constraints. Optional
leaves and optional groups default to `None`. Preparation omits missing data
keys and entirely empty optional groups. Required groups remain required even
if some of their leaves are optional. Scientific zero and false are preserved.

`sourceId` has a 1–64 character bound. Counts are integers, dimensions are 0–3,
and geometric fractions are 0–1. No numerical ceiling is derived from the
observed dataset maximum. Data models allow Pydantic's default type conversion
while retaining field constraints. All Table-row models also permit type conversion; RAC fields use regular floats.
All numeric values must be finite; CSV parsing happens before validation.
MOFid strings are preserved without truncation. Both versions may coexist for
the same MOF. V1 uses SMILES node/linker representations; V2 postprocesses V1
calculation outputs using metal-node categories and SELFIES linkers.
The outer format is `<components> MOFid-v1.<topology>.cat<n>` or its `v2`
counterpart, with optional `.<revision>` and `;<name>` suffixes. Patterns check
this format while allowing topology placeholders and multiple topology labels;
they do not validate the chemistry of the encoded components.

`metalElements` is a semicolon-separated string. Each supplied symbol must be
a valid element classified as a metal by `pymatgen.core.Element.is_metal`.
The validator preserves the supplied string. Missing values may be `None`;
metalloids are represented separately in `metalloidElements`.

Checker votes use the shared `CheckerStatus` StrEnum (`PASS`, `FAIL`), and
consensus fields use `ConsensusStatus` (`CR`, `NCR`, `AMBIGUOUS`). Values remain
strings in serialized output. These enums constrain labels; consensus agreement
is checked before model validation.

## Geometry and Table correspondence

The API names below adapt the MOFSimplify descriptor names to camelCase.
The laboratory calculations use N2/He probe radii of 1.655/1.32 angstrom.
Matching descriptor definitions does not imply identical values to a calculation
using MOFSimplify's 1.86 angstrom setting.

| Data path | MOFSimplify name | Source | Unit |
|---|---|---|---|
| `geometry.di` | Di | Zeo `largestCavityDiameter` | angstrom |
| `geometry.df` | Df | Zeo `poreLimitingDiameter` | angstrom |
| `geometry.dif` | Dif | Zeo `largestFreePathDiameter` | angstrom |
| `geometry.gsa` | GSA | Zeo `n2AccessibleSurfaceAreaGravimetric` | m^2/g |
| `geometry.vsa` | VSA | Zeo `n2AccessibleSurfaceAreaVolumetric` | m^2/cm^3 |
| `geometry.gpoav` | GPOAV | Zeo `n2AccessibleVolumeGravimetric` | cm^3/g |
| `geometry.gponav` | GPONAV | Zeo `n2NonaccessibleVolumeGravimetric` | cm^3/g |
| `geometry.poav` | POAV | Zeo `n2AccessibleVolumePerCell` | angstrom^3 |
| `geometry.ponav` | PONAV | Zeo `n2NonaccessibleVolumePerCell` | angstrom^3 |
| `geometry.poavVolFrac` | POAV_vol_frac | Zeo `n2AccessibleVolumeFraction` | dimensionless |
| `geometry.ponavVolFrac` | PONAV_vol_frac | Zeo `n2NonaccessibleVolumeFraction` | dimensionless |
| `geometry.cellV` | cell_v | Metadata `cell_volume_A3` | angstrom^3 |
| `geometry.vpov` | VPOV | `poavVolFrac + ponavVolFrac` | dimensionless |
| `geometry.gpov` | GPOV | `vpov / Zeo.density` | cm^3/g |

Eleven values are copied from the Zeo row; one comes from metadata; two are
derived during preparation. The Zeo Table retains its existing names and
columns. Density remains in that Table and is used for the derivation.
`cellV` can exist independently of N2/He availability. `heVoidFraction`
is not a substitute for `vpov`. All derivations and cross-component equality
checks are performed upstream, not by field declarations.

Field descriptions state the physical units, including the Zeo Table's mixed
units. `client.init_columns` configures data paths such as
`geometry.di: "angstrom"`; it does not configure individual Table columns.
Use `""` for dimensionless numerical data and `None` for nonnumeric data.
Unit-bearing data values are prepared after Pydantic validation. No separate
unit file needs to be imported into this schema package.

## Final results and missing values

The current preparation policy requires all five checkers to finish
successfully and produce scientific PASS/FAIL votes. For each checker subset,
all PASS means CR, all FAIL means NCR, and mixed votes mean AMBIGUOUS.
Crash, timeout, incomplete checker outputs, runtime details, and
operational error payloads are not scientific fields in these schemas.

The proposed auxiliary-result policy is:

- Zeo: retain the three verified availability flags; populate only successful
  result groups. An unavailable group's result cells are Python `None`.
  Even if all three flags are false, retain a one-row Table carrying those flags.
- Topology: include summary details and subnet rows only for a successful,
  available parent result. ERROR/PARTIAL parents contribute only
  `data.topology.topologyAvailable = False`.
- RAC: revised autocorrelation descriptors encode atomic properties and
  connectivity for machine-learning use, with a maximum graph depth of 5
  (bond distances 0 through 5). Omit an unavailable Table entirely.
  A supplied row requires all 264
  finite numeric descriptors. Negative and zero descriptors remain valid;
  no common physical unit or rescaling is imposed.

Topology keys are required nonempty strings. The four optional topology
name/genome columns permit the source's empty strings as well as `None`.
These have different in-memory meanings; Table serialization may not retain
that distinction.

These are application-level types. The currently inspected MPContribs client
converts data booleans to "Yes"/"No", Table cells to strings, and missing Table
cells to empty strings. The row schemas are therefore not direct schemas for
unconverted API responses. Live storage, filtering, and display still require
verification with the deployed client and API.

## Validation responsibilities

The schemas validate shape, types, field constraints, and finite numbers.
Preparation checks execution states, availability,
diagnostics, consensus consistency, joins, and geometric derivations.
Pydantic declarations do not run calculations or submit data.

Native components and unit setup follow the
[MPContribs Quickstart](https://docs.materialsproject.org/uploading-data/what-is-mpcontribs#quickstart).
