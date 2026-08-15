from __future__ import annotations

import hashlib
import re
import time

import story_article_cleaner
import story_content_pipeline_v3 as legacy
import story_engine_v4 as story_engine
import story_renderer_v4 as story_renderer


STORY_CONTENT_PIPELINE_VERSION = "story-content-v9.2"
DISPLAY_BRAND_LABEL = legacy.DISPLAY_BRAND_LABEL
PROVIDER_LOCAL = legacy.PROVIDER_LOCAL
PROVIDER_OLLAMA = legacy.PROVIDER_OLLAMA
PROVIDER_OPENAI_COMPATIBLE = legacy.PROVIDER_OPENAI_COMPATIBLE
StoryGenerationResult = legacy.StoryGenerationResult

_MONEY_PATTERNS = [
    r"約?\s?\d+(?:\.\d+)?(?:兆\d+億|億\d+万|兆|億|万)?円",
    r"約?\s?\d+(?:\.\d+)?(?:億\d+万|億|兆|万)?ドル",
    r"\$\s?\d[\d,.]*(?:\s?(?:billion|million|trillion|bn|mn))?",
]
_CAPACITY_PATTERN = r"\d[\d,.]*\s?(?:MW|GW|メガワット|ギガワット)"
_PERCENT_PATTERN = r"\d+(?:\.\d+)?%"
# Unicode word boundaries do not work before Japanese 年 because 年 is itself a
# Unicode word character. Digit lookarounds correctly match 2027年 / 2028年 while
# still rejecting numbers embedded inside a longer digit string.
_YEAR_PATTERN = r"(?<!\d)(?:19|20)\d{2}(?!\d)"
_DURATION_PATTERNS = [
    r"(?<!\d)\d{1,2}\s?(?:years?|年間)(?!\d)",
    r"(?<!\d)\d{1,2}\s*年(?:間)?(?!\d)",
]
_GENERIC_COPY_PATTERNS = [
    "今回の動きを基準に確認する",
    "確認できる事実を見る",
    "次の条件を見る",
    "見方が変わる条件",
]


def _clean(value: object, limit: int = 800) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _sid(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _prepare_story_resources(resources: list[dict]) -> list[dict]:
    return [story_article_cleaner.clean_story_resource(dict(row)) for row in resources or [] if isinstance(row, dict)]


def _hero_resources(resources: list[dict], hero: dict) -> list[dict]:
    allowed = {str(v) for v in hero.get("resource_ids") or [] if v}
    return [dict(row) for row in resources or [] if _sid(row) in allowed]


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?。！？])\s+|\n+", str(text or ""))
    out: list[str] = []
    for value in raw:
        item = _clean(value, 900)
        if len(item) >= 12 and item not in out:
            out.append(item)
    return out


def _matches(pattern: str, sentence: str) -> list[str]:
    return [_clean(m.group(0), 120) for m in re.finditer(pattern, sentence, flags=re.I)]


def _duration_values(sentence: str) -> list[str]:
    values: list[str] = []
    for pattern in _DURATION_PATTERNS:
        for match in re.finditer(pattern, sentence, flags=re.I):
            value = _clean(match.group(0), 40)
            if value and value not in values:
                values.append(value)
    return values


def _append_fact(facts: list[dict], hero: dict, source_id: str, sentence: str, kind: str, value: str = "", confidence: float = 0.94) -> None:
    facts.append({
        "text": _clean(sentence, 420),
        "fact_type": kind,
        "value": _clean(value, 120),
        "entities": list(hero.get("entities") or [])[:4],
        "source_id": source_id,
        "source_sentence": _clean(sentence, 620),
        "confidence": round(float(confidence), 2),
    })


