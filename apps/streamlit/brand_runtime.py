from __future__ import annotations

from typing import Callable


DISPLAY_BRAND_LABEL = "キヨサキ"
INTERNAL_CHARACTER_CODENAME = "THE OBSERVER"


def _clean_source_footer(card: dict) -> str:
    source = card.get("source") or {}
    publisher = str(source.get("publisher") or "").strip()
    short_title = str(source.get("short_title") or "").strip()
    parts = [DISPLAY_BRAND_LABEL]
    if publisher and publisher not in {DISPLAY_BRAND_LABEL, "勢力ハンター キヨサキ"}:
        parts.append(publisher)
    if short_title and short_title not in {"Brand Ending", "FOLLOW"}:
        parts.append(short_title)
    return " · ".join(parts)


def apply_brand_patch(reasoning_engine) -> None:
    """Keep THE OBSERVER internal while exposing キヨサキ as the public card brand.

    This is applied before Streamlit imports app.py, so every card generated through
    the deployed app uses the public Kiyosaki label without changing the internal
    character codename used by visual prompts and metadata.
    """
    if getattr(reasoning_engine, "_kiyosaki_display_patch_applied", False):
        return

    original_ja_copy: Callable = reasoning_engine.ja_copy_for_card
    original_ko_copy: Callable = reasoning_engine.ko_copy_for_card
    original_make_outro: Callable = reasoning_engine.make_brand_outro_card
    original_make_card_set: Callable = reasoning_engine.make_card_set

    def ja_copy_for_card(card: dict) -> dict:
        copy = dict(original_ja_copy(card))
        copy["eyebrow"] = DISPLAY_BRAND_LABEL
        if card.get("card_type") == reasoning_engine.BRAND_OUTRO_TYPE:
            # The internal character codename must not leak into public display copy.
            copy["subheadline"] = ""
        return copy

    def ko_copy_for_card(card: dict) -> dict:
        copy = dict(original_ko_copy(card))
        copy["eyebrow"] = DISPLAY_BRAND_LABEL
        if card.get("card_type") == reasoning_engine.BRAND_OUTRO_TYPE:
            copy["subheadline"] = ""
        return copy

    def make_brand_outro_card(*args, **kwargs) -> dict:
        card = original_make_outro(*args, **kwargs)
        card["eyebrow"] = DISPLAY_BRAND_LABEL
        card["subheadline"] = ""
        return card

    def make_card_set(*args, **kwargs):
        cards, meta = original_make_card_set(*args, **kwargs)
        for card in cards:
            card["eyebrow"] = DISPLAY_BRAND_LABEL
            if card.get("card_type") == reasoning_engine.BRAND_OUTRO_TYPE:
                card["subheadline"] = ""
            card["footer"] = _clean_source_footer(card)
        return cards, meta

    reasoning_engine.ja_copy_for_card = ja_copy_for_card
    reasoning_engine.ko_copy_for_card = ko_copy_for_card
    reasoning_engine.make_brand_outro_card = make_brand_outro_card
    reasoning_engine.make_card_set = make_card_set

    # Keep the visual character concept internal, but expose a public-facing label
    # for downstream UI/debug consumers that need an explicit display brand.
    reasoning_engine.DISPLAY_BRAND_LABEL = DISPLAY_BRAND_LABEL
    if isinstance(getattr(reasoning_engine, "OBSERVER_BRAND_SYSTEM", None), dict):
        reasoning_engine.OBSERVER_BRAND_SYSTEM["display_brand_label"] = DISPLAY_BRAND_LABEL
        reasoning_engine.OBSERVER_BRAND_SYSTEM["internal_character_codename"] = INTERNAL_CHARACTER_CODENAME

    if isinstance(getattr(reasoning_engine, "JA_INSIGHT_LABELS", None), dict):
        reasoning_engine.JA_INSIGHT_LABELS[reasoning_engine.BRAND_OUTRO_TYPE] = [
            "FOLLOW",
            DISPLAY_BRAND_LABEL,
            "勢力ハンター",
        ]

    reasoning_engine._kiyosaki_display_patch_applied = True
