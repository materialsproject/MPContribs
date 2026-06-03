import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from src.mpcontribs_api.exceptions import ValidationError as AppValidationError
from src.mpcontribs_api.types import PrefixedEmail, ShortStr, _validate_prefixed_email


class ShortStrModel(BaseModel):
    value: ShortStr


class PrefixedEmailModel(BaseModel):
    email: PrefixedEmail


class TestShortStr:
    def test_valid_3_chars(self):
        m = ShortStrModel(value="abc")
        assert m.value == "abc"

    def test_valid_30_chars(self):
        m = ShortStrModel(value="a" * 30)
        assert m.value == "a" * 30

    def test_valid_mid_length(self):
        m = ShortStrModel(value="test-project")
        assert m.value == "test-project"

    def test_too_short_raises(self):
        with pytest.raises(PydanticValidationError):
            ShortStrModel(value="ab")

    def test_empty_raises(self):
        with pytest.raises(PydanticValidationError):
            ShortStrModel(value="")

    def test_too_long_raises(self):
        with pytest.raises(PydanticValidationError):
            ShortStrModel(value="a" * 31)

    def test_exactly_31_chars_raises(self):
        with pytest.raises(PydanticValidationError):
            ShortStrModel(value="a" * 31)


class TestValidatePrefixedEmail:
    def test_valid_format(self):
        assert _validate_prefixed_email("google:alice@example.com") == "google:alice@example.com"

    def test_strips_surrounding_whitespace(self):
        assert _validate_prefixed_email("  google:alice@example.com  ") == "google:alice@example.com"

    def test_no_colon_raises(self):
        with pytest.raises(AppValidationError):
            _validate_prefixed_email("googlealice@example.com")

    def test_no_at_sign_raises(self):
        with pytest.raises(AppValidationError):
            _validate_prefixed_email("google:aliceexample.com")

    def test_no_domain_raises(self):
        with pytest.raises(AppValidationError):
            _validate_prefixed_email("google:alice@")

    def test_no_tld_raises(self):
        with pytest.raises(AppValidationError):
            _validate_prefixed_email("google:alice@example")

    def test_empty_provider_raises(self):
        with pytest.raises(AppValidationError):
            _validate_prefixed_email(":alice@example.com")

    def test_empty_name_raises(self):
        with pytest.raises(AppValidationError):
            _validate_prefixed_email("google:@example.com")

    def test_multiple_at_signs_raises(self):
        with pytest.raises(AppValidationError):
            _validate_prefixed_email("google:alice@@example.com")

    def test_multiple_colons_raises(self):
        # The regex requires no colon in provider or local part
        with pytest.raises(AppValidationError):
            _validate_prefixed_email("goo:gle:alice@example.com")


class TestPrefixedEmailModel:
    def test_valid_email(self):
        m = PrefixedEmailModel(email="github:bob@github.com")
        assert m.email == "github:bob@github.com"

    def test_invalid_email_raises_app_validation_error(self):
        # BeforeValidator raises AppValidationError; Pydantic does not wrap
        # non-standard exceptions (ValueError/TypeError/AssertionError) from validators.
        with pytest.raises(AppValidationError):
            PrefixedEmailModel(email="not-an-email")

    def test_whitespace_stripped(self):
        m = PrefixedEmailModel(email="  orcid:12345@orcid.org  ")
        assert m.email == "orcid:12345@orcid.org"
