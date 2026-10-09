"""Discover, check and build MXene records from a tree of VASP CONTCAR files.

Check every structure from the command line (all failures are reported)::

    python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions DATA_ROOT

Build records and contributions from Python::

    from mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions import (
        build_records, load_properties,
    )
    from mpcontribs.lux.projects.two_d_mxenes.pipelines.upload import to_contribution

    records = build_records("DATA_ROOT", properties=load_properties("properties.csv"))
    contributions = [to_contribution(r.entry, r.structure) for r in records]

Labels are assigned independently of how the folders above the label folder
are named or nested: M, X, T and n come from the composition of each CONTCAR
(`structure_analysis.infer_chemistry`); the stacking label and termination
site come from the name of the folder that directly contains it (e.g. `h1a-2`).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from mpcontribs.lux.projects.two_d_mxenes.pipelines.structure_analysis import (
    compute_descriptors,
    entry_from_structure,
    infer_chemistry,
    plain_formula,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas import (
    ElasticProperties,
    Energetics,
    MXeneEntry,
    MXeneLabel,
    MXeneProperties,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import parse_folder_label
from pydantic import ValidationError
from pymatgen.core import Element, Structure

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
property, add the field to `schemas/properties.py`, the column here, and its
mapping in `load_properties`. The MPContribs columns are generated from the
schema and need no change.
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

`load_properties` ignores them; structural values are always recomputed.
"""

_HEADER = re.compile(r"^\s*(?P<name>[A-Za-z0-9]+)\s*(?:\[(?P<unit>[^\]]*)\])?\s*$")
_TERM_ORDER = {None: 0, "F": 1, "O": 2}


@dataclass(frozen=True)
class MXeneRecord:
    """A validated entry, the relaxed structure it was computed from, and its file."""

    entry: MXeneEntry
    structure: Structure
    path: Path | None = None


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
    record: MXeneRecord | None = None

    @property
    def entry(self) -> MXeneEntry | None:
        """The validated entry, for valid files."""
        return self.record.entry if self.record else None


@dataclass
class CheckResult:
    """All records from `check_dataset`, with convenience views."""

    records: list[CheckRecord]

    @property
    def valid(self) -> list[MXeneRecord]:
        """Entries with their structures, for files that passed every check."""
        return [r.record for r in self.records if r.status == "valid"]

    @property
    def entries(self) -> list[MXeneEntry]:
        """Entries of the files that passed every check."""
        return [r.entry for r in self.valid]

    @property
    def failures(self) -> list[CheckRecord]:
        """Files that failed a check."""
        return [r for r in self.records if r.status == "failed"]

    @property
    def skipped(self) -> list[CheckRecord]:
        """Auxiliary files inside entry folders."""
        return [r for r in self.records if r.status == "skipped"]


def iter_structure_files(root: str | Path) -> Iterator[Path]:
    """Yield every CONTCAR below `root`, in sorted order.

    Args:
        root: Root folder of the CONTCAR tree.

    Yields:
        Paths to CONTCAR files.
    """
    yield from sorted(Path(root).rglob(STRUCTURE_FILENAME))


def is_auxiliary(path: Path, root: Path) -> bool:
    """Whether a CONTCAR sits in a sub-folder of an entry (label) folder.

    Such files (e.g. `h1a/supercell/phonon/CONTCAR`) belong to follow-up
    calculations on an entry and are skipped.

    Args:
        path: Path to the CONTCAR.
        root: Root folder of the CONTCAR tree.

    Returns:
        True if the file is an auxiliary calculation.
    """
    parents = path.parent.relative_to(root).parts
    if not parents:
        return False
    return not _is_label(parents[-1]) and any(_is_label(p) for p in parents[:-1])


def record_from_file(
    path: str | Path, properties: MXeneProperties | None = None
) -> MXeneRecord:
    """Build one validated record from a CONTCAR and the label of its folder.

    Args:
        path: Path to the CONTCAR.
        properties: Computed properties for this structure, if any.

    Returns:
        The record.

    Raises:
        ValueError: If the file cannot be read, the folder is not a label, or
            the structure fails validation.
    """
    path = Path(path)
    stacking, site = parse_folder_label(path.parent.name)
    structure = Structure.from_file(path)
    entry = entry_from_structure(
        structure, stacking=stacking, terminationSite=site, properties=properties
    )
    return MXeneRecord(entry=entry, structure=structure, path=path)


