"""Pipeline (CI/CD workflow) generation.

Turns a :class:`~src.domain.ProjectProfile` into a GitHub Actions workflow
YAML string.

Architecture::

    ProjectProfile -> PipelineBuilder -> GitHub Actions YAML

The builder is deliberately narrow. It does **not** access GitHub, read
repository files, detect languages, or parse manifests. It only selects a
language template, substitutes profile values, conditionally includes the
test/lint steps, and returns the finished YAML.

Template strategy
-----------------
Language templates live in :mod:`src.generator.templates` as ``.yml`` files.
To avoid pulling in a template engine (and to avoid corrupting GitHub Actions
expressions like ``${{ github.ref }}``), substitution uses explicit
double-percent placeholders that cannot collide with Actions syntax:

* ``%%WORKFLOW_NAME%%`` / ``%%VERSION%%`` -- plain value substitution.
* ``%%LINT_STEP%%`` / ``%%TEST_STEP%%`` -- whole-line block placeholders that
  are either replaced with a rendered step or removed entirely when the
  corresponding command is absent.
"""

from __future__ import annotations

from importlib import resources
from typing import Optional

from src.detector.language import Language
from src.domain import ProjectProfile

# Map each supported language to its template file and default runtime version
# (used only when the profile does not specify one).
_TEMPLATES: dict[Language, str] = {
    Language.PYTHON: "python.yml",
    Language.NODEJS: "nodejs.yml",
    Language.JAVA: "java.yml",
}

_DEFAULT_VERSIONS: dict[Language, str] = {
    Language.PYTHON: "3.12",
    Language.NODEJS: "20",
    Language.JAVA: "17",
}

_DEFAULT_WORKFLOW_NAME = "CI"


class UnsupportedLanguageError(ValueError):
    """Raised when a profile's language has no workflow template."""


class DockerNotAvailableError(ValueError):
    """Raised when Docker is requested but the repository has no Dockerfile."""


class DockerPushRequiresDockerError(ValueError):
    """Raised when a Docker push is requested without enabling Docker."""


