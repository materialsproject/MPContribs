"""Shared types and identity validation for CoRE MOF schemas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field


StructureVariant = Literal["ASR", "FSR", "ION"]
SourceDatabase = Literal["COD", "CSD", "SI"]
StructureId = Annotated[
    str,
    Field(
        pattern=r"^(ASR|FSR|ION)-(COD|CSD|SI)-(?:\d{4}|UNKN)-\d{4}$",
        description="Release-preserved canonical structure identifier.",
    ),
]
PublicationYear = Annotated[
    int,
    Field(ge=1800, le=2100, description="Publication year encoded by the source."),
]
PositiveSize = Annotated[
    int,
    Field(gt=0, description="File size in bytes."),
]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]


def _parse_dimension(value: object) -> object:
    """Coerce integer CSV cells while retaining a bounded JSON integer type."""

    if isinstance(value, str) and value in {"0", "1", "2", "3"}:
        return int(value)
    return value


Dimension = Annotated[Literal[0, 1, 2, 3], BeforeValidator(_parse_dimension)]


MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


@dataclass(frozen=True)
class ParsedStructureId:
    variant: StructureVariant
    source: SourceDatabase
    publication_year: int | None
    bucket_index: int


_STRUCTURE_ID_RE = re.compile(
    r"^(?P<variant>ASR|FSR|ION)-(?P<source>COD|CSD|SI)-"
    r"(?P<year>\d{4}|UNKN)-(?P<bucket>\d{4})$"
)


def parse_structure_id(structure_id: str) -> ParsedStructureId:
    """Parse a canonical release identifier into its encoded components."""

    match = _STRUCTURE_ID_RE.fullmatch(structure_id)
    if match is None:
        raise ValueError(f"Invalid structure_id: {structure_id!r}")
    year = match.group("year")
    return ParsedStructureId(
        variant=match.group("variant"),  # type: ignore[arg-type]
        source=match.group("source"),  # type: ignore[arg-type]
        publication_year=None if year == "UNKN" else int(year),
        bucket_index=int(match.group("bucket")),
    )


def validate_identity(
    structure_id: str,
    *,
    cif_file: str | None = None,
    source_database: SourceDatabase | None = None,
    structure_variant: StructureVariant | None = None,
    publication_year: int | None = None,
    bucket_index: int | None = None,
    check_year: bool = False,
) -> None:
    """Validate redundant identity fields against the canonical identifier."""

    parsed = parse_structure_id(structure_id)
    if cif_file is not None and cif_file != f"cifs/{structure_id}.cif":
        raise ValueError("cif_file must equal cifs/{structure_id}.cif")
    if source_database is not None and source_database != parsed.source:
        raise ValueError("source_database does not match structure_id")
    if structure_variant is not None and structure_variant != parsed.variant:
        raise ValueError("structure_variant does not match structure_id")
    if check_year and publication_year != parsed.publication_year:
        raise ValueError("publication_year does not match structure_id")
    if bucket_index is not None and bucket_index != parsed.bucket_index:
        raise ValueError("bucket_index does not match structure_id")
