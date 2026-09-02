"""User-facing text that a jurisdiction can reword and a translator can translate.

Two separate problems meet in this module.

The first is that states do not use the same words for the same thing. The
document that opens a case is a *petition* in Illinois and a *complaint* in
Vermont, and a filer who is told to look for the wrong one is being given wrong
instructions, not a stylistic variation. Those differences belong in the state's
own YAML file, next to everything else that is specific to that state.

The second is Spanish. Almost every string on these screens is ordinary English
copy that no state wants to change, and moving all of it into YAML to make the
handful of state-varying strings configurable would put thousands of strings
somewhere ``makemessages`` cannot see them. So the split is:

* Copy that does not vary by state stays in the template under ``{% translate %}``.
* Copy that a state might reword lives here, with its English default, and can
  be overridden by a ``text:`` section in that state's YAML.

Both halves end up in the same gettext catalog. A string resolved through this
module is passed through :func:`pgettext` with the key as its message context,
so the Illinois wording and the Vermont wording of the same key are two
translatable messages that a translator can tell apart. Defaults are picked up
from this file by ``makemessages``; the YAML overrides are picked up from the
stub that ``manage.py extract_config_text`` generates. See ``efile/locale/README.md``.

Usage from a template::

    {% load ui_text %}
    <p>{% ui_text "organize_documents.main_document_help" %}</p>

and from Python::

    from efile.utils.ui_text import get_text
    get_text("your_information.lede", jurisdiction="vermont")

Placeholders are filled in from the jurisdiction's config (``brand_name``,
``state_name``, ``state_code``, ``court_name``), from every ``terms.*`` key
(``terms.starting_document_example`` fills ``{starting_document_example}``), and
from any keyword arguments passed by the caller. An unknown placeholder is left
in the text rather than raising, because these strings can come from a YAML file
that no test has rendered.
"""

import logging
from dataclasses import dataclass
from string import Formatter

from django.utils.translation import pgettext

logger = logging.getLogger(__name__)

#: Config section, in a state's YAML file, that holds overrides for these keys.
CONFIG_SECTION = "text"

#: Keys under this prefix are short nouns rather than sentences. Each one is
#: also offered to every other string as a ``{placeholder}`` named for its last
#: path segment, so a passage can say "like a {starting_document_example}".
TERM_PREFIX = "terms."


@dataclass(frozen=True)
class UIString:
    """One overridable, translatable string.

    Args:
        default: The English wording used when a state configures nothing.
        description: Why this string is configurable, and what a state should
            consider when rewording it. Shown to config authors in the docs and
            to translators as a comment.
    """

    default: str
    description: str = ""


UI_STRINGS: dict[str, UIString] = {
    # -- Terms ---------------------------------------------------------------
    # Short nouns. Keep them lowercase and in the middle of a sentence: they are
    # interpolated into the passages below, which capitalize for themselves.
    "terms.starting_document_example": UIString(
        default="petition",
        description=(
            "What courts here usually call the document that opens a case, used as an example "
            "when asking the filer which PDF is the main one. Vermont says complaint."
        ),
    ),
    "terms.main_document": UIString(
        default="main document",
        description=(
            "The one PDF a filing is built around. Deliberately not the court's own "
            "'lead document', which is a per-document filing component and can apply to more "
            "than one PDF in the same filing."
        ),
    ),
    # -- Organize documents --------------------------------------------------
    "organize_documents.main_document_question": UIString(
        default="Which PDF is the {main_document}?",
    ),
    "organize_documents.main_document_help": UIString(
        default="Choose the document that starts this filing, like a {starting_document_example}. Upload order does not matter.",
        description="Names the kind of document that opens a case, which differs by state.",
    ),
    "organize_documents.single_document_note": UIString(
        default="This is the only document in this filing, so it is the {main_document}.",
    ),
    "organize_documents.filing_component_label": UIString(
        default="Court filing component",
        description=(
            "Label for the court's own per-document category. This is the court's term, not "
            "ours, so a state whose court calls it something else should say so here."
        ),
    ),
    "organize_documents.filing_component_help": UIString(
        default=(
            "The court receives each PDF as its own filing, so more than one PDF can carry a "
            "court component named “Lead Document”. That is separate from the one "
            "{main_document} you chose above."
        ),
        description=(
            "Explains why several PDFs can each say “Lead Document” here. Reword it if the "
            "court in this state names its components differently."
        ),
    ),
    "organize_documents.filing_component_fixed_note": UIString(
        default="The court requires this component for this filing type, so there is nothing to choose.",
    ),
    "organize_documents.filing_component_required_note": UIString(
        default="Required by the court for this filing type.",
    ),
    "organize_documents.confidentiality_help": UIString(
        default="Choose confidential only when a court rule or court order requires it.",
        description=(
            "Explains when filers in this jurisdiction may mark a document confidential. "
            "A state should use the rule or order language its court approves."
        ),
    ),
    "organize_documents.optional_services_summary": UIString(
        default="Certified copy and courtesy email (optional)",
    ),
    "organize_documents.optional_services_help": UIString(
        default=(
            "If you want a certified copy of this document, or an email copy when it is filed, "
            "ask for it here. Neither one is required."
        ),
        description="Says plainly that these are requests the filer may make, not steps they must complete.",
    ),
    # Placeholders the organize-documents page renders from JavaScript once the
    # court's own choices have loaded. They are resolved here, and handed to the
    # script through the page, so they stay configurable and translatable.
    "organize_documents.choose_filing_type_first": UIString(
        default="Select a filing type first",
    ),
    "organize_documents.loading_choices": UIString(
        default="Loading choices…",
    ),
    "organize_documents.no_document_types": UIString(
        default="No confidentiality choices are available",
    ),
    "organize_documents.no_filing_components": UIString(
        default="No filing components are available",
    ),
    # -- Extraction review --------------------------------------------------
    "extraction_review.court_label": UIString(
        default="Court or county",
        description="The jurisdiction's plain-language name for the court or venue shown on its forms.",
    ),
    "extraction_review.court_help": UIString(
        default="Choose the court that should receive this filing.",
    ),
    "extraction_review.case_category_label": UIString(
        default="Case category",
        description="The jurisdiction's term for the broad category or division of a court case.",
    ),
    "extraction_review.case_category_help": UIString(
        default="Choose the broad category that best describes the case.",
        description="May include familiar examples that help filers recognize the court's formal categories.",
    ),
    # -- Your information ----------------------------------------------------
    "your_information.lede": UIString(
        default="Confirm how the court can contact you. We filled in what we could from your {brand_name} account.",
        description="Names the account the filer signed in with. Uses the jurisdiction's brand name.",
    ),
    # -- People / parties ----------------------------------------------------
    "parties.role_question": UIString(
        default="What is your role in this case?",
    ),
    "parties.role_help": UIString(
        default=(
            "Choose the role that describes you, and the court will list you as a party in this case. "
            "You do not have to be one: if you are filing for someone else, say so and we will ask who."
        ),
    ),
    # -- Public pages --------------------------------------------------------
    "about.project_partner_description": UIString(
        # No {state_name} in the default on purpose: a state that has partners
        # to name is a state that should be naming them in its own words.
        default=(
            "LITEFile is built with legal aid partners who help fund, build, and deploy it for "
            "self-represented litigants in their states:"
        ),
        description=(
            "The partner paragraph on this jurisdiction's About page. Partners approve their own "
            "wording, so set it per state."
        ),
    ),
}


