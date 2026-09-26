"""Orchestration: turn a RepositorySnapshot into a ProjectProfile.

This layer wires together the existing components without reimplementing any
of them::

    RepositorySnapshot
        -> StackDetector        (which language?)
        -> language parser       (extract details from config contents)
        -> ProjectProfile

The analyzer performs no GitHub calls, no YAML generation, and no repository
modification. It only selects and drives the right parser for the detected
language.
"""

from __future__ import annotations

from typing import Optional

from src.detector import Language, StackDetector
from src.domain import ProjectProfile
from src.parsers import JavaParser, NodeParser, PythonParser
from src.repository import RepositorySnapshot


class UnsupportedProjectError(Exception):
    """Raised when the snapshot's stack cannot be mapped to a parser."""


class ProjectAnalyzer:
    """Analyzes a :class:`RepositorySnapshot` into a :class:`ProjectProfile`.

    Reuses the existing detector and parsers as-is. The detector's Python ->
    Node.js -> Java precedence is preserved because detection is delegated
    entirely to :class:`StackDetector`.
    """

    def __init__(
        self,
        detector: Optional[StackDetector] = None,
        python_parser: Optional[PythonParser] = None,
        node_parser: Optional[NodeParser] = None,
        java_parser: Optional[JavaParser] = None,
    ) -> None:
        """Create an analyzer, optionally injecting components (e.g. for reuse)."""
        self._detector = detector or StackDetector()
        self._python_parser = python_parser or PythonParser()
        self._node_parser = node_parser or NodeParser()
        self._java_parser = java_parser or JavaParser()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def analyze(self, snapshot: RepositorySnapshot) -> ProjectProfile:
        """Detect the stack and build a :class:`ProjectProfile` for it.

        Args:
            snapshot: Raw repository data (file paths + relevant config text).

        Returns:
            The populated :class:`ProjectProfile`.

        Raises:
            UnsupportedProjectError: If no supported language is detected.
        """
        result = self._detector.detect(snapshot.file_paths)
        language = result.language

        if language is Language.PYTHON:
            return self._python_parser.parse(
                snapshot.file_paths,
                requirements_txt=self._select(snapshot, "requirements.txt"),
                pyproject_toml=self._select(snapshot, "pyproject.toml"),
            )
        if language is Language.NODEJS:
            return self._node_parser.parse(
                snapshot.file_paths,
                package_json=self._select(snapshot, "package.json"),
            )
        if language is Language.JAVA:
            return self._java_parser.parse(
                snapshot.file_paths,
                pom_xml=self._select(snapshot, "pom.xml"),
            )

        # Language.UNKNOWN or any unmapped language.
        raise UnsupportedProjectError(
            f"No parser available for detected language: {language.value!r}"
        )

    # ------------------------------------------------------------------ #
    # Config selection
    # ------------------------------------------------------------------ #

    @staticmethod
    def _select(snapshot: RepositorySnapshot, basename: str) -> Optional[str]:
        """Select the content of one config file by basename.

        Selection strategy (deterministic, no monorepo support):

        * If a root-level file with this basename exists (path == basename),
          use it.
        * Otherwise, among all paths sharing this basename, pick the
          lexicographically smallest path (stable and predictable).
        * If none exist, return ``None`` so the parser applies its own
          best-effort handling of missing config.
        """
        contents = snapshot.file_contents

        # Prefer the root-level file.
        if basename in contents:
            return contents[basename]

        # Otherwise, deterministic pick among nested matches.
        candidates = sorted(
            path
            for path in contents
            if path.rsplit("/", 1)[-1] == basename
        )
        if candidates:
            return contents[candidates[0]]
        return None
