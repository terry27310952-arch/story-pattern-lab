from __future__ import annotations

import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

from excel_exporter import build_excel_bytes, flatten_visual_direction_rows  # noqa: E402
from reasoning_engine import (  # noqa: E402
    CARD_TYPES,
    DEFAULT_OUTPUT_LOCALE,
    INTERNAL_VISIBLE_BLOCKLIST,
    PROVIDER_LOCAL,
    PROVIDER_OPENAI_COMPATIBLE,
    generate_content_package,
    local_generate_brief,
    visible_card_text,
)


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "btc_sample_market.json"


def sample_resources() -> list[dict]:
    return [
        {
            "source": "CoinDesk Japan",
            "source_type": "media",
            "title": "BTC ETF flow and futures positioning",
            "url": "https://example.com/btc-etf-flow",
            "tags": "BTC,ETF,FLOW",
            "trader_score": 92,
            "fetch_method": "article_body",
            "material": (
                "Bitcoin ETF inflows slowed while futures open interest stayed elevated. "
                "Traders described the setup as a market where price must confirm support "
                "before conviction increases. "
            )
            * 12,
        },
        {
            "source": "Cointelegraph",
            "source_type": "media",
            "title": "Altcoin rotation waits for BTC stability",
            "url": "https://example.com/alt-rotation",
            "tags": "ALT,ETH,SOL",
            "trader_score": 87,
            "fetch_method": "article_body",
            "material": (
                "ETH and SOL need BTC stability and relative strength before rotation broadens. "
                "The market is not yet treating altcoin catalysts as independent trend signals. "
            )
            * 12,
        },
    ]


class CardContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.resources = sample_resources()
        cls.brief = local_generate_brief(cls.resources, cls.snapshot, "daily", "professional")
        cls.package = generate_content_package(
            cls.brief,
            cls.resources,
            6,
            {"provider": PROVIDER_LOCAL},
            DEFAULT_OUTPUT_LOCALE,
        )
        cls.cards = cls.package["cards"]["6장"]

    def test_generates_six_japanese_cards(self) -> None:
        self.assertEqual(len(self.cards), 6)
        for card in self.cards:
            self.assertEqual(card.get("locale"), "ja-JP")
            text = visible_card_text(card)
            self.assertNotRegex(text, r"[가-힣]")
            self.assertNotIn("トレーダー解説", text)
            for token in INTERNAL_VISIBLE_BLOCKLIST:
                self.assertNotIn(token, text)

    def test_observer_reference_asset_exists(self) -> None:
        reference_asset = ROOT / "assets" / "brand" / "observer_reference.png"
        self.assertTrue(reference_asset.exists())
        self.assertGreater(reference_asset.stat().st_size, 100000)

    def test_card_roles_and_copy_are_not_repeated(self) -> None:
        card_types = [card["card_type"] for card in self.cards]
        self.assertTrue(set(card_types).issubset(CARD_TYPES))
        self.assertGreaterEqual(len(set(card_types)), 5)
        action_counts = Counter(
            (card.get("action") or {}).get("text")
            for card in self.cards
            if (card.get("action") or {}).get("visible")
        )
        risk_counts = Counter(
            (card.get("risk") or {}).get("text")
            for card in self.cards
            if (card.get("risk") or {}).get("visible")
        )
        self.assertFalse([text for text, count in action_counts.items() if count > 1])
        self.assertFalse([text for text, count in risk_counts.items() if count > 1])

    def test_numeric_values_are_preserved(self) -> None:
        metrics_by_id = {
            metric["id"]: metric
            for card in self.cards
            for metric in card.get("metrics", [])
        }
        self.assertEqual(metrics_by_id["btc_price"]["raw_value"], 62971)
        self.assertEqual(metrics_by_id["btc_support"]["raw_value"], 62500)
        self.assertEqual(metrics_by_id["btc_resistance"]["raw_value"], 63417)
        self.assertEqual(metrics_by_id["mark_price"]["raw_value"], 63005)
        self.assertEqual(metrics_by_id["funding"]["raw_value"], 0.01)
        self.assertEqual(metrics_by_id["open_interest"]["raw_value"], 3393932)
        self.assertEqual(metrics_by_id["rsi14"]["raw_value"], 51.81)
        self.assertEqual(metrics_by_id["macd"]["raw_value"], "bearish")

    def test_character_and_layout_variation(self) -> None:
        shots = [card["visual_direction"]["character_shot"] for card in self.cards]
        layouts = [card["visual_direction"]["layout_variant"] for card in self.cards]
        self.assertFalse([(idx, shots[idx]) for idx in range(1, len(shots)) if shots[idx] == shots[idx - 1]])
        self.assertFalse([(idx, layouts[idx]) for idx in range(1, len(layouts)) if layouts[idx] == layouts[idx - 1]])
        key_card = next(card for card in self.cards if card["card_type"] == "key_levels")
        self.assertLessEqual(key_card["visual_direction"]["character_visibility"], 0.2)
        self.assertGreaterEqual(self.cards[0]["visual_direction"]["character_visibility"], 0.45)
        self.assertGreaterEqual(self.cards[-1]["visual_direction"]["character_visibility"], 0.3)

    def test_vertical_prompts_and_excel_export(self) -> None:
        for card in self.cards:
            direction = card["visual_direction"]
            self.assertIn("4:5", direction["image_prompts"])
            self.assertIn("9:16", direction["image_prompts"])
            self.assertIn("Faceless anonymous market observer", direction["image_prompts"]["4:5"])
            self.assertIn("visible face", direction["negative_prompt"])
            self.assertNotIn("長い日本語テキスト", direction["image_prompts"]["4:5"])
        visual_rows = flatten_visual_direction_rows(self.package)
        self.assertGreaterEqual(len(visual_rows), 6)
        excel_bytes = build_excel_bytes(self.brief, self.package, self.resources, self.snapshot)
        self.assertGreater(len(excel_bytes), 20000)

    def test_external_backend_failure_falls_back_without_crash(self) -> None:
        package = generate_content_package(
            self.brief,
            self.resources,
            6,
            {"provider": PROVIDER_OPENAI_COMPATIBLE},
            "ja-JP",
        )
        self.assertEqual(len(package["cards"]["6장"]), 6)
        meta = package["content_quality"]["editor_passes"]["6장"]["reasoning"]
        self.assertEqual(meta["plan"]["provider"], PROVIDER_LOCAL)


if __name__ == "__main__":
    unittest.main()
