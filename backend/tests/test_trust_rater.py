"""
Unit tests for backend/services/trust_rater.py

Covers:
- Known High domain returns "High"
- Known Low domain returns "Low"
- Unknown domain returns "Unknown"
- Full URL is handled correctly (domain extracted)
- www. prefix is stripped
- Case-insensitive lookup
- reload() picks up changes written to disk
- Missing / malformed JSON file degrades gracefully
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from services.trust_rater import TrustRater, _extract_domain, _strip_www


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_rater(data: dict) -> tuple[TrustRater, Path]:
    """Write *data* to a temp JSON file and return a TrustRater + the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, tmp)
    tmp.close()
    path = Path(tmp.name)
    return TrustRater(domains_path=path), path


SAMPLE_DATA = {
    "high": ["reuters.com", "apnews.com", "bbc.com"],
    "medium": ["cnn.com", "huffpost.com"],
    "low": ["infowars.com", "naturalnews.com"],
}


@pytest.fixture()
def rater_and_path():
    rater, path = _make_rater(SAMPLE_DATA)
    yield rater, path
    path.unlink(missing_ok=True)


@pytest.fixture()
def rater(rater_and_path):
    return rater_and_path[0]


# ---------------------------------------------------------------------------
# Internal helper tests
# ---------------------------------------------------------------------------

class TestExtractDomain:
    def test_bare_domain(self):
        assert _extract_domain("reuters.com") == "reuters.com"

    def test_https_url(self):
        assert _extract_domain("https://reuters.com/article/123") == "reuters.com"

    def test_http_url(self):
        assert _extract_domain("http://infowars.com/page") == "infowars.com"

    def test_strips_whitespace(self):
        assert _extract_domain("  reuters.com  ") == "reuters.com"

    def test_lowercases(self):
        assert _extract_domain("Reuters.COM") == "reuters.com"

    def test_url_with_www(self):
        assert _extract_domain("https://www.bbc.com/news") == "www.bbc.com"


class TestStripWww:
    def test_removes_www(self):
        assert _strip_www("www.reuters.com") == "reuters.com"

    def test_no_www_unchanged(self):
        assert _strip_www("reuters.com") == "reuters.com"

    def test_does_not_strip_partial(self):
        # "wwwexample.com" should NOT be stripped
        assert _strip_www("wwwexample.com") == "wwwexample.com"


# ---------------------------------------------------------------------------
# TrustRater.rate() tests
# ---------------------------------------------------------------------------

class TestRate:
    def test_known_high_domain(self, rater):
        assert rater.rate("reuters.com") == "High"

    def test_known_high_domain_apnews(self, rater):
        assert rater.rate("apnews.com") == "High"

    def test_known_medium_domain(self, rater):
        assert rater.rate("cnn.com") == "Medium"

    def test_known_low_domain(self, rater):
        assert rater.rate("infowars.com") == "Low"

    def test_known_low_domain_naturalnews(self, rater):
        assert rater.rate("naturalnews.com") == "Low"

    def test_unknown_domain_returns_unknown(self, rater):
        assert rater.rate("totally-unknown-blog.xyz") == "Unknown"

    def test_empty_string_returns_unknown(self, rater):
        assert rater.rate("") == "Unknown"

    def test_full_https_url_high(self, rater):
        assert rater.rate("https://reuters.com/article/breaking-news") == "High"

    def test_full_http_url_low(self, rater):
        assert rater.rate("http://infowars.com/conspiracy") == "Low"

    def test_www_prefix_stripped_high(self, rater):
        assert rater.rate("www.reuters.com") == "High"

    def test_www_prefix_in_url_stripped(self, rater):
        assert rater.rate("https://www.bbc.com/news") == "High"

    def test_case_insensitive_domain(self, rater):
        assert rater.rate("Reuters.COM") == "High"

    def test_case_insensitive_url(self, rater):
        assert rater.rate("HTTPS://APNEWS.COM/article") == "High"


# ---------------------------------------------------------------------------
# TrustRater.reload() tests
# ---------------------------------------------------------------------------

class TestReload:
    def test_reload_picks_up_new_domain(self, rater_and_path):
        rater, path = rater_and_path

        # Initially unknown
        assert rater.rate("newsite.com") == "Unknown"

        # Update the file on disk
        updated = {**SAMPLE_DATA, "high": SAMPLE_DATA["high"] + ["newsite.com"]}
        path.write_text(json.dumps(updated), encoding="utf-8")

        # Before reload, still unknown
        assert rater.rate("newsite.com") == "Unknown"

        # After reload, should be High
        rater.reload()
        assert rater.rate("newsite.com") == "High"

    def test_reload_removes_domain(self, rater_and_path):
        rater, path = rater_and_path

        assert rater.rate("reuters.com") == "High"

        # Remove reuters.com from the list
        updated = {
            "high": ["apnews.com"],
            "medium": SAMPLE_DATA["medium"],
            "low": SAMPLE_DATA["low"],
        }
        path.write_text(json.dumps(updated), encoding="utf-8")
        rater.reload()

        assert rater.rate("reuters.com") == "Unknown"

    def test_reload_replaces_rating(self, rater_and_path):
        rater, path = rater_and_path

        assert rater.rate("cnn.com") == "Medium"

        # Move cnn.com to low
        updated = {
            "high": SAMPLE_DATA["high"],
            "medium": [],
            "low": SAMPLE_DATA["low"] + ["cnn.com"],
        }
        path.write_text(json.dumps(updated), encoding="utf-8")
        rater.reload()

        assert rater.rate("cnn.com") == "Low"


# ---------------------------------------------------------------------------
# Graceful degradation tests
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_missing_file_returns_unknown(self):
        rater = TrustRater(domains_path="/nonexistent/path/trust_domains.json")
        assert rater.rate("reuters.com") == "Unknown"

    def test_malformed_json_returns_unknown(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write("{ this is not valid json }")
            path = Path(tmp.name)

        try:
            rater = TrustRater(domains_path=path)
            assert rater.rate("reuters.com") == "Unknown"
        finally:
            path.unlink(missing_ok=True)

    def test_unknown_level_key_is_skipped(self):
        data = {
            "high": ["reuters.com"],
            "trusted": ["someblog.com"],  # unknown key – should be ignored
        }
        rater, path = _make_rater(data)
        try:
            assert rater.rate("reuters.com") == "High"
            assert rater.rate("someblog.com") == "Unknown"
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Default file smoke test
# ---------------------------------------------------------------------------

class TestDefaultFile:
    """Verify the bundled trust_domains.json loads without errors."""

    def test_default_file_loads(self):
        rater = TrustRater()
        # reuters.com is in the bundled High list
        assert rater.rate("reuters.com") == "High"

    def test_default_file_low_domain(self):
        rater = TrustRater()
        assert rater.rate("infowars.com") == "Low"

    def test_default_file_unknown(self):
        rater = TrustRater()
        assert rater.rate("completely-unknown-xyz-12345.com") == "Unknown"
