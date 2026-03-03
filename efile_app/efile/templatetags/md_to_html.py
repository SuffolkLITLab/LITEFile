import markdown
from django import template
from django.utils.safestring import mark_safe


def md_to_html(value):  # Only one argument.
    """Converts a string into all lowercase"""
    return mark_safe(markdown.markdown(value))


register = template.Library()
register.filter("md_to_html", md_to_html)
