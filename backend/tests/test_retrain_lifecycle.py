"""
End-to-end integration test for the retrain job lifecycle.

Tests the full retrain workflow:
  1. POST /api/v1/admin/dataset  — upload a small CSV fixture
  2. POST /api/v1/admin/retrain  — trigger retraining, receive job_id
  3. GET  /api/v1/admin/retrain/{job_id} — poll until completed (or failed)
  4. GET  /api/v1/admin/analytics — verify model_accuracy is present

The retrain job runs the real training pipeline in a background thread.
A small CSV fixture (20 rows) is used so the test completes quickly.

Requirements: 5.5, 5.6, 5.7
"""

from __future__ import annotations

import asyncio
import io
import os
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from jose import jwt

from backend.db.repository import InMemoryHistoryRepository
from backend.main import JWT_ALGORITHM, JWT_SECRET, create_app
from backend.ml.model_registry import ModelRegistry

# ---------------------------------------------------------------------------
# CSV fixture — 20 rows with text and label columns
# ---------------------------------------------------------------------------

_CSV_FIXTURE = """\
text,label
Scientists discover water on Mars surface in new study,Real
Breaking: Government secretly controls all weather patterns,Fake
New vaccine shows 95 percent efficacy in clinical trials,Real
Aliens have landed and are living among us says insider,Fake
Stock market reaches record high amid economic recovery,Real
Bill Gates microchips hidden in COVID vaccines exposed,Fake
Researchers develop new battery that lasts ten times longer,Real
Moon landing was staged in Hollywood studio leaked footage,Fake
Local hospital opens new pediatric wing for children,Real
5G towers are spreading coronavirus according to experts,Fake
University study links exercise to improved mental health,Real
Secret society controls all world governments documents show,Fake
New solar panel technology doubles energy output efficiency,Real
Chemtrails are poisoning the water supply whistleblower says,Fake
City council approves new public transportation expansion plan,Real
Ancient prophecy predicts end of world next Tuesday confirmed,Fake
Scientists sequence genome of rare deep sea creature,Real
Fluoride in water is mind control chemical government admits,Fake
International team wins Nobel Prize for climate research,Real
Reptilian shapeshifters infiltrate world governments sources say,Fake
"""

# ---------------------------------------------------------------------------
# Helper: generate a valid admin JWT
# ---------------------------------------------------------------------------


