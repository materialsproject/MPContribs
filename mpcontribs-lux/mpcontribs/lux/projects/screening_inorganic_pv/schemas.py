"""Pydantic schemas for this project.

Replace these starter models with project-specific, fully documented schemas.
"""

from pydantic import BaseModel, Field


class ContributionRecord(BaseModel, extra="forbid"):
    """Core contribution row schema (starter)."""

    identifier: str = Field(description="Contribution identifier")
    formula: str | None = Field(default=None, description="Reduced chemical formula")


class AttachmentRecord(BaseModel, extra="forbid"):
    """Attachment metadata schema (starter)."""

    identifier: str = Field(description="Contribution identifier")
    name: str = Field(description="Attachment logical name")
    mime_type: str | None = Field(default=None, description="Attachment MIME type")
