"""Unit tests for the thin, content-addressed ``Attachment`` index model.

Attachments are now immutable, content-addressed S3 objects like structures/tables. The Mongo document
is a thin locator whose natural key is ``(project, hash)``, plus the ``mime`` clients filter on. There
is no inline content or md5 content-hashing anymore.
"""

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.attachments.models import (
    Attachment,
    AttachmentFilter,
    AttachmentOut,
)
from mpcontribs_api.domains.components.models import ComponentIdentity
from mpcontribs_api.exceptions import ValidationError as AppValidationError

HASH = "c" * 64


def _payload(**overrides) -> dict:
    payload = {
        "_id": PydanticObjectId(),
        "project": "my_project",
        "hash": HASH,
        "size": 1024,
        "ext": "gz",
        "mime": "application/gzip",
    }
    payload.update(overrides)
    return payload


class TestAttachment:
    def test_valid_construction(self):
        attachment = Attachment(**_payload())
        assert attachment.project == "my_project"
        assert attachment.hash == HASH
        assert attachment.size == 1024
        assert attachment.ext == "gz"
        assert attachment.mime == "application/gzip"

    def test_collection_name(self):
        assert Attachment.Settings.name == "attachments"

    def test_identity_is_project_and_hash(self):
        doc = Attachment(**_payload())
        assert doc.identity_model is ComponentIdentity
        assert doc.identity() == ComponentIdentity(project="my_project", hash=HASH)

    def test_no_inline_content_or_md5(self):
        doc = Attachment(**_payload())
        assert not hasattr(doc, "content")
        assert not hasattr(doc, "md5")
        assert not hasattr(doc, "name")

    def test_invalid_mime_raises(self):
        with pytest.raises(AppValidationError):
            Attachment(**_payload(mime="not-a-mime"))

    def test_missing_mime_raises(self):
        payload = _payload()
        del payload["mime"]
        with pytest.raises(PydanticValidationError):
            Attachment(**payload)

    def test_hash_must_be_a_valid_digest(self):
        with pytest.raises(AppValidationError):
            Attachment(**_payload(hash="nothex"))


class TestAttachmentOut:
    def test_all_fields_optional(self):
        out = AttachmentOut()
        assert out.id is None
        assert out.project is None
        assert out.hash is None
        assert out.mime is None

    def test_default_fields(self):
        assert AttachmentOut.default_fields() == ("id", "project", "hash", "size", "ext", "mime")

    def test_populates_id_from_mongo_alias(self):
        oid = PydanticObjectId()
        out = AttachmentOut.model_validate({"_id": oid, "hash": HASH})
        assert out.id == oid

    def test_validators_still_apply_when_value_given(self):
        with pytest.raises(AppValidationError):
            AttachmentOut(mime="not-a-mime")


class TestAttachmentFilter:
    def test_empty_filter(self):
        filter = AttachmentFilter()
        assert filter.id is None
        assert filter.hash is None
        assert filter.mime__ilike is None

    def test_constants_bind_attachment_model(self):
        assert AttachmentFilter.Constants.model is Attachment

    def test_hash_value_validated(self):
        assert AttachmentFilter(hash=HASH).hash == HASH

    def test_invalid_hash_raises(self):
        with pytest.raises(AppValidationError):
            AttachmentFilter(hash="nothex")

    def test_id_in_accepts_object_ids(self):
        oids = [PydanticObjectId(), PydanticObjectId()]
        assert AttachmentFilter(id__in=oids).id__in == oids
