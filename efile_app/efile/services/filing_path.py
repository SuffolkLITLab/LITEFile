"""The new-or-existing-case answer: where it came from, and changing it.

A filer can say which kind of filing this is in three places -- the start
menu's "Start a new case" / "File into an existing case", a filing plan, or the
"What are you trying to do?" question -- and can correct it on Confirm case
once their documents have been read. Two things follow from that:

* Back and the progress steps should follow the way the filer actually came
  in. Someone who chose from the start menu never saw the question, and Back
  from Upload should not introduce it as if they had.
* Changing the answer is more than one field. The same draft and the same
  PDFs carry on, but what was chosen for the other kind of filing -- the
  court's filing types differ between opening a case and filing into one, an
  existing case's identity, a fee quote -- no longer applies, and is cleared
  here in one place rather than by whichever screen made the change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from efile.models import FilingDocument, FilingDraft, sync_primary_filing_type
from efile.services.fee_quotes import invalidate_fee_quote
from efile.workflow import ExistingCase, normalize_existing_case

FILING_PATH_SOURCE_KEY = "_filing_path_source"


class FilingPathSource:
    START_MENU = "start_menu"
    PLAN = "plan"
    QUESTION = "question"


def record_filing_path_source(draft: FilingDraft, source: str) -> None:
    draft.supplemental_fields = {**(draft.supplemental_fields or {}), FILING_PATH_SOURCE_KEY: source}
    draft.save(update_fields=["supplemental_fields", "updated_at"])


def filing_path_source(draft: Any | None) -> str:
    fields = getattr(draft, "supplemental_fields", None) or {}
    return str(fields.get(FILING_PATH_SOURCE_KEY) or "") if isinstance(fields, dict) else ""


def filing_path_question_was_asked(draft: Any | None) -> bool:
    """Whether "What are you trying to do?" is part of this draft's way in.

    A draft that does not say is one from before this was recorded; it keeps
    the screen, since some of those came through it.
    """

    return filing_path_source(draft) in {"", FilingPathSource.QUESTION}


def _filing_code_branch(path: str) -> str:
    # What the court's filing-type lists are asked for: an existing case, or
    # not. An unsure filer is shown the lists for opening a case.
    return "existing" if path == ExistingCase.EXISTING else "new"


@dataclass
class FilingPathChange:
    previous: str
    current: str
    cleared: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.previous != self.current

    @property
    def switched(self) -> bool:
        """Away from an earlier answer, rather than answering for the first time."""

        return bool(self.previous) and self.changed


@transaction.atomic
def change_filing_path(draft: FilingDraft, new_path: str) -> FilingPathChange:
    """Move a draft to the other kind of filing, keeping it and its documents.

    Clears only what belongs to the old kind: an existing case's number, title
    and court record when it is no longer an existing case; each document's
    filing type (and the options chosen with it) when the court's lists for
    the new kind differ; and any fee quote, which priced the old filing.
    """

    previous = normalize_existing_case(draft.existing_case)
    current = normalize_existing_case(new_path)
    change = FilingPathChange(previous=previous, current=current)
    if not change.changed:
        return change

    update_fields = ["existing_case", "updated_at"]
    draft.existing_case = current

    if current != ExistingCase.EXISTING and (draft.previous_case_id or draft.docket_number or draft.case_title):
        # A new case has no number or title until the court opens it, and a
        # case id left behind would file this into the case it came from.
        draft.previous_case_id = ""
        draft.docket_number = ""
        draft.case_title = ""
        update_fields += ["previous_case_id", "docket_number", "case_title"]
        change.cleared.append("case")

    if _filing_code_branch(previous) != _filing_code_branch(current):
        chosen = FilingDocument.objects.filter(draft=draft).exclude(filing_type_code="")
        if chosen.exists():
            chosen.update(
                filing_type_code="",
                filing_type_name="",
                filing_component_code="",
                filing_component_name="",
                requested_optional_services=[],
                filing_requires_amount_in_controversy=False,
            )
            sync_primary_filing_type(draft)
            change.cleared.append("filing_types")

    if draft.quoted_fee_total or draft.quoted_fee_breakdown or draft.quoted_fee_fingerprint:
        # The fingerprint would make it stale anyway; clearing it says outright
        # that the quote priced a different kind of filing.
        invalidate_fee_quote(draft, save=False)
        update_fields += ["quoted_fee_total", "quoted_fee_breakdown", "quoted_fee_fingerprint"]
        change.cleared.append("fees")

    draft.save(update_fields=update_fields)
    return change


PATH_NAMES = {
    ExistingCase.NEW: "a new case",
    ExistingCase.EXISTING: "a case that is already open",
    ExistingCase.UNSURE: "not sure yet",
}


def describe_path_change(change: FilingPathChange) -> str:
    """What changing the path kept and what it undid, in the filer's terms."""

    parts = [
        f"This filing is now for {PATH_NAMES.get(change.current, change.current)}. Your uploaded documents are kept."
    ]
    if "filing_types" in change.cleared:
        parts.append(
            "The court lists different filing types for new and existing cases, "
            "so you will choose each document's filing type again."
        )
    if "case" in change.cleared:
        parts.append("The case number from the existing case was removed.")
    if "fees" in change.cleared:
        parts.append("Fees will be calculated again.")
    return " ".join(parts)


# What a document's own evidence says about the kind of filing. These are the
# values the extraction records as "filing phase".
_PHASE_SUGGESTS = {"initial": ExistingCase.NEW, "subsequent": ExistingCase.EXISTING}


def filing_path_conflict(
    draft: FilingDraft,
    evidence: dict[str, Any] | None,
    document_title: str = "",
    *,
    chosen: str | None = None,
) -> dict | None:
    """When the uploaded document reads as the other kind of filing, say which.

    Only a suggestion: the extraction reads one document and can be wrong, so
    this never changes the filer's answer. Returns None when there is nothing
    to point out -- no answer yet, no evidence, or the two agree.

    `chosen` is the answer the screen is showing, when that is not the saved
    one: a form sent back with an error shows what the filer submitted, and
    the note has to be about that answer, not the one it replaces.
    """

    chosen = normalize_existing_case(draft.existing_case if chosen is None else chosen)
    if chosen not in {ExistingCase.NEW, ExistingCase.EXISTING}:
        return None
    phase = str((evidence or {}).get("filing phase") or "").strip().casefold()
    suggested = _PHASE_SUGGESTS.get(phase)
    if suggested is None or suggested == chosen:
        return None
    return {"chosen": str(chosen), "suggested": str(suggested), "document_title": str(document_title or "")}
