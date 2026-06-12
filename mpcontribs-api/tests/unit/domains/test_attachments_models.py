"""Unit tests for domains/attachments/models.py."""

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.attachments.models import (
    Attachment,
    AttachmentFilter,
    AttachmentIn,
    AttachmentOut,
    AttachmentPatch,
)
from mpcontribs_api.exceptions import ValidationError as AppValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(**overrides) -> dict:
    payload = {
        "_id": PydanticObjectId(),
        "name": "spectrum.json.gz",
        "md5": "c" * 32,
        "mime": "application/gzip",
        "content": 1,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Attachment / AttachmentIn
# ---------------------------------------------------------------------------


class TestAttachment:
    def test_valid_construction(self):
        attachment = Attachment(**_payload())
        assert attachment.name == "spectrum.json.gz"
        assert attachment.content == 1

    def test_collection_name(self):
        assert Attachment.Settings.name == "attachments"

    def test_name_requires_extension(self):
        with pytest.raises(AppValidationError):
            Attachment(**_payload(name="noextension"))

    def test_md5_normalized(self):
        attachment = Attachment(**_payload(md5="C" * 32))
        assert attachment.md5 == "c" * 32

    def test_invalid_md5_raises(self):
        with pytest.raises(AppValidationError):
            Attachment(**_payload(md5="zz"))

    def test_invalid_mime_raises(self):
        with pytest.raises(AppValidationError):
            Attachment(**_payload(mime="text/plain"))

    def test_missing_content_raises(self):
        payload = _payload()
        del payload["content"]
        with pytest.raises(PydanticValidationError):
            Attachment(**payload)

    def test_attachment_in_is_attachment(self):
        # Input models subclass their document so from_input_model can dump them 1:1.
        assert issubclass(AttachmentIn, Attachment)
        assert isinstance(AttachmentIn(**_payload()), Attachment)


# ---------------------------------------------------------------------------
# AttachmentOut
# ---------------------------------------------------------------------------


class TestAttachmentOut:
    def test_all_fields_optional(self):
        out = AttachmentOut()
        assert out.id is None
        assert out.name is None
        assert out.md5 is None
        assert out.mime is None

    def test_partial_population(self):
        out = AttachmentOut(name="a.gz")
        assert out.name == "a.gz"
        assert out.md5 is None

    def test_populates_id_from_mongo_alias(self):
        oid = PydanticObjectId()
        out = AttachmentOut.model_validate({"_id": oid, "md5": "d" * 32})
        assert out.id == oid

    def test_validators_still_apply_when_value_given(self):
        with pytest.raises(AppValidationError):
            AttachmentOut(mime="text/plain")


# ---------------------------------------------------------------------------
# AttachmentPatch
# ---------------------------------------------------------------------------


class TestAttachmentPatch:
    def test_all_fields_optional(self):
        patch = AttachmentPatch()
        assert patch.name is None
        assert patch.mime is None

    def test_partial_patch_excludes_unset(self):
        patch = AttachmentPatch(name="renamed.gz")
        assert patch.model_dump(exclude_unset=True) == {"name": "renamed.gz"}

    def test_invalid_name_raises(self):
        with pytest.raises(AppValidationError):
            AttachmentPatch(name="noextension")

    def test_invalid_mime_raises(self):
        with pytest.raises(AppValidationError):
            AttachmentPatch(mime="bogus")


# ---------------------------------------------------------------------------
# AttachmentFilter
# ---------------------------------------------------------------------------


class TestAttachmentFilter:
    def test_empty_filter(self):
        filter = AttachmentFilter()
        assert filter.id is None
        assert filter.md5 is None
        assert filter.name__ilike is None

    def test_constants_bind_attachment_model(self):
        assert AttachmentFilter.Constants.model is Attachment

    def test_md5_value_validated(self):
        assert AttachmentFilter(md5="E" * 32).md5 == "e" * 32

    def test_invalid_md5_raises(self):
        with pytest.raises(AppValidationError):
            AttachmentFilter(md5="nothex")

    def test_id_in_accepts_object_ids(self):
        oids = [PydanticObjectId(), PydanticObjectId()]
        assert AttachmentFilter(id__in=oids).id__in == oids
