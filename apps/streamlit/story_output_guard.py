from __future__ import annotations

import copy
import re

import story_japanese_rewriter


STORY_OUTPUT_GUARD_VERSION = "story-output-guard-v6.3"
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
    quality["japanese_rewriter"] = story_japanese_rewriter.STORY_JAPANESE_REWRITER_VERSION
    quality["visible_language_policy"] = "ja-JP; no Korean; no THE OBSERVER; text-only キヨサキ"
    return next_package


def _patch_model_cards(story_content_pipeline) -> None:
    """Repair missing/English batch LLM cards one role at a time before fallback copy is used."""
    if getattr(story_content_pipeline, "_kiyosaki_ja_rewriter_patch", None) == STORY_OUTPUT_GUARD_VERSION:
        return
    original_model_cards = getattr(story_content_pipeline, "_model_cards", None)
    if not callable(original_model_cards):
        return

    def model_cards_with_ja_repair(config: dict, hero: dict, plan: dict, graph: dict):
        by_role, warning = original_model_cards(config, hero, plan, graph)
        by_role = dict(by_role or {})
        provider = str(config.get("provider") or getattr(story_content_pipeline, "PROVIDER_LOCAL", "local"))
        if provider == getattr(story_content_pipeline, "PROVIDER_LOCAL", "local"):
            return by_role, warning

        repair_notes: list[str] = []
        failed_roles: list[str] = []
        subject = story_content_pipeline._subject(plan, hero)

        for item in plan.get("cards") or []:
            role = str(item.get("role") or "")
            if not role or role == "hook":
                continue
            facts = story_content_pipeline._card_facts(graph, item)
            if not facts:
                continue
            evidence = story_content_pipeline._evidence_text(facts)
            current = dict(by_role.get(role) or {})
            headline = story_content_pipeline._clean(current.get("headline"), 90)
            body = story_content_pipeline._clean(current.get("body"), 300)
            current_ok = bool(
                headline
                and body
                and story_japanese_rewriter.japanese_ratio(f"{headline} {body}") >= 0.45
                and story_content_pipeline._claim_ok(headline, body, evidence)
            )
            if current_ok:
                current["_copy_source"] = "batch_llm"
                by_role[role] = current
                continue

            repair = story_japanese_rewriter.rewrite_card(
                config,
                role=role,
                evidence=evidence,
                subject=subject,
                original_headline=headline,
                original_body=body,
                hook=False,
            )
            repaired_headline = story_content_pipeline._clean(repair.get("headline"), 90)
            repaired_body = story_content_pipeline._clean(repair.get("body"), 300)
            repaired_ok = bool(
                repair.get("accepted")
                and repaired_headline
                and repaired_body
                and story_japanese_rewriter.japanese_ratio(f"{repaired_headline} {repaired_body}") >= 0.45
                and story_content_pipeline._claim_ok(repaired_headline, repaired_body, evidence)
            )
            if repaired_ok:
                by_role[role] = {
                    "role": role,
                    "headline": repaired_headline,
                    "body": repaired_body,
                    "_copy_source": "ja_rewriter",
                    "_rewrite_attempts": int(repair.get("attempts") or 0),
                }
                repair_notes.append(f"{role}:repaired:{int(repair.get('attempts') or 0)}")
            else:
                failed_roles.append(role)
                detail = str(repair.get("warning") or "validation_failed")
                repair_notes.append(f"{role}:failed:{detail[:120]}")

        notes = "; ".join(repair_notes)
        if failed_roles:
            notes = (notes + "; " if notes else "") + "unrepaired_roles=" + ",".join(failed_roles)
        combined_warning = warning
        if notes:
            combined_warning = f"{warning} / {notes}" if warning else notes
        return by_role, combined_warning

    story_content_pipeline._model_cards = model_cards_with_ja_repair
    story_content_pipeline._kiyosaki_ja_rewriter_patch = STORY_OUTPUT_GUARD_VERSION


def apply_generation_guard(story_content_pipeline) -> None:
    if getattr(story_content_pipeline, "_kiyosaki_story_output_guard", None) == STORY_OUTPUT_GUARD_VERSION:
        return

    # This patch runs before generate_story_package executes. It makes the external
    # model the Japanese rewrite authority when batch output is missing, malformed,
    # English-heavy, or rejected by evidence/number validation.
    _patch_model_cards(story_content_pipeline)
    original = story_content_pipeline.generate_story_package

    def generate_story_package(*args, **kwargs):
        result = original(*args, **kwargs)
        if getattr(result, "package", None):
            result.package = sanitize_story_package(result.package)
        elif getattr(result, "error", None) and getattr(result, "model_warning", None):
            # Do not hide the actual model/rewrite failure behind only the final language gate.
            if "Model detail:" not in str(result.error):
                result.error = f"{result.error}\nModel detail: {result.model_warning}"
        return result

    story_content_pipeline.generate_story_package = generate_story_package
    story_content_pipeline._kiyosaki_story_output_guard = STORY_OUTPUT_GUARD_VERSION
