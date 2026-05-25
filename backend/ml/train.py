"""
TF-IDF + classifier training script for the Fake News Detector.

Trains a LogisticRegression (primary) and MultinomialNB (fallback) classifier
on top of a TfidfVectorizer fitted on the combined Fake/True news corpus.
Serialises all artifacts to backend/ml/artifacts/ using joblib.

Requirements: 2.3, 2.4

Usage (from the backend/ directory):
    python -m ml.train
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB

from backend.ml.data_loader import load_data, preprocess

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------

_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
_VECTORIZER_PATH = _ARTIFACTS_DIR / "tfidf_vectorizer.joblib"
_LR_MODEL_PATH = _ARTIFACTS_DIR / "logistic_regression.joblib"
_NB_MODEL_PATH = _ARTIFACTS_DIR / "naive_bayes.joblib"
_METADATA_PATH = _ARTIFACTS_DIR / "model_metadata.json"

# ---------------------------------------------------------------------------
# Accuracy threshold
# ---------------------------------------------------------------------------

_MIN_ACCURACY = 0.85


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def train(
    fake_csv: Optional[str] = None,
    true_csv: Optional[str] = None,
) -> dict:
    """Train the TF-IDF + classifier pipeline and serialise artifacts.

    Parameters
    ----------
    fake_csv:
        Optional path to the fake-news CSV.  Defaults to ``archive/Fake.csv``
        relative to the repository root (resolved by ``load_data``).
    true_csv:
        Optional path to the real-news CSV.  Defaults to ``archive/True.csv``
        relative to the repository root (resolved by ``load_data``).

    Returns
    -------
    dict
        A dictionary with keys:
        - ``lr_accuracy``  (float): Logistic Regression accuracy on test split.
        - ``nb_accuracy``  (float): Multinomial NB accuracy on test split.
        - ``n_samples``    (int):   Total number of training samples used.
        - ``n_features``   (int):   Number of TF-IDF features in the vocabulary.

    Raises
    ------
    AssertionError
        If either model's accuracy on the held-out split is below 85%.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    logger.info("Loading dataset …")
    df = load_data(
        fake_csv=Path(fake_csv) if fake_csv else None,
        true_csv=Path(true_csv) if true_csv else None,
    )
    logger.info("Dataset loaded: %d rows", len(df))

    # ------------------------------------------------------------------
    # 2. Preprocess text
    # ------------------------------------------------------------------
    logger.info("Preprocessing text …")
    texts = df["text"].apply(preprocess).tolist()
    labels = df["label"].tolist()

    # ------------------------------------------------------------------
    # 3. Train / test split (80/20, stratified)
    # ------------------------------------------------------------------
    logger.info("Splitting into train/test (80/20, stratified) …")
    X_train, X_test, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=0.20,
        random_state=42,
        stratify=labels,
    )
    logger.info(
        "Train size: %d  |  Test size: %d", len(X_train), len(X_test)
    )

    # ------------------------------------------------------------------
    # 4. Fit TF-IDF vectoriser on training set only
    # ------------------------------------------------------------------
    logger.info("Fitting TF-IDF vectoriser (max_features=50000) …")
    vectorizer = TfidfVectorizer(
        max_features=50_000,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    X_train_tfidf = vectorizer.fit_transform(X_train)
    X_test_tfidf = vectorizer.transform(X_test)
    n_features = len(vectorizer.vocabulary_)
    logger.info("Vocabulary size: %d features", n_features)

    # ------------------------------------------------------------------
    # 5. Train Logistic Regression (primary)
    # ------------------------------------------------------------------
    logger.info("Training LogisticRegression …")
    lr_model = LogisticRegression(max_iter=1000, C=1.0)
    lr_model.fit(X_train_tfidf, y_train)
    lr_preds = lr_model.predict(X_test_tfidf)
    lr_accuracy = float(accuracy_score(y_test, lr_preds))
    logger.info("LogisticRegression accuracy: %.4f", lr_accuracy)

    # ------------------------------------------------------------------
    # 6. Train Multinomial Naive Bayes (fallback)
    # ------------------------------------------------------------------
    logger.info("Training MultinomialNB …")
    nb_model = MultinomialNB(alpha=0.1)
    nb_model.fit(X_train_tfidf, y_train)
    nb_preds = nb_model.predict(X_test_tfidf)
    nb_accuracy = float(accuracy_score(y_test, nb_preds))
    logger.info("MultinomialNB accuracy: %.4f", nb_accuracy)

    # ------------------------------------------------------------------
    # 7. Assert accuracy ≥ 85% for English
    # ------------------------------------------------------------------
    assert lr_accuracy >= _MIN_ACCURACY, (
        f"LogisticRegression accuracy {lr_accuracy:.4f} is below the "
        f"required minimum of {_MIN_ACCURACY:.2f}"
    )
    assert nb_accuracy >= _MIN_ACCURACY, (
        f"MultinomialNB accuracy {nb_accuracy:.4f} is below the "
        f"required minimum of {_MIN_ACCURACY:.2f}"
    )
    logger.info("Both models meet the ≥85%% accuracy requirement.")

    # ------------------------------------------------------------------
    # 8. Serialise artifacts
    # ------------------------------------------------------------------
    _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Saving vectoriser → %s", _VECTORIZER_PATH)
    joblib.dump(vectorizer, _VECTORIZER_PATH)

    logger.info("Saving LogisticRegression → %s", _LR_MODEL_PATH)
    joblib.dump(lr_model, _LR_MODEL_PATH)

    logger.info("Saving MultinomialNB → %s", _NB_MODEL_PATH)
    joblib.dump(nb_model, _NB_MODEL_PATH)

    # ------------------------------------------------------------------
    # 9. Save metadata
    # ------------------------------------------------------------------
    metadata = {
        "lr_accuracy": lr_accuracy,
        "nb_accuracy": nb_accuracy,
        "n_samples": len(texts),
        "n_features": n_features,
        "training_date": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Saving metadata → %s", _METADATA_PATH)
    _METADATA_PATH.write_text(json.dumps(metadata, indent=2))

    logger.info("Training complete.")
    return {
        "lr_accuracy": lr_accuracy,
        "nb_accuracy": nb_accuracy,
        "n_samples": len(texts),
        "n_features": n_features,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = train()
    print(json.dumps(result, indent=2))
    sys.exit(0)
