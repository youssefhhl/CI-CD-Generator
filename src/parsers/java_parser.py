"""Java (Maven-only) parser.

Builds a :class:`~src.domain.ProjectProfile` from a repository's file listing
and the raw text of its ``pom.xml``.

Design notes
------------
The parser is **pure** and **best-effort**:

* It performs no I/O. Callers pass in the file paths and the ``pom.xml``
  content; reading files / talking to GitHub is someone else's job.
* Any field it cannot determine is left at its ``ProjectProfile`` default
  (``None`` for optionals, ``False`` for ``has_docker``).
* Missing or malformed ``pom.xml`` never raises: the parser falls back to a
  minimal Maven profile.

Maven POMs use a default XML namespace
(``http://maven.apache.org/POM/4.0.0``). Rather than thread that namespace
through every lookup, helpers match on the *local* tag name (the part after
any ``{namespace}`` prefix), which is robust to namespace variation.

Gradle is intentionally not supported here.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from typing import Iterable, List, Optional, Sequence, Tuple

from src.detector.language import Language
from src.domain import ProjectProfile


class JavaParser:
    """Parses a Maven-based Java project into a :class:`ProjectProfile`.

    ``build_tool`` is always ``"maven"`` and ``test_command`` is always
    ``"mvn test"`` for this parser, since it is only invoked for Maven Java
    projects. ``test_command`` is independent of ``test_framework``: a Maven
    project can always run ``mvn test`` regardless of which (if any) test
    framework is detected.
    """

    #: Constant build tool for this parser.
    _BUILD_TOOL = "maven"
    #: Constant test command for any Maven project.
    _TEST_COMMAND = "mvn test"
    #: Constant build command for any Maven project. ``mvn package`` compiles,
    #: runs the test phase, and produces the artifact.
    _BUILD_COMMAND = "mvn package"

    def parse(
        self,
        file_paths: Sequence[str],
        pom_xml: Optional[str] = None,
    ) -> ProjectProfile:
        """Build a :class:`ProjectProfile` for a Maven Java project.

        Args:
            file_paths: Repository file paths (relative or nested). Used to
                detect a ``Dockerfile``. Only basenames are considered.
            pom_xml: Raw text of ``pom.xml``, if available. May be ``None`` or
                malformed; in that case a minimal Maven profile is returned.

        Returns:
            A best-effort :class:`ProjectProfile`. Fields that cannot be
            determined are left at their defaults.
        """
        # has_docker is determined independently of the pom.
        has_docker = self._has_dockerfile(file_paths)

        root = self._safe_parse_xml(pom_xml)
        if root is None:
            # Missing/malformed pom -> minimal Maven profile, never crash.
            return ProjectProfile(
                language=Language.JAVA,
                build_tool=self._BUILD_TOOL,
                test_command=self._TEST_COMMAND,
                build_command=self._BUILD_COMMAND,
                has_docker=has_docker,
            )

        lint_tool, lint_command = self._extract_lint(root)
        return ProjectProfile(
            language=Language.JAVA,
            version=self._extract_java_version(root),
            framework=self._extract_framework(root),
            build_tool=self._BUILD_TOOL,
            test_framework=self._extract_test_framework(root),
            test_command=self._TEST_COMMAND,
            lint_tool=lint_tool,
            lint_command=lint_command,
            build_command=self._BUILD_COMMAND,
            has_docker=has_docker,
        )

    # ------------------------------------------------------------------ #
    # XML / path helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _localname(tag: str) -> str:
        """Return an ElementTree tag without its ``{namespace}`` prefix."""
        if "}" in tag:
            return tag.rsplit("}", 1)[1]
        return tag

    @classmethod
    def _find(cls, element: ET.Element, *local_names: str) -> Optional[ET.Element]:
        """Descend through direct children by local tag name.

        Namespace-agnostic equivalent of chained ``element.find`` calls.
        Returns the first matching element at each level, or ``None`` if any
        level is missing.
        """
        current: Optional[ET.Element] = element
        for name in local_names:
            if current is None:
                return None
            current = next(
                (
                    child
                    for child in current
                    if cls._localname(child.tag) == name
                ),
                None,
            )
        return current

    @classmethod
    def _iter_local(cls, element: ET.Element, local_name: str) -> Iterable[ET.Element]:
        """Yield all descendants whose local tag name matches ``local_name``."""
        for descendant in element.iter():
            if cls._localname(descendant.tag) == local_name:
                yield descendant

    @classmethod
    def _text(cls, element: Optional[ET.Element]) -> Optional[str]:
        """Stripped text of an element, or ``None`` if empty/absent."""
        if element is None or element.text is None:
            return None
        text = element.text.strip()
        return text or None

    @staticmethod
    def _safe_parse_xml(pom_xml: Optional[str]) -> Optional[ET.Element]:
        """Parse pom text into a root element; ``None`` on missing/invalid XML."""
        if not pom_xml or not pom_xml.strip():
            return None
        try:
            return ET.fromstring(pom_xml)
        except ET.ParseError:
            return None

    @classmethod
    def _has_dockerfile(cls, file_paths: Iterable[str]) -> bool:
        """Return ``True`` if any path's basename is exactly ``Dockerfile``."""
        for path in file_paths:
            if not path:
                continue
            if PurePosixPath(str(path).strip()).name == "Dockerfile":
                return True
        return False

    # ------------------------------------------------------------------ #
    # Field extraction
    # ------------------------------------------------------------------ #

    def _artifact_ids(self, root: ET.Element) -> List[str]:
        """All ``<artifactId>`` values in the pom (dependencies, plugins, etc.)."""
        ids: List[str] = []
        for element in self._iter_local(root, "artifactId"):
            text = self._text(element)
            if text:
                ids.append(text)
        return ids

    def _properties(self, root: ET.Element) -> dict[str, str]:
        """Return the ``<properties>`` block as a ``{name: value}`` dict."""
        props: dict[str, str] = {}
        properties = self._find(root, "properties")
        if properties is None:
            return props
        for child in properties:
            value = self._text(child)
            if value is not None:
                props[self._localname(child.tag)] = value
        return props

    def _extract_java_version(self, root: ET.Element) -> Optional[str]:
        """Java version via properties, then compiler-plugin config.

        Precedence: ``java.version`` -> ``maven.compiler.release`` ->
        ``maven.compiler.source`` -> compiler plugin ``<release>``/``<source>``.
        """
        props = self._properties(root)
        for key in ("java.version", "maven.compiler.release", "maven.compiler.source"):
            if key in props:
                return props[key]

        # Fall back to maven-compiler-plugin <configuration>.
        for plugin in self._iter_local(root, "plugin"):
            artifact = self._find(plugin, "artifactId")
            if self._text(artifact) != "maven-compiler-plugin":
                continue
            config = self._find(plugin, "configuration")
            if config is None:
                continue
            for tag in ("release", "source"):
                value = self._text(self._find(config, tag))
                if value:
                    return value
        return None

    def _extract_framework(self, root: ET.Element) -> Optional[str]:
        """Return ``"spring-boot"`` if any Spring Boot artifact is present."""
        for artifact_id in self._artifact_ids(root):
            if artifact_id.startswith("spring-boot"):
                return "spring-boot"
        return None

    def _extract_test_framework(self, root: ET.Element) -> Optional[str]:
        """Return ``"junit"`` if JUnit (directly or via Spring Boot) is present."""
        for artifact_id in self._artifact_ids(root):
            if "junit" in artifact_id or artifact_id == "spring-boot-starter-test":
                return "junit"
        return None

    def _extract_lint(self, root: ET.Element) -> Tuple[Optional[str], Optional[str]]:
        """Return checkstyle tool/command if the checkstyle plugin is present."""
        for artifact_id in self._artifact_ids(root):
            if artifact_id == "maven-checkstyle-plugin":
                return "checkstyle", "mvn checkstyle:check"
        return None, None
