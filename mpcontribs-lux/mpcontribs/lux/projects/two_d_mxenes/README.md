# two_d_mxenes

Relaxed structures and computed properties of 2D MXenes, M<sub>n+1</sub>X<sub>n</sub>T<sub>x</sub>, for the Materials Project's [MPContribs](https://docs.materialsproject.org/services/mpcontribs) platform. The dataset systematically varies

- the transition metal **M**: Ti, Mo, Hf, Re
- the non-metal **X**: C (carbides), N (nitrides)
- the thickness **n**: 1, 2, 3 (M<sub>2</sub>X, M<sub>3</sub>X<sub>2</sub>, M<sub>4</sub>X<sub>3</sub>)
- the surface termination **T**: none (pristine), F, O
- the stacking of the layers: octahedral (**O**) or trigonal-prismatic (**P**) coordination of each layer, and the site occupied by the termination

**Reference:** N. Oyeniran, O. Chowdhury, C. Hu, T. Dumitrica, P. Ganesh, J. Jakowski, Z. Chen, R. R. Unocic, M. Naguib, V. Meunier, Y. Gogotsi, P. R. C. Kent, B. G. Sumpter, J. Huang, "A Panoramic View of MXenes via a New Design Strategy", *Adv. Funct. Mater.* (2025), [doi:10.1002/adfm.202508047](https://doi.org/10.1002/adfm.202508047); preprint [arXiv:2501.15390](https://doi.org/10.48550/arXiv.2501.15390).

**Raw data:** [Materials Data Facility](https://www.materialsdatafacility.org/detail/a65168f7-8f13-4552-b660-c1565f6d093e-1.0)

**Maintainers:** Aidan Gesch (University of Alabama, Hu group). MP reviewer: @bfoley12.

---

## Contents

1. [What is in this folder](#what-is-in-this-folder)
2. [How MXenes are labelled](#how-mxenes-are-labelled)
3. [What one record contains](#what-one-record-contains)
4. [Quick start](#quick-start)
5. [End-to-end workflow: from raw data to MPContribs](#end-to-end-workflow-from-raw-data-to-mpcontribs)
6. [Adding new MXene data later](#adding-new-mxene-data-later)
7. [Contributing and pull requests (humans and AI agents)](#contributing-and-pull-requests-humans-and-ai-agents)

Detailed references:

- [`pipelines/README.md`](pipelines/README.md): every command, every output file, every error message and what to do about it, and the step-by-step MPContribs upload.
- [`schemas/README.md`](schemas/README.md): every field of every model, with types, units and descriptions.

---

## What is in this folder

```
mpcontribs-lux/
├── mpcontribs/lux/projects/two_d_mxenes/
│   ├── README.md                    ← this file
│   ├── pip-extra-requirements.txt   extra packages (openpyxl for .xlsx files)
│   ├── schemas/                     the data contract (pydantic models)
│   │   ├── README.md                field reference
│   │   ├── labels.py                M, X, T, n, stacking, termination site + rules
│   │   ├── structure.py             relaxed structure + descriptors computed from it
│   │   ├── properties.py            properties from the researcher's spreadsheet
│   │   ├── calculation.py           project-level DFT settings
│   │   └── mxene.py                 MXeneEntry: one validated record per structure
│   └── pipelines/                   tools that turn raw data into records and uploads
│       ├── README.md                usage, error catalogue, upload guide
│       ├── build_contributions.py   dataset check, properties template, MPContribs format, Parquet
│       └── dataset_overview.py      Excel overview grid of the dataset
├── tests/projects/two_d_mxenes/test_two_d_mxenes.py
└── test_data/by_user/two_d_mxenes/MXENE_DATA/Hf/m2x/h-1/CONTCAR   (sample Hf₂CF₂)
```

The **schemas** are the contract between the data and its users: MP staff review them, and every record uploaded must validate against them. The **pipelines** are how records are produced from the raw CONTCAR files and the properties spreadsheet.

---

## How MXenes are labelled

Each structure in the raw dataset is a VASP `CONTCAR` in a folder whose name is its **label**, for example `h1a-2`. Everything else about an MXene is read from the atoms in the file.

| label part | where it comes from | values |
|---|---|---|
| M, X, T | composition of the CONTCAR | M: transition metal; X: C or N; T: F, O or none |
| n | composition: M<sub>n+1</sub>X<sub>n</sub> | 1, 2, 3 |
| stacking | folder name, before the hyphen | `t`, `h` (n = 1); `t`, `h1a`, `h1b`, `h2` (n ≥ 2) |
| termination site | folder name, after the hyphen | `-1`, `-2` (terminated only; pristine folders have no suffix) |

The folders above the label folder (`tic/m2x/o-terminated/`, `Re/m3x/ReN/`, …) are **not** used, so the nesting can differ between metals. The unique ID of a record is `mxeneId = <formula>-<label>`, e.g. `Ti3C2O2-h1a-2` or `Mo2C-t`.

### Coordination sequence

Every atomic layer that has a layer below and above it is classified as

- **O** (octahedral) if the layers directly below and above it are *staggered* in the plane, or
- **P** (trigonal prismatic) if they are *eclipsed* (sit directly above one another).

This **coordination sequence** is measured from every structure (`StructureDescriptors.coordinationSequence`), listing interior layers from bottom to top. A pristine M<sub>n+1</sub>X<sub>n</sub> has 2n − 1 interior layers (X, M, X, …); a terminated one has 2n + 1 (outer M, X, M, …, X, outer M).

### Stacking labels (the core of the sheet)

The **core** is the part of the sequence between the two outermost metal layers.

| label | n | core sequence |
|---|---|---|
| `t` | 1 | O |
| `h` | 1 | P |
| `t` | 2, 3 | O-O-O(-O-O) |
| `h2` | 2, 3 | P-P-P(-P-P) |
| `h1a` | 2, 3 | O-P-O(-P-O) |
| `h1b` | 2, 3 | P-O-P(-O-P) |

In the core, odd positions (1st, 3rd, …) are X layers and even positions are the inner metal layers. So in `t` and `h1b` the inner metal layers are **O**, and in `h1a` and `h2` they are **P**.

### Termination site (the outer metal layers)

For terminated MXenes the suffix sets the coordination of the two outer metal layers, i.e. the first and last entries of the full sequence:

| n | stacking | `-1` | `-2` |
|---|---|---|---|
| 1 | `t`, `h` | O | P |
| ≥ 2 | `t`, `h1b` (inner metal layers O) | O | P |
| ≥ 2 | `h1a`, `h2` (inner metal layers P) | P | O |

In words: **for n = 1, site 1 is octahedral and site 2 is prismatic; for n ≥ 2, site 1 gives the outer metal layers the same coordination as the inner metal layers, and site 2 the opposite.** Geometrically, O means the termination sits staggered relative to the X layer under the outer metal; P means it sits directly above an X atom.

This rule was derived from the data: it holds for all 211 structures that passed the checks in the first full run (2026-09-29). It is implemented in `labels.expected_termination_coordination`.

Examples of full sequences: `Hf2CF2-h-1` → O-**P**-O; `Mo3C2F2-h1a-1` → P-**O-P-O**-P; `Ti4C3O2-t-2` → P-**O-O-O-O-O**-P (core in bold).

### Checks applied to every structure

A record is only accepted if all of these hold (see [`pipelines/README.md`](pipelines/README.md#error-catalogue) for the exact messages and what to do):

1. The CONTCAR parses, and the sheet lies in the plane of lattice vectors a and b.
2. The composition is M<sub>n+1</sub>X<sub>n</sub> or M<sub>n+1</sub>X<sub>n</sub>T<sub>2</sub> with one M, one X ∈ {C, N} and at most one T ∈ {F, O}.
3. The folder label is valid and allowed for this n (e.g. `h1a` needs n ≥ 2; `h` needs n = 1), and has a site suffix exactly when the MXene is terminated.
4. Every atomic layer contains a single element.
5. The measured core sequence matches the stacking label.
6. The measured outer-metal coordination matches the termination site on both surfaces.
7. No two files claim the same `mxeneId`.

---

## What one record contains

One `MXeneEntry` per CONTCAR:

| group | contents | source |
|---|---|---|
| `mxeneId` | e.g. `Ti3C2O2-h1a-2` | formula + folder label |
| `labels` | metal, nonmetal, termination, n, stacking, terminationSite | composition + folder label |
| `structure` | lattice, species, fractional coordinates | CONTCAR |
| `descriptors` | formula, a, b, γ, cell area, area per formula unit, areal mass density, thickness, vacuum, layer and coordination sequences, M–X and M–T bond lengths, space group | computed from the structure |
| `properties.energetics` | total energy, formation energy, relative stacking energy | spreadsheet (relative energy computed) |
| `properties.elastic` | C11, C12, C66, Young's modulus, Poisson's ratio, shear modulus, Born stability | spreadsheet (C11, C12, C66); the rest computed |

Units: lengths in Å, energies in eV/atom (relative stacking energy in meV/atom), 2D elastic constants and moduli in N/m. Full field list: [`schemas/README.md`](schemas/README.md).

Lattice parameters are *not* taken from the spreadsheet; they are always computed from the CONTCAR so the two can never disagree. DFT settings are the same for every structure, so they are recorded once for the project (`CalculationSettings`), not per record.

On MPContribs each record becomes one **contribution**, with identifier `mxeneId`, 21 searchable `data` columns (listed in `MPCONTRIBS_COLUMNS`) and the structure. The complete records, including arrays, are also written to a Parquet file.

---

## Quick start

```bash
# from the repository root
pip install -e "mpcontribs-lux[test]"
pip install openpyxl            # for the Excel overview and .xlsx spreadsheets

# check the dataset and produce all the helper files
python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions path/to/MXENE_DATA \
    --report check_report.csv \
    --overview dataset_overview.xlsx \
    --template properties.csv

# run the tests
pytest mpcontribs-lux/tests/projects/two_d_mxenes mpcontribs-lux/tests/test_models_for_arrow_compatibility.py
```

On Windows PowerShell, put the command on one line or replace each `\` with a backtick (`` ` ``).

---

## End-to-end workflow: from raw data to MPContribs

| step | who | what | details |
|---|---|---|---|
| 1 | data owner | Collect every relaxed CONTCAR in a folder tree whose leaf folders are named by label. Follow-up calculations (supercells, phonons, D2, …) may live in sub-folders *inside* a label folder; they are skipped. | [Dataset layout](pipelines/README.md#dataset-layout) |
| 2 | data owner | Run the check with `--report` and `--overview`. Fix or remove every ✗ file, and decide which ○ (missing) structures are intentional. Re-run until clean. | [Error catalogue](pipelines/README.md#error-catalogue) |
| 3 | data owner | Run with `--template properties.csv`; give it to the researcher, who fills in energies and elastic constants. Re-running keeps values already entered. | [Properties spreadsheet](pipelines/README.md#properties-spreadsheet) |
| 4 | maintainer | Build records with the filled spreadsheet; write the Parquet file; check the counts. | [Build the records](pipelines/README.md#1-build-and-check-the-records) |
| 5 | maintainer + MP | Schema PR reviewed and merged by MP; MP grants upload permissions. | [Contributing](#contributing-and-pull-requests-humans-and-ai-agents) |
| 6 | maintainer | Create/confirm the MPContribs project, initialise columns, submit contributions (private), verify on the portal. | [Upload](pipelines/README.md#uploading-to-mpcontribs) |
| 7 | maintainer + MP | MP approves (needed above 500 contributions) and the project is made public. | [Publish](pipelines/README.md#6-publish) |

---

## Adding new MXene data later

The pipeline is written for the MXene family, not only this dataset. Typical extensions:

| new data | what to change |
|---|---|
| more structures of existing kinds (e.g. the missing ○ cells) | nothing: add the CONTCARs in correctly named folders and re-run the check |
| a new metal M (any transition metal) | nothing in the schema; add it to `METALS` and `STUDY_TERMINATIONS` in `pipelines/dataset_overview.py` so it gets a row in the overview |
| a new termination (e.g. Cl, OH) | `Termination` in `schemas/labels.py`, the element sets in `infer_chemistry` (`schemas/mxene.py`) and `_mean_nn_distance` callers in `schemas/structure.py`, `TERMINATIONS` in `dataset_overview.py`; then tests. Multi-atom terminations such as OH need a decision on how layers are grouped. |
| a new thickness (n = 4) | `Thickness` and `_THICK_STACKINGS` in `labels.py`; `_STACKINGS` and the `n` loop in `dataset_overview.py` |
| a new property (e.g. band gap) | `schemas/properties.py`; `SPREADSHEET_COLUMNS` and `load_properties` in `pipelines/build_contributions.py`; if it should be searchable on MPContribs, also `MPCONTRIBS_COLUMNS`, `MPCONTRIBS_COLUMN_DESCRIPTIONS` and `to_contribution`; then tests |
| a new stacking label | `StackingLabel`, `expected_core_sequence`, `expected_termination_coordination` in `labels.py`; `_STACKINGS` in `dataset_overview.py`; tests with an `ideal_mxene` structure for it |

Any change to the schemas changes the contract with MP, so it goes through a PR and MP review (below). Uploading more structures of the same kinds does not.

---

## Contributing and pull requests (humans and AI agents)

### Repository and branches

- Work happens in the fork [`ahgesch/MPContribs_MXene`](https://github.com/ahgesch/MPContribs_MXene). Internal work may go straight to its `master`.
- Before opening the PR to [`materialsproject/MPContribs`](https://github.com/materialsproject/MPContribs), create a branch (e.g. `two-d-mxenes-schema`) from the fork's `master`, and open the PR from that branch with **@bfoley12** as reviewer.
- Keep PRs to `mpcontribs-lux/` only: this project's folder, its tests and its test data.

### Before every commit

```bash
pytest mpcontribs-lux/tests/projects/two_d_mxenes mpcontribs-lux/tests/test_models_for_arrow_compatibility.py
ruff check --ignore D,E501,E741,E402 mpcontribs-lux/mpcontribs/lux/projects/two_d_mxenes mpcontribs-lux/tests/projects/two_d_mxenes
black mpcontribs-lux/mpcontribs/lux/projects/two_d_mxenes mpcontribs-lux/tests/projects/two_d_mxenes
```

These match the repository's `.pre-commit-config.yaml` (ruff with those ignores, black). Two tests outside this project (`test_autogen.py`, `esoteric_ephemera`) fail unless Git LFS files are downloaded (`git lfs pull`); that is unrelated to this project.

### PR checklist

- [ ] All tests above pass, including the Arrow compatibility test for every model.
- [ ] Every new or changed field has a `description` with its unit.
- [ ] Field names are camelCase with no underscores (MPContribs rule).
- [ ] `MPCONTRIBS_COLUMNS`, `MPCONTRIBS_COLUMN_DESCRIPTIONS` and `to_contribution` agree (a test enforces this), with at most 50 columns.
- [ ] New rules come with a test that accepts a correct structure *and* rejects an incorrect one (`ideal_mxene` in the tests builds structures with any coordination sequence).
- [ ] Docs updated: this README for rules and workflow, `pipelines/README.md` for commands and errors, `schemas/README.md` for fields.
- [ ] If the change affects existing data, re-run the dataset check and state the before/after counts in the PR description.
- [ ] Test data stays small (a few CONTCARs); never commit the full dataset, API keys or tokens.

### Rules that must not be broken

These are relied on by users of the data. Changing any of them is a schema change that needs MP review:

1. `mxeneId` is `<formula>-<label>`, unique within the project, and is the MPContribs contribution identifier.
2. M, X, T, n come from the atoms, never from folder names above the label folder.
3. Structure-derived values are computed, never copied from a spreadsheet.
4. A record whose structure disagrees with its label is rejected, not corrected. If a structure genuinely relaxed into a different stacking, that needs an explicit, documented decision, not a silent relabel.
5. If several files claim the same structure, all are rejected until the conflict is resolved.
6. All models stay Arrow-compatible (or are explicitly marked `@arrow_incompatible`).

### Notes for AI agents

- Read this file, [`pipelines/README.md`](pipelines/README.md) and [`schemas/README.md`](schemas/README.md) before editing. Then read `schemas/labels.py` (rules), `schemas/mxene.py` (cross-checks) and the tests.
- Run the tests before and after your change and report both results.
- Do not relax a check (tolerances, labelling rules, duplicate handling) to make data pass. If data fails, report the file and the reason to the maintainer; the [error catalogue](pipelines/README.md#error-catalogue) lists likely causes. Data problems are resolved in the data.
- Do not change `mxeneId` formatting, field names or units without the maintainer's agreement: they are the public contract.
- Never add credentials (MP API keys, GitHub tokens) to files, commits, or logs.
- Keep commits small and self-describing; state in the commit message which rule or behaviour changed.
- When unsure whether something is a schema change, treat it as one and ask.
