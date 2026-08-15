from __future__ import annotations

import copy
import re
from typing import Any

import story_engine


STORY_PIPELINE_RUNTIME_VERSION = "story-pipeline-v5.0"
DISPLAY_BRAND_LABEL = "キヨサキ"


def _is_ja_safe(text: object) -> bool:
    value = str(text or "")
    return bool(value.strip()) and not re.search(r"[가-힣]", value) and "THE OBSERVER" not in value.upper()


def _clean_visible(text: object, limit: int = 180) -> str:
    value = " ".join(str(text or "").replace("THE OBSERVER", "").replace("The Observer", "").split())
    return value[:limit]


def _row_from_any(item: Any) -> dict | None:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "to_row"):
        try:
            row = item.to_row()
            return dict(row) if isinstance(row, dict) else None
        except Exception:
            return None
    return None


def _annotate_list(items: list[Any]) -> list[Any]:
    if not items:
        return items
    if all(isinstance(item, dict) for item in items):
        return story_engine.annotate_resources([dict(item) for item in items])
    # ResourceItem objects are left as objects; their patched to_row() will expose the
    # story scores once the collector converts them for Streamlit.
    return items


def apply_resource_patch(resource_collector) -> None:
    if getattr(resource_collector, "_kiyosaki_story_resource_version", None) == STORY_PIPELINE_RUNTIME_VERSION:
        return

    resource_cls = getattr(resource_collector, "ResourceItem", None)
    if resource_cls is not None and hasattr(resource_cls, "to_row") and not hasattr(resource_cls, "_story_original_to_row"):
        original_to_row = resource_cls.to_row
        resource_cls._story_original_to_row = original_to_row

        def to_row(self):
            row = original_to_row(self)
            return story_engine.annotate_resource(row)

        resource_cls.to_row = to_row

    original_collect = resource_collector.collect_resources

    def collect_resources(*args, **kwargs):
        result = original_collect(*args, **kwargs)
        if isinstance(result, list):
            return _annotate_list(result)
        if isinstance(result, tuple) and result:
            parts = list(result)
            if isinstance(parts[0], list):
                parts[0] = _annotate_list(parts[0])
            return tuple(parts)
        if isinstance(result, dict):
            copied = dict(result)
            for key in ["resources", "items", "rows"]:
                if isinstance(copied.get(key), list):
                    copied[key] = _annotate_list(copied[key])
                    break
            return copied
        return result

    resource_collector.collect_resources = collect_resources
    resource_collector._kiyosaki_story_resource_version = STORY_PIPELINE_RUNTIME_VERSION


def _ranked_resources(resources: list[dict]) -> list[dict]:
    rows = [row for row in (resources or []) if isinstance(row, dict)]
    return story_engine.annotate_resources(rows) if rows else list(resources or [])


def _hero_source(hero: dict) -> dict:
    row = hero.get("hero_resource") or {}
    if not row:
        return {}
    return {
        "source_id": row.get("source_id") or row.get("id") or "",
        "publisher": row.get("source") or row.get("publisher") or "",
        "short_title": row.get("title") or row.get("short_title") or "",
        "display_headline_ja": row.get("display_headline_ja") or "",
        "url": row.get("url") or "",
        "source_quality": row.get("source_quality") or {},
        "asset_relevance": row.get("asset_relevance") or {},
        "news_reaction": row.get("news_reaction") or {"available": False},
    }


def _source_fact_ja(hero: dict) -> str:
    row = hero.get("hero_resource") or {}
    title_ja = _clean_visible(row.get("display_headline_ja"), 72)
    if title_ja and title_ja not in {"BTC材料を価格で確認", "市場材料を確認"}:
        return title_ja
    entity = (hero.get("entities") or [""])[0]
    topic = hero.get("topic") or "市場"
    return f"{entity or topic}をめぐる動きを、見出しと市場データに分けて確認する。"


def _fallback_market_line(card: dict) -> str:
    for candidate in [
        card.get("key_message"),
        (card.get("insight") or {}).get("text"),
        card.get("subheadline"),
    ]:
        if _is_ja_safe(candidate):
            return _clean_visible(candidate, 150)
    return "価格・出来高・資金フローが同じ方向を向くかを確認する。"


