# two_d_mxenes pipelines

Tools that turn the raw MXene data (a tree of VASP `CONTCAR` files plus a properties spreadsheet) into validated records, helper files for the data owner, and uploads for MPContribs. Rules and background are in the [project README](../README.md); fields are in [`schemas/README.md`](../schemas/README.md).

| file | purpose |
|---|---|
| `build_contributions.py` | dataset check (command line), properties template and loader, record building, MPContribs contribution format, Parquet export |
| `dataset_overview.py` | Excel overview grid of which structures are good, broken or missing |

## Contents

- [Setup](#setup)
- [Dataset layout](#dataset-layout)
- [The dataset check (command line)](#the-dataset-check-command-line)
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
# from the repository root, in a Python >= 3.11 environment
pip install -e "mpcontribs-lux[test]"
pip install openpyxl                 # Excel overview and .xlsx spreadsheets
pip install mpcontribs-client        # only needed for uploading
```

---

## Dataset layout

```
MXENE_DATA/
├── tic/m2x/t-1/CONTCAR                          ← leaf folder name = label
├── tic/m2x/no-termination/t/CONTCAR             ← pristine: no suffix
├── tic/m3x2/o-terminated/h1a-2/CONTCAR
├── Re/m3x/ReN/h1b-1/CONTCAR                     ← extra nesting is fine
└── moc/m3x2/no-termination/h1a/
    ├── CONTCAR                                  ← the entry
    └── super331/phonon/CONTCAR                  ← auxiliary: skipped
```

- The file must be named `CONTCAR`.
- The folder that directly contains it must be a **label**: `t`, `h` (n = 1 only), `h1a`, `h1b`, `h2` (n ≥ 2 only), each followed by `-1` or `-2` if the MXene is terminated. Labels are case-insensitive but the hyphen is required.
- Folders above the label folder can have any names and any depth. They are not read.
- A `CONTCAR` in a sub-folder *inside* a label folder (for example `h1a/d2/`, `h1a/super331/phonon/`) is treated as an **auxiliary calculation** on that entry and skipped. A `CONTCAR` in a wrongly named folder that is *not* inside a label folder is an error, so a misnamed entry is never silently skipped.

---

## The dataset check (command line)

```bash
python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions MXENE_DATA \
    [--report check_report.csv] \
    [--overview dataset_overview.xlsx] \
    [--template properties.csv]
```

| option | writes |
|---|---|
| *(none)* | console summary only |
| `--report FILE.csv` | one row per CONTCAR with its status and reason |
| `--overview FILE.xlsx` | the Excel overview grid (needs `openpyxl`) |
| `--template FILE.csv` | the properties spreadsheet for the researcher, one row per **valid** structure; refreshes an existing file without losing entered values |

The exit code is `0` if every structure passed and `1` otherwise, so the command can gate scripts or CI.

The console output has four parts:

1. **Counts**: `N structures valid, N failed, N skipped (auxiliary calculations)`.
2. **Composition table**: valid structures per M, X, T and n.
3. **Termination-site table**: for every `n`/label combination, the outer-metal coordination measured on the bottom and top surfaces, counting failed structures too. A healthy dataset shows one value per row matching the rule (`O,O` or `P,P`). A row split between two values points at individual bad files; a row with the opposite value everywhere points at a labelling convention problem.
4. **Failures**: one line per failing file with its reason.

---

## Output files

### `--report` (CSV)

| column | meaning |
|---|---|
| `path` | CONTCAR path relative to the dataset root |
| `status` | `valid`, `failed` or `skipped` |
| `formula` | reduced formula of the atoms in the file, e.g. `Hf3C2F2` |
| `folderLabel` | name of the folder containing the file |
| `measuredCoordination` | the full O/P sequence, even for failed files (blank if it could not be measured) |
| `mxeneId` | ID of the accepted record (valid files only) |
| `message` | reason for failure or skip |

### `--overview` (Excel)

- **Overview** sheet: a grid with one row per M–X system (Ti–C … Re–N) and one column per structure that can exist (50 columns: n → termination → label). Symbols:
  - ✓ the CONTCAR passes every check
  - ✗ the CONTCAR has a problem; hover the cell for the file and reason
  - ○ no CONTCAR, although the structure is part of the study
  - grey: not part of the study

  Per-row and per-column totals are included. The study scope is `STUDY_TERMINATIONS` in `dataset_overview.py` (currently: Ti, Mo → pristine, F, O; Hf, Re → F only). Change it there if the scope changes.
- **Problems**: every failed file with the structure it claims, its measured sequence and the reason.
- **Missing**: every ○ cell as a filterable list, to ask the researcher which ones are intentional.
- **All files**: the full per-file report.

### `--template` (CSV)

See [Properties spreadsheet](#properties-spreadsheet).

---

## Error catalogue

Every failing file gets one of the messages below. **Fix data problems in the data**, not by loosening the checks. If you believe a rule itself is wrong, raise it with the maintainer; changing a rule is a schema change (see the [project README](../README.md#rules-that-must-not-be-broken)).

### Folder and file problems

| message | meaning | what to do |
|---|---|---|
| `Unrecognized MXene folder label 'X'` | the folder containing the CONTCAR is not a label, and it is not inside a label folder | rename the folder to its label, or move an auxiliary calculation inside its entry's folder |
| `Stacking 'h1a' is not defined for n=1; expected one of ['h', 't']` | label not allowed for this thickness, e.g. an `h1a` folder holding an M₂X file | the file is in the wrong folder, or the folder is misnamed |
| `terminationSite must be set if and only if termination is set` | a pristine structure in a `-1`/`-2` folder, or a terminated structure in a folder without a suffix | move the file, or rename the folder |
| a pymatgen error (`ValueError`, `IndexError`, `OSError` …) | the CONTCAR cannot be read: empty, truncated (the job was killed), or not a POSCAR/CONTCAR | re-copy the file from the calculation, or re-run the calculation |
| `Lattice vectors a and b must lie in the xy plane (sheet plane)` | the cell is oriented with the sheet not in the a–b plane | re-orient the cell so c is the surface normal |

### Composition problems

| message | meaning | what to do |
|---|---|---|
| `Cannot infer MXene labels from <formula>` | not one transition metal + one of C/N + at most one of F/O (e.g. a mixed-metal or foreign-element file) | wrong file, or a new chemistry the schema does not cover yet (see [Adding new MXene data](../README.md#adding-new-mxene-data-later)) |
| `Not an M_(n+1)X_n composition: <formula>` | the metal count is not one more than the X count per formula unit | wrong or damaged file |
| `Labels imply <A> but the structure is <B>` | e.g. termination on only one surface (M₂XT₁) | one-sided termination is not part of the schema: remove the file, or discuss a schema change |
| `Duplicate '<id>': also claimed by <other file>` | two or more files are the same structure (same formula and label). All of them are rejected, because the check cannot tell which is right | see [Duplicates](#duplicates) |

### Geometry problems

| message | meaning | what to do |
|---|---|---|
| `Stacking 's' implies core coordination X but the structure has Y` | the metal/X layers are not stacked as the label says | see [Structure does not match its label](#structure-does-not-match-its-label) |
| `Termination site k of 's' (n=…) implies outer-metal coordination C on both surfaces but the structure has (…)` | the termination is on the other site, or on different sites on the two surfaces | see [Structure does not match its label](#structure-does-not-match-its-label) |
| `Mixed-species atomic layer found: [...] at z = [...] Å; ...` | atoms of different elements lie within 0.4 Å of each other along the normal, so the layers cannot be separated | see [Strongly distorted structures](#strongly-distorted-structures) |

### Duplicates

The formula is read from the element names and counts in the CONTCAR. VASP copies those names from the starting POSCAR, but the atoms actually simulated are set by the **POTCAR**. So for a duplicate such as a `HfN/t-1` folder holding `Hf2CF2`:

1. Check the `TITEL` lines of the POTCAR (or the OUTCAR) in that folder.
   - They list the expected element (N): the calculation is right and only the element name in the POSCAR/CONTCAR header is wrong. Correct the header line(s) in the CONTCAR.
   - They list the wrong element (C): the calculation used the wrong chemistry. Remove the file; it needs to be re-run.
2. Compare the lattice and coordinates with the other file. If they are identical to many decimal places, one file is a copy of the other.

### Structure does not match its label

The label describes the *starting* stacking; the check measures the *relaxed* structure. A mismatch means one of:

- **A copied or misplaced file.** It often has an identical twin: filter the report by `formula` and `measuredCoordination` to find another file with the same values. Identical coordinates (to many decimals) confirm a copy. Replace it with the right file.
- **The structure changed during relaxation**, e.g. a termination atom hopped to the other site, or a metal layer slid. Compare the CONTCAR with the POSCAR from the same folder. Atoms that moved by about 1.8 Å in the plane (one site-to-site distance) confirm it. A relaxation from a high-symmetry site normally cannot do this unless symmetry was switched off or broken, so it is also worth checking the INCAR (`ISYM`).

Do **not** relabel a relaxed structure to make it pass. Whether such structures are dropped, or kept under their starting label with a flag saying the relaxed stacking differs, is a schema decision to make with the maintainer and MP. It would be recorded in this catalogue and the project README.

### Strongly distorted structures

The layers of the relaxed structure are no longer flat and separated, typically because the stacking is unstable and the sheet reconstructed. Look at the structure (VESTA, OVITO, ASE GUI). If it is a genuine reconstruction, it cannot be described by the stacking labels and is left out (or handled by a documented schema decision, as above). If the layers are merely buckled by more than 0.4 Å, raise it with the maintainer before changing `LAYER_Z_TOLERANCE`.

### Missing structures (○)

Not an error. Use the **Missing** sheet of the overview to ask the researcher which are intentional (not calculated, or not stable) and which are files that did not get copied. If a whole block is out of scope, change `STUDY_TERMINATIONS` so the overview shows it grey.

---

## Properties spreadsheet

Values that cannot be computed from a structure come from a spreadsheet.

### Create it

```bash
python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions MXENE_DATA --template properties.csv
```

This writes one row per **valid** structure, in the same order as the overview grid. Fix failing files first if you want them included.

| columns | filled by | notes |
|---|---|---|
| `mxeneId` | the tool | key used to match rows to structures; do not edit |
| `M`, `X`, `T`, `n`, `stacking`, `terminationSite`, `coordinationSequence`, `a [angstrom]`, `thickness [angstrom]`, `vacuum [angstrom]`, `metalNonmetalBondLength [angstrom]`, `metalTerminationBondLength [angstrom]`, `spaceGroup`, `file` | the tool | read-only information for whoever fills the sheet; ignored when reading it back (always recomputed from the CONTCARs) |
| `totalEnergyPerAtom [eV/atom]` | researcher | DFT total energy of the relaxed slab per atom; used to compute `relativeStackingEnergy` |
| `formationEnergyPerAtom [eV/atom]` | researcher | state the reference energies in the project description |
| `c11 [N/m]`, `c12 [N/m]` | researcher | 2D elastic constants (per unit area, **not** GPa) |
| `c66 [N/m]` | researcher (optional) | leave blank to use (C11 − C12)/2 |

Rules for filling it in:

- Numbers only in property cells; leave a cell **blank** if the value is unknown (no `N/A`, `-` or `0`).
- Give `c11` and `c12` together (and optionally `c66`), or leave all three blank.
- Keep the unit in each header. If the unit in a header is changed (e.g. to `[GPa]`), reading the sheet fails rather than storing wrong numbers.
- The file may be opened and saved in Excel, as `.csv` or `.xlsx`. Both can be read.

Young's modulus, Poisson's ratio, shear modulus and Born stability are computed from C11/C12/C66. The relative stacking energy is computed from total energies within each composition.

### Refresh it

Run the same `--template` command again after fixing structures. Values already entered are kept for every structure that is still valid. Rows that had values but whose structure is no longer valid are moved to `properties.orphaned.csv` instead of being lost; the console reports how many.

### Adding a property column

Add it in four places, then add a test:

1. a field with a description and unit in `schemas/properties.py`,
2. `SPREADSHEET_COLUMNS` (name and unit),
3. `load_properties` (map the column to the field),
4. if it should be searchable on MPContribs: `MPCONTRIBS_COLUMNS`, `MPCONTRIBS_COLUMN_DESCRIPTIONS` and `to_contribution`.

### Loader errors

| message | what to do |
|---|---|
| `Spreadsheet has unrecognized column 'X'` | a column was added or renamed; restore it, or add the property as above |
| `Column 'c11 [GPa]' has unit 'GPa', expected 'N/m'` | convert the values and restore the header |
| `<id>: give both c11 and c12 (and optionally c66), or leave all three blank` | complete or clear that row's elastic constants |
| `Duplicate mxeneId values: [...]` | a row was copied; keep one |
| `Spreadsheet is missing required column 'mxeneId'` | the key column was deleted or renamed |
| `Input should be a valid number` (pydantic) | text in a number cell, e.g. `N/A`; clear the cell |
| `No valid structure found for spreadsheet rows [...]` (when building records) | a row's structure is missing or failing; fix the structure, or remove the row |

---

## Uploading to MPContribs

Uploading needs (a) the schema PR merged by MP, (b) upload permission from MP (currently @bfoley12), and (c) an MP API key.

### 0. API key

Copy your key from your [Materials Project dashboard](https://next-gen.materialsproject.org/api) and set it as an environment variable; never paste it into code or commit it.

```bash
export MPCONTRIBS_API_KEY="<your key>"                  # macOS/Linux
```
```powershell
[Environment]::SetEnvironmentVariable("MPCONTRIBS_API_KEY", "<your key>", "User")   # Windows; reopen the terminal
```

### 1. Build and check the records

```python
from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
    build_entries, load_properties, to_contribution, write_parquet,
)

props = load_properties("properties.csv")          # or .xlsx
entries = build_entries("MXENE_DATA", properties=props)
print(len(entries), "records")
write_parquet(entries, "two_d_mxenes.parquet")    # full records for MP's S3 bucket
contributions = [to_contribution(e) for e in entries]
```

`build_entries` stops at the first bad structure, so nothing is uploaded from a dataset with problems. To upload the good part while problems are being resolved, use `build_entries(..., skip_invalid=True)`: failing structures are left out, and can be added later.

### 2. Create the project (once)

Confirm with MP whether they create the project or you do. The project name must match this folder (`two_d_mxenes`). The title must be unique and 5–30 characters long, and the description at most 2000 characters.

```python
from mpcontribs.client import Client

client = Client()     # reads MPCONTRIBS_API_KEY
client.create_project(
    name="two_d_mxenes",
    title="MXenes: A Panoramic View",
    authors="N. Oyeniran, O. Chowdhury, C. Hu, T. Dumitrica, P. Ganesh, J. Jakowski, "
            "Z. Chen, R. R. Unocic, M. Naguib, V. Meunier, Y. Gogotsi, P. R. C. Kent, "
            "B. G. Sumpter, J. Huang",
    description="DFT-relaxed structures and properties of 2D MXenes M(n+1)X(n)T(x) "
                "(M = Ti, Mo, Hf, Re; X = C, N; n = 1-3; T = none, F, O) across octahedral "
                "and prismatic stackings and termination sites.",
    url="https://doi.org/10.1002/adfm.202508047",
)
```

### 3. Describe the project and initialise the columns

```python
from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
    MPCONTRIBS_COLUMNS, project_other,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas import CalculationSettings

client = Client(project="two_d_mxenes")
settings = CalculationSettings(code="VASP", functional="PBE")   # fill in the real values
client.update_project({
    "references": [
        {"label": "paper", "url": "https://doi.org/10.1002/adfm.202508047"},
        {"label": "preprint", "url": "https://doi.org/10.48550/arXiv.2501.15390"},
        {"label": "data", "url": "https://www.materialsdatafacility.org/detail/a65168f7-8f13-4552-b660-c1565f6d093e-1.0"},
        {"label": "schema", "url": "https://github.com/materialsproject/MPContribs/tree/master/mpcontribs-lux/mpcontribs/lux/projects/two_d_mxenes"},
    ],
    "other": project_other(settings),   # column descriptions + DFT settings
})
client.init_columns(MPCONTRIBS_COLUMNS)
```

`project_other` nests the column descriptions (`geometry.a` becomes `geometry` → `a`) because the MPContribs API rejects keys containing `.` or other punctuation. `init_columns` fixes the column order and units on the project page. In `MPCONTRIBS_COLUMNS`, `None` marks text columns and `""` dimensionless numbers, as the client expects.

**Identifiers.** Each contribution's `identifier` is its `mxeneId` (e.g. `Hf2CF2-h-1`), and its formula is in the separate `formula` field. The formula cannot be the identifier: MPContribs projects accept one contribution per identifier by default (`unique_identifiers=True`), and the client silently skips the rest, so only one structure per formula would be uploaded. None of these 2D sheets has a Materials Project ID (`mp-…`) to link to. If MP prefers another convention, it is a one-line change in `to_contribution`.

### 4. Submit (still private)

```python
client.submit_contributions(contributions)   # add timeout=600 for large uploads
print(client.count(), "contributions in the project")
```

MP allows up to 500 contributions before its approval is needed; this dataset is below that.

### 5. Verify

- The count matches `len(entries)`.
- Open `https://next-gen.materialsproject.org/contribs/projects/two_d_mxenes` (while logged in), check a few rows against the overview, and open one structure.
- Spot-check from Python: `client.query_contributions(query={"identifier": "Ti3C2O2-h1a-2"})`.

### 6. Publish

After MP has reviewed the project:

```python
client.make_public(recursive=True)   # project and its contributions
```

### 7. The Parquet file

`two_d_mxenes.parquet` (step 1) holds the complete records, including arrays, in the schema reviewed in this repository. MP hosts these files on its MPContribs S3 bucket; the credentials and destination come from MP when upload permission is granted. It can be read back and re-validated with `read_parquet`.

### Updating an existing upload

- **While the project is private**, the simplest approach is to replace everything. `client.delete_contributions()` removes all contributions of the project; then re-submit.
- **After it is public**, agree the update with MP first. Individual contributions can be updated by submitting dictionaries that include their contribution `id` and only the changed fields (see `Client.submit_contributions`).
- **Adding new structures**: re-run the check, refresh the template, build entries, and submit all contributions again. Those whose `mxeneId` is already in the project are skipped; only new ones are added. Changed values of existing ones are *not* updated this way (see the previous point).

---

## Upload errors

| error | cause | what to do |
|---|---|---|
| `Project with {'name': ...} already exists!` | the project was created already (by you or MP) | skip step 2 and use `Client(project="two_d_mxenes")` |
| `Project with {'title': ...} already exists!` | the title is taken by another project | choose another title |
| `401` / `403` / "not authorized" | API key missing or wrong, or no permission for this project yet | check `MPCONTRIBS_API_KEY`; ask MP for permission |
| `certificate verify failed` (SSL) | Python cannot find root certificates | `pip install certifi`, then set `SSL_CERT_FILE` to the output of `python -m certifi` |
| `OverflowError: timeout value is too large` | known issue in the `bravado` dependency | see "Troubleshooting" in the [mpcontribs-client README](../../../../../../mpcontribs-client/README.md) |
| timeouts on large uploads | slow connection or big batch | pass `timeout=...` (seconds) to `submit_contributions`; re-running skips contributions whose identifier (`mxeneId`) already exists |
| `<id> already added for <project>` | a contribution with this `mxeneId` exists already | expected on re-runs; to change it, update it (see above) |
| far fewer contributions than records after upload | contributions were built by hand with a shared identifier such as the formula | build them with `to_contribution`, which uses the unique `mxeneId` |
| `Number of columns larger than 160!` / unit errors | `init_columns` input changed by hand | use `MPCONTRIBS_COLUMNS` unchanged; a test keeps it consistent with `to_contribution` |
| `invalid character . in …` (from `update_project`) | a dictionary with dotted or punctuated keys was passed as `other` | use `project_other(settings)` |
| `Nothing to submit for contribution #i` / `Empty 'data'` | a contribution dictionary was built by hand incorrectly | build contributions only with `to_contribution` |
| more than 500 contributions rejected | MP approval threshold | contact MP |

---

## Python API summary

All in `build_contributions.py` unless noted.

| function | purpose |
|---|---|
| `check_dataset(root)` | validate every CONTCAR, collecting all failures; returns `CheckResult` (`.records`, `.entries`, `.failures`, `.skipped`) |
| `build_entries(root, properties=None, skip_invalid=False)` | validated `MXeneEntry` list, with properties attached and relative stacking energies computed |
| `entry_from_file(path)` | one entry from one CONTCAR |
| `load_properties(path)` | read the properties CSV/XLSX into `{mxeneId: MXeneProperties}` |
| `write_properties_template(entries, path, files=None)` | write or refresh the properties CSV |
| `to_contribution(entry)` | MPContribs contribution dictionary |
| `MPCONTRIBS_COLUMNS` | column units for `init_columns` |
| `MPCONTRIBS_COLUMN_DESCRIPTIONS` | column descriptions (flat; keep in sync with `MPCONTRIBS_COLUMNS`) |
| `project_other(settings=None)` | project `other` metadata for `update_project`: nested column descriptions plus DFT settings |
| `write_parquet(entries, path)`, `read_parquet(path)` | full records to and from Parquet |
| `termination_site_table(result)` | measured outer-metal coordination per label (the console table) |
| `write_report(result, path, root)` | the `--report` CSV |
| `dataset_overview.write_overview(result, path, root)` | the `--overview` workbook |
| `dataset_overview.grid_states(result)` | the state (✓/✗/○/out of scope) of every grid cell |

---

## Tolerances

Defined at the top of `schemas/structure.py`:

| constant | value | used for |
|---|---|---|
| `LAYER_Z_TOLERANCE` | 0.4 Å | atoms closer than this along the normal belong to the same layer |
| `ECLIPSED_XY_TOLERANCE` | 0.5 Å | two layers closer than this in the plane are eclipsed (P); in an ideal cell staggered sites are about a/√3 ≈ 1.8 Å apart |
| `SYMPREC` | 0.1 Å | spglib symmetry tolerance for the space group |

Changing a tolerance changes which structures pass. Treat it as a schema change: re-run the full dataset and report the before/after counts in the PR.
