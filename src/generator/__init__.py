"""CI/CD workflow generation.

Exposes :class:`PipelineBuilder`, which renders a GitHub Actions workflow
YAML string from a :class:`~src.domain.ProjectProfile`.
"""

from .pipeline_builder import PipelineBuilder, UnsupportedLanguageError

__all__ = ["PipelineBuilder", "UnsupportedLanguageError"]
