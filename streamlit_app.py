from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app.py"
RUNTIME_TOKEN = "documentary-editorial-v4.2"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import reasoning_engine  # noqa: E402
import card_renderer  # noqa: E402
import preview_runtime  # noqa: E402
import excel_exporter  # noqa: E402
import excel_export_runtime  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402
from editorial_visual_runtime import apply_editorial_visual_patch  # noqa: E402

# Streamlit hot-reloads the entry script but can keep imported modules and monkeypatch
# flags alive in the same Python process. Reload the runtime modules explicitly so a
# new renderer/exporter commit cannot continue serving an older closure from memory.
importlib.reload(card_renderer)
importlib.reload(preview_runtime)
importlib.reload(excel_export_runtime)

# Only reset runtime guards when the deployed runtime version changes. This avoids
# wrapping Streamlit functions repeatedly on ordinary reruns while replacing stale
# preview/export closures after a deployment update.
if getattr(st, "_kiyosaki_runtime_token", None) != RUNTIME_TOKEN:
    if hasattr(st, "_kiyosaki_preview_renderer_applied"):
        delattr(st, "_kiyosaki_preview_renderer_applied")
    if hasattr(excel_exporter, "_kiyosaki_excel_preview_applied"):
        delattr(excel_exporter, "_kiyosaki_excel_preview_applied")
    if hasattr(excel_exporter, "_kiyosaki_excel_export_runtime_version"):
        delattr(excel_exporter, "_kiyosaki_excel_export_runtime_version")
    st._kiyosaki_runtime_token = RUNTIME_TOKEN

apply_brand_patch(reasoning_engine)
apply_editorial_visual_patch(reasoning_engine)
preview_runtime.apply_preview_runtime()

# IMPORTANT: app.py imports build_excel_bytes by value. Install the guaranteed Excel
# wrapper before runpy executes app.py so the local imported symbol includes previews.
excel_export_runtime.apply_excel_export_patch()

# Visible diagnostics so deployment can be verified without guessing which code path
# is actually serving previews and Excel packages.
st.sidebar.caption(f"Renderer · {RUNTIME_TOKEN}")
st.sidebar.caption(f"Excel · {excel_export_runtime.EXCEL_PREVIEW_RUNTIME_VERSION}")

runpy.run_path(str(APP_FILE), run_name="__main__")
