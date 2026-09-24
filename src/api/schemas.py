"""Request/response models for the API layer.

These Pydantic models define the API's external contract. They are kept
separate from the detector's internal dataclasses so the HTTP surface can
evolve independently of the business logic.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from src.detector import DetectionResult


class DetectRequest(BaseModel):
    """Body for ``POST /detect``."""

    file_paths: List[str] = Field(
        default_factory=list,
        description="Repository file paths to inspect (relative or nested).",
        examples=[["src/app/package.json", "README.md"]],
    )


class DetectResponse(BaseModel):
    """Serialized :class:`~src.detector.DetectionResult`."""

    language: str = Field(description="Detected language, or 'unknown'.")
    matched_markers: List[str] = Field(
        description="Marker filenames that triggered the match."
    )
    is_supported: bool = Field(
        description="Whether a supported stack was detected."
    )

    @classmethod
    def from_result(cls, result: DetectionResult) -> "DetectResponse":
        """Adapt a detector :class:`DetectionResult` into the API response."""
        return cls(
            language=result.language.value,
            matched_markers=result.matched_markers,
            is_supported=result.is_supported,
        )
