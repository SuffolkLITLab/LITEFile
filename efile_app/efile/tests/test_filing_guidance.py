"""Saved filing choices select informational guidance, never submission rules."""

import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from django.conf import settings
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
    content = response.content.decode()
    assert content.index("</h1>") < content.index(RULE["text"]) < content.index('id="document-upload-form"')
    filing.court_code = "court:other"
    filing.save()
    response = client.get(url)
    assert response.status_code == 200
    assert RULE["text"] not in response.content.decode()
    filing.refresh_from_db()
    assert filing.disclaimer_acceptance == {}
    assert filing.status == FilingDraft.Status.DRAFT


def test_invalid_guidance_is_checked_and_logged_once_per_loaded_config(monkeypatch, caplog):
    loaded = {"filing_guidance": [{**deepcopy(RULE), "steps": "review"}]}
    monkeypatch.setattr(config_loader, "load_jurisdiction_config", lambda jurisdiction: loaded)
    for _ in range(3):
        assert filing_guidance(draft(), "review") == []
    assert len([record for record in caplog.records if "Invalid filing guidance" in record.message]) == 1


def test_demo_guidance_is_shown_only_when_a_demo_file_is_set(settings, tmp_path):
    demo = tmp_path / "demo.yaml"
    demo.write_text("illinois:\n  - id: demo\n    steps: [review]\n    title: Demo title\n    text: Demo text\n")
    settings.FILING_GUIDANCE_DEMO_FILE = ""
    assert filing_guidance(draft(), "review") == []
    settings.FILING_GUIDANCE_DEMO_FILE = str(demo)
    assert [item["title"] for item in filing_guidance(draft(), "review")] == ["Demo title"]
    assert filing_guidance(draft(jurisdiction="vermont"), "review") == []


def test_shipped_demo_file_is_valid_and_kept_out_of_state_config():
    demo = Path(settings.BASE_DIR).parent / "testing" / "filing-guidance-demo.yaml"
    assert not guidance_errors({"filing_guidance": yaml.safe_load(demo.read_text())["illinois"]})
    for jurisdiction in config_loader.get_available_jurisdictions():
        rules = config_loader.load_jurisdiction_config(jurisdiction).get("filing_guidance", [])
        assert not [rule for rule in rules if rule["id"].startswith("local_validation")]


def test_every_workflow_page_shows_guidance_after_its_heading():
    templates = Path(settings.BASE_DIR) / "efile" / "templates" / "efile"
    include = '{% include "efile/partials/filing_guidance.html" %}'
    assert include not in (templates / "workflow_base.html").read_text()
    for template in templates.glob("*.html"):
        source = template.read_text()
        if 'extends "efile/workflow_base.html"' not in source:
            continue
        headings = [match.end() for match in re.finditer("</h1>", source)]
        includes = [match.start() for match in re.finditer(re.escape(include), source)]
        assert len(includes) == len(headings), template.name
        assert all(heading < position for heading, position in zip(headings, includes, strict=True)), template.name
