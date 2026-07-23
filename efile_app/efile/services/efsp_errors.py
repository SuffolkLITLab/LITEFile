"""Turn an EFSP error response into one line worth showing a filer.

The proxy answers a bad payload with a machine-readable description of which
fields are wrong rather than with an ``error`` string::

    {"required_vars": [],
     "optional_vars": [...],
     "wrong_vars": [{"name": "al_court_bundle.elements[0].filing_type",
                     "description": "What filing type is this??",
                     "datatype": "choice", "currentVal": "", "choices": [...]}]}

Reading only ``error`` out of that leaves the filer with "API returned status
400" and no way to act, while the response says exactly which document is
missing exactly which field. Shared by the fee quote and the submission so both
describe the same rejection the same way.
"""

import json
import re

# Field names the EFSP uses, in the words the UI uses for them.
_FIELD_LABELS = {
    "document_type": "document type",
    "efile_case_category": "case category",
    "efile_case_subtype": "case subtype",
    "efile_case_type": "case type",
    "filing_component": "filing component",
    "filing_parties": "filing parties",
    "filing_type": "filing type",
    "party_type": "party type",
    "previous_case_id": "case number",
    "tyler_payment_id": "payment account",
}

# "al_court_bundle.elements[0].filing_type" -> document 1, field filing_type
_BUNDLE_FIELD = re.compile(r"^al_court_bundle\.elements\[(\d+)\]\.(.+)$")

_MAX_RAW_BODY = 300


def describe_efsp_error(response) -> str:
    """Describe why the EFSP refused ``response``'s request.

    Never raises: a bad message is still better than a traceback on a path whose
    only job is reporting someone else's failure.
    """
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        text = (response.text or "").strip()
        if text:
            return f"the court's filing service returned status {response.status_code}: {text[:_MAX_RAW_BODY]}"
        return f"the court's filing service returned status {response.status_code}"

    if not isinstance(body, dict):
        return f"the court's filing service returned status {response.status_code}: {str(body)[:_MAX_RAW_BODY]}"

    problems = [
        *(_describe_var(var, missing=False) for var in _var_list(body, "wrong_vars")),
        *(_describe_var(var, missing=True) for var in _var_list(body, "required_vars")),
    ]
    problems = [problem for problem in problems if problem]
    if problems:
        return "the court could not accept this filing: " + "; ".join(problems)

    # Some errors do arrive as a plain message.
    error = body.get("error") or body.get("message") or body.get("detail")
    if error:
        message = str(error)
        validation_errors = body.get("validation_errors") or body.get("errors")
        if validation_errors:
            message += f" - Validation errors: {validation_errors}"
        return message

    return f"the court's filing service returned status {response.status_code}"


def _var_list(body, key):
    value = body.get(key)
    return [var for var in value if isinstance(var, dict)] if isinstance(value, list) else []


def _describe_var(var, *, missing: bool) -> str:
    name = str(var.get("name") or "").strip()
    if not name:
        return ""

    match = _BUNDLE_FIELD.match(name)
    if match:
        index, name = match.groups()
        where = f" on document {int(index) + 1}"
    else:
        where = ""

    label = _FIELD_LABELS.get(name, name.replace("_", " "))
    current = str(var.get("currentVal") or "").strip()

    if missing or not current:
        return f"no {label} was given{where}"
    return f"{current!r} is not a {label} this court accepts{where}"
