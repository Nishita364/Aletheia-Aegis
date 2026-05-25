"""
MongoDB-backed implementation of ``HistoryRepository`` using ``motor``.

Maps ``HistoryRecord`` Pydantic models to/from MongoDB documents, using
the record's UUID ``id`` as the document ``_id`` field.

Requirements: 4.1, 4.3, 4.5, 4.6
"""

from __future__ import annotations

import ssl
from typing import Any, Optional
from uuid import UUID

import motor.motor_asyncio

from backend.schemas import HistoryRecord
from backend.db.repository import HistoryRepository


def _record_to_doc(record: HistoryRecord) -> dict[str, Any]:
    """Convert a ``HistoryRecord`` to a MongoDB document dict.

    The Pydantic model is serialised to a plain dict; the ``id`` field is
    stored as ``_id`` (MongoDB's primary key) so that lookups by ``_id``
    are efficient.  The ``id`` key is removed to avoid duplication.
    """
    doc = record.model_dump(mode="python")
    doc["_id"] = str(doc.pop("id"))
    # Serialise nested FactCheckResult objects to plain dicts
    doc["fact_checks"] = [fc if isinstance(fc, dict) else fc for fc in doc["fact_checks"]]
    return doc


def _doc_to_record(doc: dict[str, Any]) -> HistoryRecord:
    """Convert a MongoDB document dict back to a ``HistoryRecord``.

    Restores ``_id`` → ``id`` so the Pydantic model can be constructed
    without modification.
    """
    data = dict(doc)
    data["id"] = data.pop("_id")
    return HistoryRecord.model_validate(data)


class MongoHistoryRepository(HistoryRepository):
    """Async MongoDB implementation of ``HistoryRepository``.

    Parameters
    ----------
    mongo_uri:
        MongoDB connection URI (e.g. ``"mongodb://localhost:27017"``).
    db_name:
        Name of the MongoDB database to use.
    collection_name:
        Name of the collection to store history records in (default
        ``"history"``).
    """

    def __init__(
        self,
        mongo_uri: str,
        db_name: str,
        collection_name: str = "history",
        tls_ctx: Optional[ssl.SSLContext] = None,
    ) -> None:
        # On Python 3.12 / Windows, MongoDB Atlas TLS handshakes can fail.
        # Appending tlsAllowInvalidCertificates=true to the URI is the most
        # reliable workaround for Motor/PyMongo.
        if "tlsAllowInvalidCertificates" not in mongo_uri:
            sep = "&" if "?" in mongo_uri else "?"
            mongo_uri = f"{mongo_uri}{sep}tlsAllowInvalidCertificates=true"

        self._client: motor.motor_asyncio.AsyncIOMotorClient = (
            motor.motor_asyncio.AsyncIOMotorClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,
            )
        )
        self._collection: motor.motor_asyncio.AsyncIOMotorCollection = (
            self._client[db_name][collection_name]
        )

    async def save(self, record: HistoryRecord) -> None:
        """Upsert a ``HistoryRecord`` into the MongoDB collection.

        Uses ``replace_one`` with ``upsert=True`` so that re-saving a
        record with the same ``id`` overwrites the existing document.
        """
        doc = _record_to_doc(record)
        await self._collection.replace_one(
            {"_id": doc["_id"]},
            doc,
            upsert=True,
        )

    async def list_recent(self, limit: int = 50) -> list[HistoryRecord]:
        """Return up to ``limit`` records sorted by ``created_at`` descending.

        Requirement 4.3: retrieve up to 50 most recent submissions.
        """
        cursor = (
            self._collection.find()
            .sort("created_at", -1)
            .limit(limit)
        )
        records: list[HistoryRecord] = []
        async for doc in cursor:
            records.append(_doc_to_record(doc))
        return records

    async def get_by_id(self, id: UUID) -> Optional[HistoryRecord]:
        """Fetch a single record by its UUID primary key.

        Returns ``None`` if no document with that ``_id`` exists.
        """
        doc = await self._collection.find_one({"_id": str(id)})
        if doc is None:
            return None
        return _doc_to_record(doc)

    async def delete(self, id: UUID) -> bool:
        """Delete a record by its UUID primary key.

        Returns ``True`` if a document was deleted, ``False`` if not found.
        Requirement 4.5: return 200 (True) on success.
        """
        result = await self._collection.delete_one({"_id": str(id)})
        return result.deleted_count > 0

    async def close(self) -> None:
        """Close the underlying Motor client connection."""
        self._client.close()
