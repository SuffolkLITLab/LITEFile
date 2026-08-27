"""Prepare a client-built filing payload before it is sent to the EFSP proxy.

The fee quote and the final submission post the *same* ``efile_data`` blob to
two different EFSP endpoints. Every server-side adjustment to that blob belongs
here so the two cannot drift: a fee quoted against one payload and a filing made
with another is a bug that only shows up as a wrong number on a real filing.
"""

import logging
import time

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# Labels the UI has historically stored in place of a real court filing-component
# code. None of these are meaningful to the EFSP.
_PLACEHOLDER_COMPONENT_LABELS = {"", "supporting", "attachment", "attachments"}

# Per-request ceiling for one code-list GET, and the ceiling for all of them in a
# single ``prepare_efile_payload`` call. The budget is what keeps a slow EFSP
# bounded: this runs on the fee quote and the submission alike, on a request
# thread, and a bundle with several filing types would otherwise stack one full
# timeout per lookup across three separate phases.
_EFSP_LOOKUP_TIMEOUT = 30
_EFSP_LOOKUP_BUDGET = 45


class PayloadValidationError(Exception):
    """The payload cannot succeed at the EFSP, with a reason worth showing a filer.

    Raised only for conditions the court's own code lists already prove wrong, so
    the message can be specific. Views turn this into a 400 carrying the message.
    """


class _EfspLookups:
    """Cached, time-budgeted GETs against the EFSP code lists for one payload.

    Every lookup through here fails open: it exists to make a payload or a
    message better, never to gatekeep, and the EFSP stays the authority. So a
    failure is reported as ``None`` -- *unknown* -- which callers must not
    confuse with an empty list, which is the court saying "nothing here".
    """

    def __init__(self, budget=_EFSP_LOOKUP_BUDGET):
        self._deadline = time.monotonic() + budget
        self._cache = {}

    def get(self, url):
        """Return the parsed JSON body, or None when it could not be fetched."""
        if url in self._cache:
            return self._cache[url]

        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            logger.warning("EFSP code-list time budget is spent; skipping %s", url)
            self._cache[url] = None
            return None

        payload = None
        try:
            response = requests.get(url, timeout=min(_EFSP_LOOKUP_TIMEOUT, remaining))
            if response.status_code == 200:
                payload = response.json()
            else:
                logger.warning("EFSP code list %s returned status %s", url, response.status_code)
        except (requests.RequestException, ValueError) as error:
            logger.warning("Could not fetch EFSP code list %s: %s", url, error)

        self._cache[url] = payload
        return payload


def _efsp_flag(value):
    """Read one of Tyler's booleans.

    The EFSP renders these as real JSON booleans in some courts and as the
    strings "true"/"false" in others, so every read goes through here.
    """
    return str(value).lower() == "true"


def parse_optional_services(services):
    """Normalize the EFSP's optional-services list into one shape.

    Shared with the dropdown API that feeds the service picker. The picker and
    this module have to agree about which services take a multiplier: if they
    drift, a filer selects a service and the payload silently drops -- or
    invents -- the multiplier the court demands for it.

    Services with no code are dropped; nothing downstream can select one.
    """
    if not isinstance(services, list):
        return []

    parsed = []
    for service in services:
        if not isinstance(service, dict):
            continue
        code = str(service.get("code") or service.get("id") or "").strip()
        if not code:
            continue
        parsed.append(
            {
                "code": code,
                "name": service.get("name") or service.get("label") or service.get("text"),
                "fee": service.get("fee") or service.get("cost") or 0,
                "description": service.get("description") or service.get("desc"),
                "required": service.get("required", False),
                "multiplier": _efsp_flag(service.get("multiplier")),
                "hasfeeprompt": _efsp_flag(service.get("hasfeeprompt")),
            }
        )
    return parsed


