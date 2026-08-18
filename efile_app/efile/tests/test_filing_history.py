"""What a filer can learn about filings they have already sent.

Two things are under test here. The first is reading Tyler's filing-detail
payload, which is deeply nested ECF 4 XML rendered as JSON: the fixtures below
keep that shape exactly (only the names and identifiers are invented), because
every simplification of it would test a payload the court never sends.

The second is "My cases" itself -- grouping a flat filing history into cases,
and archiving the ones the filer is done watching.
"""

from unittest.mock import patch

import pytest
from django.urls import reverse

from efile.models import ArchivedCase
from efile.services.filings import (
    archive_case,
    cases_for_user,
    court_contact,
    describe_filing_detail,
    status_presentation,
)

CASES_URL = reverse("filing_statuses", kwargs={"jurisdiction": "illinois"})


def _identification(category, value):
    return {
        "identificationID": {"value": value},
        "identificationCategory": {
            "name": "{http://niem.gov/niem/niem-core/2.0}IdentificationCategoryText",
            "value": {"value": category},
        },
    }


def _attachment(description, url):
    return {
        "binaryDescriptionText": {"value": description},
        "binaryLocationURI": {"value": url},
        "attachmentSequenceID": {"value": "0"},
    }


def rejected_detail():
    """A rejected filing, as the EFSP returns it: comment on the document."""

    return {
        "caseCourt": {
            "organizationIdentification": {
                "name": "{http://niem.gov/niem/niem-core/2.0}OrganizationIdentification",
                "value": {"identificationID": {"value": "kane"}},
            }
        },
        "filingSubmissionDate": {
            "dateRepresentation": {
                "name": "{http://niem.gov/niem/niem-core/2.0}DateTime",
                "value": {"value": 1677189792000},
            }
        },
        "documentIdentification": [
            _identification("ENVELOPEID", "275057"),
            _identification("FILINGID", "94e86d5d-de80-454d-a47c-ecd017d22e3a"),
        ],
        "filingStatus": {
            "statusDescriptionText": [{"value": "filing has been rejected"}],
            "filingStatusCode": "rejected",
        },
        "filingLeadDocument": [
            {
                "documentDescriptionText": {"value": "Appearance (No Fee)"},
                "documentStatus": {
                    "statusText": {"value": "Please refile with the case number on page 1."},
                    "statusDescriptionText": [{"value": "RejectComments"}],
                },
                "documentRendition": [
                    {
                        "documentRenditionMetadata": {
                            "documentAttachment": [
                                _attachment("Original - appearance.pdf", "https://example.tylertech.cloud/one"),
                            ]
                        }
                    }
                ],
            }
        ],
        "case": {
            "name": "{urn:oasis:names:tc:legalxml-courtfiling:schema:xsd:CivilCase-4.0}CivilCase",
            "value": {
                "caseTitleText": {"value": "Ada Torres v. Blue Harbor LLC"},
                "caseDocketID": {"value": "2017-L-000278"},
            },
        },
        "payment": {"accountName": "Global Account", "waiverIndicator": {"value": True}},
        "envelopeFees": [
            {
                "allowanceCharge": [
                    {
                        "allowanceChargeReason": {"value": "Convenience Fee"},
                        "amount": {"value": 0.0, "currencyID": "USD"},
                    },
                    {
                        "allowanceChargeReason": {"value": "Total Court Filing Fees"},
                        "amount": {"value": 89.5, "currencyID": "USD"},
                    },
                ]
            }
        ],
    }


def accepted_detail():
    """An accepted filing carries the court's own copy alongside the filer's."""

    detail = rejected_detail()
    detail["filingStatus"] = {
        "statusDescriptionText": [{"value": "filing has been accepted by the court"}],
        "filingStatusCode": "accepted",
    }
    detail["filingAcceptDate"] = {
        "dateRepresentation": {
            "name": "{http://niem.gov/niem/niem-core/2.0}DateTime",
            "value": {"value": 1677276192000},
        }
    }
    document = detail["filingLeadDocument"][0]
    document["documentStatus"] = {"statusDescriptionText": [{"value": "AcceptComments"}]}
    document["documentRendition"][0]["documentRenditionMetadata"]["documentAttachment"] = [
        _attachment("Original - appearance.pdf", "https://example.tylertech.cloud/one"),
        _attachment("Transmitted - appearance.pdf", "https://example.tylertech.cloud/two"),
    ]
    return detail


