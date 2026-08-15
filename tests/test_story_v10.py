from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import mode_exporter_v5  # noqa: E402
import story_content_pipeline_v5  # noqa: E402
import story_graph_engine  # noqa: E402
import story_renderer_v5  # noqa: E402
import story_source_engine_v5  # noqa: E402


TRANSFORMATION = {
    "id": "generic-transform-1",
    "source": "Independent Business Desk",
    "source_type": "rss",
    "region": "Global",
    "category": "Infrastructure",
    "title": "NeoGrid Holdings、GPUホスティングからAI計算基盤へ事業を拡大",
    "url": "https://example.com/neogrid",
    "tags": "INFRASTRUCTURE, AI, COMPUTE",
    "trader_score": 40,
    "risk_score": 10,
    "excerpt": "NeoGrid Holdingsが既存設備をAI計算基盤へ転用する。",
    "material": (
        "NeoGrid HoldingsはこれまでGPUホスティングを主力事業としてきた。 "
        "同社は既存の電力設備をAI計算基盤へ転用し、大手クラウド企業と10年間の利用契約を締結した。 "
        "契約対象は420MWで、契約価値は約1200億円。 "
        "2028年に第1期を稼働し、2030年までに全設備の稼働を計画している。 "
        "AI向け計算需要の増加を受け、既存設備の収益源を広げる。"
    ),
}

POLICY = {
    "id": "generic-policy-1",
    "source": "Public Policy Desk",
    "source_type": "rss",
    "region": "Japan",
    "category": "Policy",
    "title": "新しいデジタル資産保管ルール、2027年から段階適用へ",
    "url": "https://example.com/policy",
    "tags": "POLICY, DIGITAL ASSET",
    "trader_score": 42,
    "risk_score": 12,
    "excerpt": "金融当局がデジタル資産保管ルールの段階適用を公表した。",
    "material": (
        "金融当局はデジタル資産の保管事業者に対する新しい規制枠組みを公表した。 "
        "新ルールは2027年4月から段階的に施行する予定だ。 "
        "対象事業者には顧客資産の分別管理と監査報告が求められる。 "
        "既存事業者には12か月の移行期間を設ける。"
    ),
}

SECOND_PUBLISHER_SAME_EVENT = {
    **TRANSFORMATION,
    "id": "generic-transform-2",
    "source": "Another Editorial Desk",
    "url": "https://example.net/neogrid-deal",
    "title": "NeoGrid Holdings、420MWのAI計算基盤契約を締結",
    "material": (
        "NeoGrid Holdingsは大手クラウド企業とAI計算基盤の利用契約を締結した。 "
        "対象は420MWで、契約価値は約1200億円。2028年から段階稼働する。"
    ),
}


