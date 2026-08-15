from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from urllib.request import Request, urlopen

import story_engine_v2 as story_engine


STORY_CONTENT_PIPELINE_VERSION = "story-content-v7.0"
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
    "historical_parallel": "HISTORY",
    "crisis_or_risk": "RISK",
    "opportunity_window": "OPPORTUNITY",
}

ROLE_LABELS_JA = {
    "hook": "最初に見るべきこと",
    "surface": "まず見えている事実",
    "contradiction": "ここにズレがある",
    "evidence": "数字で確認する",
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


@dataclass
class StoryGenerationResult:
    package: dict
    error: str | None = None
    model_warning: str | None = None


def _clean(value: object, limit: int = 600) -> str:
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
        "title": _clean(row.get("title") or row.get("short_title"), 240),
        "url": _clean(row.get("url"), 600),
        "tags": _clean(row.get("tags"), 180),
        "story_score": row.get("story_score"),
        "story_archetype_hint": row.get("story_archetype_hint"),
        "material": _clean(row.get("material") or row.get("excerpt"), 2600),
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
    start, end = value.find("{"), value.rfind("}")
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
                    "options": {"temperature": float(config.get("temperature") or 0.30)},
                },
                {},
            )
            return _json_from_text(((raw.get("message") or {}).get("content") or "")), None
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
                    "temperature": float(config.get("temperature") or 0.30),
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
        return None, f"story reasoning model failed; evidence-bound fallback used: {error}"
    return None, f"Unsupported story provider: {provider}"


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?。！？])\s+|\n+", str(text or ""))
    output: list[str] = []
    for item in raw:
        cleaned = _clean(item, 560)
        if len(cleaned) >= 18 and cleaned not in output:
            output.append(cleaned)
    return output


def _extract_fact_pack(hero: dict, resources: list[dict]) -> dict:
    selected = _candidate_resources(resources, hero, limit=5)
    titles = [_clean(row.get("title"), 260) for row in selected if row.get("title")]
    text = " ".join(
        [
            *titles,
            *[_clean(row.get("material") or row.get("excerpt"), 4500) for row in selected],
        ]
    )
    sentences = _sentences(text)
    years = list(dict.fromkeys(re.findall(r"\b(?:18|19|20)\d{2}\b", text)))[:6]
    money = list(dict.fromkeys(re.findall(r"(?:\$|¥|￥)\s?\d[\d,.]*(?:\s?(?:billion|million|trillion|bn|mn|億|兆|万))?", text, flags=re.I)))[:6]
    percentages = list(dict.fromkeys(re.findall(r"\b\d+(?:\.\d+)?%", text)))[:6]
    metrics: list[str] = []
    for pattern, label in [
        (r"\bshiller\s+cape\b", "シラーCAPE"),
        (r"\bcape\b", "CAPE"),
        (r"price[- ]to[- ]earnings|\bp/e\b", "PER"),
        (r"\betf\b", "ETF"),
        (r"open interest|\boi\b", "OI"),
        (r"funding", "Funding"),
        (r"market share", "市場シェア"),
    ]:
        if re.search(pattern, text, flags=re.I) and label not in metrics:
            metrics.append(label)
    numeric_sentences = [s for s in sentences if re.search(r"\d", s)]
    history_sentences = [s for s in sentences if re.search(r"\b(?:18|19|20)\d{2}\b", s)]
    current_sentences = [s for s in sentences if re.search(r"\b(current|currently|now|today|stands|present)\b|現在|足元|いま", s, flags=re.I)]
    conflict_sentences = [s for s in sentences if re.search(r"\b(yet|but|despite|while|however|although)\b|しかし|一方|なのに", s, flags=re.I)]
    action_sentences = [s for s in sentences if re.search(r"\b(approved|approval|effective|launch|began|started|acquired|bought|sold|inflow|outflow|recorded)\b|承認|開始|流入|流出|買収", s, flags=re.I)]
    cape_values: list[str] = []
    for sentence in sentences:
        if re.search(r"\b(?:shiller\s+)?cape\b", sentence, flags=re.I):
            for number in re.findall(r"\b\d{1,3}(?:\.\d+)?\b", sentence):
                if number not in cape_values and not re.fullmatch(r"(?:18|19|20)\d{2}", number):
                    cape_values.append(number)
    return {
        "titles": titles,
        "text": text,
        "sentences": sentences,
        "years": years,
        "money": money,
        "percentages": percentages,
        "metrics": metrics,
        "numeric_sentences": numeric_sentences[:10],
        "history_sentences": history_sentences[:8],
        "current_sentences": current_sentences[:8],
        "conflict_sentences": conflict_sentences[:8],
        "action_sentences": action_sentences[:8],
        "cape_values": cape_values[:6],
        "entities": list(hero.get("entities") or []),
    }


