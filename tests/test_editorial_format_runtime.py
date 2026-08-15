from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

from editorial_format_runtime import apply_editorial_format_to_package, select_editorial_family  # noqa: E402


def sample_package() -> dict:
    cards = [
        {"slide": 1, "card_type": "market_conclusion", "headline": "OLD MARKET", "metrics": [{"id": "btc_price", "value": "$63,009", "raw_value": 63009}]},
        {"slide": 2, "card_type": "key_levels", "headline": "OLD LEVELS", "metrics": [{"id": "btc_primary_support", "value": "$62,491", "raw_value": 62491}]},
        {"slide": 3, "card_type": "derivatives", "headline": "OLD DERIVATIVES", "metrics": [{"id": "funding", "value": "+0.01%", "raw_value": 0.01}]},
        {
            "slide": 4,
            "card_type": "news_context",
            "headline": "OLD NEWS",
            "source": {"display_headline_ja": "BTC供給の希少性が再び焦点に"},
            "metrics": [{"id": "btc_price", "value": "$63,009", "raw_value": 63009}],
        },
        {"slide": 5, "card_type": "trade_plan", "headline": "OLD PLAN", "trade_plan": {"entry": {"condition": "$65,818を終値で回復"}}},
        {"slide": 6, "card_type": "brand_outro", "headline": "勢力ハンター キヨサキ"},
    ]
    return {"cards": {"5장": cards}, "content_quality": {}}


class EditorialFormatRuntimeTest(unittest.TestCase):
    def test_different_seeds_can_select_different_story_families(self) -> None:
        first = select_editorial_family("1" * 64, recent=[])
        second = select_editorial_family("2" * 64, recent=[first])
        self.assertNotEqual(first, second)

    def test_story_family_changes_order_and_headlines_but_not_locked_values(self) -> None:
        package = sample_package()
        brief = {"title": "brief", "one_line": "test", "generated_at": "2026-08-16"}
        out = apply_editorial_format_to_package(package, brief, [], seed_hex="2" * 64, recent=["contradiction_first"])
        cards = out["cards"]["5장"]
        self.assertEqual(cards[-1]["card_type"], "brand_outro")
        self.assertEqual(cards[-1]["headline"], "勢力ハンター キヨサキ")
        self.assertNotEqual([card["headline"] for card in cards[:-1]], ["OLD MARKET", "OLD LEVELS", "OLD DERIVATIVES", "OLD NEWS", "OLD PLAN"])
        all_metrics = [metric for card in cards for metric in (card.get("metrics") or [])]
        raw_values = {metric.get("raw_value") for metric in all_metrics}
        self.assertIn(63009, raw_values)
        self.assertIn(62491, raw_values)
        self.assertIn(0.01, raw_values)
        self.assertTrue(out["content_quality"]["editorial_blueprint"]["family"])

    def test_news_decode_surfaces_localized_news_headline(self) -> None:
        package = sample_package()
        brief = {"title": "brief", "one_line": "test", "generated_at": "2026-08-16"}
        # Search a deterministic seed that chooses news_to_price without relying on implementation internals.
        chosen = None
        for digit in "123456789abcdef":
            seed = digit * 64
            out = apply_editorial_format_to_package(package, brief, [], seed_hex=seed, recent=[])
            if out["content_quality"]["editorial_blueprint"]["family"] == "news_to_price":
                chosen = out
                break
        self.assertIsNotNone(chosen)
        news = next(card for card in chosen["cards"]["5장"] if card["card_type"] == "news_context")
        self.assertEqual(news["headline"], "BTC供給の希少性が再び焦点に")


if __name__ == "__main__":
    unittest.main()
