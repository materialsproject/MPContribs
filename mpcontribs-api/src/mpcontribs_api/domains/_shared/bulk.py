from typing import Any

from pydantic import BaseModel

from mpcontribs_api.exceptions import AppError


class BulkFailure(BaseModel):
    """A single failed item in a bulk write, identified by its position in the input batch."""

    index: int
    identifier: dict[str, Any] | None = None
    error_code: str
    message: str


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


def bulk_failure_from_exception(index: int, identifier: dict[str, Any] | None, exc: BaseException) -> BulkFailure:
    """Translate any exception into a BulkFailure entry.

    ``AppError`` subclasses contribute their ``error_code`` and ``message``; everything else
    collapses to ``internal_error`` with the exception class name in the message so we don't
    leak tracebacks or framework internals to the client.
    """
    if isinstance(exc, AppError):
        return BulkFailure(index=index, identifier=identifier, error_code=exc.error_code, message=exc.message)
    return BulkFailure(index=index, identifier=identifier, error_code="internal_error", message=type(exc).__name__)
