"""Node.js parser.

Builds a :class:`~src.domain.ProjectProfile` from a repository's file listing
and the raw text of its ``package.json``.

Like :class:`~src.parsers.java_parser.JavaParser`, this parser is **pure**
(no I/O) and **best-effort**: unknown fields stay ``None``, and missing or
malformed input never raises.
"""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Dict, Iterable, Optional, Sequence, Tuple

from src.detector.language import Language
from src.domain import ProjectProfile

# Ordered framework detection: dependency name -> framework label.
# Order defines precedence when several are present (first match wins). Next.js
# is checked before React because a Next.js app also depends on React.
_FRAMEWORKS: Tuple[Tuple[str, str], ...] = (
    ("next", "next.js"),
    ("@angular/core", "angular"),
    ("react", "react"),
    ("express", "express"),
)


class NodeParser:
    """Parses a Node.js project into a :class:`ProjectProfile`.

    Supports ``package.json`` as the dependency/script source. ``build_tool``
    is reported as ``"npm"`` when a valid ``package.json`` is present.
    """

    _BUILD_TOOL = "npm"

    def parse(
        self,
        file_paths: Sequence[str],
        package_json: Optional[str] = None,
    ) -> ProjectProfile:
        """Build a :class:`ProjectProfile` for a Node.js project.

        Args:
            file_paths: Repository file paths. Used to detect a ``Dockerfile``.
            package_json: Raw text of ``package.json``, if available.
        """
        has_docker = _has_dockerfile(file_paths)

        pkg = self._safe_parse_json(package_json)
        if pkg is None:
            # Missing/malformed package.json -> minimal Node profile, no crash.
            return ProjectProfile(
                language=Language.NODEJS,
                has_docker=has_docker,
            )

        deps = self._collect_dependencies(pkg)
        scripts = pkg.get("scripts", {}) if isinstance(pkg.get("scripts"), dict) else {}

        test_framework = self._extract_test_framework(deps)
        lint_tool = "eslint" if "eslint" in deps else None

        return ProjectProfile(
            language=Language.NODEJS,
            version=self._extract_node_version(pkg),
            framework=self._extract_framework(deps),
            build_tool=self._BUILD_TOOL,
            test_framework=test_framework,
            test_command=self._test_command(scripts, test_framework),
            lint_tool=lint_tool,
            lint_command=self._lint_command(scripts, lint_tool),
            has_docker=has_docker,
        )

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_parse_json(package_json: Optional[str]) -> Optional[dict]:
        """Parse package.json text into a dict; ``None`` on missing/invalid JSON."""
        if not package_json or not package_json.strip():
            return None
        try:
            parsed = json.loads(package_json)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _collect_dependencies(pkg: dict) -> set[str]:
        """Union of dependency names across the common dependency sections."""
        names: set[str] = set()
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            block = pkg.get(section)
            if isinstance(block, dict):
                names.update(block.keys())
        return names

    # ------------------------------------------------------------------ #
    # Field extraction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_node_version(pkg: dict) -> Optional[str]:
        """Node version from ``engines.node`` (specifier stripped)."""
        engines = pkg.get("engines")
        if not isinstance(engines, dict):
            return None
        node = engines.get("node")
        if not node:
            return None
        match = re.search(r"\d+(?:\.\d+)*", str(node))
        return match.group(0) if match else None

    @staticmethod
    def _extract_framework(deps: Iterable[str]) -> Optional[str]:
        """First matching framework by precedence, or ``None``."""
        dep_set = set(deps)
        for needle, label in _FRAMEWORKS:
            if needle in dep_set:
                return label
        return None

    @staticmethod
    def _extract_test_framework(deps: Iterable[str]) -> Optional[str]:
        """``"jest"`` or ``"vitest"`` if present, else ``None``."""
        dep_set = set(deps)
        if "jest" in dep_set:
            return "jest"
        if "vitest" in dep_set:
            return "vitest"
        return None

    @staticmethod
    def _test_command(scripts: Dict[str, str], test_framework: Optional[str]) -> Optional[str]:
        """Prefer ``scripts.test``; else a conventional command per framework."""
        script = scripts.get("test")
        if isinstance(script, str) and script.strip():
            return "npm test"
        if test_framework in ("jest", "vitest"):
            return f"npx {test_framework}"
        return None

    @staticmethod
    def _lint_command(scripts: Dict[str, str], lint_tool: Optional[str]) -> Optional[str]:
        """Prefer ``scripts.lint``; else ``npx eslint .`` when ESLint detected."""
        script = scripts.get("lint")
        if isinstance(script, str) and script.strip():
            return "npm run lint"
        if lint_tool == "eslint":
            return "npx eslint ."
        return None


def _has_dockerfile(file_paths: Iterable[str]) -> bool:
    """Return ``True`` if any path's basename is exactly ``Dockerfile``."""
    for path in file_paths:
        if not path:
            continue
        if PurePosixPath(str(path).strip()).name == "Dockerfile":
            return True
    return False
