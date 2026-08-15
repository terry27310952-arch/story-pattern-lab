from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app.py"
RUNTIME_TOKEN = "documentary-editorial-v4.3"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import reasoning_engine  # noqa: E402
import card_renderer  # noqa: E402
import preview_runtime  # noqa: E402
import excel_exporter  # noqa: E402
import excel_export_runtime  # noqa: E402
import card_download_runtime  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402
from editorial_visual_runtime import apply_editorial_visual_patch  # noqa: E402

# Streamlit hot-reloads the entry script but can keep imported modules and monkeypatch
# flags alive in the same Python process. Reload runtime modules explicitly so a new
# renderer/exporter/download commit cannot continue serving an older closure.
importlib.reload(card_renderer)
importlib.reload(preview_runtime)
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
    st._kiyosaki_runtime_token = RUNTIME_TOKEN

apply_brand_patch(reasoning_engine)
apply_editorial_visual_patch(reasoning_engine)
preview_runtime.apply_preview_runtime()

# app.py imports build_excel_bytes by value, so install the verified Excel wrapper
# before runpy executes app.py. It embeds current card_renderer PNGs in Card_Previews.
excel_export_runtime.apply_excel_export_patch()

# Make the Excel export visible inside every 5/6/7/custom card tab, directly below
# the Markdown download button. This removes the previous below-the-fold UX trap.
card_download_runtime.apply_card_download_patch()

# Visible diagnostics for deployment verification.
st.sidebar.caption(f"Renderer · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Excel · {excel_export_runtime.EXCEL_PREVIEW_RUNTIME_VERSION}")
st.sidebar.caption(f"Download · {card_download_runtime.RUNTIME_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")
