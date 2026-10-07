"""Curated, data-driven case guidance and conservative contextual search facets."""

import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=1)
def guidance_config():
    return yaml.safe_load((Path(__file__).parent.parent / "data/case_type_guidance.yaml").read_text())


@lru_cache(maxsize=256)
def topic_config(jurisdiction, topic, court_name=""):
    data = guidance_config()
    if jurisdiction not in data["jurisdictions"] or topic not in data["topics"]:
        return {}
    config = data["topics"][topic]
    state = config.get("jurisdictions", {}).get(jurisdiction, {})
    county = {}
    for entry in state.get("counties", {}).values():
        if court_name in entry.get("court_names", []) or any(
            court_name.startswith(p) for p in entry.get("court_prefixes", [])
        ):
            county = entry
            break
    court = state.get("courts", {}).get(court_name, {})
    # Local wording overrides the generated synopsis; classification rules stay
    # at the state level so filtering and path descriptions cannot disagree.
    local = {key: value for key, value in {**county, **court}.items() if key in ("text", "source")}
    return {**config, **state, **local, "_local_text": local.get("text", "")}


@lru_cache(maxsize=512)
def matches(pattern, text):
    text = re.sub(r"\b(?:excluding|except)\b[^)]*", "", text, flags=re.I)
    return bool(re.search(pattern, text, re.I))


@lru_cache(maxsize=32768)
def case_topic(jurisdiction, category, case_type):
    # Procedural tracks such as small claims must survive a more specific
    # case label (e.g. a contract claim inside the small-claims category).
    small = topic_config(jurisdiction, "small_claims")
    if small and matches(small["pattern"], f"{category} {case_type}"):
        return "small_claims"
    for text in (case_type, category):
        for key in guidance_config()["topics"]:
            config = topic_config(jurisdiction, key)
            if config and matches(config["pattern"], text):
                return key
    return ""


@lru_cache(maxsize=32768)
def case_guidance(jurisdiction, category, case_type, filing_name="", court_name=""):
    topic = case_topic(jurisdiction, category, case_type)
    if not topic:
        return {}
    config = topic_config(jurisdiction, topic, court_name)
    result = {"topic": topic, "source": config["source"]}
    text = []
    for facet in config["facets"]:
        result[facet["key"]] = "unknown"
        for option in facet["options"]:
            field = option.get("field", "case")
            name = filing_name if field == "filing" else f"{case_type} {filing_name}" if field == "both" else case_type
            if matches(option["pattern"], name):
                result[facet["key"]] = option["value"]
                if option.get("text"):
                    text.append(option["text"])
                break
    for rule in config.get("special", []):
        if matches(rule["pattern"], case_type):
            text.append(rule["text"])
            result["source"] = rule.get("source", result["source"])
            break
    for note in config.get("unknown_notes", []):
        if result.get(note["when"]) == "unknown" and result.get(note["if_known"]) != "unknown":
            text.append(note["text"])
    result["text"] = config.get("_local_text") or " ".join(text) or config["text"]
    return result


OTHER = "other"


def matches_case_filters(guidance, role="", property_kind="", relief="", *, topic="", filters=None):
    choices = filters if filters is not None else {"role": role, "property": property_kind, "relief": relief}
    if topic and guidance.get("topic") != topic:
        return False
    # Amounts are matched against the label (see ``matches_amount``), not guidance.
    choices = {key: value for key, value in choices.items() if key != "amount"}
    if not any(choices.values()):
        return True
    # "other" keeps only the case types none of a facet's options name.
    return bool(guidance) and all(
        not value or guidance.get(key, "unknown") in ((value, "unknown") if value != OTHER else ("unknown",))
        for key, value in choices.items()
    )


# Amounts are integer cents. Parse claim brackets, never arbitrary numbers or
# filing fees. Unrecognized labels remain unclassified and are not excluded.
_MONEY = r"\$?\s*(\d[\d,]*(?:\.\d{1,2})?)\s*([kK]?)"


def _cents(number, suffix):
    return int(Decimal(number.replace(",", "")) * (100000 if suffix else 100))


@lru_cache(maxsize=8192)
def claim_range(name):
    if "$" not in name and not re.search(r"\d,\d{3}", name):
        return None
    if match := re.search(_MONEY + r"\s*(?:to|thru|through|[-–])\s*" + _MONEY, name, re.I):
        low, high = _cents(*match.groups()[:2]), _cents(*match.groups()[2:])
        return (low, high) if low <= high else None
    if match := re.search(r"(?:up to|not over|not exceeding|under|less than|<=|<)\s*" + _MONEY, name, re.I):
        high = _cents(*match.groups())
        exclusive = bool(re.match(r"(?:under|less than|<(?![=]))", match.group(), re.I))
        return 0, high - int(exclusive)
    if match := re.search(_MONEY + r"\s*(?:or less|and under)", name, re.I):
        return 0, _cents(*match.groups())
    if match := re.search(r"(?:over|more than|greater than|>)\s*" + _MONEY, name, re.I):
        return _cents(*match.groups()) + 1, None
    return None


def matches_amount(label, amount):
    if not amount:
        return True
    bounds = claim_range(label["case_type"]) or claim_range(label["category"])
    if bounds is None:
        return True
    low, high = (int(part) if part else None for part in amount.split(":"))
    return (high is None or bounds[0] <= high) and (bounds[1] is None or low <= bounds[1])


def _money(cents):
    return f"${cents / 100:,.2f}".removesuffix(".00")


