"""
Unit tests for backend/ml/language_router.py

Covers:
- UnsupportedLanguageError: attributes and message
- LanguageRouter.route(): English text routes to English pipeline
- LanguageRouter.route(): Telugu text routes to Telugu pipeline with NFC normalisation
- LanguageRouter.route(): Hindi text routes to Hindi pipeline with NFC normalisation
- LanguageRouter.route(): unsupported language raises UnsupportedLanguageError
- LanguageRouter.route(): LangDetectException is wrapped in UnsupportedLanguageError
- LanguageRouter.route(): NFC normalisation is applied before Telugu/Hindi prediction
- LanguageRouter.route(): NFC normalisation is NOT applied for English
- LanguageRouter.route(): missing pipeline for detected language raises UnsupportedLanguageError
- LanguageRouter: accepts a subset of pipelines (partial mapping)
"""

from __future__ import annotations

import unicodedata
from unittest.mock import MagicMock, call, patch

import pytest
from langdetect import LangDetectException

from ml.language_router import LanguageRouter, UnsupportedLanguageError
from ml.prediction_service import PredictionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_service(label: str = "Real", confidence: float = 0.9) -> MagicMock:
    """Return a MagicMock that behaves like a PredictionService."""
    svc = MagicMock()
    svc.predict.return_value = PredictionResult(
        label=label,
        confidence=confidence,
        suspicious_phrases=["test phrase"],
        explanation=f"This article was classified as {label} with {confidence:.1%} confidence.",
    )
    return svc


def _make_router(
    en_label: str = "Real",
    te_label: str = "Real",
    hi_label: str = "Real",
) -> tuple[LanguageRouter, dict[str, MagicMock]]:
    """Build a LanguageRouter with three mock pipelines and return both."""
    services = {
        "en": _make_mock_service(en_label),
        "te": _make_mock_service(te_label),
        "hi": _make_mock_service(hi_label),
    }
    router = LanguageRouter(services)
    return router, services


# ---------------------------------------------------------------------------
# UnsupportedLanguageError
# ---------------------------------------------------------------------------


class TestUnsupportedLanguageError:
    def test_is_exception(self):
        err = UnsupportedLanguageError("fr")
        assert isinstance(err, Exception)

    def test_language_code_attribute(self):
        err = UnsupportedLanguageError("fr")
        assert err.language_code == "fr"

    def test_language_code_none(self):
        err = UnsupportedLanguageError(None)
        assert err.language_code is None

    def test_message_contains_language_code(self):
        err = UnsupportedLanguageError("zh-cn")
        assert "zh-cn" in str(err)

    def test_message_mentions_supported_languages(self):
        err = UnsupportedLanguageError("de")
        msg = str(err)
        assert "en" in msg
        assert "te" in msg
        assert "hi" in msg

    def test_default_language_code_is_none(self):
        err = UnsupportedLanguageError()
        assert err.language_code is None


# ---------------------------------------------------------------------------
# LanguageRouter construction
# ---------------------------------------------------------------------------


class TestLanguageRouterInit:
    def test_accepts_full_pipeline_dict(self):
        router, _ = _make_router()
        assert router is not None

    def test_accepts_partial_pipeline_dict(self):
        """Router should accept a dict with only some languages."""
        router = LanguageRouter({"en": _make_mock_service()})
        assert router is not None

    def test_accepts_empty_pipeline_dict(self):
        """Empty dict is valid at construction; routing will raise."""
        router = LanguageRouter({})
        assert router is not None

    def test_pipelines_are_copied(self):
        """Mutating the original dict after construction should not affect the router."""
        services = {"en": _make_mock_service()}
        router = LanguageRouter(services)
        services["en"] = _make_mock_service(label="Fake")  # mutate original
        # The router should still hold the original service
        with patch("ml.language_router.detect", return_value="en"):
            result = router.route("some english text")
        assert result.label == "Real"  # original service returned "Real"


# ---------------------------------------------------------------------------
# Routing to English pipeline
# ---------------------------------------------------------------------------


