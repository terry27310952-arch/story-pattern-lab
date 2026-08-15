from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path


APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app_v2.py"
RUNTIME_TOKEN = "dual-pipeline-v6.1"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Only renderer composition is shared between modes. Content-generation functions are
# intentionally NOT converted between trader/story. Trader and Story pipelines call
# separate builders from app_v2.py, which prevents the old trader schema from leaking
# into storytelling output.
import card_renderer  # noqa: E402
import visual_variation_runtime  # noqa: E402
import story_render_runtime  # noqa: E402
import story_content_pipeline  # noqa: E402
import story_output_guard  # noqa: E402

importlib.reload(card_renderer)
importlib.reload(visual_variation_runtime)
importlib.reload(story_render_runtime)
importlib.reload(story_content_pipeline)
importlib.reload(story_output_guard)
visual_variation_runtime.apply_renderer_patch(card_renderer)
story_render_runtime.apply_renderer_patch(card_renderer)

# This guard only strips forbidden visible tokens/language leaks and locks brand
# invariants after Story generation. It does not create, reorder or reinterpret cards.
story_output_guard.apply_generation_guard(story_content_pipeline)

runpy.run_path(str(APP_FILE), run_name="__main__")
