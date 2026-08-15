from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

import story_engine


STORY_CONTENT_PIPELINE_VERSION = "story-content-v6.0"
DISPLAY_BRAND_LABEL = "キヨサキ"
PROVIDER_LOCAL = "local"
PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"

ARCHETYPE_EYEBROWS = {
    "contradiction": "CONTRADICTION",
    "hidden_giant": "HIDDEN GIANT",
    "origin_to_now": "ORIGIN → NOW",
    "money_flow": "MONEY FLOW",
    "power_shift": "POWER SHIFT",
    "policy_change": "POLICY",
    "market_map": "MARKET MAP",
    "historical_parallel": "HISTORY",
    "crisis_or_risk": "RISK",
    "opportunity_window": "OPPORTUNITY",
}

ROLE_LABELS_JA = {
    "hook": "最初に見るべきこと",
    "surface": "まず見えている事実",
    "contradiction": "ここにズレがある",
    "evidence": "根拠を絞る",
    "explanation": "なぜそうなるのか",
    "what_changes": "見方が変わる条件",
    "watch": "次に見るポイント",
    "identity": "この話の主役",
    "what_it_does": "実際に握っているもの",
    "scale": "規模を見る",
    "why_now": "なぜ今なのか",
    "market_implication": "市場への意味",
    "origin": "始まり",
    "turning_point": "転換点",
    "now": "現在地",
    "flow_source": "資金はどこから来たか",
    "flow_size": "金額より継続性",
    "where_it_goes": "資金はどこへ向かうか",
    "price_gap": "資金と価格のズレ",
    "old_order": "これまでの主導権",
    "challenger": "新しい勢力",
    "who_gains": "誰が得をするか",
    "old_rule": "これまでのルール",
    "new_rule": "何が変わったか",
    "who_is_affected": "誰に影響するか",
    "timeline": "重要なのは実施時期",
    "market_state": "今の市場状態",
    "key_levels": "判断が変わる境界",
    "positioning": "参加者の偏り",
    "catalyst": "次の触媒",
    "scenario": "次の経路",
    "then": "当時の状況",
    "what_happened": "その後どう動いたか",
    "similarity": "似ている点",
    "difference": "違う点",
    "incident": "何が起きたか",
    "exposure": "どこまで露出しているか",
    "contagion": "連鎖するか",
    "what_changed": "入口が変わった",
    "constraint": "ただし条件がある",
}


@dataclass
class StoryGenerationResult:
    package: dict
    error: str | None = None
    model_warning: str | None = None


