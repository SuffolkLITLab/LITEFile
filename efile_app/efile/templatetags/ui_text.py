"""``{% ui_text %}`` -- jurisdiction-configurable, translatable copy in templates.

    {% load ui_text %}
    <legend>{% ui_text "organize_documents.main_document_question" %}</legend>
    <p>{% ui_text "about.project_partner_description" %}</p>

The jurisdiction and its config come from the template context, which the
``jurisdiction_context`` context processor puts there on every page. Extra
keyword arguments become placeholder values:

    {% ui_text "parties.role_help" name=filer.first_name %}

A passage marked ``links=True`` in the catalog renders its inline Markdown as
sanitized HTML; every other key is plain, escaped text.

See ``efile/utils/ui_text.py`` for the catalog of keys.
"""

from django import template

from efile.utils.ui_text import get_html

register = template.Library()


@register.simple_tag(takes_context=True)
def ui_text(context, key, **params):
    return get_html(
        key,
        jurisdiction=context.get("jurisdiction"),
        config=context.get("config"),
        **params,
    )
