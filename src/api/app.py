"""FastAPI application exposing stack detection.

The API layer is a thin adapter over :class:`~src.detector.StackDetector`.
All detection logic lives in the detector; this module only wires HTTP
requests to it and serializes the result.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from src.detector import StackDetector

from .schemas import DetectRequest, DetectResponse

# Single shared detector instance, reused across requests. It is stateless
# and cheap, but sharing keeps the wiring explicit and injectable.
_detector = StackDetector()


def get_detector() -> StackDetector:
    """Dependency provider for the shared :class:`StackDetector`."""
    return _detector


app = FastAPI(
    title="CI/CD Workflow Generator",
    description="Detects a repository's primary language from its file paths.",
    version="0.1.0",
)


@app.post("/detect", response_model=DetectResponse, tags=["detection"])
def detect(
    request: DetectRequest,
    detector: StackDetector = Depends(get_detector),
) -> DetectResponse:
    """Detect the primary language for the given repository file paths."""
    result = detector.detect(request.file_paths)
    return DetectResponse.from_result(result)
