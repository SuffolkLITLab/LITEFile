"""Small OpenAI-compatible helpers used for document field extraction."""

import json
import logging
import mimetypes
import os
import re
from typing import Any, Literal

import tiktoken
from django.conf import settings
from markitdown import MarkItDown
from openai import NotFoundError, OpenAI
from openai import OpenAIError as LlmError

logger = logging.getLogger(__name__)


def log(message: Any, status: str = "info") -> None:
    """Log a message using the application's logger."""
    if status == "error":
        logger.error(str(message))
    elif status == "warning":
        logger.warning(str(message))
    else:
        logger.info(str(message))


def get_config(key: str, default: Any = None) -> Any:
    """Read an LLM setting from environment variables or Django settings."""
    key_lower = key.lower()
    if key_lower == "open ai":
        return {
            "key": os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None),
            "base url": os.getenv("OPENAI_BASE_URL") or getattr(settings, "OPENAI_BASE_URL", None),
        }

    if key_lower in ("openai api key", "openai_api_key"):
        return os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)

    if key_lower in ("openai base url", "openai_base_url"):
        return os.getenv("OPENAI_BASE_URL") or getattr(settings, "OPENAI_BASE_URL", None)

    env_var = key.upper().replace(" ", "_")
    value = os.getenv(env_var)
    if value is not None:
        return value

    value = getattr(settings, env_var, None)
    return value if value is not None else default


if os.getenv("OPENAI_API_KEY"):
    configured_base_url = get_config("open ai", {}).get("base url")
    client: OpenAI | None = OpenAI(base_url=configured_base_url) if configured_base_url else OpenAI()
elif get_config("openai api key"):
    open_ai_config = get_config("open ai", {}) or {}
    client = OpenAI(
        api_key=open_ai_config.get("key") or get_config("openai api key"),
        base_url=(open_ai_config.get("base url") or get_config("openai base url") or "https://api.openai.com/v1/"),
    )
else:
    client = None


DEFAULT_MODEL_SETS: dict[str, list[list[str]]] = {
    "small": [
        ["gpt-5-nano", "gpt-4.1-nano", "gpt-4o-mini"],
        ["o4-mini", "o3-mini", "gpt-4o-mini"],
        ["claude-3-5-haiku", "claude-3-haiku"],
        ["gemini-2.5-flash-lite", "gemini-2.5-flash"],
    ],
    "medium": [
        ["gpt-5-mini", "gpt-4.1-mini", "gpt-4o"],
        ["o3", "gpt-4o"],
        ["claude-3-7-sonnet", "claude-3-5-sonnet"],
        ["gemini-2.5-flash"],
    ],
    "large": [
        ["gpt-5", "gpt-4.1", "gpt-4o"],
        ["o1", "o1-preview", "gpt-4o"],
        ["claude-3-7-sonnet", "claude-3-opus"],
        ["gemini-2.5-pro"],
    ],
}

MODEL_TYPE_FALLBACKS = {
    "small": "gpt-5-nano",
    "medium": "gpt-5-mini",
    "large": "gpt-5",
}

MODEL_FAMILY_PATTERNS: dict[str, list[str]] = {
    "openai": [
        r"^gpt",
        r"^o[0-9]",
        r"^chatgpt",
        r"^codex",
        r"^text-embedding",
        r"^whisper",
        r"^tts",
        r"^omni",
    ],
    "google": [r"gemini", r"^models/gemini", r"google"],
    "anthropic": [r"claude", r"anthropic"],
    "mistral": [r"mistral", r"mixtral", r"codestral", r"ministral"],
    "qwen": [r"qwen"],
    "deepseek": [r"deepseek"],
    "meta": [r"llama", r"meta-llama", r"\bl[0-9]{1,2}m?a?\b"],
}


def _extract_model_id(model: Any) -> str | None:
    """Extract a model ID from an OpenAI model object or dictionary."""
    model_id = getattr(model, "id", None)
    if isinstance(model_id, str):
        return model_id
    if isinstance(model, dict) and isinstance(model.get("id"), str):
        return model["id"]
    return None


def list_available_models(openai_client: OpenAI | None = None) -> list[str]:
    """Return model IDs available on the configured OpenAI-compatible provider."""
    openai_client = openai_client or client
    if not openai_client:
        log("Warning: No OpenAI client available to fetch models list.", "warning")
        return []

    try:
        available_models: list[str] = []
        seen = set()
        for model in openai_client.models.list():
            model_id = _extract_model_id(model)
            if not model_id or model_id.lower() in seen:
                continue
            seen.add(model_id.lower())
            available_models.append(model_id)
        return available_models
    except Exception as error:
        log(f"Error retrieving models list from OpenAI endpoint: {error}", "error")
        return []


