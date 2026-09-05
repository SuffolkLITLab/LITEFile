"""The guided court question, per jurisdiction.

The court lists here are trimmed copies of what the e-filing service returns,
kept small enough to read but keeping the shapes that matter: Cook County's
divisions, a county with one court, Vermont's units, and the Massachusetts
departments whose names have nothing in common.
"""

import json
from unittest.mock import Mock, patch

import pytest

from efile.services.court_location import normalize_court_code, parse_place
from efile.services.court_selection import (
    _readable_name,
    build_selection,
    derive_answers,
    derive_answers_from_guess,
    fetch_courts,
    is_non_filing_court,
    selector_config,
)

ILLINOIS_COURTS = [
    {"value": "TSUPCRT", "text": "Supreme Court of Illinois"},
    {"value": "cook:cvd1", "text": "Cook County - Municipal Civil - District 1 - Chicago"},
    {"value": "cook:cvd2", "text": "Cook County - Municipal Civil - District 2 - Skokie"},
    {"value": "TAC1", "text": "Appellate Court – 1st District"},
    {"value": "TAC3", "text": "Appellate Court – 3rd District"},
    {"value": "ardc", "text": "ARDC Clerk's Office"},
    {"value": "cook", "text": "Cook County"},
    {"value": "cook:chd1", "text": "Cook County - Chancery - District 1 - Chicago"},
    {"value": "cook:law1", "text": "Cook County - Law - District 1 - Chicago"},
    {"value": "KankakeeCV", "text": "Kankakee - Civil"},
    {"value": "KankakeeCR", "text": "Kankakee - Criminal"},
    {"value": "peoria", "text": "Peoria County"},
    {"value": "peoriacr", "text": "Peoria CR"},
    {"value": "peoriatr", "text": "Peoria TR"},
    {"value": "will", "text": "Will County"},
]

VERMONT_COURTS = [
    {"value": "sc:addison", "text": "Addison Unit"},
    {"value": "sc:chittendon", "text": "Chittenden Unit"},
    {"value": "sc:rutland", "text": "Rutland Unit"},
    {"value": "vermont:ed", "text": "Environmental Division"},
    {"value": "vermont:jb", "text": "Judicial Bureau"},
    {"value": "vermont:supreme", "text": "Supreme Court"},
]

# As the questions see them: the e-filing service's own names, put back the way
# a court is named, by the `court_names` rules in the Massachusetts config.
MASSACHUSETTS_COURTS = [
    {"value": "appeals:acp", "text": "Appeals Court - Panel (P docket)"},
    {"value": "appeals:acsj", "text": "Appeals Court - Single Justice (J Docket)"},
    {"value": "1245", "text": "Central Division, Boston Municipal Court"},
    {"value": "490", "text": "Cambridge District Court"},
    {"value": "504", "text": "Somerville District Court"},
    {"value": "537", "text": "Eastern Housing Court (Boston)"},
    {"value": "hc", "text": "Housing Courts"},
    {"value": "1086:BO", "text": "Boston Juvenile Court - Suffolk County"},
    {"value": "210", "text": "Land Court"},
    {"value": "344", "text": "Middlesex Probate and Family Court"},
    {"value": "sjc", "text": "Supreme Judicial Court - Commonwealth"},
]


def select(jurisdiction, answers, courts):
    """build_selection, for the jurisdictions that have a selector configured."""
    selection = build_selection(jurisdiction, answers, courts)
    assert selection is not None
    return selection


def step(selection, step_id):
    return next((item for item in selection["steps"] if item["id"] == step_id), None)


def values(selection, step_id):
    return [option["value"] for option in step(selection, step_id)["options"]]


class TestCourtListFiltering:
    @pytest.mark.parametrize(
        "name",
        ["Courtview Test - Trial Courts", "ZZZ - Essex Probate and Family Court", "System", "File & Serve"],
    )
    def test_rows_that_are_not_courts_are_dropped(self, name):
        assert is_non_filing_court(name)

    def test_real_courts_are_kept(self):
        assert not is_non_filing_court("District Court - Cambridge")
        assert not is_non_filing_court("Cook County - Chancery - District 1 - Chicago")


