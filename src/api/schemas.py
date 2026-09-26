"""Request/response models for the API layer.

These Pydantic models define the API's external contract. They are kept
separate from the detector's internal dataclasses so the HTTP surface can
evolve independently of the business logic.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from src.detector import DetectionResult
from src.domain import ProjectProfile


class DetectRequest(BaseModel):
    """Body for ``POST /detect``."""

    file_paths: List[str] = Field(
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


class GenerateRequest(BaseModel):
    """Body for ``POST /generate``."""

    repo_url: str = Field(
        description="Public GitHub repository URL.",
        examples=["https://github.com/owner/repository"],
    )
    include_docker: bool = Field(
        default=False,
        description=(
            "Whether to include a Docker build step. Requires the repository "
            "to contain a Dockerfile."
        ),
    )
    push_docker: bool = Field(
        default=False,
        description=(
            "Whether to push the built image to GitHub Container Registry "
            "(GHCR). Requires include_docker=True."
        ),
    )


class ProjectProfilePayload(BaseModel):
    """Serialized :class:`~src.domain.ProjectProfile` for API responses."""

    language: str
    version: Optional[str] = None
    framework: Optional[str] = None
    build_tool: Optional[str] = None
    test_framework: Optional[str] = None
    test_command: Optional[str] = None
    lint_tool: Optional[str] = None
    lint_command: Optional[str] = None
    build_command: Optional[str] = None
    has_docker: bool = False

    @classmethod
    def from_profile(cls, profile: ProjectProfile) -> "ProjectProfilePayload":
        """Adapt a domain :class:`ProjectProfile` into the API payload."""
        return cls(
            language=profile.language.value,
            version=profile.version,
            framework=profile.framework,
            build_tool=profile.build_tool,
            test_framework=profile.test_framework,
            test_command=profile.test_command,
            lint_tool=profile.lint_tool,
            lint_command=profile.lint_command,
            build_command=profile.build_command,
            has_docker=profile.has_docker,
        )


class GenerateResponse(BaseModel):
    """Response for ``POST /generate``."""

    language: str = Field(description="Detected primary language.")
    profile: ProjectProfilePayload = Field(
        description="The analyzed project profile."
    )
    workflow_yaml: str = Field(
        description="Generated GitHub Actions workflow YAML."
    )

    @classmethod
    def from_parts(
        cls, profile: ProjectProfile, workflow_yaml: str
    ) -> "GenerateResponse":
        """Build the response from a profile and its generated workflow."""
        return cls(
            language=profile.language.value,
            profile=ProjectProfilePayload.from_profile(profile),
            workflow_yaml=workflow_yaml,
        )
