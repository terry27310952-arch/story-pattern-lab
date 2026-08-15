from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v7.0"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Trader keeps the stable reasoning engine. Story uses independent v7 modules and is
# injected under the legacy import names before app_v2.py is executed. This avoids the
# previous patch-on-patch content path while keeping the UI file backward compatible.
import reasoning_engine  # noqa: E402
import card_renderer  # noqa: E402
import story_content_pipeline_v2  # noqa: E402
import story_engine_v2  # noqa: E402
import story_renderer_v2  # noqa: E402
import mode_exporter_v2  # noqa: E402
import story_output_guard  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402

apply_brand_patch(reasoning_engine)

# Always reload the production story modules so Streamlit hot reruns cannot retain an
# old closure or stale module implementation.
importlib.reload(card_renderer)
importlib.reload(story_engine_v2)
importlib.reload(story_content_pipeline_v2)
importlib.reload(story_renderer_v2)
importlib.reload(mode_exporter_v2)
importlib.reload(story_output_guard)

# Final visible-output invariant guard. This can sanitize copy/brand fields only; it
# cannot choose an archetype or create story cards.
story_output_guard.apply_generation_guard(story_content_pipeline_v2)

# app_v2 imports these names. Route them to the production v7 implementations before
# runpy executes the UI module.
sys.modules["story_content_pipeline"] = story_content_pipeline_v2
sys.modules["mode_exporter"] = mode_exporter_v2

# Preview rendering is explicitly dispatched by card mode. Story rendering no longer
# depends on the old global visual/story patch chain. Excel uses the same explicit
# story_renderer_v2 function inside mode_exporter_v2.
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
        return story_renderer_v2.render_story_card_image(card, width=width, height=height)
    return _trader_render_card_image(card, width=width, height=height)


def _render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    if _is_story_card(card):
        return story_renderer_v2.render_story_card_png(card, width=width, height=height)
    return _trader_render_card_png(card, width=width, height=height)


card_renderer.render_card_image = _render_card_image
card_renderer.render_card_png = _render_card_png
card_renderer._kiyosaki_runtime_router = RUNTIME_TOKEN

st.sidebar.caption(f"Runtime · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Story · {story_content_pipeline_v2.STORY_CONTENT_PIPELINE_VERSION}")
st.sidebar.caption(f"Story Engine · {story_engine_v2.STORY_ENGINE_VERSION}")
st.sidebar.caption(f"Story Renderer · {story_renderer_v2.STORY_RENDERER_VERSION}")
st.sidebar.caption(f"Excel · {mode_exporter_v2.MODE_EXPORTER_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")