class TestIllinois:
    def test_the_first_question_is_the_court_level(self):
        selection = select("illinois", {}, ILLINOIS_COURTS)
        assert values(selection, "level") == ["circuit", "appellate", "supreme"]
        assert selection["selected"] is None

    def test_the_supreme_court_needs_no_geography(self):
        selection = select("illinois", {"level": "supreme"}, ILLINOIS_COURTS)
        assert selection["selected"]["value"] == "TSUPCRT"
        assert selection["complete"]

    def test_counties_are_one_option_each_however_their_courts_are_named(self):
        selection = select("illinois", {"level": "circuit"}, ILLINOIS_COURTS)
        # Kankakee's four courts and Peoria's two are one county option each,
        # and the appellate and administrative courts are not counties at all.
        assert values(selection, "county") == ["Cook", "Kankakee", "Peoria", "Will"]

    def test_a_county_with_one_court_is_not_asked_a_second_question(self):
        selection = select("illinois", {"level": "circuit", "county": "Will"}, ILLINOIS_COURTS)
        assert step(selection, "division") is None
        assert selection["selected"]["value"] == "will"

    def test_cook_county_is_asked_which_division(self):
        selection = select("illinois", {"level": "circuit", "county": "Cook"}, ILLINOIS_COURTS)
        assert selection["selected"] is None
        # Every Cook location, grouped by the courthouse it sits in.
        assert set(values(selection, "division")) == {"cook:chd1", "cook", "cook:law1", "cook:cvd1", "cook:cvd2"}
        # The county prefix every option shares is not worth reading twice.
        labels = [option["label"] for option in step(selection, "division")["options"]]
        assert not any(label.startswith("Cook County -") for label in labels)

    def test_cook_countys_courts_read_under_their_courthouse(self):
        selection = select("illinois", {"level": "circuit", "county": "Cook"}, ILLINOIS_COURTS)
        options = step(selection, "division")["options"]
        headings = [option["group"] for option in options]
        # The Chicago courthouse comes first, where most Cook filings go, and
        # the outlying districts follow in their own order rather than
        # alphabetically. Courts with no courthouse in their name come last.
        assert headings[0] == "District 1 - Chicago"
        assert headings.index("District 2 - Skokie") > headings.index("District 1 - Chicago")
        assert headings[-1] == "No courthouse given"
        under_chicago = {option["label"] for option in options if option["group"] == "District 1 - Chicago"}
        assert {"Chancery", "Law", "Municipal Civil"} <= under_chicago
        # The courthouse is the heading, so it is not repeated on every line --
        # but away from that heading the court still needs its whole name.
        chosen = next(option for option in options if option["value"] == "cook:cvd2")
        assert chosen["label"] == "Municipal Civil"
        assert chosen["full_label"] == "Municipal Civil - District 2 - Skokie"

    def test_a_cook_division_resolves_to_one_court(self):
        selection = select("illinois", {"level": "circuit", "county": "Cook", "division": "cook:law1"}, ILLINOIS_COURTS)
        assert selection["selected"]["value"] == "cook:law1"
        assert selection["complete"]

    def test_an_appeal_can_be_identified_by_district_or_by_county(self):
        selection = select("illinois", {"level": "appellate"}, ILLINOIS_COURTS)
        # Both ways are offered at once; the filer uses whichever their
        # paperwork supports.
        assert step(selection, "appellate_district") is not None
        assert step(selection, "appellate_county") is not None

    def test_the_county_an_appeal_came_from_names_its_district(self):
        selection = select("illinois", {"level": "appellate", "appellate_county": "DuPage"}, ILLINOIS_COURTS)
        assert selection["selected"]["value"] == "TAC3"
        # Both ways stay on screen, but only the one that was answered answers.
        assert step(selection, "appellate_district")["answer"] == ""

    def test_choosing_the_district_directly_answers_for_the_county_question(self):
        selection = select(
            "illinois",
            {"level": "appellate", "appellate_district": "TAC1", "appellate_county": "Cook"},
            ILLINOIS_COURTS,
        )
        assert selection["selected"]["value"] == "TAC1"
        assert step(selection, "appellate_county")["answer"] == ""


