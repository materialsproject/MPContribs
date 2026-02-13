"""2dmatpedia ETL pipeline migrated from notebook logic."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING
from urllib.request import urlretrieve

from monty.json import MontyDecoder

from mpcontribs.lux.pipelines import LuxETL

from mpcontribs.lux.projects.twodmatpedia.schemas import DETAILS_URL, TwoDMatPediaRecord

if TYPE_CHECKING:
    from typing import Any


class TwoDMatPediaETL(LuxETL):
    """Extract, transform, and aggregate 2dmatpedia records."""

    project: str = "2dmatpedia"
    DB_JSON_URL: str = "http://www.2dmatpedia.org/static/db.json.gz"

    def extract(self) -> list[dict[str, Any]]:
        """Download (if needed) and load raw JSONL records from db.json.gz."""

        decoder = MontyDecoder()
        with NamedTemporaryFile(suffix=".json.gz") as f:
            urlretrieve(self.DB_JSON_URL, f.name)

            with gzip.open(f.name, "rb") as handle:
                raw_records: list[dict[str, Any]] = [
                    decoder.decode(line) for line in handle
                ]
        return raw_records

    def transform(self, raw_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter to supported source prefixes and map to normalized dicts."""
        return [TwoDMatPediaRecord(**raw).to_contribs_entry() for raw in raw_records]

    def filter_existing(
        self, contributions: Iterable[TwoDMatPediaRecord]
    ) -> list[dict[str, Any]]:
        """Remove existing contributions based on the `details` data-id key."""
        existing = self.client.get_all_ids(
            query={"project": self.project_name},
            data_id_fields={self.project_name: "details"},
        ).get(self.project_name, {})
        details_set = existing.get("details_set", set())

        return [
            contribution
            for contribution in contributions
            if contribution.get("data", {}).get("details") not in details_set
        ]

    def run(self, submit: bool = False, per_page: int = 30) -> list[dict[str, Any]]:
        """Run ETL and optionally submit only missing records."""
        records = self.transform(self.extract())

        if submit:
            if missing := self.filter_existing(contributions):
                self.client.submit_contributions(
                    [record.to_contribs_entry() for record in missing]
                )

        return records
