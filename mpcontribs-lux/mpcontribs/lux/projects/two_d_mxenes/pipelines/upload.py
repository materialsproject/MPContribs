"""MPContribs upload: contribution format, project metadata and Parquet export.

- `MPCONTRIBS_COLUMNS` and `MPCONTRIBS_COLUMN_DESCRIPTIONS` are generated
  from the `MXeneEntry` schema (field paths, units and descriptions), so the
  submitted data and the schema cannot diverge.
- `to_contribution` turns an entry and its relaxed structure into an
  MPContribs contribution: the entry is the `data`, the structure goes in
  `structures`.
- `CalculationSettings` holds the DFT settings, which are identical for all
  structures and are stored once in the project's `other` metadata via
  `project_other`.
- `write_parquet` / `read_parquet` store the entries, and optionally their
  structures, as a Parquet file.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import UnionType
from typing import Literal, Union, get_args, get_origin

from emmet.core.vasp.calc_types import RunType
from mpcontribs.lux.projects.two_d_mxenes.schemas import MXeneEntry
from mpcontribs.lux.projects.two_d_mxenes.schemas.descriptors import UNIT
from pydantic import BaseModel, ConfigDict, Field
from pymatgen.core import Structure

PROJECT = "two_d_mxenes"
"""Name of the MPContribs project."""

MAX_COLUMNS = 50
"""Maximum number of flattened `data` keys recommended by MPContribs."""

VdwCorrection = Literal[
    "none", "DFT-D2", "DFT-D3", "DFT-D3(BJ)", "DFT-D4", "TS", "TS-SCS", "MBD", "dDsC"
]
"""Dispersion corrections available in VASP (`IVDW` settings)."""

PotcarSet = Literal[
    "PBE", "PBE_52", "PBE_54", "PBE_64", "LDA", "LDA_52", "LDA_54", "LDA_64"
]
"""VASP POTCAR sets."""

ElasticMethod = Literal["stress-strain", "energy-strain"]
"""Methods for computing elastic constants from finite strains."""

POTCAR_SYMBOLS_PATTERN = (
    r"^[A-Z][a-z]?(?:_[A-Za-z0-9]{1,4})?(?:, [A-Z][a-z]?(?:_[A-Za-z0-9]{1,4})?){0,9}$"
)
"""Comma-separated POTCAR symbols, e.g. `Ti_sv, C, O`."""


class CalculationSettings(BaseModel):
    """DFT settings used to relax the structures and compute their properties.

    The settings are identical for every structure in the project, so they are
    stored once in the project's `other` metadata (see `project_other`), not
    in each contribution.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    code: Literal["VASP"] = Field(
        "VASP", description="Simulation code. The pipeline reads VASP output."
    )
    codeVersion: str | None = Field(
        None,
        max_length=16,
        pattern=r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2}){0,2}$",
        description="Version of the simulation code, e.g. `6.4.2`.",
    )
    functional: RunType | None = Field(
        None,
        description="Exchange-correlation functional (emmet `RunType`), e.g. `PBE`.",
    )
    vdwCorrection: VdwCorrection | None = Field(
        None,
        description="Dispersion correction (VASP `IVDW`), or `none`.",
    )
    potcarSet: PotcarSet | None = Field(
        None, description="VASP POTCAR set, e.g. `PBE_54`."
    )
    potcarSymbols: str | None = Field(
        None,
        max_length=80,
        pattern=POTCAR_SYMBOLS_PATTERN,
        description="POTCAR symbols used, comma-separated, e.g. `Ti_sv, C, O`.",
    )
    energyCutoff: float | None = Field(
        None,
        gt=0,
        le=3000,
        description="Plane-wave kinetic energy cutoff (`ENCUT`), in eV.",
    )
    kpointsA: int | None = Field(
        None, ge=1, le=100, description="k-points along a for relaxations."
    )
    kpointsB: int | None = Field(
        None, ge=1, le=100, description="k-points along b for relaxations."
    )
    kpointsC: int | None = Field(
        None, ge=1, le=100, description="k-points along c for relaxations."
    )
    spinPolarized: bool | None = Field(
        None, description="Whether calculations were spin-polarized."
    )
    electronicConvergence: float | None = Field(
        None,
        gt=0,
        le=1e-2,
        description="Electronic (SCF) energy convergence (`EDIFF`), in eV.",
    )
    forceConvergence: float | None = Field(
        None,
        gt=0,
        le=1,
        description="Maximum residual force on any atom after relaxation, in eV/Å.",
    )
    elasticMethod: ElasticMethod | None = Field(
        None,
        description="How the elastic constants were computed: from stresses "
        "(`stress-strain`) or from the curvature of the energy (`energy-strain`) "
        "under applied strains.",
    )
    maxStrain: float | None = Field(
        None,
        gt=0,
        le=10,
        description="Largest applied strain magnitude for the elastic constants, in %.",
    )
    nStrainPoints: int | None = Field(
        None,
        ge=2,
        le=50,
        description="Number of strain values per deformation mode.",
    )


