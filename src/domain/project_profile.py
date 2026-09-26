"""Normalized domain model for a single detected project.

:class:`ProjectProfile` is the shared representation that later phases build
on: language-specific parsers populate its fields, and the future
``PipelineBuilder`` reads them to emit CI/CD configuration.

Design notes
------------
This is a plain stdlib :func:`~dataclasses.dataclass`, not a Pydantic model,
because the profile is internal domain state rather than an HTTP contract.
Only :attr:`language` is required; every other field is optional because a
parser may not be able to detect it. ``has_docker`` is a plain ``bool`` that
defaults to ``False`` to avoid three-state ambiguity.

A profile represents exactly one project. Monorepo / multi-project support is
intentionally out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.detector.language import Language


@dataclass
class ProjectProfile:
    """Normalized description of a single detected project.

    Args:
        language: The project's primary language. Always known (it comes
            from stack detection), so this is the only required field.
        version: Language/runtime version (e.g. ``"3.12"``, ``"17"``).
        framework: Application framework (e.g. ``"spring-boot"``,
            ``"fastapi"``, ``"express"``).
        build_tool: Build/dependency tool (e.g. ``"maven"``, ``"pip"``,
            ``"npm"``).
        test_framework: Test framework (e.g. ``"junit"``, ``"pytest"``,
            ``"jest"``).
        test_command: Command used to run tests (e.g. ``"pytest"``,
            ``"mvn test"``).
        lint_tool: Lint/static-analysis tool (e.g. ``"ruff"``,
            ``"checkstyle"``, ``"eslint"``).
        lint_command: Command used to run the linter (e.g. ``"ruff check ."``).
        build_command: Command used to build the application/artifact
            (e.g. ``"mvn package"``, ``"npm run build"``), or ``None`` when the
            project has no build step.
        has_docker: Whether the project ships a Docker setup. Defaults to
            ``False`` when no Dockerfile is detected.
    """

    language: Language
    version: Optional[str] = None
    framework: Optional[str] = None
    build_tool: Optional[str] = None
    test_framework: Optional[str] = None
    test_command: Optional[str] = None
    lint_tool: Optional[str] = None
    lint_command: Optional[str] = None
    build_command: Optional[str] = None
    has_docker: bool = False
