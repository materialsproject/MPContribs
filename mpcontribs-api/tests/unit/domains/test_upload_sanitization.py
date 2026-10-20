"""Unit tests for upload key-segment sanitization.

A segment reaches an S3 key verbatim, so :func:`sanitize_segment` must reject every form of
traversal/separator/control character rather than silently rewriting it — this is the guard the
original backslash-in-key footgun motivated.
"""

import pytest

from mpcontribs_api.domains.uploads.models import ManifestFile
from mpcontribs_api.domains.uploads.sanitization import file_extension, sanitize_segment
from mpcontribs_api.exceptions import ValidationError


class TestSanitizeSegment:
    def test_accepts_plain_name(self):
        assert sanitize_segment("contributions.csv", field="filename") == "contributions.csv"

    def test_nfkc_normalizes(self):
        # Full-width chars fold to ASCII (NFKC), case preserved — a safe, stable rewrite.
        assert sanitize_segment("ＡＢ.csv", field="filename") == "AB.csv"

    @pytest.mark.parametrize(
        "bad",
        [
            "..",
            ".",
            "a/b.csv",  # embedded separator
            "a\\b.csv",  # backslash (the original footgun)
            "/abs.csv",  # absolute
            "../escape.csv",  # traversal
            "  ",  # empty after strip
            "a\x00b.csv",  # NUL / control char
            "a\nb.csv",  # newline
        ],
    )
    def test_rejects_unsafe(self, bad):
        with pytest.raises(ValidationError):
            sanitize_segment(bad, field="filename")

    def test_rejects_overlong(self):
        with pytest.raises(ValidationError):
            sanitize_segment("x" * 500 + ".csv", field="filename")


class TestFileExtension:
    def test_lowercased(self):
        assert file_extension("Si.CIF") == "cif"

    def test_none(self):
        assert file_extension("noext") == ""


class TestManifestFileSanitizes:
    def test_backslash_filename_rejected_at_manifest(self):
        # The manifest model runs sanitization, so a bad filename is a 422 at initiate, never a key.
        with pytest.raises(ValidationError):
            ManifestFile(
                filename="a\\b.csv", role="contributions", format="csv", content_type="text/csv", size=10
            )

    def test_extension_must_match_format(self):
        with pytest.raises(ValidationError):
            ManifestFile(filename="data.csv", role="project", format="json", content_type="application/json", size=10)
