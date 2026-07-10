from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.filters import _normalize_query_values
from mpcontribs_api.domains.contributions.models import ContributionFilter
from mpcontribs_api.domains.tables.models import TableFilter

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
