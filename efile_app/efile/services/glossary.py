"""Plain-language meanings for court terms in filing and case-type names.

Terms live in ``data/legal_glossary.yaml``: general ones, plus a state's own
under ``jurisdictions``, which replace the general entry with the same key.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

GLOSSARY_PATH = Path(__file__).resolve().parents[1] / "data" / "legal_glossary.yaml"


@lru_cache(maxsize=1)
def _config():
    config = yaml.safe_load(GLOSSARY_PATH.read_bytes())
    if config.get("version") != 1:
        raise ValueError("Unsupported glossary version")
    return config


@lru_cache(maxsize=16)
def _terms(jurisdiction):
    config = _config()
    terms = {**config.get("terms", {}), **config.get("jurisdictions", {}).get(jurisdiction, {}).get("terms", {})}
    compiled = []
    for key, term in terms.items():
        words = "|".join(re.escape(word).replace(r"\ ", r"[\s-]+") for word in term["match"])
        compiled.append((key, re.compile(rf"(?<![\w'])(?:{words})(?![\w'])", re.IGNORECASE), term))
    return compiled


def glossary_for(jurisdiction, texts):
    """The terms named anywhere in ``texts``, each once, in the order first named."""
    found = {}
    for text in texts:
        for key, pattern, term in _terms(jurisdiction):
            if key not in found and (match := pattern.search(text or "")):
                found[key] = (match.start(), len(found), term)
    # A longer term that contains a shorter one ("intentional tort") stands alone.
    shown = {}
    for key, (_, order, term) in found.items():
        words = term["label"].casefold()
        if not any(other != key and words in found[other][2]["label"].casefold() for other in found):
            shown[key] = (order, term)
    return [
        {"key": key, "label": term["label"], "text": term["text"], "source": term.get("source", "")}
        for key, (_, term) in sorted(shown.items(), key=lambda item: item[1][0])
    ]
