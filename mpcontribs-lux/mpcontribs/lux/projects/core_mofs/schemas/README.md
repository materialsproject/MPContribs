# CoRE MOF contribution schemas

Each Contribution represents one CoRE MOF structure with a unique identifier.
The native `identifier`, `formula`, `structures`, and `tables` components describe
the record identity, chemical formula, pymatgen Structures, and attached Tables.

| Module | Model | Component |
|---|---|---|
| `data.py` | `Data` | `Contribution.data`: 9 groups, 44 input fields and 2 computed output fields |
| `zeo_features.py` | `ZeoFeatures` | One `zeoFeatures` Table row, with 26 columns |
| `topology.py` | `Topology` | One row per subnet in `topologySubnets`, with 10 columns |
| `rac_features.py` | `RacFeatures` | An optional `rac5Features` Table with one row and 264 numeric columns |

Table names identify the attached components. Each row is described by its
corresponding Pydantic model; the containing Contribution associates the Tables
with the structure.

## Data groups

| Group | Required group | Required input fields | Optional input fields |
|---|---|---:|---:|
| `release` | Yes | 1 | 0 |
| `source` | Yes | 3 | 1 |
| `reference` | No | 0 | 3 |
| `mofid` | No | 0 | 2 |
| `crystallography` | No | 0 | 2 |
| `metal` | Yes | 2 | 3 |
| `checker` | Yes | 8 | 0 |
| `topology` | Yes | 1 | 5 |
| `geometry` | No | 0 | 13 |
| **Total** | **5 required groups** | **15** | **29** |

These counts describe field declarations. When topology is available, its five
summary keys are additionally required by model validation. The geometry group
has two computed fields, giving 15 geometry output fields and 46 data output
fields overall.

Optional fields default to `None`. Numeric values must be finite, and their
declared ranges apply after ordinary Pydantic type conversion. Booleans are
rejected as numeric inputs. Scientific zero and false are valid values.

`sourceId` is a 1–64 character source identifier. Counts are nonnegative or
positive integers as specified by each field. Network dimensions range from
0 to 3, space-group numbers from 1 to 230, and volume fractions from 0 to 1.

## MOF identifiers and metal annotations

A structure may have both `mofidV1` and `mofidV2`. V1 uses SMILES node/linker
representations. V2 is generated from V1 calculation outputs using metal-node
categories and SELFIES linkers. The outer formats are
`<components> MOFid-v1.<topology>.cat<n>` and the corresponding `v2` format,
with optional `.<revision>` and `;<name>` suffixes. Pattern validation checks
this syntax rather than the chemical validity of the encoded components.

`metalElements` contains semicolon-separated element symbols. Each symbol is
validated using `pymatgen.core.Element.is_metal`. `metalElementCount` and
`metalAtomCount` are nonnegative integers; `metalloidElements` describes
metalloids separately.

## Checker results

`CheckerStatus` contains `PASS` and `FAIL`. `ConsensusStatus` contains `CR`,
`NCR`, and `AMBIGUOUS`.

| Consensus | Checkers |
|---|---|
| `consensus3` | MOFClassifier, MOFChecker, Chen–Manz |
| `consensus4` | MOFClassifier, MOFChecker, Chen–Manz, MOSAEC |
| `consensus5` | MOFClassifier, MOFChecker, Chen–Manz, MOSAEC, SETC-GAT |

`CheckerData` validates each consensus against the corresponding votes:
all PASS gives CR, all FAIL gives NCR, and mixed votes give AMBIGUOUS.

## Geometry

Geometry fields correspond to the MOFSimplify descriptors, using camelCase
API names. Density is an additional input for the GPOV calculation.

