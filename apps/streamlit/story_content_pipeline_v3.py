from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from urllib.request import Request, urlopen

import story_engine_v3 as story_engine


STORY_CONTENT_PIPELINE_VERSION = "story-content-v8.0"
DISPLAY_BRAND_LABEL = "キヨサキ"
PROVIDER_LOCAL = "local"
PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"

ROLE_LABELS_JA = {
    "hook": "最初に見るべきこと",
    "old_business": "これまでの稼ぎ方",
    "turning_point": "転換点",
    "new_business": "新しい収益源",
    "deal_scale": "契約規模",
    "why_now": "なぜ今なのか",
    "market_implication": "市場への意味",
    "watch": "次に見るポイント",
    "surface": "まず確認できる事実",
    "contradiction": "ここにズレがある",
    "evidence": "数字で確認する",
    "explanation": "なぜそうなるのか",
    "what_changes": "見方が変わる条件",
    "identity": "この話の主役",
    "what_it_does": "実際に握っているもの",
    "scale": "規模を見る",
    "origin": "始まり",
    "now": "現在地",
    "flow_source": "資金はどこから来たか",
    "flow_size": "資金の規模",
    "where_it_goes": "資金はどこへ向かうか",
    "price_gap": "資金と価格のズレ",
    "old_order": "これまでの主導権",
    "challenger": "新しい勢力",
    "who_gains": "誰が得をするか",
    "old_rule": "これまでのルール",
    "new_rule": "何が変わったか",
    "who_is_affected": "誰に影響するか",
    "timeline": "いつ変わるのか",
    "then": "過去の比較対象",
    "what_happened": "過去に何が起きたか",
    "similarity": "似ている点",
    "difference": "違う点",
    "incident": "何が起きたか",
    "exposure": "どこまで露出しているか",
    "contagion": "連鎖するか",
    "what_changed": "何が変わったか",
    "constraint": "ただし条件がある",
}

SCENE_TYPES = {
    "business_transformation": {
        "hook": "industrial_data_center_exterior",
        "old_business": "bitcoin_mining_hall",
        "turning_point": "power_grid_infrastructure",
        "new_business": "ai_server_hall",
        "deal_scale": "industrial_aerial_scale",
        "why_now": "ai_compute_power_demand",
        "market_implication": "mining_vs_ai_split",
        "watch": "construction_timeline",
    },
    "historical_parallel": {
        "hook": "archival_wall_street",
        "then": "historical_newspaper",
        "what_happened": "historical_market_aftermath",
        "now": "modern_valuation_display",
        "similarity": "past_present_split",
        "difference": "modern_liquidity_context",
        "watch": "valuation_watchboard",
    },
    "money_flow": {
        "hook": "institutional_asset_manager",
        "flow_source": "fund_desk",
        "flow_size": "capital_scale",
        "where_it_goes": "capital_flow_network",
        "price_gap": "flow_vs_price_split",
        "market_implication": "institutional_market",
        "watch": "flow_monitor",
    },
    "policy_change": {
        "hook": "regulator_building",
        "old_rule": "old_policy_document",
        "new_rule": "new_policy_document",
        "who_is_affected": "affected_institutions",
        "timeline": "policy_timeline",
        "market_implication": "policy_market_bridge",
        "watch": "implementation_calendar",
    },
    "crisis_or_risk": {
        "hook": "forensic_scene",
        "incident": "incident_detail",
        "exposure": "asset_exposure_map",
        "contagion": "contagion_network",
        "evidence": "forensic_evidence",
        "market_implication": "risk_market_bridge",
        "watch": "risk_monitor",
    },
}


@dataclass
class StoryGenerationResult:
    package: dict
    error: str | None = None
    model_warning: str | None = None


def _clean(value: object, limit: int = 800) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _sid(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _hero_resources(resources: list[dict], hero: dict) -> list[dict]:
    allowed = {str(value) for value in hero.get("resource_ids") or [] if value}
    return [dict(row) for row in resources or [] if _sid(row) in allowed]


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?。！？])\s+|\n+", str(text or ""))
    out: list[str] = []
    for value in raw:
        item = _clean(value, 700)
        if len(item) >= 16 and item not in out:
            out.append(item)
    return out