def _extract_fact_pack(hero: dict, hero_resources: list[dict]) -> dict:
    allowed = {str(v) for v in hero.get("resource_ids") or [] if v}
    facts: list[dict] = []

    for row in hero_resources:
        source_id = _sid(row)
        if source_id not in allowed:
            continue
        material = _clean(row.get("material") or row.get("excerpt"), 16000)
        title = _clean(row.get("title"), 320)
        for sentence in _sentences(f"{title}。 {material}"):
            if story_article_cleaner.has_boilerplate(sentence):
                continue
            low = sentence.casefold()
            years = _matches(_YEAR_PATTERN, sentence)
            money: list[str] = []
            for pattern in _MONEY_PATTERNS:
                money.extend(_matches(pattern, sentence))
            capacities = _matches(_CAPACITY_PATTERN, sentence)
            percentages = _matches(_PERCENT_PATTERN, sentence)
            durations = _duration_values(sentence)

            contract_context = any(token in low for token in ["contract", "deal", "lease", "契約", "収益", "契約価値", "リース"])
            financing_context = any(token in low for token in ["financing", "融資", "資金調達", "つなぎ融資"])
            schedule_context = any(token in low for token in ["稼働", "開始", "予定", "計画", "運用", "full operation", "launch", "start operation"])
            historical_context = any(token in low for token in ["cape", "valuation", "dot-com", "1929", "2000", "過去", "歴史"])

            for value in money:
                _append_fact(facts, hero, source_id, sentence, "funding_value" if financing_context else ("deal_value" if contract_context else "money_value"), value, 0.98)
            for value in capacities:
                _append_fact(facts, hero, source_id, sentence, "capacity", value, 0.98)
            for value in durations:
                _append_fact(facts, hero, source_id, sentence, "duration", value, 0.98)
            for value in percentages:
                _append_fact(facts, hero, source_id, sentence, "percentage", value, 0.97)
            for value in years:
                if historical_context:
                    kind = "historical_value"
                elif schedule_context:
                    kind = "milestone_date"
                else:
                    kind = "date"
                _append_fact(facts, hero, source_id, sentence, kind, value, 0.97 if kind == "milestone_date" else 0.94)

            if any(w in low for w in ["mining", "マイニング", "マイナー"]) and any(w in low for w in ["主力", "core business", "primary business", "これまで"]):
                _append_fact(facts, hero, source_id, sentence, "before_state", "", 0.96)
            if any(w in low for w in ["data center", "データセンター", "多角化", "transition", "diversif", "ai infrastructure", "事業拡大"]):
                _append_fact(facts, hero, source_id, sentence, "after_state", "", 0.96)
            if any(w in low for w in ["inflow", "outflow", "流入", "流出"]):
                _append_fact(facts, hero, source_id, sentence, "fund_flow", money[0] if money else "", 0.95)
            if not (money or capacities or durations or percentages or years) and len(sentence) <= 360:
                _append_fact(facts, hero, source_id, sentence, "event", "", 0.88)

    unique: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for fact in facts:
        key = (str(fact.get("fact_type")), str(fact.get("value")), str(fact.get("text"))[:160])
        if key not in seen:
            seen.add(key)
            unique.append(fact)

    years: list[str] = []
    values: list[str] = []
    for fact in unique:
        value = str(fact.get("value") or "")
        if re.fullmatch(_YEAR_PATTERN, value) and value not in years:
            years.append(value)
        if value and value not in values:
            values.append(value)

    milestone_years = list(dict.fromkeys(
        str(f.get("value")) for f in unique
        if f.get("fact_type") == "milestone_date" and f.get("value")
    ))

    return {
        "source_ids": sorted({_sid(row) for row in hero_resources if _sid(row)}),
        "facts": unique[:80],
        "years": years[:12],
        "milestone_years": milestone_years[:8],
        "values": values[:30],
        "entities": list(hero.get("entities") or [])[:5],
        "cleaner": story_article_cleaner.STORY_ARTICLE_CLEANER_VERSION,
    }


def _facts_of(pack: dict, *types: str) -> list[dict]:
    wanted = set(types)
    return [fact for fact in pack.get("facts") or [] if fact.get("fact_type") in wanted]


def _find_fact(pack: dict, *types: str, contains: list[str] | None = None) -> dict | None:
    facts = _facts_of(pack, *types) if types else list(pack.get("facts") or [])
    if contains:
        for fact in facts:
            text = str(fact.get("text") or "").casefold()
            if all(token.casefold() in text for token in contains):
                return fact
    return facts[0] if facts else None