def _unwrap_model(annotation) -> type[BaseModel] | None:
    """Return the model class in `Model` or `Model | None`, else None."""
    if get_origin(annotation) in (Union, UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        annotation = args[0] if len(args) == 1 else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _iter_fields(model: type[BaseModel], prefix: str = "") -> Iterator[tuple]:
    """Yield (dotted path, unit, description) for every leaf field of a model."""
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        nested = _unwrap_model(info.annotation)
        if nested is not None:
            yield from _iter_fields(nested, f"{path}.")
        else:
            extra = info.json_schema_extra or {}
            yield path, extra.get(UNIT), info.description or ""


MPCONTRIBS_COLUMNS: dict[str, str | None] = {
    path: unit for path, unit, _ in _iter_fields(MXeneEntry)
}
"""MPContribs `data` columns and units, for `Client.init_columns`.

Generated from `MXeneEntry`: `None` marks text columns and `""` dimensionless
numbers, as the MPContribs client specifies.
"""

MPCONTRIBS_COLUMN_DESCRIPTIONS: dict[str, str] = {
    path: description for path, _, description in _iter_fields(MXeneEntry)
}
"""Column descriptions generated from the `MXeneEntry` field descriptions."""


def to_contribution(
    entry: MXeneEntry, structure: Structure, project: str = PROJECT
) -> dict:
    """Convert an entry and its relaxed structure into an MPContribs contribution.

    The entry is the contribution `data`: numbers are written as strings with
    their units, as MPContribs expects, and unset values are omitted. The
    structure is the single element of `structures`. The `identifier` is the
    `mxeneId`, which is unique, so every structure is kept under the default
    `unique_identifiers=True`; the formula is given in `formula`.

    Args:
        entry: The validated entry.
        structure: The relaxed structure the entry was computed from.
        project: Name of the MPContribs project.

    Returns:
        A contribution dictionary for `Client.submit_contributions`.
    """
    return {
        "project": project,
        "identifier": entry.mxeneId,
        "formula": entry.descriptors.reducedFormula,
        "data": _format_data(entry.model_dump(exclude_none=True)),
        "structures": [structure],
    }


def project_other(settings: CalculationSettings | None = None) -> dict:
    """The project's `other` metadata: column descriptions and DFT settings.

    For `Client.update_project({"other": project_other(settings)})`. The
    MPContribs API rejects keys containing punctuation (including `.`), so
    the column descriptions are nested by field path
    (`descriptors.a` -> `{"descriptors": {"a": ...}}`).

    Args:
        settings: DFT settings of the project, if known.

    Returns:
        The nested metadata dictionary.
    """
    other: dict = {}
    for column, text in MPCONTRIBS_COLUMN_DESCRIPTIONS.items():
        node = other
        *parents, leaf = column.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = text
    if settings is not None:
        calc = settings.model_dump(mode="json", exclude_none=True)
        if calc:
            other["calculation"] = calc
    return other


def write_parquet(
    entries: Sequence[MXeneEntry],
    path: str | Path,
    structures: Sequence[Structure] | None = None,
) -> None:
    """Write entries, and optionally their structures, to a Parquet file.

    The columns follow the `MXeneEntry` schema, converted with emmet's
    `arrowize` (the check the MPContribs-lux test suite runs on every model).
    If `structures` are given, a `structure` column holds each structure as
    pymatgen JSON.

    Args:
        entries: Validated entries.
        path: Output file.
        structures: Relaxed structures in the same order as `entries`.

    Raises:
        ValueError: If `structures` and `entries` differ in length.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from emmet.core.arrow import arrowize

    fields = list(arrowize(MXeneEntry))
    rows = [e.model_dump() for e in entries]
    if structures is not None:
        if len(structures) != len(entries):
            raise ValueError("structures and entries must have the same length")
        fields.append(pa.field("structure", pa.string()))
        for row, structure in zip(rows, structures):
            row["structure"] = structure.to_json()
    table = pa.Table.from_pylist(rows, schema=pa.schema(fields))
    pq.write_table(table, path)


def read_parquet(
    path: str | Path,
) -> tuple[list[MXeneEntry], list[Structure] | None]:
    """Read a file written by `write_parquet`, re-validating every entry.

    Args:
        path: Parquet file.

    Returns:
        The entries, and the structures if the file contains them (else None).
    """
    import pyarrow.parquet as pq

    rows = pq.read_table(path).to_pylist()
    has_structures = bool(rows) and "structure" in rows[0]
    structures = (
        [Structure.from_dict(json.loads(row.pop("structure"))) for row in rows]
        if has_structures
        else None
    )
    return [MXeneEntry.model_validate(row) for row in rows], structures


def _format_data(data: dict, prefix: str = "") -> dict:
    """Write numbers as strings with units, following `MPCONTRIBS_COLUMNS`."""
    out = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out[key] = _format_data(value, f"{path}.")
            continue
        unit = MPCONTRIBS_COLUMNS[path]
        if isinstance(value, bool):
            out[key] = "Yes" if value else "No"
        elif unit is None:
            out[key] = str(value)
        elif isinstance(value, int):
            out[key] = f"{value} {unit}".strip()
        else:
            out[key] = f"{value:.6g} {unit}".strip()
    return out
