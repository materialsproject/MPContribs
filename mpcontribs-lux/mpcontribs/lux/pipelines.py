"""Data pipeline scaffold for this project.

Implement extraction, transformation, aggregation, and optional upload helpers here.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from mpcontribs.client import Client as MPCClient, MPContribsClientError
from mpcontribs.lux.schemas import ContributionRecord

if TYPE_CHECKING:
    from collections.abc import Iterable


class LuxETL:
    """Perform basic extract, transform, load operations for MPContribs uploads.

    To use a LuxETL:
        1. (Optional) If you want to upload data to MPContribs, you first must
            create the project. Run a given LuxETL class's `init_columns_and_meta`
            method: `LuxETL.init_columns_and_meta` which will set up the project.
        2. Initialize the ETL class and run `LuxETL().load()`, which will
            execute the pipeline and return a list of records.
            To submit these to MPContribs, run instead `LuxETL().load(submit=True)`.

    NB: if you define a schema using `ContributionRecord`, the conversion to
    MPContribs-format data structures will be handled automatically.
    """

    project: str
    schema: ContributionRecord | None = None

    def __init__(self, client: MPCClient | None = None, **kwargs) -> None:

        self.client = client or MPCClient(project=self.project)

    @classmethod
    def init_project(cls, **kwargs) -> MPCClient:
        try:
            client = MPCClient(project=cls.project)

        except MPContribsClientError:
            with MPCClient() as client:
                mpr.contribs.create_project(
                    name=cls.project,
                    **kwargs,
                )
            client = MPCClient(project=cls.project)
        return client

    @classmethod
    def init_columns_and_meta(
        cls, unique_identifiers: bool | None = None, **kwargs
    ) -> None:
        if not cls.schema:
            raise ValueError("No schema provided to initialize columns")

        client = cls.init_project(**kwargs)
        client.init_columns(cls.schema.columns)

        meta = {
            "other": cls.schema.metadata,
        }
        if unique_identifiers is not None:
            meta["unique_identifiers"] = True
        client.update_project(meta)

    def extract(self) -> Iterable[dict]:
        """Load raw records from source files/APIs."""
        return []

    def transform(self, raw_records: Iterable[dict]) -> Iterable[dict[str, Any]]:
        """Normalize, clean, and validate raw records."""
        if self.schema:
            return [self.schema(**raw).to_contribs_entry() for raw in raw_records]
        return raw_records

    def load(self, submit: bool = False) -> Iterable[dict[str, Any]]:
        """Execute the default local pipeline."""
        records = self.transform(self.extract())
        if submit:
            self.client.submit_contributions(records)
        return records
