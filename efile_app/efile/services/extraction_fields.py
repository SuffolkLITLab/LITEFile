"""The complete, reviewable set of details requested from a lead document."""

COMMON_EXTRACTION_FIELDS: dict[str, str] = {
    "document title": "The title printed on the document, such as Complaint, Motion, or Affidavit",
    "court name": "The court, court unit, county, or venue shown on the document",
    "filing type": "The formal title of the filing being made",
    "case category": "The high-level court category or division for this case",
    "case type": "The more specific type of legal case this document is part of",
    "docket number": "The court's docket or case number, if one is shown",
    "case title": "The full case caption or title, if one is shown",
    "plaintiff or petitioner names": "All plaintiff or petitioner names, in document order, separated by semicolons",
    "defendant or respondent names": "All defendant or respondent names, in document order, separated by semicolons",
    "other party names": "Any other named parties and their stated roles, separated by semicolons",
    "document date": "The date the document was signed, issued, or filed, including the label that identifies the date",
}

EXTRACTION_FIELDS: dict[str, dict[str, str]] = {
    jurisdiction: dict(COMMON_EXTRACTION_FIELDS) for jurisdiction in ("illinois", "massachusetts", "vermont", "default")
}

EXTRACTION_HINTS = {
    "illinois": """
Use these Illinois categories as clues when they apply:

* Chancery (CH): specific performance, injunctions, and mechanics lien foreclosure
* Criminal Felony (CF) or Criminal: petitions to expunge or seal
* Dissolution with Children (DC) or without Children (DN): divorce
* Eviction (EV): may also be called forcible entry and detainer, residential, commercial, or ejectment
* Family (FA): parentage, visitation, or custody
* Guardianship (GR): guardianship of a minor or person with a disability
* Law Magistrate (LM): contract, tort, and other money claims over $10,000 through $50,000
* Miscellaneous Criminal (MX): expungement or sealing of arrests and civil asset forfeiture
* Miscellaneous Remedy (MR): administrative review, certiorari, or change of name
* Order of Protection (OP): order of protection, stalking no contact, civil no contact, or firearms restraining
* Probate (PR): administration of a decedent's estate
* Small Claims (SC): contract and tort claims of $10,000 or less
""",
    "massachusetts": "Always attempt to deduce the case category and case type.",
    "vermont": "Treat the court division as the case category. Always attempt to deduce the case category and type.",
    "default": "Always attempt to deduce the case category and case type.",
}

EXTRACTION_LABELS = {
    "document title": "Document title",
    "court": "Court or county",
    "filing type": "Filing type",
    "case category": "Case category",
    "case type": "Case type",
    "docket number": "Case number",
    "case title": "Case title",
    "plaintiff or petitioner names": "Plaintiff or petitioner names",
    "defendant or respondent names": "Defendant or respondent names",
    "other party names": "Other party names",
    "document date": "Document date",
}


def normalize_extracted_fields(found_fields):
    """Keep every extracted value while normalizing keys used by the workflow."""
    if not isinstance(found_fields, dict):
        return {}

    normalized = {}
    for raw_key, value in found_fields.items():
        if value in (None, "", [], {}):
            continue
        key = str(raw_key).strip().lower()
        if key in {"court name", "court unit", "court or county"}:
            key = "court"
        elif key in {"docker number", "case number"}:
            key = "docket number"
        if isinstance(value, dict):
            value = "; ".join(f"{item_key}: {item_value}" for item_key, item_value in value.items())
        elif isinstance(value, list | tuple | set):
            value = "; ".join(str(item) for item in value)
        elif not isinstance(value, str):
            value = str(value)
        normalized[key] = value.strip()
    return normalized


def extracted_details(guesses):
    """Return every extracted item in a stable, user-facing order."""
    guesses = guesses or {}
    ordered_keys = [*EXTRACTION_LABELS, *(key for key in guesses if key not in EXTRACTION_LABELS)]
    return [
        {
            "key": key,
            "label": EXTRACTION_LABELS.get(key, key.replace("_", " ").capitalize()),
            "value": guesses[key],
        }
        for key in ordered_keys
        if guesses.get(key) not in (None, "", [], {})
    ]