def _make_admin_token() -> str:
    """Create a signed JWT that passes AuthMiddleware validation."""
    payload = {
        "sub": "admin-test-user",
        "role": "admin",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """AsyncClient wired to a test app with a real ModelRegistry."""
    registry = ModelRegistry()
    app = create_app(repository=InMemoryHistoryRepository())
    # Attach the model registry so the retrain job can hot-swap the model
    app.state.model_registry = registry

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Authorization headers with a valid admin JWT."""
    return {"Authorization": f"Bearer {_make_admin_token()}"}


@pytest.fixture
def csv_file() -> bytes:
    """Small CSV fixture as bytes."""
    return _CSV_FIXTURE.encode("utf-8")


# ---------------------------------------------------------------------------
# Helper: poll retrain status until terminal state or timeout
# ---------------------------------------------------------------------------


async def _poll_until_done(
    client: httpx.AsyncClient,
    job_id: str,
    headers: dict[str, str],
    timeout_seconds: float = 120.0,
    poll_interval: float = 1.0,
) -> dict:
    """Poll GET /api/v1/admin/retrain/{job_id} until status is terminal.

    Returns the final job dict.
    Raises TimeoutError if the job does not complete within timeout_seconds.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = await client.get(
            f"/api/v1/admin/retrain/{job_id}",
            headers=headers,
        )
        assert response.status_code == 200, (
            f"Unexpected status {response.status_code} while polling: {response.text}"
        )
        job = response.json()
        if job["status"] in ("completed", "failed"):
            return job
        await asyncio.sleep(poll_interval)

    raise TimeoutError(
        f"Retrain job {job_id!r} did not reach a terminal state within "
        f"{timeout_seconds:.0f} seconds."
    )


# ===========================================================================
# Test: full retrain lifecycle
# ===========================================================================


@pytest.mark.asyncio
async def test_retrain_lifecycle_completes_and_analytics_shows_accuracy(
    admin_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    csv_file: bytes,
) -> None:
    """Full retrain lifecycle: upload CSV → trigger retrain → poll → analytics.

    Steps
    -----
    1. Upload a small CSV fixture via POST /api/v1/admin/dataset.
    2. Trigger retraining via POST /api/v1/admin/retrain.
    3. Poll GET /api/v1/admin/retrain/{job_id} until status is 'completed'.
    4. Assert GET /api/v1/admin/analytics returns a non-null model_accuracy.

    Requirements: 5.5, 5.6, 5.7
    """
    # ------------------------------------------------------------------
    # Step 1: Upload CSV dataset
    # ------------------------------------------------------------------
    upload_response = await admin_client.post(
        "/api/v1/admin/dataset",
        headers=admin_headers,
        files={"file": ("fixture.csv", io.BytesIO(csv_file), "text/csv")},
    )
    assert upload_response.status_code == 200, (
        f"Dataset upload failed ({upload_response.status_code}): {upload_response.text}"
    )
    upload_data = upload_response.json()
    assert upload_data["accepted_rows"] > 0, (
        f"Expected at least one accepted row, got: {upload_data}"
    )
    assert upload_data["skipped_rows"] == 0, (
        f"Expected no skipped rows, got: {upload_data}"
    )

    # ------------------------------------------------------------------
    # Step 2: Trigger retrain
    # ------------------------------------------------------------------
    retrain_response = await admin_client.post(
        "/api/v1/admin/retrain",
        headers=admin_headers,
    )
    assert retrain_response.status_code == 202, (
        f"Retrain trigger failed ({retrain_response.status_code}): {retrain_response.text}"
    )
    retrain_data = retrain_response.json()
    assert "job_id" in retrain_data, f"Response missing job_id: {retrain_data}"
    assert retrain_data["status"] in ("pending", "running"), (
        f"Expected initial status to be 'pending' or 'running', got: {retrain_data['status']}"
    )
    job_id = retrain_data["job_id"]

    # ------------------------------------------------------------------
    # Step 3: Poll until completed (or fail fast on 'failed')
    # ------------------------------------------------------------------
    final_job = await _poll_until_done(
        admin_client,
        job_id,
        admin_headers,
        timeout_seconds=120.0,
    )

    assert final_job["status"] == "completed", (
        f"Retrain job did not complete successfully. Final state: {final_job}"
    )
    # Accuracy should be populated after a successful retrain
    assert final_job["accuracy"] is not None, (
        f"Expected accuracy to be set after completion, got: {final_job}"
    )
    assert 0.0 <= final_job["accuracy"] <= 1.0, (
        f"Accuracy out of range [0, 1]: {final_job['accuracy']}"
    )

    # ------------------------------------------------------------------
    # Step 4: Verify analytics reflects updated model accuracy
    # ------------------------------------------------------------------
    analytics_response = await admin_client.get(
        "/api/v1/admin/analytics",
        headers=admin_headers,
    )
    assert analytics_response.status_code == 200, (
        f"Analytics request failed ({analytics_response.status_code}): {analytics_response.text}"
    )
    analytics = analytics_response.json()

    assert "model_accuracy" in analytics, (
        f"Analytics response missing 'model_accuracy': {analytics}"
    )
    assert analytics["model_accuracy"] is not None, (
        "Expected model_accuracy to be non-null after a completed retrain."
    )
    assert 0.0 <= analytics["model_accuracy"] <= 1.0, (
        f"model_accuracy out of range [0, 1]: {analytics['model_accuracy']}"
    )
    assert "total_submissions" in analytics
    assert "real_percentage" in analytics
    assert "fake_percentage" in analytics


# ===========================================================================
# Test: retrain job status transitions are observable via polling
# ===========================================================================


@pytest.mark.asyncio
async def test_retrain_job_status_is_pollable(
    admin_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    """GET /api/v1/admin/retrain/{job_id} returns valid status at each poll.

    Verifies Requirement 5.6: while a retraining job is in progress, the
    API responds to status polling requests with the current job state.

    Requirements: 5.6
    """
    # Trigger retrain
    retrain_response = await admin_client.post(
        "/api/v1/admin/retrain",
        headers=admin_headers,
    )
    assert retrain_response.status_code == 202
    job_id = retrain_response.json()["job_id"]

    # Poll at least once and verify the response structure
    poll_response = await admin_client.get(
        f"/api/v1/admin/retrain/{job_id}",
        headers=admin_headers,
    )
    assert poll_response.status_code == 200
    job = poll_response.json()

    assert job["job_id"] == job_id
    assert job["status"] in ("pending", "running", "completed", "failed"), (
        f"Unexpected status value: {job['status']}"
    )

    # Wait for completion to avoid leaving background threads running
    await _poll_until_done(admin_client, job_id, admin_headers, timeout_seconds=120.0)


# ===========================================================================
# Test: polling an unknown job_id returns 404
# ===========================================================================


@pytest.mark.asyncio
async def test_retrain_poll_unknown_job_returns_404(
    admin_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    """GET /api/v1/admin/retrain/{job_id} returns 404 for an unknown job.

    Requirements: 5.6
    """
    import uuid

    unknown_id = str(uuid.uuid4())
    response = await admin_client.get(
        f"/api/v1/admin/retrain/{unknown_id}",
        headers=admin_headers,
    )
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"] == "JOB_NOT_FOUND"


# ===========================================================================
# Test: unauthenticated retrain requests are rejected
# ===========================================================================


@pytest.mark.asyncio
async def test_retrain_requires_authentication(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST /api/v1/admin/retrain without a token returns 401.

    Requirements: 5.2
    """
    response = await admin_client.post("/api/v1/admin/retrain")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dataset_upload_requires_authentication(
    admin_client: httpx.AsyncClient,
    csv_file: bytes,
) -> None:
    """POST /api/v1/admin/dataset without a token returns 401.

    Requirements: 5.2
    """
    response = await admin_client.post(
        "/api/v1/admin/dataset",
        files={"file": ("fixture.csv", io.BytesIO(csv_file), "text/csv")},
    )
    assert response.status_code == 401
