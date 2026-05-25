"""
Property-based tests for SubmissionRequest schema validation in backend/schemas.py.

# Feature: fake-news-detector, Property 2: Submission Request Schema Validation Rejects Invalid Inputs

Property 2: Submission Request Schema Validation Rejects Invalid Inputs
  For any JSON payload that violates the Submission request schema
  (both fields null, both fields populated, text exceeding 10,000
  characters, or url not matching ^https?://), the SubmissionRequest
  schema SHALL raise a ValidationError.

Validates: Requirements 1.3, 1.4, 12.5

# Feature: fake-news-detector, Property 5: Whitespace-Only and Empty Submissions Are Rejected

Property 5: Whitespace-Only and Empty Submissions Are Rejected
  For any string composed entirely of whitespace characters (spaces, tabs,
  newlines), submitting it as the text field SHALL be rejected by raising a
  ValidationError, and no Prediction SHALL be generated.

Validates: Requirements 1.4, 12.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from schemas import SubmissionRequest

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

# A valid non-empty, non-whitespace text string (â‰¤10,000 chars).
_valid_text = st.text(min_size=1, max_size=10_000).filter(
    lambda t: t.strip() != ""
)

# A valid URL starting with http:// or https://.
_valid_url = st.one_of(
    st.text(min_size=1, max_size=200).map(lambda s: "http://" + s),
    st.text(min_size=1, max_size=200).map(lambda s: "https://" + s),
)

# A URL that does NOT start with http:// or https://.
# We generate arbitrary strings and filter out any that accidentally start
# with the valid prefixes.
_invalid_url = st.text(min_size=1, max_size=200).filter(
    lambda s: not s.startswith("http://") and not s.startswith("https://")
)

# Text that exceeds the 10,000-character limit.
# Hypothesis has a buffer-size cap on st.text(min_size=...) for very large
# strings, so we build oversized text by repeating a base string enough times
# to guarantee the result is always > 10,000 characters.
# Base string is at least 1 char; we repeat it ceil(10_001 / len(base)) + 1 times.
_oversized_text = st.text(min_size=1, max_size=50).filter(
    lambda t: t.strip() != ""
).map(lambda t: t * (10_001 // len(t) + 1))  # always > 10,000 chars

# Whitespace-only text (spaces, tabs, newlines).
_whitespace_text = st.text(
    alphabet=st.sampled_from([" ", "\t", "\n", "\r"]),
    min_size=1,
    max_size=100,
)


# ---------------------------------------------------------------------------
# Sub-property 2a: Both text and url are null â†’ ValidationError
# ---------------------------------------------------------------------------


@given(
    text=st.none(),
    url=st.none(),
)
@settings(max_examples=20)
def test_property2a_both_null_raises_validation_error(
    text: None,
    url: None,
) -> None:
    """
    **Validates: Requirements 1.4, 12.5**

    When both text and url are null, SubmissionRequest SHALL raise
    ValidationError because neither field is provided.
    """
    with pytest.raises(ValidationError):
        SubmissionRequest(text=text, url=url)


# ---------------------------------------------------------------------------
# Sub-property 2b: Both text and url are populated â†’ ValidationError
# ---------------------------------------------------------------------------


@given(
    text=_valid_text,
    url=_valid_url,
)
@settings(max_examples=20)
def test_property2b_both_populated_raises_validation_error(
    text: str,
    url: str,
) -> None:
    """
    **Validates: Requirements 1.3, 12.5**

    When both text and url are non-null and non-empty, SubmissionRequest
    SHALL raise ValidationError because mutual exclusivity is violated.
    """
    with pytest.raises(ValidationError):
        SubmissionRequest(text=text, url=url)


# ---------------------------------------------------------------------------
# Sub-property 2c: text > 10,000 characters â†’ ValidationError
# ---------------------------------------------------------------------------


@given(text=_oversized_text)
@settings(max_examples=20)
def test_property2c_oversized_text_raises_validation_error(text: str) -> None:
    """
    **Validates: Requirements 1.1, 12.5**

    When text exceeds 10,000 characters, SubmissionRequest SHALL raise
    ValidationError regardless of the url field.
    """
    with pytest.raises(ValidationError):
        SubmissionRequest(text=text, url=None)


# ---------------------------------------------------------------------------
# Sub-property 2d: url not matching ^https?:// â†’ ValidationError
# ---------------------------------------------------------------------------


@given(url=_invalid_url)
@settings(max_examples=20)
def test_property2d_invalid_url_raises_validation_error(url: str) -> None:
    """
    **Validates: Requirements 1.2, 12.5**

    When url does not match ^https?://, SubmissionRequest SHALL raise
    ValidationError regardless of the text field.
    """
    with pytest.raises(ValidationError):
        SubmissionRequest(text=None, url=url)


# ---------------------------------------------------------------------------
# Sub-property 2e: whitespace-only text â†’ ValidationError
# ---------------------------------------------------------------------------


@given(text=_whitespace_text)
@settings(max_examples=20)
def test_property2e_whitespace_only_text_raises_validation_error(text: str) -> None:
    """
    **Validates: Requirements 1.4, 12.5**

    When text is composed entirely of whitespace characters, SubmissionRequest
    SHALL raise ValidationError because whitespace-only text is treated as
    absent (equivalent to providing neither field).
    """
    with pytest.raises(ValidationError):
        SubmissionRequest(text=text, url=None)


# ---------------------------------------------------------------------------
# Property 5: Whitespace-Only and Empty Submissions Are Rejected
# ---------------------------------------------------------------------------

# Re-use the whitespace strategy defined above (_whitespace_text).
# The strategy generates strings of length 1â€“100 composed solely of
# space, tab, newline, and carriage-return characters.


@given(whitespace_text=_whitespace_text)
@settings(max_examples=20)
def test_property5_whitespace_only_submissions_rejected(
    whitespace_text: str,
) -> None:
    """
    # Feature: fake-news-detector, Property 5: Whitespace-Only and Empty Submissions Are Rejected

    **Validates: Requirements 1.4, 12.5**

    For any string composed entirely of whitespace characters (spaces, tabs,
    newlines, carriage returns), submitting it as the ``text`` field SHALL:

    1. Raise a ``ValidationError`` â€” the submission is rejected before any
       ML processing occurs.
    2. Produce no ``Prediction`` â€” because validation fails, the ML pipeline
       is never invoked and no Prediction object is returned.
    """
    # Track whether a Prediction was (incorrectly) generated.
    prediction_generated: list[object] = []

    with pytest.raises(ValidationError):
        # Attempt to create a SubmissionRequest with whitespace-only text.
        # This MUST raise ValidationError; if it does not, the test fails.
        request = SubmissionRequest(text=whitespace_text, url=None)

        # If we reach this line the validator did NOT raise â€” record it so
        # the assertion below can surface a clear failure message.
        prediction_generated.append(request)

    # Assert that no Prediction was generated (the ML pipeline was never
    # reached because validation raised before we could call it).
    assert len(prediction_generated) == 0, (
        f"Expected no Prediction to be generated for whitespace-only text "
        f"{whitespace_text!r}, but a SubmissionRequest was constructed: "
        f"{prediction_generated}"
    )
