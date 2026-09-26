"""Orchestration layer.

Exposes :class:`ProjectAnalyzer`, which connects the repository snapshot,
stack detector, and language parsers to produce a
:class:`~src.domain.ProjectProfile`.
"""

from .project_analyzer import ProjectAnalyzer, UnsupportedProjectError

__all__ = ["ProjectAnalyzer", "UnsupportedProjectError"]
