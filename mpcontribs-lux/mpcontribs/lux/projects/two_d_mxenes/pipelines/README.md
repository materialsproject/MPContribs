# two_d_mxenes pipelines

Tools that convert a tree of relaxed VASP `CONTCAR` files and a properties spreadsheet into validated `MXeneEntry` records, MPContribs contributions and a Parquet file. Labelling rules, validation phases and the accepted data are defined in the [project README](../README.md); fields are listed in [`schemas/README.md`](../schemas/README.md).

| file | purpose |
|---|---|
| `build_contributions.py` | structure check (command line), properties template and loader, record building, MPContribs contribution format, Parquet export |
| `dataset_overview.py` | Excel overview of present, failing and missing structures |

## Contents

- [Setup](#setup)
- [Folder layout](#folder-layout)
- [The structure check (command line)](#the-structure-check-command-line)
- [Output files](#output-files)
- [Error catalogue](#error-catalogue)
- [Properties spreadsheet](#properties-spreadsheet)
- [Uploading to MPContribs](#uploading-to-mpcontribs)
- [Upload errors](#upload-errors)
- [Python API summary](#python-api-summary)
- [Tolerances](#tolerances)

---

## Setup

```bash
# from the repository root, Python >= 3.11
pip install -e "mpcontribs-lux[test]"
pip install openpyxl                 # Excel overview and .xlsx spreadsheets
pip install mpcontribs-client        # uploading only
```

---

## Folder layout

```
DATA_ROOT/
├── Ti/carbides/n1/t-1/CONTCAR            leaf folder name = label
├── Ti/carbides/n1/pristine/t/CONTCAR     pristine: no suffix
├── Ti/carbides/n2/O/h1a-2/CONTCAR
├── Mo/nitrides/n3/F/h1b-1/CONTCAR        any names and depth above the label folder
└── Mo/carbides/n2/pristine/h1a/
    ├── CONTCAR                           the entry
    └── supercell/phonon/CONTCAR          auxiliary calculation: skipped
```

- Structure files are named `CONTCAR`.
- The folder directly containing a `CONTCAR` is its **label**: `t` or `h` (n = 1), or `t`, `h1a`, `h1b`, `h2` (n ≥ 2), followed by `-1` or `-2` for terminated MXenes. Labels are case-insensitive; the hyphen is required.
- Folders above the label folder are not read.
- A `CONTCAR` in a sub-folder of a label folder is an auxiliary calculation on that entry and is skipped. A `CONTCAR` in any other folder is reported as an error.

---

## The structure check (command line)

```bash
python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions DATA_ROOT \
    [--report check_report.csv] \
    [--overview structure_overview.xlsx] [--out-of-scope M:T ...] \
    [--template properties.csv]
```

| option | effect |
|---|---|
| *(none)* | console summary |
| `--report FILE.csv` | one row per `CONTCAR` with status and reason |
| `--overview FILE.xlsx` | Excel overview grid (requires `openpyxl`) |
| `--out-of-scope M:T` | marks a metal/termination combination as not expected in the overview, e.g. `Hf:O`, `Re:none` (pristine) or `*:O` (every metal); repeatable |
| `--template FILE.csv` | properties spreadsheet with one row per valid structure; an existing file is refreshed and its entered values are kept |

The exit code is `0` if every structure passes and `1` otherwise.

Console output:

1. **Counts**: `N structures valid, N failed, N skipped (auxiliary calculations)`.
2. **Composition table**: valid structures per M, X, T and n.
3. **Termination-site table**: the outer-metal coordination measured on the bottom and top surfaces for each n/label combination, including failed structures. Each row of a conforming set shows a single value matching the [termination-site rule](../README.md#termination-site).
4. **Failures**: one line per failing file with its reason.

---

## Output files

### `--report` (CSV)

| column | meaning |
|---|---|
| `path` | path relative to `DATA_ROOT` |
| `status` | `valid`, `failed` or `skipped` |
| `formula` | reduced formula of the atoms in the file, e.g. `Hf3C2F2` |
| `folderLabel` | name of the folder containing the file |
| `measuredCoordination` | full O/P sequence, also for failed files where it can be measured |
| `mxeneId` | ID of the accepted record (valid files only) |
| `message` | reason for failure or skip |

### `--overview` (Excel)

- **Overview**: one row per M–X system (every transition metal found, in order of atomic number, with C and N) and one column per possible structure (50 columns: n → termination → label). Cell symbols:
  - ✓ the `CONTCAR` passes every check
  - ✗ the `CONTCAR` fails; the cell comment gives the file and reason
  - ○ no `CONTCAR`
  - grey: excluded with `--out-of-scope`

  Rows and columns end with ✓/✗/○ totals.
- **Problems**: every failing file with the structure it claims, its measured sequence and the reason.
- **Missing**: every ○ cell as a filterable list.
- **All files**: the per-file report.

### `--template` (CSV)

See [Properties spreadsheet](#properties-spreadsheet).

---

## Error catalogue

Each failing file reports one of the messages below. Failures are resolved by correcting the data; checks, tolerances and labelling rules are not relaxed to admit a structure.

### Folder and file

| message | meaning | resolution |
|---|---|---|
| `Unrecognized MXene folder label 'X'` | the containing folder is not a label and is not inside a label folder | rename the folder to the label, or move the auxiliary calculation into its entry folder |
| `Stacking 'h1a' is not defined for n=1; expected one of ['h', 't']` | the label is not allowed for this thickness | move the file to the correct folder, or correct the folder name |
| `terminationSite must be set if and only if termination is set` | a pristine structure in a `-1`/`-2` folder, or a terminated structure in a folder without a suffix | move the file, or correct the folder name |
| pymatgen `ValueError`, `IndexError` or `OSError` | the file is empty, truncated or not in POSCAR/CONTCAR format | replace the file with the complete output of the calculation |
| `Lattice vectors a and b must lie in the xy plane (sheet plane)` | the sheet is not in the a–b plane | re-orient the cell so that c is the surface normal |

### Composition

| message | meaning | resolution |
|---|---|---|
| `Cannot infer MXene labels from <formula>` (optionally `: unsupported element(s) [...]`) | not exactly one transition metal, one of C/N and at most one of F/O (e.g. a double-metal sheet, mixed terminations, or another element such as Cl or B) | outside the schema: remove the file, or extend the schema (see [Extending the schema](../README.md#extending-the-schema)) |
| `Not an M_(n+1)X_n composition: <formula>` | the metal count is not one more than the X count per formula unit | replace the file |
| `Labels imply <A> but the structure is <B>` | e.g. a termination on only one surface (M₂XT₁) | outside the schema: remove the file |
| `Duplicate '<id>': also claimed by <other file>` | two or more files describe the same `mxeneId`; all are rejected | see [Duplicates](#duplicates) |

### Geometry

| message | meaning | resolution |
|---|---|---|
| `Stacking 's' implies core coordination X but the structure has Y` | the metal/X layers are not stacked as the label states | see [Structure does not match its label](#structure-does-not-match-its-label) |
| `Termination site k of 's' (n=…) implies outer-metal coordination C on both surfaces but the structure has (…)` | the termination occupies the other site, or different sites on the two surfaces | see [Structure does not match its label](#structure-does-not-match-its-label) |
| `Mixed-species atomic layer found: [...] at z = [...] Å; ...` | atoms of different elements lie within 0.4 Å of each other along the normal | see [Strongly distorted structures](#strongly-distorted-structures) |

### Duplicates

The formula is read from the element names in the `CONTCAR`. VASP copies these names from the input POSCAR, whereas the simulated elements are set by the POTCAR. For a duplicate:

1. Compare the `TITEL` lines of the POTCAR (or OUTCAR) with the element names in the `CONTCAR`. If the POTCAR has the expected elements, correct the element names in the `CONTCAR`. If it does not, the calculation used the wrong chemistry and the file is removed.
2. Compare the lattice and coordinates of the duplicates. Identical values identify a copied file, which is replaced with the correct one.

### Structure does not match its label

The label states the intended stacking; the check measures the relaxed structure. A mismatch has one of two causes:

- **A misplaced or copied file.** A copy usually has a twin with the same `formula` and `measuredCoordination` in the report. Replace it with the correct file.
- **A change during relaxation**, such as a termination moving to the other site or a metal layer sliding. Comparing the `CONTCAR` with its POSCAR shows in-plane displacements of about one site-to-site distance (a/√3).

In both cases the structure is rejected. A relaxed structure is never relabelled to pass.

### Strongly distorted structures

The atomic layers are not flat and separable, typically because the sheet reconstructed during relaxation. Such structures cannot be described by the stacking labels and are rejected.

### Missing structures (○)

Missing structures are not errors. The **Missing** sheet lists them. Combinations that are not expected are excluded with `--out-of-scope`.

---

## Properties spreadsheet

Properties that cannot be computed from a structure are supplied in a spreadsheet.

### Generating the template

```bash
python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions DATA_ROOT --template properties.csv
```

The template has one row per valid structure, in the order of the overview grid.

| columns | content |
|---|---|
| `mxeneId` | key matching rows to structures; not edited |
| `M`, `X`, `T`, `n`, `stacking`, `terminationSite`, `coordinationSequence`, `a [angstrom]`, `thickness [angstrom]`, `vacuum [angstrom]`, `metalNonmetalBondLength [angstrom]`, `metalTerminationBondLength [angstrom]`, `spaceGroup`, `file` | read-only information computed from the structures; ignored when the file is read |
| `totalEnergyPerAtom [eV/atom]` | DFT total energy of the relaxed slab per atom; used to compute `relativeStackingEnergy` |
| `formationEnergyPerAtom [eV/atom]` | formation energy per atom; the reference states are stated in the project description |
| `c11 [N/m]`, `c12 [N/m]` | 2D elastic constants per unit area (not GPa) |
| `c66 [N/m]` | optional; (C11 − C12)/2 when blank |

Filling rules:

- Property cells contain numbers or are blank. Placeholders such as `N/A`, `-` or `0` for unknown values are not used.
- `c11` and `c12` are given together (optionally with `c66`), or all three are blank.
- Headers keep their units. A header with a different unit (e.g. `[GPa]`) is rejected when the file is read.
- The file may be saved as `.csv` or `.xlsx`.

Young's modulus, Poisson's ratio, shear modulus and Born stability are computed from C11, C12 and C66. The relative stacking energy is computed from total energies within each composition.

### Refreshing the template

Running `--template` on an existing file keeps all entered values for structures that are still valid. Rows with values whose structure is no longer valid are written to `<name>.orphaned.csv`.

### Adding a property

1. Add a field with description and unit to `schemas/properties.py`.
2. Add the column and unit to `SPREADSHEET_COLUMNS`.
3. Map the column to the field in `load_properties`.
4. For a searchable column, add it to `MPCONTRIBS_COLUMNS`, `MPCONTRIBS_COLUMN_DESCRIPTIONS` and `to_contribution`.
5. Add tests.

### Loader errors

| message | resolution |
|---|---|
| `Spreadsheet has unrecognized column 'X'` | restore the template column, or add the property as above |
| `Column 'c11 [GPa]' has unit 'GPa', expected 'N/m'` | convert the values and restore the header |
| `<id>: give both c11 and c12 (and optionally c66), or leave all three blank` | complete or clear the row's elastic constants |
| `Duplicate mxeneId values: [...]` | remove the duplicated row |
| `Spreadsheet is missing required column 'mxeneId'` | restore the key column |
| `Input should be a valid number` (pydantic) | replace the text in the numeric cell with a number, or clear it |
| `No valid structure found for spreadsheet rows [...]` (when building records) | correct the structure, or remove the row |

---

## Uploading to MPContribs

Uploading requires the schema to be merged into `materialsproject/MPContribs`, upload permission granted by MP, and an MP API key. The steps follow the [MPContribs upload documentation](https://docs.materialsproject.org/uploading-data/what-is-mpcontribs).

### 0. API key

The API key is on the [Materials Project dashboard](https://next-gen.materialsproject.org/api). It is set as an environment variable and never written into code or files.

```bash
export MPCONTRIBS_API_KEY="<api key>"                  # macOS/Linux
```
```powershell
[Environment]::SetEnvironmentVariable("MPCONTRIBS_API_KEY", "<api key>", "User")   # Windows; reopen the terminal
```

### 1. Build and check the records

```python
from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
    build_entries, load_properties, to_contribution, write_parquet,
)

props = load_properties("properties.csv")          # or .xlsx
entries = build_entries("DATA_ROOT", properties=props)
write_parquet(entries, "two_d_mxenes.parquet")
contributions = [to_contribution(e) for e in entries]
```

`build_entries` raises on the first failing structure. `build_entries(..., skip_invalid=True)` returns only the valid structures, so that a subset can be uploaded and the remainder added later.

### 2. Create the project

The project is created once. Its name is `two_d_mxenes`, matching this folder. The title must be unique and 5–30 characters long; the description is at most 2000 characters.

```python
from mpcontribs.client import Client

client = Client()     # reads MPCONTRIBS_API_KEY
client.create_project(
    name="two_d_mxenes",
    title="<project title>",
    authors="<comma-separated authors>",
    description="<description of the contributed data>",
    url="<URL of the primary reference>",
)
```

### 3. Describe the project and initialise the columns

```python
from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
    MPCONTRIBS_COLUMNS, project_other,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas import CalculationSettings

client = Client(project="two_d_mxenes")
settings = CalculationSettings(code="VASP", functional="PBE")   # the settings used
client.update_project({
    "references": [
        {"label": "paper", "url": "<URL of the primary reference>"},
        {"label": "schema", "url": "https://github.com/materialsproject/MPContribs/tree/master/mpcontribs-lux/mpcontribs/lux/projects/two_d_mxenes"},
    ],
    "other": project_other(settings),   # column descriptions and DFT settings
})
client.init_columns(MPCONTRIBS_COLUMNS)
```

- `project_other` nests the column descriptions (`geometry.a` becomes `geometry` → `a`), because the MPContribs API rejects keys containing `.` or other punctuation.
- `init_columns` sets the column order and units. In `MPCONTRIBS_COLUMNS`, `None` marks text columns and `""` dimensionless numbers, as the client specifies.
- **Identifiers.** Each contribution's `identifier` is its `mxeneId` (e.g. `Hf2CF2-h-1`); the formula is in `formula`. Projects accept one contribution per identifier by default (`unique_identifiers=True`). Several structures share a formula, so a formula identifier would retain only one of them.

### 4. Submit

```python
client.submit_contributions(contributions)   # timeout=<seconds> for large uploads
print(client.count(), "contributions in the project")
```

Contributions are private until published. Projects that MP has not yet approved accept up to 500 contributions.

### 5. Verify

- `client.count()` equals `len(entries)`.
- The project page `https://next-gen.materialsproject.org/contribs/projects/two_d_mxenes` (signed in) shows the expected rows and structures.
- Individual contributions can be retrieved with `client.query_contributions(query={"identifier": "Ti3C2O2-h1a-2"})`.

### 6. Publish

After approval by MP:

```python
client.make_public(recursive=True)   # project and contributions
```

### 7. Parquet file

`two_d_mxenes.parquet` holds the complete records in the reviewed schema. MP hosts Parquet files on the MPContribs S3 bucket; credentials and destination are provided by MP with upload permission. `read_parquet` reads and re-validates the file.

### Updating an upload

- **Private project:** `client.delete_contributions()` removes all contributions; the full set is then submitted again.
- **Public project:** updates are coordinated with MP. A contribution is updated by submitting a dictionary with its contribution `id` and the changed fields (`Client.submit_contributions`).
- **New structures:** rebuilding and submitting all contributions adds only those whose `mxeneId` is not yet in the project. Existing contributions are not modified this way.

---

## Upload errors

| error | cause | resolution |
|---|---|---|
| `Project with {'name': ...} already exists!` | the project exists | skip step 2; use `Client(project="two_d_mxenes")` |
| `Project with {'title': ...} already exists!` | the title is in use | choose another title |
| `401` / `403` / not authorized | API key missing or invalid, or no upload permission | check `MPCONTRIBS_API_KEY`; request permission from MP |
| `certificate verify failed` | Python cannot locate root certificates | `pip install certifi`; set `SSL_CERT_FILE` to the output of `python -m certifi` |
| `OverflowError: timeout value is too large` | known issue in the `bravado` dependency | see "Troubleshooting" in the [mpcontribs-client README](../../../../../../mpcontribs-client/README.md) |
| timeouts | large batch or slow connection | pass `timeout=<seconds>` to `submit_contributions`; re-running skips contributions already present |
| `<id> already added for <project>` | a contribution with this `mxeneId` exists | expected when re-submitting; update it as described above to change it |
| fewer contributions than records | contributions built with a shared identifier | build contributions with `to_contribution` |
| `Number of columns larger than 160!` or unit errors | modified column definitions | use `MPCONTRIBS_COLUMNS` unchanged |
| `invalid character . in …` (from `update_project`) | dotted or punctuated keys in `other` | use `project_other(settings)` |
| `Nothing to submit for contribution #i` / `Empty 'data'` | malformed contribution dictionary | build contributions with `to_contribution` |
| more than 500 contributions rejected | the project is not yet approved | request approval from MP |

---

## Python API summary

All in `build_contributions.py` unless noted.

| function | purpose |
|---|---|
| `check_dataset(root)` | validate every `CONTCAR` and collect all failures; returns `CheckResult` (`.records`, `.entries`, `.failures`, `.skipped`) |
| `build_entries(root, properties=None, skip_invalid=False)` | validated `MXeneEntry` list with properties and relative stacking energies |
| `entry_from_file(path)` | one entry from one `CONTCAR` |
| `load_properties(path)` | properties CSV/XLSX as `{mxeneId: MXeneProperties}` |
| `write_properties_template(entries, path, files=None)` | write or refresh the properties CSV |
| `to_contribution(entry)` | MPContribs contribution dictionary |
| `MPCONTRIBS_COLUMNS` | column units for `init_columns` |
| `MPCONTRIBS_COLUMN_DESCRIPTIONS` | column descriptions (flat, same keys as `MPCONTRIBS_COLUMNS`) |
| `project_other(settings=None)` | project `other` metadata: nested column descriptions and DFT settings |
| `write_parquet(entries, path)`, `read_parquet(path)` | complete records to and from Parquet |
| `termination_site_table(result)` | measured outer-metal coordination per label |
| `write_report(result, path, root)` | the `--report` CSV |
| `dataset_overview.write_overview(result, path, root, out_of_scope=())` | the `--overview` workbook |
| `dataset_overview.grid_states(result, out_of_scope=())` | state (✓/✗/○/out of scope) of every grid cell |
| `dataset_overview.parse_scope_exclusion(text)` | parse `M:T` into a scope exclusion |

---

## Tolerances

Defined in `schemas/structure.py`:

| constant | value | use |
|---|---|---|
| `LAYER_Z_TOLERANCE` | 0.4 Å | atoms closer than this along the normal form one layer |
| `ECLIPSED_XY_TOLERANCE` | 0.5 Å | layers closer than this in the plane are eclipsed (P); staggered sites in an ideal cell are a/√3 ≈ 1.8 Å apart |
| `SYMPREC` | 0.1 Å | spglib tolerance for the space group |

A change to a tolerance changes which structures are accepted and is a schema change subject to MP review.
