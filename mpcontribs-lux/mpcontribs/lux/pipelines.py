"""Data pipeline scaffold for this project.

Implement extraction, transformation, aggregation, and optional upload helpers here.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from mpcontribs.client import Client as MPCClient
from mpcontribs.lux.schemas import ContributionRecord

if TYPE_CHECKING:
    from collections.abc import Iterable


class LuxETL:
    """Perform basic extract, transform, load operations for MPContribs uploads."""

    def __init__(self, project : str | None = None, client: MPCClient | None = None) -> None:
        
        if not project:
            raise ValueError(
                "Project name cannot be null or an empty string!"
            )
        self.project = project
        self.client = client or MPCClient(project=self.project)

    def extract(self) -> Iterable[dict]:
        """Load raw records from source files/APIs."""
        return []

    def transform(self, raw_records: Iterable[dict]) -> Iterable[dict]:
        """Normalize and clean raw records."""
        return raw_records

    def aggregate(self, records: Iterable[dict]) -> list[ContributionRecord]:
        """Validate and convert records into typed schema instances."""
        return [ContributionRecord(**record) for record in records]

    def run(self) -> list[ContributionRecord]:
        """Execute the default local pipeline."""
        return self.aggregate(self.transform(self.extract()))
