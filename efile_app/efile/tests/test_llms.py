from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from django.conf import settings
from openai import NotFoundError

from efile.utils.llms import (
    LlmError,
    chat_completion,
    extract_fields_from_file,
    extract_fields_from_text,
    get_config,
    list_available_models,
)


def test_openai_base_url_settings_and_config(monkeypatch):
    """Test that OPENAI_BASE_URL is recognized by get_config and settings."""
    assert hasattr(settings, "OPENAI_BASE_URL")

    custom_url = "https://custom-ai-endpoint.example.com/v1/"
    monkeypatch.setenv("OPENAI_BASE_URL", custom_url)

    assert get_config("openai base url") == custom_url
    assert get_config("open ai")["base url"] == custom_url


@patch("efile.utils.llms.OpenAI")
def test_chat_completion_uses_custom_base_url(mock_openai_cls, monkeypatch):
    """Test that chat_completion passes custom OPENAI_BASE_URL to OpenAI client."""
    custom_url = "https://my-custom-llm-proxy.com/v1/"
    monkeypatch.setenv("OPENAI_BASE_URL", custom_url)
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices[0].finish_reason = "stop"
    mock_response.choices[0].message.content = "hello test response"
    mock_client.chat.completions.create.return_value = mock_response

    result = chat_completion(
        system_message="System prompt",
        user_message="User prompt",
        model="gpt-4o",
        skip_moderation=True,
    )

    assert result == "hello test response"
    mock_openai_cls.assert_called_with(api_key="test-api-key", base_url=custom_url)


def test_llms_exports():
    """Test that standard functions and exceptions are exported."""
    assert callable(chat_completion)
    assert callable(extract_fields_from_text)
    assert callable(extract_fields_from_file)
    assert callable(list_available_models)
    assert issubclass(LlmError, Exception)


def test_pdf_extraction_prefers_inline_responses_file_input(tmp_path: Path):
    pdf_path = tmp_path / "filing.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 native document input")
    openai_client = MagicMock()
    openai_client.responses.create.return_value.output_text = '{"form identifier": "CJD 101B"}'
    diagnostics = {}

    result = extract_fields_from_file(
        pdf_path,
        {"form identifier": "Printed form identifier"},
        openai_client=openai_client,
        model="gpt-test",
        diagnostics=diagnostics,
    )

    assert result == {"form identifier": "CJD 101B"}
    request = openai_client.responses.create.call_args.kwargs
    file_input = request["input"][1]["content"][0]
    assert file_input["type"] == "input_file"
    assert file_input["filename"] == "filing.pdf"
    assert file_input["file_data"].startswith("data:application/pdf;base64,")
    assert diagnostics == {"input_mode": "native_inline_pdf"}
    openai_client.files.create.assert_not_called()


@patch("efile.utils.llms.extract_fields_from_text")
@patch("efile.utils.llms.MarkItDown")
def test_pdf_extraction_falls_back_when_gateway_cannot_read_uploaded_file(
    mock_markitdown_cls, mock_extract_text, tmp_path: Path
):
    pdf_path = tmp_path / "filing.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    openai_client = MagicMock()
    openai_client.files.create.return_value.id = "file-test"
    openai_client.chat.completions.create.side_effect = NotFoundError(
        "Files [file-test] were not found",
        response=httpx.Response(404, request=httpx.Request("POST", "https://llm.example/v1/chat/completions")),
        body={"error": {"message": "Files [file-test] were not found"}},
    )
    mock_markitdown_cls.return_value.convert.return_value.text_content = "Court: Lake County"
    mock_extract_text.return_value = {"court name": "Lake County"}

    result = extract_fields_from_file(
        pdf_path,
        {"court name": "Court name"},
        openai_client=openai_client,
        model="gpt-test",
    )

    assert result == {"court name": "Lake County"}
    mock_extract_text.assert_called_once_with(
        "Court: Lake County",
        {"court name": "Court name"},
        openai_client=openai_client,
        model="gpt-test",
        reasoning_effort="low",
        llm_hint="",
        prompt_version_name=None,
        prompt_name="document_extraction",
    )
    openai_client.files.delete.assert_called_once_with("file-test")