def filing_row(**overrides):
    """One entry as ``list_filing_data`` normalizes it."""

    row = {
        "filing_status": "accepted",
        "filing_status_text": "filing has been accepted by the court",
        "filing_id": "filing-1",
        "envelope_id": "1001",
        "case_tracking_id": "case-a",
        "case_title": "Ada Torres v. Blue Harbor LLC",
        "case_number": "2024-EV-000123",
        "court_code": "kane",
        "filing_code": "Appearance",
        "received_timestamp": 1677189792000,
        "filed_timestamp": 1677189792000,
    }
    row.update(overrides)
    return row


def described(payload, names=None):
    """``describe_filing_detail`` for a payload that is really there."""

    filing = describe_filing_detail(payload, names)
    assert filing is not None
    return filing


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="history-user", tyler_jurisdiction="illinois")


def sign_in(client, user):
    client.force_login(user)
    session = client.session
    session["jurisdiction"] = "illinois"
    session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
    session.save()


# ---------------------------------------------------------------- reading Tyler


def test_rejection_comment_is_pulled_off_the_document():
    filing = described(rejected_detail())

    assert filing["status_presentation"]["label"] == "Rejected"
    assert filing["comments"] == [
        {
            "kind": "rejection",
            "heading": "Why the court rejected this",
            "text": "Please refile with the case number on page 1.",
        }
    ]


def test_accepted_filing_offers_both_the_sent_copy_and_the_courts_copy():
    filing = described(accepted_detail())

    attachments = filing["documents"][0]["attachments"]
    assert [attachment["label"] for attachment in attachments] == [
        "The copy you sent",
        "The court's file-stamped copy",
    ]
    assert [attachment["filename"] for attachment in attachments] == ["appearance.pdf", "appearance.pdf"]
    assert attachments[1]["url"] == "https://example.tylertech.cloud/two"


def test_a_pending_filing_does_not_call_the_courts_copy_file_stamped():
    pending = rejected_detail()
    pending["filingStatus"] = {"filingStatusCode": "under-review", "statusDescriptionText": []}
    pending["filingLeadDocument"][0]["documentRendition"][0]["documentRenditionMetadata"]["documentAttachment"] = [
        _attachment("Transmitted - appearance.pdf", "https://example.tylertech.cloud/two"),
    ]

    filing = described(pending)

    assert filing["documents"][0]["attachments"][0]["label"] == "The copy the court received"


def test_identifiers_case_and_fees_come_through():
    filing = described(rejected_detail(), {"kane": "Kane County"})

    assert filing["filing_id"] == "94e86d5d-de80-454d-a47c-ecd017d22e3a"
    assert filing["envelope_id"] == "275057"
    assert filing["court_name"] == "Kane County"
    assert filing["docket_number"] == "2017-L-000278"
    assert filing["submitted_at"].year == 2023
    # Only the charges that cost something are worth showing.
    assert filing["fees"] == [{"reason": "Total Court Filing Fees", "amount": "89.50"}]


def test_a_payload_the_court_never_filled_in_still_describes_something():
    filing = described({"filingStatus": {"filingStatusCode": "submitted"}})

    assert filing["documents"] == []
    assert filing["comments"] == []
    assert filing["status_presentation"]["label"] == "Waiting on the court"
    assert describe_filing_detail(None) is None


def test_an_unfamiliar_status_code_is_described_rather_than_dropped():
    assert status_presentation("something-tyler-added-yesterday")["label"] == "Sent to the court"


def test_court_contact_falls_back_to_the_jurisdictions_help_line():
    # Massachusetts is the shipped config with jurisdiction-level help details.
    contact = court_contact("massachusetts", "no-such-court")

    assert contact["phone"] == "711"
    assert contact["url"].startswith("https://")


# ------------------------------------------------------------------- My cases


@pytest.mark.django_db
def test_filings_are_grouped_into_the_cases_they_belong_to(rf, user):
    request = rf.get(CASES_URL)
    request.user = user
    rows = [
        filing_row(filing_id="filing-1", received_timestamp=1677189792000),
        filing_row(filing_id="filing-2", filing_status="rejected", received_timestamp=1677276192000),
        filing_row(filing_id="filing-3", case_tracking_id="case-b", case_number="2024-EV-000999"),
    ]

    with (
        patch("efile.services.filings.list_filing_data", return_value=rows),
        patch("efile.services.filings.court_names", return_value={"kane": "Kane County"}),
    ):
        cases = cases_for_user(request, "illinois")

    assert [case["docket_number"] for case in cases] == ["2024-EV-000123", "2024-EV-000999"]
    first = cases[0]
    assert first["filing_count"] == 2
    assert first["court_name"] == "Kane County"
    # Newest filing first, and it is the one the case's status reflects.
    assert first["filings"][0]["filing_id"] == "filing-2"
    assert first["latest_status"]["label"] == "Rejected"