class StoryV10Test(unittest.TestCase):
    def test_generic_source_engine_has_no_named_company_registry_or_archetype_classifier(self) -> None:
        source = (ROOT / "apps" / "streamlit" / "story_source_engine_v5.py").read_text(encoding="utf-8")
        for forbidden in ["Riot Platforms", "Anthropic", "BlackRock", "Coinspeaker", "KNOWN_ENTITIES", "classify_archetype"]:
            self.assertNotIn(forbidden, source)
        row = story_source_engine_v5.annotate_resource(TRANSFORMATION)
        self.assertEqual(row["story_archetype_hint"], "dynamic")
        self.assertGreater(row["story_score"], 0)
        self.assertIn("NeoGrid Holdings", row["story_entities"])

    def test_generic_event_cluster_uses_event_evidence_not_publisher(self) -> None:
        a, b = story_source_engine_v5.annotate_resources([TRANSFORMATION, SECOND_PUBLISHER_SAME_EVENT])
        self.assertGreaterEqual(story_source_engine_v5.event_similarity(a, b), 0.47)
        clusters = story_source_engine_v5.cluster_story_candidates([TRANSFORMATION, SECOND_PUBLISHER_SAME_EVENT])
        self.assertEqual(len(clusters), 1)

    def test_graph_extracts_relations_without_article_specific_code(self) -> None:
        hero = {"resource_ids": [TRANSFORMATION["id"]], "entities": ["NeoGrid Holdings"]}
        graph = story_graph_engine.extract_fact_graph(hero, [TRANSFORMATION])
        relations = {f["relation"] for f in graph["facts"]}
        self.assertIn("before_state", relations)
        self.assertTrue({"change", "deal"} & relations)
        self.assertIn("future", relations)
        blob = str(graph)
        self.assertIn("420MW", blob)
        self.assertIn("1200億円", blob)
        self.assertIn("2028", blob)
        self.assertIn("2030", blob)

    def test_story_plan_is_fact_first_and_archetype_is_only_a_tag(self) -> None:
        hero = {"resource_ids": [TRANSFORMATION["id"]], "entities": ["NeoGrid Holdings"], "hero_resource": TRANSFORMATION}
        graph = story_graph_engine.extract_fact_graph(hero, [TRANSFORMATION])
        plan = story_graph_engine.build_story_plan(hero, graph, 6)
        self.assertEqual(plan["planning_policy"], "facts first -> multi-relation graph -> dynamic card roles -> archetype tag last")
        self.assertGreaterEqual(len(plan["cards"]), 6)
        roles = [item["role"] for item in plan["cards"]]
        self.assertEqual(roles[0], "hook")
        self.assertTrue({"scale", "deal"} & set(roles))
        self.assertIn(roles[-1], {"watch", "impact"})

        pipeline_source = (ROOT / "apps" / "streamlit" / "story_content_pipeline_v5.py").read_text(encoding="utf-8")
        self.assertNotIn("Riot", pipeline_source)
        self.assertNotIn("Anthropic", pipeline_source)
        self.assertNotIn("Coinspeaker", pipeline_source)
        self.assertNotIn("if archetype ==", pipeline_source)

    def test_different_resource_type_builds_different_plan_without_code_change(self) -> None:
        result = story_content_pipeline_v5.generate_story_package(
            [POLICY], 7, {"provider": story_content_pipeline_v5.PROVIDER_LOCAL}, generation_seed="policy-v10"
        )
        self.assertIsNone(result.error)
        package = result.package
        plan = package["story_context"]["story_plan"]
        self.assertEqual(plan["archetype_tag"], "policy_change")
        roles = [item["role"] for item in plan["cards"]]
        self.assertIn("watch", roles)
        self.assertNotIn("old_business", roles)

    def test_pipeline_builds_fact_bound_cards_and_graph_export(self) -> None:
        result = story_content_pipeline_v5.generate_story_package(
            [TRANSFORMATION], 7, {"provider": story_content_pipeline_v5.PROVIDER_LOCAL}, generation_seed="transform-v10"
        )
        self.assertIsNone(result.error)
        package = result.package
        self.assertEqual(package["content_quality"]["pipeline"], "story-content-v10.2")
        self.assertEqual(package["content_quality"]["source_engine"], "story-source-v10.1")
        self.assertEqual(package["content_quality"]["graph_engine"], "story-graph-v10.1")
        cards = package["cards"]["STORY"][:-1]
        self.assertEqual(len(cards), 6)
        self.assertTrue(all((c.get("qa") or {}).get("fact_bound") for c in cards))
        self.assertTrue(all((c.get("qa") or {}).get("claim_evidence_consistent") for c in cards))
        self.assertTrue(all(c.get("evidence_excerpt") for c in cards))
        self.assertGreaterEqual(len({(c.get("visual_direction") or {}).get("scene_type") for c in cards}), 4)
        diag = story_renderer_v5.scene_diagnostics(cards)
        self.assertGreaterEqual(diag["render_signature_count"], 4)

        raw = mode_exporter_v5.build_story_excel(package, [TRANSFORMATION])
        wb = load_workbook(BytesIO(raw))
        self.assertIn("Story_Graph", wb.sheetnames)
        self.assertIn("Story_Plan", wb.sheetnames)
        self.assertEqual(len(getattr(wb["Card_Previews"], "_images", [])), 7)

    def test_runtime_routes_to_v10_generic_stack(self) -> None:
        entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('RUNTIME_TOKEN = "dual-pipeline-v10.1"', entry)
        self.assertIn('sys.modules["story_engine"] = story_source_engine_v5', entry)
        self.assertIn('sys.modules["story_content_pipeline"] = story_content_pipeline_v5', entry)
        self.assertIn('sys.modules["mode_exporter"] = mode_exporter_v5', entry)
        self.assertIn("story_graph_engine", entry)
        self.assertIn("story_renderer_v5", entry)


if __name__ == "__main__":
    unittest.main()
