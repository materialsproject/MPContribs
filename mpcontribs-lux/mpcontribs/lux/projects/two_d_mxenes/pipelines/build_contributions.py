"""Build validated MXene entries and MPContribs contributions from raw data.

Check a whole dataset from the command line (reports every failure)::

    python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions MXENE_DATA

Use from Python::

    from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
        build_entries, load_properties, to_contribution,
    )

    props = load_properties("mxene_properties.xlsx")
    entries = build_entries("MXENE_DATA", properties=props)
    contributions = [to_contribution(e) for e in entries]

Labels are assigned as follows, which keeps the pipeline independent of how
the dataset's folders are nested (e.g. the extra `ReN/`, `HfN/` levels):

- M, X, T and n are inferred from the composition of each CONTCAR;
- the stacking label and termination site come from the name of the folder
  that directly contains the CONTCAR (e.g. `h1a-2`, `t`).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from mpcontribs.lux.projects.two_d_mxenes.schemas import (
    CalculationSettings,
    ElasticProperties,
    Energetics,
    MXeneEntry,
    MXeneLabel,
    MXeneProperties,
    StructureDescriptors,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.mxene import infer_chemistry
from mpcontribs.lux.projects.two_d_mxenes.schemas.structure import plain_formula
from pydantic import ValidationError
from pymatgen.core import Structure

STRUCTURE_FILENAME = "CONTCAR"

SPREADSHEET_COLUMNS: dict[str, str] = {
    "mxeneId": "",
    "totalEnergyPerAtom": "eV/atom",
    "formationEnergyPerAtom": "eV/atom",
    "c11": "N/m",
    "c12": "N/m",
    "c66": "N/m",
}
"""Property columns read from the spreadsheet, and their units.

These are the values that cannot be computed from a structure. To add a
property, add it here, to `schemas/properties.py`, to `load_properties`, and
(if it should be searchable) to `MPCONTRIBS_COLUMNS` and `to_contribution`.
"""

TEMPLATE_INFO_COLUMNS: dict[str, str] = {
    "M": "",
    "X": "",
    "T": "",
    "n": "",
    "stacking": "",
    "terminationSite": "",
    "coordinationSequence": "",
    "a": "angstrom",
    "thickness": "angstrom",
    "vacuum": "angstrom",
    "metalNonmetalBondLength": "angstrom",
    "metalTerminationBondLength": "angstrom",
    "spaceGroup": "",
    "file": "",
}
"""Read-only columns in the properties template, filled from the structures.

