from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import reasoning_engine as engine  # noqa: E402
from brand_runtime import apply_brand_patch  # noqa: E402
from editorial_visual_runtime import (  # noqa: E402
    CHARACTER_BIBLE,
    DISPLAY_BRAND_LABEL,
    EDITORIAL_SHELL_CSS,
    apply_editorial_visual_patch,
    visual_story_for_card,
)


class EditorialVisualRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        apply_brand_patch(engine)
        apply_editorial_visual_patch(engine)

    def test_character_consistency_is_bible_based(self) -> None:
        brand_system = engine.OBSERVER_BRAND_SYSTEM
        self.assertNotIn("reference_asset_path", brand_system)
        self.assertEqual(brand_system.get("character_consistency_source"), "character_bible")
        self.assertEqual(brand_system.get("character_bible"), CHARACTER_BIBLE)
        self.assertIn("no visible eyes", CHARACTER_BIBLE["face"])
        self.assertIn("black leather gloves", CHARACTER_BIBLE["wardrobe"])

    def test_public_brand_label_is_kiyosaki(self) -> None:
        self.assertEqual(DISPLAY_BRAND_LABEL, "キヨサキ")
        self.assertEqual(engine.OBSERVER_BRAND_SYSTEM.get("display_brand_label"), "キヨサキ")

    def test_visual_story_roles_match_reference_rhythm(self) -> None:
        cases = [
            ({"card_type": "market_conclusion", "slide": 1}, "documentary_cover", True),
            ({"card_type": "key_levels", "slide": 2}, "price_instrument", False),
            ({"card_type": "derivatives", "slide": 3}, "institutional_desk", True),
            ({"card_type": "news_context", "slide": 4}, "editorial_documentary", False),
            ({"card_type": "scenarios", "slide": 5}, "symbolic_paths", False),
            ({"card_type": "trade_plan", "slide": 6}, "decision_scene", True),
            ({"card_type": "brand_outro", "slide": 7}, "brand_poster", True),
        ]
        for card, mode, character_required in cases:
            story = visual_story_for_card(card)
            self.assertEqual(story["mode"], mode)
            self.assertEqual(story["character_required"], character_required)
            self.assertEqual(story["shell"], "full_bleed_documentary")
            self.assertEqual(story["text_zone"], "bottom")
            self.assertEqual(story["headline_style"], "orange_bold")

    def test_visual_system_emits_documentary_prompts(self) -> None:
        cards = [
            {
                "slide": 1,
                "card_type": "market_conclusion",
                "headline": "まだ追わない。",
                "metrics": [],
                "visual_direction": {},
            },
            {
                "slide": 2,
                "card_type": "key_levels",
                "headline": "まず見るのはこの2点",
                "metrics": [
                    {"id": "btc_support", "value": "$62,500"},
                    {"id": "btc_resistance", "value": "$63,417"},
                ],
                "visual_direction": {},
            },
        ]
        result = engine.editor_pass_visual_system(cards)
        cover = result[0]["visual_direction"]
        price = result[1]["visual_direction"]
        self.assertEqual(cover["composition_type"], "full_bleed_documentary")
        self.assertTrue(cover["character_present"])
        self.assertFalse(price["character_present"])
        self.assertEqual(price["character_visibility"], 0.0)
        for direction in [cover, price]:
            prompt = direction["image_prompts"]["4:5"]
            self.assertIn("full-bleed", prompt)
            self.assertIn("bottom gradient", prompt)
            self.assertIn("Do not render any readable Japanese or English text", prompt)
            self.assertNotIn("reference image", prompt.lower())

    def test_preview_shell_matches_documentary_reference(self) -> None:
        self.assertIn("bottom black", EDITORIAL_SHELL_CSS.lower())
        self.assertIn("#f5a623", EDITORIAL_SHELL_CSS.lower())
        self.assertIn("full-bleed", EDITORIAL_SHELL_CSS.lower())
        self.assertIn(".observer-preview.news_primary", EDITORIAL_SHELL_CSS)
        self.assertIn(".observer-preview.scenario_primary", EDITORIAL_SHELL_CSS)
        self.assertIn(".observer-preview.brand_outro", EDITORIAL_SHELL_CSS)


if __name__ == "__main__":
    unittest.main()