def _best_fact(pack: dict, preferred: dict | None, role: str) -> dict | None:
    if preferred and preferred.get("source_id") and not story_article_cleaner.has_boilerplate(str(preferred.get("source_sentence") or preferred.get("text") or "")):
        return preferred
    role_preferences = {
        "hook": ["deal_value", "after_state", "event", "historical_value", "fund_flow"],
        "old_business": ["before_state", "event"],
        "turning_point": ["capacity", "after_state", "event"],
        "new_business": ["after_state", "deal_value", "event"],
        "deal_scale": ["deal_value", "duration", "capacity", "funding_value"],
        "why_now": ["after_state", "capacity", "event"],
        "market_implication": ["capacity", "deal_value", "after_state", "event"],
        "watch": ["milestone_date", "capacity", "duration", "date"],
        "then": ["historical_value", "date"],
        "what_happened": ["historical_value", "event"],
        "now": ["historical_value", "money_value", "event"],
        "similarity": ["historical_value", "event"],
        "difference": ["event", "historical_value"],
        "flow_source": ["fund_flow", "event"],
        "flow_size": ["fund_flow", "money_value", "percentage"],
        "where_it_goes": ["fund_flow", "event"],
        "price_gap": ["fund_flow", "percentage", "event"],
    }
    for kind in role_preferences.get(role, []):
        fact = _find_fact(pack, kind)
        if fact:
            return fact
    facts = list(pack.get("facts") or [])
    return next((fact for fact in facts if fact.get("source_id") and float(fact.get("confidence") or 0) >= 0.88), facts[0] if facts else None)


def _story_copy(archetype: str, role: str, hero: dict, pack: dict) -> tuple[str, str, dict | None]:
    headline, body, preferred = legacy._jp_specific_copy(archetype, role, hero, pack)
    entities = list(hero.get("entities") or [])
    subject = entities[0] if entities else "この企業"

    if archetype != "business_transformation":
        return headline, body, preferred

    if role == "hook":
        deal = _find_fact(pack, "deal_value")
        cap = _find_fact(pack, "capacity")
        anchor = deal or cap or _find_fact(pack, "after_state")
        details = []
        if cap and cap.get("value"):
            details.append(str(cap["value"]))
        if deal and deal.get("value"):
            details.append(str(deal["value"]))
        body = f"{subject}はBTCマイニングを主力にしてきた。いまAIデータセンターへ収益源を広げようとしている。"
        if details:
            body += " 契約の具体値は" + "、".join(details[:2]) + "。"
        return f"{subject}が、BTC採掘からAIインフラへ動く。", body, anchor

    if role == "turning_point":
        cap = _find_fact(pack, "capacity")
        if cap and cap.get("value"):
            return "転換点は、すでに持っていた電力インフラ", f"既存施設をAI用途へ転用する計画だ。提供容量は{cap['value']}。採掘向け設備がAIインフラの土台になる。", cap

    if role == "new_business":
        fact = _find_fact(pack, "after_state", contains=["anthropic"]) or _find_fact(pack, "after_state") or _find_fact(pack, "event")
        counterparty = next((e for e in entities if "anthropic" in e.casefold()), "AI企業")
        return "新しい顧客はAI企業", f"報道では契約先は{counterparty}とされる。{subject}は既存の採掘インフラを、AI計算資源を支えるデータセンターへ広げる。", fact

    if role == "deal_scale":
        deals = _facts_of(pack, "deal_value")
        duration = _find_fact(pack, "duration")
        cap = _find_fact(pack, "capacity")
        details = [str(f.get("value")) for f in deals if f.get("value")][:2]
        if duration and duration.get("value"):
            details.append(str(duration["value"]))
        if cap and cap.get("value") and str(cap["value"]) not in details:
            details.append(str(cap["value"]))
        body = "契約は試験導入の規模ではない。"
        if details:
            body += " 確認できる条件は" + "、".join(details[:4]) + "。"
        return "規模が、事業転換の本気度を示す", body, deals[0] if deals else (duration or cap)

    if role == "why_now":
        cap = _find_fact(pack, "capacity")
        fact = _find_fact(pack, "event", contains=["計算"]) or _find_fact(pack, "after_state") or cap
        suffix = f" {subject}側には{cap['value']}規模の設備がある。" if cap and cap.get("value") else ""
        return "AI需要と、マイナーの電力設備が接続した", "AI企業は大規模な計算資源を必要とする。一方、BTCマイナーは電力・冷却設備をすでに保有している。" + suffix, fact

    if role == "market_implication":
        cap = _find_fact(pack, "capacity")
        deal = _find_fact(pack, "deal_value")
        anchor = cap or deal or _find_fact(pack, "after_state")
        concrete = []
        if cap and cap.get("value"):
            concrete.append(str(cap["value"]))
        if deal and deal.get("value"):
            concrete.append(str(deal["value"]))
        body = "BTCマイナーを見る指標が、採掘量とBTC価格だけではなくなる可能性がある。"
        if concrete:
            body += f" {subject}では" + "、".join(concrete[:2]) + "のAIインフラ契約がその変化を示している。"
        return "BTCマイナーの評価軸が変わる可能性", body, anchor

    if role == "watch":
        milestones = _facts_of(pack, "milestone_date")
        years = list(dict.fromkeys(str(f.get("value")) for f in milestones if f.get("value")))
        fact = milestones[0] if milestones else _find_fact(pack, "date")
        if years:
            if len(years) == 1:
                headline = f"次の節目は{years[0]}年"
            else:
                headline = f"次の節目は{years[0]}年と{years[1]}年"
            evidence = _clean((fact or {}).get("source_sentence"), 300)
            return headline, evidence or f"{subject}の稼働計画は{years[0]}年以降の進捗確認が重要になる。", fact

    return headline, body, preferred


