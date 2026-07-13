import pytest
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.exceptions import ValidationError as AppValidationError
from mpcontribs_api.domains._shared.types import (
    DisplayStr,
    NFKCStr,
    PrefixedEmail,
    SearchStr,
    ShortStr,
    _validate_prefixed_email,
    nfc_normalize,
    nfkc_normalize,
)

# Unicode fixtures used across the normalization tests.
OHM_SIGN = "Ω"  # U+2126, NFC-folds onto the Greek capital omega
GREEK_OMEGA = "Ω"  # U+03A9
MICRO_SIGN = "µ"  # U+00B5, NFKC-folds onto the Greek small mu (NFC leaves it alone)
GREEK_MU = "μ"  # U+03BC
FI_LIGATURE = "ﬁ"  # U+FB01, NFKC-folds to "fi"


class ShortStrModel(BaseModel):
    value: ShortStr


class PrefixedEmailModel(BaseModel):
    email: PrefixedEmail


class NormModel(BaseModel):
    nfc: DisplayStr | None = None
    nfkc: NFKCStr | None = None
    search: SearchStr | None = None


class TestUnicodeNormalization:
    def test_nfc_folds_ohm_sign_onto_omega(self):
        assert nfc_normalize(OHM_SIGN) == GREEK_OMEGA

    def test_nfc_is_noop_on_ascii(self):
        assert nfc_normalize("bandgap") == "bandgap"

    def test_nfc_does_not_fold_micro_sign(self):
        # NFC is canonical-only: the compatibility micro/mu pair stays distinct (that needs NFKC).
        assert nfc_normalize(MICRO_SIGN) == MICRO_SIGN
        assert nfc_normalize(MICRO_SIGN) != GREEK_MU

    def test_nfkc_folds_micro_sign_onto_mu(self):
        assert nfkc_normalize(MICRO_SIGN) == GREEK_MU

    def test_nfkc_folds_ligature_but_preserves_case(self):
        assert nfkc_normalize(FI_LIGATURE) == "fi"
        assert nfkc_normalize("MyTable") == "MyTable"  # case preserved, unlike SearchStr

    def test_displaystr_applies_nfc(self):
        assert NormModel(nfc=OHM_SIGN).nfc == GREEK_OMEGA

    def test_nfkcstr_applies_nfkc_without_casefold(self):
        model = NormModel(nfkc=MICRO_SIGN + "Table")
        assert model.nfkc == GREEK_MU + "Table"

    def test_searchstr_applies_nfkc_and_casefold(self):
        assert NormModel(search=MICRO_SIGN + "Table").search == GREEK_MU + "table"

    # -- whitespace stripping --------------------------------------------------
    # Heterogeneous inputs (UI, client, raw REST) carry stray whitespace; every normalizer strips it
    # so " Foo " and "Foo" collapse to the same stored/queried form.

    def test_nfc_strips_surrounding_whitespace(self):
        assert nfc_normalize("  Foo  ") == "Foo"

    def test_nfkc_strips_surrounding_whitespace(self):
        assert nfkc_normalize("\tMyTable\n") == "MyTable"

    def test_nfc_strips_unicode_nbsp(self):
        # str.strip() trims all Unicode whitespace incl. NBSP U+00A0, even though NFC does not fold it.
        assert nfc_normalize(" bandgap ") == "bandgap"

    def test_nfkc_folds_nbsp_between_words_but_strips_edges(self):
        # NFKC folds NBSP -> plain space; an interior one survives (folded), edges are trimmed.
        assert nfkc_normalize(" a b ") == "a b"

    def test_displaystr_strips_whitespace(self):
        assert NormModel(nfc="  spaced  ").nfc == "spaced"

    def test_nfkcstr_strips_whitespace(self):
        assert NormModel(nfkc="  MyTable  ").nfkc == "MyTable"

    def test_searchstr_strips_and_casefolds_whitespace(self):
        assert NormModel(search="  MySample  ").search == "mysample"

    def test_normalizers_idempotent_on_whitespace(self):
        # Normalizing an already-normalized value is a no-op (guards accidental double-strip drift).
        for fn in (nfc_normalize, nfkc_normalize):
            once = fn("  Foo Bar  ")
            assert fn(once) == once


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
