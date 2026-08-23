"""Classify document evidence against the live, court-scoped Tyler taxonomy."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import requests
from django.conf import settings

from efile.utils.llms import chat_completion, get_default_model
from efile.utils.prompt_config import prompt_version, render_prompt_messages

logger = logging.getLogger(__name__)


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _option(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not item.get("code") or not item.get("name"):
        return None
    return {
        "route_key": str(item["code"]),
        "name": str(item["name"]),
        **{key: value for key, value in item.items() if key not in {"code", "name"}},
    }


class TylerTaxonomyClient:
    """Read the current taxonomy. Route keys are deliberately kept transient."""

    def __init__(self, base_url: str | None = None, timeout: int = 15):
        self.base_url = (base_url or settings.EFSP_URL).rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        response = requests.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"Tyler taxonomy endpoint returned {type(payload).__name__}, not a list")
        return [parsed for item in payload if (parsed := _option(item)) is not None]

    def courts(self, jurisdiction: str) -> list[dict[str, Any]]:
        options = self._get(
            f"/jurisdictions/{jurisdiction}/codes/courts/",
            # The EFSP's fileable_only filter currently omits courts that have
            # valid fileable categories (for example Cambridge District Court).
            # Fetch all named courts, then confirm the chosen hierarchy through
            # the category/type endpoints below.
            {"fileable_only": False, "with_names": True},
        )
        hidden = (
            "(zodyssey)",
            "z -",
            "zz",
            "zdev",
            "courtview test",
            "rsi test",
            "do not use",
            "not used",
            "file & serve",
            "system",
        )
        return [item for item in options if not any(marker in item["name"].casefold() for marker in hidden)]

    def categories(self, jurisdiction: str, court: str, filing_phase: str) -> list[dict[str, Any]]:
        timing = "Subsequent" if filing_phase == "subsequent" else "Initial"
        return self._get(
            f"/jurisdictions/{jurisdiction}/codes/courts/{court}/categories",
            {"fileable_only": True, "timing": timing},
        )

    def case_types(
        self,
        jurisdiction: str,
        court: str,
        category: str,
        filing_phase: str,
    ) -> list[dict[str, Any]]:
        timing = "Subsequent" if filing_phase == "subsequent" else "Initial"
        return self._get(
            f"/jurisdictions/{jurisdiction}/codes/courts/{court}/case_types/",
            {"category_id": category, "timing": timing},
        )

    def filing_types(
        self,
        jurisdiction: str,
        court: str,
        category: str,
        case_type: str,
        filing_phase: str,
    ) -> list[dict[str, Any]]:
        return self._get(
            f"/jurisdictions/{jurisdiction}/codes/courts/{court}/filing_types/",
            {
                "initial": "false" if filing_phase == "subsequent" else "true",
                "category_id": category,
                "type_id": case_type,
            },
        )


class TaxonomySource(Protocol):
    """The live taxonomy surface used by the hierarchical classifier."""

    base_url: str

    def courts(self, jurisdiction: str) -> list[dict[str, Any]]: ...

    def categories(
        self,
        jurisdiction: str,
        court: str,
        filing_phase: str,
    ) -> list[dict[str, Any]]: ...

    def case_types(
        self,
        jurisdiction: str,
        court: str,
        category: str,
        filing_phase: str,
    ) -> list[dict[str, Any]]: ...

    def filing_types(
        self,
        jurisdiction: str,
        court: str,
        category: str,
        case_type: str,
        filing_phase: str,
    ) -> list[dict[str, Any]]: ...


@cache
def _crosswalk_registry(path_string: str) -> list[dict[str, Any]]:
    path = Path(path_string)
    if not path.exists():
        logger.warning("Form crosswalk is unavailable at %s", path)
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("Could not load the form crosswalk at %s", path)
        return []
    registry = payload.get("registry", []) if isinstance(payload, dict) else []
    return registry if isinstance(registry, list) else []


def exact_form_crosswalk_matches(jurisdiction: str, evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Return advisory mappings only after an exact form ID or exact-name match."""
    identifier = _normalized(evidence.get("form identifier"))
    form_name = _normalized(evidence.get("form name"))
    if not identifier and not form_name:
        return []

    matches: list[dict[str, Any]] = []
    registry_path = getattr(
        settings,
        "FORM_CODE_CROSSWALK_PATH",
        settings.BASE_DIR / "efile" / "data" / "form_code_crosswalk.json",
    )
    for entry in _crosswalk_registry(str(registry_path)):
        form = entry.get("form", {}) if isinstance(entry, dict) else {}
        if _normalized(form.get("jurisdiction")) != _normalized(jurisdiction):
            continue
        ids_match = bool(identifier and identifier == _normalized(form.get("form_id")))
        names = [form.get("canonical_name"), *(form.get("aliases") or [])]
        names_match = bool(form_name and form_name in {_normalized(name) for name in names if name})
        if not ids_match and not names_match:
            continue
        for mapping in entry.get("mappings", []):
            if not isinstance(mapping, dict):
                continue
            matches.append(
                {
                    "canonical_form_id": form.get("canonical_id"),
                    "form_id": form.get("form_id"),
                    "form_name": form.get("canonical_name"),
                    "match_basis": "exact form identifier" if ids_match else "exact form name",
                    "category": mapping.get("category"),
                    "case_type": mapping.get("case_type"),
                    "filing_type": mapping.get("filing_type"),
                    "filing_phase": mapping.get("filing_phase"),
                    "court_names": (mapping.get("court_scope") or {}).get("court_names", []),
                    "confidence": mapping.get("confidence"),
                    "association_status": mapping.get("association_status"),
                    "catalog_status": mapping.get("catalog_status"),
                }
            )
    return matches[:30]


