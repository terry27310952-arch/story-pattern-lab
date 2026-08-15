from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v6.0"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Only renderer composition is shared between modes. Content-generation functions are
# intentionally NOT monkey-patched here. Trader and Story pipelines call separate
# builders from app_v2.py, which prevents the old trader schema from leaking into
# storytelling output.
import card_renderer  # noqa: E402
import visual_variation_runtime  # noqa: E402
import story_render_runtime  # noqa: E402

importlib.reload(card_renderer)
importlib.reload(visual_variation_runtime)
importlib.reload(story_render_runtime)
visual_variation_runtime.apply_renderer_patch(card_renderer)
story_render_runtime.apply_renderer_patch(card_renderer)

runpy.run_path(str(APP_FILE), run_name="__main__")
