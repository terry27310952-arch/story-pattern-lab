from __future__ import annotations

import importlib
import os
import runpy
import sys
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v10.5"

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


def _configured_story_llm(temperature: float = 0.35) -> dict:
    """Ollama Cloud is the hosted Story default; env/session can opt into self-hosted Ollama."""
    base_url = str(
        st.session_state.get("ollama_base_url")
        or _secret_or_env("OLLAMA_BASE_URL", story_llm_runtime.DEFAULT_OLLAMA_BASE_URL)
    )
    cloud_default_model = story_llm_runtime.DEFAULT_OLLAMA_MODEL
    local_default_model = story_llm_runtime.DEFAULT_LOCAL_OLLAMA_MODEL
    default_model = cloud_default_model if story_llm_runtime.is_cloud_ollama(base_url) else local_default_model
    model = str(st.session_state.get("ollama_model") or _secret_or_env("OLLAMA_MODEL", default_model))
    return story_llm_runtime.ollama_config(
        base_url=base_url,
        model=model,
        temperature=temperature,
        api_key=_current_ollama_api_key(),
    )


_story_llm = _configured_story_llm()
_story_provider_init_key = "_story_default_provider_ollama_cloud_v1"
if not st.session_state.get(_story_provider_init_key):
    current_story_provider = str(st.session_state.get("provider_story") or "")
    if not current_story_provider or current_story_provider.startswith("내장 규칙 기반"):
        st.session_state["provider_story"] = "Ollama 로컬 추론 모델"
    st.session_state.setdefault("ollama_base_url", _story_llm.get("base_url"))
    st.session_state.setdefault("ollama_model", _story_llm.get("model"))
    st.session_state[_story_provider_init_key] = True

if story_llm_runtime.is_cloud_ollama(str(_story_llm.get("base_url") or "")) and not _current_ollama_api_key():
    st.sidebar.info("Streamlit Cloud에서는 Ollama Cloud API를 사용합니다. 최초 1회 API Key가 필요합니다.")
    st.sidebar.text_input("Ollama Cloud API Key", type="password", key="ollama_api_key")


_original_story_generate = story_content_pipeline_v5.generate_story_package


def _generate_story_llm_first(*args, **kwargs):
    """Run Story with Ollama by default, validating cloud/local transport before generation."""
    positional = list(args)
    if "config" in kwargs:
        config = dict(kwargs.get("config") or {})
    elif len(positional) >= 3:
        config = dict(positional[2] or {})
    else:
        config = {}

    incoming_provider = str(config.get("provider") or story_content_pipeline_v5.PROVIDER_LOCAL)
    promoted = incoming_provider == story_content_pipeline_v5.PROVIDER_LOCAL
    if incoming_provider in {story_content_pipeline_v5.PROVIDER_LOCAL, story_content_pipeline_v5.PROVIDER_OLLAMA}:
        temperature = float(config.get("temperature") or 0.35)
        config = {**config, **_configured_story_llm(temperature), "temperature": temperature}

    base_url = str(config.get("base_url") or story_llm_runtime.DEFAULT_OLLAMA_BASE_URL)
    model = str(config.get("model") or story_llm_runtime.DEFAULT_OLLAMA_MODEL)
    api_key = str(config.get("api_key") or _current_ollama_api_key())

    if str(config.get("provider") or "") == story_content_pipeline_v5.PROVIDER_OLLAMA:
        status = story_llm_runtime.check_ollama(base_url, model, api_key=api_key, timeout=3.5)
        st.session_state["story_ollama_status"] = status
        if status.get("auth_required"):
            return story_content_pipeline_v5.StoryGenerationResult(
                {},
                error=(
                    "Ollama Cloud API Key가 필요합니다. 사이드바의 'Ollama Cloud API Key'에 키를 입력하거나 "
                    "Streamlit Secrets에 OLLAMA_API_KEY를 추가한 뒤 다시 생성하세요."
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

        if story_llm_runtime.is_cloud_ollama(base_url):
            # Ollama Cloud exposes an OpenAI-compatible endpoint. Use it here because
            # Cloud does not support Ollama structured-output `format=json` while our
            # prompt/parser already enforce JSON at the application layer.
            config = {
                **config,
                "provider": story_content_pipeline_v5.PROVIDER_OPENAI_COMPATIBLE,
                "base_url": "https://ollama.com/v1",
                "api_key": api_key,
                "model": model,
                "ollama_cloud": True,
                "runtime_source": "OLLAMA_CLOUD_OPENAI_COMPAT",
            }

    if "config" in kwargs:
        kwargs["config"] = config
    elif len(positional) >= 3:
        positional[2] = config

    result = _original_story_generate(*positional, **kwargs)
    if getattr(result, "package", None):
        quality = result.package.setdefault("content_quality", {})
        quality["story_llm_default"] = "ollama"
        quality["story_llm_runtime"] = story_llm_runtime.STORY_LLM_RUNTIME_VERSION
        quality["story_llm_model"] = config.get("model")
        quality["story_llm_base_url"] = base_url
        quality["story_llm_transport"] = "ollama_cloud_openai_compatible" if config.get("ollama_cloud") else "ollama_native"
        quality["story_llm_auto_promoted"] = promoted
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

_story_llm = _configured_story_llm()
st.sidebar.caption(f"Runtime · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Story · {story_content_pipeline_v5.STORY_CONTENT_PIPELINE_VERSION}")
st.sidebar.caption(f"Cleaner · {story_article_cleaner.STORY_ARTICLE_CLEANER_VERSION}")
st.sidebar.caption(f"Source · {story_source_engine_v5.STORY_SOURCE_ENGINE_VERSION}")
st.sidebar.caption(f"Graph · {story_graph_engine.STORY_GRAPH_ENGINE_VERSION}")
st.sidebar.caption(f"Hook · {story_hook_engine.STORY_HOOK_ENGINE_VERSION}")
st.sidebar.caption(f"LLM Runtime · {story_llm_runtime.STORY_LLM_RUNTIME_VERSION}")
st.sidebar.caption(
    f"Story LLM · Ollama · {_story_llm.get('model')} · {_story_llm.get('runtime_source')}"
)
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

runpy.run_path(str(APP_FILE), run_name="__main__")
