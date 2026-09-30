"""Display court-authored notices with a small, sanitized HTML vocabulary."""

import re
from functools import lru_cache

import bleach
from bleach.sanitizer import ALLOWED_PROTOCOLS
from django import template
from django.utils.safestring import SafeString

from efile.templatetags.md_to_html import ALLOWED_MARKDOWN_ATTRIBUTES

register = template.Library()


@register.filter
def disclaimer_html(value):
    # All external markup passes through the allowlist sanitizer in _sanitize.
    return SafeString(_sanitize(str(value or "")))  # nosec B703


# The same court and state notices render on every Review and Upload page.
@lru_cache(maxsize=256)
def _sanitize(text):
    cleaned = bleach.clean(
        text,
        tags={"p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "a"},
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    # Drop spacer paragraphs and redundant breaks; site CSS owns block spacing.
    whitespace = r"(?:\s|&nbsp;|&#0*160;|&#x0*a0;)"
    cleaned = re.sub(rf"<p>(?:{whitespace}|<br>)*</p>", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("\n", "<br>")
    cleaned = re.sub(r"(?:<br>\s*)+", "<br>", cleaned)
    blocks = r"</?(?:p|ul|ol|li)>"
    cleaned = re.sub(rf"(<br>\s*)+(?={blocks})", "", cleaned)
    cleaned = re.sub(rf"({blocks})(?:\s*<br>)+", r"\1", cleaned)
    return re.sub(rf"\A(?:{whitespace}|<br>)+|(?:{whitespace}|<br>)+\Z", "", cleaned)
