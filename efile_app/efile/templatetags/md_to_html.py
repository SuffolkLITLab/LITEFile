import bleach
import markdown
from bleach.sanitizer import ALLOWED_PROTOCOLS
from django import template
from django.utils.safestring import SafeString

ALLOWED_MARKDOWN_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}
ALLOWED_MARKDOWN_ATTRIBUTES = {"a": ["href", "title"]}


def md_to_html(value):
    """Render Markdown while removing unsafe HTML and link protocols."""
    rendered = markdown.markdown(str(value or ""))
    sanitized = bleach.clean(
        rendered,
        tags=ALLOWED_MARKDOWN_TAGS,
        attributes=ALLOWED_MARKDOWN_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    # Bleach enforces the allowlists above before this reviewed safe-output boundary.
    return SafeString(sanitized)  # nosec B703


register = template.Library()
register.filter("md_to_html", md_to_html)
