"""Repository reader layer.

Reads raw repository information (file paths + relevant config file contents)
from a public GitHub repository, for the detector/parser layers to interpret.
"""

from .github_reader import GitHubRepositoryReader
from .models import (
    InvalidRepositoryUrlError,
    RepositoryAccessError,
    RepositoryApiError,
    RepositoryNotFoundError,
    RepositoryReadError,
    RepositorySnapshot,
)

__all__ = [
    "GitHubRepositoryReader",
    "RepositorySnapshot",
    "RepositoryReadError",
    "InvalidRepositoryUrlError",
    "RepositoryNotFoundError",
    "RepositoryAccessError",
    "RepositoryApiError",
]
