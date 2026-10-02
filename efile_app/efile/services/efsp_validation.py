"""Court code lists and text constraints shared by forms and outgoing filings.

The datafield endpoint returns Java regexes. Only portable expressions are
evaluated locally; the EFSP remains the authority for unsupported expressions.
Match by search, as the proxy's DataFieldRow.matchRegex uses Matcher.find().
"""

import logging
import re
import time
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.cache import cache

from efile.services.postal_codes import USPS_STATES

logger = logging.getLogger(__name__)
FIELD_CODES = {
    "first_name": "PartyFirstName",
    "middle_name": "PartyMiddleName",
    "last_name": "PartyLastName",
    "organization_name": "PartyBusinessName",
    "email": "PartyEmail",
    "phone": "PartyPhone",
}
FIELD_LABELS = {
    "first_name": "First name",
    "middle_name": "Middle name",
    "last_name": "Last name",
    "organization_name": "Organization name",
    "email": "Email",
    "phone": "Phone",
    "state": "State",
    "zip_code": "ZIP code",
}
_LENGTH = re.compile(r"\^\.\{(\d+),(\d+)\}\$")


class RuleLookups:
    """Bound lookup latency for a page, with fresh and last-known-good caches."""

    def __init__(self):
        self.deadline = time.monotonic() + 6

    def get(self, jurisdiction, court, suffix, expected):
        if not jurisdiction or not court:
            return None
        url = (
            f"{settings.EFSP_URL.rstrip('/')}/jurisdictions/{quote(jurisdiction, safe='')}"
            f"/codes/courts/{quote(court, safe='')}/{suffix}"
        )
        key = f"efsp-rule:{url}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        if cache.get(f"{key}:unavailable"):
            return cache.get(f"{key}:last-good")
        remaining = self.deadline - time.monotonic()
        if remaining > 0:
            try:
                response = requests.get(url, timeout=min(2, remaining))  # nosec B113
                if response.status_code == 200:
                    value = response.json()
                    valid = isinstance(value, expected)
                    if expected is list and valid:
                        valid = all(isinstance(code, str) and code.strip() for code in value)
                    if expected is dict and valid:
                        valid = value.get("code") in {"", suffix.rsplit("/", 1)[-1]}
                    if valid:
                        cache.set(key, value, 3600)
                        cache.set(f"{key}:last-good", value, 7 * 86400)
                        return value
            except (requests.RequestException, ValueError):
                logger.debug("Could not load EFSP validation metadata for %s", suffix)
        # Short negative cache prevents one unavailable service causing a series
        # of slow page loads. Empty lists are real results, not outages.
        cached = cache.get(f"{key}:last-good")
        if cached is not None:
            cache.set(key, cached, 60)
        else:
            cache.set(f"{key}:unavailable", True, 60)
        return cached


def state_choices(jurisdiction, court, country="US", *, lookups=None):
    lookups = lookups or RuleLookups()
    codes = lookups.get(jurisdiction, court, f"countries/{quote(country, safe='')}/states", list)
    if isinstance(codes, list) and all(isinstance(code, str) and code.strip() for code in codes):
        labels = USPS_STATES if country == "US" else {}
        return sorted({(code, labels.get(code, code)) for code in codes}, key=lambda item: item[1]), "efsp"
    # USPS codes are only meaningful for US addresses. Keep foreign data intact
    # rather than suggesting US states as foreign provinces.
    return list(USPS_STATES.items()) if country == "US" else [], "usps" if country == "US" else "unavailable"


