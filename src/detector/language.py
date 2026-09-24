"""Language definitions for stack detection."""

from enum import Enum


class Language(str, Enum):
    """Supported project languages plus an explicit unknown case.

    Inherits from ``str`` so values serialize cleanly (e.g. to JSON/API
    responses later) while remaining comparable to plain strings.
    """

    PYTHON = "python"
    NODEJS = "nodejs"
    JAVA = "java"
    UNKNOWN = "unknown"

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value
