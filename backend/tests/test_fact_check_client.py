"""
Unit tests for FactCheckClient.

Covers:
- Successful API call returns a list of FactCheckResult objects
- Timeout returns an empty list
- API error (non-2xx HTTP status) returns an empty list
- No API key returns an empty list gracefully
- Keyword extraction logic
- Response parsing logic
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.fact_check_client import (
    FactCheckClient,
    FactCheckResult,
    _extract_keywords,
    _parse_results,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

SAMPLE_API_RESPONSE = {
    "claims": [
        {
            "text": "The moon is made of cheese",
            "claimReview": [
                {
                    "textualRating": "False",
                    "publisher": {"name": "Snopes", "site": "snopes.com"},
                }
            ],
        },
        {
            "text": "Vaccines cause autism",
            "claimReview": [
                {
                    "textualRating": "Pants on Fire",
                    "publisher": {"name": "PolitiFact", "site": "politifact.com"},
                }
            ],
        },
    ]
}


def _make_mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Build a mock httpx.Response."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data or {}
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=mock_resp,
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# _extract_keywords unit tests
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    def test_returns_top_n_keywords(self):
        text = "climate change global warming temperature rise"
        keywords = _extract_keywords(text, max_keywords=3)
        assert len(keywords) <= 3

    def test_filters_stopwords(self):
        text = "the and or but is are was were"
        keywords = _extract_keywords(text)
        assert keywords == []

    def test_filters_short_tokens(self):
        # Single and two-character tokens should be filtered
        text = "a an it is ok go do"
        keywords = _extract_keywords(text)
        assert keywords == []

    def test_empty_text_returns_empty(self):
        assert _extract_keywords("") == []

    def test_whitespace_only_returns_empty(self):
        assert _extract_keywords("   \t\n  ") == []

    def test_returns_meaningful_words(self):
        # All 5 words are meaningful (no stopwords, all > 2 chars).
        # With first-appearance ordering the result is the words in text order.
        text = "president signed executive order immigration policy"
        keywords = _extract_keywords(text, max_keywords=6)
        assert "president" in keywords
        assert "immigration" in keywords
        assert "policy" in keywords

    def test_frequency_ordering(self):
        # "election" appears 3 times, "fraud" appears 2 times
        text = "election fraud election results election integrity fraud claims"
        keywords = _extract_keywords(text, max_keywords=2)
        assert keywords[0] == "election"
        assert keywords[1] == "fraud"

    def test_punctuation_stripped(self):
        text = "Hello, world! This is a test."
        keywords = _extract_keywords(text)
        # Should not contain punctuation
        for kw in keywords:
            assert "," not in kw
            assert "!" not in kw
            assert "." not in kw


# ---------------------------------------------------------------------------
# _parse_results unit tests
# ---------------------------------------------------------------------------


class TestParseResults:
    def test_parses_valid_response(self):
        results = _parse_results(SAMPLE_API_RESPONSE)
        assert len(results) == 2
        assert results[0].claim == "The moon is made of cheese"
        assert results[0].rating == "False"
        assert results[0].source == "Snopes"

    def test_empty_claims_returns_empty_list(self):
        assert _parse_results({}) == []
        assert _parse_results({"claims": []}) == []

    def test_multiple_reviews_per_claim(self):
        data = {
            "claims": [
                {
                    "text": "Some claim",
                    "claimReview": [
                        {"textualRating": "False", "publisher": {"name": "Source A"}},
                        {"textualRating": "Misleading", "publisher": {"name": "Source B"}},
                    ],
                }
            ]
        }
        results = _parse_results(data)
        assert len(results) == 2
        assert results[0].source == "Source A"
        assert results[1].source == "Source B"

    def test_missing_publisher_name_falls_back_to_site(self):
        data = {
            "claims": [
                {
                    "text": "A claim",
                    "claimReview": [
                        {"textualRating": "True", "publisher": {"site": "example.com"}},
                    ],
                }
            ]
        }
        results = _parse_results(data)
        assert results[0].source == "example.com"

    def test_result_is_dataclass(self):
        results = _parse_results(SAMPLE_API_RESPONSE)
        for r in results:
            assert isinstance(r, FactCheckResult)
            assert hasattr(r, "claim")
            assert hasattr(r, "rating")
            assert hasattr(r, "source")


# ---------------------------------------------------------------------------
# FactCheckClient — no API key
# ---------------------------------------------------------------------------


class TestFactCheckClientNoApiKey:
    def test_sync_no_api_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("FACT_CHECK_API_KEY", raising=False)
        client = FactCheckClient(api_key="")
        results = client.check_sync("Some important news article about elections")
        assert results == []

    @pytest.mark.asyncio
    async def test_async_no_api_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("FACT_CHECK_API_KEY", raising=False)
        client = FactCheckClient(api_key="")
        results = await client.check("Some important news article about elections")
        assert results == []

    def test_sync_env_var_not_set_returns_empty(self, monkeypatch):
        monkeypatch.delenv("FACT_CHECK_API_KEY", raising=False)
        client = FactCheckClient()
        results = client.check_sync("Some important news article about elections")
        assert results == []


# ---------------------------------------------------------------------------
# FactCheckClient — successful API call
# ---------------------------------------------------------------------------


class TestFactCheckClientSuccess:
    def test_sync_successful_call_returns_results(self, monkeypatch):
        mock_resp = _make_mock_response(200, SAMPLE_API_RESPONSE)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key-123")
            results = client.check_sync(
                "The moon is made of cheese and vaccines cause autism",
                correlation_id="req-001",
            )

        assert len(results) == 2
        assert all(isinstance(r, FactCheckResult) for r in results)
        assert results[0].claim == "The moon is made of cheese"
        assert results[0].rating == "False"
        assert results[0].source == "Snopes"

    @pytest.mark.asyncio
    async def test_async_successful_call_returns_results(self):
        mock_resp = _make_mock_response(200, SAMPLE_API_RESPONSE)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key-123")
            results = await client.check(
                "The moon is made of cheese and vaccines cause autism",
                correlation_id="req-001",
            )

        assert len(results) == 2
        assert results[1].rating == "Pants on Fire"
        assert results[1].source == "PolitiFact"

    def test_sync_passes_api_key_in_request(self, monkeypatch):
        mock_resp = _make_mock_response(200, {"claims": []})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="my-secret-key")
            client.check_sync("election fraud claims investigation")

            call_kwargs = mock_client.get.call_args
            assert call_kwargs.kwargs["params"]["key"] == "my-secret-key"

    def test_sync_empty_api_response_returns_empty_list(self):
        mock_resp = _make_mock_response(200, {"claims": []})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key")
            results = client.check_sync("election fraud claims investigation")

        assert results == []


# ---------------------------------------------------------------------------
# FactCheckClient — timeout
# ---------------------------------------------------------------------------


class TestFactCheckClientTimeout:
    def test_sync_timeout_returns_empty_list(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key")
            results = client.check_sync(
                "election fraud claims investigation",
                correlation_id="req-timeout",
            )

        assert results == []

    @pytest.mark.asyncio
    async def test_async_timeout_returns_empty_list(self):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key")
            results = await client.check(
                "election fraud claims investigation",
                correlation_id="req-timeout",
            )

        assert results == []

    def test_sync_timeout_logs_warning(self, caplog):
        import logging

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key")
            with caplog.at_level(logging.WARNING, logger="services.fact_check_client"):
                client.check_sync("election fraud claims", correlation_id="req-log-test")

        assert any("timed out" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------
# FactCheckClient — API error (non-2xx)
# ---------------------------------------------------------------------------


class TestFactCheckClientApiError:
    def test_sync_http_error_returns_empty_list(self):
        mock_resp = _make_mock_response(403)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="bad-key")
            results = client.check_sync(
                "election fraud claims investigation",
                correlation_id="req-error",
            )

        assert results == []

    @pytest.mark.asyncio
    async def test_async_http_error_returns_empty_list(self):
        mock_resp = _make_mock_response(500)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key")
            results = await client.check(
                "election fraud claims investigation",
                correlation_id="req-error",
            )

        assert results == []

    def test_sync_http_error_logs_error(self, caplog):
        import logging

        mock_resp = _make_mock_response(429)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key")
            with caplog.at_level(logging.ERROR, logger="services.fact_check_client"):
                client.check_sync("election fraud claims", correlation_id="req-log-err")

        assert any("429" in record.message for record in caplog.records)

    def test_sync_unexpected_exception_returns_empty_list(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = RuntimeError("unexpected network failure")
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key")
            results = client.check_sync("election fraud claims investigation")

        assert results == []


# ---------------------------------------------------------------------------
# FactCheckClient — correlation ID propagation
# ---------------------------------------------------------------------------


class TestFactCheckClientCorrelationId:
    def test_instance_correlation_id_used_in_logs(self, caplog):
        import logging

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key", correlation_id="instance-cid-xyz")
            with caplog.at_level(logging.WARNING, logger="services.fact_check_client"):
                client.check_sync("election fraud claims investigation")

        assert any("instance-cid-xyz" in record.message for record in caplog.records)

    def test_call_level_correlation_id_overrides_instance(self, caplog):
        import logging

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            client = FactCheckClient(api_key="test-key", correlation_id="instance-cid")
            with caplog.at_level(logging.WARNING, logger="services.fact_check_client"):
                client.check_sync(
                    "election fraud claims investigation",
                    correlation_id="call-level-cid",
                )

        assert any("call-level-cid" in record.message for record in caplog.records)