def _join_ja(items: list[str], limit: int = 3) -> str:
    values = [str(item) for item in items if item][:limit]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "、".join(values[:-1]) + "、" + values[-1]


def _fact_headline(role: str, hero: dict, facts: dict) -> str:
    archetype = str(hero.get("archetype") or "")
    years = facts.get("years") or []
    metrics = facts.get("metrics") or []
    entity = (facts.get("entities") or [""])[0]
    money = facts.get("money") or []
    if role == "hook":
        return _clean(hero.get("headline_ja"), 84) or "いま、何が変わっている？"
    if archetype == "historical_parallel":
        if role == "then" and len(years) >= 2:
            return f"比較されているのは{years[0]}年と{years[1]}年"
        if role == "what_happened":
            return "過去の共通点は「高い評価」にあった"
        if role == "now" and metrics:
            return f"現在地を{metrics[0]}で測る"
        if role == "similarity":
            return "似ているのは価格ではなく評価水準"
        if role == "difference":
            return "同じ水準でも、同じ結末とは限らない"
        if role == "watch":
            return f"次に見るのは{metrics[0] if metrics else '指標'}と実際の価格反応"
    if archetype == "money_flow":
        if role == "flow_source":
            return f"資金の入口は{entity or '機関投資家'}"
        if role == "flow_size":
            return f"確認できる資金規模は{money[0]}" if money else "一日の金額より継続性"
        if role == "where_it_goes":
            return "入った資金は、どこに定着したか"
        if role == "price_gap":
            return "資金は入った。価格はまだ追いついていない"
    return _clean(ROLE_LABELS_JA.get(role) or "次に見るポイント", 84)