They help whoever fills in the sheet; `load_properties` ignores them because
they are always recomputed from the CONTCARs.
"""

_HEADER = re.compile(r"^\s*(?P<name>[A-Za-z0-9]+)\s*(?:\[(?P<unit>[^\]]*)\])?\s*$")


def _header(name: str, unit: str) -> str:
    return f"{name} [{unit}]" if unit else name


def _parse_header(header: str) -> tuple[str, str | None]:
    """Split `c11 [N/m]` into (`c11`, `N/m`); the unit is None if absent."""
    match = _HEADER.match(str(header))
    if match is None:
        raise ValueError(f"Cannot read spreadsheet column header {header!r}")
    return match.group("name"), match.group("unit")


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig", dtype={"mxeneId": str})
    return pd.read_excel(path, dtype={"mxeneId": str})


def iter_structure_files(root: str | Path) -> Iterator[Path]:
    """Yield every CONTCAR below `root`, in sorted order."""
    yield from sorted(Path(root).rglob(STRUCTURE_FILENAME))


def entry_from_file(
    path: str | Path, properties: MXeneProperties | None = None
) -> MXeneEntry:
    """Build one validated entry from a CONTCAR and its folder label."""
    path = Path(path)
    stacking, site = MXeneLabel.parse_folder_label(path.parent.name)
    structure = Structure.from_file(path)
    return MXeneEntry.from_structure(
        structure, stacking=stacking, terminationSite=site, properties=properties
    )


def load_properties(path: str | Path) -> dict[str, MXeneProperties]:
    """Read the properties spreadsheet (xlsx or csv) keyed by `mxeneId`.

    Headers may carry units in brackets, e.g. `c11 [N/m]`, as written by
    `write_properties_template`; a unit that differs from the expected one is
    an error. Read-only template columns (`TEMPLATE_INFO_COLUMNS`) are ignored.
    """
    path = Path(path)
    df = _read_table(path)
    renamed = {}
    for header in df.columns:
        name, unit = _parse_header(header)
        expected = SPREADSHEET_COLUMNS.get(name, TEMPLATE_INFO_COLUMNS.get(name))
        if expected is None:
            raise ValueError(f"Spreadsheet has unrecognized column {header!r}")
        if unit is not None and unit != expected:
            raise ValueError(
                f"Column {header!r} has unit {unit!r}, expected {expected!r}"
            )
        renamed[header] = name
    df = df.rename(columns=renamed)
    df = df[[c for c in df.columns if c in SPREADSHEET_COLUMNS]]
    if "mxeneId" not in df.columns:
        raise ValueError("Spreadsheet is missing required column 'mxeneId'")
    df = df[df["mxeneId"].notna()]
    if df["mxeneId"].duplicated().any():
        dupes = df.loc[df["mxeneId"].duplicated(), "mxeneId"].tolist()
        raise ValueError(f"Duplicate mxeneId values: {dupes}")

    df = df.astype(object).where(pd.notna(df), None)
    out: dict[str, MXeneProperties] = {}
    for row in df.to_dict(orient="records"):
        c11, c12, c66 = row.get("c11"), row.get("c12"), row.get("c66")
        if (c11 is None) != (c12 is None) or (c66 is not None and c11 is None):
            raise ValueError(
                f"{row['mxeneId']}: give both c11 and c12 (and optionally c66), "
                "or leave all three blank"
            )
        elastic = (
            ElasticProperties.from_elastic_constants(c11, c12, c66)
            if c11 is not None and c12 is not None
            else None
        )
        energetics = Energetics(
            totalEnergyPerAtom=row.get("totalEnergyPerAtom"),
            formationEnergyPerAtom=row.get("formationEnergyPerAtom"),
        )
        out[row["mxeneId"]] = MXeneProperties(energetics=energetics, elastic=elastic)
    return out


_METAL_ORDER = ("Ti", "Mo", "Hf", "Re")
_TERM_ORDER = {None: 0, "F": 1, "O": 2}


def _entry_sort_key(entry: MXeneEntry) -> tuple:
    lab = entry.labels
    metal = _METAL_ORDER.index(lab.metal) if lab.metal in _METAL_ORDER else 99
    return (
        metal,
        lab.metal,
        lab.nonmetal,
        lab.n,
        _TERM_ORDER[lab.termination],
        lab.label,
    )


def template_rows(
    entries: list[MXeneEntry], files: Mapping[str, str] | None = None
) -> pd.DataFrame:
    """One row per entry: read-only structure columns plus blank property columns."""
    files = files or {}
    rows = []
    for entry in sorted(entries, key=_entry_sort_key):
        lab, desc = entry.labels, entry.descriptors
        info = {
            "M": lab.metal,
            "X": lab.nonmetal,
            "T": lab.termination or "none",
            "n": lab.n,
            "stacking": lab.stacking,
            "terminationSite": lab.terminationSite or "none",
            "coordinationSequence": "-".join(desc.coordinationSequence),
            "a": round(desc.a, 4),
            "thickness": round(desc.thickness, 4),
            "vacuum": round(desc.vacuum, 4),
            "metalNonmetalBondLength": round(desc.metalNonmetalBondLength, 4),
            "metalTerminationBondLength": (
                None
                if desc.metalTerminationBondLength is None
                else round(desc.metalTerminationBondLength, 4)
            ),
            "spaceGroup": desc.spaceGroupSymbol,
            "file": files.get(entry.mxeneId, ""),
        }
        row = {_header("mxeneId", ""): entry.mxeneId}
        row.update({_header(k, TEMPLATE_INFO_COLUMNS[k]): v for k, v in info.items()})
        row.update(
            {
                _header(k, u): None
                for k, u in SPREADSHEET_COLUMNS.items()
                if k != "mxeneId"
            }
        )
        rows.append(row)
    columns = (
        ["mxeneId"]
        + [_header(k, u) for k, u in TEMPLATE_INFO_COLUMNS.items()]
        + [_header(k, u) for k, u in SPREADSHEET_COLUMNS.items() if k != "mxeneId"]
    )
    return pd.DataFrame(rows, columns=columns)


def write_properties_template(
    entries: list[MXeneEntry],
    path: str | Path,
    files: Mapping[str, str] | None = None,
) -> dict[str, int]:
    """Write (or refresh) the properties CSV for the researcher to fill in.

    If `path` already exists, property values already entered are kept for
    every structure that is still present. Rows that had values but whose
    structure is no longer valid are moved to `<name>.orphaned.csv` next to
    it rather than lost.

    Returns
    -----------
    dict with counts of `rows`, `kept` (rows with values carried over) and
    `orphaned` rows
    """
    path = Path(path)
    new = template_rows(entries, files)
    fill = [_header(k, u) for k, u in SPREADSHEET_COLUMNS.items() if k != "mxeneId"]
    kept = orphaned = 0

    if path.exists():
        old = _read_table(path)
        old.columns = [
            _header(n, SPREADSHEET_COLUMNS.get(n, TEMPLATE_INFO_COLUMNS.get(n, "")))
            for n, _ in map(_parse_header, old.columns)
        ]
        old_fill = [c for c in fill if c in old.columns]
        old = old[old["mxeneId"].notna()].set_index("mxeneId")
        has_values = (
            old[old_fill].notna().any(axis=1)
            if old_fill
            else pd.Series(False, index=old.index)
        )
        new = new.set_index("mxeneId")
        for mxene_id in old.index[has_values]:
            if mxene_id in new.index:
                for col in old_fill:
                    new.loc[mxene_id, col] = old.loc[mxene_id, col]
                kept += 1
        lost = old[has_values & ~old.index.isin(new.index)]
        if len(lost):
            orphaned = len(lost)
            lost.reset_index().to_csv(
                path.with_suffix(".orphaned.csv"), index=False, encoding="utf-8-sig"
            )
        new = new.reset_index()

    new.to_csv(path, index=False, encoding="utf-8-sig")
    return {"rows": len(new), "kept": kept, "orphaned": orphaned}


def build_entries(
    root: str | Path,
    properties: Mapping[str, MXeneProperties] | None = None,
    skip_invalid: bool = False,
) -> list[MXeneEntry]:
    """Build and cross-validate entries for every CONTCAR under `root`.

    CONTCARs in sub-folders of an entry folder (auxiliary calculations such
    as supercells or phonons) are skipped.

    By default any invalid or duplicate structure raises, so nothing is
    uploaded until the whole dataset is clean. With `skip_invalid=True`, the
    structures that `check_dataset` reports as failed are left out and the
    rest are returned (use this to upload the good part of a dataset while
    problems are being resolved).

    Always raises if the spreadsheet lists an `mxeneId` with no matching
    valid structure, so property values are never silently dropped.
    """
    properties = dict(properties or {})
    if skip_invalid:
        found = check_dataset(root).entries
    else:
        found, seen = [], set()
        for path in iter_structure_files(root):
            if is_auxiliary(path, Path(root)):
                continue
            entry = entry_from_file(path)
            if entry.mxeneId in seen:
                raise ValueError(f"Duplicate mxeneId {entry.mxeneId!r} at {path}")
            seen.add(entry.mxeneId)
            found.append(entry)

    for entry in found:
        entry.properties = properties.pop(entry.mxeneId, None)
    if properties:
        raise ValueError(
            f"No valid structure found for spreadsheet rows {sorted(properties)}"
        )

    add_relative_stacking_energies(found)
    return [MXeneEntry.model_validate(e.model_dump()) for e in found]


@dataclass
class CheckRecord:
    """Outcome of checking one CONTCAR."""

    path: Path
    status: str  # "valid", "failed" or "skipped"
    message: str = ""
    formula: str = ""
    folderLabel: str = ""
    n: int | None = None
    metal: str = ""
    nonmetal: str = ""
    termination: str = ""
    cellId: str = ""  # the structure this file claims to be, e.g. `Hf2CF2-t-1`
    measuredCoordination: str = ""
    entry: MXeneEntry | None = field(default=None, repr=False)


@dataclass
class CheckResult:
    """All records from `check_dataset`, with convenience views."""

    records: list[CheckRecord]

    @property
    def entries(self) -> list[MXeneEntry]:
        return [r.entry for r in self.records if r.status == "valid"]

    @property
    def failures(self) -> list[CheckRecord]:
        return [r for r in self.records if r.status == "failed"]

    @property
    def skipped(self) -> list[CheckRecord]:
        return [r for r in self.records if r.status == "skipped"]


def _is_label(name: str) -> bool:
    try:
        MXeneLabel.parse_folder_label(name)
    except ValueError:
        return False
    return True


def is_auxiliary(path: Path, root: Path) -> bool:
    """True if a CONTCAR sits in a sub-folder of an entry folder.

    Such files (e.g. `h1a/super331/phonon/CONTCAR`) belong to follow-up
    calculations on an entry, not to new entries, and are skipped.
    """
    parents = path.parent.relative_to(root).parts
    if not parents:
        return False
    return not _is_label(parents[-1]) and any(_is_label(p) for p in parents[:-1])


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        msgs = [e["msg"].removeprefix("Value error, ") for e in exc.errors()]
        return "; ".join(msgs)
    return f"{type(exc).__name__}: {exc}"


def check_dataset(root: str | Path) -> CheckResult:
    """Validate every CONTCAR under `root`, collecting all failures.

    Unlike `build_entries`, this does not stop at the first problem. Each
    record keeps the coordination sequence measured from the structure, even
    when validation fails, so mismatches can be diagnosed.
    """
    root = Path(root)
    records: list[CheckRecord] = []
    for path in iter_structure_files(root):
        rec = CheckRecord(path=path, status="failed", folderLabel=path.parent.name)
        records.append(rec)
        if is_auxiliary(path, root):
            rec.status = "skipped"
            rec.message = "inside an entry folder (auxiliary calculation)"
            continue
        try:
            structure = Structure.from_file(path)
            rec.formula = plain_formula(structure.composition)
            chem = infer_chemistry(structure.composition)
            rec.metal, rec.nonmetal, rec.n = chem["metal"], chem["nonmetal"], chem["n"]
            rec.termination = chem["termination"] or ""
            stacking, site = MXeneLabel.parse_folder_label(path.parent.name)
            rec.cellId = f"{_cell_formula(chem)}-{path.parent.name.lower()}"
            desc = StructureDescriptors.from_structure(structure)
            rec.measuredCoordination = "-".join(desc.coordinationSequence)
            entry = MXeneEntry.from_structure(
                structure, stacking=stacking, terminationSite=site
            )
        except (ValueError, KeyError, IndexError, OSError) as exc:
            rec.message = _short_error(exc)
            continue
        rec.status, rec.entry = "valid", entry

    # Several files claiming the same structure: none can be trusted, so all
    # of them are marked failed and point at each other.
    claims: dict[str, list[CheckRecord]] = defaultdict(list)
    for rec in records:
        if rec.cellId and rec.status != "skipped":
            claims[rec.cellId].append(rec)
    for cell, group in claims.items():
        if len(group) < 2:
            continue
        for rec in group:
            others = ", ".join(str(o.path) for o in group if o is not rec)
            note = f"Duplicate {cell!r}: also claimed by {others}"
            rec.message = f"{rec.message}; {note}" if rec.message else note
            rec.status, rec.entry = "failed", None
    return CheckResult(records)


def _cell_formula(chem: dict) -> str:
    return MXeneLabel(
        **chem, stacking="t", terminationSite=1 if chem["termination"] else None
    ).formula


def termination_site_table(result: CheckResult) -> dict[tuple, Counter]:
    """Measured outer-metal coordination for each (n, stacking, site) label.

    Includes failed records, so a systematic label convention mismatch shows
    up as a whole row with the opposite coordination.
    """
    table: dict[tuple, Counter] = defaultdict(Counter)
    for rec in result.records:
        if rec.status == "skipped" or not rec.measuredCoordination:
            continue
        try:
            stacking, site = MXeneLabel.parse_folder_label(rec.folderLabel)
        except ValueError:
            continue
        seq = rec.measuredCoordination.split("-")
        if site is None or len(seq) < 3:
            continue
        n = (len(seq) - 1) // 2  # terminated: 2n + 1 interior layers
        table[(n, stacking, site)][f"{seq[0]},{seq[-1]}"] += 1
    return dict(table)


def write_report(result: CheckResult, path: str | Path, root: str | Path) -> None:
    """Write one CSV row per CONTCAR with its label, measurement and outcome."""
    rows = [
        {
            "path": str(r.path.relative_to(root)),
            "status": r.status,
            "formula": r.formula,
            "folderLabel": r.folderLabel,
            "measuredCoordination": r.measuredCoordination,
            "mxeneId": r.entry.mxeneId if r.entry else "",
            "message": r.message,
        }
        for r in result.records
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def main(argv: list[str] | None = None) -> int:
    """Check a dataset from the command line and print a summary.

    Usage: ``python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions MXENE_DATA [--report report.csv] [--overview overview.xlsx] [--template properties.csv]``
    """
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    parser.add_argument("root", help="Path to the MXENE_DATA folder")
    parser.add_argument("--report", help="Write a per-structure CSV report here")
    parser.add_argument(
        "--overview", help="Write an Excel overview grid of the dataset here"
    )
    parser.add_argument(
        "--template",
        help="Write (or refresh) a properties CSV for every valid structure here",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)

    result = check_dataset(root)
    print(
        f"{len(result.entries)} structures valid, {len(result.failures)} failed, "
        f"{len(result.skipped)} skipped (auxiliary calculations)\n"
    )

    counts: dict[tuple, int] = defaultdict(int)
    for e in result.entries:
        lab = e.labels
        counts[(lab.metal, lab.nonmetal, lab.termination or "-", lab.n)] += 1
    if counts:
        print(f"{'M':<4}{'X':<4}{'T':<4}{'n':<4}count")
        for (m, x, t, n), count in sorted(counts.items()):
            print(f"{m:<4}{x:<4}{t:<4}{n:<4}{count}")
        print()

    table = termination_site_table(result)
    if table:
        print("Measured outer-metal coordination by label (all terminated structures):")
        print(f"{'n':<4}{'label':<9}measured (bottom,top): count")
        for (n, stacking, site), counter in sorted(table.items()):
            found = ", ".join(f"{k}: {v}" for k, v in sorted(counter.items()))
            print(f"{n:<4}{stacking + '-' + str(site):<9}{found}")
        print()

    for rec in result.failures:
        print(f"FAILED {rec.path.relative_to(root)}\n    {rec.message}")

    if args.report:
        write_report(result, args.report, root)
        print(f"\nReport written to {args.report}")
    if args.overview:
        from mpcontribs.lux.projects.two_d_mxenes.pipelines.dataset_overview import (
            write_overview,
        )

        write_overview(result, args.overview, root)
        print(f"Overview written to {args.overview}")
    if args.template:
        files = {
            r.entry.mxeneId: str(r.path.relative_to(root))
            for r in result.records
            if r.status == "valid"
        }
        counts = write_properties_template(result.entries, args.template, files)
        print(
            f"Properties template written to {args.template}: {counts['rows']} "
            f"structures, values kept for {counts['kept']}"
        )
        if counts["orphaned"]:
            print(
                f"  {counts['orphaned']} filled rows no longer match a valid "
                f"structure; moved to {Path(args.template).with_suffix('.orphaned.csv')}"
            )
    return 1 if result.failures else 0


def add_relative_stacking_energies(entries: list[MXeneEntry]) -> None:
    """Fill `relativeStackingEnergy` (meV/atom) within each composition."""
    groups: dict[str, list[MXeneEntry]] = defaultdict(list)
    for entry in entries:
        energetics = entry.properties and entry.properties.energetics
        if energetics and energetics.totalEnergyPerAtom is not None:
            groups[entry.labels.formula].append(entry)
    for group in groups.values():
        e_min = min(e.properties.energetics.totalEnergyPerAtom for e in group)
        for entry in group:
            energetics = entry.properties.energetics
            energetics.relativeStackingEnergy = 1000.0 * (
                energetics.totalEnergyPerAtom - e_min
            )


MPCONTRIBS_COLUMNS: dict[str, str | None] = {
    "mxeneId": None,
    "M": None,
    "X": None,
    "T": None,
    "n": "",
    "stacking": None,
    "terminationSite": None,
    "coordination": None,
    "geometry.a": "Å",
    "geometry.thickness": "Å",
    "geometry.MX": "Å",
    "geometry.MT": "Å",
    "geometry.spaceGroup": None,
    "energy.formation": "eV/atom",
    "energy.relativeStacking": "meV/atom",
    "elastic.C11": "N/m",
    "elastic.C12": "N/m",
    "elastic.C66": "N/m",
    "elastic.Y": "N/m",
    "elastic.nu": "",
    "elastic.stable": None,
}
"""MPContribs `data` columns and units, for `Client.init_columns`.