def get_available_models(
    candidate_models: list[str],
    openai_client: OpenAI | None = None,
    available_models: list[str] | None = None,
) -> list[str]:
    """Return candidate models that exist on the configured provider."""
    if available_models is None:
        available_models = list_available_models(openai_client)
    normalized_models = {model.lower(): model for model in available_models}
    return [
        normalized_models[model_name.lower()]
        for model_name in candidate_models
        if model_name.lower() in normalized_models
    ]


def _normalize_model_sets(model_sets: Any) -> list[list[str]]:
    if not isinstance(model_sets, list):
        return []
    if model_sets and all(isinstance(item, str) for item in model_sets):
        return [model_sets]
    return [
        [model for model in entry if isinstance(model, str)]
        for entry in model_sets
        if isinstance(entry, list) and any(isinstance(model, str) for model in entry)
    ]


def get_first_available_model_set(
    preferred_model_sets: list[list[str]],
    openai_client: OpenAI | None = None,
    require_full_set: bool = True,
    return_partial_if_needed: bool = True,
    fallback_to_first_small_model: bool = True,
) -> list[str]:
    """Return the first usable model set from a prioritized list."""
    first_partial_match: list[str] = []
    available_models = list_available_models(openai_client)
    for model_set in _normalize_model_sets(preferred_model_sets):
        available = get_available_models(model_set, available_models=available_models)
        if (require_full_set and len(available) == len(model_set)) or (not require_full_set and available):
            return available
        if return_partial_if_needed and available and not first_partial_match:
            first_partial_match = available

    if return_partial_if_needed and first_partial_match:
        return first_partial_match
    if fallback_to_first_small_model:
        small_model = get_first_small_model(openai_client)
        if small_model:
            return [small_model]
    return []


def detect_model_family(model_name: str) -> str:
    """Infer a provider family from a model name."""
    lowered = model_name.lower()
    for family, patterns in MODEL_FAMILY_PATTERNS.items():
        if any(re.search(pattern, lowered) for pattern in patterns):
            return family
    match = re.split(r"[-_.:/]", lowered, maxsplit=1)
    return match[0] if match and match[0] else "unknown"


def get_available_model_families(
    openai_client: OpenAI | None = None,
) -> dict[str, list[str]]:
    """Group available models by provider family."""
    families: dict[str, list[str]] = {}
    for model_name in list_available_models(openai_client):
        families.setdefault(detect_model_family(model_name), []).append(model_name)
    return families


def get_first_small_model(
    openai_client: OpenAI | None = None,
    keywords: list[str] | None = None,
) -> str | None:
    """Return the first available model whose name suggests it is small."""
    if keywords is None:
        keywords = ["nano", "mini", "small", "lite", "haiku", "turbo", "fast"]
    lowered_keywords = [keyword.lower() for keyword in keywords]
    return next(
        (
            model_id
            for model_id in list_available_models(openai_client)
            if any(keyword in model_id.lower() for keyword in lowered_keywords)
        ),
        None,
    )


def get_default_model(
    model_type: str = "small",
    openai_client: OpenAI | None = None,
) -> str:
    """Choose a configured or available model, with a sensible fallback."""
    open_ai_config = get_config("open ai", {}) or {}
    normalized_model_type = (model_type or "small").lower()
    config_model = (
        open_ai_config.get(f"default {normalized_model_type} model")
        or get_config(f"openai default {normalized_model_type} model")
        or open_ai_config.get("default model")
        or get_config("openai default model")
    )
    if config_model:
        return config_model

    configured_sets = open_ai_config.get("model sets", [])
    if isinstance(configured_sets, dict):
        configured_sets = configured_sets.get(normalized_model_type, [])
    selected_set = get_first_available_model_set(
        _normalize_model_sets(configured_sets) + DEFAULT_MODEL_SETS.get(normalized_model_type, []),
        openai_client=openai_client,
    )
    if selected_set:
        return selected_set[0]

    if normalized_model_type == "small":
        small_model = get_first_small_model(openai_client)
        if small_model:
            return small_model
    return MODEL_TYPE_FALLBACKS.get(normalized_model_type, MODEL_TYPE_FALLBACKS["small"])