def _fact_body(role: str, hero: dict, facts: dict) -> str:
    archetype = str(hero.get("archetype") or "")
    years = facts.get("years") or []
    metrics = facts.get("metrics") or []
    cape_values = facts.get("cape_values") or []
    money = facts.get("money") or []
    percentages = facts.get("percentages") or []
    entities = facts.get("entities") or []
    metric = metrics[0] if metrics else "指標"
    entity = entities[0] if entities else "市場参加者"

    if archetype == "historical_parallel":
        if role == "hook":
            if len(years) >= 2:
                return f"今回の資料は、現在の市場を{years[0]}年と{years[1]}年の局面に並べている。比較の軸はチャートの形ではなく、評価指標の水準だ。"
            return _clean(hero.get("why_now_ja"), 180)
        if role == "then":
            return f"資料が比較対象として挙げている過去の節目は{_join_ja([y + '年' for y in years], 3)}。同じ指標が歴史的な高水準に入った局面として扱われている。"
        if role == "what_happened":
            if metric != "指標":
                return f"重要なのは、その後の値動きだけではない。{metric}が極端な水準に達していたことが、今回の比較の根拠になっている。"
            return "過去の値動きをそのまま再演と見るのではなく、当時どの評価指標が極端だったのかを切り分ける。"
        if role == "now":
            if cape_values:
                return f"記事内で確認できる{metric}関連の数値は{_join_ja(cape_values, 3)}。現在地は過去のピークと同じ物差しで比較されている。"
            if percentages:
                return f"現在地は{metric}と{_join_ja(percentages, 2)}など、記事内の実数で確認する。"
            return f"現在地は{metric}で確認する。見出しの『似ている』ではなく、同じ物差しの数字を比べる。"
        if role == "similarity":
            return f"共通しているのは、{metric}が通常より高い領域へ入っている点。過去の年号より、この共通条件が重要だ。"
        if role == "difference":
            return "ただし同じ評価水準でも、金利・利益・参加者構成まで同じとは限らない。過去の結末をそのまま現在へ貼り付けない。"
        if role == "watch":
            return f"次に確認するのは{metric}の推移と、実際の利益・価格がその高い評価を吸収できるかどうか。"

    if archetype == "money_flow":
        if role == "hook":
            return _clean(hero.get("why_now_ja"), 180)
        if role == "flow_source":
            return f"今回の資金移動で名前が出ている主体は{entity}。誰が買っているのかを先に固定する。"
        if role == "flow_size":
            if money:
                return f"記事内で確認できる資金規模は{_join_ja(money, 2)}。単日の大きさより、複数日にわたり続くかを見る。"
            return "資金規模は単日の数字だけでなく、数日から数週続くフローかどうかで読む。"
        if role == "where_it_goes":
            return "流入した資金が同じ資産に残るのか、周辺市場へ広がるのかを分けて追う。"
        if role == "price_gap":
            return _clean(hero.get("conflict_ja"), 180)
        if role in {"market_implication", "watch"}:
            return _clean(hero.get("implication_ja"), 180)

    if archetype == "policy_change":
        if role == "old_rule":
            return "まず変更前に誰が何をできなかったのかを固定する。制度の意味は、旧ルールとの差で見える。"
        if role == "new_rule":
            return f"今回の変更で中心にいるのは{entity}。見出しではなく、実際に許可・禁止・変更された範囲を確認する。"
        if role == "timeline":
            return f"記事内で確認できる時点は{_join_ja([y + '年' for y in years], 3) or '発表日と施行日'}。市場が動ける日と発表日は分けて見る。"

    if archetype == "crisis_or_risk":
        if role == "incident":
            return f"最初に固定するのは{entity}で起きた事実。被害額や対象が確認できるまで推測を広げない。"
        if role == "exposure" and money:
            return f"記事内で確認できる金額は{_join_ja(money, 2)}。直接露出と間接露出を分けて読む。"

    if role == "hook":
        return _clean(hero.get("why_now_ja"), 180)
    if role in {"contradiction", "difference", "constraint"}:
        return _clean(hero.get("conflict_ja"), 180)
    if role in {"market_implication", "watch", "what_changes", "who_gains"}:
        return _clean(hero.get("implication_ja"), 180)
    if money and role in {"scale", "evidence"}:
        return f"記事内で確認できる規模は{_join_ja(money, 2)}。この数字を他の事実と同じ時間軸に置く。"
    if percentages and role == "evidence":
        return f"記事内の確認数字は{_join_ja(percentages, 3)}。解釈より先に、数字そのものを固定する。"
    return {
        "surface": "見出しを要約するのではなく、誰が動き、何が変わったかを事実から固定する。",
        "evidence": "記事本文にある数字、主体、時点を先に固定し、推測を混ぜない。",
        "explanation": _clean(hero.get("why_now_ja"), 180),
        "identity": f"今回の主役は{entity}。知名度ではなく、市場のどこを握っているかを見る。",
        "what_it_does": f"{entity}が実際に動かしている資金・制度・インフラの位置を確認する。",
        "scale": f"規模は{_join_ja(money, 2) or _join_ja(percentages, 2) or '記事内の実数'}で確認する。",
        "why_now": _clean(hero.get("why_now_ja"), 180),
        "origin": "始点と現在地を分けると、途中で何が変わったかが見える。",
        "turning_point": "転換点は、資金・制度・利用者のどれが先に変わったかで確認する。",
        "what_changed": _clean(hero.get("why_now_ja"), 180),
        "old_order": "これまで誰が資金・顧客・規制アクセスを握っていたかを整理する。",
        "challenger": f"新しい勢力として{entity}がどこへ入ってきたのかを見る。",
        "who_is_affected": "企業、機関、個人を分け、誰の行動が実際に変わるのかを見る。",
        "contagion": "一つの問題が流動性、信用、他の主体へ広がるかを追う。",
    }.get(role, "確認できた事実から、次に変わる条件を追う。")


