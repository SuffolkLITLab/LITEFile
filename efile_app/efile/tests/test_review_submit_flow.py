import pytest
from django.urls import reverse

from efile.models import FilingDocument, FilingDraft, FilingParty
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.workflow import WorkflowStepKey


@pytest.fixture
def submission_draft(client, django_user_model):
    user = django_user_model.objects.create_user(username="review-user", tyler_jurisdiction="illinois")
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction="illinois",
        workflow_version=2,
        current_step=WorkflowStepKey.PAYMENT,
        existing_case="new",
        court_code="cook:law1",
        court_name="Circuit Court of Cook County",
        case_category_code="civil",
        case_category_name="Civil",
        case_type_code="contract",
        case_type_name="Contract",
        document_checklist_acknowledged=True,
    )
    FilingDocument.objects.create(
        draft=draft,
        role=FilingDocument.Role.LEAD,
        sort_order=0,
        name="Petition.pdf",
        filing_type_code="petition",
        filing_type_name="Petition",
        document_type_code="public",
        document_type_name="Public",
        filing_component_code="lead",
        filing_component_name="Lead document",
    )
    FilingParty.objects.create(
        draft=draft,
        role="filer",
        sort_order=0,
        party_type="PLA",
        party_type_name="Plaintiff/Petitioner",
        first_name="Jordan",
        last_name="Taylor",
        email="jordan@example.com",
        address_line_1="123 Main Street",
        city="Springfield",
        state="IL",
        zip_code="62701",
    )
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "test-token"}
    session.save()
    return draft


@pytest.mark.django_db
def test_payment_saves_account_and_advances_durable_step(client, submission_draft):
    response = client.post(
        reverse("payment", kwargs={"jurisdiction": "illinois"}),
        {"selected_payment_account": "pay-123", "selected_payment_account_name": "Card ending in 4242"},
    )

    assert response.status_code == 302
    assert response.url == reverse("case_review", kwargs={"jurisdiction": "illinois"})
    submission_draft.refresh_from_db()
    assert submission_draft.selected_payment_account_id == "pay-123"
    assert submission_draft.current_step == WorkflowStepKey.REVIEW


class _PaymentAccountTypesResponse:
    status_code = 200

    @staticmethod
    def json():
        return [
            {"code": "CC", "description": "Credit Card"},
            {"code": "WV", "description": "Waiver"},
        ]


