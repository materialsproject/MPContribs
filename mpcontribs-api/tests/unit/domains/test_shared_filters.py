from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.filters import _normalize_query_values
from mpcontribs_api.domains._shared.types import _nfkc_casefold
from mpcontribs_api.domains.contributions.models import ContributionFilter
from mpcontribs_api.domains.tables.models import TableFilter

MICRO_SIGN = "µ"  # NFKC-folds onto the Greek small mu; needs the SearchStr fold, not the NFC pass
GREEK_MU = "μ"

# OHM SIGN (U+2126) NFC-folds onto the Greek capital omega (U+03A9); the two are distinct codepoints.
OHM_SIGN = "Ω"
GREEK_OMEGA = "Ω"


def _flatten(conditions):
    """Merge the (condition, options) pairs from _get_filter_conditions into one dict."""
    merged = {}
    for condition, _options in conditions:
        merged.update(condition)
    return merged


class TestNormalizeQueryValues:
    def test_bare_string_folded(self):
        assert _normalize_query_values(OHM_SIGN) == GREEK_OMEGA

    def test_ascii_unchanged(self):
        assert _normalize_query_values("bandgap") == "bandgap"

    def test_operator_dict_value_folded(self):
        # e.g. the {"$ne": value} shape fastapi-filter builds for __neq.
        assert _normalize_query_values({"$ne": OHM_SIGN}) == {"$ne": GREEK_OMEGA}

    def test_regex_string_folded_inside_ilike_shape(self):
        out = _normalize_query_values({"$regex": f".*{OHM_SIGN}.*", "$options": "i"})
        assert out == {"$regex": f".*{GREEK_OMEGA}.*", "$options": "i"}

    def test_list_values_folded(self):
        assert _normalize_query_values({"$in": [OHM_SIGN, "eV"]}) == {"$in": [GREEK_OMEGA, "eV"]}

    def test_non_string_untouched(self):
        oid = PydanticObjectId()
        assert _normalize_query_values(oid) is oid


class TestBaseFilterQueryNormalization:
    def test_generic_pass_folds_plain_str_field(self):
        # ContributionFilter.formula is a plain str field, so folding here comes from the BaseFilter
        # NFC pass rather than a field-level validator.
        conditions = _flatten(ContributionFilter(formula=OHM_SIGN)._get_filter_conditions())
        assert conditions["formula"] == GREEK_OMEGA

    def test_id_still_remapped_to_underscore_id(self):
        oid = PydanticObjectId()
        conditions = _flatten(ContributionFilter(id=oid)._get_filter_conditions())
        assert "_id" in conditions
        assert "id" not in conditions

    def test_component_name_lookup_folded(self):
        conditions = _flatten(TableFilter(name=OHM_SIGN)._get_filter_conditions())
        assert conditions["name"] == GREEK_OMEGA

    def test_component_name_ilike_regex_folded(self):
        conditions = _flatten(TableFilter(name__ilike=OHM_SIGN)._get_filter_conditions())
        assert conditions["name"]["$regex"] == f".*{GREEK_OMEGA}.*"


class TestIdentifierFilterMatchesStoredForm:
    """``Contribution.identifier`` stores as ``SearchStr`` (NFKC + casefold); the filter fields must
    fold query values identically or exact/__in/__neq lookups silently miss.

    See ``ContributionFilter.identifier``. Regression guard for the store/query mismatch where the
    filter was a plain ``str`` and only got BaseFilter's NFC pass (no casefold, no NFKC fold).
    """

    def test_exact_identifier_casefolded_to_match_store(self):
        conditions = _flatten(ContributionFilter(identifier="MySample")._get_filter_conditions())
        assert conditions["identifier"] == "mysample"
        assert conditions["identifier"] == _nfkc_casefold("MySample")

    def test_exact_identifier_nfkc_folded_to_match_store(self):
        # The MICRO SIGN needs NFKC folding (the NFC catch-all alone would leave it as-is).
        conditions = _flatten(ContributionFilter(identifier=MICRO_SIGN + "Sample")._get_filter_conditions())
        assert conditions["identifier"] == GREEK_MU + "sample"

    def test_identifier_in_list_casefolded(self):
        conditions = _flatten(ContributionFilter(identifier__in=["ABC", "DeF"])._get_filter_conditions())
        assert conditions["identifier"]["$in"] == ["abc", "def"]

    def test_identifier_neq_casefolded(self):
        conditions = _flatten(ContributionFilter(identifier__neq="SkipMe")._get_filter_conditions())
        assert conditions["identifier"]["$ne"] == "skipme"

    def test_identifier_ilike_casefolded_regex(self):
        conditions = _flatten(ContributionFilter(identifier__ilike="Frag")._get_filter_conditions())
        assert conditions["identifier"]["$regex"] == ".*frag.*"

    def test_identifier_whitespace_stripped(self):
        conditions = _flatten(ContributionFilter(identifier="  Padded  ")._get_filter_conditions())
        assert conditions["identifier"] == "padded"
