from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


STORY_LLM_RUNTIME_VERSION = "story-llm-runtime-v1.0"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
PROVIDER_OLLAMA = "ollama"


def env_value(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or default)


def ollama_config(
    base_url: str | None = None,
    model: str | None = None,
    temperature: float = 0.35,
) -> dict:
    return {
        "provider": PROVIDER_OLLAMA,
        "base_url": str(base_url or env_value("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)).rstrip("/"),
        "model": str(model or env_value("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)),
        "temperature": float(temperature),
        "runtime_source": "OLLAMA_DEFAULT",
    }


def default_story_llm_config(temperature: float = 0.35) -> dict:
    """Story defaults to Ollama even when no environment variables were provided.

    Environment variables only override the endpoint/model; they are not required to
    choose Ollama as the Story provider.
    """
    return ollama_config(temperature=temperature)


def _model_names(payload: dict) -> list[str]:
    names: list[str] = []
    for item in payload.get("models") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _model_matches(requested: str, available: str) -> bool:
    req = str(requested or "").strip().casefold()
    have = str(available or "").strip().casefold()
    if not req or not have:
        return False
    if req == have:
        return True
    if have == req + ":latest" or req == have + ":latest":
        return True
    return False


def check_ollama(base_url: str, model: str, timeout: float = 2.0) -> dict:
    endpoint = str(base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    requested_model = str(model or DEFAULT_OLLAMA_MODEL)
    url = endpoint + "/api/tags"
    try:
        req = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = _model_names(payload if isinstance(payload, dict) else {})
        available = any(_model_matches(requested_model, name) for name in names)
        return {
            "reachable": True,
            "model_available": available,
            "base_url": endpoint,
            "model": requested_model,
            "models": names,
            "error": "" if available else f"Model '{requested_model}' is not installed in Ollama.",
        }
    except Exception as error:
        return {
            "reachable": False,
            "model_available": False,
            "base_url": endpoint,
            "model": requested_model,
            "models": [],
            "error": str(error),
        }