class _LenientParams(dict):
    """Leave an unknown ``{placeholder}`` alone instead of raising KeyError."""

    def __missing__(self, key):
        logger.warning("ui_text: no value for placeholder {%s}", key)
        return "{" + key + "}"


def _flatten(section, prefix=""):
    """Turn a nested ``text:`` config section into ``{"a.b": "value"}``."""
    flat = {}
    if not isinstance(section, dict):
        return flat
    for key, value in section.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, prefix=f"{path}."))
        elif isinstance(value, str):
            flat[path] = value
    return flat


def config_overrides(config):
    """Return the flattened ``text:`` overrides in a jurisdiction config."""
    return _flatten((config or {}).get(CONFIG_SECTION) or {})


def _load_config(jurisdiction, config):
    if config is not None:
        return config
    if not jurisdiction:
        return {}
    # Imported here: config_loader instantiates itself at import time and reads
    # settings, and ui_text is imported from templatetags and system checks.
    from efile.utils.config_loader import config_loader

    return config_loader.load_jurisdiction_config(jurisdiction) or {}


def _source(key, overrides):
    entry = UI_STRINGS.get(key)
    if entry is None:
        raise KeyError(
            f"Unknown UI text key {key!r}. Add it to efile.utils.ui_text.UI_STRINGS "
            f"before using it in a template or a state's text: config."
        )
    return overrides.get(key) or entry.default


def _jurisdiction_params(config):
    jurisdiction = (config or {}).get("jurisdiction") or {}
    state = (config or {}).get("state") or {}
    return {
        "brand_name": jurisdiction.get("brand_name") or "LITEFile",
        "court_name": jurisdiction.get("official_court_name") or "the court",
        "jurisdiction_name": jurisdiction.get("display_name") or "",
        "state_code": state.get("code") or "",
        "state_name": state.get("name") or jurisdiction.get("display_name") or "",
    }


def _format(text, params):
    try:
        return Formatter().vformat(text, (), _LenientParams(params))
    except (IndexError, ValueError) as error:
        # A stray brace in configured copy should show the filer the sentence,
        # not a server error.
        logger.warning("ui_text: could not format %r (%s)", text, error)
        return text


def get_text(key, jurisdiction=None, config=None, **params):
    """Resolve one UI string for a jurisdiction, translated and formatted.

    Args:
        key: A key in :data:`UI_STRINGS`, e.g. ``"parties.role_question"``.
        jurisdiction: Jurisdiction code, used to load config when ``config`` is
            not given.
        config: An already-loaded jurisdiction config, to avoid reloading it.
        **params: Extra placeholder values, which win over the automatic ones.

    Returns:
        str: The final string to show the filer.
    """
    config = _load_config(jurisdiction, config)
    overrides = config_overrides(config)
    text = pgettext(key, _source(key, overrides))

    values = _jurisdiction_params(config)
    if not key.startswith(TERM_PREFIX):
        # Terms are resolved without other terms in scope, so a term cannot
        # refer to itself or to another term and loop.
        for term_key in UI_STRINGS:
            if term_key.startswith(TERM_PREFIX):
                values[term_key[len(TERM_PREFIX) :]] = pgettext(term_key, _source(term_key, overrides))
    values.update(params)
    return _format(text, values)


def get_texts(keys, jurisdiction=None, config=None, **params):
    """Resolve several keys at once, for handing a page's strings to JavaScript.

    Returns:
        dict: ``{last_path_segment: resolved text}`` -- the short name keeps the
        JSON readable on the page and in the script that reads it.
    """
    config = _load_config(jurisdiction, config)
    return {key.rsplit(".", 1)[-1]: get_text(key, config=config, **params) for key in keys}
