from __future__ import annotations

import runpy
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app.py"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import reasoning_engine  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402
from editorial_visual_runtime import apply_editorial_visual_patch  # noqa: E402

apply_brand_patch(reasoning_engine)
apply_editorial_visual_patch(reasoning_engine)

runpy.run_path(str(APP_FILE), run_name="__main__")
