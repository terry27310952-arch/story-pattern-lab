from __future__ import annotations

import copy
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


def full_seven_card_deck() -> list[dict]:
    card_types = [
        "market_conclusion",
        "key_levels",
        "derivatives",
        "scenarios",
        "trade_plan",
        "trade_plan",
        "brand_outro",
    ]
    cards = []
    for slide, card_type in enumerate(card_types, start=1):
        cards.append(
            {
                "slide": slide,
                "card_type": card_type,
                "headline": f"card {slide}",
                "key_message": "test",
                "metrics": [],
                "qa": {"renderable": True},
                "visual_direction": {"image_prompts": {"4:5": "base", "9:16": "base"}},
            }
        )
    return cards


class VisualVariationRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        runtime.RECENT_BLUEPRINTS.clear()
        runtime.RECENT_SCENES.clear()

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
        self.assertIn("trading room", lock["background"])

    def test_prompt_forbids_k_monogram(self) -> None:
        package = {"cards": {"자율제안": BASE_CARDS}}
        result = runtime.apply_blueprint_to_package(package, {"title": "C"}, [])
        for card in result["cards"]["자율제안"]:
            prompt = card["visual_direction"]["image_prompts"]["4:5"]
            self.assertIn("Do not add a K monogram", prompt)

    def test_scene_direction_contains_physical_action_axes(self) -> None:
        package = {"cards": {"7장": full_seven_card_deck()}}
        result = runtime.apply_blueprint_to_package(package, {"title": "scene axes"}, [])
        cards = result["cards"]["7장"]
        required = {
            "scene_archetype",
            "environment",
            "character_action",
            "body_orientation",
            "hand_action",
            "prop",
            "camera_distance",
            "camera_height",
            "camera_side",
            "lens_language",
            "lighting_source",
            "foreground_element",
            "background_activity",
            "character_scale",
            "character_crop",
            "motion_state",
            "scene_uniqueness_key",
        }
        for card in cards:
            direction = card["visual_direction"]
            self.assertTrue(required.issubset(direction))
            self.assertTrue(direction["scene_uniqueness_key"])

    def test_non_outro_cards_do_not_reuse_brand_clasp_pose(self) -> None:
        package = {"cards": {"7장": full_seven_card_deck()}}
        result = runtime.apply_blueprint_to_package(package, {"title": "pose lock"}, [])
        cards = result["cards"]["7장"]
        for card in cards[:-1]:
            hand_action = card["visual_direction"]["hand_action"].lower()
            self.assertNotIn("clasp", hand_action)
        outro = cards[-1]["visual_direction"]
        self.assertIn("clasped", outro["hand_action"].lower())
        self.assertEqual(outro["scene_archetype"], "brand_outro_locked")

    def test_repeated_trade_plan_cards_receive_distinct_scenes(self) -> None:
        package = {"cards": {"7장": full_seven_card_deck()}}
        result = runtime.apply_blueprint_to_package(package, {"title": "trade plan diversity"}, [])
        cards = result["cards"]["7장"]
        trade_scenes = [
            card["visual_direction"]["scene_archetype"]
            for card in cards
            if card["card_type"] == "trade_plan"
        ]
        self.assertEqual(len(trade_scenes), 2)
        self.assertEqual(len(set(trade_scenes)), 2)

    def test_recent_scene_history_changes_next_briefing_pose(self) -> None:
        one_card = [copy.deepcopy(BASE_CARDS[0])]
        package = {"cards": {"자율제안": one_card}}
        first = runtime.apply_blueprint_to_package(package, {"title": "same"}, [])
        second = runtime.apply_blueprint_to_package(package, {"title": "same"}, [])
        first_scene = first["cards"]["자율제안"][0]["visual_direction"]["scene_archetype"]
        second_scene = second["cards"]["자율제안"][0]["visual_direction"]["scene_archetype"]
        self.assertNotEqual(first_scene, second_scene)

    def test_scene_prompt_leads_with_action_and_camera_not_static_portrait(self) -> None:
        package = {"cards": {"7장": full_seven_card_deck()}}
        result = runtime.apply_blueprint_to_package(package, {"title": "prompt order"}, [])
        for card in result["cards"]["7장"][:-1]:
            prompt = card["visual_direction"]["image_prompts"]["4:5"]
            self.assertTrue(prompt.startswith("SCENE FIRST."))
            self.assertIn("Visible action:", prompt)
            self.assertIn("Camera:", prompt)
            self.assertIn("Do not default to a static portrait", prompt)

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
