import json
import logging
from typing import Any, Literal

import tiktoken
from django.conf import settings
from markitdown import MarkItDown
from openai import NotFoundError, OpenAI
from openai import OpenAIError as LlmError  # noqa: F401

logger = logging.getLogger(__name__)


def extract_fields_from_file(
    the_file: str,  # file type
    field_list: dict[str, str],
    openai_client: OpenAI | None = None,
    openai_api: str | None = None,
    model: str = "gpt-5-nano",
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = "low",
    llm_hint: str | None = "",
    process_pdfs_with_ai: bool = True,
    ocr_images_and_pdfs: bool = False,
    ocr_use_google: bool | None = False,
) -> dict[str, Any]:
    """
    Extracts data (in the form of a list of expected fields) from a file using an LLM.

    When the file is a PDF, relies on the OpenAI vision API to interpret the document.
    Note that this may increase cost, but will also improve accuracy.

    If it is another file type that is convertible by Markitdown, it uses Markitdown to
    convert the file to text first.

    Can be combined with define_fields_from_dict to populate Docassemble fields.

    You can provide a hint to the LLM if it would help with data extraction. For example:
    "the document ID is usually found near the top right of the first page."

    You should normally call this function in the background as it may take some time to run,
    especially when ocr_images_and_pdfs is True.

    Args:
        the_file: The file to extract fields from
        field_list (dict[str, str]): A list of fields to extract, with the key being the field name and the value being
                                a description of the field
        openai_client (Optional[OpenAI]): An OpenAI client object. Defaults to None.
        openai_api (Optional[str]): An OpenAI API key. Defaults to None.
        model (str): The model to use for the OpenAI API. Defaults to "gpt-5-nano".
        reasoning_effort (Optional[Literal["minimal", "low", "medium", "high"]]): The reasoning effort to use for the
                                LLM. Defaults to "low".
        llm_hint (Optional[str]): an optional hint to improve processing the text layer with the LLM.
        process_pdfs_with_ai (bool): Whether to process PDFs with the OpenAI API (True) or convert to text first
                                (False). Defaults to True.
        ocr_images_and_pdfs (bool): Whether to perform OCR on PDFs before processing with the OpenAI API.
                                Defaults to False. May be useful if the PDF has a text layer that is incomplete.
        ocr_use_google (Optional[bool]): whether to use Google Vision API instead of local OCR. Only applies if
                                ocr_images_and_pdfs is True


    Returns:
        dict: A dictionary of fields extracted from the file
    """
    system_message = (
        "You are a data extraction assistant. You return answers in JSON format, like: "
        '{"field_name": "value", "field_name2": "value2"}'
    )

    if not llm_hint:
        llm_hint = ""

    user_message = f"""
    Extract only the list of fields below from the attached document. If the field is not present in the document,
    do not include it in the response.
    {llm_hint}

    ```
    {repr(field_list)}
    ```
    """

    if not openai_client:
        if not hasattr(settings, "OPENAI_API_KEY") or not settings.OPENAI_API_KEY:
            return {}
        else:
            openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

    assert openai_client is not None, "An OpenAI client or API key must be provided."

    # when ocr_images_and_pdfs, we can OCR image files, PDFs, and Word documents (which might have embedded images, too)
    if ocr_images_and_pdfs:
        # TODO(brycew): rewrite the file in place to add a text layer using tesseract functionality
        pass

    if not process_pdfs_with_ai:
        md = MarkItDown()
        try:
            conversion_result = md.convert(the_file)
        except Exception as e:
            logger.error(f"Error converting file {the_file}: {e}")
            return {}

        input_text = conversion_result.text_content

        return extract_fields_from_text(
            input_text,
            field_list,
            openai_client=openai_client,
            openai_api=openai_api,
            model=model,
            reasoning_effort=reasoning_effort,
        )

    with open(the_file, "rb") as f:
        file_upload = openai_client.files.create(
            file=f,
            purpose="user_data",
        )

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

    try:
        openai_client.files.delete(file_upload.id)
    except NotFoundError:
        logger.warning(
            f"Warning: Uploaded file not found when attempting to delete temp file; OpenAI file id: {file_upload.id}"
        )
        pass

    assert isinstance(result.choices[0].message.content, str)
    return json.loads(result.choices[0].message.content)


