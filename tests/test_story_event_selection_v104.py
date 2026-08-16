from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import story_content_pipeline_v5  # noqa: E402
import story_hook_engine  # noqa: E402
import story_output_guard  # noqa: E402
import story_source_engine_v5  # noqa: E402


TRANSFORMATION = {
    "id": "event-transform",
    "source": "Business Desk",
    "source_type": "rss",
    "region": "Japan",
    "category": "Infrastructure",
    "title": "NeoGrid、GPUホスティングからAI計算基盤へ事業を転換",
    "url": "https://example.com/transform",
    "tags": "AI, INFRASTRUCTURE",
    "trader_score": 30,
    "risk_score": 10,
    "excerpt": "NeoGridが既存設備をAI計算基盤へ転用する。",
    "material": (
        "NeoGridはこれまでGPUホスティングを主力事業としてきた。 "
        "同社は既存の電力設備をAI計算基盤へ転用し、大手クラウド企業と10年間の利用契約を締結した。 "
        "契約対象は420MWで、契約価値は約1200億円。 "
        "2028年に第1期を稼働し、2030年までに全設備の稼働を計画している。 "
        "AI向け計算需要の増加を受け、既存設備の収益源を広げる。"
    ),
}

POLICY = {
    "id": "event-policy",
    "source": "Policy Desk",
    "source_type": "rss",
    "region": "Japan",
    "category": "Policy",
    "title": "デジタル資産保管の新ルール、2027年から段階適用へ",
    "url": "https://example.com/policy",
    "tags": "POLICY, DIGITAL ASSET",
    "trader_score": 40,
    "risk_score": 12,
    "excerpt": "金融当局がデジタル資産保管ルールの段階適用を公表した。",
    "material": (
        "金融当局はデジタル資産の保管事業者に対する新しい規制枠組みを公表した。 "
        "新ルールは2027年4月から段階的に施行する予定だ。 "
        "対象事業者には顧客資産の分別管理と監査報告が求められる。 "
        "既存事業者には12か月の移行期間を設ける。 "
        "制度変更によって保管事業者の運用コストと参入条件が変わる可能性がある。"
    ),
}


class StoryEventSelectionV104Test(unittest.TestCase):
    def test_user_selected_event_is_locked_and_not_replaced_by_ranking(self) -> None:
        candidates = story_source_engine_v5.build_story_candidates([TRANSFORMATION, POLICY])
        selected = next(c for c in candidates if POLICY["id"] in c.get("resource_ids", []))
        result = story_content_pipeline_v5.generate_story_package(
            [TRANSFORMATION, POLICY],
            7,
            {"provider": story_content_pipeline_v5.PROVIDER_LOCAL},
            generation_seed="event-lock-v104",
            selected_event=selected,
        )
        self.assertIsNone(result.error)
        package = result.package
        self.assertEqual(package["content_quality"]["hero_selection_reason"], "user_selected_event_locked")
        self.assertEqual(package["content_quality"]["selected_event_id"], selected["id"])
        self.assertEqual(package["story_context"]["selected_event_id"], selected["id"])
        self.assertTrue(set(package["story_context"]["hero_resource_ids"]).issubset(set(selected["resource_ids"])))
        self.assertNotIn(TRANSFORMATION["id"], package["story_context"]["hero_resource_ids"])

    def test_hook_engine_filters_generic_copy_and_chooses_stronger_candidate(self) -> None:
        raw = {
            "candidates": [
                {"headline": "まず確認するポイント", "subline": "", "angle": "generic"},
                {"headline": "採掘会社が、AIの計算基盤へ動いた。", "subline": "収益の前提そのものが変わり始めている。", "angle": "transformation"},
                {"headline": "前提が変わった。", "subline": "", "angle": "short"},
            ]
        }
        facts = [{"sentence": "採掘事業者は既存設備をAI計算基盤へ転用した。", "values": []}]
        with patch.object(story_hook_engine, "_call_hook_model", return_value=(raw, None)):
            result = story_hook_engine.generate_hook(
                {"provider": "openai_compatible"},
                {"headline_seed": "採掘企業がAI基盤へ転換", "entities": ["NeoGrid"]},
                {"thesis": "既存設備をAI計算基盤へ転用した。"},
                facts,
                "採掘企業がAI基盤へ転換",
            )
        self.assertEqual(result["source"], "llm")
        self.assertGreaterEqual(result["candidate_count"], 1)
        self.assertTrue(result["style_pass"])
        self.assertNotIn("まず", result["headline"])
        self.assertLessEqual(len(result["headline"]), 48)
        self.assertLessEqual(len(result["subline"]), 44)

    def test_one_line_hook_survives_output_guard_without_generic_body_injection(self) -> None:
        package = {
            "cards": {
                "STORY": [
                    {
                        "card_type": "story_editorial",
                        "story_role": "hook",
                        "eyebrow": "HOOK",
                        "headline": "前提が、静かに変わった。",
                        "subheadline": "",
                        "key_message": "",
                        "visual_direction": {},
                    }
                ]
            }
        }
        sanitized = story_output_guard.sanitize_story_package(package)
        card = sanitized["cards"]["STORY"][0]
        self.assertEqual(card["subheadline"], "")
        self.assertEqual(card["key_message"], "")

    def test_story_ui_uses_single_event_radio_while_trader_keeps_multiselect_articles(self) -> None:
        source = (ROOT / "apps" / "streamlit" / "app_v2.py").read_text(encoding="utf-8")
        self.assertIn('key="story_event_radio"', source)
        self.assertIn("selected_story_event_id", source)
        self.assertIn("selected_event=event", source)
        self.assertNotIn('key="resource_selector_story"', source)
        self.assertIn('key="resource_selector_trader"', source)
        self.assertIn("user selects exactly ONE Event Candidate", source)

    def test_dedicated_hook_pass_is_separate_from_generic_card_model(self) -> None:
        source = (ROOT / "apps" / "streamlit" / "story_content_pipeline_v5.py").read_text(encoding="utf-8")
        self.assertIn('str(item.get("role")) != "hook"', source)
        self.assertIn("story_hook_engine.generate_hook", source)
        self.assertIn("hook_candidate_count", source)
        self.assertIn("weak_hook", source)


if __name__ == "__main__":
    unittest.main()