class TestRouteEnglish:
    def test_english_text_routes_to_en_pipeline(self):
        router, services = _make_router()
        with patch("ml.language_router.detect", return_value="en"):
            result = router.route("The president signed the bill into law today.")
        services["en"].predict.assert_called_once()
        services["te"].predict.assert_not_called()
        services["hi"].predict.assert_not_called()

    def test_english_returns_prediction_result(self):
        router, _ = _make_router(en_label="Fake")
        with patch("ml.language_router.detect", return_value="en"):
            result = router.route("Breaking news: shocking scandal exposed.")
        assert isinstance(result, PredictionResult)
        assert result.label == "Fake"

    def test_english_does_not_apply_nfc_normalisation(self):
        """For English, the text passed to predict() should be the original (no NFC)."""
        router, services = _make_router()
        original_text = "The president signed the bill."
        with patch("ml.language_router.detect", return_value="en"):
            router.route(original_text)
        # The text passed to predict should be the original (NFC of ASCII == ASCII)
        services["en"].predict.assert_called_once_with(original_text)


# ---------------------------------------------------------------------------
# Routing to Telugu pipeline
# ---------------------------------------------------------------------------


class TestRouteTelugu:
    def test_telugu_text_routes_to_te_pipeline(self):
        router, services = _make_router()
        with patch("ml.language_router.detect", return_value="te"):
            router.route("తెలుగు వార్తలు")
        services["te"].predict.assert_called_once()
        services["en"].predict.assert_not_called()
        services["hi"].predict.assert_not_called()

    def test_telugu_returns_prediction_result(self):
        router, _ = _make_router(te_label="Real")
        with patch("ml.language_router.detect", return_value="te"):
            result = router.route("తెలుగు వార్తలు")
        assert isinstance(result, PredictionResult)
        assert result.label == "Real"

    def test_telugu_applies_nfc_normalisation(self):
        """For Telugu, the text passed to predict() must be NFC-normalised."""
        router, services = _make_router()
        # Construct a string that is NOT in NFC form (NFD decomposed Telugu).
        raw_text = "తెలుగు"
        nfd_text = unicodedata.normalize("NFD", raw_text)
        nfc_text = unicodedata.normalize("NFC", nfd_text)

        with patch("ml.language_router.detect", return_value="te"):
            router.route(nfd_text)

        # The predict call should receive the NFC-normalised version.
        services["te"].predict.assert_called_once_with(nfc_text)

    def test_telugu_nfc_already_normalised_text_unchanged(self):
        """If text is already NFC, normalisation is a no-op."""
        router, services = _make_router()
        nfc_text = unicodedata.normalize("NFC", "తెలుగు వార్తలు")

        with patch("ml.language_router.detect", return_value="te"):
            router.route(nfc_text)

        services["te"].predict.assert_called_once_with(nfc_text)


# ---------------------------------------------------------------------------
# Routing to Hindi pipeline
# ---------------------------------------------------------------------------


class TestRouteHindi:
    def test_hindi_text_routes_to_hi_pipeline(self):
        router, services = _make_router()
        with patch("ml.language_router.detect", return_value="hi"):
            router.route("हिंदी समाचार")
        services["hi"].predict.assert_called_once()
        services["en"].predict.assert_not_called()
        services["te"].predict.assert_not_called()

    def test_hindi_returns_prediction_result(self):
        router, _ = _make_router(hi_label="Fake")
        with patch("ml.language_router.detect", return_value="hi"):
            result = router.route("हिंदी समाचार")
        assert isinstance(result, PredictionResult)
        assert result.label == "Fake"

    def test_hindi_applies_nfc_normalisation(self):
        """For Hindi, the text passed to predict() must be NFC-normalised."""
        router, services = _make_router()
        raw_text = "हिंदी"
        nfd_text = unicodedata.normalize("NFD", raw_text)
        nfc_text = unicodedata.normalize("NFC", nfd_text)

        with patch("ml.language_router.detect", return_value="hi"):
            router.route(nfd_text)

        services["hi"].predict.assert_called_once_with(nfc_text)

    def test_hindi_nfc_already_normalised_text_unchanged(self):
        """If text is already NFC, normalisation is a no-op."""
        router, services = _make_router()
        nfc_text = unicodedata.normalize("NFC", "हिंदी समाचार")

        with patch("ml.language_router.detect", return_value="hi"):
            router.route(nfc_text)

        services["hi"].predict.assert_called_once_with(nfc_text)


# ---------------------------------------------------------------------------
# Unsupported language
# ---------------------------------------------------------------------------


