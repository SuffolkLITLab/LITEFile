"""Known filing times and sourced, jurisdiction-specific timing guidance."""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import holidays

from efile.utils.config_loader import config_loader


def court_filing_timing(jurisdiction, court_code, config=None, *, now=None):
    config = config if config is not None else config_loader.load_jurisdiction_config(jurisdiction) or {}
    settings = dict(config.get("filing_timing") or {})
    court = (config.get("court_specific_requirements") or {}).get(court_code) or {}
    settings = config_loader._deep_merge(settings, court.get("filing_timing") or {})
    try:
        zone = ZoneInfo(settings.get("timezone") or "UTC")
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        zone = ZoneInfo("UTC")
    result = {"timezone": zone.key}
    for key in ("review", "office_hours"):
        item = settings.get(key)
        if not isinstance(item, dict):
            continue
        label, source = str(item.get("label") or "").strip(), str(item.get("source_url") or "").strip()
        if label and urlsplit(source).scheme in {"https", "http"} and urlsplit(source).netloc:
            result[key] = {"label": label, "source_url": source}
    if "review" in result:
        result["review"]["closure_note"] = review_closure_note(settings, zone, now=now)
    return result


def review_closure_note(settings, zone, *, now=None):
    """Explain likely closures near today, without promising a decision date."""
    calendar = settings.get("business_calendar") or {}
    if not calendar or calendar.get("enabled") is False:
        return ""
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date()
    try:
        days = int(calendar.get("review_days", 2))
        if not 1 <= days <= 14:
            return ""
        holiday_calendar = holidays.country_holidays(
            calendar.get("country", "US"),
            subdiv=calendar.get("subdivision"),
            years=[today.year, today.year + 1],
            observed=True,
        )
    except (NotImplementedError, ValueError, TypeError):
        return ""
    excluded = set(calendar.get("excluded_holidays") or [])
    aliases = calendar.get("holiday_names") or {}
    closed_weekdays = set(calendar.get("closed_weekdays", [5, 6]))
    notes = []
    day = today
    remaining = days
    # Include today's closure and the next N business days. Cap the search
    # defensively if a configuration accidentally closes every weekday.
    for _ in range(60):
        if day.weekday() not in closed_weekdays:
            name = holiday_calendar.get(day)
            if name in excluded:
                name = None
            if name:
                name = aliases.get(name, name)
                notes.append(f"{name} may add 1 day.")
            elif day > today:
                remaining -= 1
        if remaining == 0:
            break
        day += timedelta(days=1)
    if closed_weekdays == {5, 6}:
        notes.append("Courts are closed on Saturdays and Sundays.")
    return " ".join(notes)


def display_filing_time(value, zone_name="UTC"):
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    local = value.astimezone(ZoneInfo(zone_name))
    return {
        "iso": value.astimezone(timezone.utc).isoformat(),
        "label": f"{local:%b} {local.day}, {local.year}, {local:%I:%M %p %Z}".replace(", 0", ", "),
    }


def add_tracker_timing(tracker, status_code, *, submitted_at=None, accepted_at=None, status_at=None, timing=None):
    """Attach only source-provided times; a status date describes that status, not earlier stages."""
    timing = timing or {"timezone": "UTC"}
    tracker["timing"] = timing
    stages = tracker["stages"]
    if not stages:
        return tracker
    times = {0: (submitted_at, "Sent")}
    if status_code == "accepted":
        times[3] = (accepted_at or status_at, "Accepted")
    elif status_code in {"rejected", "returned"}:
        times[3] = (status_at, "Returned")
    elif status_code in {"submitted", "receipted"}:
        times[1] = (status_at, "System receipt" if status_code == "submitted" else "Court receipt")
    elif status_code in {"under-review", "reviewed"}:
        times[2] = (status_at, "Review started" if status_code == "under-review" else "Review completed")
    for index, (value, label) in times.items():
        stamp = display_filing_time(value, timing.get("timezone", "UTC"))
        if stamp:
            stages[index]["timestamp"] = stamp
            stages[index]["timestamp_label"] = label
    if timing.get("review") and tracker["state"] == "progress":
        stages[2]["estimate"] = timing["review"]["label"]
        stages[2]["estimate_source_url"] = timing["review"]["source_url"]
    tracker["missing_times"] = any(
        (stage["complete"] or stage["current"]) and not stage.get("timestamp") for stage in stages
    )
    return tracker
