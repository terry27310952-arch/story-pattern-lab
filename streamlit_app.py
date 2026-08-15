from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app.py"
RUNTIME_TOKEN = "documentary-editorial-v4.5"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import reasoning_engine  # noqa: E402
import card_renderer  # noqa: E402
import editorial_format_runtime  # noqa: E402
import visual_variation_runtime  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402
from editorial_visual_runtime import apply_editorial_visual_patch  # noqa: E402

# First reload the low-level renderer and install the variable composition engine.
# Downstream preview/export modules import render_card_png by value, so they must be
# imported/reloaded only after this patch is active.
importlib.reload(card_renderer)
importlib.reload(editorial_format_runtime)
importlib.reload(visual_variation_runtime)
visual_variation_runtime.apply_renderer_patch(card_renderer)

import preview_runtime  # noqa: E402
import excel_preview_sheet  # noqa: E402
import excel_exporter  # noqa: E402
import excel_export_runtime  # noqa: E402
import card_download_runtime  # noqa: E402

importlib.reload(preview_runtime)
importlib.reload(excel_preview_sheet)
importlib.reload(excel_export_runtime)
importlib.reload(card_download_runtime)

# Reset versioned runtime guards only when deployment version changes.
if getattr(st, "_kiyosaki_runtime_token", None) != RUNTIME_TOKEN:
    if hasattr(st, "_kiyosaki_preview_renderer_applied"):
        delattr(st, "_kiyosaki_preview_renderer_applied")
    if hasattr(excel_exporter, "_kiyosaki_excel_preview_applied"):
        delattr(excel_exporter, "_kiyosaki_excel_preview_applied")
    if hasattr(excel_exporter, "_kiyosaki_excel_export_runtime_version"):
        delattr(excel_exporter, "_kiyosaki_excel_export_runtime_version")
    if hasattr(st, "_kiyosaki_card_download_runtime_version"):
        delattr(st, "_kiyosaki_card_download_runtime_version")
    if hasattr(reasoning_engine, "_kiyosaki_editorial_format_version"):
        delattr(reasoning_engine, "_kiyosaki_editorial_format_version")
    if hasattr(reasoning_engine, "_kiyosaki_visual_variation_version"):
        delattr(reasoning_engine, "_kiyosaki_visual_variation_version")
    st._kiyosaki_runtime_token = RUNTIME_TOKEN

# Pipeline order matters. First build the evidence-safe cards, then change the
# briefing-level narrative journey, then select a matching fresh visual blueprint.
# This makes both the CONTENT FORMAT and the VISUAL FORMAT change between briefings.
apply_brand_patch(reasoning_engine)
apply_editorial_visual_patch(reasoning_engine)
preview_runtime.apply_preview_runtime()
editorial_format_runtime.apply_reasoning_patch(reasoning_engine)
visual_variation_runtime.apply_reasoning_patch(reasoning_engine)

# app.py imports build_excel_bytes by value, so install the verified Excel wrapper
# before runpy executes app.py. Card_Previews uses the exact same active renderer.
excel_export_runtime.apply_excel_export_patch()

# Make the Excel export visible inside every 5/6/7/custom card tab.
card_download_runtime.apply_card_download_patch()

# Visible diagnostics for deployment verification.
st.sidebar.caption(f"Renderer · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Editorial · {editorial_format_runtime.EDITORIAL_FORMAT_RUNTIME_VERSION}")
st.sidebar.caption(f"Blueprint · {visual_variation_runtime.VISUAL_VARIATION_RUNTIME_VERSION}")
st.sidebar.caption(f"Excel · {excel_export_runtime.EXCEL_PREVIEW_RUNTIME_VERSION}")
st.sidebar.caption(f"Download · {card_download_runtime.RUNTIME_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")

# Show the actual selected editorial + visual family/signature for this briefing.
try:
    package = st.session_state.get("content_package") or {}
    quality = package.get("content_quality") or {}
    editorial = quality.get("editorial_blueprint") or {}
    visual = quality.get("visual_blueprint") or {}
    if editorial.get("family"):
        st.sidebar.caption(f"Story · {editorial.get('family')} · {editorial.get('frame')}")
    if visual.get("family"):
        st.sidebar.caption(f"Deck · {visual.get('family')} · {visual.get('id')}")
except Exception:
    pass