class TestVermont:
    def test_units_are_labelled_with_the_county_they_cover(self):
        selection = select("vermont", {"level": "superior", "division": "family"}, VERMONT_COURTS)
        labels = [option["label"] for option in step(selection, "unit")["options"]]
        assert labels == [
            "Addison Unit (Addison County)",
            "Chittenden Unit (Chittenden County)",
            "Rutland Unit (Rutland County)",
        ]

    def test_a_statewide_division_is_not_asked_for_a_unit(self):
        selection = select("vermont", {"level": "superior", "division": "environmental"}, VERMONT_COURTS)
        assert step(selection, "unit") is None
        assert selection["selected"]["value"] == "vermont:ed"

    def test_a_unit_resolves_to_one_court(self):
        selection = select("vermont", {"level": "superior", "division": "civil", "unit": "sc:rutland"}, VERMONT_COURTS)
        assert selection["selected"]["value"] == "sc:rutland"

    def test_a_town_finds_the_unit_the_filer_may_not_know(self):
        selection = select(
            "vermont",
            {"level": "superior", "division": "family", "place": "Burlington"},
            VERMONT_COURTS,
        )
        # Vermont's own code for the Chittenden Unit carries a spelling its name
        # does not, so the match is made on the name.
        assert selection["selected"]["value"] == "sc:chittendon"
        assert selection["location"]["matched"][0]["reason"]

    def test_a_cross_county_zip_offers_both_units_rather_than_guessing(self):
        selection = select(
            "vermont",
            {"level": "superior", "division": "family", "place": "05487"},
            VERMONT_COURTS,
        )
        assert [court["value"] for court in selection["location"]["matched"]] == ["sc:addison", "sc:chittendon"]
        assert selection["selected"] is None

    def test_choosing_a_unit_leaves_the_lookup_on_screen_and_unused(self):
        selection = select(
            "vermont",
            {"level": "superior", "division": "family", "unit": "sc:rutland", "place": "Burlington"},
            VERMONT_COURTS,
        )
        assert selection["selected"]["value"] == "sc:rutland"
        assert step(selection, "place")["answer"] == ""

    def test_the_judicial_bureau_needs_no_geography(self):
        selection = select("vermont", {"level": "bureau"}, VERMONT_COURTS)
        assert selection["selected"]["value"] == "vermont:jb"


class TestMassachusetts:
    def test_the_land_court_never_asks_where(self):
        selection = select("massachusetts", {"level": "trial", "department": "land"}, MASSACHUSETTS_COURTS)
        assert step(selection, "place") is None
        assert selection["selected"]["value"] == "210"

    def test_a_department_is_asked_for_a_place_not_a_county(self):
        selection = select("massachusetts", {"level": "trial", "department": "district"}, MASSACHUSETTS_COURTS)
        place = step(selection, "place")
        assert place["type"] == "location"
        assert "county" not in place["label"].lower()

    def test_a_town_resolves_to_the_court_that_serves_it(self):
        selection = select(
            "massachusetts",
            {"level": "trial", "department": "district", "place": "Cambridge"},
            MASSACHUSETTS_COURTS,
        )
        assert selection["selected"]["value"] == "490"
        assert selection["location"]["matched"][0]["reason"]

    def test_a_town_is_matched_within_the_chosen_department(self):
        selection = select(
            "massachusetts",
            {"level": "trial", "department": "housing", "place": "Somerville"},
            MASSACHUSETTS_COURTS,
        )
        assert selection["selected"]["value"] == "537"

    def test_a_place_that_cannot_be_matched_leaves_the_list(self):
        selection = select(
            "massachusetts",
            {"level": "trial", "department": "district", "place": "Nowhere At All"},
            MASSACHUSETTS_COURTS,
        )
        assert selection["location"]["searched"] is True
        assert selection["location"]["matched"] == []
        # The department's own courts are still there to choose from by hand.
        assert {court["value"] for court in selection["courts"]} == {"1245", "490", "504"}
        assert selection["selected"] is None

    def test_a_court_can_be_chosen_by_hand_without_a_place(self):
        selection = select(
            "massachusetts",
            {"level": "trial", "department": "district", "court": "504"},
            MASSACHUSETTS_COURTS,
        )
        assert selection["selected"]["value"] == "504"
        assert selection["complete"]

    def test_a_court_outside_the_answers_is_not_the_selection(self):
        selection = select(
            "massachusetts",
            {"level": "trial", "department": "district", "court": "210"},
            MASSACHUSETTS_COURTS,
        )
        assert selection["selected"] is None

    def test_the_appeals_court_asks_which_proceeding_and_no_geography(self):
        selection = select("massachusetts", {"level": "appeals", "proceeding": "single_justice"}, MASSACHUSETTS_COURTS)
        assert selection["selected"]["value"] == "appeals:acsj"
        assert step(selection, "place") is None


