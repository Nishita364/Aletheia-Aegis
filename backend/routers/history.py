"""
History endpoints for the Fake News Detector API.

Exposes:
  - GET  /api/v1/history        — return up to 50 most recent records (created_at desc)
  - GET  /api/v1/history/{id}   — return a single record or 404
  - DELETE /api/v1/history/{id} — delete a record (200 ok); 503 if store unavailable

Requirements: 4.2, 4.3, 4.4, 4.5, 4.6
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.db.repository import HistoryRepository
from backend.schemas import HistoryRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1", tags=["History"])

# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def _get_repository(request: Request) -> HistoryRepository:
    """Return the HistoryRepository stored on app.state."""
    return request.app.state.repository


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/history",
    response_model=list[HistoryRecord],
    status_code=200,
    summary="List recent history records",
    response_description="Up to 50 most recent submission records ordered by created_at descending",
)
async def list_history(
    repository: HistoryRepository = Depends(_get_repository),
) -> list[HistoryRecord]:
    """Return up to 50 most recent history records ordered by ``created_at`` desc."""
    try:
        records = await asyncio.wait_for(repository.list_recent(limit=50), timeout=5.0)
        return records
    except asyncio.TimeoutError:
        logger.warning("History list_recent timed out — returning empty list")
        return []
    except Exception as exc:
        logger.exception("Failed to list history records: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "HISTORY_STORE_UNAVAILABLE",
                "message": "History is temporarily unavailable. Please try again later.",
            },
        )


@router.get(
    "/history/{id}",
    response_model=HistoryRecord,
    status_code=200,
    summary="Get a single history record",
    response_description="The history record with the given ID",
)
async def get_history_record(
    id: UUID,
    repository: HistoryRepository = Depends(_get_repository),
) -> HistoryRecord:
    """Return a single history record by its UUID primary key.

    Error codes
    -----------
    - **404** – No record found with the given ID.
    - **503** – History store is unavailable.
    """
    try:
        record = await repository.get_by_id(id)
    except Exception as exc:
        logger.exception("Failed to retrieve history record [id=%s]: %s", id, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "HISTORY_STORE_UNAVAILABLE",
                "message": "History is temporarily unavailable. Please try again later.",
            },
        )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NOT_FOUND",
                "message": f"No history record found with id '{id}'.",
            },
        )

    return record


@router.delete(
    "/history/{id}",
    status_code=200,
    summary="Delete a history record",
    response_description="Record deleted successfully",
)
async def delete_history_record(
    id: UUID,
    repository: HistoryRepository = Depends(_get_repository),
) -> dict:
    """Delete a history record by its UUID primary key.

    Returns 200 on success (whether or not the record existed).
    Returns 503 if the history store is unavailable.

    Error codes
    -----------
    - **503** – History store is unavailable.
    """
    try:
        deleted = await repository.delete(id)
    except Exception as exc:
        logger.exception("Failed to delete history record [id=%s]: %s", id, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "HISTORY_STORE_UNAVAILABLE",
                "message": "History is temporarily unavailable. Please try again later.",
            },
        )

    if deleted:
        logger.info("Deleted history record [id=%s]", id)
    else:
        logger.info("Delete requested for non-existent history record [id=%s]", id)

    return {"status": "ok", "deleted": deleted}
