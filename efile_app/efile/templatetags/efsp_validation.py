"""Accessible field feedback for the people forms."""

from django import template
from django.utils.html import format_html, format_html_join

register = template.Library()


@register.simple_tag(takes_context=True)
def validation_attrs(context, field):
    attrs = {"id": "suffix" if field == "suffix" else f"id_{field}", "aria-describedby": f"help_{field} error_{field}"}
    if context.get("field_errors", {}).get(field):
        attrs["aria-invalid"] = "true"
    rule = context.get("validation_rules", {}).get(field, {})
    if field in {"email", "phone"} and rule.get("required"):
        attrs["required"] = "required"
    return format_html_join(" ", '{}="{}"', attrs.items())


@register.simple_tag(takes_context=True)
def field_feedback(context, field):
    rule = context.get("validation_rules", {}).get(field, {})
    help_text = rule.get("help", "")
    if rule.get("max_length") is not None:
        help_text = f"{help_text} {rule['max_length']} characters or fewer.".strip()
    error = context.get("field_errors", {}).get(field, "")
    return format_html(
        '<span class="form-text" id="help_{}">{}</span><span class="field-error" id="error_{}" {}>{}</span>',
        field,
        help_text,
        field,
        "" if error else "hidden",
        error,
    )
