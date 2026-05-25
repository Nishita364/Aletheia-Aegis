"""
Unit tests for the HistoryRepository interface and InMemoryHistoryRepository.

Tests cover:
- save and retrieve a record by id
- list_recent returns up to 50 records ordered by created_at desc
- get_by_id returns None for a missing id
- delete returns True when the record exists, False when it does not

Uses InMemoryHistoryRepository so no real MongoDB is required.

Requirements: 4.1, 4.3, 4.5, 4.6
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import List

import pytest

from backend.schemas import HistoryRecord, FactCheckResult
from backend.db.repository import InMemoryHistoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_record(
    *,
    id: uuid.UUID | None = None,
    label: str = "Real",
    confidence: float = 0.9,
    created_at: datetime | None = None,
    input_text: str = "Sample article text.",
) -> HistoryRecord:
    """Create a minimal valid HistoryRecord for testing."""
    return HistoryRecord(
        id=id or uuid.uuid4(),
        input_text=input_text,
        input_url=None,
        label=label,  # type: ignore[arg-type]
        confidence=confidence,
        suspicious_phrases=["suspicious"],
        explanation="This article appears to be real.",
        fact_checks=[],
        trust_rating=None,
        language="en",
        created_at=created_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_retrieve_by_id() -> None:
    """Saving a record and retrieving it by id returns the same record."""
    repo = InMemoryHistoryRepository()
    record = make_record()

    await repo.save(record)
    retrieved = await repo.get_by_id(record.id)

    assert retrieved is not None
    assert retrieved.id == record.id
    assert retrieved.label == record.label
    assert retrieved.confidence == record.confidence
    assert retrieved.explanation == record.explanation
    assert retrieved.suspicious_phrases == record.suspicious_phrases


@pytest.mark.asyncio
async def test_save_overwrites_existing_record() -> None:
    """Re-saving a record with the same id overwrites the previous version."""
    repo = InMemoryHistoryRepository()
    record_id = uuid.uuid4()

    original = make_record(id=record_id, label="Real", confidence=0.8)
    updated = make_record(id=record_id, label="Fake", confidence=0.6)

    await repo.save(original)
    await repo.save(updated)

    retrieved = await repo.get_by_id(record_id)
    assert retrieved is not None
    assert retrieved.label == "Fake"
    assert retrieved.confidence == 0.6


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing_id() -> None:
    """get_by_id returns None when no record with that id exists."""
    repo = InMemoryHistoryRepository()
    missing_id = uuid.uuid4()

    result = await repo.get_by_id(missing_id)

    assert result is None


@pytest.mark.asyncio
async def test_list_recent_returns_records_ordered_by_created_at_desc() -> None:
    """list_recent returns records sorted newest-first."""
    repo = InMemoryHistoryRepository()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Insert 5 records with different timestamps
    records = [
        make_record(created_at=base_time + timedelta(hours=i))
        for i in range(5)
    ]
    for r in records:
        await repo.save(r)

    result = await repo.list_recent()

    # Should be newest first
    assert len(result) == 5
    for i in range(len(result) - 1):
        assert result[i].created_at >= result[i + 1].created_at


@pytest.mark.asyncio
async def test_list_recent_respects_limit() -> None:
    """list_recent returns at most ``limit`` records."""
    repo = InMemoryHistoryRepository()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    for i in range(10):
        await repo.save(make_record(created_at=base_time + timedelta(hours=i)))

    result = await repo.list_recent(limit=3)

    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_recent_default_limit_is_50() -> None:
    """list_recent with default limit returns at most 50 records."""
    repo = InMemoryHistoryRepository()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Insert 60 records
    for i in range(60):
        await repo.save(make_record(created_at=base_time + timedelta(minutes=i)))

    result = await repo.list_recent()

    assert len(result) == 50


@pytest.mark.asyncio
async def test_list_recent_returns_newest_50_when_more_exist() -> None:
    """When more than 50 records exist, list_recent returns the 50 newest."""
    repo = InMemoryHistoryRepository()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    records = [
        make_record(created_at=base_time + timedelta(minutes=i))
        for i in range(60)
    ]
    for r in records:
        await repo.save(r)

    result = await repo.list_recent()

    # The 50 newest should be the last 50 inserted (indices 10..59)
    expected_newest = sorted(records, key=lambda r: r.created_at, reverse=True)[:50]
    result_ids = {r.id for r in result}
    expected_ids = {r.id for r in expected_newest}
    assert result_ids == expected_ids


@pytest.mark.asyncio
async def test_list_recent_empty_repository() -> None:
    """list_recent on an empty repository returns an empty list."""
    repo = InMemoryHistoryRepository()

    result = await repo.list_recent()

    assert result == []


@pytest.mark.asyncio
async def test_delete_returns_true_when_record_exists() -> None:
    """delete returns True when the record is found and removed."""
    repo = InMemoryHistoryRepository()
    record = make_record()
    await repo.save(record)

    deleted = await repo.delete(record.id)

    assert deleted is True
    # Confirm it's gone
    assert await repo.get_by_id(record.id) is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_record_not_found() -> None:
    """delete returns False when no record with that id exists."""
    repo = InMemoryHistoryRepository()
    missing_id = uuid.uuid4()

    deleted = await repo.delete(missing_id)

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_does_not_affect_other_records() -> None:
    """Deleting one record leaves other records intact."""
    repo = InMemoryHistoryRepository()
    record_a = make_record()
    record_b = make_record()

    await repo.save(record_a)
    await repo.save(record_b)

    await repo.delete(record_a.id)

    assert await repo.get_by_id(record_a.id) is None
    assert await repo.get_by_id(record_b.id) is not None


@pytest.mark.asyncio
async def test_save_preserves_all_fields() -> None:
    """Saving a record with all fields populated preserves them on retrieval."""
    repo = InMemoryHistoryRepository()
    record = HistoryRecord(
        id=uuid.uuid4(),
        input_text="Full article text here.",
        input_url="https://example.com/article",
        label="Fake",
        confidence=0.75,
        suspicious_phrases=["breaking news", "shocking"],
        explanation="Multiple sensationalist phrases detected.",
        fact_checks=[
            FactCheckResult(
                claim="The claim",
                rating="False",
                source="FactChecker.org",
            )
        ],
        trust_rating="Low",
        language="en",
        created_at=datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
    )

    await repo.save(record)
    retrieved = await repo.get_by_id(record.id)

    assert retrieved is not None
    assert retrieved.input_text == record.input_text
    assert retrieved.input_url == record.input_url
    assert retrieved.label == record.label
    assert retrieved.confidence == record.confidence
    assert retrieved.suspicious_phrases == record.suspicious_phrases
    assert retrieved.explanation == record.explanation
    assert len(retrieved.fact_checks) == 1
    assert retrieved.fact_checks[0].claim == "The claim"
    assert retrieved.trust_rating == record.trust_rating
    assert retrieved.language == record.language
    assert retrieved.created_at == record.created_at