@pytest.mark.django_db
def test_a_filing_with_no_case_yet_keeps_its_own_entry(rf, user):
    request = rf.get(CASES_URL)
    request.user = user
    rows = [filing_row(case_tracking_id="", case_number="", case_title="", filing_status="rejected")]

    with (
        patch("efile.services.filings.list_filing_data", return_value=rows),
        patch("efile.services.filings.court_names", return_value={}),
    ):
        cases = cases_for_user(request, "illinois")

    assert len(cases) == 1
    assert cases[0]["case_tracking_id"] == ""


@pytest.mark.django_db
def test_archiving_a_case_takes_it_out_of_the_list_without_losing_it(client, user):
    sign_in(client, user)
    rows = [filing_row(), filing_row(filing_id="filing-3", case_tracking_id="case-b", case_number="2024-EV-000999")]

    with (
        patch("efile.services.filings.list_filing_data", return_value=rows),
        patch("efile.services.filings.court_names", return_value={}),
    ):
        response = client.post(
            CASES_URL,
            {"action": "archive", "case_tracking_id": "case-a", "docket_number": "2024-EV-000123"},
            follow=True,
        )
        assert response.status_code == 200
        assert ArchivedCase.objects.filter(user=user, case_tracking_id="case-a").exists()

        listed = client.get(CASES_URL)
        assert [case["docket_number"] for case in listed.context["cases"]] == ["2024-EV-000999"]
        assert listed.context["archived_count"] == 1

        archived = client.get(f"{CASES_URL}?archived=1")
        assert [case["docket_number"] for case in archived.context["cases"]] == ["2024-EV-000123"]


@pytest.mark.django_db
def test_a_case_can_come_back_out_of_the_archive(client, user):
    sign_in(client, user)
    archive_case(user, "illinois", "case-a", docket_number="2024-EV-000123")

    with (
        patch("efile.services.filings.list_filing_data", return_value=[filing_row()]),
        patch("efile.services.filings.court_names", return_value={}),
    ):
        client.post(CASES_URL, {"action": "unarchive", "case_tracking_id": "case-a"}, follow=True)
        listed = client.get(CASES_URL)

    assert not ArchivedCase.objects.filter(user=user).exists()
    assert [case["docket_number"] for case in listed.context["cases"]] == ["2024-EV-000123"]


@pytest.mark.django_db
def test_one_filers_archive_does_not_touch_anothers(client, user, django_user_model):
    other = django_user_model.objects.create_user(username="other-filer", tyler_jurisdiction="illinois")
    archive_case(other, "illinois", "case-a", docket_number="2024-EV-000123")
    sign_in(client, user)

    with (
        patch("efile.services.filings.list_filing_data", return_value=[filing_row()]),
        patch("efile.services.filings.court_names", return_value={}),
    ):
        listed = client.get(CASES_URL)

    assert [case["docket_number"] for case in listed.context["cases"]] == ["2024-EV-000123"]


@pytest.mark.django_db
def test_the_court_being_unreachable_says_so_instead_of_erroring(client, user):
    sign_in(client, user)

    with patch("efile.services.filings.list_filing_data", side_effect=ValueError("bad JSON")):
        response = client.get(CASES_URL)

    assert response.status_code == 200
    assert response.context["lookup_failed"] is True


@pytest.mark.django_db
def test_filing_detail_shows_the_clerks_comment_and_the_documents(client, user):
    sign_in(client, user)
    url = reverse(
        "filing_detail",
        kwargs={"jurisdiction": "illinois", "court_code": "kane", "filing_id": "filing-1"},
    )

    with (
        patch("efile.views.my_cases.fetch_filing_detail", return_value=accepted_detail()),
        patch("efile.views.my_cases.court_names", return_value={"kane": "Kane County"}),
    ):
        response = client.get(url)

    content = response.content.decode()
    assert response.status_code == 200
    assert "Please refile with the case number on page 1." not in content  # accepted filings have no reject comment
    assert "The court&#x27;s file-stamped copy" in content
    assert "https://example.tylertech.cloud/two" in content
    assert "Kane County" in content


@pytest.mark.django_db
def test_filing_detail_says_so_when_the_court_will_not_answer(client, user):
    sign_in(client, user)
    url = reverse(
        "filing_detail",
        kwargs={"jurisdiction": "illinois", "court_code": "kane", "filing_id": "filing-1"},
    )

    with patch("efile.views.my_cases.fetch_filing_detail", return_value=None):
        response = client.get(url)

    assert response.status_code == 200
    assert "could not get this filing" in response.content.decode()


@pytest.mark.django_db
def test_my_cases_needs_a_signed_in_filer(client):
    response = client.get(CASES_URL)

    assert response.status_code == 302
    assert "/login/" in response.url
