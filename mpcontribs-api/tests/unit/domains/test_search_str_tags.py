"""Fuzz the ``SearchStr`` normalizer behind ``tags`` (and the other places it is reused).

``tags`` is ``list[SearchStr]`` on ``ProjectIn`` / ``ProjectOut`` / ``ProjectPatch`` and on every
``ProjectFilter`` operator (``tags`` / ``tags__in`` / ``tags__contains``); ``SearchStr`` also backs
other fields such as ``ProjectGroupFilter.name``. ``SearchStr`` runs ``_nfkc_casefold`` — NFKC
compatibility fold, whitespace strip, then casefold — so a stored tag and a query tag always
collapse to the same bytes. These tests hit the tricky unicode edges and prove the normalizer is
applied identically wherever it is declared.

All non-ASCII codepoints use ``\\u`` escapes so the source is unambiguous byte-for-byte.
"""

import random

import pytest
from pydantic import TypeAdapter

from mpcontribs_api.domains._shared.types import SearchStr
from mpcontribs_api.domains.project_groups.models import ProjectGroupFilter
from mpcontribs_api.domains.projects.models import ProjectFilter, ProjectIn, ProjectPatch

_search = TypeAdapter(SearchStr)


# (id, raw, expected) — each row targets a distinct edge of NFKC + strip + casefold.
_CASES = [
    ("ascii_casefold", "BandGap", "bandgap"),
    ("hyphen_preserved", "Band-Gap", "band-gap"),  # SearchStr does not strip punctuation
    ("eszett_grows_length", "Straße", "strasse"),  # U+00DF casefolds to "ss" (grows length)
    ("greek_final_sigma", "ΟΔΟΣ", "οδοσ"),  # Σ -> σ (not ς)
    ("ligature_fi", "ﬁle", "file"),  # NFKC decomposes the ﬁ ligature
    ("micro_sign_to_mu", "µ", "μ"),  # MICRO SIGN -> GREEK SMALL LETTER MU
    ("kelvin_sign", "K", "k"),  # KELVIN SIGN -> latin k
    ("fullwidth_to_ascii", "ＡＢ", "ab"),  # fullwidth A B -> ascii
    ("superscript_digit", "m²", "m2"),  # m² -> m2
    ("combining_composes", "é", "é"),  # e + COMBINING ACUTE -> precomposed é
    ("roman_numeral", "Ⅷ", "viii"),  # ROMAN NUMERAL EIGHT -> viii
    ("nbsp_trimmed", " tag ", "tag"),  # NBSP folds to space, then strip
    ("mixed_whitespace_trimmed", "  Tag\n", "tag"),
    ("turkish_dotted_I", "İ", "i̇"),  # İ casefolds to i + COMBINING DOT ABOVE
    ("empty_after_strip", "   ", ""),  # no min length: whitespace-only -> ""
]


@pytest.mark.parametrize("raw,expected", [(r, e) for _, r, e in _CASES], ids=[i for i, _, _ in _CASES])
def test_searchstr_normalization(raw, expected):
    out = _search.validate_python(raw)
    assert out == expected
    # every realistic tag must be a stable key: re-folding it changes nothing
    assert _search.validate_python(out) == out


def test_searchstr_fuzz_output_is_stripped_and_casefolded():
    """Whatever the input's unicode form, the output is always trimmed and fully casefolded.

    These are the invariants that hold universally. Idempotency does *not* hold for every input --
    see ``test_searchstr_casefold_expansion_breaks_idempotency`` -- so it is asserted only for the
    realistic cases above, not fuzzed here.

    Seeded so the run is deterministic. Draws from ranges that break naive normalizers (latin-1
    supplement, combining marks, greek, fullwidth, ligatures, roman numerals, and whitespace).
    """
    rng = random.Random(1729)
    pool = (
        [chr(c) for c in range(0x20, 0x7F)]  # ascii printable
        + [chr(c) for c in range(0xA0, 0x100)]  # latin-1 supplement (µ, ß, é, NBSP, ...)
        + [chr(c) for c in range(0x300, 0x370)]  # combining marks
        + [chr(c) for c in range(0x391, 0x3CA)]  # greek letters
        + [chr(c) for c in range(0xFF01, 0xFF5F)]  # fullwidth forms
        + [chr(c) for c in range(0xFB00, 0xFB07)]  # latin ligatures
        + [chr(c) for c in range(0x2160, 0x2180)]  # roman numerals
        + ["\t", "\n", "\r", "\x20", " ", " "]  # tab/nl/cr/space/NBSP/em-space
    )
    for _ in range(2000):
        raw = "".join(rng.choice(pool) for _ in range(rng.randint(0, 8)))
        out = _search.validate_python(raw)
        assert out == out.strip(), f"leaked surrounding whitespace for {raw!r}"
        assert out == out.casefold(), f"not casefold-stable for {raw!r}"


# ligature + uppercase + trailing NBSP -> "file": exercises fold, casefold, and trim at once.
_MESSY_TAG = "  ﬁLE "

_TAG_FIELD_EXTRACTORS = [
    (
        "project_in_tags",
        lambda t: ProjectIn(
            id="proj-x",
            title="title-x",
            authors="a",
            description="d",
            owner="google:a@b.com",
            unique_identifiers=True,
            tags=[t],
        ).tags,
    ),
    ("project_patch_tags", lambda t: ProjectPatch(tags=[t]).tags),
    ("filter_tags", lambda t: ProjectFilter(tags=[t]).tags),
    ("filter_tags__in", lambda t: ProjectFilter(tags__in=[t]).tags__in),
    ("filter_tags__contains", lambda t: ProjectFilter(tags__contains=[t]).tags__contains),
    # "etc.": the same SearchStr normalizer, reused on a non-tag list field on another model.
    ("project_group_filter_name__in", lambda t: ProjectGroupFilter(name__in=[t]).name__in),
]


@pytest.mark.parametrize(
    "extract", [e for _, e in _TAG_FIELD_EXTRACTORS], ids=[i for i, _ in _TAG_FIELD_EXTRACTORS]
)
def test_searchstr_normalized_across_models(extract):
    assert extract(_MESSY_TAG) == ["file"]


@pytest.mark.xfail(
    strict=True,
    reason="_nfkc_casefold is not idempotent when casefold expands a char sitting before a combining mark",
)
def test_searchstr_casefold_expansion_breaks_idempotency():
    """Documents a real edge: a casefold-expanding char (ß -> ss) followed by a combining mark.

    NFKC runs before casefold, so ``ß`` + combining circumflex stays decomposed through the first
    fold (-> ``ss`` + circumflex). Re-folding then NFKC-composes ``s`` + circumflex into ``ŝ``, so
    the value is not stable under a second pass. Because ``ProjectOut.tags`` is also
    ``list[SearchStr]``, a stored tag re-normalizes on read and can round-trip to a different
    string. xfail(strict) so this flips to a failure the moment the normalizer is made idempotent
    (e.g. a trailing NFKC pass after casefold).
    """
    once = _search.validate_python("ß̂")  # eszett + COMBINING CIRCUMFLEX ACCENT
    assert _search.validate_python(once) == once
