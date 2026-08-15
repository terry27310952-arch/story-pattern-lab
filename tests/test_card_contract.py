from __future__ import annotations

import copy
import json
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import reasoning_engine as engine  # noqa: E402
from excel_exporter import build_excel_bytes, flatten_visual_direction_rows  # noqa: E402
from market_data import summarize_market  # noqa: E402
from reasoning_engine import (  # noqa: E402
    BRAND_OUTRO_TYPE,
    CARD_TYPES,
    DEFAULT_BRAND_OUTRO,
    DEFAULT_OUTPUT_LOCALE,
    INTERNAL_VISIBLE_BLOCKLIST,
    JA_TRANSLATIONESE_PATTERNS,
    PROVIDER_LOCAL,
    PROVIDER_OPENAI_COMPATIBLE,
    derive_variant,
    editor_pass_qa,
    evidence_profile,
    finalize_card_set,
    generate_content_package,
    has_ja_empty_variable,
    ja_copy_for_card,
    local_generate_brief,
    locked_market_metrics,
    merge_stage_patch,
    normalize_external_brief,
    normalize_sources,
    reconcile_cards_with_canonical,
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
        cls.normalized_resources = normalize_sources(cls.resources)
        cls.brief = local_generate_brief(cls.resources, cls.snapshot, "daily", "professional")
        cls.metrics = locked_market_metrics(
            cls.brief["market_summary"],
            cls.brief.get("generated_at"),
            cls.brief.get("briefing_type"),
        )
        cls.package = generate_content_package(
            cls.brief,
            cls.resources,
            6,
            {"provider": PROVIDER_LOCAL},
            DEFAULT_OUTPUT_LOCALE,
        )
        cls.cards = cls.package["cards"]["6장"]

    def content_cards(self) -> list[dict]:
        return [card for card in self.cards if card.get("card_type") != BRAND_OUTRO_TYPE]

    def test_generates_japanese_cards_with_locked_brand_outro(self) -> None:
        self.assertEqual(len(self.cards), 7)
        self.assertEqual(self.cards[-1]["card_type"], BRAND_OUTRO_TYPE)
        final_text = visible_card_text(self.cards[-1])
        self.assertIn(DEFAULT_BRAND_OUTRO["brand_name"], final_text.replace("\n", " "))
        self.assertIn(DEFAULT_BRAND_OUTRO["cta"], final_text)
        for card in self.cards:
            self.assertEqual(card.get("locale"), "ja-JP")
            self.assertTrue((card.get("qa") or {}).get("renderable", True))
            self.assertIn((card.get("qa") or {}).get("severity"), {"INFO", "WARNING", "BLOCKING"})
            text = visible_card_text(card)
            self.assertNotRegex(text, r"[\uac00-\ud7a3]")
            self.assertFalse(has_ja_empty_variable(text))
            self.assertFalse([pattern for pattern in JA_TRANSLATIONESE_PATTERNS if pattern in text])
            for token in INTERNAL_VISIBLE_BLOCKLIST:
                self.assertNotIn(token, text)

    def test_observer_reference_asset_exists(self) -> None:
        reference_asset = ROOT / "assets" / "brand" / "observer_reference.png"
        self.assertTrue(reference_asset.exists())
        self.assertGreater(reference_asset.stat().st_size, 100000)

    def test_card_roles_and_copy_are_not_repeated(self) -> None:
        card_types = [card["card_type"] for card in self.cards]
        self.assertTrue(set(card_types).issubset(CARD_TYPES))
        self.assertEqual(card_types[-1], BRAND_OUTRO_TYPE)
        self.assertGreaterEqual(len(set(card_types)), 6)
        self.assertFalse([card for card in self.cards if (card.get("semantic") or {}).get("angle") in {"time_zone", "asset_flow"}])
        for card in self.content_cards():
            self.assertGreaterEqual((card.get("evidence_score") or {}).get("evidence_strength", 0), 0.6)
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
        self.assertFalse([text for text, count in action_counts.items() if text and count > 1])
        self.assertFalse([text for text, count in risk_counts.items() if text and count > 1])

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

    def test_canonical_data_mutation_is_ignored(self) -> None:
        parsed = {
            "market_summary": {"btc_price": 70000, "btc_nearest_support": 1},
            "source_findings": [
                {
                    "source": "Fake Media",
                    "title": "Fake title",
                    "url": "https://fake.example/mutated",
                    "trader_read": "external opinion may be kept, but source identity is not",
                }
            ],
        }
        normalized = normalize_external_brief(parsed, self.brief, "fake-provider")
        self.assertEqual(normalized["market_summary"]["btc_price"], 62971)
        self.assertEqual(normalized["market_summary"]["btc_nearest_support"], 62500)
        self.assertNotEqual(normalized["source_findings"][0]["url"], "https://fake.example/mutated")
        self.assertEqual(normalized["source_findings"][0]["url"], self.brief["source_findings"][0]["url"])

    def test_metric_deletion_and_patch_replacement_do_not_mutate_canonical_fields(self) -> None:
        news_card = copy.deepcopy(next(card for card in self.cards if card["card_type"] == "news_context"))
        patch_result = {
            "cards": [
                {
                    "card_id": news_card["card_id"],
                    "headline": "WHOLE CARD SHOULD BE IGNORED",
                    "metrics": [{"id": "btc_price", "raw_value": 70000}],
                    "source": {"url": "https://fake.example/whole-card"},
                }
            ],
            "patches": [
                {
                    "card_id": news_card["card_id"],
                    "copy": {"headline": "Patch headline only"},
                    "metrics": [],
                    "source": {"url": "https://fake.example/patch"},
                }
            ],
        }
        merged = merge_stage_patch([news_card], patch_result, "card_copy")
        reconciled = reconcile_cards_with_canonical(merged, self.metrics, self.resources)
        self.assertEqual(reconciled[0]["headline"], "Patch headline only")
        metric_by_id = {metric["id"]: metric for metric in reconciled[0]["metrics"]}
        self.assertEqual(metric_by_id["btc_price"]["raw_value"], 62971)
        self.assertEqual(reconciled[0]["source"]["url"], "https://example.com/btc-etf-flow")

    def test_no_evidence_conclusion_does_not_auto_pass(self) -> None:
        weak_metrics = locked_market_metrics({"btc_price": 62971}, "2026-08-15T00:00:00Z", "daily")
        profile = evidence_profile("market_conclusion", "decision", {"metrics": weak_metrics, "findings": [], "resources": []})
        self.assertLess(profile["evidence_strength"], 0.6)

    def test_derivatives_and_rsi_semantics_follow_data_direction(self) -> None:
        derivative_card = copy.deepcopy(next(card for card in self.cards if card["card_type"] == "derivatives"))
        for metric in derivative_card["metrics"]:
            if metric["id"] == "funding":
                metric["raw_value"] = -0.02
                metric["value"] = "-0.02%"
            if metric["id"] == "rsi14":
                metric["raw_value"] = 80
                metric["value"] = "80"
        copy_result = ja_copy_for_card(derivative_card)
        text = " ".join(str(value) for value in copy_result.values())
        self.assertIn("ショート側", text)
        self.assertNotIn("ロング優勢", text)
        self.assertNotIn("ロング寄り", text)
        self.assertIn("過熱圏", text)
        self.assertNotIn("まだ過熱ではない", text)

    def test_source_binding_and_news_reaction_contract(self) -> None:
        news_card = next(card for card in self.cards if card["card_type"] == "news_context")
        source_id = news_card["source"]["source_id"]
        source_refs = [ref for ref in news_card.get("evidence_refs") or [] if ref.startswith("source:")]
        self.assertTrue(source_refs)
        self.assertTrue(all(source_id in ref for ref in source_refs))
        self.assertEqual(news_card["source"]["url"], "https://example.com/btc-etf-flow")
        text = visible_card_text(news_card)
        for forbidden in ["価格はまだ答えていない", "市場は答えていない", "反応しなかった"]:
            self.assertNotIn(forbidden, text)

    def test_renderable_false_cards_are_removed_from_production(self) -> None:
        bad_card = copy.deepcopy(next(card for card in self.cards if card["card_type"] == "key_levels"))
        bad_card.setdefault("qa", {})["renderable"] = False
        final_cards, warnings = finalize_card_set([bad_card], "test", "ja-JP", {"provider": PROVIDER_LOCAL}, self.metrics, self.resources)
        self.assertEqual([card["card_type"] for card in final_cards], [BRAND_OUTRO_TYPE])
        self.assertEqual(bad_card["qa"].get("severity"), "BLOCKING")
        self.assertTrue(any("removed" in warning for warning in warnings))

    def test_brand_outro_uses_configured_cta(self) -> None:
        configured_cta = "フォローして、\n今日の勢力ポイントを確認。"
        cards, _meta = derive_variant(
            self.cards,
            5,
            "configured",
            "ja-JP",
            {"brand_outro": {"cta": configured_cta}},
            self.package["content_quality"]["editor_passes"]["6장"],
        )
        self.assertEqual(cards[-1]["card_type"], BRAND_OUTRO_TYPE)
        self.assertEqual(cards[-1]["key_message"], configured_cta)
        checked, warnings = editor_pass_qa(cards)
        self.assertTrue(checked[-1]["qa"].get("renderable", True))
        self.assertFalse([warning for warning in warnings if "brand_outro missing configured CTA" in warning])

    def test_character_and_layout_variation(self) -> None:
        shots = [card["visual_direction"]["character_shot"] for card in self.cards]
        layouts = [card["visual_direction"]["layout_variant"] for card in self.cards]
        self.assertFalse([(idx, shots[idx]) for idx in range(1, len(shots)) if shots[idx] == shots[idx - 1]])
        self.assertFalse([(idx, layouts[idx]) for idx in range(1, len(layouts)) if layouts[idx] == layouts[idx - 1]])
        key_card = next(card for card in self.cards if card["card_type"] == "key_levels")
        self.assertLessEqual(key_card["visual_direction"]["character_visibility"], 0.2)
        self.assertGreaterEqual(self.cards[0]["visual_direction"]["character_visibility"], 0.45)
        self.assertGreaterEqual(self.cards[-1]["visual_direction"]["character_visibility"], 0.5)
        self.assertEqual(self.cards[-1]["visual_direction"]["layout_variant"], "brand_outro")

    def test_vertical_prompts_and_excel_export(self) -> None:
        for card in self.cards:
            direction = card["visual_direction"]
            self.assertIn("4:5", direction["image_prompts"])
            self.assertIn("9:16", direction["image_prompts"])
            self.assertIn("Faceless adult male anonymous market observer", direction["image_prompts"]["4:5"])
            self.assertIn("no readable Japanese text generated by the image model", direction["image_prompts"]["4:5"])
            self.assertIn("visible face", direction["negative_prompt"])
            self.assertNotIn("勢力ハンター", direction["image_prompts"]["4:5"])
        visual_rows = flatten_visual_direction_rows(self.package)
        self.assertGreaterEqual(len(visual_rows), 7)
        excel_bytes = build_excel_bytes(self.brief, self.package, self.resources, self.snapshot)
        self.assertGreater(len(excel_bytes), 20000)

    def test_master_carousel_variants_share_one_analysis_and_call_count(self) -> None:
        master_ids = {
            meta.get("master_analysis_id")
            for meta in (self.package["content_quality"]["editor_passes"] or {}).values()
        }
        self.assertEqual(len(master_ids), 1)
        original_reason = engine.reason
        calls: list[str] = []

        def counting_reason(*args, **kwargs):
            calls.append(args[1])
            return original_reason(*args, **kwargs)

        engine.reason = counting_reason
        try:
            generate_content_package(self.brief, self.resources, 6, {"provider": PROVIDER_LOCAL}, DEFAULT_OUTPUT_LOCALE)
        finally:
            engine.reason = original_reason
        self.assertEqual(calls, ["carousel_plan", "card_copy", "ja_localization", "visual_direction"])

    def test_global_context_has_provenance(self) -> None:
        market = summarize_market(self.snapshot)
        self.assertEqual(market["btc_dominance"], 50.8333)
        self.assertEqual(market["eth_btc"], 0.02993473)
        self.assertEqual(market["total2_market_cap"], 1140000000000)
        self.assertEqual(market["total3_market_cap"], 915000000000)
        self.assertIn("btc_dominance", market["global_context_sources"])
        self.assertIn("total2_market_cap", market["global_context_provenance"])
        self.assertIn("total3_market_cap", market["global_context_provenance"])

    def test_external_backend_failure_falls_back_without_crash(self) -> None:
        package = generate_content_package(
            self.brief,
            self.resources,
            6,
            {"provider": PROVIDER_OPENAI_COMPATIBLE},
            "ja-JP",
        )
        cards = package["cards"]["6장"]
        self.assertEqual(len(cards), 7)
        self.assertEqual(cards[-1]["card_type"], BRAND_OUTRO_TYPE)
        meta = package["content_quality"]["editor_passes"]["6장"]["reasoning"]
        self.assertEqual(meta["plan"]["provider"], PROVIDER_LOCAL)

    def test_legacy_streamlit_pages_are_not_in_production_namespace(self) -> None:
        pages_dir = ROOT / "apps" / "streamlit" / "pages"
        if not pages_dir.exists():
            return
        self.assertFalse([path.name for path in pages_dir.glob("*.py")])


if __name__ == "__main__":
    unittest.main()