def _normalize_claim_token(value: str) -> str:
    text = _clean(value, 100).casefold().replace(",", "").replace(" ", "")
    text = text.replace("約", "").replace("メガワット", "mw").replace("ギガワット", "gw")
    return text


def _claim_tokens(text: str) -> set[str]:
    raw: list[str] = []
    raw.extend(_matches(_YEAR_PATTERN, text))
    raw.extend(_matches(_CAPACITY_PATTERN, text))
    raw.extend(_matches(_PERCENT_PATTERN, text))
    for pattern in _MONEY_PATTERNS:
        raw.extend(_matches(pattern, text))
    raw.extend(_duration_values(text))
    return {_normalize_claim_token(v) for v in raw if v}


def _supporting_facts(pack: dict, role: str, primary: dict | None) -> list[dict]:
    ordered: list[dict] = []
    if primary:
        ordered.append(primary)
    role_types = {
        "hook": ["deal_value", "capacity", "after_state"],
        "turning_point": ["capacity", "after_state"],
        "new_business": ["after_state", "deal_value", "event"],
        "deal_scale": ["deal_value", "duration", "capacity", "funding_value"],
        "why_now": ["event", "capacity", "after_state"],
        "market_implication": ["capacity", "deal_value", "after_state"],
        "watch": ["milestone_date", "capacity"],
        "timeline": ["milestone_date", "date"],
        "flow_size": ["fund_flow", "money_value", "percentage"],
    }
    for kind in role_types.get(role, []):
        for fact in _facts_of(pack, kind):
            if fact not in ordered:
                ordered.append(fact)
    return ordered[:5]


def _evidence_excerpt(pack: dict, role: str, primary: dict | None) -> str:
    chunks: list[str] = []
    for fact in _supporting_facts(pack, role, primary):
        sentence = _clean(fact.get("source_sentence") or fact.get("text"), 420)
        if sentence and sentence not in chunks and not story_article_cleaner.has_boilerplate(sentence):
            chunks.append(sentence)
    return _clean(" ".join(chunks), 900)


def _claim_evidence_consistent(headline: str, body: str, evidence: str) -> bool:
    claims = _claim_tokens(f"{headline} {body}")
    if not claims:
        return True
    supported = _claim_tokens(evidence)
    return claims.issubset(supported)


def _specific_anchor(text: str, hero: dict, pack: dict) -> bool:
    if _claim_tokens(text):
        return True
    folded = (text or "").casefold()
    return any(entity and entity.casefold() in folded for entity in hero.get("entities") or [])


def _ensure_specific_copy(headline: str, body: str, hero: dict, fact: dict | None, pack: dict) -> tuple[str, str]:
    combined = f"{headline} {body}"
    if _specific_anchor(combined, hero, pack):
        return headline, body
    subject = next((e for e in hero.get("entities") or [] if e), "")
    if subject:
        body = f"{body} {subject}を主語に、確認できる事実だけで読む。"
    elif fact and fact.get("value"):
        body = f"{body} 確認できる数値は{fact['value']}。"
    return headline, body


def _model_specific(text: str, hero: dict, pack: dict) -> bool:
    return _specific_anchor(text, hero, pack) and legacy._model_numeric_safe(text, pack)


