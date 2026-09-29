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

from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from mpcontribs.lux.projects.two_d_mxenes.schemas import (
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
"""Expected spreadsheet columns and their units (see the project README)."""


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
    """Read the properties spreadsheet (xlsx or csv) keyed by `mxeneId`."""
    path = Path(path)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_excel(path)
    missing = {"mxeneId"} - set(df.columns)
    if missing:
        raise ValueError(f"Spreadsheet is missing required columns {missing}")
    unknown = set(df.columns) - set(SPREADSHEET_COLUMNS)
    if unknown:
        raise ValueError(f"Spreadsheet has unrecognized columns {sorted(unknown)}")
    if df["mxeneId"].duplicated().any():
        dupes = df.loc[df["mxeneId"].duplicated(), "mxeneId"].tolist()
        raise ValueError(f"Duplicate mxeneId values: {dupes}")

    df = df.astype(object).where(pd.notna(df), None)
    out: dict[str, MXeneProperties] = {}
    for row in df.to_dict(orient="records"):
        c11, c12, c66 = row.get("c11"), row.get("c12"), row.get("c66")
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


def build_entries(
    root: str | Path, properties: Mapping[str, MXeneProperties] | None = None
) -> list[MXeneEntry]:
    """Build and cross-validate entries for every CONTCAR under `root`.

    CONTCARs in sub-folders of an entry folder (auxiliary calculations such
    as supercells or phonons) are skipped. Raises if two structures map to
    the same `mxeneId`, or if the spreadsheet lists an `mxeneId` with no
    matching structure.
    """
    properties = dict(properties or {})
    entries: dict[str, MXeneEntry] = {}
    for path in iter_structure_files(root):
        if is_auxiliary(path, Path(root)):
            continue
        entry = entry_from_file(path)
        if entry.mxeneId in entries:
            raise ValueError(f"Duplicate mxeneId {entry.mxeneId!r} at {path}")
        entry.properties = properties.pop(entry.mxeneId, None)
        entries[entry.mxeneId] = entry
    if properties:
        raise ValueError(
            f"No structure found for spreadsheet rows {sorted(properties)}"
        )

    result = list(entries.values())
    add_relative_stacking_energies(result)
    return [MXeneEntry.model_validate(e.model_dump()) for e in result]


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

    Usage: ``python -m mpcontribs.lux.projects.two_d_mxenes.pipelines.build_contributions MXENE_DATA [--report report.csv] [--overview overview.xlsx]``
    """
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    parser.add_argument("root", help="Path to the MXENE_DATA folder")
    parser.add_argument("--report", help="Write a per-structure CSV report here")
    parser.add_argument(
        "--overview", help="Write an Excel overview grid of the dataset here"
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


def to_contribution(entry: MXeneEntry, project: str = "two_d_mxenes") -> dict:
    """Convert an entry into an MPContribs contribution dictionary.

    Only searchable quantities go into `data` (MPContribs allows at most 50
    flattened keys); values carry units as strings, as MPContribs expects.
    The full record, including arrays, lives in the project's Parquet file.
    """
    lab, desc = entry.labels, entry.descriptors
    data: dict = {
        "mxeneId": entry.mxeneId,
        "M": lab.metal,
        "X": lab.nonmetal,
        "T": lab.termination or "none",
        "n": lab.n,
        "stacking": lab.stacking,
        "terminationSite": lab.terminationSite or "none",
        "coordination": "-".join(desc.coordinationSequence),
        "structure": {
            "a": f"{desc.a:.4f} Å",
            "thickness": f"{desc.thickness:.4f} Å",
            "MX": f"{desc.metalNonmetalBondLength:.4f} Å",
            "spaceGroup": desc.spaceGroupSymbol,
        },
    }
    if desc.metalTerminationBondLength is not None:
        data["structure"]["MT"] = f"{desc.metalTerminationBondLength:.4f} Å"

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
        "identifier": entry.descriptors.reducedFormula,
        "data": data,
        "structures": [entry.structure.pymatgen_structure],
    }


def _with_unit(value: float | None, unit: str) -> str | None:
    if value is None:
        return None
    return f"{value:.6g} {unit}".strip()


if __name__ == "__main__":
    raise SystemExit(main())
