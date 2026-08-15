from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import card_renderer  # noqa: E402
import visual_variation_runtime as runtime  # noqa: E402


BASE_CARDS = [
    {
        "slide": 1,
        "card_type": "market_conclusion",
        "headline": "センチメントは弱い。でも、価格はまだ崩れていない。",
        "key_message": "材料ではなく、いま市場に残っている矛盾を見る。",
        "metrics": [{"id": "btc_price", "label": "BTC", "value": "$63,008", "raw_value": 63008}],
        "qa": {"renderable": True},
        "visual_direction": {"image_prompts": {"4:5": "base", "9:16": "base"}},
    },
    {
        "slide": 2,
        "card_type": "key_levels",
        "headline": "まず見るのはこの2点",
        "key_message": "下は$62,491。上は$65,818を回復できるか。",
        "metrics": [
            {"id": "btc_price", "label": "BTC", "value": "$63,008", "raw_value": 63008},
            {"id": "btc_primary_support", "label": "SUPPORT", "value": "$62,491", "raw_value": 62491},
            {"id": "btc_primary_resistance", "label": "RESISTANCE", "value": "$65,818", "raw_value": 65818},
        ],
        "qa": {"renderable": True},
        "visual_direction": {"image_prompts": {"4:5": "base", "9:16": "base"}},
    },
    {
        "slide": 3,
        "card_type": "brand_outro",
        "headline": "勢力ハンター キヨサキ",
        "key_message": "フォローして、勢力が入ったポイントを無料でチェック。",
        "qa": {"renderable": True},
        "visual_direction": {"image_prompts": {"4:5": "base", "9:16": "base"}},
    },
]


class VisualVariationRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        runtime.RECENT_BLUEPRINTS.clear()

    def test_consecutive_briefings_use_different_deck_family(self) -> None:
        package = {"cards": {"자율제안": BASE_CARDS}}
        first = runtime.apply_blueprint_to_package(package, {"title": "A"}, [])
        second = runtime.apply_blueprint_to_package(package, {"title": "A"}, [])
        first_family = first["content_quality"]["visual_blueprint"]["family"]
        second_family = second["content_quality"]["visual_blueprint"]["family"]
        self.assertNotEqual(first_family, second_family)

    def test_no_adjacent_same_format_and_outro_is_locked(self) -> None:
        package = {"cards": {"자율제안": BASE_CARDS}}
        result = runtime.apply_blueprint_to_package(package, {"title": "B"}, [])
        cards = result["cards"]["자율제안"]
        variants = [card["visual_direction"]["format_variant"] for card in cards]
        for left, right in zip(variants, variants[1:]):
            self.assertNotEqual(left, right)
        self.assertEqual(variants[-1], "brand_locked")
        lock = cards[-1]["visual_direction"]["character_style_lock"]
        self.assertIn("featureless", lock["face"])
        self.assertIn("black leather gloves", lock["wardrobe"])

    def test_prompt_forbids_k_monogram(self) -> None:
        package = {"cards": {"자율제안": BASE_CARDS}}
        result = runtime.apply_blueprint_to_package(package, {"title": "C"}, [])
        for card in result["cards"]["자율제안"]:
            prompt = card["visual_direction"]["image_prompts"]["4:5"]
            self.assertIn("Do not add a K monogram", prompt)

    def test_renderer_changes_with_format_variant(self) -> None:
        runtime.apply_renderer_patch(card_renderer)
        a = dict(BASE_CARDS[0])
        b = dict(BASE_CARDS[0])
        a["visual_direction"] = {"format_variant": "split_left"}
        b["visual_direction"] = {"format_variant": "poster_center"}
        png_a = card_renderer.render_card_png(a, width=432, height=540)
        png_b = card_renderer.render_card_png(b, width=432, height=540)
        self.assertTrue(png_a.startswith(b"\x89PNG"))
        self.assertTrue(png_b.startswith(b"\x89PNG"))
        self.assertNotEqual(png_a, png_b)


if __name__ == "__main__":
    unittest.main()
