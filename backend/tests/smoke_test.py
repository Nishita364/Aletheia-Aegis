"""
Smoke tests for the Fake News Detector backend.

Verifies that the most critical system components are operational:
  1. GET /api/v1/health returns 200 (liveness probe)
  2. ML model (PredictionService) loads without error
  3. History store (InMemoryHistoryRepository) connection is established
  4. Admin auth rejects unauthenticated requests with 401

These tests are intentionally lightweight — they confirm the system is
"alive" rather than exercising full business logic.

Requirements: 5.2
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

from backend.main import create_app
from backend.db.repository import InMemoryHistoryRepository


# ---------------------------------------------------------------------------
# Shared fixture: a minimal app with real (non-mocked) dependencies where
# possible, so the smoke tests exercise actual wiring.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def smoke_client() -> httpx.AsyncClient:
    """AsyncClient wired to a freshly created app instance.

    Uses InMemoryHistoryRepository so no real MongoDB is required.
    The LanguageRouter, TrustRater, and FactCheckClient are left as their
    defaults (created inside create_app) to verify they initialise cleanly.
    """
    app = create_app(repository=InMemoryHistoryRepository())
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# ===========================================================================
# Smoke test 1: Health endpoint
# ===========================================================================


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(smoke_client: httpx.AsyncClient) -> None:
    """GET /api/v1/health must return HTTP 200 with {"status": "ok"}.

    Confirms the FastAPI application starts up and the liveness probe is
    reachable.

    Requirements: 5.2
    """
    response = await smoke_client.get("/api/v1/health")

    assert response.status_code == 200, (
        f"Expected 200 from /api/v1/health, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body.get("status") == "ok", f"Unexpected health body: {body}"


# ===========================================================================
# Smoke test 2: ML model loads without error
# ===========================================================================


def test_prediction_service_loads_without_error() -> None:
    """PredictionService must instantiate successfully from saved artifacts.

    Verifies that the trained TF-IDF vectorizer and LogisticRegression model
    can be loaded from disk without raising any exception.

    Requirements: 5.2
    """
    # Import here so any ImportError is surfaced as a test failure rather
    # than a collection error.
    from backend.ml.prediction_service import PredictionService  # noqa: PLC0415

    # Instantiation loads artifacts from backend/ml/artifacts/
    service = PredictionService()

    # Basic sanity: the service should be able to produce a prediction
    result = service.predict("Scientists discover a new planet in the solar system.")

    assert result.label in ("Real", "Fake"), f"Unexpected label: {result.label!r}"
    assert 0.0 <= result.confidence <= 1.0, (
        f"Confidence out of range: {result.confidence}"
    )
    assert isinstance(result.suspicious_phrases, list), (
        "suspicious_phrases should be a list"
    )
    assert isinstance(result.explanation, str) and result.explanation, (
        "explanation should be a non-empty string"
    )


# ===========================================================================
# Smoke test 3: History store connection is established
# ===========================================================================


@pytest.mark.asyncio
async def test_history_store_connection_established() -> None:
    """InMemoryHistoryRepository must be usable for save and retrieve operations.

    For the in-memory store this confirms the repository initialises and
    basic CRUD operations work, establishing that the History_Store layer
    is wired correctly.

    Requirements: 5.2
    """
    import uuid
    from datetime import datetime, timezone
    from backend.schemas import HistoryRecord  # noqa: PLC0415

    repo = InMemoryHistoryRepository()

    # Verify the store starts empty
    records = await repo.list_recent()
    assert records == [], f"Expected empty store on init, got {records}"

    # Save a record
    record = HistoryRecord(
        id=uuid.uuid4(),
        input_text="Smoke test article text.",
        input_url=None,
        label="Real",  # type: ignore[arg-type]
        confidence=0.95,
        suspicious_phrases=[],
        explanation="Smoke test explanation.",
        fact_checks=[],
        trust_rating=None,
        language="en",
        created_at=datetime.now(timezone.utc),
    )
    await repo.save(record)

    # Retrieve and verify
    fetched = await repo.get_by_id(record.id)
    assert fetched is not None, "Record should be retrievable after save"
    assert fetched.id == record.id
    assert fetched.label == "Real"
    assert fetched.confidence == pytest.approx(0.95)

    # Confirm list_recent returns it
    recent = await repo.list_recent()
    assert len(recent) == 1
    assert recent[0].id == record.id


# ===========================================================================
# Smoke test 4: Admin auth rejects unauthenticated requests
# ===========================================================================


@pytest.mark.asyncio
async def test_admin_auth_rejects_unauthenticated_request(
    smoke_client: httpx.AsyncClient,
) -> None:
    """Requests to /api/v1/admin/* without a token must be rejected with 401.

    Verifies that the AuthMiddleware is active and correctly guards all
    admin endpoints against unauthenticated access.

    Requirements: 5.2
    """
    # Test several admin endpoints to confirm the middleware applies broadly
    admin_endpoints = [
        ("GET", "/api/v1/admin/analytics"),
        ("POST", "/api/v1/admin/retrain"),
        ("GET", "/api/v1/admin/retrain/some-job-id"),
    ]

    for method, path in admin_endpoints:
        response = await smoke_client.request(method, path)
        assert response.status_code in (401, 403), (
            f"Expected 401 or 403 for unauthenticated {method} {path}, "
            f"got {response.status_code}: {response.text}"
        )


@pytest.mark.asyncio
async def test_admin_auth_rejects_malformed_token(
    smoke_client: httpx.AsyncClient,
) -> None:
    """Requests to /api/v1/admin/* with an invalid token must be rejected with 401.

    Requirements: 5.2
    """
    response = await smoke_client.get(
        "/api/v1/admin/analytics",
        headers={"Authorization": "Bearer this-is-not-a-valid-jwt"},
    )
    assert response.status_code == 401, (
        f"Expected 401 for invalid token, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body.get("error") == "UNAUTHORIZED"