def check_dataset(root: str | Path) -> CheckResult:
    """Validate every CONTCAR under `root`, collecting all failures.

    Unlike `build_records`, this does not stop at the first problem. Each
    check record keeps the coordination sequence measured from the structure,
    also when validation fails, so that mismatches can be diagnosed. Files
    that claim the same `mxeneId` are all marked failed.

    Args:
        root: Root folder of the CONTCAR tree.

    Returns:
        One check record per CONTCAR.
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
            stacking, site = parse_folder_label(path.parent.name)
            rec.cellId = f"{_cell_formula(chem)}-{path.parent.name.lower()}"
            rec.measuredCoordination = compute_descriptors(
                structure
            ).coordinationSequence
            entry = entry_from_structure(
                structure, stacking=stacking, terminationSite=site
            )
        except (ValueError, KeyError, IndexError, OSError) as exc:
            rec.message = _short_error(exc)
            continue
        rec.status = "valid"
        rec.record = MXeneRecord(entry=entry, structure=structure, path=path)

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
            rec.status, rec.record = "failed", None
    return CheckResult(records)


def build_records(
    root: str | Path,
    properties: Mapping[str, MXeneProperties] | None = None,
    skip_invalid: bool = False,
) -> list[MXeneRecord]:
    """Build validated records, with properties, for every CONTCAR under `root`.

    Auxiliary calculations inside entry folders are skipped. Relative stacking
    energies are computed from the total energies.

    Args:
        root: Root folder of the CONTCAR tree.
        properties: Properties keyed by `mxeneId` (see `load_properties`).
        skip_invalid: If False (default), the first invalid or duplicate
            structure raises. If True, structures that `check_dataset`
            reports as failed are left out.

    Returns:
        One record per valid structure.

    Raises:
        ValueError: If a structure is invalid or duplicated (unless
            `skip_invalid`), or if a property row has no valid structure.
    """
    properties = dict(properties or {})
    if skip_invalid:
        found = check_dataset(root).valid
    else:
        found, seen = [], set()
        for path in iter_structure_files(root):
            if is_auxiliary(path, Path(root)):
                continue
            record = record_from_file(path)
            if record.entry.mxeneId in seen:
                raise ValueError(
                    f"Duplicate mxeneId {record.entry.mxeneId!r} at {path}"
                )
            seen.add(record.entry.mxeneId)
            found.append(record)

    entries = [r.entry.model_copy(deep=True) for r in found]
    for entry in entries:
        entry.properties = properties.pop(entry.mxeneId, None)
    if properties:
        raise ValueError(
            f"No valid structure found for spreadsheet rows {sorted(properties)}"
        )
    add_relative_stacking_energies(entries)
    return [
        MXeneRecord(
            entry=MXeneEntry.model_validate(entry.model_dump()),
            structure=record.structure,
            path=record.path,
        )
        for entry, record in zip(entries, found)
    ]


def build_entries(
    root: str | Path,
    properties: Mapping[str, MXeneProperties] | None = None,
    skip_invalid: bool = False,
) -> list[MXeneEntry]:
    """Entries of `build_records` (same arguments), without the structures.

    Returns:
        One validated entry per valid structure.
    """
    return [r.entry for r in build_records(root, properties, skip_invalid)]


def add_relative_stacking_energies(entries: list[MXeneEntry]) -> None:
    """Fill `relativeStackingEnergy` (meV/atom) within each composition, in place.

    Args:
        entries: Entries whose properties may contain total energies.
    """
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


def load_properties(path: str | Path) -> dict[str, MXeneProperties]:
    """Read the properties spreadsheet (CSV or XLSX), keyed by `mxeneId`.

    Headers may carry units in brackets, e.g. `c11 [N/m]`, as written by
    `write_properties_template`; a unit different from the expected one is an
    error. Read-only template columns (`TEMPLATE_INFO_COLUMNS`) are ignored.

    Args:
        path: Spreadsheet file.

    Returns:
        Properties per `mxeneId`.

    Raises:
        ValueError: On unknown columns, wrong units, duplicate or missing
            `mxeneId`, incomplete elastic constants or invalid values.
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
        for column in SPREADSHEET_COLUMNS:
            if column != "mxeneId" and row.get(column) is not None:
                row[column] = _number(row[column], row["mxeneId"], column)
        c11, c12, c66 = row.get("c11"), row.get("c12"), row.get("c66")
        if (c11 is None) != (c12 is None) or (c66 is not None and c11 is None):
            raise ValueError(
                f"{row['mxeneId']}: give both c11 and c12 (and optionally c66), "
                "or leave all three blank"
            )
        elastic = (
            ElasticProperties.from_elastic_constants(c11, c12, c66)
            if c11 is not None
            else None
        )
        energetics = Energetics(
            totalEnergyPerAtom=row.get("totalEnergyPerAtom"),
            formationEnergyPerAtom=row.get("formationEnergyPerAtom"),
        )
        out[row["mxeneId"]] = MXeneProperties(energetics=energetics, elastic=elastic)
    return out


def template_rows(
    entries: list[MXeneEntry], files: Mapping[str, str] | None = None
) -> pd.DataFrame:
    """Build the properties template: read-only structure columns, blank properties.

    Args:
        entries: Valid entries, one row each.
        files: Source file per `mxeneId`, for the `file` column.

    Returns:
        The template rows in the order of the overview grid.
    """
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
            "coordinationSequence": desc.coordinationSequence,
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
        row.update({c: None for c in _fill_columns()})
        rows.append(row)
    columns = (
        ["mxeneId"]
        + [_header(k, u) for k, u in TEMPLATE_INFO_COLUMNS.items()]
        + _fill_columns()
    )
    return pd.DataFrame(rows, columns=columns)