class PipelineBuilder:
    """Builds a GitHub Actions workflow YAML string from a ProjectProfile."""

    def build(
        self,
        profile: ProjectProfile,
        include_docker: bool = False,
        push_docker: bool = False,
    ) -> str:
        """Render a GitHub Actions workflow for ``profile``.

        Args:
            profile: The project profile to generate a workflow for.
            include_docker: Whether the user requested a Docker build step.
                A Docker step is only emitted when this is ``True`` **and**
                the repository actually contains a Dockerfile
                (``profile.has_docker``).
            push_docker: Whether to also push the built image to GitHub
                Container Registry (GHCR). Requires ``include_docker=True``.
                Uses the workflow's automatic ``GITHUB_TOKEN`` for auth; no
                credentials are ever embedded.

        Returns:
            The workflow as a YAML string.

        Raises:
            UnsupportedLanguageError: If the profile's language is
                :attr:`Language.UNKNOWN` or otherwise unsupported.
            DockerNotAvailableError: If ``include_docker`` is ``True`` but the
                repository has no Dockerfile.
            DockerPushRequiresDockerError: If ``push_docker`` is ``True`` while
                ``include_docker`` is ``False``.
        """
        template_name = _TEMPLATES.get(profile.language)
        if template_name is None:
            raise UnsupportedLanguageError(
                f"No workflow template for language: {profile.language.value!r}"
            )

        # A push without Docker enabled is a contradictory request; reject it
        # rather than silently ignoring the user's stated intent.
        if push_docker and not include_docker:
            raise DockerPushRequiresDockerError(
                "push_docker=True requires include_docker=True."
            )

        # User requested Docker, but there is no Dockerfile to build from.
        if include_docker and not profile.has_docker:
            raise DockerNotAvailableError(
                "Docker was requested but no Dockerfile was found in the repository."
            )

        docker_enabled = include_docker and profile.has_docker
        push_enabled = docker_enabled and push_docker

        template = self._load_template(template_name)
        version = profile.version or _DEFAULT_VERSIONS[profile.language]

        rendered = template.replace("%%WORKFLOW_NAME%%", _DEFAULT_WORKFLOW_NAME)
        rendered = rendered.replace("%%VERSION%%", version)
        # Job-level permissions are only needed to push packages to GHCR.
        rendered = self._apply_permissions(rendered, push_enabled)
        rendered = self._apply_step(
            rendered, "%%LINT_STEP%%", "Lint", profile.lint_command
        )
        rendered = self._apply_step(
            rendered, "%%TEST_STEP%%", "Test", profile.test_command
        )
        rendered = self._apply_step(
            rendered, "%%BUILD_STEP%%", "Build", profile.build_command
        )
        # Docker step is opt-in: only when requested and a Dockerfile exists.
        rendered = self._apply_docker_step(rendered, docker_enabled, push_enabled)
        return rendered

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load_template(name: str) -> str:
        """Load a packaged template by filename."""
        return (
            resources.files("src.generator.templates")
            .joinpath(name)
            .read_text(encoding="utf-8")
        )

    @staticmethod
    def _apply_step(
        rendered: str,
        placeholder: str,
        step_name: str,
        command: Optional[str],
    ) -> str:
        """Replace a whole-line step placeholder, or remove the line.

        When ``command`` is provided, the placeholder line is replaced with a
        rendered GitHub Actions step (indented to match the surrounding
        ``steps:`` block). When ``command`` is ``None``/empty, the placeholder
        line is removed entirely so no empty step remains.
        """
        lines = rendered.splitlines()
        out: list[str] = []
        for line in lines:
            if line.strip() != placeholder:
                out.append(line)
                continue
            if command:
                out.append("")  # blank separator before the step
                out.append(f"      - name: {step_name}")
                out.append(f"        run: {command}")
            # If no command, drop the placeholder line entirely.
        text = "\n".join(out)
        if not text.endswith("\n"):
            text += "\n"
        return text

    @staticmethod
    def _apply_permissions(rendered: str, push_enabled: bool) -> str:
        """Fill ``%%PERMISSIONS%%`` with a job-level permissions block or drop it.

        The ``packages: write`` permission is only required to push images to
        GHCR, so the block is emitted only when a push is enabled.
        """
        placeholder = "%%PERMISSIONS%%"
        lines = rendered.splitlines()
        out: list[str] = []
        for line in lines:
            if line.strip() != placeholder:
                out.append(line)
                continue
            if push_enabled:
                out.append("    permissions:")
                out.append("      contents: read")
                out.append("      packages: write")
            # Otherwise drop the placeholder line entirely.
        text = "\n".join(out)
        if not text.endswith("\n"):
            text += "\n"
        return text

    @staticmethod
    def _apply_docker_step(
        rendered: str, docker_enabled: bool, push_enabled: bool
    ) -> str:
        """Replace ``%%DOCKER_STEP%%`` with Docker build (and optional push).

        * ``docker_enabled`` false -> the placeholder line is removed.
        * ``push_enabled`` false   -> a provider-neutral local ``docker build``
          step (no registry, no login, no push).
        * ``push_enabled`` true    -> the standard GHCR flow using
          ``docker/login-action`` + ``docker/build-push-action`` with
          ``push: true``. Authentication uses the workflow's automatic
          ``GITHUB_TOKEN``; no credentials are ever embedded. The image is
          tagged ``ghcr.io/${{ github.repository }}:${{ github.sha }}``.
        """
        placeholder = "%%DOCKER_STEP%%"
        lines = rendered.splitlines()
        out: list[str] = []
        for line in lines:
            if line.strip() != placeholder:
                out.append(line)
                continue
            if not docker_enabled:
                continue  # drop the placeholder line entirely
            if not push_enabled:
                # Build-only, provider-neutral local image.
                out.append("")
                out.append("      - name: Docker build")
                out.append(
                    "        run: docker build -t "
                    "${{ github.event.repository.name }}:${{ github.sha }} ."
                )
            else:
                # GHCR login + build/push using the automatic GITHUB_TOKEN.
                out.append("")
                out.append("      - name: Log in to GitHub Container Registry")
                out.append("        uses: docker/login-action@v3")
                out.append("        with:")
                out.append("          registry: ghcr.io")
                out.append("          username: ${{ github.actor }}")
                out.append("          password: ${{ secrets.GITHUB_TOKEN }}")
                out.append("")
                out.append("      - name: Docker build and push")
                out.append("        uses: docker/build-push-action@v6")
                out.append("        with:")
                out.append("          context: .")
                out.append("          push: true")
                out.append(
                    "          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}"
                )
        text = "\n".join(out)
        if not text.endswith("\n"):
            text += "\n"
        return text
