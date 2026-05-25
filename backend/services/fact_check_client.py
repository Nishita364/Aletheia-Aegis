"""
Fact-Check API Client.

Wraps the Google Fact Check Explorer API to cross-reference claims extracted
from submission text against independently verified fact-checks.

API endpoint: https://factchecktools.googleapis.com/v1alpha1/claims:search

Usage:
    client = FactCheckClient()
    results = await client.check(text="Some news article text...", correlation_id="req-123")
    # Returns a list of FactCheckResult objects, or [] on timeout/error.

    # Synchronous usage:
    client = FactCheckClient()
    results = client.check_sync(text="Some news article text...")

Environment:
    FACT_CHECK_API_KEY — Google Fact Check Explorer API key.
"""

from __future__ import annotations

import logging
import os
import re
import string
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Google Fact Check Explorer API endpoint
_FACT_CHECK_API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

# Timeout for API calls (seconds)
_TIMEOUT_SECONDS = 5.0

# Common English stopwords for keyword extraction
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "not", "no", "nor",
    "so", "yet", "both", "either", "neither", "each", "few", "more", "most",
    "other", "some", "such", "than", "too", "very", "just", "that", "this",
    "these", "those", "it", "its", "as", "if", "then", "than", "when",
    "where", "who", "which", "what", "how", "all", "any", "both", "each",
    "he", "she", "they", "we", "you", "i", "me", "him", "her", "us", "them",
    "my", "your", "his", "our", "their", "about", "after", "before", "into",
    "through", "during", "up", "down", "out", "off", "over", "under",
    "again", "further", "once", "here", "there", "while", "although",
    "because", "since", "until", "unless", "also", "only", "own", "same",
    "s", "t", "re", "ve", "ll", "d", "m",
})

# Maximum number of keywords to use for the query
_MAX_KEYWORDS = 5


@dataclass
class FactCheckResult:
    """A single fact-check result from the Google Fact Check Explorer API."""

    claim: str
    rating: str
    source: str


def _extract_keywords(text: str, max_keywords: int = _MAX_KEYWORDS) -> list[str]:
    """Extract key terms from text using simple frequency-based keyword extraction.

    Removes punctuation, lowercases, filters stopwords and short tokens,
    then returns the top N most frequent remaining words.

    Parameters
    ----------
    text:
        The input text to extract keywords from.
    max_keywords:
        Maximum number of keywords to return.

    Returns
    -------
    list[str]
        A list of up to *max_keywords* keywords, ordered by frequency descending.
    """
    # Strip punctuation and lowercase
    translator = str.maketrans(string.punctuation, " " * len(string.punctuation))
    cleaned = text.translate(translator).lower()

    # Tokenise on whitespace
    tokens = cleaned.split()

    # Filter stopwords and short tokens (≤ 2 chars)
    meaningful = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    if not meaningful:
        return []

    # Count frequencies
    freq: dict[str, int] = {}
    for token in meaningful:
        freq[token] = freq.get(token, 0) + 1

    # Sort by frequency descending, then alphabetically for determinism
    sorted_tokens = sorted(freq.keys(), key=lambda t: (-freq[t], t))

    return sorted_tokens[:max_keywords]


def _parse_results(data: dict) -> list[FactCheckResult]:
    """Parse the JSON response from the Fact Check Explorer API.

    Parameters
    ----------
    data:
        Parsed JSON response body from the API.

    Returns
    -------
    list[FactCheckResult]
        Parsed fact-check results; empty list if no claims found.
    """
    results: list[FactCheckResult] = []
    claims = data.get("claims", [])
    for claim_obj in claims:
        claim_text = claim_obj.get("text", "")
        reviews = claim_obj.get("claimReview", [])
        for review in reviews:
            rating = review.get("textualRating", "")
            publisher = review.get("publisher", {})
            source = publisher.get("name", publisher.get("site", ""))
            if claim_text or rating or source:
                results.append(FactCheckResult(
                    claim=claim_text,
                    rating=rating,
                    source=source,
                ))
    return results