def write_properties_template(
    entries: list[MXeneEntry],
    path: str | Path,
    files: Mapping[str, str] | None = None,
) -> dict[str, int]:
    """Write, or refresh, the properties CSV to be filled in.

    If `path` exists, values already entered are kept for every structure
    that is still present. Rows with values whose structure is no longer
    valid are written to `<name>.orphaned.csv` next to it.

    Args:
        entries: Valid entries, one row each.
        path: CSV file to write.
        files: Source file per `mxeneId`, for the `file` column.

    Returns:
        Counts of `rows`, `kept` (rows with values carried over) and `orphaned`.
    """
    path = Path(path)
    new = template_rows(entries, files)
    fill = _fill_columns()
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


def termination_site_table(result: CheckResult) -> dict[tuple, Counter]:
    """Count the measured outer-metal coordination per (n, stacking, site) label.

    Failed files are included, so that a systematic labelling problem shows up
    as a row with the opposite coordination.

    Args:
        result: Output of `check_dataset`.

    Returns:
        `{(n, stacking, site): Counter({"O,O": count, ...})}`.
    """
    table: dict[tuple, Counter] = defaultdict(Counter)
    for rec in result.records:
        if rec.status == "skipped" or not rec.measuredCoordination:
            continue
        try:
            stacking, site = parse_folder_label(rec.folderLabel)
        except ValueError:
            continue
        seq = rec.measuredCoordination.split("-")
        if site is None or len(seq) < 3:
            continue
        n = (len(seq) - 1) // 2  # terminated: 2n + 1 interior layers
        table[(n, stacking, site)][f"{seq[0]},{seq[-1]}"] += 1
    return dict(table)


def write_report(result: CheckResult, path: str | Path, root: str | Path) -> None:
    """Write one CSV row per CONTCAR with its label, measurement and outcome.

    Args:
        result: Output of `check_dataset`.
        path: CSV file to write.
        root: Root folder, for relative paths.
    """
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
    """Check a CONTCAR tree from the command line and print a summary.

    Args:
        argv: Command-line arguments (default: `sys.argv`).

    Returns:
        0 if every structure passed, 1 otherwise.
    """
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    parser.add_argument("root", help="Root folder of the CONTCAR tree")
    parser.add_argument("--report", help="Write a per-structure CSV report here")
    parser.add_argument(
        "--overview", help="Write an Excel overview grid of the structures here"
    )
    parser.add_argument(
        "--out-of-scope",
        action="append",
        default=[],
        metavar="M:T",
        help="Combination with no expected structures, shown grey in the "
        "overview, e.g. Hf:O, Re:none or *:O (repeatable)",
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
            parse_scope_exclusion,
            write_overview,
        )

        try:
            scope = [parse_scope_exclusion(t) for t in args.out_of_scope]
        except ValueError as exc:
            parser.error(str(exc))
        write_overview(result, args.overview, root, out_of_scope=scope)
        print(f"Overview written to {args.overview}")
    if args.template:
        files = {r.entry.mxeneId: str(r.path.relative_to(root)) for r in result.valid}
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


def _is_label(name: str) -> bool:
    try:
        parse_folder_label(name)
    except ValueError:
        return False
    return True


def _cell_formula(chem: dict) -> str:
    return MXeneLabel(
        **chem, stacking="t", terminationSite=1 if chem["termination"] else None
    ).formula


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        msgs = [e["msg"].removeprefix("Value error, ") for e in exc.errors()]
        return "; ".join(msgs)
    return f"{type(exc).__name__}: {exc}"


def _entry_sort_key(entry: MXeneEntry) -> tuple:
    """Order of the overview grid: metal (by Z), X, n, termination, label."""
    lab = entry.labels
    return (
        Element(lab.metal).Z,
        lab.nonmetal,
        lab.n,
        _TERM_ORDER[lab.termination],
        lab.label,
    )


def _number(value, mxene_id: str, column: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{mxene_id}: {column} must be a number or blank, got {value!r}"
        ) from None


def _header(name: str, unit: str) -> str:
    return f"{name} [{unit}]" if unit else name


def _fill_columns() -> list[str]:
    return [_header(k, u) for k, u in SPREADSHEET_COLUMNS.items() if k != "mxeneId"]


def _parse_header(header: str) -> tuple[str, str | None]:
    """Split `c11 [N/m]` into (`c11`, `N/m`); the unit is None if absent."""
    match = _HEADER.match(str(header))
    if match is None:
        raise ValueError(f"Cannot read spreadsheet column header {header!r}")
    return match.group("name"), match.group("unit")


def _read_table(path: Path) -> pd.DataFrame:
    """Read a CSV or Excel sheet; only empty cells count as missing values.

    pandas would otherwise turn placeholders such as `N/A` or `null` into
    blanks silently; here they are kept as text and rejected on validation.
    """
    options = {"dtype": {"mxeneId": str}, "keep_default_na": False, "na_values": [""]}
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig", **options)
    return pd.read_excel(path, **options)


if __name__ == "__main__":
    raise SystemExit(main())
