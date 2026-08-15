from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v9.2"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


# Streamlit reuses the same Python process across reruns. v9.0 temporarily routed the
# *_v3 module names to v4 in sys.modules. On the next rerun, story_engine_v4 imported
# `story_engine_v3 as legacy`, but that name already pointed back to story_engine_v4,
# so legacy.annotate_resource() recursively called itself until RecursionError.
# Repair stale aliases before importing/reloading the production stack.
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


# Trader keeps the stable reasoning engine. Story v9 is layered on top of the REAL
# v3 compatibility modules, never on aliases back to itself.
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

# Import/reload Story v9.2 after the legacy layer is repaired. The article cleaner is
# explicitly reloaded because Streamlit hot-reruns otherwise retain an older cleaner.
import story_article_cleaner  # noqa: E402
import story_engine_v4  # noqa: E402
import story_renderer_v4  # noqa: E402
import story_content_pipeline_v4  # noqa: E402
import mode_exporter_v4  # noqa: E402
import story_output_guard  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402

apply_brand_patch(reasoning_engine)

importlib.reload(story_article_cleaner)
importlib.reload(story_engine_v4)
importlib.reload(story_renderer_v4)
importlib.reload(story_content_pipeline_v4)
importlib.reload(mode_exporter_v4)
importlib.reload(story_output_guard)

if story_engine_v4.legacy is story_engine_v4:
    raise RuntimeError("Story runtime boot failed: story_engine_v4 legacy dependency points to itself")
if story_content_pipeline_v4.legacy is story_content_pipeline_v4:
    raise RuntimeError("Story runtime boot failed: story_content_pipeline_v4 legacy dependency points to itself")
if story_renderer_v4.legacy is story_renderer_v4:
    raise RuntimeError("Story runtime boot failed: story_renderer_v4 legacy dependency points to itself")

story_output_guard.apply_generation_guard(story_content_pipeline_v4)

# app_v2 imports generic production names. Route ONLY those generic names to v9.
sys.modules["story_engine"] = story_engine_v4
sys.modules["story_content_pipeline"] = story_content_pipeline_v4
sys.modules["mode_exporter"] = mode_exporter_v4

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
        return story_renderer_v4.render_story_card_image(card, width=width, height=height)
    return _trader_render_card_image(card, width=width, height=height)


def _render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
    if _is_story_card(card):
        return story_renderer_v4.render_story_card_png(card, width=width, height=height)
    return _trader_render_card_png(card, width=width, height=height)


card_renderer.render_card_image = _render_card_image
card_renderer.render_card_png = _render_card_png
card_renderer._kiyosaki_runtime_router = RUNTIME_TOKEN

st.sidebar.caption(f"Runtime · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Story · {story_content_pipeline_v4.STORY_CONTENT_PIPELINE_VERSION}")
st.sidebar.caption(f"Cleaner · {story_article_cleaner.STORY_ARTICLE_CLEANER_VERSION}")
st.sidebar.caption(f"Story Engine · {story_engine_v4.STORY_ENGINE_VERSION}")
st.sidebar.caption(f"Story Renderer · {story_renderer_v4.STORY_RENDERER_VERSION}")
st.sidebar.caption(f"Excel · {mode_exporter_v4.MODE_EXPORTER_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")