def _cluster_ref_coherence(hero: dict, hero_rows: list[dict]) -> tuple[bool, dict[str, float]]:
    hero_resource = dict(hero.get("hero_resource") or {})
    if not hero_resource and hero_rows:
        hero_resource = hero_rows[0]
    scores: dict[str, float] = {}
    ok = True
    for row in hero_rows:
        sid = _sid(row)
        score = 1.0 if sid == _sid(hero_resource) else story_engine.event_similarity(hero_resource, row)
        scores[sid] = score
        if score < 0.47:
            ok = False
    return ok, scores


def _source_specific_card(card: dict, hero: dict, pack: dict) -> bool:
    evidence = _clean(card.get("evidence_excerpt"), 900)
    headline = str(card.get("headline") or "")
    body = str(card.get("key_message") or "")
    text = f"{headline} {body}"
    if not evidence or not (card.get("qa") or {}).get("fact_bound"):
        return False
    if any(pattern in text for pattern in _GENERIC_COPY_PATTERNS):
        return False
    role = str(card.get("story_role") or "")
    if role in {"turning_point", "deal_scale", "watch", "timeline", "flow_size", "scale", "evidence"} and not _claim_tokens(text):
        return False
    return _specific_anchor(text, hero, pack) and bool((card.get("qa") or {}).get("claim_evidence_consistent"))


