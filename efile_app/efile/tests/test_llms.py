from unittest.mock import MagicMock, patch

from django.conf import settings

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