def _evidence_excerpt(role: str, facts: dict) -> str:
    pools = []
    if role in {"then", "what_happened", "similarity", "difference"}:
        pools += facts.get("history_sentences") or []
    if role in {"now", "watch"}:
        pools += facts.get("current_sentences") or []
    if role in {"contradiction", "price_gap", "constraint"}:
        pools += facts.get("conflict_sentences") or []
    if role in {"flow_source", "flow_size", "new_rule", "turning_point", "what_changed"}:
        pools += facts.get("action_sentences") or []
    pools += facts.get("numeric_sentences") or []
    pools += facts.get("sentences") or []
    return _clean(next((item for item in pools if item), ""), 520)


def _model_prompts(hero: dict, roles: list[str], resources: list[dict], facts: dict) -> tuple[str, str]:
    allowed_sources = [_source_payload(row) for row in resources]
    allowed_ids = [row["id"] for row in allowed_sources if row.get("id")]
    system_prompt = (
        "You are the editorial director of a premium Japanese financial documentary carousel. "
        "This is not a trader briefing. Every slide must add a concrete source-bound fact, comparison, entity, number, date, or implication. "
        "Generic advice such as 'check the flow' is not sufficient unless the source fact is also stated. "
        "Use only facts supported by allowed_sources and evidence_facts. Never invent numbers, quotes, dates, reactions, or causality. "
        "Write concise native Japanese. Do not expose THE OBSERVER, Korean text, K monograms, or internal debug terms. Return JSON only."
    )
    schema = {
        "hero": {"headline_ja": "Japanese hook", "why_now_ja": "Japanese", "conflict_ja": "Japanese", "implication_ja": "Japanese", "visual_motifs": ["visual phrase"]},
        "cards": [{"role": "supplied role", "headline": "Japanese", "body": "Japanese source-bound copy", "evidence_refs": ["allowed source id"], "visual_concept": "production direction"}],
    }
    user_prompt = json.dumps(
        {
            "story": {key: hero.get(key) for key in ["id", "topic", "archetype", "headline_seed", "headline_ja", "why_now_ja", "conflict_ja", "implication_ja", "entities"]},
            "roles": roles,
            "evidence_facts": {key: facts.get(key) for key in ["years", "money", "percentages", "metrics", "cape_values", "history_sentences", "current_sentences", "conflict_sentences"]},
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
    by_role: dict[str, dict] = {}
    for item in raw.get("cards") if isinstance(raw.get("cards"), list) else []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if role not in roles or role in by_role:
            continue
        headline = _clean(item.get("headline"), 92)
        body = _clean(item.get("body"), 230)
        if not _is_japanese_visible(headline) or not _is_japanese_visible(body):
            continue
        by_role[role] = {
            "role": role,
            "headline": headline,
            "body": body,
            "evidence_refs": [str(ref) for ref in (item.get("evidence_refs") or []) if str(ref) in allowed_ids],
            "visual_concept": _clean(item.get("visual_concept"), 300),
        }
    return hero_patch, [by_role[role] for role in roles if role in by_role]


def _source_display(row: dict) -> dict:
    if not row:
        return {}
    return {
        "source_id": _source_id(row),
        "publisher": _clean(row.get("source") or row.get("publisher"), 80),
        "short_title": _clean(row.get("title") or row.get("short_title"), 160),
        "url": _clean(row.get("url"), 600),
        "source_quality": {"story_score": row.get("story_score"), "risk_score": row.get("risk_score")},
    }


def _scene_prompt(archetype: str, role: str, hero: dict, layout: str, facts: dict, visual_concept: str = "") -> str:
    motifs = ", ".join(hero.get("visual_motifs") or ["source-specific financial documentary"])
    entities = ", ".join((hero.get("entities") or [])[:2]) or str(hero.get("topic") or "financial market")
    years = ", ".join((facts.get("years") or [])[:3])
    metrics = ", ".join((facts.get("metrics") or [])[:2])
    evidence_hint = ", ".join(value for value in [years, metrics] if value)
    concept = visual_concept or f"source-specific documentary scene for role {role}"
    return (
        f"Premium Japanese financial documentary editorial image. Archetype: {archetype}. Story role: {role}. "
        f"Actual subject: {entities}. Evidence context: {evidence_hint or 'source article facts'}. Motifs: {motifs}. "
        f"Concept: {concept}. Composition: {layout}. Realistic, cinematic, tactile, high-end magazine photography. "
        "The main visual must change with the story role, not reuse the same chart background. "
        "No text inside the image, no captions, no Japanese glyphs, no K monogram, no orange K symbol, no logo, no watermark, no floating coins. "
        "Leave intentional negative space for renderer-composited typography."
    )


def _build_story_card(*, index: int, role: str, hero: dict, model_card: dict | None, resources_by_id: dict[str, dict], facts: dict, generation_seed: str) -> dict:
    archetype = str(hero.get("archetype") or "opportunity_window")
    model_card = model_card or {}
    headline = _clean(model_card.get("headline"), 92) if _is_japanese_visible(model_card.get("headline")) else _fact_headline(role, hero, facts)
    body = _clean(model_card.get("body"), 230) if _is_japanese_visible(model_card.get("body")) else _fact_body(role, hero, facts)
    evidence_refs = [str(ref) for ref in model_card.get("evidence_refs") or [] if str(ref) in resources_by_id]
    if not evidence_refs:
        evidence_refs = [str(item) for item in (hero.get("resource_ids") or []) if str(item) in resources_by_id][:2]
    source_row = resources_by_id.get(evidence_refs[0]) if evidence_refs else {}
    layout = story_engine.layout_for_story(archetype, index, f"{generation_seed}:{role}:{hero.get('id')}")
    evidence_excerpt = _evidence_excerpt(role, facts)
    scene_prompt = _scene_prompt(archetype, role, hero, layout, facts, _clean(model_card.get("visual_concept"), 300))
    return {
        "set": "STORY",
        "slide": index + 1,
        "card_id": f"story-{hero.get('id') or 'hero'}-{index + 1}",
        "card_type": "story_editorial",
        "story_id": hero.get("id") or "story",
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
        "evidence_excerpt": evidence_excerpt,
        "evidence_score": round(float(hero.get("story_score") or 0.0) / 100.0, 3),
        "card_purpose": f"story:{role}",
        "new_information": body,
        "semantic_summary": {"semantic_key": f"story:{archetype}:{role}", "story_role": role, "topic": hero.get("topic")},
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
            "image_prompts": {"4:5": scene_prompt + " 4:5 vertical composition, 1080x1350.", "9:16": scene_prompt + " 9:16 vertical composition, 1080x1920."},
        },
        "qa": {"renderable": True, "mode": "story", "evidence_bound": bool(evidence_excerpt or evidence_refs)},
    }


def _build_outro(total_cards: int, archetype: str, brand: dict | None = None) -> dict:
    brand = dict(brand or {})
    cta = _clean(brand.get("cta"), 180) or "フォローして、勢力が入ったポイントを無料でチェック。"
    account = _clean(brand.get("account"), 80)
    footer = DISPLAY_BRAND_LABEL + (f" · {account}" if account else "")
    return {
        "set": "STORY",
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
        f"- Archetype: {hero.get('archetype') or ''}",
        f"- Story Score: {hero.get('story_score') or 0}",
        f"- Conflict: {hero.get('conflict_ja') or ''}",
        f"- Implication: {hero.get('implication_ja') or ''}",
        "",
        "## Story Arc",
    ]
    for card in cards:
        if card.get("card_type") == "brand_outro":
            continue
        lines.extend([f"### {card.get('slide')}. {card.get('headline')}", card.get("key_message") or "", ""])
    lines.append("## Sources")
    used: set[str] = set()
    for card in cards:
        for ref in card.get("evidence_refs") or []:
            if ref in used:
                continue
            used.add(ref)
            row = resources_by_id.get(ref) or {}
            lines.append(f"- {_clean(row.get('source'), 80)} · {_clean(row.get('title'), 180)} · {_clean(row.get('url'), 600)}")
    return "\n".join(lines).strip()


def generate_story_package(resources: list[dict], total_card_count: int, config: dict, output_locale: str = "ja-JP", brand: dict | None = None, generation_seed: str | None = None) -> StoryGenerationResult:
    if output_locale != "ja-JP":
        return StoryGenerationResult(package={}, error="Storytelling mode currently requires ja-JP output.")
    ranked = story_engine.annotate_resources([dict(row) for row in resources or []])
    if not ranked:
        return StoryGenerationResult(package={}, error="No story resources are available.")
    context = story_engine.story_context(ranked)
    hero = dict(context.get("hero_story") or {})
    if not hero:
        return StoryGenerationResult(package={}, error="No evidence-backed Hero Story could be selected.")
    total_card_count = max(5, min(8, int(total_card_count or 7)))
    roles = story_engine.story_arc(str(hero.get("archetype") or "opportunity_window"), total_card_count - 1)
    seed = generation_seed or hashlib.sha1(f"{hero.get('id')}|{time.time_ns()}".encode("utf-8", errors="ignore")).hexdigest()[:16]

    selected_resources = _candidate_resources(ranked, hero, limit=7)
    resources_by_id = {_source_id(row): row for row in ranked if _source_id(row)}
    facts = _extract_fact_pack(hero, selected_resources)
    system_prompt, user_prompt = _model_prompts(hero, roles, selected_resources, facts)
    model_raw, model_warning = _call_story_model(config, system_prompt, user_prompt)
    allowed_ids = {_source_id(row) for row in selected_resources if _source_id(row)}
    hero_patch, model_cards = _validate_model_cards(model_raw, roles, allowed_ids)

    for key in ["headline_ja", "why_now_ja", "conflict_ja", "implication_ja"]:
        candidate = _clean(hero_patch.get(key), 220)
        if _is_japanese_visible(candidate):
            hero[key] = candidate
    motifs = hero_patch.get("visual_motifs") if isinstance(hero_patch.get("visual_motifs"), list) else []
    if motifs:
        hero["visual_motifs"] = [_clean(item, 120) for item in motifs if _clean(item, 120)][:3]

    model_by_role = {item["role"]: item for item in model_cards}
    cards = [
        _build_story_card(
            index=index,
            role=role,
            hero=hero,
            model_card=model_by_role.get(role),
            resources_by_id=resources_by_id,
            facts=facts,
            generation_seed=seed,
        )
        for index, role in enumerate(roles)
    ]
    cards.append(_build_outro(total_card_count, str(hero.get("archetype") or "opportunity_window"), brand))

    context = dict(context)
    context["hero_story"] = hero
    context["evidence_facts"] = {key: facts.get(key) for key in ["years", "money", "percentages", "metrics", "cape_values"]}
    package = {
        "mode": "story",
        "story_context": context,
        "cards": {"STORY": cards},
        "note_markdown": _note_markdown(context, cards, resources_by_id),
        "content_quality": {
            "mode": "story",
            "pipeline": STORY_CONTENT_PIPELINE_VERSION,
            "engine": story_engine.STORY_ENGINE_VERSION,
            "generation_seed": seed,
            "hero_story_title": hero.get("headline_ja") or "",
            "story_archetype": hero.get("archetype") or "",
            "story_score": hero.get("story_score") or 0,
            "model_provider": config.get("provider") or PROVIDER_LOCAL,
            "model_used": bool(model_raw),
            "evidence_binding": "role copy and visual direction are derived from source-bound fact pack; no trader intermediate",
        },
    }
    return StoryGenerationResult(package=package, error=None, model_warning=model_warning)
