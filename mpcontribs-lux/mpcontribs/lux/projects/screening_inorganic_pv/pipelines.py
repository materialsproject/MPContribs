"""Data pipeline scaffold for this project.

Implement extraction, transformation, aggregation, and optional upload helpers here.
"""

from collections.abc import Iterable

from .schemas import ContributionRecord


def extract() -> Iterable[dict]:
    """Load raw records from source files/APIs."""
    return []


def transform(raw_records: Iterable[dict]) -> Iterable[dict]:
    """Normalize and clean raw records."""
    return raw_records


def aggregate(records: Iterable[dict]) -> list[ContributionRecord]:
    """Validate and convert records into typed schema instances."""
    return [ContributionRecord(**record) for record in records]


def run() -> list[ContributionRecord]:
    """Execute the default local pipeline."""
    return aggregate(transform(extract()))
