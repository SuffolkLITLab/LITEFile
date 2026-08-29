"""Resolve crosswalk forms to PDFs already present in the working directory."""

import csv
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markitdown import MarkItDown
from pypdf import PdfReader

JURISDICTION_DIRECTORY_NAMES = {
    "illinois": "il",
    "il": "il",
    "massachusetts": "ma",
    "ma": "ma",
    "vermont": "vt",
    "vt": "vt",
}


@dataclass(frozen=True)
class LocalFormDocument:
    """A PDF and the registry metadata used to identify it."""

    # ``path`` is displayed to a reviewer; ``source_path`` retains the original
    # downloaded PDF used for deterministic printed-ID evidence.
    path: Path
    source_path: Path
    relative_path: str
    filename: str
    jurisdiction: str
    source_url: str
    form_id: str
    title: str


@dataclass(frozen=True)
class LocalFormIndex:
    """In-memory indexes for constant-time local form lookup after startup."""

    by_source_url: dict[tuple[str, str], tuple[LocalFormDocument, ...]]
    by_source_path: dict[tuple[str, str], tuple[LocalFormDocument, ...]]
    by_form_id: dict[tuple[str, str], tuple[LocalFormDocument, ...]]
    by_title: dict[tuple[str, str], tuple[LocalFormDocument, ...]]
    by_relative_path: dict[str, LocalFormDocument]
    document_count: int


@dataclass(frozen=True)
class LocalFormIdVerification:
    """Whether a form's assigned ID is printed in a local candidate PDF."""

    status: str
    form_id: str
    page: int | None = None
    error: str = ""
    source: str = ""

    @property
    def verified(self) -> bool:
        return self.status == "verified"


def _text_key(value: str | None) -> str:
    """Normalize human text so punctuation, spacing, and accents do not matter."""
    normalized = unicodedata.normalize("NFKD", value or "").casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _identifier_occurrence_page(text: str, form_id: str) -> int | None:
    """Find an exact ID while ignoring internal punctuation and whitespace."""
    identifier = _text_key(form_id)
    if not identifier:
        return None
    normalized = unicodedata.normalize("NFKC", text).casefold()
    compact_characters = []
    source_positions = []
    for position, character in enumerate(normalized):
        if character in "abcdefghijklmnopqrstuvwxyz0123456789":
            compact_characters.append(character)
            source_positions.append(position)
    compact = "".join(compact_characters)
    start = compact.find(identifier)
    while start >= 0:
        end = start + len(identifier) - 1
        source_start = source_positions[start]
        source_end = source_positions[end] + 1
        before = normalized[source_start - 1] if source_start else ""
        after = normalized[source_end] if source_end < len(normalized) else ""
        if not (
            (before and before in "abcdefghijklmnopqrstuvwxyz0123456789")
            or (after and after in "abcdefghijklmnopqrstuvwxyz0123456789")
        ):
            return normalized[:source_start].count("\f") + 1
        start = compact.find(identifier, start + 1)
    return None


@lru_cache(maxsize=2048)
def _pdf_text(path_string: str, modified_ns: int, size: int) -> tuple[str, str]:
    """Extract local PDF text once per file version for ID validation."""
    del modified_ns, size
    try:
        reader = PdfReader(path_string)
        return "\f".join(page.extract_text() or "" for page in reader.pages), ""
    except Exception as error:  # pypdf has several parser-specific error types.
        return "", str(error)


@lru_cache(maxsize=2048)
def _markitdown_pdf_text(path_string: str, modified_ns: int, size: int) -> tuple[str, str]:
    """Use MarkItDown when pypdf cannot prove the assigned printed ID."""
    del modified_ns, size
    try:
        return MarkItDown().convert(path_string).text_content, ""
    except Exception as error:  # Conversion failures leave the candidate unverified.
        return "", str(error)


def verify_local_form_id(form, document: LocalFormDocument) -> LocalFormIdVerification:
    """Validate that the assigned crosswalk ID appears in the candidate PDF."""
    form_id = str(getattr(form, "form_id", "") or "").strip()
    if not _text_key(form_id):
        return LocalFormIdVerification(status="no_assigned_id", form_id=form_id)
    try:
        stat = document.source_path.stat()
    except OSError as error:
        return LocalFormIdVerification(status="unreadable", form_id=form_id, error=str(error))
    text, error = _pdf_text(str(document.source_path), stat.st_mtime_ns, stat.st_size)
    page = _identifier_occurrence_page(text, form_id) if not error else None
    if page is not None:
        return LocalFormIdVerification(status="verified", form_id=form_id, page=page, source="pypdf")
    markitdown_text, markitdown_error = _markitdown_pdf_text(str(document.source_path), stat.st_mtime_ns, stat.st_size)
    page = _identifier_occurrence_page(markitdown_text, form_id) if not markitdown_error else None
    if page is not None:
        return LocalFormIdVerification(status="verified", form_id=form_id, page=page, source="markitdown")
    if error and markitdown_error:
        return LocalFormIdVerification(
            status="unreadable",
            form_id=form_id,
            error=f"pypdf: {error}; MarkItDown: {markitdown_error}",
        )
    return LocalFormIdVerification(status="missing", form_id=form_id)


