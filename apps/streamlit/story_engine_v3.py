from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass


STORY_ENGINE_VERSION = "story-engine-v8.0"

ARCHETYPES = {
    "business_transformation",
    "contradiction",
    "hidden_giant",
    "origin_to_now",
    "money_flow",
    "power_shift",
    "policy_change",
    "historical_parallel",
    "crisis_or_risk",
    "opportunity_window",
}

STORY_ARCS = {
    "business_transformation": ["hook", "old_business", "turning_point", "new_business", "deal_scale", "why_now", "market_implication", "watch"],
    "contradiction": ["hook", "surface", "contradiction", "evidence", "explanation", "what_changes", "watch"],
    "hidden_giant": ["hook", "identity", "what_it_does", "scale", "why_now", "market_implication", "watch"],
    "origin_to_now": ["hook", "origin", "turning_point", "now", "evidence", "market_implication", "watch"],
    "money_flow": ["hook", "flow_source", "flow_size", "where_it_goes", "price_gap", "market_implication", "watch"],
    "power_shift": ["hook", "old_order", "challenger", "turning_point", "who_gains", "market_implication", "watch"],
    "policy_change": ["hook", "old_rule", "new_rule", "who_is_affected", "timeline", "market_implication", "watch"],
    "historical_parallel": ["hook", "then", "what_happened", "now", "similarity", "difference", "watch"],
    "crisis_or_risk": ["hook", "incident", "exposure", "contagion", "evidence", "market_implication", "watch"],
    "opportunity_window": ["hook", "what_changed", "why_now", "evidence", "constraint", "market_implication", "watch"],
}

ARCHETYPE_LAYOUTS = {
    "business_transformation": ["full_bleed_bottom", "split_left", "top_caption", "poster_center", "data_monument", "newspaper_panel", "split_top", "full_bleed_bottom"],
    "contradiction": ["split_top", "split_left", "poster_center", "newspaper_panel", "full_bleed_bottom", "top_caption", "data_monument"],
    "hidden_giant": ["full_bleed_bottom", "poster_center", "split_left", "data_monument", "newspaper_panel", "split_top", "top_caption"],
    "origin_to_now": ["poster_center", "split_top", "newspaper_panel", "split_left", "data_monument", "full_bleed_bottom", "top_caption"],
    "money_flow": ["data_monument", "split_left", "full_bleed_bottom", "split_top", "poster_center", "newspaper_panel", "top_caption"],
    "power_shift": ["poster_center", "split_left", "newspaper_panel", "data_monument", "full_bleed_bottom", "split_top", "top_caption"],
    "policy_change": ["newspaper_panel", "poster_center", "split_left", "top_caption", "data_monument", "full_bleed_bottom", "split_top"],
    "historical_parallel": ["newspaper_panel", "split_left", "poster_center", "split_top", "data_monument", "full_bleed_bottom", "top_caption"],
    "crisis_or_risk": ["poster_center", "newspaper_panel", "split_left", "data_monument", "split_top", "full_bleed_bottom", "top_caption"],
    "opportunity_window": ["full_bleed_bottom", "poster_center", "split_left", "data_monument", "split_top", "newspaper_panel", "top_caption"],
}

GENERIC_ENTITIES = {
    "crypto", "editor", "reporter", "news", "market", "markets", "today", "global", "japan", "coin",
    "article", "breaking", "exclusive", "update", "analysis", "bitcoin", "ethereum", "btc", "eth", "etf",
}