| Geometry field | MOFSimplify name | Corresponding Zeo field or definition | Unit |
|---|---|---|---|
| `di` | Di | `largestCavityDiameter` | angstrom |
| `df` | Df | `poreLimitingDiameter` | angstrom |
| `dif` | Dif | `largestFreePathDiameter` | angstrom |
| `gsa` | GSA | `n2AccessibleSurfaceAreaGravimetric` | m^2/g |
| `vsa` | VSA | `n2AccessibleSurfaceAreaVolumetric` | m^2/cm^3 |
| `gpoav` | GPOAV | `n2AccessibleVolumeGravimetric` | cm^3/g |
| `gponav` | GPONAV | `n2NonaccessibleVolumeGravimetric` | cm^3/g |
| `poav` | POAV | `n2AccessibleVolumePerCell` | angstrom^3 |
| `ponav` | PONAV | `n2NonaccessibleVolumePerCell` | angstrom^3 |
| `poavVolFrac` | POAV_vol_frac | `n2AccessibleVolumeFraction` | dimensionless |
| `ponavVolFrac` | PONAV_vol_frac | `n2NonaccessibleVolumeFraction` | dimensionless |
| `cellV` | cell_v | Unit-cell volume | angstrom^3 |
| `density` | Additional input | `density` | g/cm^3 |
| `vpov` | VPOV | `poavVolFrac + ponavVolFrac` | dimensionless |
| `gpov` | GPOV | `vpov / density` | cm^3/g |

`GeometryData` computes `vpov` and `gpov` as read-only properties exposed by
Pydantic `computed_field`. They are included in `model_dump()` output rather
than supplied as inputs. `model_dump(round_trip=True)` produces input values
for revalidation without these computed fields.

VPOV requires both volume fractions; GPOV also requires positive density.
Missing calculation inputs produce `None`. The model validates that VPOV is
between 0 and 1 and that a computed GPOV is finite. Zero is valid.

## Zeo++ Table

`ZeoFeatures` describes pore diameters, surface areas, pore volumes, framework
dimensions, and open metal sites. The N2 and He probe radii are 1.655 and
1.32 angstrom, respectively. Field descriptions specify the physical units.

`n2HeAvailable`, `periodicityAvailable`, and `omsAvailable` describe the
availability of the corresponding result groups. Missing numeric cells are
represented by `None` in the row model.

The OMS validator requires a nonnegative integer `openMetalSiteCount` when
`omsAvailable` is true. A positive count indicates open metal sites, while
zero indicates none. When `omsAvailable` is false, the count must be absent
or `None`.

## Topology summaries and subnet Table

`TopologyData` describes availability and five summary fields.
When `topologyAvailable` is true, all five summary keys must be supplied.
`singleAllAgree` must be a boolean and `catenationDegree` a positive integer.
`networkDimension`, `singleNodeNet`, and `allNodeNet` represent common subnet
values and may be `None` when there is no common value. When topology is
unavailable, summary values must be absent or `None`.

Each `Topology` row describes SingleNodes and AllNodes representations of one
subnet. Their topology keys must contain a non-whitespace character. Optional
name and genome fields allow empty strings and `None`. The row validator
checks that `singleAllAgree` matches equality of the two topology keys.

The exported `validate_topology(summary, rows)` function checks the relationship
between a validated summary and its validated rows:

- Available topology has a positive number of rows equal to `catenationDegree`.
- Unavailable topology has no rows.
- `subnetIndex` values are unique within the Contribution.
- Dimension and net summaries match the common corresponding row values,
  or `None` when those values differ.
- The summary agreement flag is true exactly when every row agrees.

This function is called separately from individual model validation because
the summary and Table are separate Contribution components.

## RAC Table

Revised autocorrelation descriptors encode atomic properties and connectivity
as machine-learning features. `RacFeatures` uses a maximum graph depth of 5,
covering bond distances from 0 to 5. A supplied Table contains exactly one row
with all 264 finite numeric values. Signed and zero descriptor values are
valid. An absent RAC result is represented by omission of the Table.

## Units and native components

Field descriptions specify units. `client.init_columns` configures the units
of data paths, such as `geometry.di` in angstrom; individual Table-column
units are described by their row fields. Native components and data-column
configuration follow the
[MPContribs Quickstart](https://docs.materialsproject.org/uploading-data/what-is-mpcontribs#quickstart).
