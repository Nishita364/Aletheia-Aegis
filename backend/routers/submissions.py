"""
POST /api/v1/submissions endpoint.

Accepts a SubmissionRequest (text or URL), runs the full analysis pipeline,
persists the result, and returns a PredictionResponse.

Pipeline steps
--------------
1. Validate SubmissionRequest (Pydantic, 400 on failure).
2. If URL provided, fetch article body with a 10-second timeout (502 on failure).
3. Detect language via LanguageRouter (400 on UnsupportedLanguageError).
4. Call PredictionService via LanguageRouter (504 on asyncio.TimeoutError).
5. Call TrustRater if URL was provided (8.1).
6. Call FactCheckClient (9.1; returns [] on timeout/error).
7. Persist HistoryRecord to HistoryRepository (4.1).
8. Return PredictionResponse.

Requirements: 1.5, 1.6, 1.7, 2.1, 2.2, 8.1, 9.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.db.repository import HistoryRepository, InMemoryHistoryRepository
from backend.ml.language_router import LanguageRouter, UnsupportedLanguageError
from backend.schemas import (
    FactCheckResult,
    HistoryRecord,
    PredictionResponse,
    SubmissionRequest,
)
from backend.services.fact_check_client import FactCheckClient
from backend.services.trust_rater import TrustRater

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["Submissions"])

# ---------------------------------------------------------------------------
# Dependency-injectable singletons
# (In production these are provided via app.state; tests can override them.)
# ---------------------------------------------------------------------------

_URL_FETCH_TIMEOUT: float = 30.0
_PREDICTION_TIMEOUT: float = 60.0  # Indic models are large; 5s was too short

# Browser-like headers so news sites don't block the request with 401/403
_FETCH_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Tags whose content we discard entirely when extracting article text
_DISCARD_TAGS_RE = re.compile(
    r"<(script|style|noscript|nav|header|footer|aside|form|button|svg|iframe)"
    r"[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
# Strip remaining HTML tags
_TAG_RE = re.compile(r"<[^>]+>")
# Collapse whitespace
_WHITESPACE_RE = re.compile(r"\s{2,}")


def _get_language_router(request: Request) -> LanguageRouter:
    """Return the LanguageRouter stored on app.state."""
    return request.app.state.language_router


def _get_trust_rater(request: Request) -> TrustRater:
    """Return the TrustRater stored on app.state."""
    return request.app.state.trust_rater


def _get_fact_check_client(request: Request) -> FactCheckClient:
    """Return the FactCheckClient stored on app.state."""
    return request.app.state.fact_check_client


def _get_repository(request: Request) -> HistoryRepository:
    """Return the HistoryRepository stored on app.state."""
    return request.app.state.repository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_article_body(url: str, correlation_id: str) -> str:
    """Fetch the text body of an article URL.

    Parameters
    ----------
    url:
        The HTTP/HTTPS URL to fetch.
    correlation_id:
        Request correlation ID for logging.

    Returns
    -------
    str
        The response body as plain text.

    Raises
    ------
    HTTPException(502):
        If the request times out, the server returns a non-2xx status, or
        any other network error occurs.
    """
    try:
        async with httpx.AsyncClient(timeout=_URL_FETCH_TIMEOUT) as client:
            response = await client.get(
                url,
                follow_redirects=True,
                headers=_FETCH_HEADERS,
            )
            response.raise_for_status()
            return _extract_text_from_html(response.text)
    except httpx.TimeoutException:
        logger.warning(
            "URL fetch timed out after %.1fs [url=%r, correlation_id=%s]",
            _URL_FETCH_TIMEOUT,
            url,
            correlation_id,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "URL_FETCH_TIMEOUT",
                "message": (
                    f"The article URL did not respond within "
                    f"{_URL_FETCH_TIMEOUT:.0f} seconds."
                ),
            },
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "URL fetch returned HTTP %d [url=%r, correlation_id=%s]",
            exc.response.status_code,
            url,
            correlation_id,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "URL_FETCH_ERROR",
                "message": (
                    f"The article URL returned HTTP {exc.response.status_code}."
                ),
            },
        )
    except Exception as exc:
        logger.exception(
            "URL fetch failed [url=%r, correlation_id=%s]: %s",
            url,
            correlation_id,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "error": "URL_FETCH_ERROR",
                "message": "Failed to fetch the article from the provided URL.",
            },
        )


def _extract_text_from_html(html: str) -> str:
    """Strip HTML and return clean article text for the ML pipeline.

    Tries to extract content from semantic article/main tags first,
    then falls back to all paragraph text, then bare tag stripping.
    """
    # 1. Remove noisy blocks entirely
    text = _DISCARD_TAGS_RE.sub(" ", html)

    # 2. Try to extract content from <article> or <main> tags first
    article_match = re.search(
        r"<(article|main)[^>]*>(.*?)</\1>", text, re.DOTALL | re.IGNORECASE
    )
    if article_match:
        text = article_match.group(2)
    else:
        # Fall back to extracting all <p> paragraph text
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", text, re.DOTALL | re.IGNORECASE)
        if paragraphs:
            text = " ".join(paragraphs)

    # 3. Strip remaining tags
    text = _TAG_RE.sub(" ", text)

    # 4. Decode common HTML entities
    text = (
        text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
    )

    # 5. Collapse whitespace
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def _extract_domain(url: str) -> Optional[str]:
    """Extract the hostname from a URL, or None on parse failure."""
    try:
        return urlparse(url).hostname or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/submissions",
    response_model=PredictionResponse,
    status_code=200,
    summary="Submit a news article for fake-news detection",
    response_description="Prediction result with label, confidence, and supporting data",
)
async def create_submission(
    body: SubmissionRequest,
    request: Request,
    language_router: LanguageRouter = Depends(_get_language_router),
    trust_rater: TrustRater = Depends(_get_trust_rater),
    fact_check_client: FactCheckClient = Depends(_get_fact_check_client),
    repository: HistoryRepository = Depends(_get_repository),
) -> PredictionResponse:
    """Analyse a news article and return a prediction.

    Accepts either raw ``text`` or a ``url`` (exactly one must be provided).
    When a URL is given the article body is fetched first.  The text is then
    routed through the language-specific ML pipeline, cross-referenced with
    the Fact Check API, and the result is persisted to the history store.

    Error codes
    -----------
    - **400** – Unsupported language detected.
    - **502** – Article URL could not be fetched.
    - **504** – ML prediction timed out.
    """
    correlation_id: str = getattr(request.state, "request_id", str(uuid.uuid4()))

    # ------------------------------------------------------------------
    # Step 1: Resolve article text
    # ------------------------------------------------------------------
    article_text: str
    input_url: Optional[str] = body.url

    if body.url:
        logger.info(
            "Fetching article from URL [url=%r, correlation_id=%s]",
            body.url,
            correlation_id,
        )
        article_text = await _fetch_article_body(body.url, correlation_id)
        # Guard: if we got very little text the page likely blocked us or
        # returned a redirect/login wall — treat it as a fetch failure.
        if len(article_text.split()) < 50:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "URL_FETCH_ERROR",
                    "message": (
                        "Could not extract enough article text from the URL. "
                        "The page may require a login or block automated access."
                    ),
                },
            )
    else:
        article_text = body.text  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Step 2: Language detection + ML prediction (with timeout guard)
    # ------------------------------------------------------------------
    try:
        prediction_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, language_router.route, article_text
            ),
            timeout=_PREDICTION_TIMEOUT,
        )
        detected_language: str = _resolve_language(language_router, article_text)
    except UnsupportedLanguageError as exc:
        logger.info(
            "Unsupported language %r [correlation_id=%s]",
            exc.language_code,
            correlation_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UNSUPPORTED_LANGUAGE",
                "message": str(exc),
                "language_code": exc.language_code,
            },
        )
    except asyncio.TimeoutError:
        logger.error(
            "ML prediction timed out after %.1fs [correlation_id=%s]",
            _PREDICTION_TIMEOUT,
            correlation_id,
        )
        raise HTTPException(
            status_code=504,
            detail={
                "error": "PREDICTION_TIMEOUT",
                "message": (
                    f"The ML model did not respond within "
                    f"{_PREDICTION_TIMEOUT:.0f} seconds."
                ),
            },
        )

    # ------------------------------------------------------------------
    # Step 3: Trust rating (only when a URL was submitted)
    # ------------------------------------------------------------------
    trust_rating = None
    if input_url:
        domain = _extract_domain(input_url)
        if domain:
            trust_rating = trust_rater.rate(domain)
            logger.debug(
                "Trust rating for %r: %s [correlation_id=%s]",
                domain,
                trust_rating,
                correlation_id,
            )

    # ------------------------------------------------------------------
    # Step 4: Fact-check (best-effort; never blocks the response)
    # ------------------------------------------------------------------
    fact_check_results = await fact_check_client.check(
        text=article_text,
        correlation_id=correlation_id,
    )
    # Convert dataclass FactCheckResult → Pydantic FactCheckResult
    pydantic_fact_checks = [
        FactCheckResult(
            claim=fc.claim,
            rating=fc.rating,
            source=fc.source,
        )
        for fc in fact_check_results
    ]

    # ------------------------------------------------------------------
    # Step 5: Build response
    # ------------------------------------------------------------------
    record_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    response = PredictionResponse(
        id=record_id,
        label=prediction_result.label,  # type: ignore[arg-type]
        confidence=prediction_result.confidence,
        suspicious_phrases=prediction_result.suspicious_phrases,
        explanation=prediction_result.explanation,
        fact_checks=pydantic_fact_checks,
        trust_rating=trust_rating,
        language=detected_language,  # type: ignore[arg-type]
        timestamp=now,
        input_text=article_text if not input_url else None,
        input_url=input_url,
    )

    # ------------------------------------------------------------------
    # Step 6: Persist to history store
    # ------------------------------------------------------------------
    history_record = HistoryRecord(
        id=record_id,
        input_text=article_text if not input_url else None,
        input_url=input_url,
        label=response.label,
        confidence=response.confidence,
        suspicious_phrases=response.suspicious_phrases,
        explanation=response.explanation,
        fact_checks=response.fact_checks,
        trust_rating=response.trust_rating,
        language=response.language,
        created_at=now,
    )
    try:
        await repository.save(history_record)
        logger.info(
            "Persisted history record [id=%s, correlation_id=%s]",
            record_id,
            correlation_id,
        )
    except Exception:
        # Persistence failure must not prevent the response from being returned.
        logger.exception(
            "Failed to persist history record [id=%s, correlation_id=%s]",
            record_id,
            correlation_id,
        )

    return response


# ---------------------------------------------------------------------------
# Internal helper: re-detect language for the response field
# ---------------------------------------------------------------------------


def _resolve_language(language_router: LanguageRouter, text: str) -> str:
    """Return the detected language code without routing to a pipeline.

    We call the private ``_detect_language`` method so we can populate the
    ``language`` field of the response without a second full prediction.
    Falls back to ``"en"`` if detection fails (should not happen since
    ``route()`` already succeeded).
    """
    try:
        return language_router._detect_language(text)
    except UnsupportedLanguageError:
        return "en"
