"""
Abstract repository interface and in-memory implementation for history records.

Defines the ``HistoryRepository`` ABC that all concrete implementations must
satisfy, plus an ``InMemoryHistoryRepository`` suitable for unit tests and
local development without a real database.

Requirements: 4.1, 4.3, 4.5, 4.6
"""

from __future__ import annotations

import abc
from typing import Optional
from uuid import UUID

from backend.schemas import HistoryRecord


class HistoryRepository(abc.ABC):
    """Abstract interface for persisting and retrieving history records.

    All methods are async to support both in-memory and I/O-bound
    (e.g. MongoDB) implementations behind the same interface.
    """

    @abc.abstractmethod
    async def save(self, record: HistoryRecord) -> None:
        """Persist a history record.

        Parameters
        ----------
        record:
            The ``HistoryRecord`` to store.  If a record with the same
            ``id`` already exists it should be overwritten.
        """

    @abc.abstractmethod
    async def list_recent(self, limit: int = 50) -> list[HistoryRecord]:
        """Return the most recent history records ordered by ``created_at`` desc.

        Parameters
        ----------
        limit:
            Maximum number of records to return (default 50).

        Returns
        -------
        list[HistoryRecord]
            Records sorted newest-first, at most ``limit`` items.
        """

    @abc.abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[HistoryRecord]:
        """Retrieve a single record by its primary key.

        Parameters
        ----------
        id:
            The UUID of the record to fetch.

        Returns
        -------
        HistoryRecord | None
            The matching record, or ``None`` if not found.
        """

    @abc.abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete a record by its primary key.

        Parameters
        ----------
        id:
            The UUID of the record to delete.

        Returns
        -------
        bool
            ``True`` if the record was found and deleted, ``False`` if no
            record with that ``id`` exists.
        """


# ---------------------------------------------------------------------------
# In-memory implementation (for tests and local development)
# ---------------------------------------------------------------------------


class InMemoryHistoryRepository(HistoryRepository):
    """Thread-safe in-memory implementation backed by a plain dict.

    Suitable for unit tests and local development; does not require a
    running database.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, HistoryRecord] = {}

    async def save(self, record: HistoryRecord) -> None:
        """Store or overwrite a record keyed by its ``id``."""
        self._store[record.id] = record

    async def list_recent(self, limit: int = 50) -> list[HistoryRecord]:
        """Return up to ``limit`` records sorted by ``created_at`` descending."""
        sorted_records = sorted(
            self._store.values(),
            key=lambda r: r.created_at,
            reverse=True,
        )
        return sorted_records[:limit]

    async def get_by_id(self, id: UUID) -> Optional[HistoryRecord]:
        """Return the record with the given ``id``, or ``None``."""
        return self._store.get(id)

    async def delete(self, id: UUID) -> bool:
        """Delete the record with the given ``id``.

        Returns ``True`` if deleted, ``False`` if not found.
        """
        if id in self._store:
            del self._store[id]
            return True
        return False
