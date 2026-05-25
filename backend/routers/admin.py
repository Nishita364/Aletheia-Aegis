"""
Admin endpoints for the Fake News Detector API.

All routes are protected by AuthMiddleware (JWT) already registered in main.py.

Exposes:
  - POST   /api/v1/admin/dataset            — upload CSV training data
  - POST   /api/v1/admin/retrain            — enqueue a retrain job
  - GET    /api/v1/admin/retrain/{job_id}   — poll retrain job status
  - GET    /api/v1/admin/analytics          — submission stats + model accuracy
  - PUT    /api/v1/admin/trust-domains      — replace trust domain list

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 8.5
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from backend.db.repository import HistoryRepository
from backend.schemas import RetrainJob
from backend.services.trust_rater import TrustRater

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_CSV_BYTES = 200 * 1024 * 1024  # 200 MB
_REQUIRED_COLUMNS = {"text", "label"}

# Path to the trust_domains.json file (same location as TrustRater default)
_TRUST_DOMAINS_PATH = (
    Path(__file__).resolve().parent.parent / "services" / "trust_domains.json"
)

# ---------------------------------------------------------------------------
# In-process job store (keyed by job_id UUID)
# ---------------------------------------------------------------------------

_jobs: dict[UUID, RetrainJob] = {}
_jobs_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _get_repository(request: Request) -> HistoryRepository:
    """Return the HistoryRepository stored on app.state."""
    return request.app.state.repository


def _get_trust_rater(request: Request) -> TrustRater:
    """Return the TrustRater stored on app.state."""
    return request.app.state.trust_rater


def _get_model_registry(request: Request):
    """Return the ModelRegistry stored on app.state (may be None)."""
    return getattr(request.app.state, "model_registry", None)


# ---------------------------------------------------------------------------
# POST /api/v1/admin/dataset
# ---------------------------------------------------------------------------


@router.post(
    "/dataset",
    status_code=200,
    summary="Upload CSV training dataset",
    response_description="Summary of parsed rows",
)
async def upload_dataset(
    file: UploadFile,
) -> dict:
    """Validate and parse an uploaded CSV training dataset.

    Validation rules
    ----------------
    - File size must not exceed 200 MB → **413 Payload Too Large**
    - CSV must contain at minimum a ``text`` column and a ``label`` column
      → **422 Unprocessable Entity** with column names listed
    - Malformed rows (missing required fields) are skipped with a warning log
      and do not halt parsing.

    Returns
    -------
    dict
        ``{ "accepted_rows": int, "skipped_rows": int }``

    Error codes
    -----------
    - **413** – File exceeds 200 MB.
    - **422** – Required columns missing.
    """
    # ------------------------------------------------------------------
    # 1. Read raw bytes and check size
    # ------------------------------------------------------------------
    raw_bytes = await file.read()
    if len(raw_bytes) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "PAYLOAD_TOO_LARGE",
                "message": (
                    f"Uploaded file exceeds the 200 MB limit "
                    f"({len(raw_bytes) / (1024 * 1024):.1f} MB received)."
                ),
            },
        )

    # ------------------------------------------------------------------
    # 2. Decode and parse CSV header
    # ------------------------------------------------------------------
    try:
        text_content = raw_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "CSV_DECODE_ERROR",
                "message": f"Could not decode file as UTF-8: {exc}",
            },
        )

    reader = csv.DictReader(io.StringIO(text_content))

    # Validate columns
    if reader.fieldnames is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "MISSING_COLUMNS",
                "message": "CSV file appears to be empty or has no header row.",
                "required_columns": sorted(_REQUIRED_COLUMNS),
            },
        )

    actual_columns = {col.strip().lower() for col in reader.fieldnames if col}
    missing = _REQUIRED_COLUMNS - actual_columns
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "MISSING_COLUMNS",
                "message": (
                    f"CSV is missing required column(s): {sorted(missing)}. "
                    f"Found columns: {sorted(actual_columns)}."
                ),
                "required_columns": sorted(_REQUIRED_COLUMNS),
                "missing_columns": sorted(missing),
            },
        )

    # ------------------------------------------------------------------
    # 3. Parse rows — skip malformed ones with warning logs
    # ------------------------------------------------------------------
    accepted_rows = 0
    skipped_rows = 0

    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        text_val = row.get("text", "").strip() if row.get("text") is not None else ""
        label_val = row.get("label", "").strip() if row.get("label") is not None else ""

        if not text_val or not label_val:
            logger.warning(
                "Skipping malformed CSV row %d: text=%r, label=%r",
                row_number,
                text_val,
                label_val,
            )
            skipped_rows += 1
            continue

        # Row is valid — in a full implementation this would be persisted
        # to a training dataset store; here we count it as accepted.
        accepted_rows += 1

    logger.info(
        "CSV upload complete: accepted=%d, skipped=%d",
        accepted_rows,
        skipped_rows,
    )

    return {
        "accepted_rows": accepted_rows,
        "skipped_rows": skipped_rows,
    }


# ---------------------------------------------------------------------------
# POST /api/v1/admin/retrain
# ---------------------------------------------------------------------------


@router.post(
    "/retrain",
    response_model=RetrainJob,
    status_code=202,
    summary="Enqueue a model retraining job",
    response_description="Retrain job record with job_id and initial status",
)
async def trigger_retrain(
    request: Request,
    model_registry=Depends(_get_model_registry),
) -> RetrainJob:
    """Enqueue a background model retraining job.

    Returns a :class:`RetrainJob` with ``status="pending"`` immediately.
    The job runs in a background thread; poll
    ``GET /api/v1/admin/retrain/{job_id}`` for status updates.

    Error codes
    -----------
    - **401** – Missing or invalid JWT (enforced by AuthMiddleware).
    """
    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    job = RetrainJob(
        job_id=job_id,
        status="pending",
        accuracy=None,
        started_at=None,
        completed_at=None,
        error=None,
    )

    with _jobs_lock:
        _jobs[job_id] = job

    logger.info("Retrain job enqueued [job_id=%s]", job_id)

    # Launch background thread to run training
    thread = threading.Thread(
        target=_run_retrain_job,
        args=(job_id, model_registry),
        daemon=True,
        name=f"retrain-{job_id}",
    )
    thread.start()

    return job


# ---------------------------------------------------------------------------
# GET /api/v1/admin/retrain/{job_id}
# ---------------------------------------------------------------------------


@router.get(
    "/retrain/{job_id}",
    response_model=RetrainJob,
    status_code=200,
    summary="Poll retraining job status",
    response_description="Current state of the retraining job",
)
async def get_retrain_status(job_id: UUID) -> RetrainJob:
    """Return the current status of a retraining job.

    Error codes
    -----------
    - **404** – No job found with the given ``job_id``.
    - **401** – Missing or invalid JWT (enforced by AuthMiddleware).
    """
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "JOB_NOT_FOUND",
                "message": f"No retrain job found with id '{job_id}'.",
            },
        )

    return job


# ---------------------------------------------------------------------------
# GET /api/v1/admin/analytics
# ---------------------------------------------------------------------------


@router.get(
    "/analytics",
    status_code=200,
    summary="Get submission analytics and model accuracy",
    response_description="Total submissions, Real/Fake percentages, model accuracy",
)
async def get_analytics(
    repository: HistoryRepository = Depends(_get_repository),
) -> dict:
    """Return analytics for the Admin Dashboard.

    Returns
    -------
    dict
        ``{ "total_submissions": int, "real_percentage": float,
            "fake_percentage": float, "model_accuracy": float | null }``

    Error codes
    -----------
    - **503** – History store is unavailable.
    - **401** – Missing or invalid JWT (enforced by AuthMiddleware).
    """
    # ------------------------------------------------------------------
    # 1. Fetch all recent records (up to 50 for now; extend as needed)
    # ------------------------------------------------------------------
    try:
        records = await asyncio.wait_for(repository.list_recent(limit=10_000), timeout=15.0)
    except asyncio.TimeoutError:
        logger.warning("Analytics list_recent timed out — returning zeros")
        records = []
    except Exception as exc:
        logger.exception("Failed to fetch records for analytics: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "HISTORY_STORE_UNAVAILABLE",
                "message": "Analytics data is temporarily unavailable.",
            },
        )

    total = len(records)
    if total == 0:
        real_pct = 0.0
        fake_pct = 0.0
    else:
        real_count = sum(1 for r in records if r.label == "Real")
        fake_count = total - real_count
        real_pct = round(real_count / total * 100, 2)
        fake_pct = round(fake_count / total * 100, 2)

    # ------------------------------------------------------------------
    # 2. Read model accuracy from the most recent training metadata
    # ------------------------------------------------------------------
    model_accuracy: Optional[float] = _read_model_accuracy()

    return {
        "total_submissions": total,
        "real_percentage": real_pct,
        "fake_percentage": fake_pct,
        "model_accuracy": model_accuracy,
    }


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/trust-domains
# ---------------------------------------------------------------------------


@router.put(
    "/trust-domains",
    status_code=200,
    summary="Replace the trust domain list",
    response_description="Confirmation that the domain list was updated",
)
async def update_trust_domains(
    body: dict,
    trust_rater: TrustRater = Depends(_get_trust_rater),
) -> dict:
    """Replace the trust domain list and trigger a hot-reload.

    The request body must be a JSON object with the shape::

        {
            "high":   ["reuters.com", ...],
            "medium": ["cnn.com", ...],
            "low":    ["infowars.com", ...]
        }

    Each key is optional; omitted keys are treated as empty lists.
    After writing the new list to disk, ``TrustRater.reload()`` is called
    so the change takes effect immediately without a server restart.

    Error codes
    -----------
    - **422** – Body is not a valid domain list object.
    - **401** – Missing or invalid JWT (enforced by AuthMiddleware).
    """
    # ------------------------------------------------------------------
    # 1. Validate body structure
    # ------------------------------------------------------------------
    allowed_keys = {"high", "medium", "low"}
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "INVALID_BODY",
                "message": "Request body must be a JSON object.",
            },
        )

    unknown_keys = set(body.keys()) - allowed_keys
    if unknown_keys:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "INVALID_BODY",
                "message": (
                    f"Unknown keys in domain list: {sorted(unknown_keys)}. "
                    f"Allowed keys: {sorted(allowed_keys)}."
                ),
            },
        )

    for key, value in body.items():
        if not isinstance(value, list) or not all(isinstance(d, str) for d in value):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "INVALID_BODY",
                    "message": (
                        f"Value for key '{key}' must be a list of strings."
                    ),
                },
            )

    # ------------------------------------------------------------------
    # 2. Write new domain list to disk
    # ------------------------------------------------------------------
    new_data: dict[str, list[str]] = {
        "high": body.get("high", []),
        "medium": body.get("medium", []),
        "low": body.get("low", []),
    }

    try:
        _TRUST_DOMAINS_PATH.write_text(
            json.dumps(new_data, indent=2), encoding="utf-8"
        )
        logger.info(
            "Trust domain list updated: high=%d, medium=%d, low=%d",
            len(new_data["high"]),
            len(new_data["medium"]),
            len(new_data["low"]),
        )
    except OSError as exc:
        logger.exception("Failed to write trust_domains.json: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "WRITE_ERROR",
                "message": "Failed to persist the updated domain list.",
            },
        )

    # ------------------------------------------------------------------
    # 3. Hot-reload TrustRater
    # ------------------------------------------------------------------
    trust_rater.reload()
    logger.info("TrustRater reloaded after domain list update.")

    total_domains = (
        len(new_data["high"]) + len(new_data["medium"]) + len(new_data["low"])
    )
    return {
        "status": "ok",
        "total_domains": total_domains,
        "high": len(new_data["high"]),
        "medium": len(new_data["medium"]),
        "low": len(new_data["low"]),
    }


# ---------------------------------------------------------------------------
# Background retrain worker
# ---------------------------------------------------------------------------


def _run_retrain_job(job_id: UUID, model_registry: Any) -> None:
    """Run the training pipeline in a background thread.

    Updates the job record in ``_jobs`` as the job progresses.
    On completion, swaps the active model in ``model_registry`` if one is
    available.
    """
    # Mark as running
    _update_job(job_id, status="running", started_at=datetime.now(timezone.utc))
    logger.info("Retrain job started [job_id=%s]", job_id)

    try:
        from backend.ml.train import train  # noqa: PLC0415 — lazy import

        result = train()
        lr_accuracy: float = result.get("lr_accuracy", 0.0)

        # Hot-swap the model if a registry is available
        if model_registry is not None:
            try:
                from backend.ml.prediction_service import PredictionService  # noqa: PLC0415

                new_service = PredictionService()
                model_registry.swap(new_service)
                logger.info(
                    "ModelRegistry swapped to new service after retrain [job_id=%s]",
                    job_id,
                )
            except Exception as swap_exc:
                logger.exception(
                    "Failed to swap model after retrain [job_id=%s]: %s",
                    job_id,
                    swap_exc,
                )

        _update_job(
            job_id,
            status="completed",
            accuracy=lr_accuracy,
            completed_at=datetime.now(timezone.utc),
        )
        logger.info(
            "Retrain job completed [job_id=%s, lr_accuracy=%.4f]",
            job_id,
            lr_accuracy,
        )

    except Exception as exc:
        logger.exception("Retrain job failed [job_id=%s]: %s", job_id, exc)
        _update_job(
            job_id,
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error=str(exc),
        )


def _update_job(job_id: UUID, **kwargs: Any) -> None:
    """Thread-safe update of a job record in ``_jobs``."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        updated = job.model_copy(update=kwargs)
        _jobs[job_id] = updated


# ---------------------------------------------------------------------------
# Helper: read model accuracy from training metadata
# ---------------------------------------------------------------------------


def _read_model_accuracy() -> Optional[float]:
    """Return the LR accuracy from the most recent training metadata file.

    Returns ``None`` if the file does not exist or cannot be parsed.
    """
    metadata_path = (
        Path(__file__).resolve().parent.parent / "ml" / "artifacts" / "model_metadata.json"
    )
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        # Key is "accuracy" in multilingual metadata, "lr_accuracy" in legacy
        acc = data.get("accuracy") or data.get("lr_accuracy")
        return float(acc) if acc is not None else None
    except FileNotFoundError:
        logger.debug("model_metadata.json not found; model_accuracy will be null")
        return None
    except Exception as exc:
        logger.warning("Could not read model_metadata.json: %s", exc)
        return None
