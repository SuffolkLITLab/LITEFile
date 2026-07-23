"""Prepare a client-built filing payload before it is sent to the EFSP proxy.

The fee quote and the final submission post the *same* ``efile_data`` blob to
two different EFSP endpoints. Every server-side adjustment to that blob belongs
here so the two cannot drift: a fee quoted against one payload and a filing made
with another is a bug that only shows up as a wrong number on a real filing.
"""

import logging

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# Labels the UI has historically stored in place of a real court filing-component
# code. None of these are meaningful to the EFSP.
_PLACEHOLDER_COMPONENT_LABELS = {"", "supporting", "attachment", "attachments"}


class PayloadValidationError(Exception):
    """The payload cannot succeed at the EFSP, with a reason worth showing a filer.

    Raised only for conditions the court's own code lists already prove wrong, so
    the message can be specific. Views turn this into a 400 carrying the message.
    """


def prepare_efile_payload(efile_data, jurisdiction_id, court_id):
    """Apply every server-side fixup an EFSP request needs. Mutates ``efile_data``.

    Raises ``PayloadValidationError`` when the payload is knowably invalid.
    """
    _drop_empty_cross_references(efile_data)
    substitute_test_document_urls(efile_data)
    validate_document_selections(efile_data)
    resolve_placeholder_filing_components(efile_data, jurisdiction_id, court_id)
    validate_required_party_types(efile_data, jurisdiction_id, court_id)
    return efile_data


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


def resolve_placeholder_filing_components(efile_data, jurisdiction_id, court_id):
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

    resolved_codes: dict[str, str | None] = {}
    for bundle in bundles:
        filing_type = bundle.get("filing_type")
        if not filing_type:
            continue
        if filing_type not in resolved_codes:
            resolved_codes[filing_type] = _lookup_attachment_component(jurisdiction_id, court_id, filing_type)
        code = resolved_codes[filing_type]
        if code:
            bundle["filing_component"] = code


def validate_required_party_types(efile_data, jurisdiction_id, court_id):
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

    required = _lookup_required_party_types(jurisdiction_id, court_id, case_type)
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


def _lookup_required_party_types(jurisdiction_id, court_id, case_type):
    """Return ``{code: name}`` for the case type's required party types.

    Empty when the list cannot be fetched or the court marks nothing required, so
    callers treat "unknown" and "nothing required" alike -- both mean "do not
    block on this".
    """
    url = (
        f"{settings.EFSP_URL}/jurisdictions/{jurisdiction_id}/codes/courts/{court_id}/"
        f"case_types/{case_type}/party_types"
    )
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return {}
        party_types = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("Could not resolve required party types for case type %s: %s", case_type, error)
        return {}

    if not isinstance(party_types, list):
        return {}

    return {
        str(party_type.get("code")): party_type.get("name") or str(party_type.get("code"))
        for party_type in party_types
        # The EFSP renders this as a JSON boolean, but Tyler has been seen sending
        # the string "true" for the same field elsewhere in the code lists.
        if isinstance(party_type, dict) and str(party_type.get("isrequired", "")).lower() == "true"
    }


def _lookup_attachment_component(jurisdiction_id, court_id, filing_type):
    """Return the court's attachment filing-component code, or None if unavailable."""
    url = (
        f"{settings.EFSP_URL}/jurisdictions/{jurisdiction_id}/codes/courts/{court_id}/"
        f"filing_types/{filing_type}/filing_components"
    )
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
        components = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.warning("Could not resolve filing component for filing type %s: %s", filing_type, error)
        return None

    if not isinstance(components, list):
        return None

    for component in components:
        if isinstance(component, dict) and str(component.get("name", "")).lower() in {"attachment", "attachments"}:
            return component.get("code")
    return None
