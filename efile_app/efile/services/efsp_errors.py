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

Some rejections instead arrive as a single free-text sentence (a "Malformed
Interview" body, or a plain ``error`` string) written for a developer reading
the proxy's logs, not a filer. ``_KNOWN_MESSAGE_HINTS`` recognizes the ones
that come up in practice -- lifted from the literal strings the proxy raises,
in ~/EfileProxyServer (see e.g. ``Ecf4Filer.java`` and
``FilingInformationDocassembleJacksonDeserializer.java``) -- and appends a
sentence saying what to actually do about it. Unrecognized messages still pass
through unchanged rather than being hidden.
"""

import json
import re
from collections.abc import Callable

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
_OTHER_PARTY_ADDRESS_FIELD = re.compile(r"^other_parties\[(\d+)\]\.address\.(address|city|state|zip)$")

_MAX_RAW_BODY = 300

# (pattern, hint builder) pairs checked in order against a free-text EFSP
# message; the first match wins. Each hint tells the filer what to actually do,
# not just what went wrong. Patterns are deliberately specific substrings of
# the proxy's own wording so an unrelated message never matches by accident.
_KNOWN_MESSAGE_HINTS: list[tuple[re.Pattern, Callable[[re.Match], str]]] = [
    (
        re.compile(r"doesn't allow subsequent filing into non-indexed cases", re.IGNORECASE),
        lambda m: (
            "Go back to the case details step: choose New case and remove the case number, "
            "or choose Existing case and look up the case instead."
        ),
    ),
    (
        re.compile(r"needs docket number, but not present", re.IGNORECASE),
        lambda m: "Go back to the case details step and provide the court's case number for this existing case.",
    ),
    (
        re.compile(r"Document .*? is too big! Must be max (\d+)", re.IGNORECASE),
        lambda m: (
            f"One of your PDFs is over the court's {int(m.group(1)):,}-byte limit. "
            "Compress it or split it into smaller files, then re-upload."
        ),
    ),
    (
        re.compile(r"All Documents combined are too big! Must be max\s*(\d+)", re.IGNORECASE),
        lambda m: (
            f"Your documents add up to more than the court's {int(m.group(1)):,}-byte combined limit. "
            "Remove or compress some documents and try again."
        ),
    ),
    (
        re.compile(r"Need a filing type! FilingTypes are empty", re.IGNORECASE),
        lambda m: (
            "This court doesn't offer any filing types for that case category and case type "
            "together. Go back and double-check the case category, case type, and whether "
            "this is a new or existing case."
        ),
    ),
    (
        re.compile(r"Amount in controversy required", re.IGNORECASE),
        lambda m: (
            "This case type requires an amount in controversy, which this tool doesn't collect yet. "
            "Contact the court about filing this case another way."
        ),
    ),
]


def _actionable_hint(message: str) -> str | None:
    for pattern, build_hint in _KNOWN_MESSAGE_HINTS:
        match = pattern.search(message)
        if match:
            return build_hint(match)
    return None


def _with_hint(message: str) -> str:
    hint = _actionable_hint(message)
    return f"{message} {hint}" if hint else message


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
        return _with_hint(message)

    # "Malformed Interview" errors (e.g. a docket number on a case the court has
    # no record of) arrive as {"type": ..., "description": ...} instead.
    description = body.get("description")
    if description:
        error_type = str(body.get("type") or "").strip()
        message = f"{error_type}: {description}" if error_type else str(description)
        return _with_hint(message)

    return f"the court's filing service returned status {response.status_code}"


def _var_list(body, key):
    value = body.get(key)
    return [var for var in value if isinstance(var, dict)] if isinstance(value, list) else []


def _describe_var(var, *, missing: bool) -> str:
    name = str(var.get("name") or "").strip()
    if not name:
        return ""
    current = str(var.get("currentVal") or "").strip()

    match = _BUNDLE_FIELD.match(name)
    if match:
        index, name = match.groups()
        where = f" on document {int(index) + 1}"
    else:
        where = ""

    address_match = _OTHER_PARTY_ADDRESS_FIELD.match(name)
    if address_match:
        index, field = address_match.groups()
        field_label = {"address": "street address", "zip": "ZIP code"}.get(field, field)
        if current:
            return f"{current!r} is not a {field_label} the court accepts for other party {int(index) + 1}"
        return f"{field_label} is required for other party {int(index) + 1}'s mailing address"

    label = _FIELD_LABELS.get(name, name.replace("_", " "))
    if missing or not current:
        return f"no {label} was given{where}"
    return f"{current!r} is not a {label} this court accepts{where}"