def _jurisdiction_key(value: str | None) -> str:
    return JURISDICTION_DIRECTORY_NAMES.get((value or "").strip().casefold(), (value or "").strip().casefold())


def _source_url_key(value: str | None) -> str:
    parsed = urlsplit(unquote(value or ""))
    path = parsed.path.rstrip("/").casefold()
    return f"{parsed.netloc.casefold()}{path}"


def _source_path_key(value: str | None) -> str:
    parsed = urlsplit(unquote(value or ""))
    filename = parsed.path.rsplit("/", 1)[-1]
    if filename.casefold().endswith(".pdf"):
        filename = filename[:-4]
    return _text_key(filename)


def _deduplicate(documents: list[LocalFormDocument]) -> tuple[LocalFormDocument, ...]:
    by_path = {document.relative_path: document for document in documents}
    return tuple(by_path.values())


def _registry_rows(root: Path) -> list[dict[str, object]]:
    """Read the download registry, with CSV as a compatibility fallback."""
    json_path = root / "form_registry.json"
    try:
        with json_path.open(encoding="utf-8") as registry_file:
            rows = json.load(registry_file)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    except (OSError, json.JSONDecodeError):
        pass

    csv_path = root / "form_registry.csv"
    try:
        with csv_path.open(newline="", encoding="utf-8") as registry_file:
            return list(csv.DictReader(registry_file))
    except OSError:
        return []


@lru_cache(maxsize=4)
def local_form_index(root_string: str) -> LocalFormIndex:
    """Build and cache the local PDF index for one configured forms directory."""
    root = Path(root_string).expanduser().resolve()
    empty = LocalFormIndex({}, {}, {}, {}, {}, 0)
    if not root.is_dir():
        return empty

    documents = []
    for row in _registry_rows(root):
        relative_path = str(row.get("relative_path") or row.get("filename") or "").strip()
        if not relative_path:
            continue
        source_path = (root / relative_path).resolve()
        try:
            source_path.relative_to(root)
        except ValueError:
            continue
        if source_path.suffix.casefold() != ".pdf" or not source_path.is_file():
            continue
        rendered_relative_path = str(row.get("rendered_visual_path") or "").strip()
        rendered_path = (root / rendered_relative_path).resolve() if rendered_relative_path else source_path
        try:
            rendered_path.relative_to(root)
        except ValueError:
            rendered_path = source_path
        path = rendered_path if rendered_path.is_file() else source_path
        documents.append(
            LocalFormDocument(
                path=path,
                source_path=source_path,
                relative_path=source_path.relative_to(root).as_posix(),
                filename=source_path.name,
                jurisdiction=_jurisdiction_key(str(row.get("jurisdiction") or relative_path.split("/", 1)[0])),
                source_url=str(row.get("source_url") or ""),
                form_id=str(row.get("form_id") or ""),
                title=str(row.get("canonical_title") or row.get("title") or ""),
            )
        )

    indexes: dict[str, dict[tuple[str, str], list[LocalFormDocument]]] = {
        "by_source_url": {},
        "by_source_path": {},
        "by_form_id": {},
        "by_title": {},
    }
    for document in documents:
        jurisdiction = document.jurisdiction
        for index_name, key in (
            ("by_source_url", _source_url_key(document.source_url)),
            ("by_source_path", _source_path_key(document.source_url)),
            ("by_form_id", _text_key(document.form_id)),
            ("by_title", _text_key(document.title)),
        ):
            if key:
                indexes[index_name].setdefault((jurisdiction, key), []).append(document)

    return LocalFormIndex(
        **{name: {key: _deduplicate(value) for key, value in entries.items()} for name, entries in indexes.items()},
        by_relative_path={document.relative_path: document for document in documents},
        document_count=len(documents),
    )


@lru_cache(maxsize=8)
def _printed_id_matches(root_string: str, modified_ns: int) -> dict[str, tuple[str, ...]]:
    """Read the generated, exact-ID PDF reverse index for one file version."""
    del modified_ns
    report_path = Path(root_string) / "form_id_matches.json"
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    forms = payload.get("forms", {}) if isinstance(payload, dict) else {}
    if not isinstance(forms, dict):
        return {}
    matches = {}
    for canonical_id, value in forms.items():
        if not isinstance(value, dict) or value.get("status") not in {
            "unique_printed_id_match",
            "unique_printed_id_and_title_match",
            "printed_id_form_family",
        }:
            continue
        paths = value.get("candidate_paths", [])
        if isinstance(paths, list) and paths and all(isinstance(path, str) for path in paths):
            matches[str(canonical_id)] = tuple(paths)
    return matches


