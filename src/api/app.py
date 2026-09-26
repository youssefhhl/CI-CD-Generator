"""FastAPI application exposing stack detection.

The API layer is a thin adapter over :class:`~src.detector.StackDetector`.
All detection logic lives in the detector; this module only wires HTTP
requests to it and serializes the result.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from src.analyzer import ProjectAnalyzer, UnsupportedProjectError
from src.detector import StackDetector
from src.generator import PipelineBuilder, UnsupportedLanguageError
from src.repository import (
    GitHubRepositoryReader,
    InvalidRepositoryUrlError,
    RepositoryAccessError,
    RepositoryApiError,
    RepositoryNotFoundError,
)

from .schemas import (
    DetectRequest,
    DetectResponse,
    GenerateRequest,
    GenerateResponse,
)

# Single shared instances, reused across requests. They are stateless and
# cheap, but sharing keeps the wiring explicit and injectable.
_detector = StackDetector()
_reader = GitHubRepositoryReader()
_analyzer = ProjectAnalyzer()
_builder = PipelineBuilder()


def get_detector() -> StackDetector:
    """Dependency provider for the shared :class:`StackDetector`."""
    return _detector


def get_reader() -> GitHubRepositoryReader:
    """Dependency provider for the shared :class:`GitHubRepositoryReader`."""
    return _reader


def get_analyzer() -> ProjectAnalyzer:
    """Dependency provider for the shared :class:`ProjectAnalyzer`."""
    return _analyzer


def get_builder() -> PipelineBuilder:
    """Dependency provider for the shared :class:`PipelineBuilder`."""
    return _builder


app = FastAPI(
    title="CI/CD Workflow Generator",
    description=(
        "Detects a repository's primary language and generates a GitHub "
        "Actions CI workflow for it."
    ),
    version="0.2.0",
)


@app.post("/detect", response_model=DetectResponse, tags=["detection"])
def detect(
    request: DetectRequest,
    detector: StackDetector = Depends(get_detector),
) -> DetectResponse:
    """Detect the primary language for the given repository file paths."""
    result = detector.detect(request.file_paths)
    return DetectResponse.from_result(result)


@app.post("/generate", response_model=GenerateResponse, tags=["generation"])
def generate(
    request: GenerateRequest,
    reader: GitHubRepositoryReader = Depends(get_reader),
    analyzer: ProjectAnalyzer = Depends(get_analyzer),
    builder: PipelineBuilder = Depends(get_builder),
) -> GenerateResponse:
    """Generate a GitHub Actions workflow for a public GitHub repository.

    Reads the repository, analyzes it into a project profile, and renders a
    workflow. It does not modify the repository.
    """
    try:
        snapshot = reader.read(request.repo_url)
    except InvalidRepositoryUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RepositoryAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RepositoryApiError as exc:
        # Upstream GitHub/network failure.
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        profile = analyzer.analyze(snapshot)
    except UnsupportedProjectError as exc:
        # Repository read fine, but its stack isn't supported.
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        workflow_yaml = builder.build(profile)
    except UnsupportedLanguageError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=422, detail=str(exc))

    return GenerateResponse.from_parts(profile, workflow_yaml)
