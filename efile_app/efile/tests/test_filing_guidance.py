"""Saved filing choices select informational guidance, never submission rules."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

from efile.checks import configured_filing_guidance_is_valid
from efile.management.commands.extract_config_text import _render
from efile.models import FilingDraft
from efile.services.filing_guidance import filing_guidance, guidance_errors
from efile.tests.test_document_extractions import authorize
from efile.utils.config_loader import config_loader

RULE = {
    "id": "local_help",
    "steps": ["upload_documents", "review"],
    "title": "Help with your documents",
    "text": "Read the local document instructions if you need help.",
    "when": {"court_codes": ["court:a", "court:b"], "case_type_codes": ["civil"]},
    "resources": [{"label": "Document instructions", "url": "https://court.example.org/help"}],
}


@pytest.fixture
def config(monkeypatch):
    value = {"filing_guidance": [deepcopy(RULE)]}
    original = config_loader.load_jurisdiction_config

    def configured(jurisdiction):
        return {**original(jurisdiction), **value} if jurisdiction == "illinois" else original(jurisdiction)

    monkeypatch.setattr(config_loader, "load_jurisdiction_config", configured)
    return value


def draft(**kwargs):
    values = dict(jurisdiction="illinois", court_code="court:a", case_type_code="civil", documents=MagicMock())
    values.update(kwargs)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("values", "step", "matches"),
    [
        ({}, "upload_documents", True),
        ({"court_code": "court:b"}, "review", True),
        ({}, "payment", False),
        ({"court_code": "court:a-extra"}, "review", False),
        ({"court_code": ""}, "review", False),
        ({"case_type_code": ""}, "review", False),
        ({"case_type_code": "family"}, "review", False),
        ({"jurisdiction": "vermont"}, "review", False),
    ],
)
def test_guidance_matches_saved_codes_and_configured_steps(config, values, step, matches):
    assert bool(filing_guidance(draft(**values), step)) is matches


def test_no_draft_has_no_guidance(config):
    assert filing_guidance(None, "upload_documents") == []


def test_unconditional_guidance_needs_no_court_and_keeps_config_order(config):
    first = config["filing_guidance"][0]
    first.pop("when")
    config["filing_guidance"].append({**first, "id": "another_tip", "title": "Another tip"})
    assert [item["title"] for item in filing_guidance(draft(court_code=""), "review")] == [RULE["title"], "Another tip"]


def test_filing_types_use_all_current_documents_and_ignore_old_draft_defaults(config):
    config["filing_guidance"][0]["when"]["filing_type_codes"] = ["cover"]
    filing = draft(filing_type_code="cover")
    filing.documents.values_list.return_value = ["petition", "cover"]
    assert filing_guidance(filing, "review")
    filing.documents.values_list.return_value = ["petition"]
    assert filing_guidance(filing, "review") == []
    filing.documents.values_list.assert_called_with("filing_type_code", flat=True)


def test_other_saved_metadata_conditions(config):
    config["filing_guidance"][0]["when"].update(
        case_category_codes=["family"], case_subtype_codes=["minor"], existing_case=["new"]
    )
    filing = draft(case_category_code="family", case_subtype_code="minor", existing_case="new")
    assert filing_guidance(filing, "review")
    filing.existing_case = "existing"
    assert not filing_guidance(filing, "review")


@pytest.mark.parametrize(
    "change",
    [
        {"blocking": True},
        {"when": {"court_code": ["court:a"]}},
        {"when": {"court_codes": []}},
        {"when": {"court_codes": [123]}},
        {"when": {"existing_case": ["maybe"]}},
        {"when": []},
        {"steps": ["not_a_step"]},
        {"steps": "review"},
        {"steps": []},
        {"text": ""},
        {"title": None},
        {"resources": [{"label": "Help", "url": "javascript:alert(1)"}]},
        {"resources": [{"label": "Help", "url": "//example.org/help"}]},
        {"resources": [{"label": "Help", "url": "https://user:pass@example.org/help"}]},
        {"resources": [{"label": "Help", "url": "https://[broken"}]},
        {"resources": "https://example.org"},
    ],
)
def test_invalid_guidance_is_reported_and_omitted_without_blocking(config, change):
    config["filing_guidance"][0].update(change)
    assert guidance_errors(config)
    assert filing_guidance(draft(), "review") == []
    problems = configured_filing_guidance_is_valid(None)
    assert problems
    assert all(problem.id == "efile.W004" for problem in problems)


@pytest.mark.parametrize("rules", [None, {}, ["bad"], [RULE, RULE]])
def test_invalid_lists_and_duplicate_ids(rules):
    assert guidance_errors({"filing_guidance": rules})


def test_plain_text_is_escaped_and_resources_are_links(config):
    config["filing_guidance"][0]["title"] = '<script>alert("x")</script>'
    html = render_to_string(
        "efile/partials/filing_guidance.html", {"filing_guidance": filing_guidance(draft(), "review")}
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'href="https://court.example.org/help"' in html
    assert 'aria-labelledby="filing-guidance-1"' in html
    assert "<input" not in html
    assert "<button" not in html


def test_guidance_strings_join_the_existing_translation_extractor(config):
    generated = _render()
    assert '"filing_guidance.local_help.title"' in generated
    assert '"filing_guidance.local_help.text"' in generated
    assert '"filing_guidance.local_help.resources.0.label"' in generated
    assert RULE["text"] in generated


@pytest.mark.django_db
def test_workflow_renders_current_saved_guidance_after_resuming(client, django_user_model, config):
    user = django_user_model.objects.create_user(username="guidance-filer", tyler_jurisdiction="illinois")
    filing = FilingDraft.objects.create(
        user=user, jurisdiction="illinois", court_code="court:a", case_type_code="civil", workflow_version=2
    )
    authorize(client, filing)
    url = reverse("upload_documents", kwargs={"jurisdiction": "illinois"}) + f"?draft={filing.pk}"
    response = client.get(url)
    assert response.status_code == 200
    assert RULE["text"] in response.content.decode()
    assert response.content.decode().index(RULE["text"]) < response.content.decode().index('id="document-upload-form"')
    filing.court_code = "court:other"
    filing.save()
    response = client.get(url)
    assert response.status_code == 200
    assert RULE["text"] not in response.content.decode()
    filing.refresh_from_db()
    assert filing.disclaimer_acceptance == {}
    assert filing.status == FilingDraft.Status.DRAFT
