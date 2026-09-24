"""Stack detection from repository file paths.

The detector inspects a list of repository file paths and infers the
project's primary language from well-known marker files.

Design notes
------------
Detection is driven by a registry of :class:`StackSignature` objects. Each
signature maps a language to the set of marker filenames that identify it.
This keeps the detector simple today while leaving a clear extension point:
later, language-specific parsers can build on the same signature registry
without changing the detection flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable, List, Sequence

from .language import Language


@dataclass(frozen=True)
class StackSignature:
    """Associates a language with the marker filenames that identify it.

    Args:
        language: The language this signature detects.
        markers: Marker filenames (basename only, e.g. ``package.json``)
            that indicate the language is present.
    """

    language: Language
    markers: frozenset[str]

    def matches(self, filenames: Iterable[str]) -> bool:
        """Return ``True`` if any marker filename is present."""
        names = set(filenames)
        return bool(self.markers & names)


# Ordered registry of known stack signatures. Order defines precedence when
# multiple stacks could match; the first match wins.
DEFAULT_SIGNATURES: tuple[StackSignature, ...] = (
    StackSignature(Language.PYTHON, frozenset({"requirements.txt", "pyproject.toml"})),
    StackSignature(Language.NODEJS, frozenset({"package.json"})),
    StackSignature(Language.JAVA, frozenset({"pom.xml", "build.gradle"})),
)


@dataclass
class DetectionResult:
    """The outcome of a stack detection run.

    Args:
        language: The detected language, or :attr:`Language.UNKNOWN`.
        matched_markers: The marker filenames that triggered the match.
    """

    language: Language
    matched_markers: List[str] = field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        """Whether a supported stack was detected."""
        return self.language is not Language.UNKNOWN


class StackDetector:
    """Detects a project's primary language from repository file paths."""

    def __init__(self, signatures: Sequence[StackSignature] | None = None) -> None:
        """Create a detector.

        Args:
            signatures: Optional custom signature registry. Defaults to
                :data:`DEFAULT_SIGNATURES`. Order defines match precedence.
        """
        self._signatures: tuple[StackSignature, ...] = tuple(
            signatures if signatures is not None else DEFAULT_SIGNATURES
        )

    def detect(self, file_paths: Iterable[str]) -> DetectionResult:
        """Detect the language for the given repository file paths.

        Args:
            file_paths: Repository file paths. May be relative or nested
                (e.g. ``src/app/package.json``); only basenames are matched.

        Returns:
            A :class:`DetectionResult`. If no supported stack is found, the
            result's language is :attr:`Language.UNKNOWN`.
        """
        filenames = self._to_filenames(file_paths)

        for signature in self._signatures:
            matched = sorted(signature.markers & filenames)
            if matched:
                return DetectionResult(language=signature.language, matched_markers=matched)

        return DetectionResult(language=Language.UNKNOWN)

    @staticmethod
    def _to_filenames(file_paths: Iterable[str]) -> set[str]:
        """Reduce arbitrary file paths to their basenames, ignoring blanks."""
        filenames: set[str] = set()
        for path in file_paths:
            if not path:
                continue
            name = PurePosixPath(str(path).strip()).name
            if name:
                filenames.add(name)
        return filenames
