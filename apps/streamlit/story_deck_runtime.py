from __future__ import annotations

import copy

import story_engine
import story_pipeline_runtime


STORY_DECK_RUNTIME_VERSION = "story-deck-v5.0"

# This is not a fixed carousel template. Each archetype gets a different information
# sequence so the underlying renderer/card data changes together with the story arc.
# Missing card types are skipped and the remaining cards keep their relative safety
# constraints/evidence. The brand outro is always appended last.
ARCHETYPE_CARD_ORDER: dict[str, list[str]] = {
    "contradiction": ["market_conclusion", "news_context", "derivatives", "key_levels", "scenarios", "trade_plan"],
    "money_flow": ["news_context", "derivatives", "market_conclusion", "key_levels", "scenarios", "trade_plan"],
    "policy_change": ["news_context", "market_conclusion", "key_levels", "derivatives", "scenarios", "trade_plan"],
    "power_shift": ["news_context", "market_conclusion", "derivatives", "key_levels", "scenarios", "trade_plan"],
    "hidden_giant": ["news_context", "market_conclusion", "derivatives", "key_levels", "scenarios", "trade_plan"],
    "origin_to_now": ["news_context", "market_conclusion", "key_levels", "derivatives", "scenarios", "trade_plan"],
    "historical_parallel": ["news_context", "market_conclusion", "key_levels", "derivatives", "scenarios", "trade_plan"],
    "crisis_or_risk": ["news_context", "derivatives", "market_conclusion", "key_levels", "trade_plan", "scenarios"],
    "opportunity_window": ["news_context", "market_conclusion", "derivatives", "key_levels", "scenarios", "trade_plan"],
    "market_map": ["market_conclusion", "key_levels", "derivatives", "news_context", "scenarios", "trade_plan"],
}


def _reorder_content(cards: list[dict], archetype: str) -> list[dict]:
    content = [copy.deepcopy(card) for card in cards if card.get("card_type") != "brand_outro"]
    preferred = ARCHETYPE_CARD_ORDER.get(archetype, ARCHETYPE_CARD_ORDER["market_map"])
    selected: list[dict] = []
    used: set[int] = set()

    # Pull one card of each preferred type first.
    for card_type in preferred:
        for index, card in enumerate(content):
            if index in used:
                continue
            if card.get("card_type") == card_type:
                selected.append(card)
                used.add(index)
                break

    # Any evidence-qualified extra cards remain useful. Insert them before execution so
    # 7-card variants can still include a second news/scenario angle without losing it.
    extras = [card for index, card in enumerate(content) if index not in used]
    if extras:
        trade_index = next((i for i, card in enumerate(selected) if card.get("card_type") == "trade_plan"), len(selected))
        selected[trade_index:trade_index] = extras
    return selected


def apply_story_deck(package: dict, brief: dict, resources: list[dict]) -> dict:
    next_package = copy.deepcopy(package or {})
    context = brief.get("story_context") if isinstance(brief, dict) else None
    hero = dict((context or {}).get("hero_story") or {})
    if not hero:
        hero = story_engine.select_hero_story(resources)
    archetype = str(hero.get("archetype") or "market_map")
    quality = next_package.setdefault("content_quality", {})
    blueprint = quality.get("visual_blueprint") or {}
    seed = str(blueprint.get("id") or hero.get("id") or "story-deck")

    for set_label, cards in list((next_package.get("cards") or {}).items()):
        cards = list(cards or [])
        outro = next((copy.deepcopy(card) for card in reversed(cards) if card.get("card_type") == "brand_outro"), None)
        content = _reorder_content(cards, archetype)
        roles = story_engine.story_arc(archetype, len(content))
        transformed = [
            story_pipeline_runtime._storyify_card(card, roles[index], index, hero, f"{seed}:{set_label}:deck")
            for index, card in enumerate(content)
        ]
        if outro is not None:
            transformed.append(story_pipeline_runtime._storyify_card(outro, "brand_outro", len(transformed), hero, seed))
        for index, card in enumerate(transformed, start=1):
            card["slide"] = index
            card["set"] = set_label
        next_package["cards"][set_label] = transformed

    quality["story_deck"] = {
        "runtime": STORY_DECK_RUNTIME_VERSION,
        "archetype": archetype,
        "preferred_card_order": ARCHETYPE_CARD_ORDER.get(archetype, ARCHETYPE_CARD_ORDER["market_map"]),
        "policy": "archetype changes both narrative role order and underlying card/data renderer order",
    }
    return next_package


def apply_reasoning_patch(reasoning_engine) -> None:
    if getattr(reasoning_engine, "_kiyosaki_story_deck_version", None) == STORY_DECK_RUNTIME_VERSION:
        return
    original = reasoning_engine.generate_content_package

    def generate_content_package(*args, **kwargs):
        package = original(*args, **kwargs)
        brief = args[0] if args else kwargs.get("brief") or {}
        resources = args[1] if len(args) > 1 else kwargs.get("resources") or []
        return apply_story_deck(package, brief, list(resources or []))

    reasoning_engine.generate_content_package = generate_content_package
    reasoning_engine._kiyosaki_story_deck_version = STORY_DECK_RUNTIME_VERSION
