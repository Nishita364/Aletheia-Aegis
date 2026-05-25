"""
LanguageRouter: detects the language of input text and routes it to the
appropriate language-specific PredictionService pipeline.

Supported languages:
  - English (en)  → English TF-IDF pipeline (trained on English CSV dataset)
  - Telugu  (te)  → Telugu TF-IDF pipeline  (trained on Telugu .txt dataset)
  - Hindi   (hi)  → Hindi TF-IDF pipeline   (trained on Hindi .txt dataset)

All other detected languages raise UnsupportedLanguageError, which the API
layer maps to a 400 UNSUPPORTED_LANGUAGE response.

No translation is performed — each language uses its own native model.

Requirements: 10.2, 10.3, 10.4
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Dict

from langdetect import LangDetectException, detect

from backend.ml.prediction_service import PredictionResult, PredictionService

logger = logging.getLogger(__name__)

# Languages that require Unicode NFC normalisation before prediction.
_NFC_LANGUAGES: frozenset[str] = frozenset({"te", "hi"})

# All languages supported by the router.
_SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "te", "hi"})


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class UnsupportedLanguageError(Exception):
    """Raised when the detected language is not supported by any pipeline.

    Attributes
    ----------
    language_code:
        The ISO 639-1 language code detected by langdetect, or ``None``
        when detection itself failed.
    """

    def __init__(self, language_code: str | None = None) -> None:
        self.language_code = language_code
        msg = (
            f"Unsupported language: {language_code!r}. "
            "Supported languages are: en (English), te (Telugu), hi (Hindi)."
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# LanguageRouter
# ---------------------------------------------------------------------------


class LanguageRouter:
    """Routes text to the appropriate :class:`PredictionService` pipeline.

    Each language has its own native model — no translation is performed.

    Parameters
    ----------
    pipelines:
        A mapping from ISO 639-1 language code to a :class:`PredictionService`
        instance.  Keys ``"en"``, ``"te"``, and ``"hi"`` are supported.

    Example
    -------
    >>> router = LanguageRouter({"en": en_svc, "te": te_svc, "hi": hi_svc})
    >>> result = router.route("Breaking news: government scandal exposed")
    """

    def __init__(self, pipelines: Dict[str, PredictionService]) -> None:
        self._pipelines: Dict[str, PredictionService] = dict(pipelines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, text: str) -> PredictionResult:
        """Detect the language of *text* and delegate to the matching pipeline.

        Steps
        -----
        1. Detect language using ``langdetect.detect``.
        2. If the detected language is Telugu or Hindi, apply Unicode NFC
           normalisation to *text* before prediction (Requirement 10.3).
        3. Look up the matching :class:`PredictionService` in ``self._pipelines``.
        4. If no matching pipeline exists (or detection fails), raise
           :class:`UnsupportedLanguageError` (Requirement 10.4).
        5. Call ``pipeline.predict(text)`` and return the result.

        Parameters
        ----------
        text:
            Raw article text in any language.

        Returns
        -------
        PredictionResult
            The prediction from the language-specific native pipeline.

        Raises
        ------
        UnsupportedLanguageError
            If the detected language is not supported or language detection
            itself fails (e.g., text is too short or ambiguous).
        """
        # Step 1: Detect language.
        detected_lang = self._detect_language(text)

        # Step 2: Apply NFC normalisation for Telugu / Hindi.
        if detected_lang in _NFC_LANGUAGES:
            logger.debug("Applying NFC normalisation for language %r", detected_lang)
            text = unicodedata.normalize("NFC", text)

        # Step 3: Look up pipeline; raise if not found.
        pipeline = self._pipelines.get(detected_lang)
        if pipeline is None:
            logger.warning(
                "No pipeline registered for language %r; raising UnsupportedLanguageError",
                detected_lang,
            )
            raise UnsupportedLanguageError(detected_lang)

        # Step 4: Delegate to the native language pipeline.
        logger.debug("Routing text to %r pipeline", detected_lang)
        return pipeline.predict(text)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_language(self, text: str) -> str:
        """Detect the language of *text* using langdetect.

        Parameters
        ----------
        text:
            Input text.

        Returns
        -------
        str
            ISO 639-1 language code (e.g. ``"en"``, ``"te"``, ``"hi"``).

        Raises
        ------
        UnsupportedLanguageError
            If ``langdetect`` raises :class:`LangDetectException`.
        """
        try:
            lang = detect(text)
            logger.debug("Detected language: %r", lang)
            return lang
        except LangDetectException as exc:
            logger.warning(
                "Language detection failed for text (len=%d): %s",
                len(text),
                exc,
            )
            raise UnsupportedLanguageError(None) from exc
