import pytest
from beanie import PydanticObjectId
from pymongo.results import DeleteResult

from mpcontribs_api.domains._shared.models import (
    BaseDocumentWithInput,
    ComponentIdentity,
    DeleteResponse,
    DocumentOut,
)
from mpcontribs_api.domains.attachments.models import Attachment, ComponentIdentity, AttachmentIn
from mpcontribs_api.domains.consumers.models import Consumer, ConsumerIdentity
from mpcontribs_api.domains.contributions.models import Contribution, ContributionIdentity
from mpcontribs_api.domains.initiatives.models import Initiative, InitiativeIdentity
from mpcontribs_api.domains.project_groups.models import ProjectGroup, ProjectGroupIdentity
from mpcontribs_api.domains.projects.models import Project, ProjectIdentity, ProjectIn
from mpcontribs_api.domains.structures.models import Structure, ComponentIdentity
from mpcontribs_api.domains.tables.models import Table, ComponentIdentity
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
# Identity abstraction: every domain declares its natural key once, via ``identity_model``.
# The repository reads ``identity_model.model_fields`` directly (and ``identity()`` derives from it)
# so methods stay agnostic to how a given domain is identified (``_id`` vs a compound business key).
# ---------------------------------------------------------------------------


# (Document class, its Identity class, expected natural-key field set)
_DOMAIN_IDENTITIES = [
    (Project, ProjectIdentity, {"id"}),
    (Initiative, InitiativeIdentity, {"slug"}),
    (ProjectGroup, ProjectGroupIdentity, {"name", "owner"}),
    (Consumer, ConsumerIdentity, {"consumer_id"}),
    (Structure, ComponentIdentity, {"md5"}),
    (Table, ComponentIdentity, {"md5"}),
    (Attachment, ComponentIdentity, {"md5"}),
    (
        Contribution,
        ContributionIdentity,
        {"project", "material_id", "chemical_system_id", "formula", "unique_value", "condition_key"},
    ),
]


class TestIdentityContract:
    @pytest.mark.parametrize(("document", "identity", "fields"), _DOMAIN_IDENTITIES)
    def test_identity_model_is_bound(self, document, identity, fields):
        assert document.identity_model is identity

    @pytest.mark.parametrize(("document", "identity", "fields"), _DOMAIN_IDENTITIES)
    def test_natural_key_derives_from_identity_model(self, document, identity, fields):
        # Single source of truth: the natural key comes from the Identity class's fields directly.
        assert identity.model_fields.keys() == fields
        assert document.identity_model.model_fields.keys() == fields

    def test_component_identity_shared_shape_is_md5(self):
        # The three component identities all share ComponentIdentity's single-``md5`` shape.
        assert ComponentIdentity.model_fields.keys() == {"md5"}
        for identity in (ComponentIdentity, ComponentIdentity, ComponentIdentity):
            assert issubclass(identity, ComponentIdentity)
            assert identity.model_fields.keys() == {"md5"}


class TestDocumentIdentityRoundTrips:
    def test_id_keyed_document_identity_is_its_id(self):
        # A project's identity IS its id (the human-chosen slug), so ``identity()`` reads it off ``id``.
        project = Project.from_input_model(
            ProjectIn(title="my-project", authors="a", description="d", owner="google:a@example.com"),
            id="my-proj",
        )
        assert project.identity() == ProjectIdentity(id="my-proj")
        assert project.identity().as_dict() == {"id": "my-proj"}

    def test_content_addressed_component_identity_is_its_md5(self):
        # A component's identity is its server-computed content md5.
        doc = Attachment.from_input(_attachment_in())
        assert doc.identity() == ComponentIdentity(md5=doc.md5)
        assert doc.identity().as_dict() == {"md5": doc.md5}

    def test_compound_identity_reads_all_fields_and_tolerates_nulls(self):
        # A chem-system-only contribution stores null material_id/formula; identity() falls back to the
        # dataclass defaults (keep_nulls=False parity) rather than raising.
        contribution = Contribution.model_validate(
            {"_id": PydanticObjectId(), "project": "p", "chemical_system_id": "Fe-O", "data": {}}
        )
        assert contribution.identity() == ContributionIdentity(
            project="p",
            material_id=None,
            chemical_system_id="Fe-O",
            formula=None,
            unique_value=None,
            condition_key="",
        )


# ---------------------------------------------------------------------------
# DeleteResponse.from_delete_result
# ---------------------------------------------------------------------------


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
