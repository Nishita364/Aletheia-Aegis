"""
Trust Rater service.

Loads a curated domain list from trust_domains.json and rates any domain
(or full URL) as High, Medium, Low, or Unknown.

The JSON file has the shape:
    {
        "high":   ["reuters.com", ...],
        "medium": ["cnn.com", ...],
        "low":    ["infowars.com", ...]
    }

Usage:
    rater = TrustRater()
    rating = rater.rate("https://reuters.com/article/123")  # "High"
    rating = rater.rate("reuters.com")                      # "High"
    rating = rater.rate("unknown-blog.xyz")                 # "Unknown"

    # Hot-reload after the JSON file has been updated on disk:
    rater.reload()
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Path to the bundled domain list (same directory as this module).
_DEFAULT_DOMAINS_PATH = Path(__file__).parent / "trust_domains.json"

TrustRating = Literal["High", "Medium", "Low", "Unknown"]

# Regex to extract the hostname from a URL (handles http/https and bare domains).
_URL_RE = re.compile(r"^(?:https?://)?([^/?\s]+)", re.IGNORECASE)


def _extract_domain(value: str) -> str:
    """Return the bare hostname from a URL or a bare domain string.

    Examples:
        "https://www.reuters.com/article/1" -> "www.reuters.com"
        "reuters.com"                        -> "reuters.com"
        "  Reuters.COM  "                    -> "reuters.com"
    """
    value = value.strip().lower()
    match = _URL_RE.match(value)
    if match:
        return match.group(1)
    return value


def _strip_www(domain: str) -> str:
    """Remove a leading 'www.' prefix so lookups are prefix-agnostic."""
    if domain.startswith("www."):
        return domain[4:]
    return domain


class TrustRater:
    """Rates the trustworthiness of a news-source domain.

    Parameters
    ----------
    domains_path:
        Path to the ``trust_domains.json`` file.  Defaults to the file
        bundled alongside this module.
    """

    def __init__(self, domains_path: Path | str | None = None) -> None:
        self._path = Path(domains_path) if domains_path else _DEFAULT_DOMAINS_PATH
        self._ratings: dict[str, TrustRating] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rate(self, domain: str) -> TrustRating:
        """Return the trust rating for *domain*.

        *domain* may be a bare hostname (``"reuters.com"``) or a full URL
        (``"https://reuters.com/article/123"``).  The lookup is
        case-insensitive and ignores a leading ``www.`` prefix.

        Returns ``"Unknown"`` when the domain is not in the curated list.
        """
        try:
            bare = _strip_www(_extract_domain(domain))
            return self._ratings.get(bare, "Unknown")
        except Exception:  # pragma: no cover – defensive catch
            logger.exception("Unexpected error rating domain %r", domain)
            return "Unknown"

    def reload(self) -> None:
        """Re-read the JSON file from disk and rebuild the in-memory dict.

        Call this after the file has been updated (e.g. via the admin API)
        to pick up changes without restarting the server.
        """
        self._load()
        logger.info("TrustRater: reloaded domain list from %s", self._path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load (or reload) the domain list from disk."""
        try:
            with self._path.open(encoding="utf-8") as fh:
                data: dict[str, list[str]] = json.load(fh)
        except FileNotFoundError:
            logger.error("TrustRater: domain file not found at %s", self._path)
            self._ratings = {}
            return
        except json.JSONDecodeError as exc:
            logger.error("TrustRater: invalid JSON in %s – %s", self._path, exc)
            self._ratings = {}
            return

        ratings: dict[str, TrustRating] = {}
        for level, domains in data.items():
            rating = _LEVEL_MAP.get(level.lower())
            if rating is None:
                logger.warning("TrustRater: unknown trust level %r – skipping", level)
                continue
            for raw_domain in domains:
                key = _strip_www(raw_domain.strip().lower())
                ratings[key] = rating

        self._ratings = ratings
        logger.debug("TrustRater: loaded %d domains", len(self._ratings))


# Map JSON keys → typed literals
_LEVEL_MAP: dict[str, TrustRating] = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}
