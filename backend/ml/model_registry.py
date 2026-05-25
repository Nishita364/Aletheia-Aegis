"""
ModelRegistry: thread-safe hot-swap container for the active PredictionService.

Holds a reference to the active PredictionService and exposes an atomic
``swap()`` method so a newly trained model can be activated without a server
restart.  In-flight requests that already hold a reference to the old service
complete normally; only new calls to ``predict()`` (after the swap) use the
new service.

Requirements: 5.7
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from backend.ml.prediction_service import PredictionResult, PredictionService

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Thread-safe registry that holds the active :class:`PredictionService`.

    Usage
    -----
    ::

        registry = ModelRegistry(initial_service)

        # In a request handler:
        result = registry.predict(article_text)

        # After retraining completes:
        registry.swap(new_service)

    The ``swap()`` method replaces the internal reference under a lock so that
    concurrent calls to ``predict()`` either use the old service (if they
    acquired the reference before the swap) or the new service (if they
    acquire it after).  No request is left without a valid service.

    Parameters
    ----------
    service:
        The initial :class:`PredictionService` to activate.  May be ``None``
        if the registry is constructed before a service is available, but
        ``predict()`` will raise ``RuntimeError`` until a service is swapped
        in.
    """

    def __init__(self, service: Optional[PredictionService] = None) -> None:
        self._lock = threading.Lock()
        self._service: Optional[PredictionService] = service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def swap(self, new_service: PredictionService) -> PredictionService:
        """Atomically replace the active service with *new_service*.

        The replacement is performed under a lock so that the reference
        update is visible to all threads immediately after the call returns.
        Any in-flight ``predict()`` calls that already captured a local
        reference to the old service will complete against the old model;
        subsequent calls will use *new_service*.

        Parameters
        ----------
        new_service:
            The :class:`PredictionService` to activate.

        Returns
        -------
        PredictionService
            The *previous* active service (useful for cleanup or rollback).

        Raises
        ------
        TypeError
            If *new_service* is not a :class:`PredictionService` instance.
        """
        if not isinstance(new_service, PredictionService):
            raise TypeError(
                f"new_service must be a PredictionService instance, "
                f"got {type(new_service).__name__!r}"
            )

        with self._lock:
            old_service = self._service
            self._service = new_service

        logger.info(
            "ModelRegistry: swapped active service from %r to %r",
            old_service,
            new_service,
        )
        return old_service  # type: ignore[return-value]

    def get_service(self) -> PredictionService:
        """Return the currently active :class:`PredictionService`.

        Returns
        -------
        PredictionService
            The active service.

        Raises
        ------
        RuntimeError
            If no service has been registered yet.
        """
        with self._lock:
            service = self._service

        if service is None:
            raise RuntimeError(
                "ModelRegistry has no active PredictionService. "
                "Call swap() with a valid service before predicting."
            )
        return service

    def predict(self, text: str) -> PredictionResult:
        """Classify *text* using the currently active service.

        Captures a local reference to the active service *before* delegating,
        so a concurrent ``swap()`` during prediction does not affect this
        call — the prediction completes against the model that was active
        when ``predict()`` was entered.

        Parameters
        ----------
        text:
            Raw article text to classify.

        Returns
        -------
        PredictionResult
            The prediction from the active service.

        Raises
        ------
        RuntimeError
            If no service has been registered yet.
        """
        # Capture the reference outside the lock so the lock is held only
        # for the pointer read, not for the (potentially slow) prediction.
        service = self.get_service()
        return service.predict(text)
