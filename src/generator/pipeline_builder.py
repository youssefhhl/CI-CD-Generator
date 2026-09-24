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


class PipelineBuilder:
    """Builds a GitHub Actions workflow YAML string from a ProjectProfile."""

    def build(self, profile: ProjectProfile) -> str:
        """Render a GitHub Actions workflow for ``profile``.

        Args:
            profile: The project profile to generate a workflow for.

        Returns:
            The workflow as a YAML string.

        Raises:
            UnsupportedLanguageError: If the profile's language is
                :attr:`Language.UNKNOWN` or otherwise unsupported.
        """
        template_name = _TEMPLATES.get(profile.language)
        if template_name is None:
            raise UnsupportedLanguageError(
                f"No workflow template for language: {profile.language.value!r}"
            )

        template = self._load_template(template_name)
        version = profile.version or _DEFAULT_VERSIONS[profile.language]

        rendered = template.replace("%%WORKFLOW_NAME%%", _DEFAULT_WORKFLOW_NAME)
        rendered = rendered.replace("%%VERSION%%", version)
        rendered = self._apply_step(
            rendered, "%%LINT_STEP%%", "Lint", profile.lint_command
        )
        rendered = self._apply_step(
            rendered, "%%TEST_STEP%%", "Test", profile.test_command
        )
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
