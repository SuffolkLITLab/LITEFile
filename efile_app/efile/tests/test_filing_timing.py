from copy import deepcopy
from datetime import datetime, timezone

import pytest

from efile.services.filing_timing import court_filing_timing, display_filing_time
from efile.services.filings import describe_filing_detail, filing_tracker
from efile.tests.test_filing_history import accepted_detail


def test_tracker_only_assigns_timestamps_to_the_events_the_court_reported():
    sent = datetime(2026, 10, 12, 14, 15, tzinfo=timezone.utc)
    updated = datetime(2026, 10, 13, 15, 30, tzinfo=timezone.utc)
    tracker = filing_tracker(
        "under-review", submitted_at=sent, status_at=updated, timing={"timezone": "America/Chicago"}
    )
    assert tracker["stages"][0]["timestamp"]["label"] == "Oct 12, 2026, 9:15 AM CDT"
    assert tracker["stages"][2]["timestamp"]["label"] == "Oct 13, 2026, 10:30 AM CDT"
    assert tracker["stages"][2]["timestamp_label"] == "Review started"
    assert "timestamp" not in tracker["stages"][1]
    assert "timestamp" not in tracker["stages"][3]
    assert tracker["missing_times"] is True


@pytest.mark.parametrize(
    ("code", "index", "label"),
    [
        ("submitted", 1, "System receipt"),
        ("receipted", 1, "Court receipt"),
        ("reviewed", 2, "Review completed"),
        ("rejected", 3, "Returned"),
        ("accepted", 3, "Accepted"),
    ],
)
def test_status_timestamp_is_not_mistaken_for_an_earlier_stage(code, index, label):
    tracker = filing_tracker(code, status_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert tracker["stages"][index]["timestamp_label"] == label
    assert sum("timestamp" in stage for stage in tracker["stages"]) == 1


def test_detail_uses_submission_acceptance_and_current_status_dates():
    payload = accepted_detail()
    detail = describe_filing_detail(payload, timing={"timezone": "America/Chicago"})
    assert detail is not None
    tracker = detail["tracker"]
    assert tracker["stages"][0]["timestamp"]["iso"]
    assert tracker["stages"][3]["timestamp"]["iso"]
    assert "timestamp" not in tracker["stages"][1]
    assert "timestamp" not in tracker["stages"][2]
    payload["filingStatus"]["filingStatusCode"] = "under-review"
    payload["filingStatus"]["statusDate"] = deepcopy(payload["filingAcceptDate"])
    detail = describe_filing_detail(payload)
    assert detail is not None
    tracker = detail["tracker"]
    assert tracker["stages"][2]["timestamp"]["iso"]
    assert "timestamp" not in tracker["stages"][3]
    payload["filingSubmissionDate"]["dateRepresentation"]["name"] = "{http://niem.gov/niem/niem-core/2.0}Date"
    detail = describe_filing_detail(payload)
    assert detail is not None
    assert "timestamp" not in detail["tracker"]["stages"][0]


def test_time_zone_respects_daylight_saving_and_does_not_guess_naive_times():
    winter = display_filing_time(datetime(2026, 1, 2, 16, tzinfo=timezone.utc), "America/Chicago")
    assert winter["label"] == "Jan 2, 2026, 10:00 AM CST"
    assert display_filing_time(datetime(2026, 1, 2)) is None


def test_sourced_court_hours_and_jurisdiction_range_are_shared_without_leaking_between_states():
    adams = court_filing_timing("illinois", "adams")
    assert adams["review"]["label"] == "1–2 days"
    assert "8:15 a.m." in adams["office_hours"]["label"]
    other = court_filing_timing("illinois", "unknown")
    assert "office_hours" not in other
    for state in ["massachusetts", "vermont"]:
        timing = court_filing_timing(state, "unknown")
        assert timing["timezone"] == "America/New_York"
        assert "review" not in timing and "office_hours" not in timing
    assert filing_tracker("accepted", timing=adams)["stages"][2].get("estimate") is None


def test_court_overrides_and_missing_sources():
    config = {
        "filing_timing": {"timezone": "invalid", "review": {"label": "1–2 business days"}},
        "court_specific_requirements": {
            "test": {
                "filing_timing": {
                    "review": {"label": "2–3 business days", "source_url": "https://court.example/timing"}
                }
            }
        },
    }
    assert court_filing_timing("", "", config) == {"timezone": "UTC"}
    timing = court_filing_timing("", "test", config)
    assert timing["review"]["label"] == "2–3 business days"
    assert filing_tracker("submitted", timing=timing)["stages"][2]["estimate"] == "2–3 business days"


@pytest.mark.parametrize(
    ("instant", "holiday", "absent"),
    [
        ("2026-10-12T14:00:00+00:00", "Indigenous Peoples’ Day / Columbus Day", "Veterans Day"),
        ("2026-10-09T14:00:00+00:00", "Indigenous Peoples’ Day / Columbus Day", "Veterans Day"),
        ("2026-10-14T14:00:00+00:00", None, "Columbus Day"),
        ("2026-07-02T14:00:00+00:00", "Independence Day (observed)", "Columbus Day"),
        ("2026-12-31T14:00:00+00:00", "New Year's Day", "Columbus Day"),
        # Still Oct 12 in Chicago, although already Oct 13 in UTC.
        ("2026-10-13T01:00:00+00:00", "Indigenous Peoples’ Day / Columbus Day", "Veterans Day"),
    ],
)
def test_upcoming_closures_use_local_date_observed_holidays_and_year_rollover(instant, holiday, absent):
    timing = court_filing_timing("illinois", "adams", now=datetime.fromisoformat(instant))
    note = timing["review"]["closure_note"]
    assert "Courts are closed on Saturdays and Sundays." in note
    assert absent not in note
    if holiday:
        assert f"{holiday} may add 1 day." in note
    else:
        assert "may add" not in note


def test_holiday_guidance_requires_configured_calendar():
    config = {"filing_timing": {"review": {"label": "1–2 days", "source_url": "https://example.test"}}}
    assert court_filing_timing("", "", config)["review"]["closure_note"] == ""


@pytest.mark.parametrize("year,day", [(2026, 2), (2027, 1), (2028, 6)])
@pytest.mark.parametrize(
    "court", ["cook:cd1", "cook:dr1", "cook:cvd1", "cook:dr2", "cook:crcbc", "cook:jd", "cook:jjcp", "cook:jjcpd6"]
)
def test_pulaski_day_is_cook_specific_and_follows_first_monday(year, day, court):
    now = datetime(year, 3, day, 15, tzinfo=timezone.utc)
    assert (
        "Casimir Pulaski Day may add 1 day."
        in court_filing_timing("illinois", court, now=now)["review"]["closure_note"]
    )
    for other in ("adams", "unknown", "pulaski"):
        assert "Pulaski" not in court_filing_timing("illinois", other, now=now)["review"]["closure_note"]


def test_pulaski_day_is_visible_from_previous_friday_but_not_tuesday():
    friday = datetime(2026, 2, 27, 15, tzinfo=timezone.utc)
    tuesday = datetime(2026, 3, 3, 15, tzinfo=timezone.utc)
    assert "Pulaski" in court_filing_timing("illinois", "cook:cd1", now=friday)["review"]["closure_note"]
    assert "Pulaski" not in court_filing_timing("illinois", "cook:cd1", now=tuesday)["review"]["closure_note"]
