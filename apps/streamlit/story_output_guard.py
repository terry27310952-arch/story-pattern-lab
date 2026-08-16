from __future__ import annotations

import copy
import re


STORY_OUTPUT_GUARD_VERSION = "story-output-guard-v6.2"
DISPLAY_BRAND_LABEL = "キヨサキ"
FORBIDDEN_VISIBLE_TOKENS = ["THE OBSERVER", "The Observer"]


JA_FALLBACKS = {
    "headline": "次に見るポイント",
    "subheadline": "確認できた事実だけを残し、次の変化を待つ。",
    "key_message": "確認できた事実だけを残し、次の変化を待つ。",
    "eyebrow": "STORY",
}


def _clean_visible(value: object) -> str:
    text = " ".join(str(value or "").split())
    for token in FORBIDDEN_VISIBLE_TOKENS:
        text = text.replace(token, "")
    text = re.sub(r"[가-힣]+(?:\s+[가-힣]+)*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _safe_field(card: dict, key: str) -> str:
    cleaned = _clean_visible(card.get(key))
    if cleaned and not re.search(r"[가-힣]", cleaned):
        return cleaned
    return JA_FALLBACKS[key]


def sanitize_story_package(package: dict) -> dict:
    next_package = copy.deepcopy(package or {})
    for _, cards in (next_package.get("cards") or {}).items():
        for card in cards or []:
            if card.get("card_type") == "brand_outro":
                card["eyebrow"] = DISPLAY_BRAND_LABEL
                card["headline"] = "勢力ハンター キヨサキ"
                card["subheadline"] = ""
                card["key_message"] = _clean_visible(card.get("key_message")) or "フォローして、勢力が入ったポイントを無料でチェック。"
            elif card.get("story_role") == "hook":
                # A premium carousel hook may deliberately be a single line. Do not
                # inject generic fallback body copy into an intentionally empty second line.
                card["eyebrow"] = _safe_field(card, "eyebrow")
                card["headline"] = _safe_field(card, "headline")
                card["subheadline"] = _clean_visible(card.get("subheadline"))
                card["key_message"] = _clean_visible(card.get("key_message"))
            else:
                for key in ["eyebrow", "headline", "subheadline", "key_message"]:
                    card[key] = _safe_field(card, key)

            direction = card.setdefault("visual_direction", {})
            direction["brand_mark_policy"] = "text-only キヨサキ; no K monogram/icon"
            if card.get("card_type") != "brand_outro":
                direction["character_required"] = False
                direction["character_visibility"] = 0.0
                direction["character_shot"] = "none"
                direction["character_pose"] = "none"
            prompts = dict(direction.get("image_prompts") or {})
            for ratio, value in prompts.items():
                cleaned = _clean_visible(value)
                cleaned += " No K monogram, no orange K symbol, no decorative logo, no watermark."
                prompts[ratio] = cleaned.strip()
            direction["image_prompts"] = prompts

    quality = next_package.setdefault("content_quality", {})
    quality["output_guard"] = STORY_OUTPUT_GUARD_VERSION
    quality["visible_language_policy"] = "ja-JP; no Korean; no THE OBSERVER; text-only キヨサキ"
    return next_package


def apply_generation_guard(story_content_pipeline) -> None:
    if getattr(story_content_pipeline, "_kiyosaki_story_output_guard", None) == STORY_OUTPUT_GUARD_VERSION:
        return
    original = story_content_pipeline.generate_story_package

    def generate_story_package(*args, **kwargs):
        result = original(*args, **kwargs)
        if getattr(result, "package", None):
            result.package = sanitize_story_package(result.package)
        return result

    story_content_pipeline.generate_story_package = generate_story_package
    story_content_pipeline._kiyosaki_story_output_guard = STORY_OUTPUT_GUARD_VERSION
