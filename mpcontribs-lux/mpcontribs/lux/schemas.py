"""Pydantic schemas for this project.

Replace these starter models with project-specific, fully documented schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_serializer
from typing import TYPE_CHECKING, get_args

from emmet.core.types.pymatgen_types.structure_adapter import StructureType

if TYPE_CHECKING:
    from typing_extensions import Self
    from typing import Any

NON_DATA_FIELDS = {
    "identifier",
    "formula",
    "units",
    "aliases",
    "structures",
    "attachments",
}


class AttachmentRecord(BaseModel):
    """Attachment metadata schema (starter)."""

    identifier: str = Field(description="Contribution identifier")
    name: str = Field(description="Attachment logical name")
    mime_type: str | None = Field(default=None, description="Attachment MIME type")


class ContributionRecord(BaseModel):
    """Core contribution row schema (starter)."""

    identifier: str = Field(description="Contribution identifier")
    formula: str | None = Field(None, description="Reduced chemical formula")

    units: dict[str, str] = Field(
        {}, description="mapping of column names to units.", exclude=True
    )
    structures: list[StructureType] = Field(
        [], description="Structures associated with this entry."
    )
    attachments: list[AttachmentRecord] = Field([])
    aliases: dict[str, str] = Field(
        {},
        description="Aliases of fields to use when generating column names.",
        exclude=True,
    )

    def to_contribs_entry(self) -> dict[str, Any]:
        """Format this entry as an MPContribs compatible entry."""
        return {
            "identifier": self.identifier,
            "formula": self.formula,
            "data": {
                self.aliases.get(
                    k, k
                ): f"{getattr(self,k,None)} {self.units.get(k,'')}".strip()
                for k in set(self.__class__.model_fields).difference(NON_DATA_FIELDS)
            },
            "structures": self.structures,
            "attachments": self.attachments,
        }

    @property
    def columns(self) -> dict[str, str]:
        return {
            self.aliases.get(k, k): self.units.get(k)
            or (
                ""
                if any(t in get_args(field.annotation) for t in (int, float))
                else None
            )
            for k, field in self.__class__.model_fields.items()
            if k not in NON_DATA_FIELDS
        }

    @property
    def metadata(self) -> dict[str, str]:
        return {
            self.aliases.get(k, k): field.description
            for k, field in self.__class__.model_fields.items()
            if k not in NON_DATA_FIELDS and field.description
        }
