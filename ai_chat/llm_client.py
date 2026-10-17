import json
from typing import Any

import requests

from core.config import settings
from ai_chat.timing import timing


DEFAULT_MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def generate_text(
    *,
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    num_predict: int = 500,
    timeout: int = 120,
) -> str:
    if settings.openai_api_key:
        return generate_openai_text(
            prompt=prompt,
            model=settings.openai_model,
            timeout=timeout,
        )

    with timing("llm_call", model=model):
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": num_predict,
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

    return (data.get("response") or "").strip()


def generate_openai_text(*, prompt: str, model: str, timeout: int = 120) -> str:
    payload = {
        "model": model,
        "input": prompt,
    }
    data = _post_openai(payload=payload, model=model, timeout=timeout)
    return _extract_output_text(data)


def generate_openai_json(
    *,
    prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    model: str | None = None,
    timeout: int = 60,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    selected_model = model or settings.openai_model
    payload = {
        "model": selected_model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    if reasoning_effort is not None:
        payload['reasoning'] = {'effort': reasoning_effort}
    data = _post_openai(payload=payload, model=selected_model, timeout=timeout)
    return json.loads(_extract_output_text(data))


def _post_openai(*, payload: dict[str, Any], model: str, timeout: int) -> dict[str, Any]:
    with timing("llm_call", model=model, provider="openai"):
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()


def _extract_output_text(data: dict[str, Any]) -> str:
    if data.get("output_text"):
        return str(data["output_text"]).strip()

    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"]).strip()

    raise ValueError("OpenAI response does not contain output text")