class TestDerivingAnswersFromASavedCourt:
    @pytest.mark.parametrize(
        ("jurisdiction", "courts", "code", "expected"),
        [
            ("illinois", ILLINOIS_COURTS, "cook:law1", {"level": "circuit", "county": "Cook", "division": "cook:law1"}),
            ("illinois", ILLINOIS_COURTS, "will", {"level": "circuit", "county": "Will"}),
            ("vermont", VERMONT_COURTS, "sc:rutland", {"level": "superior", "unit": "sc:rutland"}),
            ("massachusetts", MASSACHUSETTS_COURTS, "490", {"level": "trial", "department": "district"}),
            ("massachusetts", MASSACHUSETTS_COURTS, "210", {"level": "trial", "department": "land"}),
        ],
    )
    def test_a_saved_court_fills_the_questions_back_in(self, jurisdiction, courts, code, expected):
        assert derive_answers(jurisdiction, code, courts) == expected

    def test_a_court_that_is_not_on_the_list_derives_nothing(self):
        assert derive_answers("illinois", "not-a-court", ILLINOIS_COURTS) == {}


class TestPlaceParsing:
    @pytest.mark.parametrize(
        ("typed", "expected"),
        [
            ("Cambridge", {"street_address": "", "city": "Cambridge", "postal_code": ""}),
            ("Boston 02108", {"street_address": "", "city": "Boston", "postal_code": "02108"}),
            ("24 Beacon St, Boston", {"street_address": "24 Beacon St", "city": "Boston", "postal_code": ""}),
            ("Somerville, MA", {"street_address": "", "city": "Somerville", "postal_code": ""}),
            ("02108", {"street_address": "", "city": "", "postal_code": "02108"}),
        ],
    )
    def test_a_typed_place_is_read_into_the_fields_a_lookup_uses(self, typed, expected):
        assert parse_place(typed) == expected

    def test_court_codes_compare_past_padding_and_case(self):
        # Tyler writes the same Juvenile Court session both ways.
        assert normalize_court_code("0965:BE") == normalize_court_code("965:be")
        assert normalize_court_code("490") != normalize_court_code("491")


@pytest.mark.django_db
class TestCourtSelectorEndpoint:
    def test_it_returns_the_first_question(self, client):
        with patch("efile.api.court_selector_views.fetch_courts", return_value=ILLINOIS_COURTS):
            response = client.get("/api/dropdowns/court-selector/", {"jurisdiction": "illinois"})
        data = json.loads(response.content)["data"]
        assert data["available"] is True
        assert data["steps"][0]["id"] == "level"

    def test_it_answers_the_questions_it_is_given(self):
        query = {"jurisdiction": "illinois", "answers": json.dumps({"level": "circuit", "county": "Will"})}
        with patch("efile.api.court_selector_views.fetch_courts", return_value=ILLINOIS_COURTS):
            response = client_get(query)
        assert response["selected"]["value"] == "will"

    def test_a_saved_court_comes_back_with_its_questions_answered(self):
        query = {"jurisdiction": "illinois", "court": "cook:chd1"}
        with patch("efile.api.court_selector_views.fetch_courts", return_value=ILLINOIS_COURTS):
            response = client_get(query)
        assert response["selected"]["value"] == "cook:chd1"
        assert [item["answer"] for item in response["steps"]] == ["circuit", "Cook", "cook:chd1"]

    def test_a_jurisdiction_with_no_configured_questions_says_so(self, client):
        with patch("efile.api.court_selector_views.fetch_courts", return_value=[]):
            response = client.get("/api/dropdowns/court-selector/", {"jurisdiction": "atlantis"})
        assert json.loads(response.content)["data"] == {"available": False}

    def test_a_court_list_that_will_not_load_is_reported(self, client):
        import requests

        with patch("efile.api.court_selector_views.fetch_courts", side_effect=requests.RequestException("down")):
            response = client.get("/api/dropdowns/court-selector/", {"jurisdiction": "illinois"})
        assert response.status_code == 400
        assert json.loads(response.content)["success"] is False


def client_get(query):
    from django.test import Client

    response = Client().get("/api/dropdowns/court-selector/", query)
    return json.loads(response.content)["data"]


