"""
Pydantic data models and API schemas for the Fake News Detector.

Defines request/response schemas with validation rules enforced at the
API boundary, ensuring all payloads conform to the defined contract.

Requirements: 1.3, 1.4, 2.1, 3.1, 12.3, 12.5
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared / nested models
# ---------------------------------------------------------------------------


class FactCheckResult(BaseModel):
    """A single fact-check result returned alongside a prediction.

    This is the Pydantic version of the dataclass defined in
    ``services/fact_check_client.py``.  It is used for API serialisation.
    """

    claim: str
    rating: str
    source: str


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class SubmissionRequest(BaseModel):
    """Payload for ``POST /api/v1/submissions``.

    Exactly one of ``text`` or ``url`` must be provided and non-empty.

    Validation rules
    ----------------
    - Exactly one of ``text`` / ``url`` must be non-null and non-empty.
    - ``text`` must not exceed 10,000 characters.
    - ``text`` must not be whitespace-only.
    - ``url`` must match ``^https?://``.
    """

    text: Optional[str] = Field(
        default=None,
        description="Raw article text (max 10,000 characters).",
    )
    url: Optional[str] = Field(
        default=None,
        description="Article URL (must start with http:// or https://).",
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) > 10_000:
            raise ValueError("text must not exceed 10,000 characters")
        if v.strip() == "":
            raise ValueError("text must not be whitespace-only")
        # Require at least 10 words so the model has enough signal
        # (Telugu/Hindi words are longer — 10 words ≈ 20+ English words after translation)
        word_count = len(v.split())
        if word_count < 10:
            raise ValueError(
                f"text is too short ({word_count} words). "
                "Please provide at least a few sentences for accurate analysis."
            )
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^https?://", v):
            raise ValueError("url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def validate_mutual_exclusivity(self) -> "SubmissionRequest":
        """Ensure exactly one of text/url is provided and non-empty."""
        has_text = self.text is not None and self.text.strip() != ""
        has_url = self.url is not None and self.url.strip() != ""

        if has_text and has_url:
            raise ValueError(
                "Exactly one of 'text' or 'url' must be provided, not both."
            )
        if not has_text and not has_url:
            raise ValueError(
                "Exactly one of 'text' or 'url' must be provided; both are missing."
            )
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PredictionResponse(BaseModel):
    """Full prediction result returned by ``POST /api/v1/submissions``.

    Validation rules
    ----------------
    - ``label`` must be exactly ``"Real"`` or ``"Fake"``.
    - ``confidence`` must be in ``[0.0, 1.0]``.
    - ``language`` must be one of ``"en"``, ``"te"``, ``"hi"``.
    - ``trust_rating`` must be one of ``"High"``, ``"Medium"``, ``"Low"``,
      ``"Unknown"``, or ``None``.
    """

    id: UUID = Field(description="Unique identifier for this prediction (UUID v4).")
    label: Literal["Real", "Fake"] = Field(
        description="Classification result: 'Real' or 'Fake'."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Probability of the predicted class, in [0.0, 1.0].",
    )
    suspicious_phrases: list[str] = Field(
        default_factory=list,
        description="Top TF-IDF tokens that appear in the original text.",
    )
    explanation: str = Field(
        description="Plain-language explanation of the prediction."
    )
    fact_checks: list[FactCheckResult] = Field(
        default_factory=list,
        description="Matching fact-check entries from the Fact Check API.",
    )
    trust_rating: Optional[Literal["High", "Medium", "Low", "Unknown"]] = Field(
        default=None,
        description="Source domain trust rating, or null if not applicable.",
    )
    language: Literal["en", "te", "hi"] = Field(
        description="Detected language of the submission."
    )
    timestamp: datetime = Field(
        description="UTC timestamp of when the prediction was generated (ISO 8601)."
    )
    input_text: Optional[str] = Field(
        default=None,
        description="The article text that was analysed (null for URL submissions).",
    )
    input_url: Optional[str] = Field(
        default=None,
        description="The URL that was submitted (null for text submissions).",
    )

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ---------------------------------------------------------------------------
# History record schema
# ---------------------------------------------------------------------------


class HistoryRecord(BaseModel):
    """A persisted submission + prediction record from the History_Store.

    Used for ``GET /api/v1/history`` and ``GET /api/v1/history/{id}``
    responses.
    """

    id: UUID = Field(description="Primary key (UUID).")
    input_text: Optional[str] = Field(
        default=None,
        description="Extracted or pasted article text.",
    )
    input_url: Optional[str] = Field(
        default=None,
        description="Original URL if the submission was URL-based.",
    )
    label: Literal["Real", "Fake"] = Field(
        description="Classification result: 'Real' or 'Fake'."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score in [0.0, 1.0].",
    )
    suspicious_phrases: list[str] = Field(
        default_factory=list,
        description="Suspicious phrases identified in the submission.",
    )
    explanation: str = Field(
        description="Plain-language explanation of the prediction."
    )
    fact_checks: list[FactCheckResult] = Field(
        default_factory=list,
        description="Fact-check results associated with this submission.",
    )
    trust_rating: Optional[Literal["High", "Medium", "Low", "Unknown"]] = Field(
        default=None,
        description="Source domain trust rating.",
    )
    language: Literal["en", "te", "hi"] = Field(
        description="Detected language of the submission."
    )
    created_at: datetime = Field(
        description="UTC timestamp when the record was created (ISO 8601)."
    )

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ---------------------------------------------------------------------------
# Admin / retrain schemas
# ---------------------------------------------------------------------------


class RetrainJob(BaseModel):
    """Status record for a model retraining job.

    Returned by ``POST /api/v1/admin/retrain`` and polled via
    ``GET /api/v1/admin/retrain/{job_id}``.
    """

    job_id: UUID = Field(description="Unique identifier for this retrain job.")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        description="Current state of the retraining job."
    )
    accuracy: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model accuracy on the test split after training completes.",
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the job started, or null if not yet started.",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the job finished, or null if still running.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the job failed, otherwise null.",
    )

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
