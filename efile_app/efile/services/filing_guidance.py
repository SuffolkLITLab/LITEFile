"""Informational, jurisdiction-maintained help matched to saved filing choices."""

import logging
from urllib.parse import urlsplit

from django.utils.translation import pgettext

from efile.utils.config_loader import config_loader

logger = logging.getLogger(__name__)

# Exact provider codes, not names inferred from a document or a court caption.
DRAFT_CONDITIONS = {
    "court_codes": "court_code",
    "case_category_codes": "case_category_code",
    "case_type_codes": "case_type_code",
    "case_subtype_codes": "case_subtype_code",
    "existing_case": "existing_case",
}
CONDITION_KEYS = {*DRAFT_CONDITIONS, "filing_type_codes"}
RULE_KEYS = {"id", "steps", "title", "text", "when", "resources"}


def _strings(value):
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _resource_is_valid(resource):
    if not isinstance(resource, dict) or set(resource) != {"label", "url"}:
        return False
    if not all(isinstance(resource[key], str) and resource[key].strip() for key in ("label", "url")):
        return False
    try:
        url = urlsplit(resource["url"])
        return url.scheme == "https" and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


def guidance_errors(config):
    """Validate authoring errors without treating guidance as a filing requirement."""
    from efile.workflow import FILING_WORKFLOW

    rules = config.get("filing_guidance", [])
    if not isinstance(rules, list):
        return ["filing_guidance must be a list."]
    steps = {step.key for step in FILING_WORKFLOW}
    errors = []
    identifiers = set()
    for index, rule in enumerate(rules):
        prefix = f"filing_guidance[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be a mapping.")
            continue
        if set(rule) - RULE_KEYS:
            errors.append(
                f"{prefix} contains unknown keys: {', '.join(sorted(str(key) for key in set(rule) - RULE_KEYS))}."
            )
        for key in ("id", "title", "text"):
            if not isinstance(rule.get(key), str) or not rule[key].strip():
                errors.append(f"{prefix}.{key} must be nonempty text.")
        identifier = rule.get("id")
        if isinstance(identifier, str):
            if identifier in identifiers:
                errors.append(f"{prefix}.id duplicates {identifier}.")
            identifiers.add(identifier)
        if not _strings(rule.get("steps")) or not set(rule["steps"]).issubset(steps):
            errors.append(f"{prefix}.steps must list active workflow step keys.")
        conditions = rule.get("when", {})
        if not isinstance(conditions, dict):
            errors.append(f"{prefix}.when must be a mapping.")
        else:
            for key, values in conditions.items():
                if key not in CONDITION_KEYS or not _strings(values):
                    errors.append(f"{prefix}.when.{key} must be a supported condition with a nonempty list of strings.")
                elif key == "existing_case" and not set(values).issubset({"new", "existing"}):
                    errors.append(f"{prefix}.when.existing_case accepts only new and existing.")
        resources = rule.get("resources", [])
        if not isinstance(resources, list) or not all(_resource_is_valid(resource) for resource in resources):
            errors.append(f"{prefix}.resources must contain label and absolute HTTPS url pairs.")
    return errors


def guidance_strings(config):
    """Strings shared by runtime translation and the config extraction command."""
    for rule in config.get("filing_guidance", []):
        prefix = f"filing_guidance.{rule['id']}"
        for field in ("title", "text"):
            yield f"{prefix}.{field}", rule[field]
        for index, resource in enumerate(rule.get("resources", [])):
            yield f"{prefix}.resources.{index}.label", resource["label"]


def filing_guidance(draft, step, *, jurisdiction=None):
    if draft is None:
        return []
    jurisdiction = jurisdiction or draft.jurisdiction
    config = config_loader.load_jurisdiction_config(jurisdiction)
    errors = guidance_errors(config)
    if errors:
        # Invalid informational copy must not prevent a filer from proceeding.
        # The system check reports it to maintainers before deployment.
        logger.warning("Invalid filing guidance for %s: %s", jurisdiction, "; ".join(errors))
        return []
    matches = []
    document_codes = None
    for rule in config.get("filing_guidance", []):
        if step not in rule["steps"]:
            continue
        conditions = rule.get("when", {})
        if any(
            getattr(draft, field, "") not in conditions[key]
            for key, field in DRAFT_CONDITIONS.items()
            if key in conditions
        ):
            continue
        if "filing_type_codes" in conditions:
            if document_codes is None:
                document_codes = set(draft.documents.values_list("filing_type_code", flat=True)) - {""}
            if not document_codes.intersection(conditions["filing_type_codes"]):
                continue
        prefix = f"filing_guidance.{rule['id']}"
        matches.append(
            {
                "title": pgettext(f"{prefix}.title", rule["title"]),
                "text": pgettext(f"{prefix}.text", rule["text"]),
                "resources": [
                    {"label": pgettext(f"{prefix}.resources.{index}.label", resource["label"]), "url": resource["url"]}
                    for index, resource in enumerate(rule.get("resources", []))
                ],
            }
        )
    return matches
