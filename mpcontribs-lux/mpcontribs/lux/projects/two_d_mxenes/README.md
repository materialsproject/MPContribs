# two_d_mxenes

Schemas and pipelines for the MPContribs project `two_d_mxenes`: relaxed structures and computed properties of two-dimensional MXenes, M<sub>n+1</sub>X<sub>n</sub>T<sub>x</sub>. Each contribution describes one MXene variant, defined by

- the transition metals **M**: one metal, or several (ordered double-metal, solid-solution and high-entropy MXenes),
- the non-metals **X**: C (carbide), N (nitride) or both (carbonitride),
- the thickness index **n**: 1 to 4 (M<sub>2</sub>X, M<sub>3</sub>X<sub>2</sub>, M<sub>4</sub>X<sub>3</sub>, M<sub>5</sub>X<sub>4</sub>),
- the surface terminations **T**: none (pristine), or one or more single-element halogen or chalcogen terminations (F, Cl, Br, I, O, S, Se, Te),
- the stacking of the layers (octahedral **O** or trigonal-prismatic **P** coordination of each layer), the site occupied by the termination, and, for compositions with several atomic arrangements, a configuration index.

Each entry also records its calculation method: DFT, or a machine-learning interatomic potential (MLIP).

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
│   ├── schemas/                     the data contract: contribution data (pydantic models)
│   │   ├── README.md                field reference
│   │   ├── labels.py                M, X, T, n, stacking, termination site, configuration; labelling rules
│   │   ├── descriptors.py           geometric descriptors of the relaxed structure
│   │   ├── properties.py            energetics and elastic properties
│   │   ├── provenance.py            calculation method (DFT or MLIP)
│   │   └── mxene.py                 MXeneEntry: the cross-validated data of one contribution
│   └── pipelines/                   code that produces and uploads contributions
│       ├── README.md                modules, usage, error catalogue, upload guide
│       ├── structure_analysis.py    structure -> chemistry, layers, coordination, descriptors, MXeneEntry
│       ├── build_contributions.py   discovery, structure check (command line), properties template and loader
│       ├── upload.py                CalculationSettings, MPContribs columns and contributions, project metadata, Parquet
│       └── dataset_overview.py      Excel overview of present, failing and missing structures
├── tests/projects/two_d_mxenes/test_two_d_mxenes.py
└── test_data/by_user/two_d_mxenes/MXENE_DATA/Hf/m2x/h-1/CONTCAR   sample Hf₂CF₂ structure
```

The **schemas** define the data of one MPContribs contribution. `MXeneEntry` is exactly the contribution's `data`: every field is a scalar or a short validated string, and units are declared in the field metadata. The relaxed structure is not part of the schema; it is submitted alongside, as a pymatgen `Structure` in the contribution's `structures` component.

The **pipelines** contain all code that operates on structures and files: they analyse VASP `CONTCAR` files, read the properties spreadsheet, build validated `MXeneEntry` objects, and convert them to MPContribs contributions and Parquet.

---

## Labelling

Each structure is a VASP `CONTCAR` in a folder named by its **label**, for example `h1a-2`. All other information is read from the atoms in the file.

| label part | source | values |
|---|---|---|
| M, X, T | composition | M: one or more transition metals; X: C, N or both; T: one or more of F, Cl, Br, I, O, S, Se, Te, or none |
| n | composition (M<sub>n+1</sub>X<sub>n</sub>, from the total amounts of M and X) | 1, 2, 3, 4 |
| stacking | folder name, first part | `t`, `h` (n = 1); `t`, `h1a`, `h1b`, `h2` (n ≥ 2) |
| termination site | folder name, `-1` or `-2` | required for terminated MXenes; absent for pristine |
| configuration | folder name, `-c<k>` (k = 1–999), last | optional; numbers different atomic arrangements of the same composition and stacking, e.g. special quasirandom structures |

Folders above the label folder are not read and may be named and nested freely. Element lists are stored as strings ordered by atomic number and joined by `-` (e.g. metals `Ti-V-Nb-Mo`, X `C-N`, T `O-F`). The record ID is `mxeneId = <reduced formula>-<label>`, e.g. `Ti3C2O2-h1a-2`, `Mo2C-t`, `TiMo2C2-t` or `TiVNbMoC3O2-t-1-c2`. The reduced formula lists metals, then X, then terminations, each by atomic number.

### Layers and metal arrangement

Atoms are grouped into layers along the normal. A layer may hold several elements of the same role, e.g. Ti and V in a solid-solution metal layer, and is then written with `/` (`Ti/V`); a layer mixing roles (metal with X, or X with T) is rejected. Layers alternate M, X, M, …, M, with a T layer on each surface of a terminated MXene. The **metal arrangement** is `single` (one metal), `out-of-plane ordered` (each metal layer holds one element, e.g. Mo<sub>2</sub>TiC<sub>2</sub> = `Mo-C-Ti-C-Mo`) or `in-plane mixed` (at least one metal layer holds several metals: in-plane ordered or solid solution).

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
| `t` | 2–4 | O-O-O(-O-O…) | O |
| `h2` | 2–4 | P-P-P(-P-P…) | P |
| `h1a` | 2–4 | O-P-O(-P-O…) | P |
| `h1b` | 2–4 | P-O-P(-O-P…) | O |

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
| 1. Discovery | Files named `CONTCAR` are collected. A file whose folder is a valid label is an entry. A file in a sub-folder of an entry folder is an auxiliary calculation and is skipped. Any other file is an error. | `pipelines/build_contributions.py`: `iter_structure_files`, `is_auxiliary` |
| 2. Parsing and chemistry | The file parses as a structure. Every element is a transition metal, C/N or a supported termination, with at least one metal and one of C/N. The total amounts give M<sub>n+1</sub>X<sub>n</sub> with integer n and, if terminated, exactly two termination atoms per formula unit. M, X, T and n are inferred. | `pipelines/structure_analysis.py`: `infer_chemistry` |
| 3. Label | The folder label is a known stacking with an optional `-1`/`-2` suffix and an optional `-c<k>` suffix. The metals are transition metals and every element list is in canonical order. The stacking is allowed for n. A site suffix is present exactly when the MXene is terminated. | `schemas/labels.py`: `parse_folder_label`, `MXeneLabel` |
| 4. Structure and descriptors | Lattice vectors a and b lie in the sheet plane. Atoms group into layers that each hold one role (metal, X or termination). Descriptors are computed and validated: bounded numbers, formula and sequence patterns, maximum string lengths, a space-group symbol known to spglib that matches its number, one coordination entry per interior layer. | `pipelines/structure_analysis.py`: `compute_descriptors`; `schemas/descriptors.py`: `StructureDescriptors` |
| 5. Cross-validation | `mxeneId` is `<reduced formula>-<label>`. The composition holds exactly the labelled elements in M<sub>n+1</sub>X<sub>n</sub>(T<sub>2</sub>) proportions. Every layer holds elements of its role, and together the layers hold all labelled elements. The metal arrangement matches the metal layers. The measured core sequence matches the stacking. The measured outer-metal coordination matches the termination site on both surfaces. Elastic data of a non-hexagonal cell includes C22 and C66, and a hexagonal cell has C22 = C11. | `schemas/mxene.py`: `MXeneEntry` |
| 6. Uniqueness | No two files claim the same `mxeneId`. If several do, all of them are rejected. | `pipelines/build_contributions.py`: `check_dataset`, `build_records` |
| 7. Properties | Spreadsheet columns are known and their header units match. Property cells are numbers or blank. C11 and C12 are given together; C22 comes with C66. The method is `DFT` or `MLIP`, with a potential name exactly for `MLIP`. Every row matches a valid structure. Values lie within physical bounds, and derived moduli and stability are consistent with the elastic constants. | `pipelines/build_contributions.py`: `load_properties`, `load_provenance`; `schemas/properties.py`, `schemas/provenance.py` |
| 8. Export | The contribution data is the schema itself: columns, units and descriptions are generated from the field metadata, numbers are written with units the MPContribs client parses, and the structure is attached in `structures`. Entries, with their structures, round-trip through Parquet. | `pipelines/upload.py`: `to_contribution`, `write_parquet` |

---

## Accepted and rejected data

### Structures

| accepted | rejected |
|---|---|
| Relaxed slab structures in VASP POSCAR/CONTCAR format, one per label folder | Files that cannot be parsed (empty, truncated) |
| One or more transition metals (single-metal, ordered double-metal such as Mo<sub>2</sub>TiC<sub>2</sub>, solid-solution and high-entropy MXenes); X = C, N or both; T = one or more of F, Cl, Br, I, O, S, Se, Te, or none | Other elements, e.g. H (OH terminations) or B (MBenes) |
| Thickness n = 1, 2, 3, 4 | n ≥ 5 |
| Terminations on both surfaces (T<sub>2</sub> per formula unit), of one or several elements, mixed within a layer or different on the two surfaces (Janus) | One-sided or partial terminations (e.g. M<sub>2</sub>XT<sub>1</sub>) |
| Layers that each hold one role (metal, X or termination), possibly several elements of it | Layers mixing roles (e.g. C in a metal layer, antisite defects) |
| Several arrangements of one composition and stacking, numbered with `-c<k>` | Several arrangements without a configuration suffix (duplicate `mxeneId`) |
| Stoichiometric sheets | Vacancies or non-stoichiometric compositions |
| Any in-plane cell, including supercells, with the sheet normal along c | Cells whose a and b vectors are not in the sheet plane |
| Sheets split across the periodic boundary along c | Sheets whose atomic layers overlap along the normal (more than 0.4 Å out of plane, e.g. reconstructed structures) |
| Descriptors within physical bounds (e.g. 0 < γ < 180°, bond lengths up to 5 Å) | Out-of-range, NaN or infinite values; strings that do not match their pattern or exceed their maximum length |
| Structures whose measured stacking and termination site match the label (all termination atoms of a surface on the same site type) | Structures whose geometry contradicts their label; they are rejected, never relabelled |
| One structure per `mxeneId` | Several structures claiming the same `mxeneId` (all are rejected) |
| Follow-up calculations inside an entry folder (supercells, phonons, …) | (these are skipped, not uploaded) |

### Properties

| accepted | rejected |
|---|---|
| Numeric values in the declared units (eV/atom, N/m), within physical bounds | Text in numeric cells (`N/A`, `-`, `null`), NaN, infinity, out-of-range values |
| Blank cells for unknown values | Columns that are not declared, or headers with a different unit (e.g. `c11 [GPa]`) |
| C11 and C12 together, optionally C66; for a non-hexagonal cell also C22 with C66 | C11 without C12 (or vice versa); C22 or C66 without C11 and C12; C22 without C66; elastic data of a non-hexagonal cell without C22; C22 ≠ C11 for a hexagonal cell |
| Method `DFT` (or blank) or `MLIP` with the potential's name, e.g. `MACE-MP-0-medium` | Other methods; `MLIP` without a potential, or a potential with `DFT` |
| One row per valid structure | Duplicate `mxeneId` rows; rows with no valid structure |

Lattice parameters and other structural quantities are never read from the spreadsheet; they are computed from the structure.

---

## Record contents

One contribution per structure:

| part | contents | source |
|---|---|---|
| `identifier` | the `mxeneId`, e.g. `Ti3C2O2-h1a-2` | formula + label |
| `formula` | reduced formula, e.g. `Ti3C2O2` | structure |
| `data.mxeneId` | the `mxeneId` | formula + label |
| `data.labels` | metals, number of metals, nonmetals, terminations, n, stacking, terminationSite, configuration | composition + label |
| `data.descriptors` | formula, number of sites, a, b, γ, cell area, area per formula unit, areal mass density, thickness, vacuum, layer sequence (e.g. `F-Hf-C-Hf-F`, `Ti/V-C-Ti/V`), coordination sequence (e.g. `O-P-O`), metal arrangement, M–X and M–T bond lengths, space-group symbol and number | computed from the structure |
| `data.provenance` | method (`DFT` or `MLIP`) and, for `MLIP`, the potential | spreadsheet; `DFT` if blank |
| `data.properties.energetics` | total energy, formation energy, relative stacking energy | spreadsheet; relative stacking energy computed |
| `data.properties.elastic` | C11, C12, C22, C66, Young's modulus, Poisson's ratio, shear modulus, Born stability | spreadsheet (C11, C12, C22, C66); the rest computed |
| `structures` | the relaxed structure (pymatgen `Structure`) | CONTCAR |

`data` is `MXeneEntry` (39 columns, generated as `MPCONTRIBS_COLUMNS`). Units: lengths in Å; energies in eV/atom (relative stacking energy in meV/atom); 2D elastic constants and moduli in N/m. Sequences are stored as strings of layer symbols or O/P letters joined by `-`. The full field list is in [`schemas/README.md`](schemas/README.md).

DFT settings are identical for every DFT entry and are stored once in the project metadata (`CalculationSettings` in `pipelines/upload.py`). Entries computed with a machine-learning interatomic potential name it in `provenance.potential`; the potential and its training data are referenced in the project description. Relative stacking energies compare only entries of the same reduced formula and the same method. Entries and their structures are also written to Parquet.

---

## Conformance with MPContribs requirements

| requirement (source) | implementation |
|---|---|
| Schemas in `mpcontribs-lux/mpcontribs/lux/projects/<project>/schemas` (MP onboarding) | `two_d_mxenes/schemas/` |
| Annotated pydantic models (MPContribs-lux README) | every field has a description; numeric fields declare their unit in `json_schema_extra` |
| Arrow/Parquet compatibility (MPContribs-lux README) | all 8 models (including `CalculationSettings`) pass `tests/test_models_for_arrow_compatibility.py`; Parquet round-trip tested |
| Project name of 3–31 alphanumeric/underscore characters (MPContribs docs) | `two_d_mxenes` |
| Column names alphanumeric, without underscores or spaces, dot-nested up to 4 levels (MPContribs docs) | camelCase field names, at most 3 levels (e.g. `properties.elastic.c11`); enforced by a test |
| At most 50 flattened `data` keys (MPContribs docs) | 39; enforced by a test |
| Numbers as strings with pint units; `None` for text and `""` for dimensionless columns (MPContribs docs, client `init_columns`) | `MPCONTRIBS_COLUMNS` is generated from the schema's unit metadata; values formatted by `to_contribution`; parsed with the client's unit registry in a test. Integers that are categories (`terminationSite`, `configuration`, `spaceGroupNumber`) have no unit and are stored as text; ordered quantities (`n`, `nMetals`, `nSites`) are dimensionless numbers. |
| No NaN or unset keys in `data` (MPContribs docs) | missing values are omitted; NaN and infinity are rejected by the models |
| No lists in `data` (MPContribs docs) | the schema has no list fields; element lists and sequences are validated strings |
| Structures as pymatgen objects in `structures`, at most 10 per contribution (MPContribs docs) | one relaxed structure per contribution; not duplicated in `data` |
| Bounded string fields (MP review) | `Literal` vocabularies where the values are known (X, stacking, metal arrangement, method, code, functional, dispersion correction, POTCAR set, elastic method), otherwise a pattern and a maximum length; element lists are also checked element by element against their vocabulary (metals, terminations) |
| An `identifier` per contribution; may be arbitrary (MPContribs-lux upload example) | `mxeneId`; unique, so the default `unique_identifiers=True` keeps every structure |
| `formula` per contribution (MPContribs-lux upload example) | reduced formula, e.g. `Hf3C2F2` or `TiVNbMoC3` |
| Project `other` metadata keys without punctuation (MPContribs API validation) | `project_other()` nests column descriptions |
| Tests under `tests/projects/<project>`, data under `test_data/by_user/<project>` (repository layout) | as shown in [Layout](#layout) |
| Project README and extra requirements file (`lux project scaffold`) | `README.md`, `pip-extra-requirements.txt` |
| Repository code style (`.pre-commit-config.yaml`, MP review) | ruff, black and pyupgrade pass; Google-style docstrings; `model_config` declared in each model |

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
| 4 | Build the records (entries with their structures) and the Parquet file. | [Build the records](pipelines/README.md#1-build-and-check-the-records) |
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
| labels: folder-label parsing (with configuration suffix), element-list vocabularies and order, stacking/thickness rules, core and termination-site rules for every n and stacking, implied coordination sequences | 3, 5 |
| structure analysis: chemistry inference for single, alloy, high-entropy, carbonitride and mixed-termination compositions; descriptors of the sample structure, sheets split across the cell, coordination detection for every stacking, formula formatting, distorted and tilted structures | 2, 4 |
| descriptor limits: patterns, lengths, bounds, space-group symbol and number | 4 |
| entry: validation without a structure; rejection of a wrong ID, composition, stoichiometry, layer roles, metal arrangement, stacking, termination site or mixed sites | 5 |
| alloys and mixing: ordered double-metal, solid-solution and high-entropy sheets, carbonitrides, mixed and Janus terminations, configurations; elastic data against cell symmetry | 2, 4, 5 |
| properties and provenance: derived moduli and stability (isotropic and anisotropic); incomplete, inconsistent or out-of-range elastic data; method and potential; relative stacking energies per method | 7 |
| pipeline: building records from a folder tree, auxiliary files, duplicate and orphan handling, collected failures, command-line report | 1, 6, 7 |
| properties template and loader: round-trip, refresh with kept and orphaned values, rejected inputs | 7 |
| overview: grid columns, cell states, alloy systems, scope exclusions, workbook contents (needs `openpyxl`) | 1, 6 |
| upload: columns generated from the schema, contribution data equal to the schema, units against the client's registry, `CalculationSettings` limits, server-safe project metadata, Parquet with and without structures | 8 |
| accepted and rejected data: supercells; wider vocabulary (Cl, Te, S, Br, n = 4); other elements, MBenes, n = 5, one-sided terminations, vacancies | 2, 5 |
| repository: Arrow compatibility of every model (`tests/test_models_for_arrow_compatibility.py`) | 8 |

Structures for any stacking and termination site are built in the tests with `ideal_mxene`, and alloy and mixed-layer structures with `mixed_slab`, so every rule is tested for both acceptance and rejection.

---

## Extending the schema

| extension | changes |
|---|---|
| more structures of supported kinds | none |
| structures with any combination of supported M, X and T, n = 1–4, and any number of configurations | none: the overview grid also extends to the systems, n and terminations found in the data |
| another single-element termination | `Termination` in `schemas/labels.py` (the analysis in `pipelines/structure_analysis.py` and the overview use the same vocabulary); tests |
| a multi-atom termination (e.g. OH) | as above, plus a layer-grouping rule in `pipelines/structure_analysis.py` and a formula pattern that allows it |
| n ≥ 5 | `Thickness` in `schemas/labels.py`; `MXENE_ID_PATTERN` (`schemas/mxene.py`) and the sequence patterns and lengths (`schemas/descriptors.py`); tests |
| another stacking label | `StackingLabel`, `FOLDER_LABEL`, `expected_core_sequence` and `expected_termination_coordination` in `schemas/labels.py`; `MXENE_ID_PATTERN`; `_STACKING_ORDER` in `pipelines/dataset_overview.py`; tests built with `ideal_mxene` |
| another property | a field with unit metadata in `schemas/properties.py`; `SPREADSHEET_COLUMNS` and `load_properties` in `pipelines/build_contributions.py`; tests. The MPContribs columns follow automatically. |
| another calculation method | `Method` in `schemas/provenance.py`; tests |

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
- [ ] Every new or changed field has a description; numeric fields declare their unit in `json_schema_extra`; integers that are categories rather than quantities declare none (text column).
- [ ] Every string field is a `Literal` or has a pattern and a maximum length; numeric fields have bounds.
- [ ] Field names are camelCase without underscores; the schema has no list fields; at most 50 columns (enforced by tests).
- [ ] Each model declares `model_config = ConfigDict(extra="forbid", allow_inf_nan=False)`; docstrings follow the Google style.
- [ ] Every new rule has tests that accept a conforming structure and reject a non-conforming one.
- [ ] Documentation is updated: this README (rules, phases, accepted data), `pipelines/README.md` (commands, errors), `schemas/README.md` (fields).
- [ ] Test data is limited to small sample files. No credentials appear in code, commits or logs.

### Invariants

The following are part of the public contract. Changing any of them requires MP review:

1. `MXeneEntry` is exactly the contribution `data`; the structure is submitted in `structures`, never in `data`.
2. `mxeneId` is `<reduced formula>-<label>`, is unique within the project, and is the contribution identifier.
3. M, X, T and n are determined by the atoms, never by folder names.
4. Structural quantities are computed from the structure, never read from a spreadsheet.
5. A structure whose geometry contradicts its label is rejected, not relabelled.
6. When several structures claim the same `mxeneId`, all are rejected.
7. Every model is Arrow-compatible.

### Guidance for automated (AI) contributors

- Read this file, [`pipelines/README.md`](pipelines/README.md), [`schemas/README.md`](schemas/README.md), `schemas/labels.py`, `schemas/mxene.py`, `pipelines/structure_analysis.py` and the tests before making changes.
- Keep `schemas/` free of computation on structures and files; such code belongs in `pipelines/`.
- Run the tests before and after a change and report both results.
- Do not relax a check, tolerance or labelling rule to make data pass. Report failing files and their messages instead.
- Do not change identifiers, field names or units without the maintainers' agreement.
- Never write credentials to files, commits or logs.
- Keep commits small; state in each commit message which rule or behaviour changed.