class TestFetchingTheCourtList:
    @staticmethod
    def _fetch(all_courts, fileable):
        """fetch_courts against a stubbed pair of court lists."""

        def response(url, params=None, **kwargs):
            listing = fileable if (params or {}).get("fileable_only") else all_courts
            stub = Mock()
            stub.json.return_value = listing
            stub.raise_for_status.return_value = None
            return stub

        with (
            patch("efile.services.court_selection.requests.get", side_effect=response),
            patch("efile.services.court_selection.cache") as cache,
        ):
            cache.get.return_value = None
            return fetch_courts("illinois")

    def test_rows_that_are_not_courts_never_reach_the_questions(self):
        payload = [
            {"code": "will", "name": "Will County"},
            {"code": "0", "name": "System"},
            {"code": "9418", "name": "Courtview Test - BMC - Brighton"},
        ]
        assert self._fetch(payload, payload) == [{"value": "will", "text": "Will County"}]

    def test_a_county_that_only_heads_its_divisions_is_not_offered(self):
        payload = [
            {"code": "cook", "name": "Cook County"},
            {"code": "cook:chd", "name": "Cook County - Chancery"},
            {"code": "cook:cvd1", "name": "Cook County - Municipal Civil - District 1 - Chicago"},
            {"code": "will", "name": "Will County"},
        ]
        # The e-filing service leaves both Cook rows out of its fileable list,
        # but only the county is a dead end: Chancery has locations under it and
        # takes filings of its own, so the flag alone is not enough to drop it.
        courts = self._fetch(payload, [{"code": "cook:cvd1"}, {"code": "will"}])
        assert [court["value"] for court in courts] == ["cook:chd", "cook:cvd1", "will"]

    def test_nothing_is_dropped_when_the_fileable_list_cannot_be_read(self):
        payload = [
            {"code": "cook", "name": "Cook County"},
            {"code": "cook:cvd1", "name": "Cook County - Municipal Civil - District 1 - Chicago"},
        ]
        with (
            patch("efile.services.court_selection.requests.get") as get,
            patch("efile.services.court_selection.cache") as cache,
        ):
            cache.get.return_value = None
            get.return_value.json.side_effect = [payload, ValueError("not json")]
            get.return_value.raise_for_status.return_value = None
            assert len(fetch_courts("illinois")) == 2


@pytest.mark.django_db
class TestTheScreensThatAskForACourt:
    """The selector draws itself over the court <select> already on the page."""

    @pytest.fixture
    def draft(self, client, django_user_model):
        from efile.models import FilingDocument, FilingDraft
        from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY

        user = django_user_model.objects.create_user(username="court-user", tyler_jurisdiction="illinois")
        draft = FilingDraft.objects.create(user=user, jurisdiction="illinois", workflow_version=2)
        FilingDocument.objects.create(draft=draft, role=FilingDocument.Role.LEAD, name="petition.pdf")
        client.force_login(user)
        session = client.session
        session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
        session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "token"}
        session["jurisdiction"] = "illinois"
        session.save()
        return draft

    @pytest.mark.parametrize("view", ["extraction_review", "case_lookup"])
    def test_the_court_field_carries_the_selector(self, client, draft, view):
        from django.urls import reverse

        if view == "case_lookup":
            draft.existing_case = "existing"
            draft.save()
        content = client.get(reverse(view, kwargs={"jurisdiction": "illinois"})).content.decode()
        assert 'id="court-selector"' in content
        assert "js/court-selector.js" in content


class TestWhatTheDocumentAlreadySaid:
    """A caption names a court in its own words. Whatever those words settle is
    filled in; whatever they leave open stays a question."""

    def test_a_caption_that_names_the_county_answers_the_county(self):
        answers = derive_answers_from_guess(
            "illinois", "IN THE CIRCUIT COURT OF COOK COUNTY, ILLINOIS", ILLINOIS_COURTS
        )
        assert answers == {"level": "circuit", "county": "Cook"}

    def test_it_does_not_choose_a_division_the_document_never_named(self):
        answers = derive_answers_from_guess("illinois", "Circuit Court of Cook County", ILLINOIS_COURTS)
        assert "division" not in answers
        assert "court" not in answers

    def test_a_caption_that_names_one_court_settles_it(self):
        answers = derive_answers_from_guess("illinois", "Will County Circuit Court", ILLINOIS_COURTS)
        assert answers["court"] == "will"

    def test_a_court_named_in_another_order_still_matches(self):
        answers = derive_answers_from_guess("massachusetts", "Cambridge District Court", MASSACHUSETTS_COURTS)
        assert answers["court"] == "490"

    def test_words_the_courts_do_not_share_settle_nothing(self):
        assert derive_answers_from_guess("illinois", "Superior Court of California", ILLINOIS_COURTS) == {}

    def test_the_document_only_fills_in_what_is_still_unanswered(self, client):
        query = {"jurisdiction": "illinois", "guessed_court": "Circuit Court of Cook County"}
        with patch("efile.api.court_selector_views.fetch_courts", return_value=ILLINOIS_COURTS):
            data = json.loads(client.get("/api/dropdowns/court-selector/", query).content)["data"]
        answered = {item["id"]: (item["answer"], item["from_document"]) for item in data["steps"]}
        assert answered["level"] == ("circuit", True)
        assert answered["county"] == ("Cook", True)
        # The division is still the filer's to answer, and is not labelled as
        # something the document said.
        assert answered["division"] == ("", False)

    def test_a_saved_court_wins_over_the_document(self, client):
        query = {
            "jurisdiction": "illinois",
            "court": "cook:chd1",
            "guessed_court": "Circuit Court of Cook County",
        }
        with patch("efile.api.court_selector_views.fetch_courts", return_value=ILLINOIS_COURTS):
            data = json.loads(client.get("/api/dropdowns/court-selector/", query).content)["data"]
        assert data["selected"]["value"] == "cook:chd1"
        assert not any(item["from_document"] for item in data["steps"])


