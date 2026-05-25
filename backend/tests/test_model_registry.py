"""
Unit tests for backend/ml/model_registry.py

Covers:
- ModelRegistry construction (with and without an initial service)
- get_service() returns the active service
- get_service() raises RuntimeError when no service is registered
- predict() delegates to the active service
- predict() raises RuntimeError when no service is registered
- swap() atomically replaces the active service and returns the old one
- swap() raises TypeError for non-PredictionService arguments
- Thread-safety: concurrent swap() and predict() calls do not corrupt state
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import joblib
import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from ml.model_registry import ModelRegistry
from ml.prediction_service import PredictionResult, PredictionService


# ---------------------------------------------------------------------------
# Helpers: build minimal real artifacts
# ---------------------------------------------------------------------------


def _build_artifacts(tmp_path: Path) -> dict[str, Path]:
    """Train a tiny TF-IDF + LR model and save artifacts to *tmp_path*."""
    texts = [
        "breaking news shocking scandal exposed government lies",
        "you won't believe what politicians are hiding from you",
        "the president signed the infrastructure bill into law today",
        "scientists publish new research on climate change in nature journal",
    ]
    labels = [1, 1, 0, 0]

    vectorizer = TfidfVectorizer(max_features=100)
    X = vectorizer.fit_transform(texts)
    lr_model = LogisticRegression(max_iter=500)
    lr_model.fit(X, labels)

    vp = tmp_path / "tfidf_vectorizer.joblib"
    lp = tmp_path / "logistic_regression.joblib"
    mp = tmp_path / "model_metadata.json"

    joblib.dump(vectorizer, vp)
    joblib.dump(lr_model, lp)
    mp.write_text(json.dumps({"lr_accuracy": 1.0}))

    return {"vectorizer": vp, "lr_model": lp, "metadata": mp}


@pytest.fixture(scope="module")
def artifact_paths(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("registry_artifacts")
    return _build_artifacts(tmp)


@pytest.fixture(scope="module")
def service_a(artifact_paths):
    return PredictionService(
        vectorizer_path=artifact_paths["vectorizer"],
        lr_model_path=artifact_paths["lr_model"],
        metadata_path=artifact_paths["metadata"],
    )


@pytest.fixture(scope="module")
def service_b(artifact_paths):
    """A second PredictionService instance (same artifacts, different object)."""
    return PredictionService(
        vectorizer_path=artifact_paths["vectorizer"],
        lr_model_path=artifact_paths["lr_model"],
        metadata_path=artifact_paths["metadata"],
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestModelRegistryConstruction:
    def test_construct_with_service(self, service_a):
        registry = ModelRegistry(service_a)
        assert registry.get_service() is service_a

    def test_construct_without_service(self):
        registry = ModelRegistry()
        with pytest.raises(RuntimeError, match="no active PredictionService"):
            registry.get_service()

    def test_construct_with_none_explicit(self):
        registry = ModelRegistry(None)
        with pytest.raises(RuntimeError):
            registry.get_service()


# ---------------------------------------------------------------------------
# get_service()
# ---------------------------------------------------------------------------


class TestGetService:
    def test_returns_initial_service(self, service_a):
        registry = ModelRegistry(service_a)
        assert registry.get_service() is service_a

    def test_raises_when_no_service(self):
        registry = ModelRegistry()
        with pytest.raises(RuntimeError):
            registry.get_service()

    def test_returns_same_object_on_repeated_calls(self, service_a):
        registry = ModelRegistry(service_a)
        assert registry.get_service() is registry.get_service()


# ---------------------------------------------------------------------------
# predict()
# ---------------------------------------------------------------------------


class TestPredict:
    def test_predict_delegates_to_active_service(self, service_a):
        registry = ModelRegistry(service_a)
        result = registry.predict("breaking news shocking scandal")
        assert isinstance(result, PredictionResult)
        assert result.label in {"Real", "Fake"}
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_raises_when_no_service(self):
        registry = ModelRegistry()
        with pytest.raises(RuntimeError):
            registry.predict("some text")

    def test_predict_returns_prediction_result(self, service_a):
        registry = ModelRegistry(service_a)
        result = registry.predict("scientists publish new research on climate")
        assert isinstance(result, PredictionResult)
        assert isinstance(result.label, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.suspicious_phrases, list)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0


# ---------------------------------------------------------------------------
# swap()
# ---------------------------------------------------------------------------


class TestSwap:
    def test_swap_replaces_active_service(self, service_a, service_b):
        registry = ModelRegistry(service_a)
        registry.swap(service_b)
        assert registry.get_service() is service_b

    def test_swap_returns_old_service(self, service_a, service_b):
        registry = ModelRegistry(service_a)
        old = registry.swap(service_b)
        assert old is service_a

    def test_swap_from_none_returns_none(self, service_a):
        registry = ModelRegistry()
        old = registry.swap(service_a)
        assert old is None

    def test_swap_raises_for_non_service(self, service_a):
        registry = ModelRegistry(service_a)
        with pytest.raises(TypeError, match="PredictionService"):
            registry.swap("not a service")  # type: ignore[arg-type]

    def test_swap_raises_for_none(self, service_a):
        registry = ModelRegistry(service_a)
        with pytest.raises(TypeError):
            registry.swap(None)  # type: ignore[arg-type]

    def test_predict_uses_new_service_after_swap(self, service_a, service_b):
        """After swap(), predict() should use the new service."""
        # Wrap service_b with a mock to track calls.
        mock_service = MagicMock(spec=PredictionService)
        mock_service.predict.return_value = PredictionResult(
            label="Fake", confidence=0.99, suspicious_phrases=[], explanation="mocked"
        )

        registry = ModelRegistry(service_a)
        registry.swap(mock_service)

        result = registry.predict("any text")
        mock_service.predict.assert_called_once_with("any text")
        assert result.label == "Fake"
        assert result.explanation == "mocked"

    def test_multiple_swaps(self, service_a, service_b):
        """Registry should correctly track the latest service after many swaps."""
        registry = ModelRegistry(service_a)
        for i in range(10):
            target = service_b if i % 2 == 0 else service_a
            registry.swap(target)
        # After 10 swaps (0-indexed even → service_b last), service_a is last
        assert registry.get_service() is service_a


# ---------------------------------------------------------------------------
# Thread-safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_swaps_leave_registry_consistent(self, service_a, service_b):
        """Many threads swapping concurrently should not corrupt the registry."""
        registry = ModelRegistry(service_a)
        errors: list[Exception] = []

        def swap_repeatedly(svc, n: int) -> None:
            for _ in range(n):
                try:
                    registry.swap(svc)
                except Exception as exc:
                    errors.append(exc)

        threads = [
            threading.Thread(target=swap_repeatedly, args=(service_a, 50)),
            threading.Thread(target=swap_repeatedly, args=(service_b, 50)),
            threading.Thread(target=swap_repeatedly, args=(service_a, 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent swaps: {errors}"
        # After all swaps, the registry must hold one of the two valid services.
        assert registry.get_service() in {service_a, service_b}

    def test_predict_during_swap_does_not_raise(self, service_a, service_b):
        """predict() called concurrently with swap() should not raise."""
        registry = ModelRegistry(service_a)
        errors: list[Exception] = []

        def predict_loop(n: int) -> None:
            for _ in range(n):
                try:
                    registry.predict("breaking news shocking scandal")
                except RuntimeError:
                    # RuntimeError is acceptable only if the registry is empty,
                    # which should not happen here since we start with service_a.
                    errors.append(RuntimeError("predict raised RuntimeError unexpectedly"))
                except Exception as exc:
                    errors.append(exc)

        def swap_loop(n: int) -> None:
            for i in range(n):
                try:
                    registry.swap(service_b if i % 2 == 0 else service_a)
                except Exception as exc:
                    errors.append(exc)

        threads = [
            threading.Thread(target=predict_loop, args=(30,)),
            threading.Thread(target=swap_loop, args=(30,)),
            threading.Thread(target=predict_loop, args=(30,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent predict/swap: {errors}"

    def test_in_flight_predict_uses_captured_service(self, artifact_paths):
        """A predict() call that starts before a swap() completes against the
        service that was active when predict() was entered."""
        # Use a mock service that introduces a small delay so we can observe
        # the captured-reference behaviour.
        barrier = threading.Barrier(2)
        captured_services: list[PredictionService] = []

        class SlowService(PredictionService):
            """Overrides predict() to record which instance handled the call."""
            def predict(self, text: str):
                captured_services.append(self)
                # Signal that we've captured self, then wait for the swap to happen.
                barrier.wait(timeout=5)
                return super().predict(text)

        slow_svc = SlowService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )
        new_svc = PredictionService(
            vectorizer_path=artifact_paths["vectorizer"],
            lr_model_path=artifact_paths["lr_model"],
            metadata_path=artifact_paths["metadata"],
        )

        registry = ModelRegistry(slow_svc)

        predict_result: list = []

        def do_predict():
            result = registry.predict("breaking news shocking scandal")
            predict_result.append(result)

        def do_swap():
            # Wait until predict() has captured its service reference.
            barrier.wait(timeout=5)
            registry.swap(new_svc)

        t_predict = threading.Thread(target=do_predict)
        t_swap = threading.Thread(target=do_swap)

        t_predict.start()
        t_swap.start()
        t_predict.join(timeout=10)
        t_swap.join(timeout=10)

        # The in-flight predict() must have used slow_svc (the old service).
        assert len(captured_services) == 1
        assert captured_services[0] is slow_svc
        # The registry must now point to new_svc.
        assert registry.get_service() is new_svc
        # The prediction must have completed successfully.
        assert len(predict_result) == 1
        assert isinstance(predict_result[0], PredictionResult)