def chat_completion(
    system_message: str | None = None,
    user_message: str | None = None,
    openai_client: OpenAI | None = None,
    openai_api: str | None = None,
    temperature: float = 0.5,
    json_mode: bool = False,
    model: str | None = None,
    messages: list[dict[str, str]] | None = None,
    skip_moderation: bool = True,
    openai_base_url: str | None = None,
    max_output_tokens: int | None = None,
    max_input_tokens: int | None = None,
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None,
) -> list[Any] | dict[str, Any] | str:
    """Call an OpenAI-compatible chat endpoint and optionally parse JSON."""
    config = get_config("open ai", {}) or {}
    reasoning_effort = reasoning_effort or config.get("reasoning effort") or "low"
    configured_base_url = config.get("base url") or get_config("openai base url")
    explicit_base_url = openai_base_url is not None
    openai_base_url = openai_base_url or configured_base_url or "https://api.openai.com/v1/"

    if messages and json_mode and not any("json" in message.get("content", "").lower() for message in messages):
        log(
            "Warning: json_mode is enabled but no message mentions JSON; adding an instruction.",
            "warning",
        )
        messages = list(messages) + [{"role": "system", "content": "Respond only with a JSON object"}]

    if not messages:
        if not isinstance(system_message, str) or not isinstance(user_message, str):
            raise TypeError("system_message and user_message must be strings")
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

    if not openai_client:
        if openai_api:
            openai_client = OpenAI(api_key=openai_api, base_url=openai_base_url)
        elif (explicit_base_url or configured_base_url) and openai_base_url != "https://api.openai.com/v1/":
            api_key = os.getenv("OPENAI_API_KEY") or get_config("openai api key")
            openai_client = (
                OpenAI(api_key=api_key, base_url=openai_base_url) if api_key else OpenAI(base_url=openai_base_url)
            )
        else:
            openai_client = client

    if not openai_client:
        raise RuntimeError("An OpenAI client or API key must be provided to use this function.")

    model = model or get_default_model(openai_client=openai_client)
    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        encoding = tiktoken.encoding_for_model("gpt-4o")

    token_count = len(encoding.encode(str(messages)))
    if model == "gpt-4" or model.startswith(("gpt-4-", "gpt-3.5")):
        max_output_tokens = max_output_tokens or 4096
        max_input_tokens = max_input_tokens or 32768
    else:
        max_output_tokens = max_output_tokens or 16380
        max_input_tokens = max_input_tokens or 128000
    if token_count > max_input_tokens:
        raise RuntimeError(f"Input to OpenAI is too long ({token_count} tokens). Maximum is {max_input_tokens} tokens.")

    if not skip_moderation and openai_base_url == "https://api.openai.com/v1/":
        moderation_response = openai_client.moderations.create(input=str(messages))
        if moderation_response.results[0].flagged:
            raise RuntimeError(f"OpenAI moderation error: {moderation_response.results[0]}")

    is_thinking_model = model.startswith(("o1", "o3", "gpt-5"))
    parameters: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_output_tokens,
    }
    if json_mode:
        parameters["response_format"] = {"type": "json_object"}
    if is_thinking_model:
        parameters["reasoning_effort"] = reasoning_effort
    else:
        parameters["temperature"] = temperature

    response = openai_client.chat.completions.create(**parameters)
    finish_reason = response.choices[0].finish_reason
    if finish_reason != "stop":
        raise RuntimeError(f"OpenAI did not finish processing the document. Finish reason: {finish_reason}")

    content = response.choices[0].message.content
    if json_mode:
        if not isinstance(content, str):
            raise TypeError("The JSON response did not contain text content")
        return json.loads(content)
    return content


def extract_fields_from_text(
    text: str,
    field_list: dict[str, str],
    openai_client: OpenAI | None = None,
    openai_api: str | None = None,
    temperature: float = 0,
    model: str | None = None,
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = "low",
    openai_base_url: str | None = None,
) -> dict[str, Any]:
    """Extract the requested fields from text and return them as a dictionary."""
    system_message = f"""
    Extract the list of fields from the text supplied by the user.

    ```
    {repr(field_list)}
    ```

    If a field cannot be defined from the text, omit it from the JSON response.
    """
    result = chat_completion(
        system_message=system_message,
        user_message=text,
        model=model,
        openai_client=openai_client,
        openai_api=openai_api,
        temperature=temperature,
        json_mode=True,
        reasoning_effort=reasoning_effort,
        openai_base_url=openai_base_url,
    )
    if not isinstance(result, dict):
        raise TypeError("Field extraction did not return a JSON object")
    return result


def _file_path_and_mimetype(the_file: Any) -> tuple[str, str]:
    """Get a local path and MIME type from a path or file-like wrapper."""
    if hasattr(the_file, "path"):
        path_attribute = the_file.path
        file_path = path_attribute() if callable(path_attribute) else path_attribute
        mimetype = getattr(the_file, "mimetype", "")
    else:
        file_path = os.fspath(the_file)
        mimetype = ""

    file_path = os.fspath(file_path)
    return file_path, mimetype or mimetypes.guess_type(file_path)[0] or ""


