import polars as pl
import pytest
from pydantic import BaseModel, ConfigDict

from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FileLike,
    MD5Hash,
    MimeFormat,
    PolarsFrame,
    _coerce_frame,
    _serialize_frame,
)
from mpcontribs_api.exceptions import ValidationError as AppValidationError


class FileLikeModel(BaseModel):
    name: FileLike


class MD5Model(BaseModel):
    digest: MD5Hash


class MimeModel(BaseModel):
    mime: MimeFormat


class FrameModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: PolarsFrame


# ---------------------------------------------------------------------------
# FileLike / _file_name_like_str
# ---------------------------------------------------------------------------


class TestFileLike:
    def test_simple_extension(self):
        assert FileLikeModel(name="archive.gz").name == "archive.gz"

    def test_multiple_dots_valid(self):
        assert FileLikeModel(name="data.tar.gz").name == "data.tar.gz"

    def test_strips_surrounding_whitespace(self):
        assert FileLikeModel(name="  notes.txt  ").name == "notes.txt"

    def test_no_extension_raises(self):
        with pytest.raises(AppValidationError):
            FileLikeModel(name="noextension")

    def test_trailing_dot_raises(self):
        with pytest.raises(AppValidationError):
            FileLikeModel(name="name.")

    def test_empty_string_raises(self):
        with pytest.raises(AppValidationError):
            FileLikeModel(name="")

    def test_leading_dot_file_is_accepted(self):
        # Documents current behavior: dotfiles split into ["", "ext"], which
        # has a non-empty last part and therefore passes.
        assert FileLikeModel(name=".gitignore").name == ".gitignore"


# ---------------------------------------------------------------------------
# MD5Hash / _md5_like
# ---------------------------------------------------------------------------


class TestMD5Hash:
    def test_valid_lowercase_hex(self):
        assert MD5Model(digest="a" * 32).digest == "a" * 32

    def test_uppercase_normalized_to_lowercase(self):
        assert MD5Model(digest="ABCDEF" + "0" * 26).digest == "abcdef" + "0" * 26

    def test_strips_whitespace(self):
        assert MD5Model(digest=f"  {'b' * 32}  ").digest == "b" * 32

    def test_too_short_raises(self):
        with pytest.raises(AppValidationError):
            MD5Model(digest="a" * 31)

    def test_too_long_raises(self):
        with pytest.raises(AppValidationError):
            MD5Model(digest="a" * 33)

    def test_non_hex_characters_raise(self):
        with pytest.raises(AppValidationError):
            MD5Model(digest="g" * 32)

    def test_empty_raises(self):
        with pytest.raises(AppValidationError):
            MD5Model(digest="")


# ---------------------------------------------------------------------------
# MimeFormat / _mime_like
# ---------------------------------------------------------------------------


class TestMimeFormat:
    def test_valid_application_mime(self):
        assert MimeModel(mime="application/gzip").mime == "application/gzip"

    def test_uppercase_normalized(self):
        assert MimeModel(mime="APPLICATION/JSON").mime == "application/json"

    def test_strips_whitespace(self):
        assert MimeModel(mime=" application/zip ").mime == "application/zip"

    def test_non_application_prefix_raises(self):
        with pytest.raises(AppValidationError):
            MimeModel(mime="text/plain")

    def test_empty_subtype_raises(self):
        with pytest.raises(AppValidationError):
            MimeModel(mime="application/")

    def test_missing_slash_raises(self):
        with pytest.raises(AppValidationError):
            MimeModel(mime="applicationgzip")

    def test_extra_slash_raises(self):
        with pytest.raises(AppValidationError):
            MimeModel(mime="application/x/y")


# ---------------------------------------------------------------------------
# DownloadFormat
# ---------------------------------------------------------------------------


class TestDownloadFormat:
    def test_members(self):
        assert {f.value for f in DownloadFormat} == {"jsonl", "csv"}

    def test_constructible_from_value(self):
        assert DownloadFormat("jsonl") is DownloadFormat.JSONL
        assert DownloadFormat("csv") is DownloadFormat.CSV

    def test_str_enum_compares_to_plain_str(self):
        assert DownloadFormat.CSV == "csv"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            DownloadFormat("parquet")


# ---------------------------------------------------------------------------
# PolarsFrame: _coerce_frame / _serialize_frame
# ---------------------------------------------------------------------------


class TestCoerceFrame:
    def test_dataframe_passthrough_is_same_object(self):
        df = pl.DataFrame({"a": [1, 2]})
        assert _coerce_frame(df) is df

    def test_dict_coerced_to_dataframe(self):
        result = _coerce_frame({"a": [1, 2], "b": [3.0, 4.0]})
        assert isinstance(result, pl.DataFrame)
        assert result.columns == ["a", "b"]
        assert result.height == 2

    def test_unsupported_type_raises_value_error(self):
        with pytest.raises(ValueError, match="cannot coerce"):
            _coerce_frame([[1, 2], [3, 4]])

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="cannot coerce"):
            _coerce_frame(None)


class TestSerializeFrame:
    def test_round_trips_to_column_dict(self):
        df = pl.DataFrame({"x": [1, 2], "y": [10, 20]})
        assert _serialize_frame(df) == {"x": [1, 2], "y": [10, 20]}

    def test_empty_frame(self):
        assert _serialize_frame(pl.DataFrame({"x": []})) == {"x": []}


class TestPolarsFrameAnnotated:
    def test_model_accepts_dict(self):
        m = FrameModel(data={"a": [1, 2]})
        assert isinstance(m.data, pl.DataFrame)
        assert m.data["a"].to_list() == [1, 2]

    def test_model_accepts_dataframe(self):
        df = pl.DataFrame({"a": [1]})
        assert FrameModel(data=df).data is df

    def test_model_dump_serializes_to_dict(self):
        m = FrameModel(data={"a": [1, 2]})
        assert m.model_dump() == {"data": {"a": [1, 2]}}

    def test_model_dump_json_round_trip(self):
        m = FrameModel(data={"a": [1, 2]})
        assert m.model_dump_json() == '{"data":{"a":[1,2]}}'

    def test_invalid_payload_fails_validation(self):
        with pytest.raises(Exception):
            FrameModel(data=42)
