"""transparent_conductors ETL pipeline migrated from notebook logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pandas import read_excel

from mpcontribs.lux.pipelines import LuxETL

from .schemas import GOOGLE_SHEET_URL, PROJECT_NAME, SHEETS, TransparentConductorRecord

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any
    from mpcontribs.lux.schemas import ContributionRecord


class TransparentConductorsETL(LuxETL):
    """Extract and transform transparent conductor entries from the source workbook."""

    project = PROJECT_NAME
    schema = TransparentConductorRecord

    def extract(self) -> list[dict[str, Any]]:
        """Read workbook sheets and parse each row into schema-ready dicts."""
        records: list[dict[str, Any]] = []
        for sheet_name in SHEETS:
            doping = sheet_name.split(" ")[0]
            df = read_excel(GOOGLE_SHEET_URL, sheet_name=sheet_name, header=[0, 1, 2])

            records += [row for row in df.to_dict(orient="records")]
        return records

    def transform(self, raw_records: Iterable[dict]) -> Iterable[dict[str, Any]]:
        """Normalize, clean, and validate raw records."""
        return [
            self.schema.from_sheet_row(raw).to_contribs_entry() for raw in raw_records
        ]
