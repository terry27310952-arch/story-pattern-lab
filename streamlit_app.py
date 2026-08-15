from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app.py"
RUNTIME_TOKEN = "documentary-editorial-v4.1"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import reasoning_engine  # noqa: E402
import card_renderer  # noqa: E402
import preview_runtime  # noqa: E402
import excel_exporter  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402
from editorial_visual_runtime import apply_editorial_visual_patch  # noqa: E402

# Streamlit hot-reloads the entry script but can keep imported modules and monkeypatch
# flags alive in the same Python process. Reload the preview modules explicitly so a
# new renderer commit cannot continue serving an older closure from memory.
importlib.reload(card_renderer)
importlib.reload(preview_runtime)

# Only reset runtime guards when the renderer version changes. This avoids wrapping
# st.markdown repeatedly on every normal Streamlit rerun while still replacing stale
# preview/excel monkeypatches after a deployment update.
if getattr(st, "_kiyosaki_runtime_token", None) != RUNTIME_TOKEN:
    if hasattr(st, "_kiyosaki_preview_renderer_applied"):
        delattr(st, "_kiyosaki_preview_renderer_applied")
    if hasattr(excel_exporter, "_kiyosaki_excel_preview_applied"):
        delattr(excel_exporter, "_kiyosaki_excel_preview_applied")
    st._kiyosaki_runtime_token = RUNTIME_TOKEN

apply_brand_patch(reasoning_engine)
apply_editorial_visual_patch(reasoning_engine)
preview_runtime.apply_preview_runtime()

# Visible diagnostic so the deployed app can be verified without guessing which
# renderer process is actually running.
st.sidebar.caption(f"Renderer · {RUNTIME_TOKEN}")

runpy.run_path(str(APP_FILE), run_name="__main__")
