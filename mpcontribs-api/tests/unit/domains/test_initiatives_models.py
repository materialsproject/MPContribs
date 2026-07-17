import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.exceptions import ValidationError

OID = PydanticObjectId()
OWNER = "google:alice@example.com"


def _init(**overrides) -> Initiative:
    payload = {"_id": OID, "slug": "battery-genome", "name": "Battery Genome", "owner": OWNER}
    payload.update(overrides)
    return Initiative.model_validate(payload)


# ---------------------------------------------------------------------------
# Slug validation / normalisation
# ---------------------------------------------------------------------------


class TestSlug:
    def test_lowercases_and_strips(self):
        assert _init(slug="  Battery-Genome-2025 ").slug == "battery-genome-2025"

    @pytest.mark.parametrize("bad", ["has space", "under_score", "trailing-", "-leading", "sym!bol", "Dou--ble"])
    def test_rejects_malformed_slug(self, bad):
        with pytest.raises(ValidationError):
            _init(slug=bad)

    def test_rejects_too_short_via_length(self):
        # "ab" is well-formed but below the 3-char minimum, so the length constraint rejects it.
        with pytest.raises(PydanticValidationError):
            _init(slug="ab")


# ---------------------------------------------------------------------------
# Initiative document invariants
# ---------------------------------------------------------------------------


class TestInitiative:
    def test_defaults_private_unapproved(self):
        init = _init()
        assert init.is_public is False
        assert init.is_approved is False

    def test_public_and_approved_ok(self):
        init = _init(is_public=True, is_approved=True)
        assert init.is_public is True

    def test_public_without_approved_rejected(self):
        with pytest.raises(ValidationError):
            _init(is_public=True, is_approved=False)


# ---------------------------------------------------------------------------
# InitiativeIn (create contract)
# ---------------------------------------------------------------------------


class TestInitiativeIn:
    def test_minimal_valid(self):
        data = InitiativeIn(slug="battery-genome", name="Battery Genome")
        assert data.slug == "battery-genome"

    @pytest.mark.parametrize("field", ["owner", "is_public", "is_approved", "id", "unknown"])
    def test_forbids_server_controlled_and_unknown_fields(self, field):
        # owner and the flags are forced server-side; none are part of the input contract.
        with pytest.raises(PydanticValidationError):
            InitiativeIn(slug="battery-genome", name="Battery Genome", **{field: "x"})

    def test_normalises_slug(self):
        assert InitiativeIn(slug="Battery-Genome", name="x").slug == "battery-genome"


# ---------------------------------------------------------------------------
# InitiativeOut / InitiativePatch shape
# ---------------------------------------------------------------------------


class TestOutAndPatch:
    def test_out_populates_id_from_alias(self):
        out = InitiativeOut.model_validate({"_id": OID, "slug": "battery-genome"})
        assert out.id == OID

    def test_patch_tracks_only_set_fields(self):
        patch = InitiativePatch(name="Renamed")
        assert patch.model_dump(exclude_unset=True) == {"name": "Renamed"}

    def test_patch_has_no_slug_or_owner_field(self):
        # slug and owner are immutable, so they are not part of the patch surface.
        assert "slug" not in InitiativePatch.model_fields
        assert "owner" not in InitiativePatch.model_fields
