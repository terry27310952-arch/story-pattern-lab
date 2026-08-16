from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


STORY_LLM_RUNTIME_VERSION = "story-llm-runtime-v1.1"
DEFAULT_OLLAMA_BASE_URL = "https://ollama.com/api"
DEFAULT_OLLAMA_MODEL = "gpt-oss:20b"
DEFAULT_LOCAL_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_LOCAL_OLLAMA_MODEL = "qwen3:4b"
PROVIDER_OLLAMA = "ollama"


def env_value(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or default)


def is_cloud_ollama(base_url: str) -> bool:
    value = str(base_url or "").rstrip("/").casefold()
    return value in {"https://ollama.com", "https://ollama.com/api"} or value.startswith("https://ollama.com/api/")


def ollama_api_url(base_url: str, route: str) -> str:
    base = str(base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    suffix = "/" + str(route or "").lstrip("/")
    if base.endswith("/api"):
        return base + suffix
    return base + "/api" + suffix


def ollama_headers(api_key: str = "") -> dict[str, str]:
    key = str(api_key or "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def ollama_config(
    base_url: str | None = None,
    model: str | None = None,
    temperature: float = 0.35,
    api_key: str | None = None,
) -> dict:
    endpoint = str(base_url or env_value("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)).rstrip("/")
    default_model = DEFAULT_OLLAMA_MODEL if is_cloud_ollama(endpoint) else DEFAULT_LOCAL_OLLAMA_MODEL
    selected_model = str(model or env_value("OLLAMA_MODEL", default_model))
    key = str(api_key if api_key is not None else env_value("OLLAMA_API_KEY", ""))
    return {
        "provider": PROVIDER_OLLAMA,
        "base_url": endpoint,
        "model": selected_model,
        "api_key": key,
        "temperature": float(temperature),
        "ollama_cloud": is_cloud_ollama(endpoint),
        "runtime_source": "OLLAMA_CLOUD_DEFAULT" if is_cloud_ollama(endpoint) else "OLLAMA_SELF_HOSTED",
    }


def default_story_llm_config(temperature: float = 0.35) -> dict:
    """Story defaults to Ollama Cloud so hosted Streamlit can reach the model.

    Set OLLAMA_BASE_URL=http://localhost:11434 and OLLAMA_MODEL=qwen3:4b to
    explicitly use a local/self-hosted Ollama server instead.
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
    if have == req + "-cloud" or req == have + "-cloud":
        return True
    return False


def check_ollama(base_url: str, model: str, api_key: str = "", timeout: float = 3.5) -> dict:
    endpoint = str(base_url or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    requested_model = str(model or (DEFAULT_OLLAMA_MODEL if is_cloud_ollama(endpoint) else DEFAULT_LOCAL_OLLAMA_MODEL))
    cloud = is_cloud_ollama(endpoint)
    key = str(api_key or "").strip()
    if cloud and not key:
        return {
            "reachable": False,
            "model_available": False,
            "auth_required": True,
            "base_url": endpoint,
            "model": requested_model,
            "models": [],
            "error": "OLLAMA_API_KEY is required for direct Ollama Cloud API access.",
        }

    url = ollama_api_url(endpoint, "tags")
    try:
        req = Request(url, headers={"Accept": "application/json", **ollama_headers(key)}, method="GET")
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = _model_names(payload if isinstance(payload, dict) else {})
        available = any(_model_matches(requested_model, name) for name in names)
        return {
            "reachable": True,
            "model_available": available,
            "auth_required": False,
            "base_url": endpoint,
            "model": requested_model,
            "models": names,
            "error": "" if available else f"Model '{requested_model}' is not available from this Ollama host/account.",
        }
    except Exception as error:
        return {
            "reachable": False,
            "model_available": False,
            "auth_required": False,
            "base_url": endpoint,
            "model": requested_model,
            "models": [],
            "error": str(error),
        }
