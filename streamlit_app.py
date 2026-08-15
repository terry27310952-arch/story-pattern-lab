from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app.py"
RUNTIME_TOKEN = "story-first-editorial-v5.2"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import reasoning_engine  # noqa: E402
import resource_collector  # noqa: E402
import card_renderer  # noqa: E402
import visual_variation_runtime  # noqa: E402
import story_engine  # noqa: E402
import story_pipeline_runtime  # noqa: E402
import story_source_runtime  # noqa: E402
import story_deck_runtime  # noqa: E402
import story_render_runtime  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402
from editorial_visual_runtime import apply_editorial_visual_patch  # noqa: E402

# Renderer order matters. The existing deck-variation renderer is installed first,
# then the story renderer adds archetype-aware visual motifs on top. Preview/export
# modules import render_card_png by value, so they are imported only after both patches.
importlib.reload(card_renderer)
importlib.reload(visual_variation_runtime)
importlib.reload(story_engine)
importlib.reload(story_pipeline_runtime)
importlib.reload(story_source_runtime)
importlib.reload(story_deck_runtime)
importlib.reload(story_render_runtime)
visual_variation_runtime.apply_renderer_patch(card_renderer)
story_render_runtime.apply_renderer_patch(card_renderer)

import preview_runtime  # noqa: E402
import excel_preview_sheet  # noqa: E402
import excel_exporter  # noqa: E402
import excel_export_runtime  # noqa: E402
import story_export_runtime  # noqa: E402
import card_download_runtime  # noqa: E402

importlib.reload(preview_runtime)
importlib.reload(excel_preview_sheet)
importlib.reload(excel_export_runtime)
importlib.reload(story_export_runtime)
importlib.reload(card_download_runtime)

# Reset versioned runtime guards only when deployment version changes.
if getattr(st, "_kiyosaki_runtime_token", None) != RUNTIME_TOKEN:
    if hasattr(st, "_kiyosaki_preview_renderer_applied"):
        delattr(st, "_kiyosaki_preview_renderer_applied")
    if hasattr(excel_exporter, "_kiyosaki_excel_preview_applied"):
        delattr(excel_exporter, "_kiyosaki_excel_preview_applied")
    if hasattr(excel_exporter, "_kiyosaki_excel_export_runtime_version"):
        delattr(excel_exporter, "_kiyosaki_excel_export_runtime_version")
    if hasattr(excel_exporter, "_kiyosaki_story_export_version"):
        delattr(excel_exporter, "_kiyosaki_story_export_version")
    if hasattr(st, "_kiyosaki_card_download_runtime_version"):
        delattr(st, "_kiyosaki_card_download_runtime_version")
    if hasattr(reasoning_engine, "_kiyosaki_visual_variation_version"):
        delattr(reasoning_engine, "_kiyosaki_visual_variation_version")
    if hasattr(reasoning_engine, "_kiyosaki_story_pipeline_version"):
        delattr(reasoning_engine, "_kiyosaki_story_pipeline_version")
    if hasattr(reasoning_engine, "_kiyosaki_story_deck_version"):
        delattr(reasoning_engine, "_kiyosaki_story_deck_version")
    if hasattr(resource_collector, "_kiyosaki_story_resource_version"):
        delattr(resource_collector, "_kiyosaki_story_resource_version")
    if hasattr(resource_collector, "_kiyosaki_story_source_version"):
        delattr(resource_collector, "_kiyosaki_story_source_version")
    st._kiyosaki_runtime_token = RUNTIME_TOKEN

# Content pipeline order:
# canonical brand/QA semantics -> story annotation -> story-rich source expansion and
# ranking -> briefing visual family -> story candidate/archetype copy -> archetype card
# ordering. app.py imports the patched functions only after this setup is complete.
apply_brand_patch(reasoning_engine)
apply_editorial_visual_patch(reasoning_engine)
story_pipeline_runtime.apply_resource_patch(resource_collector)
story_source_runtime.apply_source_patch(resource_collector)
visual_variation_runtime.apply_reasoning_patch(reasoning_engine)
story_pipeline_runtime.apply_reasoning_patch(reasoning_engine)
story_deck_runtime.apply_reasoning_patch(reasoning_engine)
preview_runtime.apply_preview_runtime()

# Excel keeps the existing embedded PNG gallery, then receives story context/candidate
# sheets. This is applied before app.py imports build_excel_bytes by value.
excel_export_runtime.apply_excel_export_patch()
story_export_runtime.apply_excel_patch(excel_exporter)
card_download_runtime.apply_card_download_patch()

# Visible deployment diagnostics.
st.sidebar.caption(f"Runtime · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Source · {story_source_runtime.STORY_SOURCE_RUNTIME_VERSION}")
st.sidebar.caption(f"Story · {story_engine.STORY_ENGINE_VERSION}")
st.sidebar.caption(f"Deck · {story_deck_runtime.STORY_DECK_RUNTIME_VERSION}")
st.sidebar.caption(f"Renderer · {story_render_runtime.STORY_RENDER_RUNTIME_VERSION}")
st.sidebar.caption(f"Blueprint · {visual_variation_runtime.VISUAL_VARIATION_RUNTIME_VERSION}")
st.sidebar.caption(f"Excel · {story_export_runtime.STORY_EXPORT_RUNTIME_VERSION}")
st.sidebar.caption(f"Download · {card_download_runtime.RUNTIME_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")

# Show what the story engine actually selected for the current briefing.
try:
    brief = st.session_state.get("brief") or {}
    package = st.session_state.get("content_package") or {}
    story_context = brief.get("story_context") or {}
    hero = story_context.get("hero_story") or {}
    story_meta = (package.get("content_quality") or {}).get("story_engine") or {}
    blueprint = (package.get("content_quality") or {}).get("visual_blueprint") or {}
    if hero.get("headline_ja"):
        st.sidebar.caption(f"Hero · {hero.get('headline_ja')}")
    if hero.get("archetype"):
        st.sidebar.caption(f"Archetype · {hero.get('archetype')} · score {hero.get('story_score', 0)}")
    if blueprint.get("family"):
        st.sidebar.caption(f"Deck seed · {blueprint.get('family')} · {blueprint.get('id')}")
    elif story_meta.get("hero_story", {}).get("archetype"):
        st.sidebar.caption(f"Deck family · story_{story_meta['hero_story'].get('archetype')}")
except Exception:
    pass
