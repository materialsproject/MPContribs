from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.bulk import (
    BulkDeleteSummary,
    BulkFailure,
    BulkWriteSummary,
    bulk_failure_from_exception,
)
from mpcontribs_api.exceptions import ConflictError, NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# BulkFailure
# ---------------------------------------------------------------------------


class TestBulkFailure:
    def test_required_fields(self):
        failure = BulkFailure(index=3, error_code="conflict", message="duplicate")
        assert failure.index == 3
        assert failure.error_code == "conflict"
        assert failure.message == "duplicate"

    def test_identifier_defaults_to_none(self):
        failure = BulkFailure(index=0, error_code="x", message="y")
        assert failure.identifier is None

    def test_identifier_carries_arbitrary_dict(self):
        identifier = {"project": "proj", "identifier": "mp-1"}
        failure = BulkFailure(index=0, identifier=identifier, error_code="x", message="y")
        assert failure.identifier == identifier


# ---------------------------------------------------------------------------
# BulkWriteSummary
# ---------------------------------------------------------------------------


class TestBulkWriteSummary:
    def test_fields(self):
        summary = BulkWriteSummary[int](total=3, succeeded=[1, 2], failed=[])
        assert summary.total == 3
        assert summary.succeeded == [1, 2]
        assert summary.failed == []

    def test_failed_items_typed(self):
        failure = BulkFailure(index=1, error_code="validation_error", message="bad")
        summary = BulkWriteSummary[int](total=2, succeeded=[1], failed=[failure])
        assert summary.failed[0].index == 1

    def test_empty_summary(self):
        summary = BulkWriteSummary[int](total=0, succeeded=[], failed=[])
        assert summary.total == 0

    def test_serialization_shape(self):
        failure = BulkFailure(index=0, error_code="conflict", message="dup")
        summary = BulkWriteSummary[int](total=1, succeeded=[], failed=[failure])
        dumped = summary.model_dump()
        assert dumped == {
            "total": 1,
            "succeeded": [],
            "failed": [{"index": 0, "identifier": None, "error_code": "conflict", "message": "dup"}],
        }


# ---------------------------------------------------------------------------
# BulkDeleteSummary
# ---------------------------------------------------------------------------


class TestBulkDeleteSummary:
    def test_fields(self):
        summary = BulkDeleteSummary(num_deleted=5, num_children_deleted=12)
        assert summary.num_deleted == 5
        assert summary.num_children_deleted == 12

    def test_zero_counts(self):
        summary = BulkDeleteSummary(num_deleted=0, num_children_deleted=0)
        assert summary.model_dump() == {"num_deleted": 0, "num_children_deleted": 0}


# ---------------------------------------------------------------------------
# bulk_failure_from_exception
# ---------------------------------------------------------------------------


class TestBulkFailureFromException:
    def test_app_error_uses_its_error_code_and_message(self):
        failure = bulk_failure_from_exception(2, None, ConflictError("already exists"))
        assert failure.index == 2
        assert failure.error_code == "conflict"
        assert failure.message == "already exists"

    def test_not_found_error(self):
        failure = bulk_failure_from_exception(0, None, NotFoundError("gone"))
        assert failure.error_code == "not_found"

    def test_validation_error(self):
        failure = bulk_failure_from_exception(0, None, ValidationError("bad payload"))
        assert failure.error_code == "validation_error"
        assert failure.message == "bad payload"

    def test_app_error_default_message_is_class_name(self):
        failure = bulk_failure_from_exception(0, None, ConflictError())
        assert failure.message == "ConflictError"

    def test_generic_exception_collapses_to_internal_error(self):
        failure = bulk_failure_from_exception(1, None, RuntimeError("secret traceback details"))
        assert failure.error_code == "internal_error"

    def test_generic_exception_message_is_class_name_only(self):
        # Internals must not leak to the client; only the exception class name survives.
        failure = bulk_failure_from_exception(1, None, RuntimeError("secret traceback details"))
        assert failure.message == "RuntimeError"
        assert "secret" not in failure.message

    def test_identifier_threaded_through(self):
        identifier = {"id": str(PydanticObjectId())}
        failure = bulk_failure_from_exception(4, identifier, ValueError("x"))
        assert failure.identifier == identifier
        assert failure.index == 4