def prepare_efile_payload(efile_data, jurisdiction_id, court_id):
    """Apply every server-side fixup an EFSP request needs. Mutates ``efile_data``.

    Raises ``PayloadValidationError`` when the payload is knowably invalid.
    """
    lookups = _EfspLookups()
    _clean_case_identifiers(efile_data)
    _drop_empty_cross_references(efile_data)
    substitute_test_document_urls(efile_data)
    validate_document_selections(efile_data)
    resolve_placeholder_filing_components(efile_data, jurisdiction_id, court_id, lookups=lookups)
    normalize_optional_services(efile_data, jurisdiction_id, court_id, lookups=lookups)
    validate_required_party_types(efile_data, jurisdiction_id, court_id, lookups=lookups)
    return efile_data


def _clean_case_identifiers(efile_data):
    """Ensure docket_number is omitted for new cases where there is no previous_case_id."""
    if not efile_data.get("previous_case_id") or efile_data.get("user_started_case") is True:
        efile_data.pop("docket_number", None)


def _drop_empty_cross_references(efile_data):
    """Omit ``cross_references`` entirely rather than sending an empty value."""
    if not efile_data.get("cross_references"):
        efile_data.pop("cross_references", None)


def substitute_test_document_urls(efile_data):
    """Point the proxy at a stand-in PDF when ``EFSP_TEST_DOCUMENT_URL`` is set.

    The proxy downloads every ``data_url`` itself -- for a fee quote just as much
    as for a real filing -- and refuses any scheme other than http(s). A
    LocalStack URL is not reachable from outside Docker, so exercising fees
    locally would otherwise require public ingress to the dev machine.

    Documents are still uploaded to S3 for real and drafts still store their real
    keys and URLs; only the URL handed to the proxy is replaced.

    Three independent things have to hold for a substitution to happen, so that no
    single mistake can put a stand-in document in front of a real court:

    1. ``settings_dev`` refuses to load on a deployed host at all.
    2. The setting is defined in ``settings_dev`` alone -- staging and production
       never read the environment variable, so exporting it there does nothing.
    3. This function refuses to substitute when ``DEBUG`` is off, and raises
       rather than quietly falling back, because a production process holding a
       stand-in URL is a broken deploy and should not file anything.
    """
    test_url = getattr(settings, "EFSP_TEST_DOCUMENT_URL", "")
    if not test_url:
        return

    if not settings.DEBUG:
        # Fail closed and loud. Silently sending the real document would leave a
        # misconfigured deploy running and undiagnosed until it did something
        # worse; silently sending the stand-in would file a placeholder PDF as
        # though it were the filer's document.
        raise ImproperlyConfigured(
            "EFSP_TEST_DOCUMENT_URL is set while DEBUG is False. The stand-in filing "
            "document is a local-development affordance and must never reach a real "
            "court. Unset EFSP_TEST_DOCUMENT_URL in this environment."
        )

    substituted = 0
    for bundle in efile_data.get("al_court_bundle", []):
        if bundle.get("data_url") == test_url:
            continue
        bundle["data_url"] = test_url
        substituted += 1

    if substituted:
        logger.warning(
            "EFSP_TEST_DOCUMENT_URL is set: sent %d stand-in document(s) to the EFSP instead of the "
            "uploaded file(s). Fees and filings from this request do not reflect real documents.",
            substituted,
        )


def validate_document_selections(efile_data):
    """Reject a document that carries no filing type.

    The filing type is chosen per document on the upload screen, and a draft can
    reach the fee quote without one: an interrupted session, or an upload page
    running a stale script whose own check was missing. The blank travels as
    ``"filing_type": ""`` and the EFSP answers with a `wrong_vars` entry naming
    ``al_court_bundle.elements[0].filing_type`` and a bare list of code numbers.

    Only the filing type is checked. It is required for every court -- the code
    lists are keyed on it -- while document type and the rest vary by court, and
    this module refuses payloads only where the court's own rules already prove
    them wrong.
    """
    missing = [
        _document_label(bundle, index)
        for index, bundle in enumerate(efile_data.get("al_court_bundle", []))
        if not str(bundle.get("filing_type") or "").strip()
    ]
    if not missing:
        return

    raise PayloadValidationError(
        f"No filing type is set for: {', '.join(missing)}. Go back to the documents step "
        f"and choose a filing type for each document."
    )


