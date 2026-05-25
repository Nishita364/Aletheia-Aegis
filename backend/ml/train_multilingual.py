"""
Multilingual training script for Aletheia-Aegis.

Trains separate TF-IDF + Logistic Regression models for:
  - Hindi (hi)  — from Hindi_F&R_News/
  - Telugu (te) — from Telugu_F&R_News/

Strategy:
  1. Load full articles.
  2. Augment with short snippets (first 3-5 sentences of each article)
     so the model learns to classify partial text, not just full articles.
  3. Combined word-level + character-level TF-IDF (FeatureUnion) for
     robustness across both short and long inputs.

Artifacts saved to backend/ml/artifacts/:
  - hi_tfidf_vectorizer.joblib  (full sklearn Pipeline)
  - hi_logistic_regression.joblib
  - hi_model_metadata.json
  - te_tfidf_vectorizer.joblib  (full sklearn Pipeline)
  - te_logistic_regression.joblib
  - te_model_metadata.json

Usage:
    python -m backend.ml.train_multilingual
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

HINDI_FAKE_DIR  = PROJECT_ROOT / "Hindi_F&R_News"  / "Hindi_fake_news"
HINDI_REAL_DIR  = PROJECT_ROOT / "Hindi_F&R_News"  / "Hindi_real_news"
TELUGU_FAKE_DIR = PROJECT_ROOT / "Telugu_F&R_News" / "Telugu_fake_news"
TELUGU_REAL_DIR = PROJECT_ROOT / "Telugu_F&R_News" / "Telugu_real_news"

# Sentence splitter — splits on ।  .  ?  !  followed by whitespace
_SENT_RE = re.compile(r'(?<=[।.?!])\s+')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences using Devanagari/Latin punctuation."""
    parts = _SENT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _make_snippets(text: str, min_words: int = 10) -> List[str]:
    """Return short snippets (first 3, 5, 8 sentences) from *text*.

    This augments training so the model learns to classify partial text.
    """
    sentences = _split_sentences(text)
    snippets = []
    for n in (3, 5, 8):
        if len(sentences) >= n:
            snippet = " ".join(sentences[:n])
            if len(snippet.split()) >= min_words:
                snippets.append(snippet)
    return snippets


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_txt_files(
    directory: Path,
    label: int,
    max_files: int = 15000,
    augment_snippets: bool = True,
) -> Tuple[List[str], List[int]]:
    """Load .txt files and optionally augment with short snippets."""
    texts: List[str] = []
    labels: List[int] = []
    files = sorted(directory.glob("*.txt"))[:max_files]
    logger.info(
        "Loading %d files from %s (label=%d, augment=%s)",
        len(files), directory.name, label, augment_snippets,
    )
    for f in files:
        try:
            raw = f.read_text(encoding="utf-8", errors="ignore").strip()
            if not raw:
                continue
            text = unicodedata.normalize("NFC", raw)
            # Full article
            texts.append(text)
            labels.append(label)
            # Short snippets (augmentation)
            if augment_snippets:
                for snippet in _make_snippets(text):
                    texts.append(snippet)
                    labels.append(label)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", f.name, exc)
    return texts, labels


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train_language_model(lang_code: str, fake_dir: Path, real_dir: Path) -> None:
    """Train and save a combined word+char TF-IDF + LR pipeline."""
    logger.info("=== Training %s model ===", lang_code.upper())

    fake_texts, fake_labels = load_txt_files(fake_dir, label=1, augment_snippets=True)
    real_texts, real_labels = load_txt_files(real_dir, label=0, augment_snippets=True)

    texts  = fake_texts + real_texts
    labels = fake_labels + real_labels

    logger.info(
        "%s dataset: %d fake, %d real, %d total (with snippets)",
        lang_code.upper(), len(fake_texts), len(real_texts), len(texts),
    )

    if len(texts) < 100:
        logger.error("Not enough data for %s — skipping", lang_code)
        return

    # ------------------------------------------------------------------ #
    # Feature engineering: word n-grams + character n-grams               #
    # Word n-grams: capture topic/vocabulary (good for short text)         #
    # Char n-grams: capture morphological patterns (good for Indic scripts)#
    # ------------------------------------------------------------------ #
    word_tfidf = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        max_features=100_000,
        sublinear_tf=True,
        min_df=2,
        token_pattern=r"(?u)\b\w+\b",
    )
    char_tfidf = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        max_features=100_000,
        sublinear_tf=True,
        min_df=2,
    )

    combined = FeatureUnion([
        ("word", word_tfidf),
        ("char", char_tfidf),
    ])

    pipeline = Pipeline([
        ("features", combined),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=1.0,
            solver="lbfgs",
            random_state=42,
        )),
    ])

    # Stratified train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    logger.info("Fitting combined word+char TF-IDF pipeline (%d train samples)...", len(X_train))
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    logger.info("%s model accuracy: %.2f%%", lang_code.upper(), accuracy * 100)
    logger.info("\n%s", classification_report(y_test, y_pred, target_names=["Real", "Fake"]))

    # Save artifacts
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    pipeline_path = ARTIFACTS_DIR / f"{lang_code}_tfidf_vectorizer.joblib"
    lr_path       = ARTIFACTS_DIR / f"{lang_code}_logistic_regression.joblib"
    meta_path     = ARTIFACTS_DIR / f"{lang_code}_model_metadata.json"

    joblib.dump(pipeline, pipeline_path)
    joblib.dump(pipeline.named_steps["clf"], lr_path)

    meta = {
        "language": lang_code,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": round(accuracy, 4),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "fake_samples": len(fake_texts),
        "real_samples": len(real_texts),
        "pipeline_mode": True,
        "augmented_snippets": True,
        "vectorizer": "FeatureUnion(word TF-IDF(1,2) + char_wb TF-IDF(3,5))",
        "classifier": "LogisticRegression(C=1.0, max_iter=1000)",
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    logger.info(
        "Saved %s pipeline → %s (%.2f%% accuracy)",
        lang_code.upper(), pipeline_path.name, accuracy * 100,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("Starting multilingual model training with snippet augmentation...")

    if HINDI_FAKE_DIR.exists() and HINDI_REAL_DIR.exists():
        train_language_model("hi", HINDI_FAKE_DIR, HINDI_REAL_DIR)
    else:
        logger.warning("Hindi dataset not found at %s", HINDI_FAKE_DIR.parent)

    if TELUGU_FAKE_DIR.exists() and TELUGU_REAL_DIR.exists():
        train_language_model("te", TELUGU_FAKE_DIR, TELUGU_REAL_DIR)
    else:
        logger.warning("Telugu dataset not found at %s", TELUGU_FAKE_DIR.parent)

    logger.info("Multilingual training complete.")


if __name__ == "__main__":
    main()
