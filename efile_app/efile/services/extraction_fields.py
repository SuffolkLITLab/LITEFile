"""The complete, reviewable set of details requested from a lead document."""

from efile.utils.prompt_config import load_prompt

DOCUMENT_EXTRACTION_PROMPT = load_prompt("document_evidence_extraction")
COMMON_EXTRACTION_FIELDS: dict[str, str] = dict(DOCUMENT_EXTRACTION_PROMPT["fields"])

EXTRACTION_FIELDS: dict[str, dict[str, str]] = {
    jurisdiction: dict(COMMON_EXTRACTION_FIELDS) for jurisdiction in ("illinois", "massachusetts", "vermont", "default")
}

EXTRACTION_HINTS: dict[str, str] = {
    jurisdiction: "Extract source evidence without guessing an e-filing taxonomy value."
    for jurisdiction in ("illinois", "massachusetts", "vermont", "default")
}

EXTRACTION_LABELS = {
    "document title": "Document title",
    "form name": "Form name",
    "form identifier": "Form number or ID",
    "form revision": "Form revision",
    "form purpose": "What the form asks the court to do",
    "court": "Court or county",
    "filing type": "Filing type",
    "case category": "Case category",
    "case type": "Case type",
    "docket number": "Case number",
    "case title": "Case title",
    "plaintiff or petitioner names": "Plaintiff or petitioner names",
    "defendant or respondent names": "Defendant or respondent names",
    "other party names": "Other party names",
    "document date": "Document date",
    "filing phase": "Filing phase",
    "requested relief": "Requested relief",
    "monetary amounts": "Monetary amounts",
    "selected options": "Selected options",
    "docket code evidence": "Docket code evidence",
    "classification evidence": "Classification evidence",
}


def normalize_extracted_fields(found_fields):
    """Keep every extracted value while normalizing keys used by the workflow."""
    if not isinstance(found_fields, dict):
        return {}

    normalized = {}
    for raw_key, value in found_fields.items():
        if value in (None, "", [], {}):
            continue
        key = str(raw_key).strip().lower()
        if key in {"court name", "court unit", "court or county"}:
            key = "court"
        elif key in {"docker number", "case number"}:
            key = "docket number"
        if isinstance(value, dict):
            value = "; ".join(f"{item_key}: {item_value}" for item_key, item_value in value.items())
        elif isinstance(value, list | tuple | set):
            value = "; ".join(str(item) for item in value)
        elif not isinstance(value, str):
            value = str(value)
        normalized[key] = value.strip()
    return normalized


def normalize_document_evidence(found_fields):
    """Normalize evidence keys without destroying arrays and evidence objects."""
    if not isinstance(found_fields, dict):
        return {}
    normalized = {}
    for raw_key, value in found_fields.items():
        if value in (None, "", [], {}):
            continue
        key = str(raw_key).strip().lower()
        if key in {"court unit", "court or county"}:
            key = "court name"
        elif key in {"monetary amount", "amount in controversy"}:
            key = "monetary amounts"
        normalized[key] = value
    return normalized


def display_extracted_fields(found_fields):
    """Flatten structured evidence only at the user-interface boundary."""
    if not isinstance(found_fields, dict):
        return {}
    display = {}
    for raw_key, value in found_fields.items():
        if value in (None, "", [], {}):
            continue
        key = str(raw_key).strip().lower()
        if key in {"court name", "court unit", "court or county"}:
            key = "court"
        if isinstance(value, list):
            rendered = []
            for item in value:
                if isinstance(item, dict):
                    label = item.get("label")
                    raw = item.get("raw") or item.get("amount")
                    rendered.append(": ".join(str(part) for part in (label, raw) if part))
                else:
                    rendered.append(str(item))
            display[key] = "; ".join(part for part in rendered if part)
        elif isinstance(value, dict):
            display[key] = "; ".join(f"{item_key}: {item_value}" for item_key, item_value in value.items())
        else:
            display[key] = str(value).strip()
    return {key: value for key, value in display.items() if value}


def extracted_details(guesses):
    """Return every extracted item in a stable, user-facing order."""
    guesses = guesses or {}
    ordered_keys = [*EXTRACTION_LABELS, *(key for key in guesses if key not in EXTRACTION_LABELS)]
    return [
        {
            "key": key,
            "label": EXTRACTION_LABELS.get(key, key.replace("_", " ").capitalize()),
            "value": guesses[key],
        }
        for key in ordered_keys
        if guesses.get(key) not in (None, "", [], {})
    ]
