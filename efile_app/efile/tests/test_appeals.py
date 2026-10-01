"""New appeals preserve lower-court details through review and EFSP."""

from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.urls import reverse

from efile.models import FilingDraft
from efile.services import appeals
from efile.services.appeals import code_list as live_code_list
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.services.drafts import read_case_data
from efile.services.efsp_payload import PayloadValidationError, _clean_case_identifiers, validate_lower_court
from efile.services.fee_quotes import fee_fingerprint
from efile.tests.helpers import reviewed_document


@pytest.fixture
def catalog(monkeypatch):
    def lookup(jurisdiction, path, lookups=None):
        if path.endswith("/categories"):
            return [{"code": "appeal", "ecfcasetype": "AppellateCase"}, {"code": "civil", "ecfcasetype": "CivilCase"}]
        return [
            {"code": "cook:law1", "name": "Cook County Law Division"},
            {"code": "TAC1", "name": "Appellate Court - 1st District"},
            {"code": "test", "name": "zDev Test Court"},
        ]

    monkeypatch.setattr(appeals, "code_list", lookup)


def draft_info(**overrides):
    return SimpleNamespace(
        **(
            {
                "existing_case": "new",
                "previous_case_id": "",
                "court_code": "TAC1",
                "court_name": "Court",
                "case_category_code": "appeal",
                "case_category_name": "Category",
                "jurisdiction": "illinois",
            }
            | overrides
        )
    )


def test_detection_uses_category_metadata_and_new_case_branch(catalog):
    assert appeals.is_new_appeal(draft_info())
    assert not appeals.is_new_appeal(draft_info(existing_case="existing"))
    assert not appeals.is_new_appeal(draft_info(previous_case_id="existing-id"))
    assert not appeals.is_new_appeal(draft_info(case_category_code="civil", court_name="Appeals Court"))


def test_illinois_options_exclude_test_and_appellate_courts(catalog):
    assert appeals.lower_court_options("illinois") == [
        {"value": "cook:law1", "label": "Cook County Law Division", "prod_code": "cook:law1"}
    ]


def test_massachusetts_keeps_distinct_environment_codes():
    options = appeals.lower_court_options("massachusetts")
    assert len(options) > 100
    assert len({option["value"] for option in options}) == len(options)
    brighton = next(row for row in options if row["value"] == "1753")
    assert brighton["prod_code"] == "6982"
    assert "Brighton" in brighton["label"]


@pytest.mark.parametrize(
    "jurisdiction,code,prod", [("illinois", "cook:law1", "cook:law1"), ("massachusetts", "1753", "6982")]
)
def test_payload_formats_lower_court(catalog, jurisdiction, code, prod):
    payload = {
        "efile_case_category": "appeal",
        "previous_case_id": "",
        "docket_number": "not-an-appellate-case-number",
        "lower_court_case": {"title": " Example v. Test ", "docket_number": "24-CV-001"},
        "trial_court": {"tyler_lower_court_code": code, "tyler_prod_lower_court_code": "wrong"},
    }
    _clean_case_identifiers(payload)
    validate_lower_court(payload, jurisdiction, "court")
    assert "previous_case_id" not in payload
    assert "docket_number" not in payload
    assert payload["trial_court"]["tyler_prod_lower_court_code"] == prod
    assert payload["lower_court_case"] == {"title": "Example v. Test", "docket_number": "24-CV-001", "judge": ""}


def test_payload_rejects_missing_or_invalid_lower_court(catalog):
    with pytest.raises(PayloadValidationError):
        validate_lower_court({"efile_case_category": "appeal"}, "illinois", "TAC1")
    with pytest.raises(PayloadValidationError):
        validate_lower_court(
            {
                "efile_case_category": "appeal",
                "lower_court_case": {"title": "Caption", "docket_number": "24-1"},
                "trial_court": {"tyler_lower_court_code": "invented"},
            },
            "illinois",
            "TAC1",
        )


class FakeLookups:
    def __init__(self, response):
        self.response = response
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return self.response


@pytest.fixture
def live_code_lists(monkeypatch):
    """Undo the autouse stub so lookups reach the given ``FakeLookups``."""
    monkeypatch.setattr(appeals, "code_list", live_code_list)
    cache.clear()
    yield
    cache.clear()


