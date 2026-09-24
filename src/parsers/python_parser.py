"""Python parser.

Builds a :class:`~src.domain.ProjectProfile` from a repository's file listing
and the raw text of its ``requirements.txt`` and/or ``pyproject.toml``.

Like :class:`~src.parsers.java_parser.JavaParser`, this parser is **pure**
(no I/O) and **best-effort**: unknown fields stay ``None``, and missing or
malformed input never raises.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.detector.language import Language
from src.domain import ProjectProfile

# Ordered framework detection: dependency name substring -> framework label.
# Order defines precedence when several are present (first match wins).
_FRAMEWORKS: Tuple[Tuple[str, str], ...] = (
    ("fastapi", "fastapi"),
    ("django", "django"),
    ("flask", "flask"),
)


class PythonParser:
    """Parses a Python project into a :class:`ProjectProfile`.

    Supports ``requirements.txt`` and ``pyproject.toml`` as dependency
    sources. ``build_tool`` is reported as ``"pip"`` (the conventional MVP
    default) whenever any dependency source is present.
    """

    _BUILD_TOOL = "pip"

    def parse(
        self,
        file_paths: Sequence[str],
        requirements_txt: Optional[str] = None,
        pyproject_toml: Optional[str] = None,
    ) -> ProjectProfile:
        """Build a :class:`ProjectProfile` for a Python project.

        Args:
            file_paths: Repository file paths. Used to detect a ``Dockerfile``.
            requirements_txt: Raw text of ``requirements.txt``, if available.
            pyproject_toml: Raw text of ``pyproject.toml``, if available.
        """
        has_docker = _has_dockerfile(file_paths)

        pyproject = self._safe_parse_toml(pyproject_toml)
        # Normalized set of dependency names (lowercased, no version specifiers).
        deps = self._collect_dependencies(requirements_txt, pyproject)
        has_config = bool(requirements_txt and requirements_txt.strip()) or pyproject is not None

        framework = self._extract_framework(deps)
        test_framework = self._extract_test_framework(deps)

        return ProjectProfile(
            language=Language.PYTHON,
            version=self._extract_python_version(pyproject),
            framework=framework,
            build_tool=self._BUILD_TOOL if has_config else None,
            test_framework=test_framework,
            test_command=self._test_command(test_framework),
            lint_tool="ruff" if "ruff" in deps else None,
            lint_command="ruff check ." if "ruff" in deps else None,
            has_docker=has_docker,
        )

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_parse_toml(pyproject_toml: Optional[str]) -> Optional[dict]:
        """Parse pyproject text into a dict; ``None`` on missing/invalid TOML."""
        if not pyproject_toml or not pyproject_toml.strip():
            return None
        try:
            return tomllib.loads(pyproject_toml)
        except tomllib.TOMLDecodeError:
            return None

    @staticmethod
    def _normalize_name(raw: str) -> Optional[str]:
        """Extract a bare, lowercased package name from a dependency spec."""
        # Strip environment markers and comments, then split off any version
        # specifier / extras. E.g. "Flask[async]>=2.0  # web" -> "flask".
        spec = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not spec:
            return None
        match = re.match(r"[A-Za-z0-9._-]+", spec)
        if not match:
            return None
        return match.group(0).split("[", 1)[0].lower()

    @classmethod
    def _collect_dependencies(
        cls,
        requirements_txt: Optional[str],
        pyproject: Optional[dict],
    ) -> set[str]:
        """Collect normalized dependency names from both sources."""
        names: set[str] = set()

        if requirements_txt:
            for line in requirements_txt.splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue  # skip blanks, comments, and pip flags (-r, -e, ...)
                name = cls._normalize_name(line)
                if name:
                    names.add(name)

        if pyproject:
            project = pyproject.get("project", {})
            for dep in project.get("dependencies", []) or []:
                name = cls._normalize_name(str(dep))
                if name:
                    names.add(name)
            # optional-dependencies: {group: [specs...]}
            for group in (project.get("optional-dependencies", {}) or {}).values():
                for dep in group or []:
                    name = cls._normalize_name(str(dep))
                    if name:
                        names.add(name)

        return names

    # ------------------------------------------------------------------ #
    # Field extraction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_python_version(pyproject: Optional[dict]) -> Optional[str]:
        """Python version from ``project.requires-python`` (specifier stripped)."""
        if not pyproject:
            return None
        requires = pyproject.get("project", {}).get("requires-python")
        if not requires:
            return None
        # e.g. ">=3.12", "==3.11", "~=3.10" -> "3.12" / "3.11" / "3.10".
        match = re.search(r"\d+(?:\.\d+)*", str(requires))
        return match.group(0) if match else None

    @staticmethod
    def _extract_framework(deps: Iterable[str]) -> Optional[str]:
        """First matching framework by precedence, or ``None``."""
        dep_set = set(deps)
        for needle, label in _FRAMEWORKS:
            if any(needle in name for name in dep_set):
                return label
        return None

    @staticmethod
    def _extract_test_framework(deps: Iterable[str]) -> Optional[str]:
        """``"pytest"`` if pytest is a dependency, else ``None``.

        ``unittest`` is part of the stdlib and rarely appears as a dependency,
        so it cannot be reliably detected from dependency lists alone; we only
        claim it when there is a real signal (pytest).
        """
        return "pytest" if "pytest" in set(deps) else None

    @staticmethod
    def _test_command(test_framework: Optional[str]) -> Optional[str]:
        """Conventional test command when a test framework was detected."""
        if test_framework == "pytest":
            return "pytest"
        return None


def _has_dockerfile(file_paths: Iterable[str]) -> bool:
    """Return ``True`` if any path's basename is exactly ``Dockerfile``."""
    for path in file_paths:
        if not path:
            continue
        if PurePosixPath(str(path).strip()).name == "Dockerfile":
            return True
    return False