def extract_fields_from_file(
    the_file: Any,
    field_list: dict[str, str],
    openai_client: OpenAI | None = None,
    openai_api: str | None = None,
    model: str | None = None,
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = "low",
    llm_hint: str | None = "",
    process_pdfs_with_ai: bool = True,
    ocr_images_and_pdfs: bool = False,
    ocr_use_google: bool = False,
    openai_base_url: str | None = None,
) -> dict[str, Any]:
    """Extract requested fields from a local file and return a dictionary.

    ``the_file`` may be a path, ``pathlib.Path``, a one-item list of paths, or an
    object exposing a ``path`` attribute or method. The function never assigns
    extracted values to application variables.
    """
    system_message = (
        "You are a data extraction assistant. You return answers in JSON format, "
        'like: {"field_name": "value", "field_name2": "value2"}'
    )
    user_message = f"""
    Extract only the list of fields below from the attached document. If the field is not present in the document, do not include it in the response.
    {llm_hint or ""}

    ```
    {repr(field_list)}
    ```
    """

    if isinstance(the_file, list | tuple):
        if not the_file:
            raise ValueError("the_file cannot be an empty list")
        the_file = the_file[0]

    file_path, mimetype = _file_path_and_mimetype(the_file)

    if (
        mimetype == "application/pdf"
        or "image" in mimetype
        or mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ) and ocr_images_and_pdfs:
        make_ocr_pdf = getattr(the_file, "make_ocr_pdf", None)
        if callable(make_ocr_pdf):
            make_ocr_pdf(use_google=ocr_use_google)
            file_path, mimetype = _file_path_and_mimetype(the_file)

    if mimetype != "application/pdf" or not process_pdfs_with_ai:
        try:
            conversion_result = MarkItDown().convert(file_path)
        except Exception as error:
            log(f"Error converting file {file_path}: {error}", "error")
            return {}
        return extract_fields_from_text(
            conversion_result.text_content,
            field_list,
            openai_client=openai_client,
            openai_api=openai_api,
            model=model,
            reasoning_effort=reasoning_effort,
            openai_base_url=openai_base_url,
        )

    if not openai_client:
        if openai_api:
            openai_client = OpenAI(
                api_key=openai_api,
                base_url=openai_base_url or "https://api.openai.com/v1/",
            )
        elif openai_base_url:
            api_key = os.getenv("OPENAI_API_KEY") or get_config("openai api key")
            openai_client = (
                OpenAI(api_key=api_key, base_url=openai_base_url) if api_key else OpenAI(base_url=openai_base_url)
            )
        else:
            openai_client = client

    if not openai_client:
        raise RuntimeError("An OpenAI client or API key must be provided.")
    model = model or get_default_model(openai_client=openai_client)

    with open(file_path, "rb") as file_handle:
        file_upload = openai_client.files.create(file=file_handle, purpose="user_data")

    try:
        try:
            result = openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {
                        "role": "user",
                        "content": [
                            {"type": "file", "file": {"file_id": file_upload.id}},
                            {"type": "text", "text": user_message},
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                reasoning_effort=reasoning_effort,
            )
        except NotFoundError:
            # Some OpenAI-compatible gateways accept Files API uploads but do
            # not make those IDs available to Chat Completions. Text PDFs can
            # still use the same extraction prompt without losing the feature.
            log("The LLM gateway could not read its uploaded file; extracting PDF text instead.", "warning")
            try:
                text = MarkItDown().convert(file_path).text_content
            except Exception as error:
                log(f"Error converting PDF {file_path}: {error}", "error")
                return {}
            return extract_fields_from_text(
                text,
                field_list,
                openai_client=openai_client,
                model=model,
                reasoning_effort=reasoning_effort,
            )
    finally:
        try:
            openai_client.files.delete(file_upload.id)
        except NotFoundError:
            log(
                f"Uploaded file was not found while deleting the temporary file (OpenAI file id: {file_upload.id}).",
                "warning",
            )

    content = result.choices[0].message.content
    if not isinstance(content, str):
        raise TypeError("The JSON response did not contain text content")
    return json.loads(content)


__all__ = [
    "LlmError",
    "chat_completion",
    "extract_fields_from_text",
    "extract_fields_from_file",
    "list_available_models",
    "get_available_models",
    "get_first_available_model_set",
    "detect_model_family",
    "get_available_model_families",
    "get_first_small_model",
    "get_default_model",
]
