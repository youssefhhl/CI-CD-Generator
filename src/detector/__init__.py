"""Stack detection package.

Public API for detecting a project's primary language from repository
file paths. Later phases (parsers, YAML generation) build on top of this.
"""

from .language import Language
from .stack_detector import (
    DEFAULT_SIGNATURES,
    DetectionResult,
    StackDetector,
    StackSignature,
)

__all__ = [
    "Language",
    "StackDetector",
    "DetectionResult",
    "StackSignature",
    "DEFAULT_SIGNATURES",
]