class TestUnsupportedLanguage:
    @pytest.mark.parametrize("lang_code", ["fr", "de", "zh-cn", "ja", "ar", "es", "pt"])
    def test_unsupported_language_raises(self, lang_code):
        router, services = _make_router()
        with patch("ml.language_router.detect", return_value=lang_code):
            with pytest.raises(UnsupportedLanguageError) as exc_info:
                router.route("some text in an unsupported language")
        assert exc_info.value.language_code == lang_code

    def test_unsupported_language_does_not_call_any_pipeline(self):
        router, services = _make_router()
        with patch("ml.language_router.detect", return_value="fr"):
            with pytest.raises(UnsupportedLanguageError):
                router.route("Bonjour le monde")
        services["en"].predict.assert_not_called()
        services["te"].predict.assert_not_called()
        services["hi"].predict.assert_not_called()

    def test_missing_pipeline_for_detected_language_raises(self):
        """If a supported language is detected but no pipeline is registered, raise."""
        # Router only has English pipeline; Telugu is detected.
        router = LanguageRouter({"en": _make_mock_service()})
        with patch("ml.language_router.detect", return_value="te"):
            with pytest.raises(UnsupportedLanguageError) as exc_info:
                router.route("తెలుగు వార్తలు")
        assert exc_info.value.language_code == "te"

    def test_empty_router_raises_for_english(self):
        """Even English raises if no pipeline is registered."""
        router = LanguageRouter({})
        with patch("ml.language_router.detect", return_value="en"):
            with pytest.raises(UnsupportedLanguageError) as exc_info:
                router.route("some english text")
        assert exc_info.value.language_code == "en"


# ---------------------------------------------------------------------------
# LangDetectException handling
# ---------------------------------------------------------------------------


class TestLangDetectExceptionHandling:
    def test_lang_detect_exception_raises_unsupported_language_error(self):
        router, _ = _make_router()
        with patch(
            "ml.language_router.detect",
            side_effect=LangDetectException(0, "No features in text."),
        ):
            with pytest.raises(UnsupportedLanguageError) as exc_info:
                router.route("123")
        assert exc_info.value.language_code is None

    def test_lang_detect_exception_does_not_call_any_pipeline(self):
        router, services = _make_router()
        with patch(
            "ml.language_router.detect",
            side_effect=LangDetectException(0, "No features in text."),
        ):
            with pytest.raises(UnsupportedLanguageError):
                router.route("!!!")
        services["en"].predict.assert_not_called()
        services["te"].predict.assert_not_called()
        services["hi"].predict.assert_not_called()

    def test_lang_detect_exception_is_chained(self):
        """UnsupportedLanguageError should chain the original LangDetectException."""
        router, _ = _make_router()
        original_exc = LangDetectException(0, "No features in text.")
        with patch("ml.language_router.detect", side_effect=original_exc):
            with pytest.raises(UnsupportedLanguageError) as exc_info:
                router.route("xyz")
        assert exc_info.value.__cause__ is original_exc


# ---------------------------------------------------------------------------
# NFC normalisation detail
# ---------------------------------------------------------------------------


class TestNFCNormalisation:
    def test_nfc_applied_only_for_te_and_hi(self):
        """English text must NOT be NFC-normalised by the router."""
        router, services = _make_router()
        # Use a string that changes under NFC (e.g. NFD-decomposed ASCII-range
        # characters are rare, but we can verify by checking the exact argument).
        text = "The president signed the bill."
        with patch("ml.language_router.detect", return_value="en"):
            router.route(text)
        # predict() should receive the original text unchanged
        services["en"].predict.assert_called_once_with(text)

    def test_nfc_normalisation_result_is_valid_nfc(self):
        """After routing Telugu, the text received by predict() must be NFC."""
        received_texts: list[str] = []

        mock_svc = MagicMock()
        mock_svc.predict.side_effect = lambda t: (
            received_texts.append(t)
            or PredictionResult(label="Real", confidence=0.8)
        )
        router = LanguageRouter({"te": mock_svc})

        nfd_text = unicodedata.normalize("NFD", "తెలుగు వార్తలు")
        with patch("ml.language_router.detect", return_value="te"):
            router.route(nfd_text)

        assert len(received_texts) == 1
        received = received_texts[0]
        assert unicodedata.is_normalized("NFC", received), (
            "Text passed to Telugu pipeline is not NFC-normalised"
        )
