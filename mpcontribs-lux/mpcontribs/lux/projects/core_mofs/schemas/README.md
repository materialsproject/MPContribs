# CoRE MOF contribution schemas

Each Contribution represents one CoRE MOF structure with a unique identifier.
The native `identifier`, `formula`, `structures`, and `tables` components describe
the record identity, chemical formula, pymatgen Structures, and attached Tables.

| Module | Model | Component |
|---|---|---|
| `data.py` | `Data` | `Contribution.data`: 9 groups, 46 input fields, including two automatically calculated volume fields |
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
| `geometry` | No | 0 | 15 |
| **Total** | **5 required groups** | **15** | **31** |

These counts describe field declarations. When topology is available, its five
summary keys are additionally required by model validation. The geometry group
has 15 optional fields, giving 46 data fields overall.

Optional fields default to `None`. Numeric values must be finite, and their
declared ranges apply after ordinary Pydantic type conversion. Booleans are
rejected as numeric inputs. Scientific zero and false are valid values.

`sourceId` is a 1–64 character source identifier. Counts are nonnegative or
positive integers as specified by each field. Network dimensions range from
0 to 3, space-group numbers from 1 to 230, and volume fractions from 0 to 1.

## CCDC source links

`source.ccdcUrl` is optional and defaults to `None`. A supplied URL is allowed
only when `sourceDatabase` is `CSD` and must have the exact form
`https://www.ccdc.cam.ac.uk/structures/Search?Ccdcid={sourceId}&DatabaseToSearch=Published`.
The refcode contains six uppercase letters, optionally followed by two digits,
and must match `sourceId`. COD and SI records allow only an absent or `None`
URL. URL validation checks syntax and source consistency, without contacting
the CCDC service.

## Publication DOI

`reference.doi` is an optional DOI string, not a DOI resolver URL. It defaults
to `None`, has a maximum length of 128 characters, and must match
`^10\.\d{4,9}(\.\d+)*/\S+$` when supplied. Validation checks the identifier
format without resolving it online.

## MOF identifiers and metal annotations

A structure may have both `mofidV1` and `mofidV2`. V1 uses SMILES node/linker
representations. V2 is generated from V1 calculation outputs using metal-node
categories and SELFIES linkers. The outer formats are
`<components> MOFid-v1.<topology>.cat<n>` and the corresponding `v2` format,
with optional `.<revision>` and `;<name>` suffixes. Pattern validation checks
this syntax rather than the chemical validity of the encoded components.

`metalElements` and `metalloidElements` share an `ElementSymbolList` type:
1–512 characters, with one- or two-letter element symbols separated by single
semicolons and no whitespace. Each symbol in `metalElements` is additionally
validated using `pymatgen.core.Element.is_metal`. `metalElementCount` and
`metalAtomCount` are nonnegative integers; `metalloidElements` describes
metalloids separately.
`metalClasses` is an optional classification string with a maximum length of
256 characters.

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
API names. The diameters `di`, `df`, and `dif` are nonnegative. Density is an
additional input for the GPOV calculation.

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
| `gpov` | GPOV | `(poavVolFrac + ponavVolFrac) / density` | cm^3/g |

`vpov` and `gpov` are ordinary optional fields. The model fills missing values
from the two volume fractions and, for GPOV, positive density. Supplied values
are preserved when they agree with the calculation: comparisons allow 0.01%
relative error or 0.0001 absolute error (dimensionless for VPOV; cm^3/g for
GPOV), whichever is larger. GPOV is checked directly against the fraction sum
divided by density, avoiding accumulation of an accepted VPOV rounding error.

Supplied volumes require their calculation inputs. If a volume is absent or
`None`, it is calculated when possible; otherwise it remains `None`. The
fraction sum and VPOV must be between 0 and 1, and GPOV must be finite and
nonnegative. Zero is valid. Unknown fields are forbidden, but both volume
fields are accepted on revalidation of `model_dump()` or `model_dump_json()`.

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

The two topology keys and two topology names have a maximum length of 256
characters. Each topological genome has a maximum length of 200,000 characters
and, when nonempty, contains integers separated by single spaces; negative
integers are permitted. Optional names and genomes still accept `None` and
empty strings. These constraints validate representation, not the scientific
meaning of an encoded genome.

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
