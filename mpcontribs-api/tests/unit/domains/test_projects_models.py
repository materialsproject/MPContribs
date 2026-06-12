import pytest
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.projects.models import (
    Column,
    Project,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    Reference,
    Stats,
)

# ---------------------------------------------------------------------------
# Column
# ---------------------------------------------------------------------------


class TestColumn:
    def test_path_only(self):
        col = Column(path="data.band_gap")
        assert col.path == "data.band_gap"
        assert col.min is None
        assert col.max is None
        assert col.unit is None

    def test_full_column(self):
        col = Column(path="data.band_gap", min=0.0, max=10.0, unit="eV")
        assert col.min == 0.0
        assert col.max == 10.0
        assert col.unit == "eV"

    def test_segments_single(self):
        col = Column(path="energy")
        assert col.segments == ("energy",)

    def test_segments_dotted(self):
        col = Column(path="data.band_gap.value")
        assert col.segments == ("data", "band_gap", "value")

    def test_segments_two_level(self):
        col = Column(path="data.volume")
        assert col.segments == ("data", "volume")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_valid_stats(self):
        stats = Stats(columns=3, contributions=100, tables=5, structures=10, attachments=2, size=1024.5)
        assert stats.columns == 3
        assert stats.contributions == 100
        assert stats.size == 1024.5

    def test_zero_values_allowed(self):
        stats = Stats(columns=0, contributions=0, tables=0, structures=0, attachments=0, size=0.0)
        assert stats.contributions == 0

    def test_missing_field_raises(self):
        with pytest.raises(PydanticValidationError):
            Stats(columns=1, contributions=2, tables=3, structures=4, attachments=5)  # missing size


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------


class TestReference:
    def test_valid_reference(self):
        ref = Reference(label="Paper", url="https://doi.org/10.1000/xyz")
        assert ref.label == "Paper"
        assert str(ref.url).startswith("https://doi.org")

    def test_invalid_url_raises(self):
        with pytest.raises(PydanticValidationError):
            Reference(label="Paper", url="not-a-url")

    def test_missing_label_raises(self):
        with pytest.raises(PydanticValidationError):
            Reference(url="https://example.com")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ProjectOut — optional fields, extra ignored
# ---------------------------------------------------------------------------


class TestProjectOut:
    def test_all_fields_optional(self):
        out = ProjectOut()
        assert out.id is None
        assert out.title is None
        assert out.authors is None
        assert out.stats is None

    def test_extra_fields_ignored(self):
        out = ProjectOut(title="My Project", _unknown_field="ignored")  # type: ignore[call-arg]
        assert out.title == "My Project"

    def test_with_stats(self):
        stats = Stats(columns=1, contributions=2, tables=0, structures=0, attachments=0, size=512.0)
        out = ProjectOut(title="My Project", stats=stats)
        assert out.stats is not None
        assert out.stats.contributions == 2

    def test_boolean_fields(self):
        out = ProjectOut(is_public=True, is_approved=False)
        assert out.is_public is True
        assert out.is_approved is False

    def test_license_values(self):
        out_cca4 = ProjectOut(license="CCA4")
        out_ccpd = ProjectOut(license="CCPD")
        assert out_cca4.license == "CCA4"
        assert out_ccpd.license == "CCPD"

    def test_invalid_license_raises(self):
        with pytest.raises(PydanticValidationError):
            ProjectOut(license="MIT")


# ---------------------------------------------------------------------------
# ProjectOut — field projection helpers (inherited from SparseFieldsModel)
# ---------------------------------------------------------------------------


class TestProjectOutProjection:
    def test_parse_fields_none_returns_none(self):
        assert ProjectOut.parse_fields(None) is None

    def test_parse_fields_valid_field(self):
        result = ProjectOut.parse_fields(["title"])
        assert result is not None
        assert "title" in result

    def test_parse_fields_multiple_fields(self):
        result = ProjectOut.parse_fields(["title", "authors", "is_public"])
        assert result is not None
        assert "title" in result
        assert "authors" in result
        assert "is_public" in result

    def test_parse_fields_unknown_raises(self):
        from mpcontribs_api.exceptions import ValidationError as AppValidationError

        with pytest.raises(AppValidationError):
            ProjectOut.parse_fields(["nonexistent_field"])

    def test_projection_none_returns_self(self):
        assert ProjectOut.projection(None) is ProjectOut

    def test_projection_with_fields(self):
        fields = ProjectOut.parse_fields(["title", "authors"])
        projected = ProjectOut.projection(fields)
        assert projected is not ProjectOut
        assert hasattr(projected.Settings, "projection")


# ---------------------------------------------------------------------------
# ProjectPatch
# ---------------------------------------------------------------------------


class TestProjectPatch:
    def test_all_optional(self):
        patch = ProjectPatch()
        assert patch.title is None
        assert patch.authors is None
        assert patch.owner is None

    def test_partial_update(self):
        patch = ProjectPatch(title="Updated Title", is_public=True)
        assert patch.title == "Updated Title"
        assert patch.is_public is True

    def test_invalid_short_str_for_title_raises(self):
        with pytest.raises(PydanticValidationError):
            ProjectPatch(title="ab")  # too short

    def test_default_lists_are_empty(self):
        patch = ProjectPatch()
        assert patch.references == []
        assert patch.columns == []

    def test_invalid_license_raises(self):
        with pytest.raises(PydanticValidationError):
            ProjectPatch(license="GPL")


# ---------------------------------------------------------------------------
# Project.from_input_model (smoke-test via ProjectIn)
# ---------------------------------------------------------------------------


VALID_STATS = Stats(columns=0, contributions=0, tables=0, structures=0, attachments=0, size=0.0)


class TestProjectFromInputModel:
    def _make_input(self, **overrides):
        defaults = {
            "_id": "test-proj",
            "title": "Test Project",
            "authors": "Alice, Bob",
            "description": "A test project",
            "owner": "google:alice@example.com",
            "unique_identifiers": True,
            "stats": VALID_STATS,
        }
        defaults.update(overrides)
        return ProjectIn(**defaults)

    def test_from_input_model_creates_project(self):
        project_in = self._make_input()
        project = Project.from_input_model(project_in)
        assert isinstance(project, Project)
        assert project.id == "test-proj"
        assert project.title == "Test Project"

    def test_from_input_model_preserves_owner(self):
        project_in = self._make_input(owner="github:bob@github.com")
        project = Project.from_input_model(project_in)
        assert project.owner == "github:bob@github.com"

    def test_from_input_model_defaults(self):
        project_in = self._make_input()
        project = Project.from_input_model(project_in)
        assert project.is_public is False
        assert project.is_approved is False
        assert project.references == []
        assert project.columns == []


# ---------------------------------------------------------------------------
# Project.decode_cursor (string-id override)
# ---------------------------------------------------------------------------


class TestProjectDecodeCursor:
    def test_round_trips_string_id(self):
        from mpcontribs_api.pagination import encode_cursor

        assert Project.decode_cursor(encode_cursor("my-project")) == "my-project"

    def test_returns_plain_str_not_object_id(self):
        from mpcontribs_api.pagination import encode_cursor

        decoded = Project.decode_cursor(encode_cursor("solar-cells"))
        assert type(decoded) is str

    def test_malformed_cursor_raises_value_error(self):
        with pytest.raises(ValueError):
            Project.decode_cursor("!!!not-base64!!!")