def portable_regex(pattern):
    """Return a shared Python/JS expression, or None for Java-only constructs."""
    if not isinstance(pattern, str) or not pattern or len(pattern) > 1000:
        return None
    # Java flags, atomic groups, class intersections, possessive quantifiers,
    # Unicode categories, quoting and Java anchor/escape semantics differ.
    if re.search(r"(?<!\\)\(\?(?!:)|&&|[+*?}]\+|\\(?![dswDW.()\[\]{}+*?^$|\\/\-])", pattern):
        return None
    # Replacing whitespace inside a character class would change its meaning.
    # Nested Java character classes (unions) also differ from Python/JS.
    if re.search(r"\[(?:[^\]\\]|\\.)*(?:\\s|\[)", pattern):
        return None
    if not pattern.isascii():
        return None
    try:
        re.compile(pattern, re.ASCII)
    except re.error:
        return None
    # Preserve Java's ASCII whitespace and line-terminator semantics in both
    # Python and JavaScript. Escaped dots and dots inside classes stay literal.
    result = []
    in_class = False
    escaped = False
    for character in pattern:
        if escaped:
            result.append(r"[ \t\n\x0B\f\r]" if character == "s" else "\\" + character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "[":
            in_class = True
            result.append(character)
        elif character == "]":
            in_class = False
            result.append(character)
        elif character == "." and not in_class:
            result.append(r"[^\n\r\u0085\u2028\u2029]")
        else:
            result.append(character)
    return "".join(result)


def text_rules(jurisdiction, court, *, lookups=None):
    lookups = lookups or RuleLookups()
    rules = {}
    for field, code in FIELD_CODES.items():
        row = lookups.get(jurisdiction, court, f"datafields/{code}", dict)
        if not isinstance(row, dict) or row.get("code") != code:
            continue
        # Name regexes are used by the proxy even if isvisible is false.
        if field in {"phone", "email"} and str(row.get("isvisible")).lower() != "true":
            continue
        raw = row.get("regularexpression")
        pattern = portable_regex(raw)
        limit = _LENGTH.fullmatch(raw) if isinstance(raw, str) else None
        max_length = int(limit[2]) if limit else None
        label = FIELD_LABELS[field]
        message = (
            f"{label} must be {max_length} characters or fewer."
            if max_length is not None
            else (row.get("validationmessage") or f"Enter a {label.lower()} in the format the court accepts.")
        )
        rules[field] = {
            "regex": pattern,
            "max_length": max_length,
            "message": message,
            "help": row.get("helptext") or row.get("ghosttext") or "",
            "required": str(row.get("isrequired")).lower() == "true",
        }
    return rules


def party_validation(jurisdiction, court, country="US"):
    lookups = RuleLookups()
    choices, source = state_choices(jurisdiction, court, country, lookups=lookups)
    return {
        "state_choices": choices,
        "state_source": source,
        "validation_rules": text_rules(jurisdiction, court, lookups=lookups),
    }


def normalized_phone(value):
    """Mirror TylerCodesParser.vetPhoneNumbers' second attempt."""
    value = value.replace("-", "").replace("(", "").replace(")", "").strip()
    if "+" in value:
        if value.startswith(("+1", "+0")):
            value = value.replace("+1", "+1 ").replace("+0", "+0 ")
        return value
    return value.replace(" ", "")


def validate_party(values, metadata, *, organization=False, address_started=False):
    errors = {}
    rules = metadata.get("validation_rules", {})
    for field, rule in rules.items():
        if (field == "organization_name") != organization and field in {
            "first_name",
            "middle_name",
            "last_name",
            "organization_name",
        }:
            continue
        value = str(values.get(field) or "")
        if not value:
            if rule.get("required"):
                errors[field] = f"{FIELD_LABELS[field]} is required by the court."
                continue
            if field in {"email", "phone"}:
                continue
        pattern = rule.get("regex")
        if pattern and not re.search(pattern, value, re.ASCII):
            if field == "phone" and re.search(pattern, normalized_phone(value), re.ASCII):
                continue
            errors[field] = rule["message"]
    state = str(values.get("state") or "")
    if address_started and metadata.get("state_source") != "unavailable":
        allowed = {code for code, _label in metadata["state_choices"]}
        if state not in allowed:
            errors["state"] = (
                f"The filing service does not accept {state!r} for this address. "
                "If your location is not listed, contact the court for filing instructions. "
                "Do not choose a different state."
            )
            if not state or metadata.get("state_source") == "usps":
                errors["state"] = "Select a state or location from the list."
    return errors
