"""Render independent two- and three-stage taxonomy prompt variations."""

import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "efile_app"))

from efile.utils.prompt_config import render_prompt_messages  # noqa: E402

ROLE_RUBRIC = """

Classification rubric for this experiment:
* A case category describes the underlying court matter, not merely the uploaded document.
* A case type describes the underlying action within the selected category.
* A filing type describes this uploaded document. Do not select a document merely mentioned in its text.
* An official form identifier and printed form title are strong evidence for filing type.
* Prefer a generic offered filing name when it accurately represents the uploaded document and a more specific offered name describes a different document or procedural request.
* Amount bands must use an amount expressly stated in the source.
Before answering, compare the strongest two candidates against those distinctions.
"""

CROSSWALK_RUBRIC = """

Official-form lookup stage:
${crosswalk}

These are deterministic exact-form retrieval results, not adjudicated gold labels. Use a suggestion only
when its hierarchy is compatible with the selected court, parents, filing phase, offered candidates, and
source document. `unverified_suggestion` means the association must be confirmed from the source.
"""

SELECTION_GUARD = """

Canonical-selection guard:
* Treat procedural qualifiers such as contested, stipulated, joint, emergency, initial, postjudgment,
  and with/without children as required facts. Do not infer a qualifier unless the source says it or
  the official form identity uniquely establishes it.
* The parent case-type amount band does not override a more specific filing-type amount band.
* After deciding, copy the complete code/name pair directly from one offered candidate. Preserve its
  spelling, punctuation, Unicode characters, and amount formatting exactly; never reconstruct the name.
"""

REFERENCE_SELECTION_GUARD = """

Selection-reference rules:
* Return only the offered `selection_ref`; application code will recover the exact canonical name and
  current route key. Do not reproduce or normalize a taxonomy name.
* A complaint is not evidence that a matter is stipulated. Without express agreement or stipulation,
  prefer a contested choice over an otherwise matching stipulated choice.
* For an official initiating petition or complaint with no specific offered filing name, `Initial Filing`
  may be the correct generic filing type. Prefer an offered document-specific name when one exists.
"""


def _render(
    context,
    *,
    rubric=False,
    crosswalk=False,
    shortlist=False,
    selection_guard=False,
    reference_selection=False,
):
    variables = context["vars"]
    candidates = variables["available_candidates"]
    retrieval_note = ""
    if shortlist:
        candidates, retrieval_note = _shortlist(variables)
    if reference_selection:
        candidates = [
            {"selection_ref": f"C{index:03d}", "name": item["name"]}
            for index, item in enumerate(candidates, start=1)
        ]
    messages, _settings = render_prompt_messages(
        "efile_taxonomy_classification",
        mode="text",
        field_definitions={},
        document_text=variables["document_text"],
        version="v1",
        template_values={
            "classification_level": variables["classification_level"],
            "jurisdiction": variables["jurisdiction"],
            "court_name": variables["court_name"],
            "filing_phase": variables["filing_phase"],
            "selected_case_category": variables.get("selected_case_category")
            or "not selected yet",
            "selected_case_type": variables.get("selected_case_type")
            or "not selected yet",
            "available_candidates": candidates,
            "extracted_evidence": variables["extracted_evidence"],
            "source_scope": variables["source_scope"],
        },
    )
    additions = ""
    if rubric:
        additions += ROLE_RUBRIC
    if crosswalk:
        additions += CROSSWALK_RUBRIC.replace(
            "${crosswalk}",
            json.dumps(variables.get("crosswalk_candidates", []), ensure_ascii=False),
        )
    if retrieval_note:
        additions += retrieval_note
    if selection_guard:
        additions += SELECTION_GUARD
    if reference_selection:
        additions += REFERENCE_SELECTION_GUARD
        messages[0]["content"] = messages[0]["content"].replace(
            "code/name pair", "selection_ref/name entry"
        )
        messages[-1]["content"] = messages[-1]["content"].replace(
            '"selection": {"code": "offered code", "name": "offered name"} or null,',
            '"selection_ref": "offered C### reference" or null,',
        )
    messages[-1]["content"] += additions
    return json.dumps(messages, ensure_ascii=False)


def _tokens(value):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value).casefold())
        if len(token) > 2 and token not in {"the", "for", "and", "this", "that", "form"}
    }


def _shortlist(variables):
    candidates = variables["available_candidates"]
    if len(candidates) <= 20:
        return (
            candidates,
            f"\nRetrieval stage supplied all {len(candidates)} candidates.\n",
        )
    evidence = variables.get("extracted_evidence", {})
    identity = variables.get("form_identity", {})
    query_parts = [
        identity.get("name"),
        identity.get("identifier"),
        evidence.get("document title"),
        evidence.get("form name"),
    ]
    query_tokens = _tokens(" ".join(str(value) for value in query_parts if value))
    level_key = {
        "case category": "category",
        "case type": "case_type",
        "filing type": "filing_type",
    }[variables["classification_level"]]
    retrieved_names = {
        str(item.get(level_key)).strip()
        for item in variables.get("crosswalk_candidates", [])
        if item.get(level_key)
    }

    def score(candidate):
        name = str(candidate["name"]).strip()
        candidate_tokens = _tokens(name)
        overlap = len(query_tokens & candidate_tokens)
        exact_bonus = 20 if name in retrieved_names else 0
        generic_initial_bonus = (
            2
            if variables["classification_level"] == "filing type"
            and variables.get("filing_phase") == "initial"
            and name == "Initial Filing"
            else 0
        )
        coverage = overlap / max(len(candidate_tokens), 1)
        return exact_bonus + generic_initial_bonus + overlap + coverage

    ranked = sorted(
        candidates, key=lambda item: (-score(item), item["name"], item["code"])
    )
    selected = ranked[:12]
    note = (
        f"\nPython retrieval stage reduced {len(candidates)} live candidates to {len(selected)} using "
        "form/evidence token overlap and exact-form crosswalk hits. If none is a good fit, return "
        "`request_more_candidates` rather than forcing a selection.\n"
    )
    return selected, note


def baseline(context):
    """Two-stage baseline: extracted evidence plus source text, then live candidate selection."""
    return _render(context)


def role_rubric(context):
    """Two-stage variant with explicit category/type/filing role distinctions."""
    return _render(context, rubric=True)


def form_crosswalk(context):
    """Three-stage variant adding deterministic exact-form retrieval before classification."""
    return _render(context, rubric=True, crosswalk=True)


def retrieval_shortlist(context):
    """Three-stage variant adding Python candidate retrieval and exact-form context."""
    return _render(context, rubric=True, crosswalk=True, shortlist=True)


def guarded_form_crosswalk(context):
    """Three-stage crosswalk variant with qualifier and exact-copy guards."""
    return _render(context, rubric=True, crosswalk=True, selection_guard=True)


def reference_form_crosswalk(context):
    """Three-stage variant where application code resolves the selected candidate reference."""
    return _render(context, rubric=True, crosswalk=True, reference_selection=True)