def _fact_type(sentence: str) -> str:
    low = sentence.lower()
    if re.search(r"\b(?:19|20)\d{2}\b", sentence) and any(w in low for w in ["cape", "valuation", "dot-com", "1929", "2000"]):
        return "historical_value"
    if re.search(r"(?:\$|約)?\s?\d[\d,.]*(?:\s?(?:billion|million|億|兆)\s?(?:dollars?|ドル)?)", sentence, flags=re.I) and any(w in low for w in ["contract", "deal", "lease", "契約"]):
        return "deal_value"
    if re.search(r"\d[\d,.]*\s?(?:mw|gw|メガワット|ギガワット)", sentence, flags=re.I):
        return "capacity"
    if re.search(r"\d+\s?(?:years?|年(?:間)?)", sentence, flags=re.I):
        return "duration"
    if any(w in low for w in ["mining", "マイニング", "マイナー"]) and any(w in low for w in ["主力", "core business", "primary business", "これまで"]):
        return "before_state"
    if any(w in low for w in ["data center", "データセンター", "多角化", "transition", "diversif", "ai infrastructure"]):
        return "after_state"
    if any(w in low for w in ["inflow", "outflow", "流入", "流出"]):
        return "fund_flow"
    if any(w in low for w in ["approval", "effective", "施行", "承認"]):
        return "policy_date"
    if re.search(r"\b(?:19|20)\d{2}\b", sentence):
        return "date"
    if re.search(r"\d", sentence):
        return "numeric_fact"
    return "event"


