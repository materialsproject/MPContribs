import base64

import pytest
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.pagination import (
    CursorParams,
    Page,
    decode_cursor,
    encode_cursor,
)


class TestEncodeCursor:
    def test_roundtrip(self):
        original = "some-mongo-id-abc123"
        assert decode_cursor(encode_cursor(original)) == original

    def test_returns_string(self):
        result = encode_cursor("abc")
        assert isinstance(result, str)

    def test_uses_urlsafe_base64(self):
        # urlsafe_b64encode uses - and _ instead of + and /
        result = encode_cursor("test-id")
        decoded_bytes = base64.urlsafe_b64decode(result.encode())
        assert decoded_bytes.decode() == "test-id"

    def test_empty_string(self):
        assert decode_cursor(encode_cursor("")) == ""

    def test_encodes_unicode(self):
        original = "projet-données"
        assert decode_cursor(encode_cursor(original)) == original


class TestDecodeCursor:
    def test_valid_cursor(self):
        encoded = base64.urlsafe_b64encode(b"abc123").decode()
        assert decode_cursor(encoded) == "abc123"

    def test_invalid_base64_raises_value_error(self):
        with pytest.raises(ValueError, match="malformed cursor"):
            decode_cursor("!!!not-valid-base64!!!")

    def test_non_utf8_bytes_raises_value_error(self):
        # Encode raw bytes that aren't valid UTF-8
        bad = base64.urlsafe_b64encode(b"\xff\xfe").decode()
        with pytest.raises(ValueError, match="malformed cursor"):
            decode_cursor(bad)


class TestCursorParams:
    def test_defaults(self):
        params = CursorParams()
        assert params.cursor is None
        assert params.limit == 20

    def test_cursor_set(self):
        params = CursorParams(cursor="abc123")
        assert params.cursor == "abc123"

    def test_limit_minimum(self):
        params = CursorParams(limit=1)
        assert params.limit == 1

    def test_limit_maximum(self):
        params = CursorParams(limit=100)
        assert params.limit == 100

    def test_limit_below_minimum_raises(self):
        with pytest.raises(PydanticValidationError):
            CursorParams(limit=0)

    def test_limit_above_maximum_raises(self):
        with pytest.raises(PydanticValidationError):
            CursorParams(limit=101)

    def test_custom_limit(self):
        params = CursorParams(limit=50)
        assert params.limit == 50


class TestPage:
    def test_items_and_no_next_cursor(self):
        page: Page[str] = Page(items=["a", "b", "c"])
        assert page.items == ["a", "b", "c"]
        assert page.next_cursor is None

    def test_with_next_cursor(self):
        cursor = encode_cursor("last-id")
        page: Page[str] = Page(items=["a"], next_cursor=cursor)
        assert page.next_cursor == cursor

    def test_empty_items(self):
        page: Page[str] = Page(items=[])
        assert page.items == []
        assert page.next_cursor is None

    def test_generic_item_types(self):
        page: Page[int] = Page(items=[1, 2, 3])
        assert page.items == [1, 2, 3]