def test_payload_passes_lower_court_through_when_efsp_list_is_unavailable(live_code_lists):
    payload = {
        "efile_case_category": "appeal",
        "lower_court_case": {"title": "Caption", "docket_number": "24-1"},
        "trial_court": {"tyler_lower_court_code": "cook:law1", "name": "Cook County Law Division"},
    }
    validate_lower_court(payload, "illinois", "TAC1", lookups=FakeLookups(None))
    assert payload["trial_court"] == {
        "name": "Cook County Law Division",
        "tyler_lower_court_code": "cook:law1",
        "tyler_prod_lower_court_code": "cook:law1",
    }
    with pytest.raises(PayloadValidationError):
        validate_lower_court(
            {"efile_case_category": "appeal", "lower_court_case": {"title": "Caption", "docket_number": "24-1"}},
            "illinois",
            "TAC1",
            lookups=FakeLookups(None),
        )


def test_payload_lookups_use_the_request_budget_and_do_not_cache_its_failures(live_code_lists, monkeypatch):
    def unbudgeted(*args, **kwargs):
        raise AssertionError("lower-court lookups must go through the payload's lookups")

    monkeypatch.setattr(appeals.requests, "get", unbudgeted)
    lookups = FakeLookups(None)
    payload = {
        "efile_case_category": "appeal",
        "lower_court_case": {"title": "Caption", "docket_number": "24-1"},
        "trial_court": {"tyler_lower_court_code": "cook:law1"},
    }
    validate_lower_court(payload, "illinois", "TAC1", lookups=lookups)
    assert [url.rpartition("/codes/")[2] for url in lookups.urls] == [
        "courts/TAC1/categories",
        "courts/?fileable_only=false&with_names=true",
    ]
    courts = [{"code": "cook:law1", "name": "Cook County Law Division"}]
    assert appeals.code_list("illinois", "courts/TAC1/categories", lookups=FakeLookups(courts)) == courts


@pytest.mark.parametrize("extra", [{"previous_case_id": "123"}, {"efile_case_category": "civil"}])
def test_stale_lower_court_is_omitted(catalog, extra):
    payload = {"efile_case_category": "appeal", "lower_court_case": {"title": "old"}, "trial_court": {}} | extra
    validate_lower_court(payload, "illinois", "TAC1")
    assert "lower_court_case" not in payload
    assert "trial_court" not in payload


@pytest.mark.django_db
@pytest.mark.parametrize(
    "jurisdiction,code,name",
    [("illinois", "cook:law1", "Cook County Law Division"), ("massachusetts", "1753", "Brighton Division")],
)
def test_questions_validate_persist_review_and_edit(client, django_user_model, catalog, jurisdiction, code, name):
    user = django_user_model.objects.create_user(username=f"appeal-{jurisdiction}", tyler_jurisdiction=jurisdiction)
    draft = FilingDraft.objects.create(
        user=user,
        jurisdiction=jurisdiction,
        workflow_version=2,
        existing_case="new",
        court_code="appellate",
        case_category_code="appeal",
        case_type_code="appeal-type",
        selected_payment_account_id="waiver",
        selected_payment_account_type="WV",
    )
    reviewed_document(draft=draft, role="lead")
    client.force_login(user)
    session = client.session
    session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
    session["auth_tokens"] = {f"TYLER-TOKEN-{jurisdiction.upper()}": "test-token"}
    session["jurisdiction"] = jurisdiction
    session.save()
    url = reverse("case_questions", kwargs={"jurisdiction": jurisdiction})
    review = reverse("case_review", kwargs={"jurisdiction": jurisdiction})
    assert client.get(review).url.partition("?")[0] == url
    response = client.get(url)
    assert b'name="lower_court_code"' in response.content
    assert name.encode() in response.content
    data = {
        "lower_court_code": "invalid",
        "lower_court_title": "Example v. Test",
        "lower_court_docket_number": "24-CV-001",
        "lower_court_judge": "Judge Example",
        "return_to": "review",
    }
    response = client.post(url, data)
    assert response.status_code == 200
    assert b"Answer these questions" in response.content
    assert b"Example v. Test" in response.content
    assert b'name="return_to" value="review"' in response.content
    data["lower_court_code"] = code
    assert client.post(url, data).status_code == 302
    draft.refresh_from_db()
    assert read_case_data(draft)["lower_court_code"] == code
    before = fee_fingerprint(draft)
    response = client.get(review)
    assert response.status_code == 200
    assert name.encode() in response.content
    assert b"24-CV-001" in response.content
    assert b"Example v. Test" in response.content
    assert b"Judge Example" in response.content
    data["lower_court_docket_number"] = "24-CV-002"
    client.post(url, data)
    draft.refresh_from_db()
    assert fee_fingerprint(draft) != before
    assert b"24-CV-002" in client.get(review).content
    draft.existing_case = "existing"
    draft.previous_case_id = "existing-case"
    draft.save()
    assert "lower_court_code" not in read_case_data(draft)
    assert client.get(url).status_code == 302