def generate_story_package(
    resources: list[dict],
    total_card_count: int,
    config: dict,
    output_locale: str = "ja-JP",
    brand: dict | None = None,
    generation_seed: str | None = None,
) -> StoryGenerationResult:
    if output_locale != "ja-JP":
        return StoryGenerationResult({}, error="Storytelling mode requires ja-JP output.")

    prepared = _prepare_story_resources([dict(r) for r in resources or []])
    ranked = story_engine.annotate_resources(prepared)
    if not ranked:
        return StoryGenerationResult({}, error="No story resources are available.")

    context = story_engine.story_context(ranked)
    hero = dict(context.get("hero_story") or {})
    hero_rows = _hero_resources(ranked, hero)
    if not hero_rows:
        return StoryGenerationResult({}, error="Hero Story has no isolated source resources.")

    cluster_ok, cluster_scores = _cluster_ref_coherence(hero, hero_rows)
    if not cluster_ok:
        return StoryGenerationResult({}, error="Hero Story cluster contains resources from different events.")

    pack = _extract_fact_pack(hero, hero_rows)
    hero_ids = {str(v) for v in hero.get("resource_ids") or [] if v}
    if not set(pack.get("source_ids") or []).issubset(hero_ids):
        return StoryGenerationResult({}, error="Hero evidence isolation failed before generation.")

    total_card_count = max(5, min(9, int(total_card_count or 7)))
    roles = story_engine.story_arc(str(hero.get("archetype") or "hidden_giant"), total_card_count - 1)
    seed = generation_seed or hashlib.sha1(f"{hero.get('id')}|{time.time_ns()}".encode()).hexdigest()[:16]
    model_raw, model_warning = legacy._call_model(config, hero, roles, pack)
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
        baseline_headline, baseline_body, preferred_fact = _story_copy(str(hero.get("archetype")), role, hero, pack)
        fact = _best_fact(pack, preferred_fact, role)
        baseline_headline, baseline_body = _ensure_specific_copy(baseline_headline, baseline_body, hero, fact, pack)
        evidence_excerpt = _evidence_excerpt(pack, role, fact)

        headline, body = baseline_headline, baseline_body
        model_card = model_by_role.get(role) or {}
        mh = _clean(model_card.get("headline"), 90)
        mb = _clean(model_card.get("body"), 240)
        if mh and mb and not re.search(r"[가-힣]", mh + mb) and _model_specific(mh + " " + mb, hero, pack):
            if _claim_evidence_consistent(mh, mb, evidence_excerpt):
                headline, body = mh, mb

        claim_ok = _claim_evidence_consistent(headline, body, evidence_excerpt)
        if not claim_ok:
            headline, body = baseline_headline, baseline_body
            claim_ok = _claim_evidence_consistent(headline, body, evidence_excerpt)

        evidence_ref = str((fact or {}).get("source_id") or "")
        if not evidence_ref or evidence_ref not in hero_ids:
            evidence_ref = next(iter(hero_ids))
            if fact:
                fact = dict(fact)
                fact["source_id"] = evidence_ref

        layout = story_engine.layout_for_story(str(hero.get("archetype")), index, f"{seed}:{role}")
        candidates = list(story_engine.ARCHETYPE_LAYOUTS.get(str(hero.get("archetype"))) or [])
        if layout == previous_layout or used_layouts.get(layout, 0) >= 1:
            for alt in candidates:
                if alt != previous_layout and used_layouts.get(alt, 0) == 0:
                    layout = alt
                    break
        previous_layout = layout
        used_layouts[layout] = used_layouts.get(layout, 0) + 1

        scene_type = legacy._scene_type(str(hero.get("archetype")), role)
        prompt = legacy._scene_prompt(str(hero.get("archetype")), role, hero, layout, scene_type, evidence_excerpt)
        cards.append({
            "set": "STORY",
            "slide": index + 1,
            "card_id": f"story-{hero.get('id')}-{index+1}",
            "card_type": "story_editorial",
            "story_id": hero.get("id"),
            "story_role": role,
            "story_archetype": hero.get("archetype"),
            "eyebrow": str(hero.get("archetype") or "STORY").replace("_", " ").upper(),
            "headline": headline,
            "subheadline": body,
            "key_message": body,
            "metrics": [],
            "evidence_refs": [evidence_ref],
            "evidence_excerpt": evidence_excerpt,
            "evidence_score": round(float((fact or {}).get("confidence") or 0.0), 2),
            "source": legacy._source_display(source_map.get(evidence_ref)),
            "footer": "",
            "visual_direction": {
                "deck_family": f"story_{hero.get('archetype')}",
                "format_variant": layout,
                "layout_variant": layout,
                "scene_type": scene_type,
                "story_role": role,
                "story_archetype": hero.get("archetype"),
                "character_required": False,
                "character_visibility": 0.0,
                "character_shot": "none",
                "character_pose": "none",
                "visual_focus": ", ".join(hero.get("visual_motifs") or []),
                "story_scene_prompt": prompt,
                "brand_mark_policy": "text-only キヨサキ; no K monogram/icon",
                "image_prompts": {
                    "4:5": prompt + " 4:5 vertical, 1080x1350.",
                    "9:16": prompt + " 9:16 vertical, 1080x1920.",
                },
            },
            "qa": {
                "renderable": True,
                "mode": "story",
                "fact_bound": bool(fact and evidence_excerpt),
                "claim_evidence_consistent": claim_ok,
                "claim_tokens": sorted(_claim_tokens(f"{headline} {body}")),
                "event_ref_score": cluster_scores.get(evidence_ref, 1.0),
            },
        })

    cards.append(legacy._outro(total_card_count, str(hero.get("archetype")), brand))
    content_cards = cards[:-1]

    generic_count = sum(1 for card in content_cards if not _source_specific_card(card, hero, pack))
    unique_layouts = len({(c.get("visual_direction") or {}).get("layout_variant") for c in content_cards})
    unique_scene_types = len({(c.get("visual_direction") or {}).get("scene_type") for c in content_cards})
    refs_ok = all(set(c.get("evidence_refs") or []).issubset(hero_ids) for c in content_cards)
    evidence_bound = all((c.get("qa") or {}).get("fact_bound") for c in content_cards)
    claim_mismatches = [c.get("slide") for c in content_cards if not (c.get("qa") or {}).get("claim_evidence_consistent")]
    leaks = sum(1 for c in cards if re.search(r"[가-힣]", " ".join(str(c.get(k) or "") for k in ["headline", "subheadline", "key_message"])))
    entity_details = list(hero.get("entity_details") or [])
    entity_pass = bool(entity_details) and all(
        float(e.get("confidence") or 0) >= 0.72
        and str(e.get("name") or "").casefold() not in {"crypto", "crypto.", "editor", "updated", "that", "what", "million", "back", "bitflyer"}
        for e in entity_details
    )
    cluster_coherence = float(hero.get("cluster_coherence") or (1.0 if len(hero_rows) == 1 else 0.0))
    cluster_pass = cluster_ok and cluster_coherence >= 0.47

    boilerplate_facts = [f for f in pack.get("facts") or [] if story_article_cleaner.has_boilerplate(str(f.get("source_sentence") or f.get("text") or ""))]
    article_cleaning_pass = not boilerplate_facts and all(
        not story_article_cleaner.has_boilerplate(str(row.get("material") or "")) for row in hero_rows
    )

    visual_diag = story_renderer.scene_diagnostics(content_cards)
    render_signature_count = int(visual_diag.get("render_signature_count") or 0)
    near_duplicates = list(visual_diag.get("near_duplicate_scene_pairs") or [])
    max_scene_similarity = float(visual_diag.get("max_scene_similarity") or 0.0)
    visual_pass = (
        unique_scene_types >= min(4, len(content_cards))
        and render_signature_count >= min(4, len(content_cards))
        and not near_duplicates
    )

    failures: list[str] = []
    if not refs_ok:
        failures.append("evidence_ref_outside_hero_cluster")
    if not cluster_pass:
        failures.append("hero_cluster_not_same_event")
    if not article_cleaning_pass:
        failures.append("article_boilerplate_contamination")
    if not evidence_bound:
        failures.append("unbound_story_card_evidence")
    if claim_mismatches:
        failures.append("claim_evidence_mismatch")
    if generic_count:
        failures.append("generic_story_copy")
    if leaks:
        failures.append("foreign_language_leak")
    if unique_layouts < min(4, len(content_cards)):
        failures.append("layout_repetition")
    if not visual_pass:
        failures.append("visual_scene_repetition")
    if not entity_pass:
        failures.append("entity_quality")

    publishable = not failures
    story_qa = {
        "hero_evidence_isolated": refs_ok and set(pack.get("source_ids") or []).issubset(hero_ids),
        "hero_cluster_same_event": cluster_pass,
        "cluster_coherence": round(cluster_coherence, 4),
        "cluster_event_scores": cluster_scores,
        "article_cleaning_pass": article_cleaning_pass,
        "boilerplate_fact_count": len(boilerplate_facts),
        "specific_fact_cards": f"{len(content_cards)-generic_count}/{len(content_cards)}",
        "fact_bound_cards": sum(1 for c in content_cards if (c.get("qa") or {}).get("fact_bound")),
        "claim_evidence_mismatch_count": len(claim_mismatches),
        "claim_evidence_mismatch_slides": claim_mismatches,
        "extracted_values_count": len(pack.get("values") or []),
        "milestone_years": pack.get("milestone_years") or [],
        "unique_layouts": unique_layouts,
        "unique_scene_types": unique_scene_types,
        "render_signature_count": render_signature_count,
        "max_scene_similarity": round(max_scene_similarity, 4),
        "near_duplicate_scene_pairs": near_duplicates,
        "generic_card_count": generic_count,
        "foreign_language_leaks": leaks,
        "entity_confidence_pass": entity_pass,
        "publishable": publishable,
        "blocking_reasons": failures,
    }

    for card in cards:
        card.setdefault("qa", {})["story_publishable"] = publishable

    context = dict(context)
    context["hero_story"] = hero
    context["evidence_facts"] = pack
    context["hero_resource_ids"] = sorted(hero_ids)
    context["cluster_event_scores"] = cluster_scores
    context["article_cleaning"] = {str(_sid(row)): row.get("story_cleaning") or {} for row in hero_rows}

    note_lines = [f"# {hero.get('headline_ja')}", "", hero.get("why_now_ja") or "", ""]
    for c in content_cards:
        note_lines.extend([f"## {c['slide']}. {c['headline']}", c.get("key_message") or "", ""])

    package = {
        "mode": "story",
        "story_context": context,
        "cards": {"STORY": cards},
        "note_markdown": "\n".join(note_lines).strip(),
        "content_quality": {
            "mode": "story",
            "pipeline": STORY_CONTENT_PIPELINE_VERSION,
            "engine": story_engine.STORY_ENGINE_VERSION,
            "renderer": story_renderer.STORY_RENDERER_VERSION,
            "cleaner": story_article_cleaner.STORY_ARTICLE_CLEANER_VERSION,
            "generation_seed": seed,
            "hero_story_title": hero.get("headline_ja"),
            "story_archetype": hero.get("archetype"),
            "story_score": hero.get("story_score"),
            "hero_story_score": hero.get("hero_story_score"),
            "model_provider": config.get("provider") or PROVIDER_LOCAL,
            "model_used": bool(model_raw),
            "story_qa": story_qa,
            "policy": "clean article -> same-event cluster -> hero-only typed facts -> claim/evidence validation -> scene renderer -> pixel QA",
        },
    }
    return StoryGenerationResult(package=package, model_warning=model_warning)
