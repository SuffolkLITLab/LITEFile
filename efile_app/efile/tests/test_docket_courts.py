import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from efile.services.docket_courts import infer_massachusetts_court

FIXTURES = json.loads((Path(__file__).parent / "fixtures/massachusetts_dockets.json").read_text())


@pytest.mark.parametrize("example", FIXTURES["verified_examples"])
def test_official_examples_resolve_only_to_an_offered_court(example):
    offered = [{"value": example["tyler_code"], "text": example["name"]}]
    assert infer_massachusetts_court(example["docket"], offered) == offered[0]
    assert infer_massachusetts_court(example["docket"], []) is None


@pytest.mark.parametrize("docket", FIXTURES["manual_examples"])
def test_unrecognized_and_legacy_numbers_need_manual_selection(docket):
    assert infer_massachusetts_court(docket, [{"value": "336", "text": "Ayer"}]) is None


def test_ambiguous_mapping_does_not_choose_a_court():
    records = [
        SimpleNamespace(court_code="48", department="District Court", tyler_code=code) for code in ["one", "two"]
    ]
    offered = [{"value": code, "text": code} for code in ["one", "two"]]
    assert infer_massachusetts_court("1448CV001026", offered, records=records) is None


def test_spacing_and_case_do_not_change_a_verified_match():
    offered = [{"value": "336", "text": "Ayer District Court"}]
    assert infer_massachusetts_court("14 48 cv 001026", offered) == offered[0]


@pytest.mark.django_db
def test_inference_endpoint_requires_auth_and_returns_an_offered_court(client, django_user_model):
    from unittest.mock import patch

    from django.urls import reverse

    from efile.models import FilingDraft
    from efile.tests.test_document_extractions import authorize

    url = reverse("docket_court", kwargs={"jurisdiction": "massachusetts"})
    assert client.get(url).status_code == 401
    user = django_user_model.objects.create_user(username="docket-test", tyler_jurisdiction="massachusetts")
    draft = FilingDraft.objects.create(user=user, jurisdiction="massachusetts")
    authorize(client, draft)
    offered = [{"value": "336", "text": "Ayer District Court"}]
    with patch("efile.services.court_selection.fetch_courts", return_value=offered):
        response = client.get(url, {"docket_number": "1448CV001026"})
    assert response.json() == {"success": True, "court": offered[0]}