KNOWN_ENTITIES = {
    "riot platforms": ("Riot Platforms", "company"),
    "riot": ("Riot Platforms", "company"),
    "anthropic": ("Anthropic", "company"),
    "jason les": ("Jason Les", "person"),
    "ジェイソン・レス": ("Jason Les", "person"),
    "ライオット・プラットフォームズ": ("Riot Platforms", "company"),
    "アンソロピック": ("Anthropic", "company"),
    "blackrock": ("BlackRock", "company"),
    "fidelity": ("Fidelity", "company"),
    "binance": ("Binance", "company"),
    "coinbase": ("Coinbase", "company"),
    "metaplanet": ("Metaplanet", "company"),
    "bitflyer": ("bitFlyer", "company"),
    "ビットフライヤー": ("bitFlyer", "company"),
    "arthur hayes": ("Arthur Hayes", "person"),
    "アーサー・ヘイズ": ("Arthur Hayes", "person"),
    "tether": ("Tether", "company"),
    "sec": ("SEC", "institution"),
    "cftc": ("CFTC", "institution"),
    "fbi": ("FBI", "institution"),
    "wall street": ("Wall Street", "institution"),
    "robert shiller": ("Robert Shiller", "person"),
    "shiller": ("Shiller", "person"),
    "s&p 500": ("S&P 500", "index"),
}

TRANSFORM_WORDS = ["diversif", "pivot", "transition", "shift", "expand", "conversion", "転換", "多角化", "事業拡大", "転じ", "移行"]
DEAL_WORDS = ["contract", "lease", "deal", "agreement", "acquire", "partnership", "契約", "リース", "提携", "買収"]
HISTORY_WORDS = ["1929", "2000", "dot-com", "dotcom", "cape", "shiller", "historical", "歴史", "過去"]
FLOW_WORDS = ["inflow", "outflow", "fund flow", "etf flow", "流入", "流出", "資金", "etf"]
POLICY_WORDS = ["regulation", "law", "rule", "approval", "sec", "cftc", "規制", "法律", "承認", "金融庁"]
CRISIS_WORDS = ["hack", "exploit", "liquidation", "bankrupt", "collapse", "attack", "theft", "stole", "ハック", "破綻", "清算", "窃盗", "起訴"]
POWER_WORDS = ["market share", "dominance", "takeover", "challenger", "主導権", "シェア", "覇権"]
OPPORTUNITY_WORDS = ["launch", "open access", "adoption", "解禁", "採用", "開始", "新規参入"]
CONFLICT_WORDS = ["but", "yet", "despite", "however", "while", "しかし", "一方", "なのに"]


@dataclass
class StoryCandidate:
    id: str
    topic: str
    archetype: str
    entities: list[str]
    entity_details: list[dict]
    resource_ids: list[str]
    source_names: list[str]
    headline_seed: str
    headline_ja: str
    why_now_ja: str
    conflict_ja: str
    implication_ja: str
    visual_motifs: list[str]
    story_score: float
    hero_story_score: float
    confidence: float
    cluster_size: int
    hero_resource: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: object, limit: int = 7000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _title(row: dict) -> str:
    return _clean(row.get("title") or row.get("short_title"), 320)


def _material(row: dict) -> str:
    return _clean(row.get("material") or row.get("full_material") or row.get("excerpt"), 7000)


def _combined(row: dict) -> str:
    return f"{_title(row)} {_clean(row.get('tags'), 240)} {_material(row)}"


def _has(text: str, word: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9 .&+/-]+", word):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text, flags=re.I))
    return word in text


def _hits(text: str, words: list[str]) -> int:
    return sum(1 for word in words if _has(text, word))


def _numeric_density(text: str) -> int:
    return len(re.findall(r"(?:\$|¥|￥)?\d[\d,.]*(?:\s?(?:%|billion|million|trillion|bn|mn|億|兆|万|MW|GW|年))?", text, flags=re.I))


