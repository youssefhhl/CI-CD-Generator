"""Internal models for the repository reader layer.

These are raw, provider-agnostic representations of what was read from a
repository. They deliberately contain **no** detection or parsing results:
turning this data into a :class:`~src.domain.ProjectProfile` is the job of the
detector and parser layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RepositorySnapshot:
    """Raw snapshot of a repository's structure and relevant config files.

    Args:
        file_paths: All repository-relative file paths (blobs only; no
            directories).
        file_contents: Mapping of repository-relative path -> raw text, for
            the configuration files the reader chose to fetch. Paths use the
            same relative form as in :attr:`file_paths`.
    """

    file_paths: List[str] = field(default_factory=list)
    file_contents: Dict[str, str] = field(default_factory=dict)


class RepositoryReadError(Exception):
    """Base class for all repository reader failures."""


class InvalidRepositoryUrlError(RepositoryReadError):
    """The provided repository URL was malformed or unsupported."""


class RepositoryNotFoundError(RepositoryReadError):
    """The repository does not exist (HTTP 404)."""


class RepositoryAccessError(RepositoryReadError):
    """The repository is inaccessible/private or the API refused the request.

    Covers HTTP 403 (including rate limiting) and 401.
    """


class RepositoryApiError(RepositoryReadError):
    """A network error or an unexpected GitHub API response occurred."""