class TestWhereACountyHasNoCourtOfItsOwn:
    """Cook County is a heading over eighty locations, not a court."""

    def test_a_caption_naming_only_the_county_still_finds_it(self):
        # The county's own row is not in the list, because it takes no filings.
        courts = [court for court in ILLINOIS_COURTS if court["value"] != "cook"]
        answers = derive_answers_from_guess("illinois", "IN THE CIRCUIT COURT OF COOK COUNTY", courts)
        assert answers["level"] == "circuit"
        assert answers["county"] == "Cook"

    def test_the_county_starts_at_the_division_most_filings_go_to(self):
        courts = [court for court in ILLINOIS_COURTS if court["value"] != "cook"] + [
            {"value": "cook:cvd", "text": "Cook County - Municipal Civil"}
        ]
        selection = select("illinois", {"level": "circuit", "county": "Cook"}, courts)
        division = step(selection, "division")
        assert division["answer"] == "cook:cvd"
        # Suggested, not chosen: the question stays on screen saying so.
        assert division["defaulted"] is True
        assert division["default_hint"]
        assert selection["selected"]["value"] == "cook:cvd"

    def test_a_division_the_filer_chose_is_not_marked_as_a_suggestion(self):
        selection = select("illinois", {"level": "circuit", "county": "Cook", "division": "cook:law1"}, ILLINOIS_COURTS)
        assert step(selection, "division")["defaulted"] is False

    def test_a_county_with_no_default_is_left_to_the_filer(self):
        selection = select("illinois", {"level": "circuit", "county": "Peoria"}, ILLINOIS_COURTS)
        assert step(selection, "division")["answer"] == ""
        assert selection["selected"] is None


class TestHowCourtsAreNamed:
    """The service names courts so they sort. Nobody calls them that."""

    @pytest.mark.parametrize(
        ("listed", "called"),
        [
            ("Juvenile Court -- Suffolk County -- Boston", "Boston Juvenile Court - Suffolk County"),
            ("District Court - Cambridge", "Cambridge District Court"),
            ("BMC -  Charlestown", "Charlestown Division, Boston Municipal Court"),
            ("Superior Court - Bristol", "Bristol Superior Court"),
            ("Housing - Eastern (Boston)", "Eastern Housing Court (Boston)"),
            ("Housing - Northeast", "Northeast Housing Court"),
            # Already the right way round, and left alone.
            ("Middlesex Probate and Family Court", "Middlesex Probate and Family Court"),
            ("Southeast Housing Court - Brockton", "Southeast Housing Court - Brockton"),
            ("Land Court", "Land Court"),
        ],
    )
    def test_massachusetts_courts_read_as_they_are_named(self, listed, called):
        config = selector_config("massachusetts")
        assert config is not None
        rules = config["court_names"]
        assert _readable_name(listed, rules) == called

    def test_a_jurisdiction_with_no_rules_keeps_every_name(self):
        assert (selector_config("vermont") or {}).get("court_names") is None
        assert _readable_name("Addison Unit", []) == "Addison Unit"

    def test_the_renamed_court_is_what_the_filer_picks_and_what_is_saved(self):
        selection = select(
            "massachusetts",
            {"level": "trial", "department": "juvenile", "court": "1086:BO"},
            MASSACHUSETTS_COURTS,
        )
        assert selection["selected"]["text"] == "Boston Juvenile Court - Suffolk County"