def _entity_details(row: dict) -> list[dict]:
    title = _title(row)
    lead = _material(row)[:2200]
    text = f"{title} {lead}"
    details: dict[str, dict] = {}
    lower = text.lower()
    for key, (display, kind) in KNOWN_ENTITIES.items():
        count = lower.count(key.lower()) if key.isascii() else text.count(key)
        if count:
            score = min(0.99, 0.70 + 0.06 * min(count, 4) + (0.12 if key.lower() in title.lower() else 0.0))
            current = details.get(display)
            if current is None or score > current["confidence"]:
                details[display] = {"name": display, "type": kind, "confidence": round(score, 2), "mentions": count}

    for match in re.findall(r"\b(?:[A-Z][A-Za-z0-9.&-]{2,})(?:\s+[A-Z][A-Za-z0-9.&-]{2,}){0,2}\b", f"{title} {lead[:900]}"):
        name = match.strip(" .,:;-")
        if not name or name.lower() in GENERIC_ENTITIES:
            continue
        if any(part.lower() in GENERIC_ENTITIES for part in name.split()):
            continue
        if len(name) < 4 or name.upper() in {"USD", "MW", "GW"}:
            continue
        count = len(re.findall(re.escape(name), text, flags=re.I))
        confidence = 0.66 + min(0.18, count * 0.04) + (0.08 if name in title else 0.0)
        details.setdefault(name, {"name": name, "type": "proper_noun", "confidence": round(min(0.92, confidence), 2), "mentions": count})

    return sorted(details.values(), key=lambda item: (item["confidence"], item["mentions"]), reverse=True)[:6]


def _entities(row: dict) -> list[str]:
    return [item["name"] for item in _entity_details(row) if item["confidence"] >= 0.72][:5]


def _is_business_transformation(text: str) -> bool:
    mining = any(_has(text, w) for w in ["mining", "miner", "マイニング", "マイナー"])
    ai_infra = any(_has(text, w) for w in ["data center", "datacenter", "ai infrastructure", "データセンター", "AI"])
    has_deal = _hits(text, DEAL_WORDS) >= 1
    has_transform = _hits(text, TRANSFORM_WORDS) >= 1
    has_scale = _numeric_density(text) >= 3
    return mining and ai_infra and has_deal and (has_transform or has_scale)


def _is_contradiction(text: str) -> bool:
    # A contradiction requires a connective plus two distinct measurable market ideas.
    if _hits(text, CONFLICT_WORDS) == 0:
        return False
    signal_groups = 0
    for words in [
        ["price", "価格"], ["inflow", "outflow", "flow", "流入", "流出", "資金"],
        ["sentiment", "センチメント"], ["volume", "出来高"], ["demand", "supply", "需要", "供給"],
    ]:
        if any(_has(text, word) for word in words):
            signal_groups += 1
    return signal_groups >= 2


def classify_archetype(row: dict) -> str:
    text = _combined(row)
    if _is_business_transformation(text):
        return "business_transformation"
    if _hits(text, HISTORY_WORDS) >= 2:
        return "historical_parallel"
    if _hits(text, CRISIS_WORDS) >= 1:
        return "crisis_or_risk"
    if _hits(text, POLICY_WORDS) >= 2:
        return "policy_change"
    if _hits(text, FLOW_WORDS) >= 2:
        return "money_flow"
    if _hits(text, POWER_WORDS) >= 2:
        return "power_shift"
    if _is_contradiction(text):
        return "contradiction"
    if _hits(text, OPPORTUNITY_WORDS) >= 2:
        return "opportunity_window"
    if _hits(text, TRANSFORM_WORDS) >= 1:
        return "origin_to_now"
    return "hidden_giant"


def _visual_motifs(row: dict, archetype: str) -> list[str]:
    text = _combined(row)
    if archetype == "business_transformation":
        return ["Bitcoin mining hall", "high-voltage power infrastructure", "hyperscale AI data center"]
    if archetype == "historical_parallel":
        return ["archival Wall Street", "historical newspaper", "modern valuation display"]
    if archetype == "money_flow":
        return ["institutional asset manager", "capital flow network", "market price reaction"]
    if archetype == "policy_change":
        return ["official policy document", "regulator building", "affected financial institution"]
    if archetype == "crisis_or_risk":
        return ["forensic evidence", "digital asset custody", "risk contagion map"]
    if archetype == "power_shift":
        return ["competing institutions", "market share transition", "capital reallocation"]
    if archetype == "origin_to_now":
        return ["archive-to-present transformation", "industrial infrastructure", "current market role"]
    if archetype == "contradiction":
        return ["two opposing market signals", "price versus flow", "evidence split-screen"]
    if archetype == "opportunity_window":
        return ["new market access", "institutional gateway", "early adoption"]
    entities = _entities(row)
    return [f"documentary environment around {entities[0]}" if entities else "institutional documentary scene"]


