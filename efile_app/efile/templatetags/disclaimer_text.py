"""Display court-authored notices with a small, sanitized HTML vocabulary."""

import re

import bleach
from django import template
from django.utils.safestring import SafeString

register = template.Library()


@register.filter
def disclaimer_html(value):
    # Some proxy code tables contain literal backslash escapes inside the JSON
    # string, including quotes around link attributes and paragraph separators.
    text = str(value or "").replace('\\"', '"').replace("\\n", "\n")
    cleaned = bleach.clean(
        text,
        tags={"p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "a"},
        attributes={"a": ["href", "title"]},
        protocols={"https", "http", "mailto"},
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
    cleaned = re.sub(rf"\A(?:{whitespace}|<br>)+|(?:{whitespace}|<br>)+\Z", "", cleaned)
    # All external markup passed through the allowlist sanitizer above.
    return SafeString(cleaned)  # nosec B703
