"""
Property-based tests for History Persistence Round-Trip.

# Feature: fake-news-detector, Property 6: History Persistence Round-Trip

Property 6: History Persistence Round-Trip
  For any successfully generated Prediction, storing it to the History_Store
  and then retrieving it by its `id` SHALL return a record whose `label`,
  `confidence`, `suspicious_phrases`, and `explanation` fields are equal to
  those of the original Prediction.

Validates: Requirements 4.1, 4.4
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.db.repository import InMemoryHistoryRepository
from backend.schemas import FactCheckResult, HistoryRecord


# ---------------------------------------------------------------------------
# Hypothesis strategies for HistoryRecord
# ---------------------------------------------------------------------------

_st_label = st.sampled_from(["Real", "Fake"])
_st_confidence = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_st_trust_rating = st.one_of(
    st.none(),
    st.sampled_from(["High", "Medium", "Low", "Unknown"]),
)
_st_language = st.sampled_from(["en", "te", "hi"])
_st_phrase = st.text(min_size=1, max_size=100)
_st_fact_check = st.builds(
    FactCheckResult,
    claim=st.text(min_size=1, max_size=200),
    rating=st.text(min_size=1, max_size=50),
    source=st.text(min_size=1, max_size=100),
)
_st_timestamp = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 12, 31),
    timezones=st.just(timezone.utc),
)
_st_history_record = st.builds(
    HistoryRecord,
    id=st.uuids(),
    input_text=st.one_of(st.none(), st.text(min_size=1, max_size=500)),
    input_url=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    label=_st_label,
    confidence=_st_confidence,
    suspicious_phrases=st.lists(_st_phrase, max_size=10),
    explanation=st.text(min_size=1, max_size=500),
    fact_checks=st.lists(_st_fact_check, max_size=5),
    trust_rating=_st_trust_rating,
    language=_st_language,
    created_at=_st_timestamp,
)


# ---------------------------------------------------------------------------
# Property 6: History Persistence Round-Trip
# ---------------------------------------------------------------------------


@given(record=_st_history_record)
@settings(max_examples=20)
def test_property6_history_persistence_round_trip(record: HistoryRecord) -> None:
    """
    **Validates: Requirements 4.1, 4.4**

    Property 6: History Persistence Round-Trip

    For any successfully generated Prediction, storing it to the History_Store
    and then retrieving it by its `id` SHALL return a record whose `label`,
    `confidence`, `suspicious_phrases`, and `explanation` fields are equal to
    those of the original Prediction.
    """
    # Feature: fake-news-detector, Property 6: History Persistence Round-Trip
    repo = InMemoryHistoryRepository()

    # Save the record to the in-memory repository
    asyncio.run(repo.save(record))

    # Retrieve by id
    retrieved = asyncio.run(repo.get_by_id(record.id))

    # Assert the record was found
    assert retrieved is not None, (
        f"Record with id={record.id} was not found after saving.\n"
        f"Original: {record!r}"
    )

    # Assert label is preserved
    assert retrieved.label == record.label, (
        f"label mismatch.\n"
        f"Expected: {record.label!r}\n"
        f"Got:      {retrieved.label!r}"
    )

    # Assert confidence is preserved
    assert retrieved.confidence == record.confidence, (
        f"confidence mismatch.\n"
        f"Expected: {record.confidence}\n"
        f"Got:      {retrieved.confidence}"
    )

    # Assert suspicious_phrases are preserved
    assert retrieved.suspicious_phrases == record.suspicious_phrases, (
        f"suspicious_phrases mismatch.\n"
        f"Expected: {record.suspicious_phrases!r}\n"
        f"Got:      {retrieved.suspicious_phrases!r}"
    )

    # Assert explanation is preserved
    assert retrieved.explanation == record.explanation, (
        f"explanation mismatch.\n"
        f"Expected: {record.explanation!r}\n"
        f"Got:      {retrieved.explanation!r}"
    )
