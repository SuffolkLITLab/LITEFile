"""Load and render versioned LITEFile prompts bundled with the application."""

import os
from functools import cache
from pathlib import Path
from string import Template
from typing import Any, Literal

import yaml

PromptMode = Literal["file", "text"]


def prompt_directory() -> Path:
    """Return the prompt catalog directory, allowing an explicit deployment override."""
    configured = os.getenv("LITEFILE_PROMPTS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "prompts"


@cache
def load_prompt(name: str) -> dict[str, Any]:
    """Load one prompt definition and perform basic structural validation."""
    path = prompt_directory() / f"{name}.yaml"
    with path.open(encoding="utf-8") as prompt_file:
        definition = yaml.safe_load(prompt_file)

    if not isinstance(definition, dict):
        raise ValueError(f"Prompt definition must be a mapping: {path}")
    versions = definition.get("versions")
    production_version = definition.get("production_version")
    if not isinstance(versions, dict) or production_version not in versions:
        raise ValueError(f"Prompt definition has no valid production version: {path}")
    return definition


def prompt_version(
    name: str, version: str | None = None
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return the selected version name, full definition, and version settings."""
    definition = load_prompt(name)
    selected = version or definition["production_version"]
    version_config = definition["versions"].get(selected)
    if not isinstance(version_config, dict):
        raise ValueError(f"Unknown {name} prompt version: {selected}")
    return selected, definition, version_config


def render_prompt_messages(
    name: str,
    *,
    mode: PromptMode,
    field_definitions: dict[str, str],
    jurisdiction_hint: str = "",
    document_text: str = "",
    version: str | None = None,
    template_values: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Render a prompt version into OpenAI-compatible system and user messages."""
    selected, _definition, version_config = prompt_version(name, version)
    templates = version_config.get("templates")
    if not isinstance(templates, dict):
        raise ValueError(f"Prompt {name}/{selected} has no templates")

    values = {
        "field_definitions": repr(field_definitions),
        "jurisdiction_hint": jurisdiction_hint or "",
        "document_text": document_text,
    }
    if template_values:
        values.update(
            {key: _template_value(value) for key, value in template_values.items()}
        )
    messages = []
    for role, template_name in (("system", f"{mode}_system"), ("user", f"{mode}_user")):
        template = templates.get(template_name)
        if not isinstance(template, str):
            raise ValueError(
                f"Prompt {name}/{selected} has no {template_name} template"
            )
        messages.append(
            {"role": role, "content": Template(template).substitute(values).strip()}
        )
    return messages, version_config


def _template_value(value: Any) -> str:
    """Render structured prompt inputs deterministically without losing their shape."""
    if isinstance(value, str):
        return value
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()


def shared_prompt_text(name: str, key: str) -> str:
    """Return a reusable instruction stored alongside a prompt definition."""
    shared = load_prompt(name).get("shared", {})
    value = shared.get(key) if isinstance(shared, dict) else None
    if not isinstance(value, str):
        raise ValueError(f"Prompt {name} has no shared text named {key}")
    return value