def _copy_for_role(role: str, hero: dict, card: dict) -> dict:
    archetype = hero.get("archetype") or "market_map"
    headline = hero.get("headline_ja") or "いま市場で、一番先に見るべきこと。"
    why_now = hero.get("why_now_ja") or "材料と価格を分けて見る。"
    conflict = hero.get("conflict_ja") or "材料と価格反応にはズレがある。"
    implication = hero.get("implication_ja") or "次の価格反応を確認する。"
    source_fact = _source_fact_ja(hero)
    market_line = _fallback_market_line(card)

    role_copy: dict[str, tuple[str, str]] = {
        "hook": (headline, why_now),
        "surface": ("まず、見えている事実。", source_fact),
        "contradiction": ("ここに、ズレがある。", conflict),
        "evidence": ("事実を、3つに絞る。", "一次情報、資金、価格。この3つを同じ時間軸で確認する。"),
        "explanation": ("なぜ、このズレが生まれる？", why_now),
        "what_changes": ("何が変われば、見方も変わる？", implication),
        "watch": ("次に見るのは、ここ。", market_line),
        "identity": ("この話の主役は誰か。", source_fact),
        "what_it_does": ("実際に握っているもの。", "知名度ではなく、資金・インフラ・流動性のどこを握っているかを見る。"),
        "scale": ("規模を見ると、意味が変わる。", "数字は大きさだけでなく、過去との変化と市場全体に占める比率で読む。"),
        "why_now": ("なぜ、いま注目される？", why_now),
        "market_implication": ("市場への意味は、ここ。", implication),
        "origin": ("始まりは、今とは違った。", source_fact),
        "turning_point": ("流れを変えた転換点。", "市場参加者、規制、資金のどれが変化を加速させたかを見る。"),
        "now": ("そして、現在地。", why_now),
        "flow_source": ("資金は、どこから来た？", "ETF、機関、企業、個人。買い手を分けるとフローの質が見える。"),
        "flow_size": ("金額より、継続性。", "一日の流入額ではなく、数日から数週続くかを確認する。"),
        "where_it_goes": ("入った資金は、どこへ向かう？", "BTCだけに残るのか、ETHや他のリスク資産へ広がるのかを見る。"),
        "price_gap": ("資金と価格に、ズレがある。", conflict),
        "old_order": ("これまでの主導権。", "誰が流動性、顧客、規制アクセスを握っていたかを確認する。"),
        "challenger": ("そこに、新しい勢力が入る。", source_fact),
        "who_gains": ("得をするのは誰か。", "シェアだけでなく、資金調達と出来高まで動くかを見る。"),
        "old_rule": ("これまでのルール。", "旧ルールで制限されていた参加者と資金の動きを整理する。"),
        "new_rule": ("何が変わった？", source_fact),
        "who_is_affected": ("影響を受けるのは誰か。", "取引所、機関、企業、個人投資家への影響を分けて見る。"),
        "timeline": ("重要なのは、実施時期。", "発表日と施行日は別。市場がいつから行動を変えられるかを確認する。"),
        "market_state": ("いまの市場状態。", market_line),
        "key_levels": ("価格は、どこで判断が変わる？", market_line),
        "positioning": ("ポジションの偏りを見る。", "FundingとOIは方向予想ではなく、参加者の偏りを測るために使う。"),
        "catalyst": ("次の触媒は何か。", source_fact),
        "scenario": ("次の経路は、ひとつではない。", implication),
        "then": ("当時、何が起きていた？", source_fact),
        "what_happened": ("その後、市場はどう動いた？", "価格だけでなく、流動性と参加者の変化まで追う。"),
        "similarity": ("似ている点。", "市場心理、資金フロー、価格構造の重なりを見る。"),
        "difference": ("でも、同じではない。", conflict),
        "incident": ("まず、何が起きたのか。", source_fact),
        "exposure": ("どこまで露出している？", "被害対象、資金量、関連サービスを分けて確認する。"),
        "contagion": ("次に見るのは、連鎖。", "一社の問題が流動性や取引所、他資産へ広がるかを見る。"),
        "what_changed": ("入口が変わった。", source_fact),
        "constraint": ("ただし、条件がある。", conflict),
    }
    role_headline, role_body = role_copy.get(role, (headline, why_now))
    eyebrow = {
        "money_flow": "MONEY FLOW",
        "policy_change": "POLICY",
        "crisis_or_risk": "RISK",
        "power_shift": "POWER SHIFT",
        "historical_parallel": "HISTORY",
        "origin_to_now": "STORY",
        "hidden_giant": "HIDDEN GIANT",
        "opportunity_window": "OPPORTUNITY",
        "contradiction": "CONTRADICTION",
        "market_map": "MARKET MAP",
    }.get(archetype, "STORY")
    return {
        "eyebrow": eyebrow,
        "headline": _clean_visible(role_headline, 84),
        "subheadline": _clean_visible(role_body, 155),
        "key_message": _clean_visible(role_body, 155),
        "insight": {"visible": False, "label": "", "text": ""},
        "action": {"visible": False, "label": "", "text": ""},
        "risk": {"visible": False, "text": ""},
    }


