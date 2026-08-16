from __future__ import annotations

import importlib
import os
import runpy
import sys
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v10.3"

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


def _configured_story_llm() -> dict:
    free_base = _secret_or_env("FREE_AI_API_BASE")
    free_model = _secret_or_env("FREE_AI_MODEL")
    free_key = _secret_or_env("FREE_AI_API_KEY")
    if free_base and free_model:
        return {
            "provider": story_content_pipeline_v5.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": free_base,
            "model": free_model,
            "api_key": free_key,
            "runtime_source": "FREE_AI_*",
        }

    ollama_base = _secret_or_env("OLLAMA_BASE_URL")
    ollama_model = _secret_or_env("OLLAMA_MODEL")
    if ollama_base and ollama_model:
        return {
            "provider": story_content_pipeline_v5.PROVIDER_OLLAMA,
            "base_url": ollama_base,
            "model": ollama_model,
            "runtime_source": "OLLAMA_*",
        }
    return {}


_story_llm = _configured_story_llm()
if _story_llm:
    desired_label = (
        "OpenAI-compatible API · 외부 추론 모델"
        if _story_llm.get("provider") == story_content_pipeline_v5.PROVIDER_OPENAI_COMPATIBLE
        else "Ollama 로컬 추론 모델"
    )
    current_story_provider = str(st.session_state.get("provider_story") or "")
    if not current_story_provider or current_story_provider.startswith("내장 규칙 기반"):
        st.session_state["provider_story"] = desired_label
else:
    st.sidebar.warning(
        "Story LLM이 아직 설정되지 않았습니다. 영어/비일본어 원문을 일본어 카드로 만들고 1번 Hook을 창의적으로 생성하려면 "
        "OpenAI-compatible 또는 Ollama 모델 설정이 필요합니다."
    )


_original_story_generate = story_content_pipeline_v5.generate_story_package


def _generate_story_llm_first(*args, **kwargs):
    """Use a configured reasoning model automatically for Story when the UI is still on deterministic fallback."""
    positional = list(args)
    if "config" in kwargs:
        config = dict(kwargs.get("config") or {})
    elif len(positional) >= 3:
        config = dict(positional[2] or {})
    else:
        config = {}

    promoted = False
    if str(config.get("provider") or story_content_pipeline_v5.PROVIDER_LOCAL) == story_content_pipeline_v5.PROVIDER_LOCAL:
        llm = _configured_story_llm()
        if llm:
            promoted = True
            temperature = float(config.get("temperature") or 0.35)
            config = {**config, **llm, "temperature": temperature}
            if "config" in kwargs:
                kwargs["config"] = config
            elif len(positional) >= 3:
                positional[2] = config
        else:
            return story_content_pipeline_v5.StoryGenerationResult(
                {},
                error=(
                    "Story mode requires an LLM for non-Japanese evidence and for the dedicated creative Hook pass. "
                    "Configure OpenAI-compatible API (FREE_AI_API_BASE / FREE_AI_MODEL / optional FREE_AI_API_KEY) "
                    "or Ollama, then generate again."
                ),
            )

    result = _original_story_generate(*positional, **kwargs)
    if promoted and getattr(result, "package", None):
        quality = result.package.setdefault("content_quality", {})
        quality["story_llm_auto_promoted"] = True
        quality["story_llm_runtime_source"] = config.get("runtime_source")
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

st.sidebar.caption(f"Runtime · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Story · {story_content_pipeline_v5.STORY_CONTENT_PIPELINE_VERSION}")
st.sidebar.caption(f"Cleaner · {story_article_cleaner.STORY_ARTICLE_CLEANER_VERSION}")
st.sidebar.caption(f"Source · {story_source_engine_v5.STORY_SOURCE_ENGINE_VERSION}")
st.sidebar.caption(f"Graph · {story_graph_engine.STORY_GRAPH_ENGINE_VERSION}")
st.sidebar.caption(f"Hook · {story_hook_engine.STORY_HOOK_ENGINE_VERSION}")
st.sidebar.caption(
    "Story LLM · " + (
        str(_story_llm.get("runtime_source")) if _story_llm else "NOT CONFIGURED"
    )
)
st.sidebar.caption(f"Story Renderer · {story_renderer_v5.STORY_RENDERER_VERSION}")
st.sidebar.caption(f"Excel · {mode_exporter_v5.MODE_EXPORTER_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")
