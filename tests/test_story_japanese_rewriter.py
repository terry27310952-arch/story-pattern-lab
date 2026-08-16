from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import story_japanese_rewriter  # noqa: E402
import story_output_guard  # noqa: E402


class StoryJapaneseRewriterTest(unittest.TestCase):
    def test_parser_recovers_json_after_model_preamble(self) -> None:
        raw = 'Here is the requested result:\n```json\n{"headline":"資金は入った。","body":"価格はまだ追いついていない。"}\n```'
        parsed = story_japanese_rewriter.parse_json_object(raw)
        self.assertEqual(parsed["headline"], "資金は入った。")
        self.assertEqual(parsed["body"], "価格はまだ追いついていない。")

    def test_rewriter_retries_when_first_answer_invents_number(self) -> None:
        bad = '{"headline":"2029年に転換","body":"事業の軸が変わる。"}'
        good = '{"headline":"2028年が次の節目","body":"計画では2028年の稼働が示されている。"}'
        config = {"provider": "ollama", "base_url": "https://ollama.com/api", "model": "gpt-oss:20b", "api_key": "x"}
        with patch.object(story_japanese_rewriter, "_call_model", side_effect=[(bad, None), (good, None)]) as mocked:
            result = story_japanese_rewriter.rewrite_card(
                config,
                role="watch",
                evidence="The project is scheduled to begin operation in 2028.",
                subject="NeoGrid",
            )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn("2028", result["headline"] + result["body"])
        self.assertEqual(mocked.call_count, 2)

    def test_rewriter_has_line_protocol_third_recovery(self) -> None:
        config = {"provider": "ollama", "base_url": "https://ollama.com/api", "model": "gpt-oss:20b", "api_key": "x"}
        responses = [
            ("not json", None),
            ('{"headline":"English only","body":"still English"}', None),
            ("HEADLINE: 採掘会社がAIへ動いた。\nBODY: 既存設備をAI向けに転用する計画が示された。", None),
        ]
        with patch.object(story_japanese_rewriter, "_call_model", side_effect=responses):
            result = story_japanese_rewriter.rewrite_card(
                config,
                role="change",
                evidence="The mining company plans to repurpose existing facilities for AI infrastructure.",
                subject="NeoGrid",
            )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["attempts"], 3)
        self.assertGreaterEqual(story_japanese_rewriter.japanese_ratio(result["headline"] + result["body"]), 0.42)

    def test_output_guard_repairs_english_batch_card_before_pipeline_fallback(self) -> None:
        fake = SimpleNamespace()
        fake.PROVIDER_LOCAL = "local"
        fake._kiyosaki_ja_rewriter_patch = None
        fake._model_cards = lambda config, hero, plan, graph: (
            {"change": {"role": "change", "headline": "What changed", "body": "The business model changed."}},
            None,
        )
        fake._subject = lambda plan, hero: "NeoGrid"
        fake._card_facts = lambda graph, item: [{"sentence": "NeoGrid shifted its business model toward AI infrastructure."}]
        fake._evidence_text = lambda facts: facts[0]["sentence"]
        fake._clean = lambda value, limit=900: str(value or "")[:limit]
        fake._claim_ok = lambda headline, body, evidence: True

        with patch.object(
            story_japanese_rewriter,
            "rewrite_card",
            return_value={
                "accepted": True,
                "headline": "事業の軸が変わった",
                "body": "NeoGridはAIインフラへ事業の軸を移した。",
                "attempts": 1,
                "warning": "",
            },
        ):
            story_output_guard._patch_model_cards(fake)
            cards, warning = fake._model_cards(
                {"provider": "ollama"},
                {"entities": ["NeoGrid"]},
                {"cards": [{"role": "change", "fact_ids": ["f1"]}]},
                {"facts": []},
            )

        self.assertEqual(cards["change"]["headline"], "事業の軸が変わった")
        self.assertIn("AIインフラ", cards["change"]["body"])
        self.assertIn("change:repaired:1", warning)


if __name__ == "__main__":
    unittest.main()