def amount_options(labels):
    ranges = set()
    small_claims = set()
    for label in labels:
        bounds = claim_range(label["case_type"]) or claim_range(label["category"])
        if bounds is None:
            continue
        ranges.add(bounds)
        if re.search(r"\bsmall claims?\b", f"{label['category']} {label['case_type']}", re.IGNORECASE):
            small_claims.add(bounds)
    if len(ranges) < 2:
        return []
    cuts = sorted({0, *(low for low, _ in ranges), *(high + 1 for _, high in ranges if high is not None)})
    bands = []
    for i, low in enumerate(cuts):
        high = cuts[i + 1] - 1 if i + 1 < len(cuts) else None
        members = frozenset(bounds for bounds in ranges if bounds[0] <= low and (bounds[1] is None or low <= bounds[1]))
        if not members:
            continue
        if bands and bands[-1][2] == members and bands[-1][1] == low - 1:
            bands[-1] = (bands[-1][0], high, members)
        else:
            bands.append((low, high, members))
    # Name a band "small claims" only when it sets small claims apart from
    # the others, as a civil search spanning both does.
    marked = [bool(members & small_claims) for _, _, members in bands]
    return [
        {
            "value": f"{low}:{high if high is not None else ''}",
            "label": (
                f"{_money(low)} or more"
                if high is None
                else f"Up to {_money(high)}"
                if low == 0
                else f"{_money(low)}–{_money(high)}"
            )
            + (" (small claims)" if is_small and not all(marked) else ""),
        }
        for (low, high, _), is_small in zip(bands, marked, strict=True)
    ]


def _valid_amount(value):
    if value == "":
        return True
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,12}:\d{0,12}", value):
        return False
    low, high = value.split(":")
    return not high or int(low) <= int(high)


def validate_case_filters(jurisdiction, topic, choices):
    if not isinstance(choices, dict) or len(choices) > 8:
        raise ValueError("Choose valid case-type filters.")
    if topic in ("", "all"):
        # A claim amount narrows any search; other details belong to a case area.
        if set(choices) - {"amount"} or not _valid_amount(choices.get("amount", "")):
            raise ValueError("Choose a case area before narrowing its details.")
        return
    config = topic_config(jurisdiction, topic)
    if not config:
        raise ValueError("Choose a supported case area.")
    allowed = {
        facet["key"]: {option["value"] for option in facet["options"]} | ({OTHER} if facet.get("other") else set())
        for facet in config["facets"]
    }
    for key, value in choices.items():
        if not isinstance(value, str):
            raise ValueError("Choose valid case-type filters.")
        if key == "amount" and _valid_amount(value):
            continue
        if key not in allowed or value not in allowed[key] | {""}:
            raise ValueError("Choose valid case-type filters.")


def facet_metadata(jurisdiction, query, labels, topic="", choices=None):
    available = {case_topic(jurisdiction, label["category"], label["case_type"]) for label in labels} - {""}
    selected = topic
    if not selected:
        inferred = [key for key in available if matches(topic_config(jurisdiction, key)["query_pattern"], query)]
        selected = inferred[0] if len(inferred) == 1 else next(iter(available)) if len(available) == 1 else ""
    config = topic_config(jurisdiction, selected)
    if config:
        available.add(selected)
    facets = []
    for facet in config.get("facets", []):
        # Keep alternatives visible, but hide dimensions with no known labels.
        known = {
            case_guidance(jurisdiction, label["category"], label["case_type"], label["name"]).get(
                facet["key"], "unknown"
            )
            for label in labels
            if case_topic(jurisdiction, label["category"], label["case_type"]) == selected
        }
        if known - {"unknown"} or (choices or {}).get(facet["key"]):
            facets.append(
                {
                    "key": facet["key"],
                    "label": facet["label"],
                    "options": [{"value": option["value"], "label": option["label"]} for option in facet["options"]]
                    + ([{"value": OTHER, "label": facet["other"]}] if facet.get("other") else []),
                }
            )
    # Claim amounts narrow any search whose case types differ by amount -- a
    # civil complaint search spanning small claims and larger claims, say --
    # not only one already in small claims.
    in_area = selected not in ("", "all")
    applicable = [
        label
        for label in labels
        if (not in_area or case_topic(jurisdiction, label["category"], label["case_type"]) == selected)
        and matches_case_filters(
            case_guidance(jurisdiction, label["category"], label["case_type"], label["name"]), filters=choices or {}
        )
    ]
    options = amount_options(applicable)
    selected_amount = (choices or {}).get("amount")
    if selected_amount and not any(option["value"] == selected_amount for option in options):
        low, high = selected_amount.split(":")
        options.append(
            {
                "value": selected_amount,
                "label": f"{_money(int(low))}–{_money(int(high))}" if high else f"{_money(int(low))} or more",
            }
        )
    small_claims = selected == "small_claims"
    limit = config.get("usual_limit_cents") if small_claims else None
    if limit:
        for option in options:
            low, high = option["value"].split(":")
            if int(low) > limit or not high or int(high) > limit:
                option["label"] += " (check small-claims limit)"
    if options or selected_amount:
        facets.append(
            {
                "key": "amount",
                "label": "How much are you asking for?",
                "options": options,
                "help": config.get("amount_help", "") if small_claims else "",
                "source": config["source"] if small_claims else "",
            }
        )
    return {
        "case_topics": [{"value": key, "label": topic_config(jurisdiction, key)["label"]} for key in sorted(available)],
        "case_topic": selected,
        "case_facets": facets,
    }