def _document_label(bundle, index):
    """Name a bundle the way the filer would recognise it."""
    for key in ("filename", "filing_description", "document_description"):
        label = str(bundle.get(key) or "").strip()
        if label:
            return label
    return f"document {index + 1}"


def resolve_placeholder_filing_components(efile_data, jurisdiction_id, court_id, *, lookups=None):
    """Replace leftover UI labels such as ``"supporting"`` with the court's code.

    Newer uploads store the real code, so this only fires for drafts saved by an
    older client. Results are cached per filing type because a bundle commonly
    repeats the same one.
    """
    bundles = [
        bundle
        for bundle in efile_data.get("al_court_bundle", [])
        if str(bundle.get("filing_component", "")).lower() in _PLACEHOLDER_COMPONENT_LABELS
    ]
    if not bundles:
        return

    lookups = lookups or _EfspLookups()
    resolved_codes: dict[str, str | None] = {}
    for bundle in bundles:
        filing_type = bundle.get("filing_type")
        if not filing_type:
            continue
        if filing_type not in resolved_codes:
            resolved_codes[filing_type] = _lookup_lead_component(jurisdiction_id, court_id, filing_type, lookups)
        code = resolved_codes[filing_type]
        if code:
            bundle["filing_component"] = code


def validate_required_party_types(efile_data, jurisdiction_id, court_id, *, lookups=None):
    """Reject a payload that leaves one of the court's required party types empty.

    A case type declares which party types are mandatory -- a Cook County civil
    case needs both a Plaintiff and a Defendant. Nothing in the UI stops a filer
    from choosing the same type for themselves and for the other side, and the
    EFSP answers that with an opaque 400 ("All required parties not covered by
    existing party types. ([173174]. Missing [173180]") that reaches the filer as
    a generic failure with no way to act on it.

    Checked here rather than in the browser so the fee quote and the submission
    share one answer, and so it holds regardless of what the client sends.

    Fails open: if the court's party-type list cannot be fetched, the payload goes
    through and the EFSP stays the authority. This check exists to produce a
    better message, not to be a second gatekeeper.
    """
    case_type = efile_data.get("efile_case_type")
    if not case_type:
        return

    required = _lookup_required_party_types(jurisdiction_id, court_id, case_type, lookups or _EfspLookups())
    if not required:
        return

    present = {
        str(party.get("party_type"))
        for party in [*efile_data.get("users", []), *efile_data.get("other_parties", [])]
        if party.get("party_type")
    }
    missing = {code: name for code, name in required.items() if code not in present}
    if not missing:
        return

    missing_names = ", ".join(sorted(missing.values()))
    raise PayloadValidationError(
        f"This case type requires a party of every required type, and none was given for: "
        f"{missing_names}. Go back to the case details and give each side a different party type."
    )


def _lookup_required_party_types(jurisdiction_id, court_id, case_type, lookups):
    """Return ``{code: name}`` for the case type's required party types.

    Empty when the list cannot be fetched or the court marks nothing required, so
    callers treat "unknown" and "nothing required" alike -- both mean "do not
    block on this".
    """
    url = (
        f"{settings.EFSP_URL}/jurisdictions/{jurisdiction_id}/codes/courts/{court_id}/"
        f"case_types/{case_type}/party_types"
    )
    party_types = lookups.get(url)
    if not isinstance(party_types, list):
        return {}

    return {
        str(party_type.get("code")): party_type.get("name") or str(party_type.get("code"))
        for party_type in party_types
        if isinstance(party_type, dict) and _efsp_flag(party_type.get("isrequired"))
    }


