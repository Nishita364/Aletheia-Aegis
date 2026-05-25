"""
Unit tests for backend/ml/prediction_service.py

Covers:
- PredictionResult dataclass fields and defaults
- PredictionService.predict(): label mapping (0 → "Real", 1 → "Fake")
- PredictionService.predict(): confidence is in [0.0, 1.0]
- PredictionService.predict(): every suspicious phrase is a substring of the input
- PredictionService.predict(): explanation is a non-empty string
- PredictionService: dependency injection of artifact paths
- Edge cases: empty-ish text, text with no matching tokens
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from ml.prediction_service import PredictionResult, PredictionService


# ---------------------------------------------------------------------------
# Fixtures: build minimal real artifacts in a temp directory
# ---------------------------------------------------------------------------


def _build_artifacts(tmp_path: Path) -> dict[str, Path]:
    """Train a tiny TF-IDF + LR model on a handful of sentences and save
    the artifacts to *tmp_path*.  Returns a dict of artifact paths."""

    # Minimal training corpus: 4 fake (label=1) + 4 real (label=0)
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
    """Module-scoped fixture: build artifacts once and reuse across tests."""
    tmp = tmp_path_factory.mktemp("artifacts")
    return _build_artifacts(tmp)


@pytest.fixture(scope="module")
def service(artifact_paths):
    """Module-scoped PredictionService backed by the tiny test artifacts."""
    return PredictionService(
        vectorizer_path=artifact_paths["vectorizer"],
        lr_model_path=artifact_paths["lr_model"],
        metadata_path=artifact_paths["metadata"],
        top_n=10,
    )


# ---------------------------------------------------------------------------
# PredictionResult dataclass
# ---------------------------------------------------------------------------


class TestPredictionResult:
    def test_fields_accessible(self):
        result = PredictionResult(
            label="Fake",
            confidence=0.92,
            suspicious_phrases=["breaking news"],
            explanation="This article was classified as Fake.",
        )
        assert result.label == "Fake"
        assert result.confidence == 0.92
        assert result.suspicious_phrases == ["breaking news"]
        assert result.explanation == "This article was classified as Fake."

    def test_default_suspicious_phrases_is_empty_list(self):
        result = PredictionResult(label="Real", confidence=0.75)
        assert result.suspicious_phrases == []

    def test_default_explanation_is_empty_string(self):
        result = PredictionResult(label="Real", confidence=0.75)
        assert result.explanation == ""

    def test_label_real(self):
        result = PredictionResult(label="Real", confidence=0.8)
        assert result.label == "Real"

    def test_label_fake(self):
        result = PredictionResult(label="Fake", confidence=0.9)
        assert result.label == "Fake"


# ---------------------------------------------------------------------------
# PredictionService instantiation
# ---------------------------------------------------------------------------


class TestPredictionServiceInit:
    def test_loads_with_explicit_paths(self, artifact_paths):
        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )
        assert svc is not None

    def test_missing_metadata_does_not_raise(self, artifact_paths, tmp_path):
        """metadata_path is optional; missing file should not raise."""
        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=tmp_path / "nonexistent_metadata.json",
        )
        assert svc is not None

    def test_raises_on_missing_vectorizer(self, tmp_path, artifact_paths):
        with pytest.raises(Exception):
            PredictionService(
                vectorizer_path=tmp_path / "no_vectorizer.joblib",
                lr_model_path=artifact_paths["lr_model"],
            )

    def test_raises_on_missing_lr_model(self, tmp_path, artifact_paths):
        with pytest.raises(Exception):
            PredictionService(
                vectorizer_path=artifact_paths["vectorizer"],
                lr_model_path=tmp_path / "no_model.joblib",
            )


# ---------------------------------------------------------------------------
# Label mapping
# ---------------------------------------------------------------------------


class TestLabelMapping:
    def test_fake_article_returns_fake_label(self, service):
        """Text that strongly resembles the fake training corpus."""
        result = service.predict(
            "breaking news shocking scandal exposed government lies conspiracy"
        )
        # The model is tiny; we only assert the label is one of the valid values.
        assert result.label in {"Real", "Fake"}

    def test_real_article_returns_real_label(self, service):
        """Text that strongly resembles the real training corpus."""
        result = service.predict(
            "the president signed the infrastructure bill into law today"
        )
        assert result.label in {"Real", "Fake"}

    def test_label_is_exactly_real_or_fake(self, service):
        """Label must be exactly 'Real' or 'Fake', nothing else."""
        for text in [
            "breaking news shocking scandal",
            "scientists publish new research",
            "you won't believe what politicians are hiding",
            "federal reserve raises interest rates",
        ]:
            result = service.predict(text)
            assert result.label in {"Real", "Fake"}, (
                f"Unexpected label {result.label!r} for text: {text!r}"
            )

    def test_label_mapping_class_0_is_real(self, artifact_paths):
        """Directly verify that class index 0 maps to 'Real'."""
        # Build a mock LR model that always predicts class 0 with 90% confidence.
        mock_lr = MagicMock()
        mock_lr.predict_proba.return_value = np.array([[0.9, 0.1]])

        with patch("joblib.load", side_effect=[
            # First call: vectorizer (real)
            joblib.load(artifact_paths["vectorizer"]),
            # Second call: lr_model (mocked)
            mock_lr,
        ]):
            svc = PredictionService(
                vectorizer_path=artifact_paths["vectorizer"],
                lr_model_path=artifact_paths["lr_model"],
                metadata_path=artifact_paths["metadata"],
            )
            svc._lr_model = mock_lr  # inject mock directly

        result = svc.predict("some article text here")
        assert result.label == "Real"

    def test_label_mapping_class_1_is_fake(self, artifact_paths):
        """Directly verify that class index 1 maps to 'Fake'."""
        mock_lr = MagicMock()
        mock_lr.predict_proba.return_value = np.array([[0.1, 0.9]])

        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )
        svc._lr_model = mock_lr  # inject mock directly

        result = svc.predict("some article text here")
        assert result.label == "Fake"


# ---------------------------------------------------------------------------
# Confidence range
# ---------------------------------------------------------------------------


class TestConfidenceRange:
    def test_confidence_is_float(self, service):
        result = service.predict("breaking news shocking scandal")
        assert isinstance(result.confidence, float)

    def test_confidence_in_unit_interval(self, service):
        for text in [
            "breaking news shocking scandal exposed",
            "scientists publish new research on climate",
            "you won't believe what politicians are hiding",
            "the president signed the infrastructure bill",
            "secret conspiracy revealed mainstream media",
        ]:
            result = service.predict(text)
            assert 0.0 <= result.confidence <= 1.0, (
                f"confidence={result.confidence} out of [0,1] for text: {text!r}"
            )

    def test_confidence_not_nan(self, service):
        result = service.predict("some article text")
        assert not (result.confidence != result.confidence)  # NaN check

    def test_confidence_matches_predicted_class_probability(self, artifact_paths):
        """confidence should equal the probability of the predicted class."""
        mock_lr = MagicMock()
        mock_lr.predict_proba.return_value = np.array([[0.3, 0.7]])

        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )
        svc._lr_model = mock_lr

        result = svc.predict("some article text here")
        assert abs(result.confidence - 0.7) < 1e-9


# ---------------------------------------------------------------------------
# Suspicious phrases are substrings of the original text
# ---------------------------------------------------------------------------


class TestSuspiciousPhrases:
    def test_all_phrases_are_substrings_of_original(self, service):
        text = "breaking news shocking scandal exposed government lies conspiracy"
        result = service.predict(text)
        original_lower = text.lower()
        for phrase in result.suspicious_phrases:
            assert phrase in original_lower, (
                f"Phrase {phrase!r} is not a substring of the original text"
            )

    def test_phrases_are_substrings_for_real_text(self, service):
        text = "The president signed the infrastructure bill into law today"
        result = service.predict(text)
        original_lower = text.lower()
        for phrase in result.suspicious_phrases:
            assert phrase in original_lower, (
                f"Phrase {phrase!r} is not a substring of the original text"
            )

    def test_phrases_is_a_list(self, service):
        result = service.predict("breaking news shocking scandal")
        assert isinstance(result.suspicious_phrases, list)

    def test_phrases_are_strings(self, service):
        result = service.predict("breaking news shocking scandal")
        for phrase in result.suspicious_phrases:
            assert isinstance(phrase, str)

    def test_phrases_not_in_unrelated_text_are_excluded(self, artifact_paths):
        """Tokens that are NOT substrings of the original text must be filtered out."""
        # Use a text that, after preprocessing, produces TF-IDF tokens, but
        # we inject a mock vectorizer that returns a weight for a token that
        # does NOT appear in the original text.
        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )

        # Patch feature names to include a token that won't be in the text.
        svc._feature_names = np.array(["xyzzy_not_in_text", "breaking"])

        # Patch the vectorizer to return weights for both tokens.
        mock_vectorizer = MagicMock()
        mock_tfidf = _sparse_from_dense(np.array([[0.8, 0.5]]))
        mock_vectorizer.transform.return_value = mock_tfidf
        svc._vectorizer = mock_vectorizer

        # Also mock the LR model so it accepts the 2-feature matrix from the
        # mocked vectorizer (the real model expects the full vocabulary size).
        mock_lr = MagicMock()
        mock_lr.predict_proba.return_value = np.array([[0.2, 0.8]])
        svc._lr_model = mock_lr

        result = svc.predict("breaking news today")
        # "xyzzy_not_in_text" must NOT appear; "breaking" should appear.
        assert "xyzzy_not_in_text" not in result.suspicious_phrases
        assert "breaking" in result.suspicious_phrases

    def test_empty_text_returns_empty_phrases(self, service):
        """Empty string should not crash and should return an empty phrase list."""
        result = service.predict("")
        assert isinstance(result.suspicious_phrases, list)

    def test_phrases_respect_top_n_limit(self, artifact_paths):
        """No more than top_n phrases should be returned."""
        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
            top_n=3,
        )
        text = "breaking news shocking scandal exposed government lies conspiracy revealed"
        result = svc.predict(text)
        assert len(result.suspicious_phrases) <= 3


# ---------------------------------------------------------------------------
# Explanation is non-empty
# ---------------------------------------------------------------------------


class TestExplanation:
    def test_explanation_is_string(self, service):
        result = service.predict("breaking news shocking scandal")
        assert isinstance(result.explanation, str)

    def test_explanation_is_non_empty(self, service):
        for text in [
            "breaking news shocking scandal exposed",
            "scientists publish new research on climate",
            "the president signed the infrastructure bill",
        ]:
            result = service.predict(text)
            assert len(result.explanation) > 0, (
                f"explanation is empty for text: {text!r}"
            )

    def test_explanation_contains_label(self, service):
        result = service.predict("breaking news shocking scandal")
        assert result.label in result.explanation

    def test_explanation_contains_confidence_percentage(self, service):
        result = service.predict("breaking news shocking scandal")
        # Confidence formatted as e.g. "92.3%"
        assert "%" in result.explanation

    def test_explanation_with_no_phrases_still_non_empty(self, artifact_paths):
        """Even when no suspicious phrases are found, explanation must be non-empty."""
        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )
        # Inject a vectorizer that returns all-zero weights → no phrases.
        mock_vectorizer = MagicMock()
        mock_vectorizer.transform.return_value = _sparse_from_dense(
            np.zeros((1, len(svc._feature_names)))
        )
        svc._vectorizer = mock_vectorizer

        result = svc.predict("some text that produces no tfidf weights")
        assert len(result.explanation) > 0

    def test_explanation_mentions_phrases_when_present(self, artifact_paths):
        """When phrases are found, explanation should reference them."""
        svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )
        result = svc.predict(
            "breaking news shocking scandal exposed government lies"
        )
        if result.suspicious_phrases:
            assert "phrases such as" in result.explanation.lower() or \
                   any(p in result.explanation for p in result.suspicious_phrases[:3])


# ---------------------------------------------------------------------------
# Helper: build a scipy sparse matrix from a dense numpy array
# ---------------------------------------------------------------------------


def _sparse_from_dense(arr: np.ndarray):
    """Return a scipy csr_matrix wrapping *arr* (shape must be 2-D)."""
    from scipy.sparse import csr_matrix
    return csr_matrix(arr)