def _scene_prompt(role: str, hero: dict, layout: str) -> str:
    motifs = ", ".join(hero.get("visual_motifs") or ["institutional financial environment"])
    archetype = hero.get("archetype") or "market_map"
    entity = ", ".join((hero.get("entities") or [])[:2]) or hero.get("topic") or "Bitcoin market"
    return (
        f"Premium Japanese financial editorial visual for story archetype {archetype}. "
        f"Story role: {role}. Main subject: {entity}. Visual motifs: {motifs}. "
        f"Composition shell: {layout}. Documentary, tactile, cinematic, realistic financial-world atmosphere. "
        "No generated Japanese text, no K monogram, no orange K symbol, no decorative logo, no floating coins, "
        "no influencer thumbnail style. Leave clean negative space for renderer-composited typography."
    )


def _storyify_card(card: dict, role: str, role_index: int, hero: dict, layout_seed: str) -> dict:
    next_card = copy.deepcopy(card)
    if next_card.get("card_type") == "brand_outro":
        next_card["eyebrow"] = DISPLAY_BRAND_LABEL
        next_card["subheadline"] = ""
        next_card["story_role"] = "brand_outro"
        next_card["story_archetype"] = hero.get("archetype") or "market_map"
        next_card.setdefault("visual_direction", {})["character_required"] = True
        next_card["visual_direction"]["character_style_lock"] = {
            "face": "smooth completely black featureless face, no eyes nose mouth",
            "wardrobe": "tailored black suit, black shirt, black tie, black leather gloves",
            "pose": "front-facing waist-up, hands clasped calmly at lower abdomen",
            "lighting": "subtle warm orange rim light tracing head and shoulders",
            "mood": "quiet premium anonymous financial analyst",
        }
        return next_card

    copy_patch = _copy_for_role(role, hero, next_card)
    next_card.update(copy_patch)
    next_card["story_role"] = role
    next_card["story_archetype"] = hero.get("archetype") or "market_map"
    next_card["story_id"] = hero.get("id") or "story_market_map"
    next_card["card_purpose"] = f"story:{role}"
    next_card["new_information"] = _clean_visible(copy_patch.get("key_message"), 160)
    summary = dict(next_card.get("semantic_summary") or {})
    summary["semantic_key"] = f"story:{next_card['story_archetype']}:{role}"
    summary["story_role"] = role
    next_card["semantic_summary"] = summary

    hero_source = _hero_source(hero)
    if hero_source.get("url") and role not in {"market_state", "key_levels", "positioning", "scenario", "watch"}:
        next_card["source"] = hero_source

    layout = story_engine.layout_for_story(next_card["story_archetype"], role_index, layout_seed)
    direction = dict(next_card.get("visual_direction") or {})
    direction.update(
        {
            "deck_family": f"story_{next_card['story_archetype']}",
            "format_variant": layout,
            "layout_variant": layout,
            "story_role": role,
            "story_archetype": next_card["story_archetype"],
            "character_required": False,
            "character_visibility": 0.0,
            "character_shot": "none",
            "character_pose": "none",
            "visual_focus": ", ".join(hero.get("visual_motifs") or ["story evidence"]),
            "format_instruction": f"story-driven {layout}; one visual idea, one editorial message",
            "brand_mark_policy": "text-only キヨサキ; no K monogram/icon",
            "story_scene_prompt": _scene_prompt(role, hero, layout),
        }
    )
    direction["image_prompts"] = {
        "4:5": direction["story_scene_prompt"] + " 4:5 vertical composition, 1080x1350.",
        "9:16": direction["story_scene_prompt"] + " 9:16 vertical composition, 1080x1920.",
    }
    next_card["visual_direction"] = direction
    return next_card


