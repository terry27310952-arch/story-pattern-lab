from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v8.0"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Trader keeps the stable reasoning engine. Story is a separate production pipeline.
import reasoning_engine  # noqa: E402
import card_renderer  # noqa: E402
import story_engine_v3  # noqa: E402
import story_content_pipeline_v3  # noqa: E402
import story_renderer_v3  # noqa: E402
import mode_exporter_v3  # noqa: E402
import story_output_guard  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402

apply_brand_patch(reasoning_engine)

# Streamlit hot reruns must not retain old story modules or patched closures.
importlib.reload(card_renderer)
importlib.reload(story_engine_v3)
importlib.reload(story_content_pipeline_v3)
importlib.reload(story_renderer_v3)
importlib.reload(mode_exporter_v3)
importlib.reload(story_output_guard)

# Visible-output guard only. It does not select stories or manufacture evidence.
story_output_guard.apply_generation_guard(story_content_pipeline_v3)

# app_v2 and the mode resource pipeline import these legacy module names. Route all
# story-facing imports to the same v8 engine so collection, ranking, generation and
# export cannot silently use different generations of Story logic.
sys.modules["story_engine"] = story_engine_v3
sys.modules["story_content_pipeline"] = story_content_pipeline_v3
sys.modules["mode_exporter"] = mode_exporter_v3

# Explicit preview dispatcher. Story never falls back to the trader renderer.
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
        return story_renderer_v3.render_story_card_image(card, width=width, height=height)
    return _trader_render_card_image(card, width=width, height=height)


def _render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    if _is_story_card(card):
        return story_renderer_v3.render_story_card_png(card, width=width, height=height)
    return _trader_render_card_png(card, width=width, height=height)


card_renderer.render_card_image = _render_card_image
card_renderer.render_card_png = _render_card_png
card_renderer._kiyosaki_runtime_router = RUNTIME_TOKEN

st.sidebar.caption(f"Runtime · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Story · {story_content_pipeline_v3.STORY_CONTENT_PIPELINE_VERSION}")
st.sidebar.caption(f"Story Engine · {story_engine_v3.STORY_ENGINE_VERSION}")
st.sidebar.caption(f"Story Renderer · {story_renderer_v3.STORY_RENDERER_VERSION}")
st.sidebar.caption(f"Excel · {mode_exporter_v3.MODE_EXPORTER_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")
