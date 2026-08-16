from __future__ import annotations

import importlib
import json
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import streamlit as st


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v10.5"

STORY_PROVIDER_CLOUD = "Ollama Cloud · 기본 추론 모델"
STORY_PROVIDER_FALLBACK = "내장 규칙 기반 · deterministic fallback"
STORY_PROVIDER_LOCAL = "Ollama 로컬 추론 모델"
STORY_PROVIDER_OPENAI = "OpenAI-compatible API · 외부 추론 모델"
STORY_PROVIDER_OPTIONS = [
    STORY_PROVIDER_CLOUD,
    STORY_PROVIDER_FALLBACK,
    STORY_PROVIDER_LOCAL,
    STORY_PROVIDER_OPENAI,
]

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _drop_poisoned_legacy_alias(module_name: str, expected_filename: str) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        return
    module_file = Path(str(getattr(module, "__file__", "") or "")).name
    if module_file != expected_filename:
        del sys.modules[module_name]


for _module_name, _expected_filename in {
    "story_engine_v3": "story_engine_v3.py",
    "story_content_pipeline_v3": "story_content_pipeline_v3.py",
    "story_renderer_v3": "story_renderer_v3.py",
}.items():
    _drop_poisoned_legacy_alias(_module_name, _expected_filename)

import reasoning_engine  # noqa: E402
import card_renderer  # noqa: E402
import story_engine_v3 as story_engine_legacy  # noqa: E402
import story_renderer_v3 as story_renderer_legacy  # noqa: E402
import story_content_pipeline_v3 as story_content_pipeline_legacy  # noqa: E402

importlib.reload(card_renderer)
importlib.reload(story_engine_legacy)
importlib.reload(story_renderer_legacy)
importlib.reload(story_content_pipeline_legacy)

sys.modules["story_engine_v3"] = story_engine_legacy
sys.modules["story_renderer_v3"] = story_renderer_legacy
sys.modules["story_content_pipeline_v3"] = story_content_pipeline_legacy

import story_article_cleaner  # noqa: E402
import story_source_engine_v5  # noqa: E402
import story_graph_engine  # noqa: E402
import story_hook_engine  # noqa: E402
import story_llm_runtime  # noqa: E402
import story_renderer_v4  # noqa: E402
import story_renderer_v5  # noqa: E402
import story_content_pipeline_v5  # noqa: E402
import mode_exporter_v5  # noqa: E402
import story_output_guard  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402

apply_brand_patch(reasoning_engine)

importlib.reload(story_article_cleaner)
importlib.reload(story_source_engine_v5)
importlib.reload(story_graph_engine)
importlib.reload(story_hook_engine)
importlib.reload(story_llm_runtime)
importlib.reload(story_renderer_v4)
importlib.reload(story_renderer_v5)
importlib.reload(story_content_pipeline_v5)
importlib.reload(mode_exporter_v5)
importlib.reload(story_output_guard)

if story_renderer_v4.legacy is story_renderer_v4:
    raise RuntimeError("Story runtime boot failed: renderer legacy dependency points to itself")