def _decimal_amount(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value or "").replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def extracted_amounts(evidence: dict[str, Any]) -> list[Decimal]:
    values = evidence.get("monetary amounts") or evidence.get("monetary amount") or []
    if isinstance(values, dict | str | int | float):
        values = [values]
    amounts: list[Decimal] = []
    for value in values if isinstance(values, list) else []:
        raw = value.get("amount") or value.get("raw") if isinstance(value, dict) else value
        amount = _decimal_amount(raw)
        if amount is not None and amount not in amounts:
            amounts.append(amount)
    return amounts


def primary_amount_in_controversy(evidence: dict[str, Any]) -> str:
    """Prefill only when the filing supplies one unambiguous claim-like amount."""
    values = evidence.get("monetary amounts") or evidence.get("monetary amount") or []
    if isinstance(values, dict | str | int | float):
        values = [values]
    candidates: list[Decimal] = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict):
            label = _normalized(value.get("label"))
            if label and not any(term in label for term in ("claim", "controversy", "damages", "demand")):
                continue
            raw = value.get("amount") or value.get("raw")
        else:
            raw = value
        amount = _decimal_amount(raw)
        if amount is not None and amount not in candidates:
            candidates.append(amount)
    if len(candidates) != 1:
        return ""
    return format(candidates[0], "f")


