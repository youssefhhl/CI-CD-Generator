"""Read a public GitHub repository into a :class:`RepositorySnapshot`.

The reader uses the GitHub REST API (v3) over the standard library only
(:mod:`urllib.request` + :mod:`json`) so no HTTP dependency is required.

Responsibilities (intentionally narrow):

* Validate the repository URL.
* Retrieve the recursive git tree and extract file paths.
* Fetch the contents of a small, fixed set of *relevant* config files.

It does **not** detect languages, parse manifests, or build profiles. It
returns raw data for the detector/parser layers to interpret.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from .models import (
    InvalidRepositoryUrlError,
    RepositoryAccessError,
    RepositoryApiError,
    RepositoryNotFoundError,
    RepositorySnapshot,
)

# Basenames of the configuration files we fetch contents for. These mirror the
# inputs the current parsers accept; the reader itself does not interpret them.
_RELEVANT_CONFIG_FILES: frozenset[str] = frozenset(
    {"pom.xml", "requirements.txt", "pyproject.toml", "package.json"}
)

_API_ROOT = "https://api.github.com"
# Accept the current GitHub REST media type and identify ourselves; GitHub
# requires a User-Agent header or it rejects the request.
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "ci-cd-generator-repository-reader",
    "X-GitHub-Api-Version": "2022-11-28",
}


class GitHubRepositoryReader:
    """Reads a public GitHub repository via the REST API."""

    def __init__(self, timeout: float = 15.0) -> None:
        """Create a reader.

        Args:
            timeout: Per-request network timeout in seconds.
        """
        self._timeout = timeout

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def read(self, repo_url: str) -> RepositorySnapshot:
        """Read a public repository into a :class:`RepositorySnapshot`.

        Args:
            repo_url: A GitHub repo URL, e.g. ``https://github.com/owner/repo``.

        Returns:
            A :class:`RepositorySnapshot` with all file paths and the contents
            of the relevant configuration files.

        Raises:
            InvalidRepositoryUrlError: If the URL is malformed/unsupported.
            RepositoryNotFoundError: If the repository does not exist.
            RepositoryAccessError: If the repository is private/inaccessible.
            RepositoryApiError: On network errors or unexpected responses.
        """
        owner, repo = self._parse_repo_url(repo_url)

        default_branch = self._get_default_branch(owner, repo)
        file_paths = self._get_file_paths(owner, repo, default_branch)
        file_contents = self._get_relevant_contents(owner, repo, file_paths)

        return RepositorySnapshot(file_paths=file_paths, file_contents=file_contents)

    # ------------------------------------------------------------------ #
    # URL parsing / validation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_repo_url(repo_url: str) -> Tuple[str, str]:
        """Extract ``(owner, repo)`` from a GitHub URL.

        Accepts forms like ``https://github.com/owner/repo``,
        ``http://github.com/owner/repo/``, ``github.com/owner/repo``, and a
        trailing ``.git`` suffix. Rejects anything else.
        """
        if not repo_url or not isinstance(repo_url, str):
            raise InvalidRepositoryUrlError("Repository URL must be a non-empty string.")

        url = repo_url.strip()
        # Normalize: drop scheme and an optional leading www., then require the
        # github.com host followed by owner/repo.
        match = re.match(
            r"^(?:https?://)?(?:www\.)?github\.com/"
            r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$",
            url,
        )
        if not match:
            raise InvalidRepositoryUrlError(
                f"Not a valid GitHub repository URL: {repo_url!r}. "
                "Expected 'https://github.com/owner/repository'."
            )
        return match.group("owner"), match.group("repo")

    # ------------------------------------------------------------------ #
    # GitHub API calls
    # ------------------------------------------------------------------ #

    def _get_default_branch(self, owner: str, repo: str) -> str:
        """Return the repo's default branch (also validates existence/access)."""
        data = self._api_get_json(f"/repos/{owner}/{repo}")
        branch = data.get("default_branch")
        if not isinstance(branch, str) or not branch:
            raise RepositoryApiError(
                "Unexpected GitHub response: missing 'default_branch'."
            )
        return branch

    def _get_file_paths(self, owner: str, repo: str, branch: str) -> List[str]:
        """Return all blob (file) paths from the recursive git tree."""
        data = self._api_get_json(
            f"/repos/{owner}/{repo}/git/trees/{branch}", query="recursive=1"
        )
        tree = data.get("tree")
        if not isinstance(tree, list):
            raise RepositoryApiError("Unexpected GitHub response: missing 'tree'.")

        paths: List[str] = []
        for entry in tree:
            if not isinstance(entry, dict):
                continue
            # Only blobs are files; skip 'tree' (directories) and anything else.
            if entry.get("type") != "blob":
                continue
            path = entry.get("path")
            if isinstance(path, str) and path:
                paths.append(path)
        return paths

    def _get_relevant_contents(
        self, owner: str, repo: str, file_paths: List[str]
    ) -> Dict[str, str]:
        """Fetch text contents for the relevant config files among ``file_paths``."""
        contents: Dict[str, str] = {}
        for path in file_paths:
            basename = path.rsplit("/", 1)[-1]
            if basename not in _RELEVANT_CONFIG_FILES:
                continue
            text = self._get_file_text(owner, repo, path)
            if text is not None:
                contents[path] = text
        return contents

    def _get_file_text(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Fetch and base64-decode a single file's text content."""
        # Percent-encode path segments but preserve '/'.
        encoded = urllib.parse.quote(path)
        data = self._api_get_json(f"/repos/{owner}/{repo}/contents/{encoded}")
        if data.get("encoding") != "base64" or "content" not in data:
            # e.g. a submodule/symlink or oversized file; skip rather than fail.
            return None
        try:
            raw = base64.b64decode(data["content"])
            return raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

    # ------------------------------------------------------------------ #
    # HTTP helper
    # ------------------------------------------------------------------ #

    def _api_get_json(self, path: str, query: str = "") -> dict:
        """GET a GitHub API endpoint and parse the JSON body.

        Translates HTTP/network failures into the reader's error hierarchy.
        """
        url = f"{_API_ROOT}{path}"
        if query:
            url = f"{url}?{query}"

        request = urllib.request.Request(url, headers=_HEADERS, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            self._raise_for_http_error(exc)
        except urllib.error.URLError as exc:
            raise RepositoryApiError(f"Network error contacting GitHub: {exc.reason}")

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RepositoryApiError(f"Invalid JSON from GitHub API: {exc}")
        if not isinstance(parsed, dict):
            raise RepositoryApiError("Unexpected GitHub API response shape.")
        return parsed

    @staticmethod
    def _raise_for_http_error(exc: urllib.error.HTTPError) -> None:
        """Map an HTTP error status to the reader's error hierarchy."""
        status = exc.code
        if status == 404:
            raise RepositoryNotFoundError("Repository not found (HTTP 404).")
        if status in (401, 403):
            raise RepositoryAccessError(
                f"Repository is inaccessible or the request was refused (HTTP {status}). "
                "It may be private or the API rate limit was exceeded."
            )
        raise RepositoryApiError(f"Unexpected GitHub API status: HTTP {status}.")