def _secret_or_env(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return str(os.environ.get(name, default) or default)


def _current_ollama_api_key() -> str:
    return str(st.session_state.get("ollama_api_key") or _secret_or_env("OLLAMA_API_KEY", "") or "")


def _story_provider_label() -> str:
    value = str(st.session_state.get("provider_story") or "").strip()
    return value if value in STORY_PROVIDER_OPTIONS else STORY_PROVIDER_CLOUD


def _story_transport_mode() -> str:
    label = _story_provider_label()
    if label == STORY_PROVIDER_LOCAL:
        return "local"
    if label == STORY_PROVIDER_FALLBACK:
        return "deterministic"
    if label == STORY_PROVIDER_OPENAI:
        return "openai"
    return "cloud"


def _cloud_story_llm(temperature: float = 0.35) -> dict:
    # Cloud settings deliberately use dedicated keys. A stale OLLAMA_BASE_URL or
    # session localhost value must never override the hosted Story default.
    base_url = _secret_or_env("OLLAMA_CLOUD_BASE_URL", story_llm_runtime.DEFAULT_OLLAMA_BASE_URL)
    model = _secret_or_env("OLLAMA_CLOUD_MODEL", story_llm_runtime.DEFAULT_OLLAMA_MODEL)
    return story_llm_runtime.ollama_config(
        base_url=base_url,
        model=model,
        temperature=temperature,
        api_key=_current_ollama_api_key(),
    )


def _local_story_llm(temperature: float = 0.35) -> dict:
    base_url = str(
        st.session_state.get("ollama_base_url")
        or _secret_or_env(
            "OLLAMA_LOCAL_BASE_URL",
            _secret_or_env("OLLAMA_BASE_URL", story_llm_runtime.DEFAULT_LOCAL_OLLAMA_BASE_URL),
        )
    )
    model = str(
        st.session_state.get("ollama_model")
        or _secret_or_env(
            "OLLAMA_LOCAL_MODEL",
            _secret_or_env("OLLAMA_MODEL", story_llm_runtime.DEFAULT_LOCAL_OLLAMA_MODEL),
        )
    )
    return story_llm_runtime.ollama_config(
        base_url=base_url,
        model=model,
        temperature=temperature,
        api_key="",
    )


def _configured_story_llm(temperature: float = 0.35) -> dict:
    return _local_story_llm(temperature) if _story_transport_mode() == "local" else _cloud_story_llm(temperature)


def _migrate_story_provider_state() -> None:
    migration_key = "_story_provider_cloud_default_v106"
    if not st.session_state.get(migration_key):
        current = str(st.session_state.get("provider_story") or "")
        stale_local = str(st.session_state.get("ollama_base_url") or "").startswith("http://localhost")
        if not current or current == STORY_PROVIDER_FALLBACK or (current == STORY_PROVIDER_LOCAL and stale_local):
            st.session_state["provider_story"] = STORY_PROVIDER_CLOUD
        st.session_state[migration_key] = True

    # The cloud path is authoritative. This also clears stale localhost widget
    # state left by older deployments before app_v2 builds provider_config().
    if _story_transport_mode() == "cloud":
        cloud = _cloud_story_llm()
        st.session_state["ollama_base_url"] = cloud["base_url"]
        st.session_state["ollama_model"] = cloud["model"]
    elif _story_transport_mode() == "local":
        current_base = str(st.session_state.get("ollama_base_url") or "")
        if story_llm_runtime.is_cloud_ollama(current_base):
            st.session_state["ollama_base_url"] = _secret_or_env(
                "OLLAMA_LOCAL_BASE_URL", story_llm_runtime.DEFAULT_LOCAL_OLLAMA_BASE_URL
            )
            st.session_state["ollama_model"] = _secret_or_env(
                "OLLAMA_LOCAL_MODEL", story_llm_runtime.DEFAULT_LOCAL_OLLAMA_MODEL
            )


_migrate_story_provider_state()

if _story_transport_mode() == "cloud" and not _current_ollama_api_key():
    st.sidebar.info("Story 기본 엔진은 Ollama Cloud입니다. 최초 1회 API Key가 필요합니다.")
    st.sidebar.text_input("Ollama Cloud API Key", type="password", key="ollama_api_key")
elif _story_transport_mode() == "cloud":
    st.sidebar.success("Ollama Cloud API Key 인식 완료")


# v3 remains the transport helper used by the v10 Story pipeline. Its historical
# Ollama branch has no Authorization header, so patch only the Cloud branch to use
# Ollama's authenticated native /api/chat endpoint. Local Ollama and every other
# provider keep the legacy implementation unchanged.
_legacy_story_call_model = story_content_pipeline_legacy._call_model


def _call_story_model_with_cloud_auth(config: dict, hero: dict, roles: list[str], pack: dict):
    provider = str(config.get("provider") or story_content_pipeline_v5.PROVIDER_LOCAL)
    base = str(config.get("base_url") or "").rstrip("/")
    if provider != story_content_pipeline_v5.PROVIDER_OLLAMA or not story_llm_runtime.is_cloud_ollama(base):
        return _legacy_story_call_model(config, hero, roles, pack)

    facts = [
        {"type": f.get("fact_type"), "text": f.get("text"), "source_id": f.get("source_id")}
        for f in (pack.get("facts") or [])[:18]
    ]
    system = (
        "You edit premium Japanese financial documentary cards. Use ONLY supplied facts. "
        "Never invent numbers, dates, entities or causes. Return JSON only."
    )
    user = json.dumps(
        {
            "hero": hero,
            "roles": roles,
            "facts": facts,
            "schema": {"cards": [{"role": "same role", "headline": "Japanese", "body": "Japanese, factual"}]},
        },
        ensure_ascii=False,
    )
    try:
        raw = story_content_pipeline_legacy._post_json(
            story_llm_runtime.ollama_api_url(base, "chat"),
            {
                "model": config.get("model") or story_llm_runtime.DEFAULT_OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "options": {"temperature": float(config.get("temperature") or 0.25)},
            },
            story_llm_runtime.ollama_headers(str(config.get("api_key") or "")),
        )
        return story_content_pipeline_legacy._json_from_text(
            ((raw.get("message") or {}).get("content") or "")
        ), None
    except Exception as error:
        return None, f"story reasoning model failed; evidence-bound fallback used: {error}"


story_content_pipeline_legacy._call_model = _call_story_model_with_cloud_auth

_original_story_generate = story_content_pipeline_v5.generate_story_package


def _generate_story_llm_first(*args, **kwargs):
    """Honor the UI provider exactly; Story defaults to authenticated Ollama Cloud."""
    positional = list(args)
    if "config" in kwargs:
        config = dict(kwargs.get("config") or {})
    elif len(positional) >= 3:
        config = dict(positional[2] or {})
    else:
        config = {}

    incoming_provider = str(config.get("provider") or story_content_pipeline_v5.PROVIDER_LOCAL)
    transport_mode = _story_transport_mode()

    # Deterministic is a real fallback, not an alias for Ollama. Only an explicit
    # Ollama selection is rewritten with the authoritative Cloud/local runtime.
    if incoming_provider == story_content_pipeline_v5.PROVIDER_OLLAMA:
        temperature = float(config.get("temperature") or 0.35)
        selected = _local_story_llm(temperature) if transport_mode == "local" else _cloud_story_llm(temperature)
        config = {**config, **selected, "temperature": temperature}

        base_url = str(config.get("base_url") or "")
        model = str(config.get("model") or "")
        api_key = str(config.get("api_key") or "")
        status = story_llm_runtime.check_ollama(base_url, model, api_key=api_key, timeout=5.0)
        st.session_state["story_ollama_status"] = status
        if status.get("auth_required"):
            return story_content_pipeline_v5.StoryGenerationResult(
                {},
                error=(
                    "Ollama Cloud API Key가 필요합니다. Streamlit Secrets의 OLLAMA_API_KEY 또는 "
                    "사이드바 API Key 입력값을 확인하세요."
                ),
            )
        if not status.get("reachable"):
            return story_content_pipeline_v5.StoryGenerationResult(
                {},
                error=f"Ollama에 연결할 수 없습니다: {base_url}. 상세: {status.get('error') or 'unknown error'}",
            )
        if not status.get("model_available"):
            available = ", ".join((status.get("models") or [])[:8]) or "확인된 모델 없음"
            return story_content_pipeline_v5.StoryGenerationResult(
                {},
                error=f"Ollama 연결은 정상이나 모델 '{model}'을 사용할 수 없습니다. 사용 가능 모델: {available}",
            )
    else:
        base_url = str(config.get("base_url") or "")

    if "config" in kwargs:
        kwargs["config"] = config
    elif len(positional) >= 3:
        positional[2] = config

    result = _original_story_generate(*positional, **kwargs)
    if getattr(result, "package", None):
        quality = result.package.setdefault("content_quality", {})
        quality["story_llm_runtime"] = story_llm_runtime.STORY_LLM_RUNTIME_VERSION
        quality["story_llm_provider_ui"] = _story_provider_label()
        quality["story_llm_transport"] = transport_mode
        if incoming_provider == story_content_pipeline_v5.PROVIDER_OLLAMA:
            quality["story_llm_model"] = config.get("model")
            quality["story_llm_base_url"] = config.get("base_url")
            quality["story_llm_default"] = "ollama_cloud" if transport_mode == "cloud" else "ollama_local"
        elif incoming_provider == story_content_pipeline_v5.PROVIDER_LOCAL:
            quality["story_llm_default"] = "deterministic_fallback"
    return result


story_content_pipeline_v5.generate_story_package = _generate_story_llm_first
story_output_guard.apply_generation_guard(story_content_pipeline_v5)

sys.modules["story_engine"] = story_source_engine_v5
sys.modules["story_content_pipeline"] = story_content_pipeline_v5
sys.modules["mode_exporter"] = mode_exporter_v5

_trader_render_card_image = card_renderer.render_card_image
_trader_render_card_png = card_renderer.render_card_png


def _is_story_card(card: dict) -> bool:
    return (
        (card.get("qa") or {}).get("mode") == "story"
        or card.get("card_type") == "story_editorial"
        or str(card.get("set") or "").upper() == "STORY"
    )


def _render_card_image(card: dict, width: int = 1080, height: int = 1350):
    if _is_story_card(card):
        return story_renderer_v5.render_story_card_image(card, width=width, height=height)
    return _trader_render_card_image(card, width=width, height=height)


def _render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    if _is_story_card(card):
        return story_renderer_v5.render_story_card_png(card, width=width, height=height)
    return _trader_render_card_png(card, width=width, height=height)


card_renderer.render_card_image = _render_card_image
card_renderer.render_card_png = _render_card_png
card_renderer._kiyosaki_runtime_router = RUNTIME_TOKEN


# app_v2 still contains the old three-option provider widget. Patch only that
# Story widget at runtime so the visible UI and provider_config() agree with the
# new Cloud-first behavior, without touching Trader or other selectboxes.
_original_sidebar_selectbox = st.sidebar.selectbox
_original_sidebar_text_input = st.sidebar.text_input


def _provider_selectbox(label, options, *args, **kwargs):
    if kwargs.get("key") == "provider_story":
        current = _story_provider_label()
        st.session_state["provider_story"] = current
        kwargs["index"] = STORY_PROVIDER_OPTIONS.index(current)
        return _original_sidebar_selectbox(label, STORY_PROVIDER_OPTIONS, *args, **kwargs)
    return _original_sidebar_selectbox(label, options, *args, **kwargs)


def _provider_text_input(label, *args, **kwargs):
    key = kwargs.get("key")
    if _story_transport_mode() == "cloud" and key == "ollama_base_url":
        value = _cloud_story_llm()["base_url"]
        st.session_state["ollama_base_url"] = value
        st.sidebar.caption(f"Ollama Cloud URL · {value}")
        return value
    if _story_transport_mode() == "cloud" and key == "ollama_model":
        value = _cloud_story_llm()["model"]
        st.session_state["ollama_model"] = value
        st.sidebar.caption(f"Ollama Cloud 모델 · {value}")
        return value
    return _original_sidebar_text_input(label, *args, **kwargs)


_story_llm = _configured_story_llm()
st.sidebar.caption(f"Runtime · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Story · {story_content_pipeline_v5.STORY_CONTENT_PIPELINE_VERSION}")
st.sidebar.caption(f"Cleaner · {story_article_cleaner.STORY_ARTICLE_CLEANER_VERSION}")
st.sidebar.caption(f"Source · {story_source_engine_v5.STORY_SOURCE_ENGINE_VERSION}")
st.sidebar.caption(f"Graph · {story_graph_engine.STORY_GRAPH_ENGINE_VERSION}")
st.sidebar.caption(f"Hook · {story_hook_engine.STORY_HOOK_ENGINE_VERSION}")
st.sidebar.caption(f"LLM Runtime · {story_llm_runtime.STORY_LLM_RUNTIME_VERSION}")
st.sidebar.caption(f"Story AI · {_story_provider_label()}")
if _story_transport_mode() in {"cloud", "local"}:
    st.sidebar.caption(f"Model · {_story_llm.get('model')} · {_story_llm.get('base_url')}")
_ollama_status = st.session_state.get("story_ollama_status") or {}
if _ollama_status:
    if _ollama_status.get("reachable") and _ollama_status.get("model_available"):
        st.sidebar.success("Ollama 연결 · 모델 확인 완료")
    elif _ollama_status.get("auth_required"):
        st.sidebar.warning("Ollama Cloud · API Key 필요")
    elif _ollama_status.get("reachable"):
        st.sidebar.warning("Ollama 연결됨 · 선택 모델 사용 불가")
    else:
        st.sidebar.error("Ollama 연결 실패")
st.sidebar.caption(f"Story Renderer · {story_renderer_v5.STORY_RENDERER_VERSION}")
st.sidebar.caption(f"Excel · {mode_exporter_v5.MODE_EXPORTER_VERSION}")

with patch.object(st.sidebar, "selectbox", new=_provider_selectbox), patch.object(
    st.sidebar, "text_input", new=_provider_text_input
):
    runpy.run_path(str(APP_FILE), run_name="__main__")