def extract_fields_from_text(
    text: str,
    field_list: dict[str, str],
    openai_client: OpenAI | None = None,
    openai_api: str | None = None,
    temperature: float = 0,
    model="gpt-5-nano",
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = "low",
) -> dict[str, Any]:
    """
    Extracts fields from text.

    Args:
        text (str): The text to extract fields from
        field_list (dict[str, str]): A list of fields to extract, with the key being the field name and the value being
                a description of the field
        openai_client (Optional[OpenAI]): An OpenAI client object. Defaults to None.
        openai_api (Optional[str]): An OpenAI API key. Defaults to None.
        temperature (float): The temperature to use for the OpenAI API. Defaults to 0.
        model (str): The model to use for the OpenAI API. Defaults to "gpt-5-nano".
        reasoning_effort (Optional[Literal["minimal", "low", "medium", "high"]]): The reasoning effort to use for the
                LLM. Defaults to "low".

    Returns:
        dict: A dictionary of fields extracted from the text
    """
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
    )
    assert isinstance(result, dict)
    return result


def chat_completion(
    system_message: str | None = None,
    user_message: str | None = None,
    openai_client: OpenAI | None = None,
    openai_api: str | None = None,
    temperature: float = 0.5,
    json_mode=False,
    model: str = "gpt-4o",
    messages: list[dict[str, str]] | None = None,
    skip_moderation: bool = True,
    openai_base_url: str | None = None,  # "https://api.openai.com/v1/",
    max_output_tokens: int | None = None,
    max_input_tokens: int | None = None,
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None,
) -> list[Any] | dict[str, Any] | str:
    """A light wrapper on the OpenAI chat endpoint.

    Includes support for token limits, minimal error handling, and moderation.

    Args:
        system_message (str): The role the chat engine should play
        user_message (str): The message (data) from the user
        openai_client (Optional[OpenAI]): An OpenAI client object, optional. If omitted, will fall back to creating a
                new OpenAI client with the API key provided as an environment variable
        openai_api (Optional[str]): the API key for an OpenAI client, optional. If provided, a new OpenAI client will
                be created.
        temperature (float): The temperature to use for the GPT API
        json_mode (bool): Whether to use JSON mode for the GPT API. Requires the word `json` in the system message,
                but will add if you omit it.
        model (str): The model to use for the GPT API
        messages (Optional[list[dict[str, str]]]): A list of messages to send to the chat engine. If provided,
                system_message and user_message will be ignored.
        skip_moderation (bool): Whether to skip the OpenAI moderation step, which may save seconds but risks banning
                your account. Only enable when you have full control over the inputs.
        openai_base_url (Optional[str]): The base URL for the OpenAI API. Defaults to value provided in the
                configuration or "https://api.openai.com/v1/".
        max_output_tokens (Optional[int]): The maximum number of tokens to return from the API. Defaults to 16380.
        max_input_tokens (Optional[int]): The maximum number of tokens to send to the API. Defaults to 128000.
        reasoning_effort (Optional[Literal["minimal", "low", "medium", "high"]]) = None: The reasoning effort to use
                for thinking models. Defaults to value provided in the configuration or "low".

    Returns:
        A string with the response from the API endpoint or JSON data if json_mode is True
    """
    if not reasoning_effort:
        reasoning_effort = "low"

    if not openai_base_url:
        openai_base_url = "https://api.openai.com/v1/"

    elif openai_api:
        openai_client = OpenAI(api_key=openai_api)
    elif messages and json_mode and not any("json" in message["content"].lower() for message in messages):
        logger.warning(
            "Warning: No messages contain the word 'json' but json_mode is set to True. Adding 'json' silently"
        )
        messages.append({"role": "system", "content": "Respond only with a JSON object"})

    if not messages:
        assert isinstance(system_message, (str))
        assert isinstance(user_message, (str))
        messages = [
            {"role": "system", "content": str(system_message)},
            {"role": "user", "content": str(user_message)},
        ]

    if openai_base_url:
        openai_client = None  # Always override client in this circumstance

    if not openai_client:
        if openai_api:
            openai_base_url = openai_base_url or "https://api.openai.com/v1/"
            openai_client = OpenAI(api_key=openai_api, base_url=openai_base_url)
        elif not hasattr(settings, "OPENAI_API_KEY") or not settings.OPENAI_API_KEY:
            return ""
        else:
            openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

    if not openai_client:
        raise Exception(
            "You need to pass an OpenAI client or API key to use this function, or the API key needs to"
            "be set in the environment or Docassemble configuration. Try adding a new section in your global"
            "config that looks like this:\n\nopen ai:\n    key: sk-..."
        )

    try:
        encoding = tiktoken.encoding_for_model(model)
    except Exception:
        # We can try encoding for gpt-4o because it seems like OpenAI isn't really changing the encoding anymore
        encoding = tiktoken.encoding_for_model("gpt-4o")

    token_count = len(encoding.encode(str(messages)))

    # Set the max tokens to a reasonable default if not provided. This is reasonable for current models. The ones with
    # smaller limits are mostly obsolete now

    if model == "gpt-4" or (model and (model.startswith("gpt-4-") or model.startswith("gpt-3.5"))):
        max_output_tokens = max_output_tokens or 4096
        max_input_tokens = max_input_tokens or 32768
    else:
        max_output_tokens = max_output_tokens or 16380
        max_input_tokens = max_input_tokens or 128000

    if token_count > max_input_tokens:
        raise Exception(f"Input to OpenAI is too long ({token_count} tokens). Maximum is {max_input_tokens} tokens.")

    if not skip_moderation and openai_base_url == "https://api.openai.com/v1/":
        # Currently only checking if we're using the OpenAI endpoint
        moderation_response = openai_client.moderations.create(input=str(messages))
        if moderation_response.results[0].flagged:
            raise Exception(f"OpenAI moderation error: {moderation_response.results[0]}")

    # Thinking models (o1, o3, gpt-5) don't support temperature parameter
    is_thinking_model = any(model.startswith(prefix) for prefix in ["o1", "o3", "gpt-5"])

    # Build completion parameters based on model type
    if is_thinking_model:
        # Thinking models don't support temperature but do support reasoning_effort
        if json_mode:
            response = openai_client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=messages,  # type: ignore[arg-type]
                response_format={"type": "json_object"},
                max_completion_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
            )
        else:
            response = openai_client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_completion_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
            )
    else:
        # Regular models support temperature but not reasoning_effort
        if json_mode:
            response = openai_client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=messages,  # type: ignore[arg-type]
                response_format={"type": "json_object"},
                max_completion_tokens=max_output_tokens,
                temperature=temperature,
            )
        else:
            response = openai_client.chat.completions.create(  # type: ignore[call-overload]
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_completion_tokens=max_output_tokens,
                temperature=temperature,
            )

    # check finish reason
    if response.choices[0].finish_reason != "stop":
        raise Exception(
            f"OpenAI did not finish processing the document. Finish reason: {response.choices[0].finish_reason}"
        )

    if json_mode:
        assert isinstance(response.choices[0].message.content, str)
        # log(f"JSON response is { response.choices[0].message.content }")
        return json.loads(response.choices[0].message.content)
    else:
        # log(f"Response is { response.choices[0].message.content }")
        return response.choices[0].message.content
