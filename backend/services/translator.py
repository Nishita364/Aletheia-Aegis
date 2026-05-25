"""
Translation service for Telugu and Hindi text.

Uses deep-translator (Google Translate free tier) to translate
Telugu (te) and Hindi (hi) text to English before passing to the
English ML pipeline.

This is Option A: translate-then-classify approach.
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Language codes that need translation before classification
TRANSLATABLE_LANGUAGES = frozenset({"te", "hi"})

# Language display names for logging/UI
LANGUAGE_NAMES = {
    "te": "Telugu",
    "hi": "Hindi",
    "en": "English",
}


def translate_to_english(text: str, source_lang: str) -> str:
    """Translate *text* from *source_lang* to English.

    Parameters
    ----------
    text:
        The text to translate.
    source_lang:
        ISO 639-1 language code (e.g. "te" for Telugu, "hi" for Hindi).

    Returns
    -------
    str
        Translated English text, or the original text if translation fails.
    """
    if source_lang == "en":
        return text

    if source_lang not in TRANSLATABLE_LANGUAGES:
        logger.warning("translate_to_english: unsupported language %r", source_lang)
        return text

    try:
        from deep_translator import GoogleTranslator  # noqa: PLC0415

        translated = GoogleTranslator(source=source_lang, target="en").translate(text)
        if translated:
            logger.info(
                "Translated %s text (%d chars) to English (%d chars)",
                LANGUAGE_NAMES.get(source_lang, source_lang),
                len(text),
                len(translated),
            )
            return translated
        logger.warning("Translation returned empty result for lang=%r", source_lang)
        return text

    except Exception as exc:
        logger.error(
            "Translation failed for lang=%r: %s — using original text",
            source_lang,
            exc,
        )
        return text