def storyify_package(package: dict, brief: dict, resources: list[dict]) -> dict:
    next_package = copy.deepcopy(package or {})
    context = brief.get("story_context") if isinstance(brief, dict) else None
    if not context:
        context = story_engine.story_context(_ranked_resources(resources))
    hero = dict((context or {}).get("hero_story") or {})
    if not hero:
        hero = story_engine.select_hero_story(_ranked_resources(resources))

    quality = next_package.setdefault("content_quality", {})
    existing_blueprint = quality.get("visual_blueprint") or {}
    blueprint_seed = str(existing_blueprint.get("id") or hero.get("id") or "story")
    quality["story_engine"] = {
        "runtime": STORY_PIPELINE_RUNTIME_VERSION,
        "hero_story": {key: value for key, value in hero.items() if key != "hero_resource"},
        "candidate_count": len((context or {}).get("candidates") or []),
        "policy": "source -> story score -> event cluster -> hero story -> archetype -> dynamic carousel",
    }
    quality["hero_story_title"] = hero.get("headline_ja") or ""
    quality["story_archetype"] = hero.get("archetype") or "market_map"
    quality["story_score"] = hero.get("story_score") or 0

    for set_label, cards in (next_package.get("cards") or {}).items():
        cards = list(cards or [])
        content_cards = [card for card in cards if card.get("card_type") != "brand_outro"]
        outro_cards = [card for card in cards if card.get("card_type") == "brand_outro"]
        roles = story_engine.story_arc(hero.get("archetype") or "market_map", len(content_cards))
        transformed = [
            _storyify_card(card, roles[index], index, hero, f"{blueprint_seed}:{set_label}:{hero.get('id')}")
            for index, card in enumerate(content_cards)
        ]
        if outro_cards:
            transformed.append(_storyify_card(outro_cards[-1], "brand_outro", len(transformed), hero, blueprint_seed))
        for index, card in enumerate(transformed, start=1):
            card["slide"] = index
            card["set"] = set_label
        next_package["cards"][set_label] = transformed

    note = str(next_package.get("note_markdown") or "")
    story_note = (
        "\n\n## Story Engine\n"
        f"- Hero Story: {hero.get('headline_ja', '')}\n"
        f"- Archetype: {hero.get('archetype', 'market_map')}\n"
        f"- Story Score: {hero.get('story_score', 0)}\n"
        f"- Why Now: {hero.get('why_now_ja', '')}\n"
        f"- Conflict: {hero.get('conflict_ja', '')}\n"
        f"- Market Implication: {hero.get('implication_ja', '')}\n"
    )
    if "## Story Engine" not in note:
        next_package["note_markdown"] = note + story_note
    return next_package


def apply_reasoning_patch(reasoning_engine) -> None:
    if getattr(reasoning_engine, "_kiyosaki_story_pipeline_version", None) == STORY_PIPELINE_RUNTIME_VERSION:
        return

    original_brief = reasoning_engine.generate_trader_brief
    original_package = reasoning_engine.generate_content_package

    def generate_trader_brief(*args, **kwargs):
        resources = list(args[0] if args else kwargs.get("resources") or [])
        ranked = _ranked_resources(resources)
        if args:
            args = (ranked, *args[1:])
        else:
            kwargs["resources"] = ranked
        brief, warning = original_brief(*args, **kwargs)
        brief = dict(brief or {})
        brief["story_context"] = story_engine.story_context(ranked)
        brief["editorial_resource_order"] = [row.get("id") or row.get("source_id") or row.get("url") for row in ranked]
        # Put the hero source first when the source_findings structure allows it. This
        # improves downstream evidence/copy selection without mutating URLs or facts.
        hero_resource = ((brief.get("story_context") or {}).get("hero_story") or {}).get("hero_resource") or {}
        hero_url = hero_resource.get("url")
        findings = list(brief.get("source_findings") or [])
        if hero_url and findings:
            findings.sort(key=lambda item: 0 if item.get("url") == hero_url else 1)
            brief["source_findings"] = findings
        return brief, warning

    def generate_content_package(*args, **kwargs):
        package = original_package(*args, **kwargs)
        brief = args[0] if args else kwargs.get("brief") or {}
        resources = args[1] if len(args) > 1 else kwargs.get("resources") or []
        return storyify_package(package, brief, _ranked_resources(list(resources or [])))

    reasoning_engine.generate_trader_brief = generate_trader_brief
    reasoning_engine.generate_content_package = generate_content_package
    reasoning_engine._kiyosaki_story_pipeline_version = STORY_PIPELINE_RUNTIME_VERSION