@pytest.mark.django_db
def test_payment_account_types_proxies_the_courts_type_list(client, submission_draft, monkeypatch):
    monkeypatch.setattr(
        "efile.api.auth_views.requests.get",
        lambda *args, **kwargs: _PaymentAccountTypesResponse(),
    )

    response = client.get(reverse("api:payment_account_types"), {"jurisdiction": "illinois"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert {"code": "CC", "description": "Credit Card"} in body["data"]


@pytest.mark.django_db
def test_payment_persists_account_type_and_quoted_fees(client, submission_draft):
    response = client.post(
        reverse("payment", kwargs={"jurisdiction": "illinois"}),
        {
            "selected_payment_account": "pay-123",
            "selected_payment_account_name": "Card ending in 4242",
            "selected_payment_account_type": "CC",
            "quoted_fee_total": "125.00",
            "quoted_fee_breakdown": '[{"label": "Filing fee", "amount": "100.00"}, {"label": "Technology fee", "amount": "25.00"}]',
        },
    )

    assert response.status_code == 302
    submission_draft.refresh_from_db()
    assert submission_draft.selected_payment_account_type == "CC"
    assert submission_draft.quoted_fee_total == "125.00"
    assert submission_draft.quoted_fee_breakdown == [
        {"label": "Filing fee", "amount": "100.00"},
        {"label": "Technology fee", "amount": "25.00"},
    ]


@pytest.mark.django_db
def test_payment_tolerates_malformed_fee_breakdown(client, submission_draft):
    response = client.post(
        reverse("payment", kwargs={"jurisdiction": "illinois"}),
        {
            "selected_payment_account": "pay-123",
            "selected_payment_account_name": "Payment waiver",
            "selected_payment_account_type": "WV",
            "quoted_fee_breakdown": "not json",
        },
    )

    assert response.status_code == 302
    submission_draft.refresh_from_db()
    assert submission_draft.selected_payment_account_type == "WV"
    assert submission_draft.quoted_fee_breakdown == []


@pytest.mark.django_db
def test_review_shows_waiver_messaging_instead_of_fee_reference(client, submission_draft):
    submission_draft.selected_payment_account_id = "pay-123"
    submission_draft.selected_payment_account_name = "Payment waiver"
    submission_draft.selected_payment_account_type = "WV"
    submission_draft.save(
        update_fields=["selected_payment_account_id", "selected_payment_account_name", "selected_payment_account_type"]
    )

    response = client.get(reverse("case_review", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    assert b"fee waiver" in response.content
    assert b"the previous screen" not in response.content


@pytest.mark.django_db
def test_review_shows_previously_calculated_fee_total(client, submission_draft):
    submission_draft.selected_payment_account_id = "pay-123"
    submission_draft.selected_payment_account_name = "Card ending in 4242"
    submission_draft.selected_payment_account_type = "CC"
    submission_draft.quoted_fee_total = "125.00"
    submission_draft.quoted_fee_breakdown = [{"label": "Filing fee", "amount": "125.00"}]
    submission_draft.save(
        update_fields=[
            "selected_payment_account_id",
            "selected_payment_account_name",
            "selected_payment_account_type",
            "quoted_fee_total",
            "quoted_fee_breakdown",
        ]
    )

    response = client.get(reverse("case_review", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    assert b"125.00" in response.content
    assert b"Filing fee" in response.content
    assert b"the previous screen" not in response.content


@pytest.mark.django_db
def test_review_uses_new_edit_routes_and_durable_summary(client, submission_draft):
    submission_draft.selected_payment_account_id = "pay-123"
    submission_draft.selected_payment_account_name = "Card ending in 4242"
    submission_draft.save(update_fields=["selected_payment_account_id", "selected_payment_account_name"])

    response = client.get(reverse("case_review", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    assert b"Jordan" in response.content
    assert b"Petition.pdf" in response.content
    assert b"Filing type:" in response.content
    assert b"review-document-tag" in response.content
    assert reverse("organize_documents", kwargs={"jurisdiction": "illinois"}).encode() in response.content
    assert reverse("your_information", kwargs={"jurisdiction": "illinois"}).encode() in response.content
    assert reverse("expert_form", kwargs={"jurisdiction": "illinois"}).encode() not in response.content
    assert reverse("upload", kwargs={"jurisdiction": "illinois"}).encode() not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route", "target"),
    [
        ("upload_first", "upload_documents"),
        ("expert_form", "extraction_review"),
        ("upload", "organize_documents"),
    ],
)
def test_retired_screen_urls_redirect_forward(client, submission_draft, route, target):
    response = client.get(reverse(route, kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 302
    # The filing is named in the URL: following an old link carries on with that
    # filing rather than leaving the next screen to guess which one it is.
    assert response.url == (reverse(target, kwargs={"jurisdiction": "illinois"}) + f"?draft={submission_draft.pk}")


@pytest.mark.django_db
def test_confirmation_uses_saved_submission_reference(client, submission_draft):
    submission_draft.mark_submitted({"confirmationNumber": "IL-2026-12345"})
    session = client.session
    session["last_submitted_filing_draft_id"] = submission_draft.pk
    session.save()

    response = client.get(reverse("filing_confirmation", kwargs={"jurisdiction": "illinois"}))

    assert response.status_code == 200
    assert b"IL-2026-12345" in response.content
    assert b"Circuit Court of Cook County" in response.content
