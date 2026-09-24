"""Domain models for the CI/CD Workflow Generator.

Shared, transport-agnostic representations consumed by parsers and the
future ``PipelineBuilder``.
"""

from .project_profile import ProjectProfile

__all__ = ["ProjectProfile"]