def _lookup_lead_component(jurisdiction_id, court_id, filing_type, lookups):
    """Return the component a filing of this type must carry, or None.

    Every entry in ``al_court_bundle`` is one filing of one filing type, and a
    filing type declares one component as required -- its lead document. A
    bundle without it is refused ("Required filing component '332' not found"),
    so a bundle that never got a component gets that one rather than a guess.
    """
    url = (
        f"{settings.EFSP_URL}/jurisdictions/{jurisdiction_id}/codes/courts/{court_id}/"
        f"filing_types/{filing_type}/filing_components"
    )
    components = lookups.get(url)
    if not isinstance(components, list):
        return None

    components = [component for component in components if isinstance(component, dict)]
    for component in components:
        if _efsp_flag(component.get("required")):
            return component.get("code")
    for component in components:
        if str(component.get("efspcode", "")).upper() == "LEAD":
            return component.get("code")
    return None


def normalize_optional_services(efile_data, jurisdiction_id, court_id, *, lookups=None):
    """Ensure optional_services in each court bundle match what the EFSP expects.

    The EFSP expects each entry in ``optional_services`` to be an object
    ``{"code": str}``. If the service is defined with ``multiplier=True`` by the
    court, EFSP requires ``"multiplier": 1`` (or the provided positive integer)
    and rejects payloads without it (400 Malformed Interview: needs a multiplier).
    If ``multiplier=False``, EFSP rejects payloads that include a multiplier
    (422 Optional service does not support a fee multiplier).

    This normalizes string codes or dicts into the exact structure expected.

    When the court's metadata cannot be fetched the client's own answer stands:
    the picker that offered the service read the same list, so its multiplier is
    the best evidence left. Defaulting to "no multiplier" there would silently
    strip the field on exactly the services the court demands it for, and the
    filing would fail at the EFSP with the error this function exists to avoid.
    """
    lookups = lookups or _EfspLookups()
    cache: dict[str, dict[str, dict] | None] = {}
    for bundle in efile_data.get("al_court_bundle", []):
        raw_services = bundle.get("optional_services")
        if not raw_services:
            bundle["optional_services"] = []
            continue

        filing_type = str(bundle.get("filing_type") or "")
        if filing_type and filing_type not in cache:
            cache[filing_type] = _lookup_optional_services_meta(jurisdiction_id, court_id, filing_type, lookups)
        # None means "not known", which is not the same as "the court defines
        # none" -- only the latter justifies dropping a multiplier.
        meta_by_code = cache.get(filing_type)

        normalized = []
        for item in raw_services:
            if isinstance(item, dict):
                code = str(item.get("code") or item.get("id") or "").strip()
                multiplier = item.get("multiplier")
            else:
                code = str(item).strip()
                multiplier = None

            if not code:
                continue

            if meta_by_code is None:
                needs_multiplier = multiplier is not None
            else:
                service_meta = meta_by_code.get(code)
                needs_multiplier = bool(service_meta and service_meta["multiplier"])

            entry = {"code": code}
            if needs_multiplier:
                try:
                    mult_val = int(multiplier) if multiplier is not None else 1
                    if mult_val < 1:
                        mult_val = 1
                except (ValueError, TypeError):
                    mult_val = 1
                entry["multiplier"] = mult_val

            normalized.append(entry)

        bundle["optional_services"] = normalized


def _lookup_optional_services_meta(jurisdiction_id, court_id, filing_type, lookups):
    """Return ``{code: service}`` for a filing type, or None when unknown."""
    if not (jurisdiction_id and court_id and filing_type):
        return None
    url = (
        f"{settings.EFSP_URL}/jurisdictions/{jurisdiction_id}/codes/courts/{court_id}/"
        f"filing_types/{filing_type}/optional_services"
    )
    services = lookups.get(url)
    if not isinstance(services, list):
        return None
    return {service["code"]: service for service in parse_optional_services(services)}
