import pytest
from beanie import PydanticObjectId
from pymongo.results import DeleteResult

from mpcontribs_api.domains._shared.models import (
    BaseDocumentWithInput,
    DeleteResponse,
    DocumentOut,
)
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentIn
from mpcontribs_api.domains.contributions.models import Contribution, ContributionIn
from mpcontribs_api.domains.project_groups.models import ProjectGroup
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.pagination import encode_cursor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _attachment_in(**overrides) -> AttachmentIn:
    payload = {
        "name": "data.csv.gz",
        "mime": "application/gzip",
        "content": 1,
    }
    payload.update(overrides)
    return AttachmentIn(**payload)


class _OidOut(DocumentOut[PydanticObjectId]):
    name: str | None = None


# ---------------------------------------------------------------------------
# Component.from_input (server-assigned id, computed md5)
# ---------------------------------------------------------------------------


class TestComponentFromInput:
    def test_returns_document_class_instance(self):
        doc = Attachment.from_input(_attachment_in())
        assert isinstance(doc, Attachment)

    def test_content_carried_id_assigned_md5_computed(self):
        doc = Attachment.from_input(_attachment_in(name="x.gz"))
        assert doc.name == "x.gz"
        assert doc.mime == "application/gzip"
        assert doc.content == 1
        assert doc.id is not None
        assert len(doc.md5) == 32


# ---------------------------------------------------------------------------
# BaseDocumentWithInput.decode_cursor
# ---------------------------------------------------------------------------


class TestDecodeCursor:
    def test_round_trips_object_id(self):
        oid = PydanticObjectId()
        decoded = BaseDocumentWithInput.decode_cursor(encode_cursor(str(oid)))
        assert decoded == oid

    def test_returns_pydantic_object_id(self):
        cursor = encode_cursor(str(PydanticObjectId()))
        assert isinstance(BaseDocumentWithInput.decode_cursor(cursor), PydanticObjectId)

    def test_malformed_base64_raises_value_error(self):
        with pytest.raises(ValueError):
            BaseDocumentWithInput.decode_cursor("!!!not-base64!!!")

    def test_callable_off_concrete_subclass(self):
        oid = PydanticObjectId()
        assert Attachment.decode_cursor(encode_cursor(str(oid))) == oid


# ---------------------------------------------------------------------------
# DocumentOut
# ---------------------------------------------------------------------------


class TestDocumentOut:
    def test_id_defaults_to_none(self):
        assert _OidOut().id is None

    def test_populates_from_mongo_alias(self):
        oid = PydanticObjectId()
        out = _OidOut.model_validate({"_id": oid})
        assert out.id == oid

    def test_serializes_under_id_not_underscore_id(self):
        oid = PydanticObjectId()
        dumped = _OidOut.model_validate({"_id": oid, "name": "n"}).model_dump(by_alias=True)
        assert dumped["id"] == oid
        assert "_id" not in dumped


# ---------------------------------------------------------------------------
# DeleteResponse.from_delete_result
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# identifier_fields() / identifiers() contract
# ---------------------------------------------------------------------------


class TestIdentifierContract:
    def test_default_identifier_fields_is_primary_key(self):
        # Content-addressed components fall back to the base default.
        assert Attachment.identifier_fields() == frozenset({"id"})

    def test_project_uses_id(self):
        assert Project.identifier_fields() == frozenset({"id"})

    def test_project_group_uses_name_and_owner(self):
        assert ProjectGroup.identifier_fields() == frozenset({"name", "owner"})

    def test_contribution_uses_project_and_identifier(self):
        assert Contribution.identifier_fields() == frozenset({"project", "identifier"})
        assert ContributionIn.identifier_fields() == frozenset({"project", "identifier"})

    def test_default_identifiers_reads_values_off_instance(self):
        oid = PydanticObjectId()
        doc = Attachment.from_input(_attachment_in())
        doc.id = oid
        assert doc.identifiers() == {"id": oid}

    def test_contribution_identifiers_returns_natural_key_values(self):
        contrib = ContributionIn(
            **{
                "_id": PydanticObjectId(),
                "project": "test-project",
                "identifier": "mp-1234",
                "formula": "Fe2O3",
                "data": {},
            }
        )
        assert contrib.identifiers() == {"project": "test-project", "identifier": "mp-1234"}


class TestDeleteResponse:
    def test_from_delete_result(self):
        result = DeleteResult({"n": 3}, acknowledged=True)
        assert DeleteResponse.from_delete_result(result).num_deleted == 3

    def test_zero_deleted(self):
        result = DeleteResult({"n": 0}, acknowledged=True)
        assert DeleteResponse.from_delete_result(result).num_deleted == 0

    def test_serialization_shape(self):
        result = DeleteResult({"n": 7}, acknowledged=True)
        assert DeleteResponse.from_delete_result(result).model_dump() == {"num_deleted": 7}
