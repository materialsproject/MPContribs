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
from mpcontribs.lux.projects.twodmatpedia.schemas import TwoDMatPediaRecord

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
