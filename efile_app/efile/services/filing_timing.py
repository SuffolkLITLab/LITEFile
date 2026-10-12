"""Known filing times and sourced, jurisdiction-specific timing guidance."""

from datetime import datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from efile.utils.config_loader import config_loader


def court_filing_timing(jurisdiction, court_code, config=None):
    config = config if config is not None else config_loader.load_jurisdiction_config(jurisdiction) or {}
    settings = dict(config.get("filing_timing") or {})
    court = (config.get("court_specific_requirements") or {}).get(court_code) or {}
    settings.update(court.get("filing_timing") or {})
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
    return result


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
    tracker["missing_times"] = any(
        (stage["complete"] or stage["current"]) and not stage.get("timestamp") for stage in stages
    )
    return tracker
