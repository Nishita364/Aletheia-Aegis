"""
Property-based tests for backend/services/trust_rater.py.

# Feature: fake-news-detector, Property 8: Trust Rater Returns a Valid Rating for Any Domain

Property 8: Trust Rater Returns a Valid Rating for Any Domain
  For any domain string, the Trust_Rater SHALL return exactly one of
  "High", "Medium", "Low", or "Unknown", and SHALL never raise an
  unhandled exception.

Validates: Requirements 8.2, 8.4
"""

from __future__ import annotations

from typing import Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from services.trust_rater import TrustRater

# ---------------------------------------------------------------------------
# Module-level fixture: a single TrustRater instance backed by the bundled
# trust_domains.json.  Creating it once avoids repeated file I/O per example.
# ---------------------------------------------------------------------------

_RATER = TrustRater()

VALID_RATINGS: frozenset[str] = frozenset({"High", "Medium", "Low", "Unknown"})

# ---------------------------------------------------------------------------
# Strategy: arbitrary domain strings
#
# We use st.text() with no alphabet restriction so Hypothesis explores the
# full Unicode space â€” including empty strings, whitespace-only strings,
# strings with control characters, very long strings, and strings that look
# like URLs.  This matches the "any domain string" requirement.
# ---------------------------------------------------------------------------

_any_domain = st.text()


# ---------------------------------------------------------------------------
# Property 8: Trust Rater Returns a Valid Rating for Any Domain
# ---------------------------------------------------------------------------


@given(domain=_any_domain)
@settings(max_examples=20)
def test_property8_trust_rater_returns_valid_rating(domain: str) -> None:
    """
    **Validates: Requirements 8.2, 8.4**

    Property 8: Trust Rater Returns a Valid Rating for Any Domain

    For any arbitrary domain string:
    - TrustRater.rate() returns exactly one of {"High", "Medium", "Low", "Unknown"}.
    - No unhandled exception is raised.
    """
    # The call itself must not raise any exception.
    rating = _RATER.rate(domain)

    # The return value must be one of the four valid ratings.
    assert rating in VALID_RATINGS, (
        f"TrustRater.rate({domain!r}) returned {rating!r}, "
        f"which is not one of {sorted(VALID_RATINGS)}"
    )