def _component_scores(row: dict) -> dict:
    text = _combined(row)
    title = _title(row)
    entities = _entity_details(row)
    nums = _numeric_density(text)
    hook = min(100.0, 30 + (18 if "?" in title or "？" in title else 0) + min(42, nums * 5))
    conflict = 78.0 if _is_contradiction(text) else min(45.0, _hits(text, CONFLICT_WORDS) * 18.0)
    character = min(100.0, len(entities) * 24.0)
    change = min(100.0, _hits(text, TRANSFORM_WORDS + DEAL_WORDS) * 20.0)
    scale = min(100.0, nums * 10.0)
    implication = min(100.0, 35 + 10 * sum(_has(text, w) for w in ["bitcoin", "btc", "market", "institution", "ビットコイン", "市場", "AI"]))
    visual = min(100.0, 35 + 12 * sum(_has(text, w) for w in ["data center", "mining", "wall street", "bank", "データセンター", "マイニング", "AI"]))
    evidence = min(100.0, 25 + min(55, nums * 6) + (15 if len(_material(row)) > 800 else 0))
    novelty = 85.0 if _is_business_transformation(text) else 55.0
    return {
        "story_hook_score": round(hook, 1),
        "conflict_score": round(conflict, 1),
        "character_score": round(character, 1),
        "change_score": round(change, 1),
        "scale_score": round(scale, 1),
        "market_implication_score": round(implication, 1),
        "visuality_score": round(visual, 1),
        "evidence_story_score": round(evidence, 1),
        "novelty_score": round(novelty, 1),
    }


def annotate_resource(row: dict) -> dict:
    item = dict(row or {})
    components = _component_scores(item)
    archetype = classify_archetype(item)
    weighted = (
        components["story_hook_score"] * 0.14 + components["conflict_score"] * 0.08
        + components["character_score"] * 0.12 + components["change_score"] * 0.16
        + components["scale_score"] * 0.12 + components["market_implication_score"] * 0.12
        + components["visuality_score"] * 0.12 + components["evidence_story_score"] * 0.09
        + components["novelty_score"] * 0.05
    )
    risk_penalty = max(0.0, (float(item.get("risk_score") or 0) - 35.0) * 0.20)
    story_score = max(0.0, min(100.0, weighted - risk_penalty))
    item.update(components)
    item["story_score"] = round(story_score, 2)
    item["story_archetype_hint"] = archetype
    item["story_entity_details"] = _entity_details(item)
    item["story_entities"] = _entities(item)
    item["story_topic"] = _clean(item.get("tags"), 100) or (item["story_entities"][0] if item["story_entities"] else "STORY")
    item["story_visual_motifs"] = _visual_motifs(item, archetype)
    item["editorial_score"] = round(story_score * 0.85 + float(item.get("trader_score") or 0.0) * 0.15, 2)
    return item


def annotate_resources(resources: list[dict]) -> list[dict]:
    rows = [annotate_resource(row) for row in resources or [] if isinstance(row, dict)]
    return sorted(rows, key=lambda row: (float(row.get("editorial_score") or 0), float(row.get("story_score") or 0)), reverse=True)


def _tokens(row: dict) -> set[str]:
    text = f"{_title(row)} {' '.join(row.get('story_entities') or [])}".lower()
    stop = {"bitcoin", "btc", "crypto", "market", "news", "today", "ビットコイン", "暗号資産"}
    return {t for t in re.findall(r"[a-z0-9]{3,}|[ァ-ヶ一-龥]{2,}", text) if t not in stop}


def _similarity(a: dict, b: dict) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    jac = len(ta & tb) / max(1, len(ta | tb))
    ea, eb = set(a.get("story_entities") or []), set(b.get("story_entities") or [])
    entity = len(ea & eb) / max(1, len(ea | eb)) if ea or eb else 0.0
    return jac * 0.72 + entity * 0.28