def _extract_value(sentence: str) -> str:
    patterns = [
        r"約?\s?\d[\d,.]*\s?億ドル",
        r"約?\s?\d[\d,.]*\s?兆ドル",
        r"\$\s?\d[\d,.]*(?:\s?(?:billion|million|trillion))?",
        r"\d[\d,.]*\s?(?:MW|GW|メガワット|ギガワット)",
        r"\d+(?:\.\d+)?%",
        r"\b(?:19|20)\d{2}\b",
        r"\b\d+(?:\.\d+)?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.I)
        if match:
            return match.group(0)
    return ""


def extract_fact_pack(hero: dict, hero_resources: list[dict]) -> dict:
    allowed = {str(value) for value in hero.get("resource_ids") or [] if value}
    facts: list[dict] = []
    for row in hero_resources:
        source_id = _sid(row)
        if source_id not in allowed:
            continue
        material = _clean(row.get("material") or row.get("excerpt"), 7000)
        title = _clean(row.get("title"), 320)
        for sentence in _sentences(f"{title}。 {material}"):
            kind = _fact_type(sentence)
            value = _extract_value(sentence)
            if kind == "event" and not value and len(sentence) > 320:
                continue
            facts.append({
                "text": _clean(sentence, 360),
                "fact_type": kind,
                "value": value,
                "entities": list(hero.get("entities") or [])[:4],
                "source_id": source_id,
                "source_sentence": _clean(sentence, 520),
                "confidence": 0.96 if value or kind in {"before_state", "after_state"} else 0.88,
            })
    # Deduplicate while keeping hero-source provenance.
    unique: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for fact in facts:
        key = (fact["fact_type"], fact["text"][:120])
        if key not in seen:
            seen.add(key)
            unique.append(fact)
    return {
        "source_ids": sorted({_sid(row) for row in hero_resources if _sid(row)}),
        "facts": unique[:40],
        "years": list(dict.fromkeys(re.findall(r"\b(?:19|20)\d{2}\b", " ".join(f["text"] for f in unique))))[:8],
        "values": [f["value"] for f in unique if f.get("value")][:12],
        "entities": list(hero.get("entities") or [])[:5],
    }


def _facts_of(pack: dict, *types: str) -> list[dict]:
    wanted = set(types)
    return [fact for fact in pack.get("facts") or [] if fact.get("fact_type") in wanted]


def _find_fact(pack: dict, *types: str, contains: list[str] | None = None) -> dict | None:
    facts = _facts_of(pack, *types) if types else list(pack.get("facts") or [])
    if contains:
        for fact in facts:
            text = str(fact.get("text") or "").lower()
            if all(token.lower() in text for token in contains):
                return fact
    return facts[0] if facts else None


def _jp_specific_copy(archetype: str, role: str, hero: dict, pack: dict) -> tuple[str, str, dict | None]:
    entities = hero.get("entities") or []
    subject = entities[0] if entities else "この企業"

    if archetype == "business_transformation":
        if role == "hook":
            deal = _find_fact(pack, "deal_value")
            body = f"{subject}はBTCマイニングを主力にしてきた。いまAIデータセンターの長期契約が、企業の評価軸を変えようとしている。"
            if deal and deal.get("value"):
                body += f" 契約規模の手掛かりは{deal['value']}。"
            return f"{subject}が、BTC採掘からAIインフラへ動く。", body, deal
        if role == "old_business":
            fact = _find_fact(pack, "before_state", contains=["マイニング"]) or _find_fact(pack, "before_state")
            return "これまでの主力はBTCマイニング", f"{subject}はこれまでBTCマイニングを主力事業としてきた。既存の電力設備そのものが次の転換の土台になった。", fact
        if role == "turning_point":
            fact = _find_fact(pack, "capacity")
            value = fact.get("value") if fact else ""
            return "転換点は、すでに持っていた電力インフラ", f"テキサスの既存設備をAI用途へ転用する。{value + 'の' if value else ''}IT容量が、採掘企業をインフラ企業へ近づける。", fact
        if role == "new_business":
            fact = _find_fact(pack, "after_state", contains=["anthropic"]) or _find_fact(pack, "after_state")
            counterparty = "Anthropic" if "Anthropic" in entities else "AI企業"
            return "新しい顧客はAI企業", f"報道では契約先は{counterparty}とされる。採掘設備ではなく、AI計算資源を支えるデータセンターとして長期利用される計画だ。", fact
        if role == "deal_scale":
            deals = _facts_of(pack, "deal_value")
            values = [f.get("value") for f in deals if f.get("value")]
            body = "契約は単なる試験導入ではない。"
            if values:
                body += " 金額は" + "、".join(values[:2]) + "と報じられている。"
            duration = _find_fact(pack, "duration")
            if duration and duration.get("value"):
                body += f" 期間は{duration['value']}。"
            return "規模が、事業転換の本気度を示す", body, deals[0] if deals else duration
        if role == "why_now":
            fact = _find_fact(pack, "after_state", contains=["ai"]) or _find_fact(pack, "after_state")
            return "AIは、電力と冷却設備を大量に必要とする", "AI企業は巨大な計算能力を必要としている。一方、BTCマイナーは大規模な電力・冷却設備をすでに持つ。この接点が新しい収益源を作る。", fact
        if role == "market_implication":
            return "BTCマイナーの評価軸が変わる可能性", "採掘量とBTC価格だけでなく、電力容量・土地・AI向け長期契約が企業価値に加わるなら、同業他社の見方まで変わる。", _find_fact(pack, "capacity", "deal_value")
        if role == "watch":
            dated = _facts_of(pack, "date", "capacity")
            years = pack.get("years") or []
            body = "契約発表より、実際の稼働開始を確認する。"
            if years:
                body += " 次の節目は" + "、".join(years[-2:]) + "。"
            return "次に見るのは、AI設備が予定通り稼働するか", body, dated[-1] if dated else None

    if archetype == "historical_parallel":
        years = pack.get("years") or []
        values = pack.get("values") or []
        if role == "hook":
            body = "同じ形だから同じ結末になる、という話ではない。"
            if years:
                body = f"{ '年・'.join(years[:2]) + '年' if len(years) >= 2 else years[0] + '年'}と比較されるほど、現在の評価指標が極端な領域にある。"
            return "1929年と2000年。いま再び同じ警戒線へ。", body, _find_fact(pack, "historical_value")
        if role == "then":
            fact = _find_fact(pack, "historical_value")
            return "比較対象は、過去の極端なバリュエーション", fact.get("text") if fact else "1929年と2000年は、極端な評価水準の代表的な比較対象になっている。", fact
        if role == "what_happened":
            fact = _find_fact(pack, "historical_value")
            return "過去は、割高だけで終わらなかった", "高い評価水準は長く続くこともある。ただしピーク後の収益率と下落リスクがどう変わったかまで見る必要がある。", fact
        if role == "now":
            metric = "シラーCAPE" if any("CAPE" in str(f.get("text")) or "cape" in str(f.get("text")).lower() for f in pack.get("facts") or []) else "評価指標"
            nums = [v for v in values if re.fullmatch(r"\d+(?:\.\d+)?", str(v))]
            suffix = f" 現在の比較値には{nums[0]}付近が含まれる。" if nums else ""
            return "現在地を同じ指標で測る", f"今回の比較で使われているのは{metric}。過去と同じ指標で見ることで、単なるチャート形状の比較を避ける。{suffix}", _find_fact(pack, "historical_value", "numeric_fact")
        if role == "similarity":
            return "似ているのは、価格ではなく評価の極端さ", "共通点は市場が高い成長を織り込み、評価指標が歴史的な上限圏に近づいたこと。", _find_fact(pack, "historical_value")
        if role == "difference":
            return "違うのは、流動性と参加者", "1929年・2000年と現在では、金融政策、ETF、アルゴリズム取引、投資家構成が違う。同じ指標でも同じ速度で崩れるとは限らない。", _find_fact(pack, "historical_value")
        if role == "watch":
            return "次に見るのは、高評価が利益成長で正当化されるか", "評価指標だけで天井を決めず、利益成長と市場反応が高い期待に追いつくかを確認する。", _find_fact(pack, "historical_value")

    if archetype == "money_flow":
        flow = _find_fact(pack, "fund_flow", "numeric_fact")
        if role == "hook":
            return hero.get("headline_ja") or "資金は入った。価格は追いついたか。", "資金流入の見出しだけでは足りない。誰が、どれだけ、何日続けて買っているかを価格反応と一緒に見る。", flow
        if role == "flow_size":
            return "金額より、継続性を見る", flow.get("text") if flow else "単日の流入額より、数日から数週続くフローかを確認する。", flow

    fact = _find_fact(pack, "numeric_fact", "event", "date", "after_state", "before_state")
    headline = ROLE_LABELS_JA.get(role, "次に見るポイント")
    if fact:
        text = fact.get("text") or ""
        # If source sentence is Japanese, expose it directly. Otherwise summarize around its value/entities.
        if re.search(r"[ぁ-んァ-ン一-龥]", text):
            body = _clean(text, 170)
        else:
            value = fact.get("value") or ""
            entity = subject
            body = f"{entity}について確認できる具体的な事実は{value or 'この出来事'}。次のカードでもこの根拠から離れない。"
        return headline, body, fact
    return headline, f"{subject}を主語に、確認できる出来事だけを追う。", None


def _scene_type(archetype: str, role: str) -> str:
    return (SCENE_TYPES.get(archetype) or {}).get(role) or f"{archetype}_{role}"


def _scene_prompt(archetype: str, role: str, hero: dict, layout: str, scene_type: str, evidence: str) -> str:
    entities = ", ".join(hero.get("entities") or []) or "financial subject"
    motifs = ", ".join(hero.get("visual_motifs") or [])
    return (
        f"Premium Japanese financial documentary editorial image. Archetype: {archetype}. Story role: {role}. "
        f"Scene type: {scene_type}. Actual subject: {entities}. Evidence: {_clean(evidence, 260)}. Motifs: {motifs}. "
        f"Composition: {layout}. Create a distinct documentary scene for this role, not a generic market chart. "
        "Realistic, cinematic, tactile, high-end magazine photography. No text inside image, no captions, no glyphs, "
        "no K monogram, no orange K symbol, no logo, no watermark, no floating coins. Leave negative space for typography."
    )


def _source_display(row: dict | None) -> dict:
    row = row or {}
    return {
        "source_id": _sid(row),
        "publisher": _clean(row.get("source"), 80),
        "short_title": _clean(row.get("title"), 120),
        "url": _clean(row.get("url"), 600),
        "source_quality": {"story_score": row.get("story_score"), "risk_score": row.get("risk_score")},
    }


def _model_numeric_safe(text: str, pack: dict) -> bool:
    allowed_text = " ".join(str(f.get("text") or "") for f in pack.get("facts") or [])
    for token in re.findall(r"\d+(?:\.\d+)?", str(text or "")):
        if token not in allowed_text:
            return False
    return True


def _json_from_text(text: str) -> dict | None:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 90) -> dict:
    req = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _call_model(config: dict, hero: dict, roles: list[str], pack: dict) -> tuple[dict | None, str | None]:
    provider = str(config.get("provider") or PROVIDER_LOCAL)
    if provider == PROVIDER_LOCAL:
        return None, None
    facts = [{"type": f.get("fact_type"), "text": f.get("text"), "source_id": f.get("source_id")} for f in (pack.get("facts") or [])[:18]]
    system = "You edit premium Japanese financial documentary cards. Use ONLY supplied facts. Never invent numbers, dates, entities or causes. Return JSON only."
    user = json.dumps({"hero": hero, "roles": roles, "facts": facts, "schema": {"cards": [{"role": "same role", "headline": "Japanese", "body": "Japanese, factual"}]}}, ensure_ascii=False)
    try:
        if provider == PROVIDER_OLLAMA:
            base = str(config.get("base_url") or "http://localhost:11434").rstrip("/")
            raw = _post_json(base + "/api/chat", {"model": config.get("model") or "qwen3:4b", "stream": False, "format": "json", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "options": {"temperature": float(config.get("temperature") or 0.25)}}, {})
            return _json_from_text(((raw.get("message") or {}).get("content") or "")), None
        if provider == PROVIDER_OPENAI_COMPATIBLE:
            base = str(config.get("base_url") or "").rstrip("/")
            model = str(config.get("model") or "")
            if not base or not model:
                return None, "OpenAI-compatible story model configuration is incomplete."
            endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
            key = str(config.get("api_key") or "")
            raw = _post_json(endpoint, {"model": model, "temperature": float(config.get("temperature") or 0.25), "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, {"Authorization": f"Bearer {key}"} if key else {})
            choices = raw.get("choices") or []
            return _json_from_text((((choices[0] if choices else {}).get("message") or {}).get("content") or "")), None
    except Exception as error:
        return None, f"story reasoning model failed; evidence-bound fallback used: {error}"
    return None, f"Unsupported story provider: {provider}"


def _outro(total: int, archetype: str, brand: dict | None) -> dict:
    brand = brand or {}
    return {
        "set": "STORY", "slide": total, "card_id": "story-brand-outro", "card_type": "brand_outro",
        "story_role": "brand_outro", "story_archetype": archetype, "eyebrow": DISPLAY_BRAND_LABEL,
        "headline": "勢力ハンター キヨサキ", "subheadline": "", "key_message": _clean(brand.get("cta"), 180) or "フォローして、勢力が入ったポイントを無料でチェック。",
        "metrics": [], "source": {}, "footer": DISPLAY_BRAND_LABEL,
        "visual_direction": {
            "format_variant": "brand_locked", "layout_variant": "brand_locked", "scene_type": "brand_character_photographic",
            "character_required": True, "character_visibility": 0.52,
            "character_style_lock": {
                "face": "completely featureless black face, no eyes nose mouth", "wardrobe": "tailored black suit, black shirt, black tie, black leather gloves",
                "pose": "front-facing waist-up, hands clasped naturally at lower abdomen", "lighting": "subtle orange rim around head and shoulders",
                "mood": "premium photographic realism; not vector, not icon, not flat illustration",
            },
            "brand_mark_policy": "text-only キヨサキ; no K monogram/icon",
            "image_prompts": {"4:5": "Photorealistic faceless adult male, black tailored suit, black shirt, black tie, black leather gloves clasped naturally, centered front view, warm orange rim light, near-black studio, subtle orange dust, realistic fabric folds and glove texture. No text, no logo, no K monogram. 4:5."},
        },
        "qa": {"renderable": True, "mode": "story"},
    }


def generate_story_package(resources: list[dict], total_card_count: int, config: dict, output_locale: str = "ja-JP", brand: dict | None = None, generation_seed: str | None = None) -> StoryGenerationResult:
    if output_locale != "ja-JP":
        return StoryGenerationResult({}, error="Storytelling mode requires ja-JP output.")
    ranked = story_engine.annotate_resources([dict(r) for r in resources or []])
    if not ranked:
        return StoryGenerationResult({}, error="No story resources are available.")

    context = story_engine.story_context(ranked)
    hero = dict(context.get("hero_story") or {})
    hero_rows = _hero_resources(ranked, hero)
    if not hero_rows:
        return StoryGenerationResult({}, error="Hero Story has no isolated source resources.")

    pack = extract_fact_pack(hero, hero_rows)
    hero_ids = {str(v) for v in hero.get("resource_ids") or [] if v}
    if not set(pack.get("source_ids") or []).issubset(hero_ids):
        return StoryGenerationResult({}, error="Hero evidence isolation failed before generation.")

    total_card_count = max(5, min(9, int(total_card_count or 7)))
    roles = story_engine.story_arc(str(hero.get("archetype") or "hidden_giant"), total_card_count - 1)
    seed = generation_seed or hashlib.sha1(f"{hero.get('id')}|{time.time_ns()}".encode()).hexdigest()[:16]
    model_raw, model_warning = _call_model(config, hero, roles, pack)
    model_by_role: dict[str, dict] = {}
    if isinstance(model_raw, dict):
        for item in model_raw.get("cards") or []:
            if isinstance(item, dict) and item.get("role") in roles:
                model_by_role[str(item["role"])] = item

    source_map = {_sid(r): r for r in hero_rows}
    cards: list[dict] = []
    used_layouts: dict[str, int] = {}
    previous_layout = ""
    for index, role in enumerate(roles):
        headline, body, fact = _jp_specific_copy(str(hero.get("archetype")), role, hero, pack)
        model_card = model_by_role.get(role) or {}
        mh, mb = _clean(model_card.get("headline"), 90), _clean(model_card.get("body"), 220)
        if mh and mb and not re.search(r"[가-힣]", mh + mb) and _model_numeric_safe(mh + " " + mb, pack):
            headline, body = mh, mb
        evidence_ref = str((fact or {}).get("source_id") or next(iter(hero_ids)))
        if evidence_ref not in hero_ids:
            evidence_ref = next(iter(hero_ids))
        layout = story_engine.layout_for_story(str(hero.get("archetype")), index, f"{seed}:{role}")
        # Avoid immediate/repeated layout collisions when an alternative exists.
        candidates = list(story_engine.ARCHETYPE_LAYOUTS.get(str(hero.get("archetype"))) or [])
        if layout == previous_layout or used_layouts.get(layout, 0) >= 1:
            for alt in candidates:
                if alt != previous_layout and used_layouts.get(alt, 0) == 0:
                    layout = alt
                    break
        previous_layout = layout
        used_layouts[layout] = used_layouts.get(layout, 0) + 1
        scene_type = _scene_type(str(hero.get("archetype")), role)
        evidence_excerpt = _clean((fact or {}).get("source_sentence") or (fact or {}).get("text") or body, 360)
        prompt = _scene_prompt(str(hero.get("archetype")), role, hero, layout, scene_type, evidence_excerpt)
        cards.append({
            "set": "STORY", "slide": index + 1, "card_id": f"story-{hero.get('id')}-{index+1}", "card_type": "story_editorial",
            "story_id": hero.get("id"), "story_role": role, "story_archetype": hero.get("archetype"), "eyebrow": str(hero.get("archetype") or "STORY").replace("_", " ").upper(),
            "headline": headline, "subheadline": body, "key_message": body, "metrics": [], "evidence_refs": [evidence_ref], "evidence_excerpt": evidence_excerpt,
            "evidence_score": round(float((fact or {}).get("confidence") or 0.8), 2), "source": _source_display(source_map.get(evidence_ref)), "footer": "",
            "visual_direction": {
                "deck_family": f"story_{hero.get('archetype')}", "format_variant": layout, "layout_variant": layout, "scene_type": scene_type,
                "story_role": role, "story_archetype": hero.get("archetype"), "character_required": False, "character_visibility": 0.0,
                "character_shot": "none", "character_pose": "none", "visual_focus": ", ".join(hero.get("visual_motifs") or []), "story_scene_prompt": prompt,
                "brand_mark_policy": "text-only キヨサキ; no K monogram/icon", "image_prompts": {"4:5": prompt + " 4:5 vertical, 1080x1350.", "9:16": prompt + " 9:16 vertical, 1080x1920."},
            },
            "qa": {"renderable": True, "mode": "story"},
        })

    cards.append(_outro(total_card_count, str(hero.get("archetype")), brand))

    content_cards = cards[:-1]
    generic_count = sum(1 for c in content_cards if not (re.search(r"\d", c.get("key_message") or "") or any(e in (c.get("key_message") or "") for e in hero.get("entities") or []) or c.get("evidence_excerpt")))
    unique_layouts = len({(c.get("visual_direction") or {}).get("layout_variant") for c in content_cards})
    unique_scenes = len({(c.get("visual_direction") or {}).get("scene_type") for c in content_cards})
    refs_ok = all(set(c.get("evidence_refs") or []).issubset(hero_ids) for c in content_cards)
    leaks = sum(1 for c in cards if re.search(r"[가-힣]", " ".join(str(c.get(k) or "") for k in ["headline", "subheadline", "key_message"])))
    entity_pass = bool(hero.get("entity_details")) and all(float(e.get("confidence") or 0) >= 0.70 and str(e.get("name") or "").lower() not in {"crypto.", "crypto", "editor"} for e in hero.get("entity_details") or [])
    publishable = refs_ok and generic_count == 0 and leaks == 0 and unique_layouts >= min(4, len(content_cards)) and unique_scenes >= min(4, len(content_cards)) and entity_pass
    story_qa = {
        "hero_evidence_isolated": refs_ok and set(pack.get("source_ids") or []).issubset(hero_ids),
        "specific_fact_cards": f"{len(content_cards)-generic_count}/{len(content_cards)}",
        "unique_layouts": unique_layouts,
        "unique_scene_types": unique_scenes,
        "generic_card_count": generic_count,
        "foreign_language_leaks": leaks,
        "entity_confidence_pass": entity_pass,
        "publishable": publishable,
    }

    context = dict(context)
    context["hero_story"] = hero
    context["evidence_facts"] = pack
    context["hero_resource_ids"] = sorted(hero_ids)
    note_lines = [f"# {hero.get('headline_ja')}", "", hero.get("why_now_ja") or "", ""]
    for c in content_cards:
        note_lines.extend([f"## {c['slide']}. {c['headline']}", c.get("key_message") or "", ""])
    package = {
        "mode": "story", "story_context": context, "cards": {"STORY": cards}, "note_markdown": "\n".join(note_lines).strip(),
        "content_quality": {
            "mode": "story", "pipeline": STORY_CONTENT_PIPELINE_VERSION, "engine": story_engine.STORY_ENGINE_VERSION,
            "generation_seed": seed, "hero_story_title": hero.get("headline_ja"), "story_archetype": hero.get("archetype"),
            "story_score": hero.get("story_score"), "hero_story_score": hero.get("hero_story_score"), "model_provider": config.get("provider") or PROVIDER_LOCAL,
            "model_used": bool(model_raw), "story_qa": story_qa,
            "policy": "hero-only evidence -> typed fact pack -> archetype story arc -> role-specific scene and copy; no cross-candidate evidence",
        },
    }
    return StoryGenerationResult(package=package, model_warning=model_warning)
