"""Prepare a client-built filing payload before it is sent to the EFSP proxy.

The fee quote and the final submission post the *same* ``efile_data`` blob to
two different EFSP endpoints. Every server-side adjustment to that blob belongs
here so the two cannot drift: a fee quoted against one payload and a filing made
with another is a bug that only shows up as a wrong number on a real filing.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Labels the UI has historically stored in place of a real court filing-component
# code. None of these are meaningful to the EFSP.
_PLACEHOLDER_COMPONENT_LABELS = {"", "supporting", "attachment", "attachments"}


def prepare_efile_payload(efile_data, jurisdiction_id, court_id):
    """Apply every server-side fixup an EFSP request needs. Mutates ``efile_data``."""
    _drop_empty_cross_references(efile_data)
    substitute_test_document_urls(efile_data)
    resolve_placeholder_filing_components(efile_data, jurisdiction_id, court_id)
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
    keys and URLs; only the URL handed to the proxy is replaced. The setting is
    defined in ``settings_dev`` alone, so no environment variable can turn this on
    in staging or production.
    """
    test_url = getattr(settings, "EFSP_TEST_DOCUMENT_URL", "")
    if not test_url:
        return

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