def printed_id_match(form, root: str | Path) -> LocalFormDocument | None:
    """Return a unique PDF selected by its exact printed crosswalk ID."""
    root_path = Path(root).expanduser().resolve()
    report_path = root_path / "form_id_matches.json"
    try:
        modified_ns = report_path.stat().st_mtime_ns
    except OSError:
        return None
    paths = _printed_id_matches(str(root_path), modified_ns).get(str(getattr(form, "canonical_id", "")), ())
    if not paths:
        return None
    return local_form_index(str(root_path)).by_relative_path.get(paths[0])


@lru_cache(maxsize=8)
def _has_printed_id_index(root_string: str, modified_ns: int) -> bool:
    """Validate and cache the presence of one generated index file version."""
    del modified_ns
    report_path = Path(root_string) / "form_id_matches.json"
    try:
        return isinstance(json.loads(report_path.read_text(encoding="utf-8")), dict)
    except (OSError, json.JSONDecodeError):
        return False


def has_printed_id_index(root: str | Path) -> bool:
    """Return whether a generated exact-ID PDF crosswalk is available."""
    root_path = Path(root).expanduser().resolve()
    report_path = root_path / "form_id_matches.json"
    try:
        modified_ns = report_path.stat().st_mtime_ns
    except OSError:
        return False
    return _has_printed_id_index(str(root_path), modified_ns)


def resolve_local_form(form, root: str | Path) -> tuple[LocalFormDocument | None, str]:
    """Return an unambiguous local PDF and the method that identified it.

    Source URL matches are preferred. Form ID and title matching are only used
    when they produce one file, so a shared form ID or repeated translated title
    cannot silently select the wrong PDF.
    """
    if document := printed_id_match(form, root):
        return document, "printed form ID"
    # Once the generated exact-ID crosswalk exists, it is authoritative. Do
    # not revive a title/source candidate that the deterministic pass rejected.
    # A record with no claimed ID is different: a unique exact title is its
    # canonical identity rather than a fallback from a disproven code.
    if has_printed_id_index(root):
        if not _text_key(getattr(form, "form_id", "")):
            index = local_form_index(str(Path(root).expanduser().resolve()))
            raw_data = getattr(form, "raw_data", {})
            aliases = raw_data.get("aliases", []) if isinstance(raw_data, dict) else []
            title_values = [getattr(form, "canonical_name", ""), *(aliases if isinstance(aliases, list) else [])]
            title_documents = {
                document.relative_path: document
                for title in title_values
                for document in index.by_title.get(
                    (_jurisdiction_key(getattr(form, "jurisdiction", "")), _text_key(title)), ()
                )
            }
            if len(title_documents) == 1:
                return next(iter(title_documents.values())), "unique title"
        return None, ""

    index = local_form_index(str(Path(root).expanduser().resolve()))
    jurisdiction = _jurisdiction_key(getattr(form, "jurisdiction", ""))
    source_urls = getattr(form, "safe_source_urls", None) or []
    for source_url in source_urls:
        documents = index.by_source_url.get((jurisdiction, _source_url_key(source_url)), ())
        if len(documents) == 1:
            return documents[0], "source URL"
    for source_url in source_urls:
        source_path_key = _source_path_key(source_url)
        if not source_path_key:
            continue
        documents = index.by_source_path.get((jurisdiction, source_path_key), ())
        if len(documents) == 1:
            return documents[0], "source filename"

    form_id = _text_key(getattr(form, "form_id", ""))
    id_documents = index.by_form_id.get((jurisdiction, form_id), ()) if form_id else ()
    raw_data = getattr(form, "raw_data", {})
    aliases = raw_data.get("aliases", []) if isinstance(raw_data, dict) else []
    title_values = [getattr(form, "canonical_name", ""), *(aliases if isinstance(aliases, list) else [])]
    title_documents = {
        document.relative_path
        for title in title_values
        for document in index.by_title.get((jurisdiction, _text_key(title)), ())
    }
    id_and_title = tuple(document for document in id_documents if document.relative_path in title_documents)
    if len(id_and_title) == 1:
        return id_and_title[0], "form ID and title"

    canonical_title_documents = index.by_title.get(
        (jurisdiction, _text_key(getattr(form, "canonical_name", ""))),
        (),
    )
    if len(canonical_title_documents) == 1:
        return canonical_title_documents[0], "title"
    if len(id_documents) == 1:
        return id_documents[0], "form ID"
    return None, ""
