"""
Property-based tests for PredictionService.predict() and PredictionResponse schema.

# Feature: fake-news-detector, Property 1: Prediction Response Round-Trip Integrity
# Feature: fake-news-detector, Property 3: Valid Submission Always Produces a Structurally Valid Prediction
# Feature: fake-news-detector, Property 4: Suspicious Phrases Are Substrings of Input

Property 1: Prediction Response Round-Trip Integrity
  For any valid PredictionResponse object, serializing to JSON with
  .model_dump_json() and deserializing with PredictionResponse.model_validate_json()
  SHALL produce an object equal to the original.

Validates: Requirements 12.4

Property 3: Valid Submission Always Produces a Structurally Valid Prediction
  For any valid (non-empty) input text, PredictionService.predict() SHALL return
  a PredictionResult where:
    - label âˆˆ {"Real", "Fake"}
    - confidence âˆˆ [0.0, 1.0]
    - every element of suspicious_phrases is a contiguous substring of the input
    - explanation is a non-empty string

Validates: Requirements 2.1, 2.5, 2.6

Property 4: Suspicious Phrases Are Substrings of Input
  For any input text and the resulting Prediction, every string in
  `suspicious_phrases` SHALL appear as a contiguous substring within the
  original input text.

Validates: Requirements 2.5
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import joblib
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from ml.prediction_service import PredictionService
from schemas import FactCheckResult, PredictionResponse


# ---------------------------------------------------------------------------
# Hypothesis strategies for PredictionResponse
# ---------------------------------------------------------------------------

_st_label = st.sampled_from(["Real", "Fake"])
_st_confidence = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
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
_st_prediction_response = st.builds(
    PredictionResponse,
    id=st.uuids(),
    label=_st_label,
    confidence=_st_confidence,
    suspicious_phrases=st.lists(_st_phrase, max_size=10),
    explanation=st.text(min_size=1, max_size=500),
    fact_checks=st.lists(_st_fact_check, max_size=5),
    trust_rating=_st_trust_rating,
    language=_st_language,
    timestamp=_st_timestamp,
)


# ---------------------------------------------------------------------------
# Property 1: Prediction Response Round-Trip Integrity
# ---------------------------------------------------------------------------


@given(response=_st_prediction_response)
@settings(max_examples=20)
def test_property1_prediction_response_round_trip_integrity(
    response: PredictionResponse,
) -> None:
    """
    **Validates: Requirements 12.4**

    Property 1: Prediction Response Round-Trip Integrity

    For any valid PredictionResponse object, serializing to JSON with
    .model_dump_json() and deserializing with PredictionResponse.model_validate_json()
    SHALL produce an object equal to the original.
    """
    # Feature: fake-news-detector, Property 1: Prediction Response Round-Trip Integrity
    json_str = response.model_dump_json()
    restored = PredictionResponse.model_validate_json(json_str)
    assert restored == response, (
        f"Round-trip failed.\n"
        f"Original:  {response!r}\n"
        f"Restored:  {restored!r}\n"
        f"JSON:      {json_str}"
    )


# ---------------------------------------------------------------------------
# Shared artifact fixture (module-scoped so it is built only once)
# ---------------------------------------------------------------------------


def _build_artifacts(tmp_path: Path) -> dict[str, Path]:
    """Train a tiny TF-IDF + LR model and save artifacts to *tmp_path*."""
    texts = [
        # fake
        "breaking news shocking scandal exposed government lies",
        "you won't believe what politicians are hiding from you",
        "secret conspiracy revealed mainstream media won't report",
        "shocking truth about vaccines big pharma doesn't want you to know",
        # real
        "the president signed the infrastructure bill into law today",
        "scientists publish new research on climate change in nature journal",
        "federal reserve raises interest rates by quarter point",
        "olympic committee announces host city for 2032 summer games",
    ]
    labels = [1, 1, 1, 1, 0, 0, 0, 0]

    vectorizer = TfidfVectorizer(max_features=200, ngram_range=(1, 2), sublinear_tf=True)
    X = vectorizer.fit_transform(texts)

    lr_model = LogisticRegression(max_iter=1000, C=1.0)
    lr_model.fit(X, labels)

    vp = tmp_path / "tfidf_vectorizer.joblib"
    lp = tmp_path / "logistic_regression.joblib"
    mp = tmp_path / "model_metadata.json"

    joblib.dump(vectorizer, vp)
    joblib.dump(lr_model, lp)
    mp.write_text(json.dumps({"lr_accuracy": 1.0, "n_features": 200}))

    return {"vectorizer": vp, "lr_model": lp, "metadata": mp}


@pytest.fixture(scope="module")
def artifact_paths(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("prop4_artifacts")
    return _build_artifacts(tmp)


# ---------------------------------------------------------------------------
# Helper: build a PredictionService with a mocked LR model
# ---------------------------------------------------------------------------


def _make_service_with_mock_lr(artifact_paths: dict[str, Path]) -> PredictionService:
    """Return a PredictionService that uses the real TF-IDF vectorizer but a
    mocked LogisticRegression that always predicts class 1 ("Fake") with 80%
    confidence.  This ensures predict() exercises the full phrase-extraction
    path without requiring a trained model that generalises well."""
    mock_lr = MagicMock()
    mock_lr.predict_proba.return_value = np.array([[0.2, 0.8]])

    svc = PredictionService(
        vectorizer_path=artifact_paths["vectorizer"],
        lr_model_path=artifact_paths["lr_model"],
        metadata_path=artifact_paths["metadata"],
        top_n=10,
    )
    # Inject the mock so the LR model doesn't need to handle arbitrary vocab sizes.
    svc._lr_model = mock_lr
    return svc


# ---------------------------------------------------------------------------
# Property 4: Suspicious Phrases Are Substrings of Input
# ---------------------------------------------------------------------------


@given(text=st.text(min_size=1, max_size=10_000))
@settings(max_examples=20)
def test_property4_suspicious_phrases_are_substrings(
    text: str,
    artifact_paths,
) -> None:
    """
    **Validates: Requirements 2.5**

    Property 4: Suspicious Phrases Are Substrings of Input

    For any non-empty string input (up to 10,000 characters), every phrase
    returned in `result.suspicious_phrases` must be a contiguous substring
    of the original input text (case-insensitive, because `preprocess()`
    lowercases the text before vectorisation).
    """
    # Feature: fake-news-detector, Property 4: Suspicious Phrases Are Substrings of Input
    svc = _make_service_with_mock_lr(artifact_paths)

    result = svc.predict(text)

    original_lower = text.lower()
    for phrase in result.suspicious_phrases:
        assert phrase in original_lower, (
            f"Phrase {phrase!r} is not a substring of the lowercased input.\n"
            f"Input (first 200 chars): {text[:200]!r}\n"
            f"All phrases: {result.suspicious_phrases}"
        )


# ---------------------------------------------------------------------------
# Property 3: Valid Submission Always Produces a Structurally Valid Prediction
# ---------------------------------------------------------------------------


@given(text=st.text(min_size=1, max_size=10_000))
@settings(max_examples=20)
def test_property3_valid_submission_produces_structurally_valid_prediction(
    text: str,
    artifact_paths,
) -> None:
    """
    **Validates: Requirements 2.1, 2.5, 2.6**

    Property 3: Valid Submission Always Produces a Structurally Valid Prediction

    For any non-empty string input (up to 10,000 characters), PredictionService.predict()
    must return a PredictionResult satisfying ALL of:
      - label âˆˆ {"Real", "Fake"}
      - confidence âˆˆ [0.0, 1.0]
      - every element of suspicious_phrases is a contiguous substring of the input
      - explanation is a non-empty string
    """
    # Feature: fake-news-detector, Property 3: Valid Submission Always Produces a Structurally Valid Prediction
    svc = _make_service_with_mock_lr(artifact_paths)

    result = svc.predict(text)

    # label âˆˆ {"Real", "Fake"}
    assert result.label in {"Real", "Fake"}, (
        f"label {result.label!r} is not one of {{'Real', 'Fake'}}"
    )

    # confidence âˆˆ [0.0, 1.0]
    assert 0.0 <= result.confidence <= 1.0, (
        f"confidence {result.confidence} is outside [0.0, 1.0]"
    )

    # every suspicious_phrase is a contiguous substring of the input (case-insensitive)
    original_lower = text.lower()
    for phrase in result.suspicious_phrases:
        assert phrase in original_lower, (
            f"Phrase {phrase!r} is not a substring of the lowercased input.\n"
            f"Input (first 200 chars): {text[:200]!r}\n"
            f"All phrases: {result.suspicious_phrases}"
        )

    # explanation is a non-empty string
    assert isinstance(result.explanation, str) and len(result.explanation) > 0, (
        f"explanation must be a non-empty string, got {result.explanation!r}"
    )