def _clean(value: object, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _is_japanese_visible(value: object) -> bool:
    text = str(value or "")
    if not text.strip() or re.search(r"[가-힣]", text):
        return False
    return "THE OBSERVER" not in text.upper()


def _source_id(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _source_payload(row: dict) -> dict:
    return {
        "id": _source_id(row),
        "publisher": _clean(row.get("source") or row.get("publisher"), 80),
        "title": _clean(row.get("title") or row.get("short_title"), 220),
        "url": _clean(row.get("url"), 600),
        "tags": _clean(row.get("tags"), 180),
        "story_score": row.get("story_score"),
        "story_archetype_hint": row.get("story_archetype_hint"),
        "material": _clean(row.get("material") or row.get("excerpt"), 1800),
    }


def _candidate_resources(resources: list[dict], hero: dict, limit: int = 7) -> list[dict]:
    annotated = story_engine.annotate_resources([dict(row) for row in resources or []])
    wanted = {str(item) for item in (hero.get("resource_ids") or []) if item}
    selected = [row for row in annotated if _source_id(row) in wanted]
    for row in annotated:
        if row not in selected:
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected[:limit]


def _json_from_text(text: str) -> dict | None:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(value[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 90) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _call_story_model(config: dict, system_prompt: str, user_prompt: str) -> tuple[dict | None, str | None]:
    provider = str(config.get("provider") or PROVIDER_LOCAL)
    if provider == PROVIDER_LOCAL:
        return None, None

    try:
        if provider == PROVIDER_OLLAMA:
            base = str(config.get("base_url") or "http://localhost:11434").rstrip("/")
            model = str(config.get("model") or "qwen3:4b")
            raw = _post_json(
                base + "/api/chat",
                {
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "options": {"temperature": float(config.get("temperature") or 0.35)},
                },
                {},
            )
            text = ((raw.get("message") or {}).get("content") or "")
            return _json_from_text(text), None

        if provider == PROVIDER_OPENAI_COMPATIBLE:
            base = str(config.get("base_url") or "").rstrip("/")
            model = str(config.get("model") or "")
            api_key = str(config.get("api_key") or "")
            if not base or not model:
                return None, "OpenAI-compatible story model configuration is incomplete."
            endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
            raw = _post_json(
                endpoint,
                {
                    "model": model,
                    "temperature": float(config.get("temperature") or 0.35),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                {"Authorization": f"Bearer {api_key}"} if api_key else {},
            )
            choices = raw.get("choices") or []
            text = (((choices[0] if choices else {}).get("message") or {}).get("content") or "")
            return _json_from_text(text), None
    except Exception as error:
        return None, f"story reasoning model failed; deterministic fallback used: {error}"

    return None, f"Unsupported story provider: {provider}"


def _fallback_body(role: str, hero: dict) -> str:
    why_now = _clean(hero.get("why_now_ja"), 180)
    conflict = _clean(hero.get("conflict_ja"), 180)
    implication = _clean(hero.get("implication_ja"), 180)
    mapping = {
        "hook": why_now,
        "surface": "見出しだけで結論を出さず、誰が動き、何が変わったかを先に確認する。",
        "contradiction": conflict,
        "evidence": "一次情報、数字、価格反応を同じ時間軸に置く。揃わない部分があれば、そこを残す。",
        "explanation": why_now,
        "what_changes": implication,
        "watch": implication,
        "identity": "知名度ではなく、この主体が資金・制度・インフラのどこを握っているかを見る。",
        "what_it_does": "事業の説明より、市場のどのボトルネックを押さえているかが重要になる。",
        "scale": "単日の数字ではなく、過去比と市場全体に占める比率で規模を読む。",
        "why_now": why_now,
        "market_implication": implication,
        "origin": "最初の状態と現在地を分けると、途中で何が変わったかが見える。",
        "turning_point": "資金、規制、利用者のどれが転換点を作ったかを確認する。",
        "now": why_now,
        "flow_source": "ETF、機関、企業、個人を分け、買い手の質を確認する。",
        "flow_size": "一日の金額より、数日から数週続くフローかどうかを見る。",
        "where_it_goes": "入った資金が同じ資産に残るのか、周辺市場へ広がるのかを追う。",
        "price_gap": conflict,
        "old_order": "これまで誰が流動性、顧客、規制アクセスを握っていたかを整理する。",
        "challenger": "新しい参加者が入ると、価格より先にシェアと資金経路が変わることがある。",
        "who_gains": implication,
        "old_rule": "旧ルールで動けなかった参加者と資金を先に整理する。",
        "new_rule": "発表の見出しではなく、実際に許可・禁止・変更された範囲を確認する。",
        "who_is_affected": "取引所、機関、企業、個人投資家を分けて影響を見る。",
        "timeline": "発表日と施行日は別。市場参加者が実際に行動を変えられる日を見る。",
        "market_state": "価格だけでなく、出来高と資金フローが同じ方向を向くかを確認する。",
        "key_levels": "予想ではなく、見方が変わる境界だけを先に決める。",
        "positioning": "FundingやOIは方向予想ではなく、参加者の偏りを測るために使う。",
        "catalyst": "次のニュースより、次に確認できる事実が何かを決めておく。",
        "scenario": implication,
        "then": "過去の形だけでなく、その時の流動性と参加者を一緒に見る。",
        "what_happened": "価格の結果だけでなく、途中で資金と参加者がどう変わったかを追う。",
        "similarity": "心理、資金フロー、価格構造の重なる部分だけを比較する。",
        "difference": conflict,
        "incident": "最初の見出しと確認된 사실을 분리한다.".replace("확인된 사실을 분리한다.", "確認できた事実を分ける。"),
        "exposure": "被害対象、資金量、関連サービスを分け、直接露出と間接露出を混ぜない。",
        "contagion": "一社の問題が流動性、取引所、他資産へ広がるかを見る。",
        "what_changed": why_now,
        "constraint": conflict,
    }
    return _clean(mapping.get(role) or why_now or implication or "次に確認できる事実を待つ。", 180)


def _fallback_headline(role: str, hero: dict) -> str:
    if role == "hook":
        return _clean(hero.get("headline_ja"), 84) or "いま、何が変わっている？"
    return _clean(ROLE_LABELS_JA.get(role) or "次に見るポイント", 84)


def _model_prompts(hero: dict, roles: list[str], resources: list[dict]) -> tuple[str, str]:
    allowed_sources = [_source_payload(row) for row in resources]
    allowed_ids = [row["id"] for row in allowed_sources if row.get("id")]
    schema = {
        "hero": {
            "headline_ja": "Japanese hook, <= 34 Japanese characters where possible",
            "why_now_ja": "1 concise Japanese sentence",
            "conflict_ja": "1 concise Japanese sentence",
            "implication_ja": "1 concise Japanese sentence",
            "visual_motifs": ["visual noun phrase"],
        },
        "cards": [
            {
                "role": "must equal one of the supplied roles in the same order",
                "headline": "Japanese, concise",
                "body": "Japanese, 1-2 concise sentences",
                "evidence_refs": ["exact source id from allowed_sources"],
                "visual_concept": "English or Japanese production direction, no typography",
            }
        ],
    }
    system_prompt = (
        "You are the editorial director of a premium Japanese financial documentary carousel. "
        "This is NOT a trader briefing. Do not force support/resistance, funding, RSI, entry, wait, or invalidation into the story unless the supplied story role explicitly requires market structure. "
        "Build a narrative from the supplied evidence: hook -> change/conflict -> evidence -> implication -> watch. "
        "Use only facts supported by allowed_sources. Never invent numbers, quotes, dates, reactions, or causality. "
        "If evidence does not support a detail, omit it. Write natural native Japanese. "
        "Do not expose THE OBSERVER, internal debug terms, Korean text, K monograms, or decorative logos. "
        "Return JSON only."
    )
    user_prompt = json.dumps(
        {
            "story": {
                "id": hero.get("id"),
                "topic": hero.get("topic"),
                "archetype": hero.get("archetype"),
                "headline_seed": hero.get("headline_seed"),
                "baseline_headline_ja": hero.get("headline_ja"),
                "baseline_why_now_ja": hero.get("why_now_ja"),
                "baseline_conflict_ja": hero.get("conflict_ja"),
                "baseline_implication_ja": hero.get("implication_ja"),
                "entities": hero.get("entities") or [],
            },
            "roles": roles,
            "allowed_source_ids": allowed_ids,
            "allowed_sources": allowed_sources,
            "required_schema": schema,
        },
        ensure_ascii=False,
    )
    return system_prompt, user_prompt


def _validate_model_cards(raw: dict | None, roles: list[str], allowed_ids: set[str]) -> tuple[dict, list[dict]]:
    if not isinstance(raw, dict):
        return {}, []
    hero_patch = raw.get("hero") if isinstance(raw.get("hero"), dict) else {}
    raw_cards = raw.get("cards") if isinstance(raw.get("cards"), list) else []
    by_role: dict[str, dict] = {}
    for item in raw_cards:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if role not in roles or role in by_role:
            continue
        refs = [str(ref) for ref in (item.get("evidence_refs") or []) if str(ref) in allowed_ids]
        headline = _clean(item.get("headline"), 92)
        body = _clean(item.get("body"), 220)
        if not _is_japanese_visible(headline) or not _is_japanese_visible(body):
            continue
        by_role[role] = {
            "role": role,
            "headline": headline,
            "body": body,
            "evidence_refs": refs,
            "visual_concept": _clean(item.get("visual_concept"), 280),
        }
    return hero_patch, [by_role[role] for role in roles if role in by_role]


def _hero_source(hero: dict, resources_by_id: dict[str, dict]) -> dict:
    for resource_id in hero.get("resource_ids") or []:
        row = resources_by_id.get(str(resource_id))
        if row:
            return row
    raw = hero.get("hero_resource") or {}
    return dict(raw) if isinstance(raw, dict) else {}


def _source_display(row: dict) -> dict:
    if not row:
        return {}
    return {
        "source_id": _source_id(row),
        "publisher": _clean(row.get("source") or row.get("publisher"), 80),
        "short_title": _clean(row.get("title") or row.get("short_title"), 150),
        "display_headline_ja": _clean(row.get("display_headline_ja"), 80),
        "url": _clean(row.get("url"), 600),
        "source_quality": {
            "story_score": row.get("story_score"),
            "risk_score": row.get("risk_score"),
        },
    }


def _scene_prompt(archetype: str, role: str, hero: dict, layout: str, visual_concept: str = "") -> str:
    motifs = ", ".join(hero.get("visual_motifs") or ["institutional financial environment"])
    entities = ", ".join((hero.get("entities") or [])[:2]) or str(hero.get("topic") or "financial market")
    concept = visual_concept or f"documentary scene expressing {role}"
    return (
        f"Premium Japanese financial documentary editorial image. Archetype: {archetype}. "
        f"Story role: {role}. Subject: {entities}. Motifs: {motifs}. Concept: {concept}. "
        f"Composition: {layout}. Realistic, cinematic, tactile, high-end magazine photography. "
        "No text inside the image, no captions, no Japanese glyphs, no K monogram, no orange K symbol, "
        "no logo, no watermark, no floating coins, no influencer-thumbnail styling. "
        "Leave intentional negative space for renderer-composited typography."
    )


def _build_story_card(
    *,
    index: int,
    role: str,
    hero: dict,
    model_card: dict | None,
    resources_by_id: dict[str, dict],
    generation_seed: str,
) -> dict:
    archetype = str(hero.get("archetype") or "market_map")
    model_card = model_card or {}
    headline = _clean(model_card.get("headline"), 92) if _is_japanese_visible(model_card.get("headline")) else _fallback_headline(role, hero)
    body = _clean(model_card.get("body"), 220) if _is_japanese_visible(model_card.get("body")) else _fallback_body(role, hero)
    evidence_refs = [str(ref) for ref in model_card.get("evidence_refs") or [] if str(ref) in resources_by_id]
    if not evidence_refs:
        evidence_refs = [str(item) for item in (hero.get("resource_ids") or []) if str(item) in resources_by_id][:2]
    source_row = resources_by_id.get(evidence_refs[0]) if evidence_refs else _hero_source(hero, resources_by_id)
    layout = story_engine.layout_for_story(archetype, index, f"{generation_seed}:{role}:{hero.get('id')}")
    scene_prompt = _scene_prompt(archetype, role, hero, layout, _clean(model_card.get("visual_concept"), 280))
    return {
        "set": "스토리",
        "slide": index + 1,
        "card_id": f"story-{hero.get('id') or 'hero'}-{index + 1}",
        "card_type": "story_editorial",
        "story_id": hero.get("id") or "story_market_map",
        "story_role": role,
        "story_archetype": archetype,
        "eyebrow": ARCHETYPE_EYEBROWS.get(archetype, "STORY"),
        "headline": headline,
        "subheadline": body,
        "key_message": body,
        "metrics": [],
        "insight": {"visible": False, "label": "", "text": ""},
        "action": {"visible": False, "label": "", "text": ""},
        "risk": {"visible": False, "text": ""},
        "evidence_refs": evidence_refs,
        "evidence_score": round(float(hero.get("story_score") or 0.0) / 100.0, 3),
        "card_purpose": f"story:{role}",
        "new_information": body,
        "semantic_summary": {
            "semantic_key": f"story:{archetype}:{role}",
            "story_role": role,
            "topic": hero.get("topic"),
        },
        "source": _source_display(source_row or {}),
        "footer": "",
        "visual_direction": {
            "deck_family": f"story_{archetype}",
            "format_variant": layout,
            "layout_variant": layout,
            "story_role": role,
            "story_archetype": archetype,
            "character_required": False,
            "character_visibility": 0.0,
            "character_shot": "none",
            "character_pose": "none",
            "visual_focus": ", ".join(hero.get("visual_motifs") or []),
            "story_scene_prompt": scene_prompt,
            "brand_mark_policy": "text-only キヨサキ; no K monogram/icon",
            "image_prompts": {
                "4:5": scene_prompt + " 4:5 vertical composition, 1080x1350.",
                "9:16": scene_prompt + " 9:16 vertical composition, 1080x1920.",
            },
        },
        "qa": {"renderable": True, "mode": "story"},
    }


def _build_outro(total_cards: int, archetype: str, brand: dict | None = None) -> dict:
    brand = dict(brand or {})
    cta = _clean(brand.get("cta"), 180) or "フォローして、勢力が入ったポイントを無料でチェック。"
    account = _clean(brand.get("account"), 80)
    footer = DISPLAY_BRAND_LABEL + (f" · {account}" if account else "")
    return {
        "set": "스토리",
        "slide": total_cards,
        "card_id": "story-brand-outro",
        "card_type": "brand_outro",
        "story_role": "brand_outro",
        "story_archetype": archetype,
        "eyebrow": DISPLAY_BRAND_LABEL,
        "headline": "勢力ハンター キヨサキ",
        "subheadline": "",
        "key_message": cta,
        "metrics": [],
        "source": {},
        "footer": footer,
        "visual_direction": {
            "format_variant": "brand_locked",
            "layout_variant": "brand_locked",
            "character_required": True,
            "character_visibility": 0.52,
            "character_style_lock": {
                "face": "smooth completely black featureless face, no eyes nose mouth",
                "wardrobe": "tailored black suit, black shirt, black tie, black leather gloves",
                "pose": "front-facing waist-up, hands clasped calmly at lower abdomen",
                "lighting": "subtle warm orange rim light tracing head and shoulders",
                "mood": "quiet premium anonymous financial analyst",
            },
            "brand_mark_policy": "text-only キヨサキ; no K monogram/icon",
            "image_prompts": {
                "4:5": "Centered front-facing faceless adult male, smooth completely black featureless face, tailored black suit, black shirt, black tie, black leather gloves clasped calmly at lower abdomen, waist-up, warm orange rim light on head and shoulders, sparse warm dust, near-black premium studio. No text, no logo, no K monogram. 4:5.",
                "9:16": "Centered front-facing faceless adult male, smooth completely black featureless face, tailored black suit, black shirt, black tie, black leather gloves clasped calmly at lower abdomen, waist-up, warm orange rim light on head and shoulders, sparse warm dust, near-black premium studio. No text, no logo, no K monogram. 9:16.",
            },
        },
        "qa": {"renderable": True, "mode": "story"},
    }


def _note_markdown(context: dict, cards: list[dict], resources_by_id: dict[str, dict]) -> str:
    hero = context.get("hero_story") or {}
    lines = [
        f"# {hero.get('headline_ja') or 'キヨサキ ストーリー'}",
        "",
        hero.get("why_now_ja") or "",
        "",
        f"- Archetype: {hero.get('archetype') or 'market_map'}",
        f"- Story Score: {hero.get('story_score') or 0}",
        f"- Conflict: {hero.get('conflict_ja') or ''}",
        f"- Implication: {hero.get('implication_ja') or ''}",
        "",
        "## Story Arc",
    ]
    for card in cards:
        if card.get("card_type") == "brand_outro":
            continue
        lines.extend([
            f"### {card.get('slide')}. {card.get('headline')}",
            card.get("key_message") or "",
            "",
        ])
    lines.append("## Sources")
    used: set[str] = set()
    for card in cards:
        for ref in card.get("evidence_refs") or []:
            if ref in used:
                continue
            used.add(ref)
            row = resources_by_id.get(ref) or {}
            title = _clean(row.get("title"), 180)
            publisher = _clean(row.get("source"), 80)
            url = _clean(row.get("url"), 600)
            lines.append(f"- {publisher} · {title} · {url}")
    return "\n".join(line for line in lines if line is not None).strip()


def generate_story_package(
    resources: list[dict],
    total_card_count: int,
    config: dict,
    output_locale: str = "ja-JP",
    brand: dict | None = None,
    generation_seed: str | None = None,
) -> StoryGenerationResult:
    if output_locale != "ja-JP":
        return StoryGenerationResult(package={}, error="Storytelling mode currently requires ja-JP output.")
    ranked = story_engine.annotate_resources([dict(row) for row in resources or []])
    if not ranked:
        return StoryGenerationResult(package={}, error="No story resources are available.")

    context = story_engine.story_context(ranked)
    hero = dict(context.get("hero_story") or {})
    total_card_count = max(5, min(8, int(total_card_count or 6)))
    content_count = total_card_count - 1
    roles = story_engine.story_arc(str(hero.get("archetype") or "market_map"), content_count)
    seed = generation_seed or hashlib.sha1(
        f"{hero.get('id')}|{time.time_ns()}".encode("utf-8", errors="ignore")
    ).hexdigest()[:16]

    selected_resources = _candidate_resources(ranked, hero, limit=7)
    resources_by_id = {_source_id(row): row for row in ranked if _source_id(row)}
    system_prompt, user_prompt = _model_prompts(hero, roles, selected_resources)
    model_raw, model_warning = _call_story_model(config, system_prompt, user_prompt)
    allowed_ids = {_source_id(row) for row in selected_resources if _source_id(row)}
    hero_patch, model_cards = _validate_model_cards(model_raw, roles, allowed_ids)

    # The model may improve editorial wording, but it may not change the selected
    # archetype, source IDs, score, or other evidence-owned facts.
    for key in ["headline_ja", "why_now_ja", "conflict_ja", "implication_ja"]:
        candidate = _clean(hero_patch.get(key), 220)
        if _is_japanese_visible(candidate):
            hero[key] = candidate
    motifs = hero_patch.get("visual_motifs") if isinstance(hero_patch.get("visual_motifs"), list) else []
    if motifs:
        hero["visual_motifs"] = [_clean(item, 120) for item in motifs if _clean(item, 120)][:4]

    model_by_role = {item["role"]: item for item in model_cards}
    cards = [
        _build_story_card(
            index=index,
            role=role,
            hero=hero,
            model_card=model_by_role.get(role),
            resources_by_id=resources_by_id,
            generation_seed=seed,
        )
        for index, role in enumerate(roles)
    ]
    cards.append(_build_outro(total_card_count, str(hero.get("archetype") or "market_map"), brand))

    context = dict(context)
    context["hero_story"] = hero
    package = {
        "mode": "story",
        "story_context": context,
        "cards": {"스토리": cards},
        "note_markdown": _note_markdown(context, cards, resources_by_id),
        "content_quality": {
            "mode": "story",
            "pipeline": STORY_CONTENT_PIPELINE_VERSION,
            "generation_seed": seed,
            "hero_story_title": hero.get("headline_ja") or "",
            "story_archetype": hero.get("archetype") or "market_map",
            "story_score": hero.get("story_score") or 0,
            "model_provider": config.get("provider") or PROVIDER_LOCAL,
            "model_used": bool(model_raw),
            "policy": "story sources -> story score -> event cluster -> hero story -> archetype arc -> story cards; no trader brief intermediate",
        },
    }
    return StoryGenerationResult(package=package, error=None, model_warning=model_warning)
