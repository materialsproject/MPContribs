import pytest
from mpcontribs_api.exceptions import ValidationError as AppValidationError
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.domains.projects.models import (
    Column,
    Project,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    Reference,
    Stats,
    validate_column_limit,
)
from mpcontribs_api.exceptions import ValidationError


class TestUniqueColumnValidation:
    def _make_input(self, **overrides):
        defaults = {
            "_id": "uc-proj",
            "title": "Test Project",
            "authors": "Alice",
            "description": "A test project",
            "owner": "google:alice@example.com",
            "stats": Stats(columns=0, contributions=0, tables=0, structures=0, attachments=0, size=0.0),
        }
        defaults.update(overrides)
        return ProjectIn(**defaults)

    def test_none_is_allowed(self):
        assert self._make_input().unique_column is None

    def test_dotted_path_accepted_even_if_absent_from_columns(self):
        # No subset-of-columns check: columns is derived/eventually-consistent.
        assert self._make_input(unique_column="conditions.temp").unique_column == "conditions.temp"

    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            self._make_input(unique_column="")

    def test_blank_segment_rejected(self):
        with pytest.raises(ValidationError):
            self._make_input(unique_column="a..b")

    def test_patch_validates_unique_column(self):
        with pytest.raises(ValidationError):
            ProjectPatch(unique_column="a..b")

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

    def test_fields_default_to_zero(self):
        # Stats is server-computed and every field defaults to zero, so an empty Stats is valid.
        stats = Stats()
        assert stats.columns == 0
        assert stats.contributions == 0
        assert stats.tables == 0
        assert stats.structures == 0
        assert stats.attachments == 0
        assert stats.size == 0.0


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
    def test_parse_fields_none_returns_default_fields(self):
        # Omitted _fields (None) -> the route's default_fields() (plus identity), not "all".
        assert ProjectOut.parse_fields(None) == frozenset(ProjectOut.default_fields())

    def test_parse_fields_empty_returns_identity_only(self):
        # Present-but-empty _fields -> identity fields only.
        assert ProjectOut.parse_fields([]) == frozenset({"id"})

    def test_parse_fields_all_sentinel_returns_none(self):
        # `_all` -> every field.
        assert ProjectOut.parse_fields(["_all"]) is None

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

    def test_is_approved_defaults_to_none(self):
        # None => unset, so an ordinary patch never implicitly touches approval.
        assert ProjectPatch().is_approved is None

    def test_columns_is_not_a_patch_field(self):
        # ``columns`` is server-owned and must not be accepted on the patch model.
        assert "columns" not in ProjectPatch.model_fields
        assert "stats" not in ProjectPatch.model_fields

    def test_invalid_license_raises(self):
        with pytest.raises(PydanticValidationError):
            ProjectPatch(license="GPL")


# ---------------------------------------------------------------------------
# Project.from_input_model (smoke-test via ProjectIn)
# ---------------------------------------------------------------------------


class TestProjectFromInputModel:
    def _make_input(self, **overrides):
        defaults = {
            "title": "Test Project",
            "authors": "Alice, Bob",
            "description": "A test project",
            "owner": "google:alice@example.com",
        }
        defaults.update(overrides)
        return ProjectIn(**defaults)

    def test_from_input_model_creates_project(self):
        project_in = self._make_input()
        project = Project.from_input_model(project_in, id="test-proj")
        assert isinstance(project, Project)
        assert project.id == "test-proj"
        assert project.title == "Test Project"

    def test_from_input_model_preserves_owner(self):
        project_in = self._make_input(owner="github:bob@github.com")
        project = Project.from_input_model(project_in, id="test-proj")
        assert project.owner == "github:bob@github.com"

    def test_from_input_model_defaults(self):
        project_in = self._make_input()
        project = Project.from_input_model(project_in, id="test-proj")
        assert project.is_public is False
        assert project.is_approved is False
        assert project.references == []
        assert project.columns == []

    def test_from_input_model_starts_with_empty_server_owned_fields(self):
        # stats/columns aren't on the input model and default empty on the document.
        project = Project.from_input_model(self._make_input(), id="test-proj")
        assert project.stats == Stats()
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


# ---------------------------------------------------------------------------
# Column-length quota (max_columns)
# ---------------------------------------------------------------------------


def _columns(n: int) -> list[Column]:
    return [Column(path=f"data.col_{i}") for i in range(n)]


class TestColumnLengthQuota:
    """The column cap is enforced by ``validate_column_limit`` (called from the repository with the
    caller's effective ``max_columns``), not by the ``ProjectIn``/``ProjectPatch`` models. These
    tests pin the pure function's contract: the cap is inclusive, over-cap writes raise, and a
    non-list value is a no-op so legacy documents that already exceed the cap can still be read back.
    """

    def test_at_cap_is_allowed(self):
        # Inclusive: exactly max_columns entries must pass.
        validate_column_limit(_columns(2), max_columns=2)

    def test_under_cap_is_allowed(self):
        validate_column_limit(_columns(1), max_columns=2)

    def test_over_cap_raises(self):
        with pytest.raises(AppValidationError):
            validate_column_limit(_columns(3), max_columns=2)

    def test_error_reports_offending_length(self):
        with pytest.raises(AppValidationError) as exc_info:
            validate_column_limit(_columns(5), max_columns=2)
        assert exc_info.value.context["column_length"] == 5

    def test_none_is_noop(self):
        # A read path may pass a non-list (e.g. an unset field); it must never raise so legacy
        # documents that predate the cap remain retrievable.
        validate_column_limit(None, max_columns=0)
