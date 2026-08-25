from django.utils.safestring import SafeData

from efile.templatetags.md_to_html import md_to_html


def test_md_to_html_preserves_safe_markdown():
    result = md_to_html("**Important:** [Court](https://example.com)")

    assert isinstance(result, SafeData)
    assert "<strong>Important:</strong>" in result
    assert '<a href="https://example.com">Court</a>' in result


def test_md_to_html_removes_unsafe_html_and_link_protocols():
    result = md_to_html('<script>alert("xss")</script><img src=x onerror="alert(1)">[Unsafe](javascript:alert(1))')

    assert "<script" not in result
    assert "<img" not in result
    assert "onerror" not in result
    assert "javascript:" not in result
