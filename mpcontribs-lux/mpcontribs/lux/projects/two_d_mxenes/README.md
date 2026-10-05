# two_d_mxenes

Schemas and pipelines for the MPContribs project `two_d_mxenes`: relaxed structures and computed properties of two-dimensional MXenes, M<sub>n+1</sub>X<sub>n</sub>T<sub>x</sub>. Each record describes one MXene variant, defined by

- the transition metal **M**,
- the non-metal **X**: C (carbide) or N (nitride),
- the thickness index **n**: 1, 2 or 3 (M<sub>2</sub>X, M<sub>3</sub>X<sub>2</sub>, M<sub>4</sub>X<sub>3</sub>),
- the surface termination **T**: none (pristine), F or O,
- the stacking of the layers (octahedral **O** or trigonal-prismatic **P** coordination of each layer) and the site occupied by the termination.

The stacking nomenclature follows N. Oyeniran *et al.*, *Adv. Funct. Mater.* (2025), [doi:10.1002/adfm.202508047](https://doi.org/10.1002/adfm.202508047).

---

## Contents

1. [Layout](#layout)
2. [Labelling](#labelling)
3. [Validation phases](#validation-phases)
4. [Accepted and rejected data](#accepted-and-rejected-data)
5. [Record contents](#record-contents)
6. [Conformance with MPContribs requirements](#conformance-with-mpcontribs-requirements)
7. [Quick start](#quick-start)
8. [Workflow](#workflow)
9. [Testing](#testing)
10. [Extending the schema](#extending-the-schema)
11. [Contributing](#contributing)

Detailed references:

- [`pipelines/README.md`](pipelines/README.md): commands, output files, error catalogue with remedies, properties spreadsheet, MPContribs upload.
- [`schemas/README.md`](schemas/README.md): every field of every model, with type, unit and description.

---

## Layout

```
mpcontribs-lux/
├── mpcontribs/lux/projects/two_d_mxenes/
│   ├── README.md                    this file
│   ├── pip-extra-requirements.txt   optional packages (openpyxl, for .xlsx files)
│   ├── schemas/                     the data contract (pydantic models)
│   │   ├── README.md                field reference
│   │   ├── labels.py                M, X, T, n, stacking, termination site; labelling rules
│   │   ├── structure.py             relaxed structure; descriptors computed from it
│   │   ├── properties.py            energetics and elastic properties
│   │   ├── calculation.py           project-level DFT settings
│   │   └── mxene.py                 MXeneEntry: one cross-validated record per structure
│   └── pipelines/
│       ├── README.md                usage, error catalogue, upload guide
│       ├── build_contributions.py   structure check, properties template and loader, MPContribs format, Parquet
│       └── dataset_overview.py      Excel overview of present, failing and missing structures
├── tests/projects/two_d_mxenes/test_two_d_mxenes.py
└── test_data/by_user/two_d_mxenes/MXENE_DATA/Hf/m2x/h-1/CONTCAR   sample Hf₂CF₂ structure
```

The **schemas** define what a valid record is. The **pipelines** produce records from VASP `CONTCAR` files and a properties spreadsheet, and convert them to MPContribs contributions and Parquet.

---

## Labelling

Each structure is a VASP `CONTCAR` in a folder named by its **label**, for example `h1a-2`. All other information is read from the atoms in the file.

| label part | source | values |
|---|---|---|
| M, X, T | composition | M: one transition metal; X: C or N; T: F, O or none |
| n | composition (M<sub>n+1</sub>X<sub>n</sub>) | 1, 2, 3 |
| stacking | folder name, before the hyphen | `t`, `h` (n = 1); `t`, `h1a`, `h1b`, `h2` (n ≥ 2) |
| termination site | folder name, after the hyphen | `-1`, `-2` for terminated MXenes; no suffix for pristine |

Folders above the label folder are not read and may be named and nested freely. The record ID is `mxeneId = <formula>-<label>`, e.g. `Ti3C2O2-h1a-2` or `Mo2C-t`.

### Coordination sequence

Each atomic layer with a layer directly below and above it is classified as

- **O** (octahedral): the layers below and above are *staggered* in the plane;
- **P** (trigonal prismatic): the layers below and above are *eclipsed*.

The resulting **coordination sequence** (`StructureDescriptors.coordinationSequence`) lists the interior layers from bottom to top. A pristine M<sub>n+1</sub>X<sub>n</sub> has 2n − 1 interior layers (X, M, X, …); a terminated M<sub>n+1</sub>X<sub>n</sub>T<sub>2</sub> has 2n + 1 (outer M, X, M, …, X, outer M).

### Stacking labels

The **core** is the part of the sequence between the two outermost metal layers. Its odd positions are X layers and its even positions are the inner metal layers.

| label | n | core sequence | inner metal layers |
|---|---|---|---|
| `t` | 1 | O | – |
| `h` | 1 | P | – |
| `t` | 2, 3 | O-O-O(-O-O) | O |
| `h2` | 2, 3 | P-P-P(-P-P) | P |
| `h1a` | 2, 3 | O-P-O(-P-O) | P |
| `h1b` | 2, 3 | P-O-P(-O-P) | O |

### Termination site

The suffix of a terminated MXene sets the coordination of both outer metal layers (the first and last entries of the full sequence):

| n | stacking | `-1` | `-2` |
|---|---|---|---|
| 1 | `t`, `h` | O | P |
| ≥ 2 | `t`, `h1b` | O | P |
| ≥ 2 | `h1a`, `h2` | P | O |

For n = 1, site 1 is octahedral and site 2 prismatic. For n ≥ 2, site 1 gives the outer metal layers the same coordination as the inner metal layers, and site 2 the opposite. Geometrically, O means the termination is staggered relative to the X layer beneath the outer metal; P means it lies directly above an X atom. The rule is implemented in `labels.expected_termination_coordination`.

Examples (core in bold): `Hf2CF2-h-1` → O-**P**-O; `Mo3C2F2-h1a-1` → P-**O-P-O**-P; `Ti4C3O2-t-2` → P-**O-O-O-O-O**-P.

---

## Validation phases

Every structure passes through the following phases in order. A structure that fails any phase produces no record; the [error catalogue](pipelines/README.md#error-catalogue) lists each message and its remedy.

| phase | what is checked | where |
|---|---|---|
| 1. Discovery | Files named `CONTCAR` are collected. A file whose folder is a valid label is an entry. A file in a sub-folder of an entry folder is an auxiliary calculation and is skipped. Any other file is an error. | `iter_structure_files`, `is_auxiliary` |
| 2. Parsing and chemistry | The file parses as a structure. The composition contains exactly one transition metal, exactly one of C/N and at most one of F/O, with M<sub>n+1</sub>X<sub>n</sub> stoichiometry. M, X, T and n are inferred. | `infer_chemistry` |
| 3. Label | The folder label is a known stacking with an optional `-1`/`-2` suffix. The stacking is allowed for n. A suffix is present exactly when the MXene is terminated. | `MXeneLabel` |
| 4. Structure | Species and coordinates are consistent. Lattice vectors a and b lie in the sheet plane. Atoms group into single-element layers. Descriptors are computed. | `MXeneStructure`, `StructureDescriptors` |
| 5. Cross-validation | The composition matches the labels (including T<sub>2</sub>). The measured core sequence matches the stacking. The measured outer-metal coordination matches the termination site on both surfaces. | `MXeneEntry` |
| 6. Uniqueness | No two files claim the same `mxeneId`. If several do, all of them are rejected. | `check_dataset`, `build_entries` |
| 7. Properties | Spreadsheet columns are known and their header units match. Values are numeric and finite. C11 and C12 are given together. Every row matches a valid structure. Derived properties are computed. | `load_properties`, `properties.py` |
| 8. Export | Contributions use only the declared columns, with units the MPContribs client parses. Records convert to Arrow and round-trip through Parquet. | `to_contribution`, `write_parquet` |

---

## Accepted and rejected data

### Structures

| accepted | rejected |
|---|---|
| Relaxed slab structures in VASP POSCAR/CONTCAR format, one per label folder | Files that cannot be parsed (empty, truncated) |
| Any transition metal M; X = C or N; T = F, O or none | Other elements, e.g. Cl, S, or H (OH terminations); B (MBenes) |
| Thickness n = 1, 2, 3 | n ≥ 4 |
| Terminations on both surfaces (T<sub>2</sub> per formula unit) | One-sided or partial terminations (e.g. M<sub>2</sub>XT<sub>1</sub>) |
| A single termination species | Mixed terminations (e.g. O and F in one sheet) |
| A single metal species | Ordered or solid-solution double-metal MXenes (e.g. Mo<sub>2</sub>TiC<sub>2</sub>) |
| Stoichiometric sheets | Vacancies or non-stoichiometric compositions |
| Any in-plane cell, including supercells, with the sheet normal along c | Cells whose a and b vectors are not in the sheet plane |
| Sheets split across the periodic boundary along c | Sheets whose atomic layers overlap along the normal (more than 0.4 Å out of plane, e.g. reconstructed structures) |
| Structures whose measured stacking and termination site match the label | Structures whose geometry contradicts their label; they are rejected, never relabelled |
| One structure per `mxeneId` | Several structures claiming the same `mxeneId` (all are rejected) |
| Follow-up calculations inside an entry folder (supercells, phonons, …) | (these are skipped, not uploaded) |

### Properties

| accepted | rejected |
|---|---|
| Numeric values in the declared units (eV/atom, N/m) | Text in numeric cells (`N/A`, `-`), NaN, infinity |
| Blank cells for unknown values | Columns that are not declared, or headers with a different unit (e.g. `c11 [GPa]`) |
| C11 and C12 together, optionally C66 | C11 without C12 (or vice versa), or C66 without both |
| One row per valid structure | Duplicate `mxeneId` rows; rows with no valid structure |

Lattice parameters and other structural quantities are never read from the spreadsheet; they are computed from the structure.

---

## Record contents

One `MXeneEntry` per structure:

| group | contents | source |
|---|---|---|
| `mxeneId` | e.g. `Ti3C2O2-h1a-2` | formula + label |
| `labels` | metal, nonmetal, termination, n, stacking, terminationSite | composition + label |
| `structure` | lattice, species, fractional coordinates | CONTCAR |
| `descriptors` | formula, a, b, γ, cell area, area per formula unit, areal mass density, thickness, vacuum, layer and coordination sequences, M–X and M–T bond lengths, space group | computed from the structure |
| `properties.energetics` | total energy, formation energy, relative stacking energy | spreadsheet; relative stacking energy computed |
| `properties.elastic` | C11, C12, C66, Young's modulus, Poisson's ratio, shear modulus, Born stability | spreadsheet (C11, C12, C66); the rest computed |

Units: lengths in Å; energies in eV/atom (relative stacking energy in meV/atom); 2D elastic constants and moduli in N/m. DFT settings are identical for all records and are stored once per project (`CalculationSettings`). The full field list is in [`schemas/README.md`](schemas/README.md).

On MPContribs each record is one contribution: identifier `mxeneId`, the formula in `formula`, 21 searchable `data` columns (`MPCONTRIBS_COLUMNS`) and the relaxed structure. The complete records are also written to Parquet.

---

## Conformance with MPContribs requirements

| requirement (source) | implementation |
|---|---|
| Schemas in `mpcontribs-lux/mpcontribs/lux/projects/<project>/schemas` (MP onboarding) | `two_d_mxenes/schemas/` |
| Annotated pydantic models (MPContribs-lux README) | every field has a description with its unit |
| Arrow/Parquet compatibility (MPContribs-lux README) | all 8 models pass `tests/test_models_for_arrow_compatibility.py`; Parquet round-trip tested |
| Project name of 3–31 alphanumeric/underscore characters (MPContribs docs) | `two_d_mxenes` |
| Column names alphanumeric, without underscores or spaces, dot-nested up to 4 levels (MPContribs docs) | camelCase, at most 2 levels (e.g. `geometry.a`); enforced by a test |
| At most 50 flattened `data` keys (MPContribs docs) | 21; enforced by a test |
| Numbers as strings with pint units; `None` for text and `""` for dimensionless columns (MPContribs docs, client `init_columns`) | `MPCONTRIBS_COLUMNS`; values formatted by `to_contribution`; parsed with the client's unit registry in a test |
| No NaN or unset keys in `data` (MPContribs docs) | missing values are omitted; NaN and infinity are rejected by the models |
| Lists converted to named fields (MPContribs docs) | `data` contains no lists |
| Structures as pymatgen objects, at most 10 per contribution (MPContribs docs) | one relaxed structure per contribution |
| An `identifier` per contribution; may be arbitrary (MPContribs-lux upload example) | `mxeneId`; unique, so the default `unique_identifiers=True` keeps every structure |
| `formula` per contribution (MPContribs-lux upload example) | reduced formula, e.g. `Hf3C2F2` |
| Project `other` metadata keys without punctuation (MPContribs API validation) | `project_other()` nests column descriptions |
| Tests under `tests/projects/<project>`, data under `test_data/by_user/<project>` (repository layout) | as shown in [Layout](#layout) |
| Project README and extra requirements file (`lux project scaffold`) | `README.md`, `pip-extra-requirements.txt` |
| Repository code style (`.pre-commit-config.yaml`) | ruff, black and pyupgrade pass |

---

## Quick start

```bash
# from the repository root
pip install -e "mpcontribs-lux[test]"
pip install openpyxl            # Excel overview and .xlsx spreadsheets

python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions DATA_ROOT \
    --report check_report.csv \
    --overview structure_overview.xlsx \
    --template properties.csv
```

`DATA_ROOT` is the root folder of the CONTCAR tree. On Windows PowerShell, write the command on one line or end each line with a backtick (`` ` ``) instead of `\`.

---

## Workflow

| step | action | reference |
|---|---|---|
| 1 | Arrange the relaxed CONTCARs in label folders. | [Folder layout](pipelines/README.md#folder-layout) |
| 2 | Run the check with `--report` and `--overview`; resolve every failure; re-run until no structure fails. | [Error catalogue](pipelines/README.md#error-catalogue) |
| 3 | Generate the properties template with `--template`, fill in the property columns, and re-run to refresh it as structures change. | [Properties spreadsheet](pipelines/README.md#properties-spreadsheet) |
| 4 | Build the records with the properties; write the Parquet file. | [Build the records](pipelines/README.md#1-build-and-check-the-records) |
| 5 | Create the MPContribs project, initialise the columns, submit the contributions and verify them while the project is private. | [Uploading to MPContribs](pipelines/README.md#uploading-to-mpcontribs) |
| 6 | Publish after MP approval. | [Publish](pipelines/README.md#6-publish) |

Uploading requires the schema to be merged into `materialsproject/MPContribs` and upload permission from MP.

---

## Testing

```bash
pytest mpcontribs-lux/tests/projects/two_d_mxenes mpcontribs-lux/tests/test_models_for_arrow_compatibility.py
```

| test group | covers phases |
|---|---|
| labels: folder-label parsing, stacking/thickness rules, core and termination-site rules for every n and stacking | 3, 5 |
| structure: round-trip to pymatgen, descriptors of the sample structure, sheets split across the cell, coordination detection for every stacking, formula formatting, distorted structures | 2, 4 |
| entry: chemistry inference, rejection of wrong stacking, wrong termination site, mixed sites and wrong composition | 2, 5 |
| properties: derived moduli and stability | 7 |
| pipeline: building from a folder tree, auxiliary files, duplicate and orphan handling, collected failures, command-line report | 1, 6, 7 |
| overview: grid columns, cell states, scope exclusions, workbook contents (needs `openpyxl`) | 1, 6 |
| contribution format: declared columns, units, identifier, server-safe project metadata, unit registry | 8 |
| properties template: round-trip, refresh with kept and orphaned values, rejected inputs | 7 |
| Parquet: write and read back identical records | 8 |
| repository: Arrow compatibility of every model (`tests/test_models_for_arrow_compatibility.py`) | 8 |

Structures for any stacking and termination site are built in the tests with `ideal_mxene`, so every rule is tested for both acceptance and rejection.

---

## Extending the schema

| extension | changes |
|---|---|
| more structures of supported kinds | none |
| another termination (e.g. Cl) | `Termination` in `schemas/labels.py`; element sets in `infer_chemistry` (`schemas/mxene.py`) and `StructureDescriptors.from_structure` (`schemas/structure.py`); `TERMINATIONS` in `pipelines/dataset_overview.py`; tests. Multi-atom terminations (e.g. OH) also require a layer-grouping rule. |
| n = 4 | `Thickness` and `_THICK_STACKINGS` in `labels.py`; `_STACKINGS` and the `n` loop in `dataset_overview.py`; tests |
| another stacking label | `StackingLabel`, `expected_core_sequence` and `expected_termination_coordination` in `labels.py`; `_STACKINGS` in `dataset_overview.py`; tests built with `ideal_mxene` |
| another property | `schemas/properties.py`; `SPREADSHEET_COLUMNS` and `load_properties` in `pipelines/build_contributions.py`; for a searchable column also `MPCONTRIBS_COLUMNS`, `MPCONTRIBS_COLUMN_DESCRIPTIONS` and `to_contribution`; tests |

Every extension changes the data contract and is submitted for MP review.

---

## Contributing

### Pull requests

- Pull requests target [`materialsproject/MPContribs`](https://github.com/materialsproject/MPContribs) `master`, from a branch that is up to date with it, and change only this project's folder, its tests and its test data.
- Review is by MP staff. Enable "Allow edits by maintainers".

### Checks before every commit

```bash
pytest mpcontribs-lux/tests/projects/two_d_mxenes mpcontribs-lux/tests/test_models_for_arrow_compatibility.py
pre-commit run --files <changed files>
```

### Checklist

- [ ] Tests pass on Python 3.11 and 3.12, including the Arrow compatibility test.
- [ ] Every new or changed field has a description with its unit.
- [ ] Field and column names are camelCase without underscores.
- [ ] `MPCONTRIBS_COLUMNS`, `MPCONTRIBS_COLUMN_DESCRIPTIONS` and `to_contribution` agree; at most 50 columns (enforced by tests).
- [ ] Every new rule has tests that accept a conforming structure and reject a non-conforming one.
- [ ] Documentation is updated: this README (rules, phases, accepted data), `pipelines/README.md` (commands, errors), `schemas/README.md` (fields).
- [ ] Test data is limited to small sample files. No credentials appear in code, commits or logs.

### Invariants

The following are part of the public contract. Changing any of them requires MP review:

1. `mxeneId` is `<formula>-<label>`, is unique within the project, and is the contribution identifier.
2. M, X, T and n are determined by the atoms, never by folder names.
3. Structural quantities are computed from the structure, never read from a spreadsheet.
4. A structure whose geometry contradicts its label is rejected, not relabelled.
5. When several structures claim the same `mxeneId`, all are rejected.
6. Every model is Arrow-compatible.

### Guidance for automated (AI) contributors

- Read this file, [`pipelines/README.md`](pipelines/README.md), [`schemas/README.md`](schemas/README.md), `schemas/labels.py`, `schemas/mxene.py` and the tests before making changes.
- Run the tests before and after a change and report both results.
- Do not relax a check, tolerance or labelling rule to make data pass. Report failing files and their messages instead.
- Do not change identifiers, field names or units without the maintainers' agreement.
- Never write credentials to files, commits or logs.
- Keep commits small; state in each commit message which rule or behaviour changed.
