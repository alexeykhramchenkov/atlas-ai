from typing import Any

import requests

from ai_chat.timing import timing


DEFAULT_MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"


def generate_text(
    *,
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    num_predict: int = 500,
    timeout: int = 120,
) -> str:
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