def _amount_fit(name: str, amounts: list[Decimal]) -> str | None:
    """Annotate obvious amount bands without filtering authoritative candidates."""
    if not amounts or "$" not in name:
        return None
    amount = amounts[0]
    compact = name.casefold().replace(",", "")
    numbers = [Decimal(number) for number in re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", compact)]
    if len(numbers) >= 2 and ("-" in compact or "through" in compact or " to " in compact):
        return "compatible" if numbers[0] <= amount <= numbers[1] else "incompatible"
    if numbers and any(term in compact for term in ("or less", "up to", "under")):
        return "compatible" if amount <= numbers[0] else "incompatible"
    if numbers and any(term in compact for term in ("over", "more than", "above")):
        return "compatible" if amount > numbers[0] else "incompatible"
    return None


def _crosswalk_names(matches: list[dict[str, Any]], level: str) -> set[str]:
    key = {"case category": "category", "case type": "case_type", "filing type": "filing_type"}.get(level)
    return {_normalized(item.get(key)) for item in matches if key and item.get(key)}


@dataclass
class ClassificationRun:
    selections: dict[str, dict[str, Any]]
    metadata: dict[str, Any]


class HierarchicalDocumentClassifier:
    """Select every supported hierarchy level from current live candidates."""

    def __init__(self, taxonomy: TaxonomySource | None = None, model: str | None = None):
        self.taxonomy = taxonomy or TylerTaxonomyClient()
        self.model = model or getattr(settings, "DOCUMENT_CLASSIFICATION_MODEL", "") or get_default_model("medium")
        self.prompt_name = "efile_taxonomy_classification"
        self.prompt_version, _definition, _config = prompt_version(self.prompt_name)

    def _select(
        self,
        *,
        level: str,
        jurisdiction: str,
        candidates: list[dict[str, Any]],
        evidence: dict[str, Any],
        source_text: str,
        filing_phase: str,
        selections: dict[str, dict[str, Any]],
        crosswalk: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not candidates:
            return {"status": "abstain", "reason": "The live taxonomy returned no candidates."}

        amounts = extracted_amounts(evidence)
        crosswalk_names = _crosswalk_names(crosswalk, level)
        offered: list[dict[str, Any]] = []
        references: dict[str, dict[str, Any]] = {}
        for index, candidate in enumerate(candidates, start=1):
            reference = f"C{index:03d}"
            references[reference] = candidate
            prompt_candidate: dict[str, Any] = {"selection_ref": reference, "name": candidate["name"]}
            amount_fit = _amount_fit(candidate["name"], amounts)
            if amount_fit:
                prompt_candidate["express_amount_fit"] = amount_fit
            if _normalized(candidate["name"]) in crosswalk_names:
                prompt_candidate["exact_form_crosswalk_match"] = True
            offered.append(prompt_candidate)

        messages, version_config = render_prompt_messages(
            self.prompt_name,
            mode="text",
            field_definitions={},
            document_text=source_text,
            version=self.prompt_version,
            template_values={
                "classification_level": level,
                "jurisdiction": jurisdiction,
                "court_name": selections.get("court", {}).get("name") or "not selected yet",
                "filing_phase": filing_phase,
                "selected_case_category": selections.get("case category", {}).get("name") or "not selected yet",
                "selected_case_type": selections.get("case type", {}).get("name") or "not selected yet",
                "available_candidates": offered,
                "extracted_evidence": evidence,
                "crosswalk_matches": crosswalk,
                "source_scope": f"MarkItDown text from the first {settings.DOCUMENT_CLASSIFICATION_SOURCE_PAGES} pages",
            },
        )
        inference = version_config.get("inference", {})
        result = chat_completion(
            messages=messages,
            model=self.model,
            json_mode=True,
            temperature=inference.get("temperature", 0),
            reasoning_effort=inference.get("reasoning_effort", "low"),
            model_type=version_config.get("preferred_model_tier", "medium"),
        )
        if not isinstance(result, dict):
            raise TypeError(f"{level} classification did not return a JSON object")
        status = str(result.get("status") or "abstain")
        selection_ref = str(result.get("selection_ref") or "")
        selected = references.get(selection_ref)
        if status == "selected" and selected:
            try:
                confidence = max(0.0, min(1.0, float(result.get("confidence", 0))))
            except (TypeError, ValueError):
                confidence = 0.0
            return {
                "status": "selected",
                "name": selected["name"],
                "route_key": selected["route_key"],
                "confidence": confidence,
                "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
                "reason": str(result.get("reason") or ""),
                "selection_ref": selection_ref,
                "candidate_count": len(candidates),
            }
        return {
            "status": "abstain" if status not in {"abstain", "request_more_candidates"} else status,
            "confidence": 0.0,
            "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
            "reason": str(result.get("reason") or ""),
            "search_query": str(result.get("search_query") or ""),
            "candidate_count": len(candidates),
        }

    def classify(self, jurisdiction: str, evidence: dict[str, Any], source_text: str) -> ClassificationRun:
        filing_phase = str(evidence.get("filing phase") or "unknown").casefold()
        if filing_phase not in {"initial", "subsequent"}:
            filing_phase = "unknown"
        crosswalk = exact_form_crosswalk_matches(jurisdiction, evidence)
        selections: dict[str, dict[str, Any]] = {}

        selections["court"] = self._select(
            level="court",
            jurisdiction=jurisdiction,
            candidates=self.taxonomy.courts(jurisdiction),
            evidence=evidence,
            source_text=source_text,
            filing_phase=filing_phase,
            selections=selections,
            crosswalk=crosswalk,
        )
        if selections["court"].get("status") != "selected":
            return self._run(selections, filing_phase, crosswalk)

        court = selections["court"]["route_key"]
        selections["case category"] = self._select(
            level="case category",
            jurisdiction=jurisdiction,
            candidates=self.taxonomy.categories(jurisdiction, court, filing_phase),
            evidence=evidence,
            source_text=source_text,
            filing_phase=filing_phase,
            selections=selections,
            crosswalk=crosswalk,
        )
        if selections["case category"].get("status") != "selected":
            return self._run(selections, filing_phase, crosswalk)

        category = selections["case category"]["route_key"]
        selections["case type"] = self._select(
            level="case type",
            jurisdiction=jurisdiction,
            candidates=self.taxonomy.case_types(jurisdiction, court, category, filing_phase),
            evidence=evidence,
            source_text=source_text,
            filing_phase=filing_phase,
            selections=selections,
            crosswalk=crosswalk,
        )
        if selections["case type"].get("status") != "selected":
            return self._run(selections, filing_phase, crosswalk)

        case_type = selections["case type"]["route_key"]
        selections["filing type"] = self._select(
            level="filing type",
            jurisdiction=jurisdiction,
            candidates=self.taxonomy.filing_types(jurisdiction, court, category, case_type, filing_phase),
            evidence=evidence,
            source_text=source_text,
            filing_phase=filing_phase,
            selections=selections,
            crosswalk=crosswalk,
        )
        return self._run(selections, filing_phase, crosswalk)

    def _run(
        self,
        selections: dict[str, dict[str, Any]],
        filing_phase: str,
        crosswalk: list[dict[str, Any]],
    ) -> ClassificationRun:
        return ClassificationRun(
            selections=selections,
            metadata={
                "prompt": self.prompt_name,
                "prompt_version": self.prompt_version,
                "model": self.model,
                "taxonomy_endpoint": self.taxonomy.base_url,
                "filing_phase": filing_phase,
                "crosswalk_match_count": len(crosswalk),
            },
        )