`None` marks text columns and `""` dimensionless numbers, following the
MPContribs client. Keep this in sync with `to_contribution`.
"""

MPCONTRIBS_COLUMN_DESCRIPTIONS: dict[str, str] = {
    "mxeneId": "Unique ID in this project: formula plus dataset label, e.g. Ti3C2O2-h1a-2",
    "M": "Transition metal M",
    "X": "Non-metal X (C or N)",
    "T": "Surface termination T, or none for pristine sheets",
    "n": "Thickness index n in M(n+1)X(n)T(x)",
    "stacking": "Stacking label of the M/X layers (t, h, h1a, h1b, h2)",
    "terminationSite": "Termination site label (1, 2, or none)",
    "coordination": "Measured O/P coordination of each interior layer, bottom to top",
    "geometry.a": "In-plane lattice constant a, in Å",
    "geometry.thickness": "Distance between the outermost atomic planes, in Å",
    "geometry.MX": "Mean nearest-neighbour M-X distance, in Å",
    "geometry.MT": "Mean nearest-neighbour M-T distance, in Å",
    "geometry.spaceGroup": "Space group of the periodic slab model",
    "energy.formation": "Formation energy per atom, in eV/atom",
    "energy.relativeStacking": "Energy above the most stable stacking of the same composition, in meV/atom",
    "elastic.C11": "2D elastic constant C11, in N/m",
    "elastic.C12": "2D elastic constant C12, in N/m",
    "elastic.C66": "2D elastic constant C66, in N/m",
    "elastic.Y": "In-plane 2D Young's modulus, in N/m",
    "elastic.nu": "In-plane Poisson's ratio",
    "elastic.stable": "Born mechanical stability of the hexagonal sheet (True/False)",
}
"""Column descriptions, for `Client.update_project({"other": ...})`."""


def project_other(settings: CalculationSettings | None = None) -> dict:
    """The project's `other` metadata: column descriptions and DFT settings.

    For `Client.update_project({"other": project_other(settings)})`. The
    MPContribs API rejects keys containing punctuation (including `.`), so
    dotted column names are nested (`geometry.a` -> `{"geometry": {"a": ...}}`)
    and list-valued settings are joined into strings.
    """
    other: dict = {}
    for column, text in MPCONTRIBS_COLUMN_DESCRIPTIONS.items():
        node = other
        *parents, leaf = column.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = text
    if settings is not None:
        calc = {}
        for key, value in settings.model_dump(exclude_none=True).items():
            if isinstance(value, list):
                sep = "x" if key == "kpointMesh" else ", "
                value = sep.join(str(v) for v in value)
            calc[key] = value
        if calc:
            other["calculation"] = calc
    return other


def to_contribution(entry: MXeneEntry, project: str = "two_d_mxenes") -> dict:
    """Convert an entry into an MPContribs contribution dictionary.

    Only searchable quantities go into `data` (see `MPCONTRIBS_COLUMNS`; MP
    asks for at most 50 flattened keys). Values carry units as strings, as
    MPContribs expects. The relaxed structure goes in `structures`.

    The contribution `identifier` is the `mxeneId`, not the formula: several
    structures share a formula (e.g. `Hf2CF2-h-1` and `Hf2CF2-t-2`), and
    MPContribs projects accept one contribution per identifier by default
    (`unique_identifiers=True`), silently skipping the rest. The formula is
    still given in `formula`.
    """
    lab, desc = entry.labels, entry.descriptors
    geometry = {
        "a": _with_unit(desc.a, "Å", 4),
        "thickness": _with_unit(desc.thickness, "Å", 4),
        "MX": _with_unit(desc.metalNonmetalBondLength, "Å", 4),
        "MT": _with_unit(desc.metalTerminationBondLength, "Å", 4),
        "spaceGroup": desc.spaceGroupSymbol,
    }
    data: dict = {
        "mxeneId": entry.mxeneId,
        "M": lab.metal,
        "X": lab.nonmetal,
        "T": lab.termination or "none",
        "n": lab.n,
        "stacking": lab.stacking,
        "terminationSite": str(lab.terminationSite or "none"),
        "coordination": "-".join(desc.coordinationSequence),
        "geometry": {k: v for k, v in geometry.items() if v is not None},
    }

    props = entry.properties
    if props and props.energetics:
        en = props.energetics
        energy = {
            "formation": _with_unit(en.formationEnergyPerAtom, "eV/atom"),
            "relativeStacking": _with_unit(en.relativeStackingEnergy, "meV/atom"),
        }
        if energy := {k: v for k, v in energy.items() if v is not None}:
            data["energy"] = energy
    if props and props.elastic:
        el = props.elastic
        elastic = {
            "C11": _with_unit(el.c11, "N/m"),
            "C12": _with_unit(el.c12, "N/m"),
            "C66": _with_unit(el.c66, "N/m"),
            "Y": _with_unit(el.youngsModulus, "N/m"),
            "nu": _with_unit(el.poissonRatio, ""),
            "stable": (
                None if el.mechanicallyStable is None else str(el.mechanicallyStable)
            ),
        }
        if elastic := {k: v for k, v in elastic.items() if v is not None}:
            data["elastic"] = elastic

    return {
        "project": project,
        "identifier": entry.mxeneId,
        "formula": desc.reducedFormula,
        "data": data,
        "structures": [entry.structure.pymatgen_structure],
    }


def write_parquet(entries: list[MXeneEntry], path: str | Path) -> None:
    """Write full records (structures, descriptors, properties) to Parquet.

    The Arrow schema is derived from `MXeneEntry` with emmet's `arrowize`,
    the same check the MPContribs-lux test suite runs on every model.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from emmet.core.arrow import arrowize

    schema = pa.schema(list(arrowize(MXeneEntry)))
    table = pa.Table.from_pylist([e.model_dump() for e in entries], schema=schema)
    pq.write_table(table, path)


def read_parquet(path: str | Path) -> list[MXeneEntry]:
    """Read records written by `write_parquet`, re-validating each one."""
    import pyarrow.parquet as pq

    return [MXeneEntry.model_validate(row) for row in pq.read_table(path).to_pylist()]


def _with_unit(
    value: float | None, unit: str, decimals: int | None = None
) -> str | None:
    if value is None:
        return None
    number = f"{value:.{decimals}f}" if decimals is not None else f"{value:.6g}"
    return f"{number} {unit}".strip()


if __name__ == "__main__":
    raise SystemExit(main())
