"""
PredictionService: loads trained ML artifacts and exposes a predict() method.

Supports two modes:
  - English ("en"): separate TfidfVectorizer + LogisticRegression files
  - Indic ("hi", "te"): full sklearn Pipeline saved as the vectorizer file
    (FeatureUnion of word + char TF-IDF → LogisticRegression)

The pipeline mode is detected automatically from the metadata file.

Requirements: 2.1, 2.2, 2.5, 2.6
"""

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

from backend.ml.data_loader import preprocess

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------

_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
_DEFAULT_VECTORIZER_PATH = _ARTIFACTS_DIR / "tfidf_vectorizer.joblib"
_DEFAULT_LR_MODEL_PATH   = _ARTIFACTS_DIR / "logistic_regression.joblib"
_DEFAULT_METADATA_PATH   = _ARTIFACTS_DIR / "model_metadata.json"

# Languages that use native Indic pipeline models
_INDIC_LANGUAGES: frozenset[str] = frozenset({"hi", "te"})

# Label mapping: 0 → Real, 1 → Fake
_LABEL_MAP: dict[int, str] = {0: "Real", 1: "Fake"}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class PredictionResult:
    """Output of a single prediction call."""

    label: str
    confidence: float
    suspicious_phrases: list[str] = field(default_factory=list)
    explanation: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PredictionService:
    """Loads ML artifacts at instantiation and exposes predict()."""

    def __init__(
        self,
        vectorizer_path: Optional[Path] = None,
        lr_model_path: Optional[Path] = None,
        metadata_path: Optional[Path] = None,
        top_n: int = 10,
        language: str = "en",
    ) -> None:
        self._language = language
        self._top_n = top_n

        # Resolve artifact paths
        if vectorizer_path is not None:
            vp = Path(vectorizer_path)
        elif language in _INDIC_LANGUAGES:
            vp = _ARTIFACTS_DIR / f"{language}_tfidf_vectorizer.joblib"
        else:
            vp = _DEFAULT_VECTORIZER_PATH

        if lr_model_path is not None:
            lp = Path(lr_model_path)
        elif language in _INDIC_LANGUAGES:
            lp = _ARTIFACTS_DIR / f"{language}_logistic_regression.joblib"
        else:
            lp = _DEFAULT_LR_MODEL_PATH

        mp = (
            Path(metadata_path) if metadata_path is not None
            else (_ARTIFACTS_DIR / f"{language}_model_metadata.json"
                  if language in _INDIC_LANGUAGES else _DEFAULT_METADATA_PATH)
        )

        # Load metadata to detect pipeline mode
        self._metadata: dict = {}
        if mp.exists():
            self._metadata = json.loads(mp.read_text())

        self._pipeline_mode: bool = bool(self._metadata.get("pipeline_mode", False))

        logger.info(
            "Loading %s model (pipeline_mode=%s) from %s",
            language.upper(), self._pipeline_mode, vp,
        )

        if self._pipeline_mode:
            # The "vectorizer" file IS the full sklearn Pipeline
            self._pipeline = joblib.load(vp)
            self._vectorizer = None
            self._lr_model = None
            self._feature_names = np.array([])
        else:
            # Legacy mode: separate vectorizer + LR
            self._pipeline = None
            self._vectorizer = joblib.load(vp)
            self._lr_model = joblib.load(lp)
            self._feature_names = np.array(
                self._vectorizer.get_feature_names_out()
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, text: str) -> PredictionResult:
        """Classify *text* and return a PredictionResult."""

        # Preprocess
        if self._language in _INDIC_LANGUAGES:
            processed = unicodedata.normalize("NFC", text)
        else:
            processed = preprocess(text)

        # Minimum length guard
        word_count = len(processed.split())
        if word_count < 5:
            return PredictionResult(
                label="Fake",
                confidence=0.50,
                suspicious_phrases=[],
                explanation=(
                    "The text is too short to analyse reliably. "
                    "Please provide more text for accurate results."
                ),
            )

        if self._pipeline_mode:
            return self._predict_pipeline(processed, text)
        else:
            return self._predict_legacy(processed, text)

    # ------------------------------------------------------------------
    # Pipeline mode (Indic languages after retraining)
    # ------------------------------------------------------------------

    def _predict_pipeline(self, processed: str, original_text: str) -> PredictionResult:
        """Use the full sklearn Pipeline for prediction."""
        proba = self._pipeline.predict_proba([processed])[0]
        predicted_class: int = int(np.argmax(proba))
        confidence: float = float(proba[predicted_class])
        label: str = _LABEL_MAP.get(predicted_class, "Unknown")

        # Extract word-level tokens from the pipeline's word vectorizer
        suspicious_phrases = self._extract_phrases_from_pipeline(processed, original_text)

        explanation = self._generate_explanation(label, confidence, suspicious_phrases)
        return PredictionResult(
            label=label,
            confidence=confidence,
            suspicious_phrases=suspicious_phrases,
            explanation=explanation,
        )

    def _extract_phrases_from_pipeline(self, processed: str, original_text: str) -> list[str]:
        """Extract top word tokens from the pipeline's word TF-IDF sub-vectorizer."""
        try:
            feature_union = self._pipeline.named_steps["features"]
            word_vec = dict(feature_union.transformer_list)["word"]
            tfidf_matrix = word_vec.transform([processed])
            weights: np.ndarray = tfidf_matrix.toarray()[0]
            nonzero = np.where(weights > 0)[0]
            if len(nonzero) == 0:
                return []
            sorted_idx = nonzero[np.argsort(weights[nonzero])[::-1]][: self._top_n]
            feature_names = np.array(word_vec.get_feature_names_out())
            candidates = [str(feature_names[i]) for i in sorted_idx]
            original_lower = original_text.lower()
            return [t for t in candidates if t in original_lower]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Legacy mode (English model)
    # ------------------------------------------------------------------

    def _predict_legacy(self, processed: str, original_text: str) -> PredictionResult:
        """Use separate vectorizer + LR for prediction (English model)."""
        tfidf_matrix = self._vectorizer.transform([processed])
        proba = self._lr_model.predict_proba(tfidf_matrix)[0]
        predicted_class: int = int(np.argmax(proba))
        confidence: float = float(proba[predicted_class])
        label: str = _LABEL_MAP.get(predicted_class, "Unknown")

        suspicious_phrases = self._extract_suspicious_phrases(tfidf_matrix, original_text)
        explanation = self._generate_explanation(label, confidence, suspicious_phrases)
        return PredictionResult(
            label=label,
            confidence=confidence,
            suspicious_phrases=suspicious_phrases,
            explanation=explanation,
        )

    def _extract_suspicious_phrases(self, tfidf_matrix, original_text: str) -> list[str]:
        weights: np.ndarray = tfidf_matrix.toarray()[0]
        nonzero_indices = np.where(weights > 0)[0]
        if len(nonzero_indices) == 0:
            return []
        sorted_indices = nonzero_indices[np.argsort(weights[nonzero_indices])[::-1]]
        top_indices = sorted_indices[: self._top_n]
        candidate_tokens = [str(self._feature_names[i]) for i in top_indices]
        original_lower = original_text.lower()
        return [t for t in candidate_tokens if t in original_lower]

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _generate_explanation(self, label: str, confidence: float, phrases: list[str]) -> str:
        if phrases:
            top_phrases = ", ".join(f'"{p}"' for p in phrases[:5])
            return (
                f'This article was classified as {label} with '
                f'{confidence:.1%} confidence based on phrases such as: '
                f'{top_phrases}.'
            )
        return f'This article was classified as {label} with {confidence:.1%} confidence.'
