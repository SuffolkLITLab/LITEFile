"""Copy that a state can reword, and the plumbing that keeps it translatable."""

import pytest
from django.core.management import CommandError, call_command
from django.template import Context, Template
from django.urls import reverse

from efile.checks import configured_ui_text_keys_are_known
from efile.models import FilingDocument, FilingDraft
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.utils.ui_text import UI_STRINGS, config_overrides, get_text, get_texts
from efile.workflow import ExistingCase, WorkflowStepKey


def test_a_state_without_an_override_gets_the_default():
    assert get_text("terms.starting_document_example", jurisdiction="illinois") == "petition"


def test_a_state_can_reword_a_term():
    """The document that opens a case is a complaint in Vermont, not a petition."""

    assert get_text("terms.starting_document_example", jurisdiction="vermont") == "complaint"


def test_a_term_reaches_the_sentences_that_use_it():
    """A state rewords the noun once, and every sentence naming it follows."""

    illinois = get_text("organize_documents.main_document_help", jurisdiction="illinois")
    vermont = get_text("organize_documents.main_document_help", jurisdiction="vermont")

    assert "like a petition" in illinois
    assert "like a complaint" in vermont


def test_jurisdiction_values_fill_placeholders():
    lede = get_text("your_information.lede", jurisdiction="vermont")

    assert "LITEFile account" in lede
    assert "eFile account" not in lede


def test_an_unknown_key_is_a_programming_error():
    with pytest.raises(KeyError, match="Unknown UI text key"):
        get_text("organize_documents.no_such_string", jurisdiction="illinois")


def test_an_unknown_placeholder_survives_rendering():
    """Configured copy is written outside the templates, so a stray placeholder
    has to show the filer a sentence rather than raise a 500."""

    config = {"text": {"parties": {"role_question": "Your role in {not_a_real_value}?"}}}

    assert get_text("parties.role_question", config=config) == "Your role in {not_a_real_value}?"


def test_overrides_are_read_as_dotted_keys():
    config = {"text": {"terms": {"starting_document_example": "complaint"}}}

    assert config_overrides(config) == {"terms.starting_document_example": "complaint"}


def test_get_texts_keys_by_short_name_for_javascript():
    texts = get_texts(["organize_documents.loading_choices"], jurisdiction="illinois")

    assert list(texts) == ["loading_choices"]


def test_the_template_tag_reads_the_jurisdiction_from_the_page():
    template = Template('{% load ui_text %}{% ui_text "organize_documents.main_document_help" %}')

    rendered = template.render(Context({"jurisdiction": "vermont"}))

    assert "like a complaint" in rendered


def test_every_configured_key_is_a_key_we_ship():
    """Guards the state YAML files themselves: a typo there would silently leave
    the filer reading the wording the state asked to change."""

    assert configured_ui_text_keys_are_known(None) == []


def test_the_check_reports_a_key_that_does_not_exist(monkeypatch):
    """Stand in for a state file that misspells a key, or names one we renamed."""

    monkeypatch.delitem(UI_STRINGS, "terms.starting_document_example")

    problems = configured_ui_text_keys_are_known(None)

    assert [problem.id for problem in problems] == ["efile.W002"]


def test_configured_copy_is_extracted_for_translators():
    """xgettext cannot read YAML, so the generated stub is what puts a state's
    own wording into the Spanish catalog. It must not go stale."""

    call_command("extract_config_text", "--check")


def test_the_extraction_check_fails_when_config_copy_changes(monkeypatch):
    from efile.management.commands import extract_config_text

    monkeypatch.setattr(extract_config_text, "_render", lambda: "something else entirely")
    with pytest.raises(CommandError, match="out of date"):
        call_command("extract_config_text", "--check")


# -- The pages themselves ---------------------------------------------------


def organize_draft(client, django_user_model, jurisdiction):
    user = django_user_model.objects.create_user(username=f"{jurisdiction}-user", tyler_jurisdiction=jurisdiction)
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction=jurisdiction,
        workflow_version=2,
        existing_case=ExistingCase.NEW,
        court_code="court",
        case_category_code="100",
        case_type_code="200",
        current_step=WorkflowStepKey.ORGANIZE_DOCUMENTS,
        document_checklist_acknowledged=True,
    )
    FilingDocument.objects.create(draft=draft, role=FilingDocument.Role.LEAD, sort_order=0, name="filing.pdf")
    FilingDocument.objects.create(draft=draft, role=FilingDocument.Role.SUPPORTING, sort_order=0, name="exhibit.pdf")
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["auth_tokens"] = {f"TYLER-TOKEN-{jurisdiction.upper()}": "token"}
    session["jurisdiction"] = jurisdiction
    session.save()
    return draft


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("jurisdiction", "example"),
    [("illinois", "like a petition"), ("vermont", "like a complaint")],
)
def test_organize_documents_names_the_document_this_state_starts_with(client, django_user_model, jurisdiction, example):
    organize_draft(client, django_user_model, jurisdiction)

    response = client.get(reverse("organize_documents", kwargs={"jurisdiction": jurisdiction}))

    assert response.status_code == 200
    assert example in response.content.decode()


@pytest.mark.django_db
def test_organize_documents_separates_the_main_document_from_court_components(client, django_user_model):
    """The filer picks one main document; the court can label several PDFs
    "Lead Document" as filing components. The screen must not read as though
    the second is a repeat of the first."""

    organize_draft(client, django_user_model, "illinois")

    content = client.get(reverse("organize_documents", kwargs={"jurisdiction": "illinois"})).content.decode()

    assert "Document role" not in content
    assert "Court filing component" in content
    assert "That is separate from the one main document you chose above" in content
    # The card header says the same thing the question above it said.
    assert "Lead document" not in content


@pytest.mark.django_db
def test_organize_documents_says_certified_copies_are_optional(client, django_user_model):
    organize_draft(client, django_user_model, "illinois")

    content = client.get(reverse("organize_documents", kwargs={"jurisdiction": "illinois"})).content.decode()

    assert "Certified copy and courtesy email (optional)" in content
    assert "Neither one is required" in content


@pytest.mark.django_db
def test_organize_documents_hands_its_own_strings_to_the_script(client, django_user_model):
    """The script rewrites these lists after the court answers, so its copy has
    to travel with the page to stay configurable and translatable."""

    organize_draft(client, django_user_model, "illinois")

    content = client.get(reverse("organize_documents", kwargs={"jurisdiction": "illinois"})).content.decode()

    assert "loading_choices" in content
    assert "filing_component_fixed_note" in content
