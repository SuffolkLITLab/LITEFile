"""Keep document suggestions separate from court-permitted filing selections."""

from efile.services.extraction_confirmation import extraction_review_fingerprint


def current_proposal(draft):
    if draft.ai_assistance_opted_out:
        return None
    saved = draft.filing_type_proposal or {}
    if saved.get("source_fingerprint") == extraction_review_fingerprint(draft):
        return saved
    name = (draft.extracted_guesses or {}).get("filing type", "")
    return {"name": str(name), "source": "ai"} if name else None


def save_proposal(draft, name):
    previous = current_proposal(draft) or {}
    draft.filing_type_proposal = {
        "name": str(name or "").strip()[:255],
        "source": "user" if str(name or "").strip() != previous.get("name", "") else previous.get("source", "ai"),
        "source_fingerprint": extraction_review_fingerprint(draft),
    }
    draft.save(update_fields=["filing_type_proposal", "updated_at"])


def resolve_proposal(draft, choices):
    proposal = current_proposal(draft)
    if not proposal or not proposal.get("name"):
        return {"status": "none"}
    name = " ".join(proposal["name"].split()).casefold()
    matches = [choice for choice in choices if " ".join(choice["text"].split()).casefold() == name]
    if len(matches) == 1:
        return {"status": "matched", "name": matches[0]["text"], "value": matches[0]["value"]}
    return {"status": "unavailable", "name": proposal["name"]}
