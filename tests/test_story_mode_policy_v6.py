from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import reasoning_engine  # noqa: E402
import story_content_pipeline  # noqa: E402
import story_engine  # noqa: E402
import story_mode_policy  # noqa: E402


WEAK_BUT_NARRATIVE = {
    "id": "weak-policy-1",
    "source": "Official Policy Feed",
    "source_type": "official",
    "title": "Japan regulator changes digital asset custody framework",
    "url": "https://example.com/policy",
    "excerpt": "Japan regulator changes a digital asset custody framework for exchanges and institutions.",
    "material": "Japan regulator changes a digital asset custody framework for exchanges and institutions. The new rule changes who can provide custody and when compliance begins.",
    "tags": "REG, EXCHANGE",
    "trader_score": 20,
    "risk_score": 18,
}


class StoryModePolicyV6Test(unittest.TestCase):
    def test_story_policy_does_not_silently_downgrade_to_market_map(self) -> None:
        original_context = story_engine.story_context
        original_marker = getattr(story_engine, "_kiyosaki_strict_story_context", None)
        if hasattr(story_engine, "_kiyosaki_strict_story_context"):
            delattr(story_engine, "_kiyosaki_strict_story_context")
        try:
            base = original_context([WEAK_BUT_NARRATIVE])
            base_hero = base.get("hero_story") or {}
            story_mode_policy.apply_strict_story_context(story_engine)
            strict = story_engine.story_context([WEAK_BUT_NARRATIVE])
            strict_hero = strict.get("hero_story") or {}
            self.assertFalse(strict_hero.get("fallback"))
            self.assertEqual(strict_hero.get("archetype"), strict_hero.get("hero_resource", {}).get("story_archetype_hint") or strict_hero.get("archetype"))
            self.assertIn("no silent market_map downgrade", strict.get("policy", ""))
            if base_hero.get("fallback"):
                self.assertNotEqual(strict.get("policy"), base.get("policy"))
        finally:
            story_engine.story_context = original_context
            if original_marker is None:
                if hasattr(story_engine, "_kiyosaki_strict_story_context"):
                    delattr(story_engine, "_kiyosaki_strict_story_context")
            else:
                story_engine._kiyosaki_strict_story_context = original_marker

    def test_story_generator_never_calls_trader_reasoning(self) -> None:
        original = reasoning_engine.generate_trader_brief

        def forbidden(*args, **kwargs):
            raise AssertionError("story pipeline called trader reasoning")

        reasoning_engine.generate_trader_brief = forbidden
        try:
            result = story_content_pipeline.generate_story_package(
                [WEAK_BUT_NARRATIVE],
                total_card_count=6,
                config={"provider": story_content_pipeline.PROVIDER_LOCAL},
                generation_seed="story-only",
            )
            self.assertIsNone(result.error)
            self.assertEqual(result.package.get("mode"), "story")
        finally:
            reasoning_engine.generate_trader_brief = original


if __name__ == "__main__":
    unittest.main()
