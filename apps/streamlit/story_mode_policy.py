from __future__ import annotations


STORY_MODE_POLICY_VERSION = "story-mode-policy-v6.0"


def apply_strict_story_context(story_engine) -> None:
    """Prevent Storytelling mode from silently collapsing back into a market brief.

    The legacy story selector intentionally changed weak candidates into `market_map`.
    That behavior was useful when story was a postprocessor on a trader briefing, but it
    defeats the new product split. Story mode must keep the best narrative archetype
    found in its selected sources, even when confidence is modest. The UI can show the
    score/confidence and let the user choose stronger material instead of secretly
    changing the product back into a technical market carousel.
    """
    if getattr(story_engine, "_kiyosaki_strict_story_context", None) == STORY_MODE_POLICY_VERSION:
        return

    original_story_context = story_engine.story_context

    def story_context(resources: list[dict]) -> dict:
        annotated = story_engine.annotate_resources(resources)
        candidates = story_engine.build_story_candidates(annotated)
        if not candidates:
            result = original_story_context(resources)
            result["policy"] = "story mode: no candidate available; explicit fallback only"
            return result
        hero = dict(candidates[0])
        hero["fallback"] = False
        return {
            "version": story_engine.STORY_ENGINE_VERSION,
            "hero_story": hero,
            "candidates": candidates[:8],
            "ranked_resource_ids": [
                row.get("id") or row.get("source_id") or row.get("url")
                for row in annotated
            ],
            "resource_count": len(annotated),
            "policy": "story mode keeps the strongest narrative archetype; no silent market_map downgrade",
        }

    story_engine.story_context = story_context
    story_engine._kiyosaki_strict_story_context = STORY_MODE_POLICY_VERSION