class FactCheckClient:
    """Client for the Google Fact Check Explorer API.

    Extracts key terms from submission text and queries the API to find
    matching fact-checks. Returns an empty list on timeout or any error,
    logging the failure with the provided correlation ID.

    Parameters
    ----------
    api_key:
        Google Fact Check Explorer API key. If not provided, reads from
        the ``FACT_CHECK_API_KEY`` environment variable.
    correlation_id:
        Optional request correlation ID used in log messages for traceability.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("FACT_CHECK_API_KEY", "")
        self._correlation_id = correlation_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(
        self,
        text: str,
        correlation_id: Optional[str] = None,
    ) -> list[FactCheckResult]:
        """Asynchronously query the Fact Check Explorer API.

        Extracts keywords from *text*, queries the API, and returns a list
        of :class:`FactCheckResult` objects. Returns an empty list if the
        API key is missing, the request times out, or any error occurs.

        Parameters
        ----------
        text:
            The submission text to extract claims from.
        correlation_id:
            Optional correlation ID for this specific call (overrides the
            instance-level correlation ID for this call).

        Returns
        -------
        list[FactCheckResult]
            Matching fact-check results, or ``[]`` on timeout/error.
        """
        cid = correlation_id or self._correlation_id

        if not self._api_key:
            logger.warning(
                "FactCheckClient: no API key configured; skipping fact-check "
                "[correlation_id=%s]",
                cid,
            )
            return []

        keywords = _extract_keywords(text)
        if not keywords:
            logger.debug(
                "FactCheckClient: no keywords extracted from text "
                "[correlation_id=%s]",
                cid,
            )
            return []

        query = " ".join(keywords)

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    _FACT_CHECK_API_URL,
                    params={"query": query, "key": self._api_key},
                )
                response.raise_for_status()
                data = response.json()
                return _parse_results(data)

        except httpx.TimeoutException:
            logger.warning(
                "FactCheckClient: request timed out after %.1fs "
                "[correlation_id=%s, query=%r]",
                _TIMEOUT_SECONDS,
                cid,
                query,
            )
            return []

        except httpx.HTTPStatusError as exc:
            logger.error(
                "FactCheckClient: API returned HTTP %d "
                "[correlation_id=%s, query=%r]",
                exc.response.status_code,
                cid,
                query,
            )
            return []

        except Exception:
            logger.exception(
                "FactCheckClient: unexpected error during fact-check "
                "[correlation_id=%s, query=%r]",
                cid,
                query,
            )
            return []

    def check_sync(
        self,
        text: str,
        correlation_id: Optional[str] = None,
    ) -> list[FactCheckResult]:
        """Synchronous wrapper around :meth:`check`.

        Useful in non-async contexts (e.g. tests, scripts). Internally
        creates a temporary ``httpx.Client`` with the same timeout.

        Parameters
        ----------
        text:
            The submission text to extract claims from.
        correlation_id:
            Optional correlation ID for this specific call.

        Returns
        -------
        list[FactCheckResult]
            Matching fact-check results, or ``[]`` on timeout/error.
        """
        cid = correlation_id or self._correlation_id

        if not self._api_key:
            logger.warning(
                "FactCheckClient: no API key configured; skipping fact-check "
                "[correlation_id=%s]",
                cid,
            )
            return []

        keywords = _extract_keywords(text)
        if not keywords:
            logger.debug(
                "FactCheckClient: no keywords extracted from text "
                "[correlation_id=%s]",
                cid,
            )
            return []

        query = " ".join(keywords)

        try:
            with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
                response = client.get(
                    _FACT_CHECK_API_URL,
                    params={"query": query, "key": self._api_key},
                )
                response.raise_for_status()
                data = response.json()
                return _parse_results(data)

        except httpx.TimeoutException:
            logger.warning(
                "FactCheckClient: request timed out after %.1fs "
                "[correlation_id=%s, query=%r]",
                _TIMEOUT_SECONDS,
                cid,
                query,
            )
            return []

        except httpx.HTTPStatusError as exc:
            logger.error(
                "FactCheckClient: API returned HTTP %d "
                "[correlation_id=%s, query=%r]",
                exc.response.status_code,
                cid,
                query,
            )
            return []

        except Exception:
            logger.exception(
                "FactCheckClient: unexpected error during fact-check "
                "[correlation_id=%s, query=%r]",
                cid,
                query,
            )
            return []