def cluster_story_candidates(resources: list[dict], similarity_threshold: float = 0.34) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for row in annotate_resources(resources):
        best_idx, best = -1, 0.0
        for idx, cluster in enumerate(clusters):
            score = max((_similarity(row, other) for other in cluster[:3]), default=0.0)
            if score > best:
                best_idx, best = idx, score
        if best_idx >= 0 and best >= similarity_threshold:
            clusters[best_idx].append(row)
        else:
            clusters.append([row])
    return clusters


def _headline_ja(row: dict, archetype: str) -> str:
    title = _title(row)
    entities = row.get("story_entities") or []
    if archetype == "business_transformation":
        subject = "Riot" if "Riot Platforms" in entities else (entities[0] if entities else "BTCマイナー")
        return f"{subject}は、BTC採掘企業からAIインフラへ軸足を移す。"
    if archetype == "historical_parallel":
        years = re.findall(r"\b(?:19|20)\d{2}\b", _combined(row))
        if "1929" in years and "2000" in years:
            return "1929年と2000年。いま再び同じ警戒線へ。"
        return "過去の極端な局面と、いまを同じ指標で比べる。"
    if archetype == "money_flow":
        subject = entities[0] if entities else "機関投資家"
        return f"{subject}に資金は入った。価格は追いついたか。"
    if archetype == "crisis_or_risk":
        return title[:54] or "暗号資産市場で起きた異変。どこまで波及する？"
    if archetype == "policy_change":
        return title[:54] or "ルール変更で、誰の行動が変わるのか。"
    if archetype == "power_shift":
        return title[:54] or "主導権が動いている。次に強くなるのは誰か。"
    if archetype == "contradiction":
        return title[:54] or "数字と反応のズレに、次のヒントがある。"
    return title[:54] or "この変化は、市場の何を変えるのか。"


def _narrative_specificity(row: dict) -> float:
    text = _combined(row)
    return min(100.0, 18 * len(_entity_details(row)) + 6 * _numeric_density(text) + (18 if _hits(text, DEAL_WORDS) else 0))


def _hero_score(row: dict, cluster_size: int) -> float:
    specificity = _narrative_specificity(row)
    evidence = float(row.get("evidence_story_score") or 0)
    headline = float(row.get("story_hook_score") or 0)
    transform = float(row.get("change_score") or 0)
    visual = float(row.get("visuality_score") or 0)
    base = float(row.get("story_score") or 0)
    corroboration = min(8.0, max(0, cluster_size - 1) * 3.0)
    weak_penalty = 10.0 if not row.get("story_entities") and _numeric_density(_combined(row)) < 2 else 0.0
    generic_penalty = 8.0 if _title(row).lower() in {"bitcoin market update", "market update"} else 0.0
    score = base * 0.40 + specificity * 0.15 + evidence * 0.15 + headline * 0.10 + transform * 0.10 + visual * 0.10 + corroboration - weak_penalty - generic_penalty
    return round(max(0.0, min(100.0, score)), 2)


def _why_now(archetype: str, row: dict) -> str:
    if archetype == "business_transformation":
        return "BTCマイニングで築いた電力インフラが、AIデータセンター需要によって別の収益源へ変わろうとしている。"
    if archetype == "historical_parallel":
        return "1929年や2000年と同じ指標が比較対象になるほど、現在のバリュエーションが極端な領域に近づいている。"
    if archetype == "money_flow":
        return "資金流入の大きさだけでなく、それが継続して価格へ伝わるかが次の焦点になる。"
    return "見出しではなく、具体的な主体・規模・変化を追うと市場への意味が見えやすい。"


def _conflict(archetype: str) -> str:
    return {
        "business_transformation": "BTC価格に依存する採掘事業と、長期契約型のAIインフラ収益では評価軸がまったく違う。",
        "historical_parallel": "指標が似た水準でも、流動性と市場参加者まで同じとは限らない。",
        "money_flow": "資金流入が大きくても、価格が同時に上がるとは限らない。",
        "contradiction": "二つの確認可能な事実が、同じ方向を示していない。",
    }.get(archetype, "材料の大きさと、実際の市場反応は分けて確認する必要がある。")


