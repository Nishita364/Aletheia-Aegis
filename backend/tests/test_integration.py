"""
Integration tests for the Fake News Detector API submission flow and history CRUD.

Tests cover:
- POST /api/v1/submissions with text input (happy path)
- POST /api/v1/submissions with URL input (mocked HTTP fetch)
- POST /api/v1/submissions → 502 when URL fetch fails
- POST /api/v1/submissions → 400 when language is unsupported
- GET  /api/v1/history     → list up to 50 records
- GET  /api/v1/history/{id} → retrieve a single record
- GET  /api/v1/history/{id} → 404 for unknown id
- DELETE /api/v1/history/{id} → delete a record (200)
- DELETE /api/v1/history/{id} → 200 even when record does not exist
- GET  /api/v1/history → 503 when repository raises

Uses pytest-asyncio + httpx.AsyncClient with ASGITransport so no real server
is needed.  PredictionService, FactCheckClient, and outbound HTTP are mocked
to keep tests fast and deterministic.

Requirements: 1.5, 1.6, 4.1, 4.3, 4.5
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from backend.db.repository import InMemoryHistoryRepository
from backend.main import create_app
from backend.ml.language_router import LanguageRouter, UnsupportedLanguageError
from backend.ml.prediction_service import PredictionResult
from backend.schemas import FactCheckResult, HistoryRecord


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_prediction_result(
    label: str = "Fake",
    confidence: float = 0.87,
    phrases: list[str] | None = None,
    explanation: str = "Classified as Fake with 87.0% confidence.",
) -> PredictionResult:
    """Return a deterministic PredictionResult for use in mocks."""
    return PredictionResult(
        label=label,
        confidence=confidence,
        suspicious_phrases=phrases or ["breaking news"],
        explanation=explanation,
    )


def _make_language_router(
    result: PredictionResult | None = None,
    *,
    raise_unsupported: bool = False,
    language: str = "en",
) -> LanguageRouter:
    """Return a LanguageRouter whose route() and _detect_language() are mocked."""
    router = MagicMock(spec=LanguageRouter)
    if raise_unsupported:
        router.route.side_effect = UnsupportedLanguageError("fr")
        router._detect_language.side_effect = UnsupportedLanguageError("fr")
    else:
        router.route.return_value = result or _make_prediction_result()
        router._detect_language.return_value = language
    return router


def _make_fact_check_client(results: list | None = None) -> AsyncMock:
    """Return a FactCheckClient mock whose check() coroutine returns results."""
    client = AsyncMock()
    client.check = AsyncMock(return_value=results or [])
    return client


def _make_trust_rater(rating: str = "Unknown") -> MagicMock:
    """Return a TrustRater mock that always returns rating."""
    rater = MagicMock()
    rater.rate.return_value = rating
    return rater


@pytest_asyncio.fixture
async def repo() -> InMemoryHistoryRepository:
    """Fresh in-memory repository for each test."""
    return InMemoryHistoryRepository()


@pytest_asyncio.fixture
async def client(repo: InMemoryHistoryRepository) -> AsyncGenerator[httpx.AsyncClient, None]:
    """AsyncClient wired to a test FastAPI app with mocked ML dependencies."""
    app = create_app(
        language_router=_make_language_router(),
        trust_rater=_make_trust_rater(),
        fact_check_client=_make_fact_check_client(),
        repository=repo,
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helper: seed a record directly into the repo
# ---------------------------------------------------------------------------


def _make_history_record(
    *,
    id: uuid.UUID | None = None,
    label: str = "Fake",
    confidence: float = 0.87,
    input_text: str = "Some article text.",
    input_url: str | None = None,
) -> HistoryRecord:
    return HistoryRecord(
        id=id or uuid.uuid4(),
        input_text=input_text,
        input_url=input_url,
        label=label,  # type: ignore[arg-type]
        confidence=confidence,
        suspicious_phrases=["breaking news"],
        explanation="Classified as Fake with 87.0% confidence.",
        fact_checks=[],
        trust_rating=None,
        language="en",
        created_at=datetime.now(timezone.utc),
    )


# ===========================================================================
# Submission flow — text input
# ===========================================================================


@pytest.mark.asyncio
async def test_text_submission_returns_200_with_prediction(
    client: httpx.AsyncClient,
) -> None:
    """POST /submissions with valid text returns 200 and a PredictionResponse.

    Requirements: 1.5, 1.6
    """
    response = await client.post(
        "/api/v1/submissions",
        json={"text": "This is a sample news article for testing purposes."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["label"] in ("Real", "Fake")
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["suspicious_phrases"], list)
    assert isinstance(data["explanation"], str) and data["explanation"]
    assert "id" in data
    assert "timestamp" in data
    assert "language" in data


@pytest.mark.asyncio
async def test_text_submission_persists_to_history(
    client: httpx.AsyncClient,
    repo: InMemoryHistoryRepository,
) -> None:
    """After a successful text submission the record is saved to the repository.

    Requirements: 4.1
    """
    response = await client.post(
        "/api/v1/submissions",
        json={"text": "Breaking news: scientists discover new planet."},
    )
    assert response.status_code == 200
    record_id = uuid.UUID(response.json()["id"])

    saved = await repo.get_by_id(record_id)
    assert saved is not None
    assert saved.label in ("Real", "Fake")
    assert saved.input_url is None


@pytest.mark.asyncio
async def test_text_submission_response_contains_correlation_id(
    client: httpx.AsyncClient,
) -> None:
    """Every response must carry an X-Request-ID header.

    Requirements: 1.6
    """
    response = await client.post(
        "/api/v1/submissions",
        json={"text": "Some news article text here."},
    )
    assert response.status_code == 200
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_text_submission_propagates_custom_correlation_id(
    client: httpx.AsyncClient,
) -> None:
    """When the client sends X-Request-ID it is echoed back in the response.

    Requirements: 1.6
    """
    custom_id = "my-custom-request-id-123"
    response = await client.post(
        "/api/v1/submissions",
        json={"text": "Some news article text here."},
        headers={"X-Request-ID": custom_id},
    )
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == custom_id


# ===========================================================================
# Submission flow — URL input (mocked HTTP)
# ===========================================================================


@pytest.mark.asyncio
async def test_url_submission_fetches_article_and_returns_prediction() -> None:
    """POST /submissions with a URL fetches the article body and returns a prediction.

    Requirements: 1.5
    """
    article_body = "Government announces new economic policy affecting millions."
    prediction = _make_prediction_result(label="Real", confidence=0.92)
    repo = InMemoryHistoryRepository()
    app = create_app(
        language_router=_make_language_router(result=prediction),
        trust_rater=_make_trust_rater(rating="High"),
        fact_check_client=_make_fact_check_client(),
        repository=repo,
    )

    # Patch httpx.AsyncClient.get so no real HTTP request is made.
    # Create the test client first (outside the patch) so the patch only
    # affects the internal _fetch_article_body call, not the test client.
    mock_response = MagicMock()
    mock_response.text = article_body
    mock_response.raise_for_status = MagicMock()

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        with patch("backend.routers.submissions.httpx.AsyncClient") as mock_client_cls:
            mock_async_ctx = AsyncMock()
            mock_async_ctx.__aenter__ = AsyncMock(return_value=mock_async_ctx)
            mock_async_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_async_ctx.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_async_ctx

            response = await ac.post(
                "/api/v1/submissions",
                json={"url": "https://example.com/article"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["label"] == "Real"
    assert data["confidence"] == pytest.approx(0.92)
    assert data["trust_rating"] == "High"


@pytest.mark.asyncio
async def test_url_submission_persists_url_to_history() -> None:
    """URL submissions store the URL (not the fetched text) in the history record.

    Requirements: 4.1
    """
    article_body = "Some article content fetched from the URL."
    repo = InMemoryHistoryRepository()
    app = create_app(
        language_router=_make_language_router(),
        trust_rater=_make_trust_rater(),
        fact_check_client=_make_fact_check_client(),
        repository=repo,
    )

    mock_response = MagicMock()
    mock_response.text = article_body
    mock_response.raise_for_status = MagicMock()

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        with patch("backend.routers.submissions.httpx.AsyncClient") as mock_client_cls:
            mock_async_ctx = AsyncMock()
            mock_async_ctx.__aenter__ = AsyncMock(return_value=mock_async_ctx)
            mock_async_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_async_ctx.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_async_ctx

            response = await ac.post(
                "/api/v1/submissions",
                json={"url": "https://example.com/news"},
            )

    assert response.status_code == 200
    record_id = uuid.UUID(response.json()["id"])
    saved = await repo.get_by_id(record_id)
    assert saved is not None
    assert saved.input_url == "https://example.com/news"
    assert saved.input_text is None


# ===========================================================================
# Submission error paths
# ===========================================================================


@pytest.mark.asyncio
async def test_url_submission_returns_502_when_fetch_times_out() -> None:
    """POST /submissions returns 502 when the URL fetch times out.

    Requirements: 1.6
    """
    repo = InMemoryHistoryRepository()
    app = create_app(
        language_router=_make_language_router(),
        trust_rater=_make_trust_rater(),
        fact_check_client=_make_fact_check_client(),
        repository=repo,
    )

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        with patch("backend.routers.submissions.httpx.AsyncClient") as mock_client_cls:
            mock_async_ctx = AsyncMock()
            mock_async_ctx.__aenter__ = AsyncMock(return_value=mock_async_ctx)
            mock_async_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_async_ctx.get = AsyncMock(
                side_effect=httpx.TimeoutException("timed out")
            )
            mock_client_cls.return_value = mock_async_ctx

            response = await ac.post(
                "/api/v1/submissions",
                json={"url": "https://slow-server.example.com/article"},
            )

    assert response.status_code == 502
    data = response.json()
    assert data["detail"]["error"] == "URL_FETCH_TIMEOUT"


@pytest.mark.asyncio
async def test_url_submission_returns_502_when_server_returns_error_status() -> None:
    """POST /submissions returns 502 when the remote server returns a non-2xx status.

    Requirements: 1.6
    """
    repo = InMemoryHistoryRepository()
    app = create_app(
        language_router=_make_language_router(),
        trust_rater=_make_trust_rater(),
        fact_check_client=_make_fact_check_client(),
        repository=repo,
    )

    # Build a mock response that raise_for_status() will raise on
    error_response = httpx.Response(status_code=404, request=httpx.Request("GET", "https://example.com/missing"))

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        with patch("backend.routers.submissions.httpx.AsyncClient") as mock_client_cls:
            mock_async_ctx = AsyncMock()
            mock_async_ctx.__aenter__ = AsyncMock(return_value=mock_async_ctx)
            mock_async_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_async_ctx.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "404 Not Found",
                    request=httpx.Request("GET", "https://example.com/missing"),
                    response=error_response,
                )
            )
            mock_client_cls.return_value = mock_async_ctx

            response = await ac.post(
                "/api/v1/submissions",
                json={"url": "https://example.com/missing"},
            )

    assert response.status_code == 502
    data = response.json()
    assert data["detail"]["error"] == "URL_FETCH_ERROR"


@pytest.mark.asyncio
async def test_submission_returns_400_for_unsupported_language() -> None:
    """POST /submissions returns 400 when the detected language is unsupported.

    Requirements: 1.6
    """
    repo = InMemoryHistoryRepository()
    app = create_app(
        language_router=_make_language_router(raise_unsupported=True),
        trust_rater=_make_trust_rater(),
        fact_check_client=_make_fact_check_client(),
        repository=repo,
    )

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/submissions",
            json={"text": "Ceci est un article en français."},
        )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "UNSUPPORTED_LANGUAGE"


@pytest.mark.asyncio
async def test_submission_returns_400_for_invalid_schema(
    client: httpx.AsyncClient,
) -> None:
    """POST /submissions returns 422 when both text and url are provided.

    Requirements: 1.6
    """
    response = await client.post(
        "/api/v1/submissions",
        json={"text": "Some text", "url": "https://example.com"},
    )
    # FastAPI returns 422 for Pydantic validation errors
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submission_returns_422_when_neither_text_nor_url(
    client: httpx.AsyncClient,
) -> None:
    """POST /submissions returns 422 when neither text nor url is provided.

    Requirements: 1.6
    """
    response = await client.post(
        "/api/v1/submissions",
        json={},
    )
    assert response.status_code == 422


# ===========================================================================
# History CRUD — list
# ===========================================================================


@pytest.mark.asyncio
async def test_history_list_returns_empty_list_initially(
    client: httpx.AsyncClient,
) -> None:
    """GET /history returns an empty list when no submissions have been made.

    Requirements: 4.3
    """
    response = await client.get("/api/v1/history")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_history_list_returns_submitted_records(
    client: httpx.AsyncClient,
    repo: InMemoryHistoryRepository,
) -> None:
    """GET /history returns records that were previously submitted.

    Requirements: 4.3
    """
    # Seed two records directly
    record_a = _make_history_record(label="Real", confidence=0.9)
    record_b = _make_history_record(label="Fake", confidence=0.75)
    await repo.save(record_a)
    await repo.save(record_b)

    response = await client.get("/api/v1/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    ids = {item["id"] for item in data}
    assert str(record_a.id) in ids
    assert str(record_b.id) in ids


@pytest.mark.asyncio
async def test_history_list_returns_at_most_50_records(
    client: httpx.AsyncClient,
    repo: InMemoryHistoryRepository,
) -> None:
    """GET /history returns at most 50 records even when more exist.

    Requirements: 4.3
    """
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(60):
        record = _make_history_record()
        # Vary created_at so ordering is deterministic
        record = record.model_copy(
            update={"created_at": base_time + timedelta(minutes=i)}
        )
        await repo.save(record)

    response = await client.get("/api/v1/history")
    assert response.status_code == 200
    assert len(response.json()) == 50


@pytest.mark.asyncio
async def test_history_list_ordered_newest_first(
    client: httpx.AsyncClient,
    repo: InMemoryHistoryRepository,
) -> None:
    """GET /history returns records ordered by created_at descending.

    Requirements: 4.3
    """
    from datetime import timedelta

    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(5):
        r = _make_history_record()
        r = r.model_copy(update={"created_at": base_time + timedelta(hours=i)})
        records.append(r)
        await repo.save(r)

    response = await client.get("/api/v1/history")
    assert response.status_code == 200
    data = response.json()
    timestamps = [item["created_at"] for item in data]
    assert timestamps == sorted(timestamps, reverse=True)


# ===========================================================================
# History CRUD — get single record
# ===========================================================================


@pytest.mark.asyncio
async def test_history_get_returns_record_by_id(
    client: httpx.AsyncClient,
    repo: InMemoryHistoryRepository,
) -> None:
    """GET /history/{id} returns the correct record.

    Requirements: 4.3
    """
    record = _make_history_record(label="Real", confidence=0.95)
    await repo.save(record)

    response = await client.get(f"/api/v1/history/{record.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(record.id)
    assert data["label"] == "Real"
    assert data["confidence"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_history_get_returns_404_for_unknown_id(
    client: httpx.AsyncClient,
) -> None:
    """GET /history/{id} returns 404 when the record does not exist.

    Requirements: 4.3
    """
    unknown_id = uuid.uuid4()
    response = await client.get(f"/api/v1/history/{unknown_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "NOT_FOUND"


# ===========================================================================
# History CRUD — delete
# ===========================================================================


@pytest.mark.asyncio
async def test_history_delete_removes_record(
    client: httpx.AsyncClient,
    repo: InMemoryHistoryRepository,
) -> None:
    """DELETE /history/{id} removes the record and returns 200.

    Requirements: 4.5
    """
    record = _make_history_record()
    await repo.save(record)

    response = await client.delete(f"/api/v1/history/{record.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["deleted"] is True

    # Confirm it's gone
    assert await repo.get_by_id(record.id) is None


@pytest.mark.asyncio
async def test_history_delete_returns_200_for_nonexistent_record(
    client: httpx.AsyncClient,
) -> None:
    """DELETE /history/{id} returns 200 even when the record does not exist.

    Requirements: 4.5
    """
    unknown_id = uuid.uuid4()
    response = await client.delete(f"/api/v1/history/{unknown_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["deleted"] is False


@pytest.mark.asyncio
async def test_history_delete_does_not_affect_other_records(
    client: httpx.AsyncClient,
    repo: InMemoryHistoryRepository,
) -> None:
    """Deleting one record leaves other records intact.

    Requirements: 4.5
    """
    record_a = _make_history_record()
    record_b = _make_history_record()
    await repo.save(record_a)
    await repo.save(record_b)

    response = await client.delete(f"/api/v1/history/{record_a.id}")
    assert response.status_code == 200

    assert await repo.get_by_id(record_a.id) is None
    assert await repo.get_by_id(record_b.id) is not None


# ===========================================================================
# History error path — 503 when repository raises
# ===========================================================================


class _BrokenRepository(InMemoryHistoryRepository):
    """Repository that always raises on read operations to simulate 503."""

    async def list_recent(self, limit: int = 50):  # type: ignore[override]
        raise RuntimeError("Database connection lost")

    async def get_by_id(self, id):  # type: ignore[override]
        raise RuntimeError("Database connection lost")

    async def delete(self, id):  # type: ignore[override]
        raise RuntimeError("Database connection lost")


@pytest_asyncio.fixture
async def broken_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """AsyncClient wired to an app with a broken repository."""
    app = create_app(
        language_router=_make_language_router(),
        trust_rater=_make_trust_rater(),
        fact_check_client=_make_fact_check_client(),
        repository=_BrokenRepository(),
    )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_history_list_returns_503_when_store_unavailable(
    broken_client: httpx.AsyncClient,
) -> None:
    """GET /history returns 503 when the history store is unavailable.

    Requirements: 4.5 (Req 4.6 — store unavailable → 503)
    """
    response = await broken_client.get("/api/v1/history")
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["error"] == "HISTORY_STORE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_history_get_returns_503_when_store_unavailable(
    broken_client: httpx.AsyncClient,
) -> None:
    """GET /history/{id} returns 503 when the history store is unavailable.

    Requirements: 4.5 (Req 4.6 — store unavailable → 503)
    """
    some_id = uuid.uuid4()
    response = await broken_client.get(f"/api/v1/history/{some_id}")
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["error"] == "HISTORY_STORE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_history_delete_returns_503_when_store_unavailable(
    broken_client: httpx.AsyncClient,
) -> None:
    """DELETE /history/{id} returns 503 when the history store is unavailable.

    Requirements: 4.5 (Req 4.6 — store unavailable → 503)
    """
    some_id = uuid.uuid4()
    response = await broken_client.delete(f"/api/v1/history/{some_id}")
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["error"] == "HISTORY_STORE_UNAVAILABLE"


# ===========================================================================
# Health endpoint sanity check
# ===========================================================================


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client: httpx.AsyncClient) -> None:
    """GET /api/v1/health returns 200 with status ok."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
