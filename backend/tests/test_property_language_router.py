"""
Property-based tests for LanguageRouter.route().

# Feature: fake-news-detector, Property 9: Language Detection Routes to Supported Pipelines or Rejects

Property 9: Language Detection Routes to Supported Pipelines or Rejects
  For any non-empty string input, LanguageRouter.route() SHALL either:
    1. Return a PredictionResult with valid structure:
         - label âˆˆ {"Real", "Fake"}
         - confidence âˆˆ [0.0, 1.0]
    2. Raise UnsupportedLanguageError

  It must NEVER silently pass text to a pipeline without detection, and must
  NEVER raise any other exception type.

Validates: Requirements 10.2, 10.4
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ml.language_router import LanguageRouter, UnsupportedLanguageError
from ml.prediction_service import PredictionResult


# ---------------------------------------------------------------------------
# Helpers: build a LanguageRouter with mocked pipelines
# ---------------------------------------------------------------------------

_SUPPORTED_LANGS = ("en", "te", "hi")


def _make_mock_pipeline(label: str = "Real", confidence: float = 0.85) -> MagicMock:
    """Return a MagicMock that behaves like a PredictionService."""
    svc = MagicMock()
    svc.predict.return_value = PredictionResult(
        label=label,
        confidence=confidence,
        suspicious_phrases=[],
        explanation=f"This article was classified as {label} with {confidence:.1%} confidence.",
    )
    return svc


def _make_router() -> LanguageRouter:
    """Build a LanguageRouter with three mock pipelines (en, te, hi)."""
    pipelines = {lang: _make_mock_pipeline() for lang in _SUPPORTED_LANGS}
    return LanguageRouter(pipelines)


# ---------------------------------------------------------------------------
# Property 9: Language Detection Routes to Supported Pipelines or Rejects
# ---------------------------------------------------------------------------


@given(text=st.text(min_size=1, max_size=10_000))
@settings(max_examples=20, deadline=None)
def test_property9_language_routing_returns_valid_prediction_or_raises_unsupported(
    text: str,
) -> None:
    """
    **Validates: Requirements 10.2, 10.4**

    Property 9: Language Detection Routes to Supported Pipelines or Rejects

    For any non-empty string (up to 10,000 characters), LanguageRouter.route()
    must either:
      1. Return a PredictionResult where:
           - label âˆˆ {"Real", "Fake"}
           - confidence âˆˆ [0.0, 1.0]
      2. Raise UnsupportedLanguageError

    It must NEVER raise any other exception type, and must NEVER silently pass
    text to a pipeline without language detection.
    """
    # Feature: fake-news-detector, Property 9: Language Detection Routes to Supported Pipelines or Rejects
    router = _make_router()

    try:
        result = router.route(text)

        # If we get here, the router returned a result â€” it must be a valid PredictionResult.
        assert isinstance(result, PredictionResult), (
            f"router.route() returned {type(result)!r}, expected PredictionResult"
        )

        # label âˆˆ {"Real", "Fake"}
        assert result.label in {"Real", "Fake"}, (
            f"label {result.label!r} is not one of {{'Real', 'Fake'}}"
        )

        # confidence âˆˆ [0.0, 1.0]
        assert 0.0 <= result.confidence <= 1.0, (
            f"confidence {result.confidence} is outside [0.0, 1.0]"
        )

    except UnsupportedLanguageError:
        # This is the expected path for unsupported or undetectable languages.
        # No further assertions needed â€” the router correctly rejected the input.
        pass

    except Exception as exc:  # noqa: BLE001
        # Any other exception is a violation of the property.
        pytest.fail(
            f"router.route() raised an unexpected exception {type(exc).__name__}: {exc}\n"
            f"Input (first 200 chars): {text[:200]!r}"
        )