def _implication(archetype: str) -> str:
    return {
        "business_transformation": "BTCマイナーの企業価値が、採掘量だけでなく電力・土地・AI向け長期契約で評価される余地が出てくる。",
        "historical_parallel": "過去の再演を決めつけず、比較指標が崩れる条件と現在の市場反応を分けて追う。",
        "money_flow": "フローが継続し、遅れて価格が追随するかを確認する。",
    }.get(archetype, "次に確認できる事実が、ストーリーの継続性を決める。")


def build_story_candidates(resources: list[dict]) -> list[dict]:
    candidates: list[StoryCandidate] = []
    for cluster in cluster_story_candidates(resources):
        cluster = sorted(cluster, key=lambda r: float(r.get("story_score") or 0), reverse=True)
        hero = cluster[0]
        archetype = str(hero.get("story_archetype_hint") or classify_archetype(hero))
        rid = [str(r.get("id") or r.get("source_id") or r.get("url") or "") for r in cluster]
        cid = "story_" + hashlib.sha1("|".join(rid + [archetype]).encode("utf-8", errors="ignore")).hexdigest()[:12]
        candidate = StoryCandidate(
            id=cid,
            topic=str(hero.get("story_topic") or "STORY"),
            archetype=archetype,
            entities=list(hero.get("story_entities") or []),
            entity_details=list(hero.get("story_entity_details") or []),
            resource_ids=rid,
            source_names=list(dict.fromkeys(str(r.get("source") or "") for r in cluster if r.get("source")))[:5],
            headline_seed=_title(hero),
            headline_ja=_headline_ja(hero, archetype),
            why_now_ja=_why_now(archetype, hero),
            conflict_ja=_conflict(archetype),
            implication_ja=_implication(archetype),
            visual_motifs=list(hero.get("story_visual_motifs") or _visual_motifs(hero, archetype)),
            story_score=round(float(hero.get("story_score") or 0), 2),
            hero_story_score=_hero_score(hero, len(cluster)),
            confidence=round(min(0.98, 0.70 + len(cluster) * 0.04 + len(hero.get("story_entities") or []) * 0.03), 2),
            cluster_size=len(cluster),
            hero_resource=hero,
        )
        candidates.append(candidate)
    return [c.to_dict() for c in sorted(candidates, key=lambda c: (c.hero_story_score, c.story_score), reverse=True)]


def story_context(resources: list[dict]) -> dict:
    candidates = build_story_candidates(resources)
    hero = candidates[0] if candidates else {}
    return {
        "engine": STORY_ENGINE_VERSION,
        "hero_story": hero,
        "candidates": candidates,
        "selection_policy": "hero_story_score = story + specificity + evidence + headline + transformation + visual potential; fact/evidence isolation happens downstream",
    }


def story_arc(archetype: str, count: int) -> list[str]:
    base = list(STORY_ARCS.get(archetype) or STORY_ARCS["hidden_giant"])
    count = max(1, int(count))
    if count >= len(base):
        return base[:count]
    # Preserve hook and watch while sampling the middle in order.
    if count == 1:
        return ["hook"]
    if count == 2:
        return ["hook", "watch"]
    middle = base[1:-1]
    if count - 2 >= len(middle):
        return ["hook", *middle, "watch"]
    indexes = [round(i * (len(middle) - 1) / max(1, count - 3)) for i in range(count - 2)] if count > 3 else [0]
    chosen = []
    for idx in indexes:
        role = middle[idx]
        if role not in chosen:
            chosen.append(role)
    while len(chosen) < count - 2:
        for role in middle:
            if role not in chosen:
                chosen.append(role)
            if len(chosen) >= count - 2:
                break
    return ["hook", *chosen[: count - 2], "watch"]


def layout_for_story(archetype: str, index: int, seed: str) -> str:
    layouts = list(ARCHETYPE_LAYOUTS.get(archetype) or ARCHETYPE_LAYOUTS["hidden_giant"])
    digest = int(hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    offset = digest % len(layouts)
    return layouts[(offset + index) % len(layouts)]
