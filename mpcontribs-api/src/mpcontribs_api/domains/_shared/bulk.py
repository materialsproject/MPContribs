from typing import Any, Self

import structlog
from pydantic import BaseModel, model_validator
from pymongo.errors import DuplicateKeyError

from mpcontribs_api.exceptions import AppError, ConflictError

logger = structlog.get_logger(__name__)


class BulkFailure(BaseModel):
    """A single failed item in a bulk write, identified by its position in the input batch."""

    index: int
    identifier: dict[str, Any] | None = None
    error_code: str
    message: str

    @model_validator(mode="after")
    def _emit_log(self) -> Self:
        logger.info(
            "bulk item failed",
            message=self.message,
            error_code=self.error_code,
            index=self.index,
            identifier=self.identifier,
        )
        return self


class BulkWriteSummary[T](BaseModel):
    """Result of a bulk write that supports per-item failure reporting.

    ``total`` is the size of the input batch (succeeded + failed). ``succeeded`` carries the
    fully inserted documents; ``failed`` carries one ``BulkFailure`` per rejected item, with
    enough context for the caller to retry just those items.
    """

    total: int
    succeeded: list[T]
    failed: list[BulkFailure]


class BulkDeleteSummary[T](BaseModel):
    num_deleted: int
    num_children_deleted: int


class BulkUpdateSummary(BaseModel):
    """Result of a filtered bulk update.

    No per-item result, reflects MongoDB's bulk update response.

    Attributes:
        matched: documents the (scoped) filter matched
        modified: documents whose stored value actually changed
        projects: the projects the update touched, so the caller can see its blast radius
    """

    matched: int
    modified: int
    projects: list[str]


def bulk_failure_from_exception(index: int, identifier: dict[str, Any] | None, exc: BaseException) -> BulkFailure:
    """Translate any exception into a BulkFailure entry.

    ``AppError`` subclasses contribute their ``error_code`` and ``message``. A raw pymongo
    ``DuplicateKeyError`` (a unique-index violation, e.g. a colliding identity on the transactional
    insert or upsert paths) maps to ``conflict``
    """
    if isinstance(exc, AppError):
        return BulkFailure(index=index, identifier=identifier, error_code=exc.error_code, message=exc.message)
    if isinstance(exc, DuplicateKeyError):
        return BulkFailure(
            index=index,
            identifier=identifier,
            error_code=ConflictError.error_code,
            message="a resource with these identifiers already exists",
        )
    return BulkFailure(index=index, identifier=identifier, error_code="internal_error", message=type(exc).__name__)
