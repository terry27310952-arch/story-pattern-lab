from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "apps" / "streamlit"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import card_renderer  # noqa: E402
import reasoning_engine  # noqa: E402
import visual_variation_runtime  # noqa: E402
from brand_runtime import DISPLAY_BRAND_LABEL, apply_brand_patch  # noqa: E402


class BrandRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        apply_brand_patch(reasoning_engine)

    def test_japanese_card_uses_kiyosaki_public_label(self) -> None:
        card = {
            "card_type": "market_conclusion",
            "slide": 1,
            "semantic": {},
            "metrics": [],
            "source": {},
        }
        copy = reasoning_engine.ja_copy_for_card(card)
        self.assertEqual(copy["eyebrow"], DISPLAY_BRAND_LABEL)
        self.assertNotIn("THE OBSERVER", " ".join(str(value) for value in copy.values()))

    def test_brand_outro_hides_internal_codename(self) -> None:
        card = reasoning_engine.make_brand_outro_card(
            "6장",
            7,
            "ja-JP",
            {"brand_outro": {"brand_name": "勢力ハンター キヨサキ", "cta": "フォローして、勢力が入ったポイントを無料でチェック。", "account": ""}},
        )
        self.assertEqual(card["eyebrow"], DISPLAY_BRAND_LABEL)
        self.assertEqual(card["subheadline"], "")
        self.assertNotIn("THE OBSERVER", reasoning_engine.visible_card_text(card))

    def test_internal_character_codename_is_preserved_only_as_metadata(self) -> None:
        self.assertEqual(reasoning_engine.OBSERVER_BRAND_SYSTEM["display_brand_label"], DISPLAY_BRAND_LABEL)
        self.assertEqual(reasoning_engine.OBSERVER_BRAND_SYSTEM["internal_character_codename"], "THE OBSERVER")

    def test_visual_director_bootstraps_before_app_generation(self) -> None:
        self.assertEqual(
            reasoning_engine.VISUAL_DIRECTOR_RUNTIME_VERSION,
            visual_variation_runtime.VISUAL_VARIATION_RUNTIME_VERSION,
        )
        self.assertEqual(
            getattr(reasoning_engine, "_kiyosaki_visual_variation_version", None),
            visual_variation_runtime.VISUAL_VARIATION_RUNTIME_VERSION,
        )
        self.assertEqual(
            getattr(card_renderer, "_kiyosaki_visual_renderer_version", None),
            visual_variation_runtime.VISUAL_VARIATION_RUNTIME_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
