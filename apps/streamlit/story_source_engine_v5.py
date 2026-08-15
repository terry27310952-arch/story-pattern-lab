from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass


STORY_SOURCE_ENGINE_VERSION = "story-source-v10.1"
STORY_ENGINE_VERSION = STORY_SOURCE_ENGINE_VERSION

_GENERIC_ENTITY_NAMES = {
    "crypto", "editor", "reporter", "news", "market", "markets", "today", "global", "japan", "article",
    "breaking", "exclusive", "update", "updated", "analysis", "bitcoin", "ethereum", "btc", "eth", "etf",
    "company", "companies", "group", "holdings", "inc", "corp", "corporation", "limited", "ltd", "the", "this",
    "that", "what", "million", "billion", "trillion", "ai", "usd", "jpy", "mw", "gw",
}
_TITLE_STOPWORDS = {
    "bitcoin", "btc", "crypto", "market", "markets", "news", "today", "global", "japan", "update", "company",
    "companies", "deal", "report", "reports", "says", "said", "new", "after", "with", "from", "into", "over",
    "about", "仮想通貨", "暗号資産", "ビットコイン", "市場", "企業", "発表", "報道", "最新", "ニュース",
    "について", "可能性", "今後", "向け", "関連", "が", "を", "に", "へ", "と", "で", "の",
}

_EVENT_TERMS = [
    "contract", "agreement", "partnership", "acquire", "acquisition", "launch", "approve", "approval", "invest",
    "funding", "raise", "expand", "shift", "transition", "pivot", "ban", "rule", "regulation", "lawsuit", "hack",
    "breach", "collapse", "inflow", "outflow", "record", "契約", "提携", "買収", "承認", "開始", "参入", "拡大",
    "転換", "移行", "規制", "法案", "施行", "訴訟", "攻撃", "盗難", "流入", "流出", "過去最高", "更新",
]
_CHANGE_TERMS = [
    "change", "shift", "transition", "pivot", "expand", "conversion", "diversif", "restructure", "転換", "移行",
    "多角化", "拡大", "再編", "転用", "参入", "変更", "変化",
]
_CONFLICT_TERMS = ["but", "yet", "despite", "however", "while", "whereas", "一方", "しかし", "だが", "なのに", "対して"]
_VISUAL_TERMS = [
    "factory", "mine", "mining", "data center", "server", "power", "plant", "office", "building", "ship", "store",
    "document", "court", "police", "exchange", "fund", "工場", "採掘", "マイニング", "データセンター",
    "サーバー", "電力", "発電", "施設", "庁", "裁判", "取引所", "店舗", "企業", "人物",
]
_IMPLICATION_TERMS = [
    "valuation", "revenue", "profit", "market share", "price", "demand", "supply", "liquidity", "investor", "industry",
    "評価", "収益", "利益", "シェア", "価格", "需要", "供給", "流動性", "投資家", "業界", "市場",
]


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
    cluster_coherence: float
    event_fingerprint: str
    hero_resource: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: object, limit: int = 7000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _title(row: dict) -> str:
    return _clean(row.get("title") or row.get("short_title"), 360)


def _material(row: dict) -> str:
    return _clean(row.get("material") or row.get("full_material") or row.get("excerpt"), 9000)


def _sid(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _combined(row: dict) -> str:
    return f"{_title(row)} {_clean(row.get('tags'), 300)} {_material(row)}"


def _has(text: str, term: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9 .&+/_-]+", term):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, flags=re.I))
    return term in text


def _hits(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if _has(text, term))


def _numbers(text: str) -> list[str]:
    return re.findall(
        r"(?:\$|¥|￥)?\d[\d,.]*(?:\.\d+)?(?:\s?(?:%|billion|million|trillion|bn|mn|億|兆|万|円|ドル|MW|GW|年|か月|ヶ月))?",
        text,
        flags=re.I,
    )


def _japanese_text(value: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ヶ一-龥]", value or ""))


def _entity_details(row: dict) -> list[dict]:
    title = _title(row)
    lead = _material(row)[:2600]
    text = f"{title} {lead}"
    details: dict[str, dict] = {}

    for match in re.findall(r"\b(?:[A-Z][A-Za-z0-9.&'-]{1,})(?:\s+(?:[A-Z][A-Za-z0-9.&'-]{1,}|of|and|&)){0,3}\b", f"{title} {lead[:1200]}"):
        name = match.strip(" .,:;-_")
        parts = [part.strip(" .,:;-_").casefold() for part in name.split()]
        if len(name) < 3 or not parts or all(part in _GENERIC_ENTITY_NAMES for part in parts):
            continue
        if any(part in {"the", "this", "that", "what"} for part in parts):
            continue
        mentions = len(re.findall(re.escape(name), text, flags=re.I))
        title_bonus = 0.14 if name.casefold() in title.casefold() else 0.0
        confidence = min(0.95, 0.62 + min(0.18, mentions * 0.045) + title_bonus)
        if confidence >= 0.70:
            details[name.casefold()] = {"name": name, "type": "proper_noun", "confidence": round(confidence, 2), "mentions": mentions}

    for name in re.findall(r"(?<![A-Za-z])\b[A-Z]{2,8}\b(?![A-Za-z])", f"{title} {lead[:900]}"):
        if name.casefold() in _GENERIC_ENTITY_NAMES:
            continue
        mentions = len(re.findall(rf"\b{re.escape(name)}\b", text))
        confidence = min(0.93, 0.68 + min(0.15, mentions * 0.04) + (0.08 if name in title else 0.0))
        details.setdefault(name.casefold(), {"name": name, "type": "institution_or_symbol", "confidence": round(confidence, 2), "mentions": mentions})

    for chunk in re.split(r"[、,:：―—\-「」『』()（）\s]+", title):
        name = chunk.strip()
        if not (2 <= len(name) <= 30) or not _japanese_text(name):
            continue
        if any(stop in name.casefold() for stop in _TITLE_STOPWORDS if len(stop) >= 2):
            continue
        if re.fullmatch(r"[ぁ-んァ-ヶ一-龥]{2,30}", name):
            mentions = text.count(name)
            if mentions >= 2:
                confidence = min(0.90, 0.64 + min(0.16, mentions * 0.04) + 0.08)
                details.setdefault(name.casefold(), {"name": name, "type": "named_subject", "confidence": round(confidence, 2), "mentions": mentions})

    return sorted(details.values(), key=lambda item: (item["confidence"], item["mentions"], len(item["name"])), reverse=True)[:8]


def _entities(row: dict) -> list[str]:
    return [item["name"] for item in _entity_details(row) if item["confidence"] >= 0.72][:6]


def _component_scores(row: dict) -> dict:
    title = _title(row)
    text = _combined(row)
    number_count = len(_numbers(text))
    entity_details = _entity_details(row)
    entity_names = [str(item.get("name") or "") for item in entity_details if item.get("name")]
    event_hits = _hits(text, _EVENT_TERMS)
    change_hits = _hits(text, _CHANGE_TERMS)
    conflict_hits = _hits(text, _CONFLICT_TERMS)
    visual_hits = _hits(text, _VISUAL_TERMS)
    implication_hits = _hits(text, _IMPLICATION_TERMS)
    material_len = len(_material(row))

    title_has_entity = bool(entity_names and entity_names[0].casefold() in title.casefold())
    hook = min(100.0, 24 + min(30, event_hits * 11) + min(28, number_count * 4) + (12 if "?" in title or "？" in title else 0))
    conflict = min(100.0, conflict_hits * 28 + (18 if conflict_hits and number_count >= 2 else 0))
    character = min(100.0, 18 + len(entity_names) * 15 + (14 if title_has_entity else 0))
    change = min(100.0, 15 + change_hits * 25 + min(25, event_hits * 5))
    scale = min(100.0, 15 + min(75, number_count * 9))
    implication = min(100.0, 18 + implication_hits * 15 + min(22, event_hits * 4))
    visuality = min(100.0, 20 + visual_hits * 16 + min(20, len(entity_names) * 4))
    evidence = min(100.0, 20 + min(38, material_len / 65) + min(34, number_count * 5) + (8 if row.get("source_type") == "official" else 0))
    novelty = min(100.0, 20 + min(40, event_hits * 9) + min(30, change_hits * 11))

    return {
        "story_hook_score": round(hook, 2), "conflict_score": round(conflict, 2), "character_score": round(character, 2),
        "change_score": round(change, 2), "scale_score": round(scale, 2), "market_implication_score": round(implication, 2),
        "visuality_score": round(visuality, 2), "evidence_story_score": round(evidence, 2), "novelty_score": round(novelty, 2),
    }


def annotate_resource(row: dict) -> dict:
    item = dict(row or {})
    scores = _component_scores(item)
    item.update(scores)
    item["story_score"] = round(
        scores["story_hook_score"] * 0.15 + scores["conflict_score"] * 0.10 + scores["character_score"] * 0.10
        + scores["change_score"] * 0.15 + scores["scale_score"] * 0.10 + scores["market_implication_score"] * 0.15
        + scores["visuality_score"] * 0.10 + scores["evidence_story_score"] * 0.10 + scores["novelty_score"] * 0.05,
        2,
    )
    details = _entity_details(item)
    item["story_entity_details"] = details
    item["story_entities"] = [d["name"] for d in details if d["confidence"] >= 0.72][:6]
    item["story_topic"] = item["story_entities"][0] if item["story_entities"] else _title(item)[:90]
    item["story_archetype_hint"] = "dynamic"
    item["editorial_score"] = round(item["story_score"] * 0.82 + float(item.get("trader_score") or 0) * 0.18, 2)
    item["event_fingerprint"] = event_fingerprint(item)
    return item


def annotate_resources(resources: list[dict]) -> list[dict]:
    rows = [annotate_resource(dict(row)) for row in resources or [] if isinstance(row, dict)]
    return sorted(rows, key=lambda r: (float(r.get("story_score") or 0), float(r.get("editorial_score") or 0)), reverse=True)


def _title_tokens(row: dict) -> set[str]:
    text = _title(row).casefold()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9.&+/_-]{2,}|[ァ-ヶー一-龥]{2,}", text, flags=re.I))
    out = set()
    for token in tokens:
        cleaned = token.strip(" .,:;!?！？()[]{}'\"")
        if not cleaned or cleaned in _TITLE_STOPWORDS:
            continue
        if cleaned.isdigit() and len(cleaned) < 3:
            continue
        out.add(cleaned)
    return out


def _number_tokens(row: dict) -> set[str]:
    values = _numbers(f"{_title(row)} {_material(row)[:2200]}")
    out = set()
    for value in values:
        norm = re.sub(r"\s+|,", "", value).casefold()
        if norm and norm not in {"1", "2", "3", "4", "5"}:
            out.add(norm)
    return out


def _entity_tokens(row: dict) -> set[str]:
    details = row.get("story_entity_details") or _entity_details(row)
    return {str(item.get("name") or "").casefold() for item in details if float(item.get("confidence") or 0) >= 0.78 and item.get("name")}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def event_similarity(a: dict, b: dict) -> float:
    if _sid(a) and _sid(a) == _sid(b):
        return 1.0
    if a.get("url") and a.get("url") == b.get("url"):
        return 1.0
    ta, tb = _title_tokens(a), _title_tokens(b)
    ea, eb = _entity_tokens(a), _entity_tokens(b)
    na, nb = _number_tokens(a), _number_tokens(b)
    title_sim = _jaccard(ta, tb)
    entity_sim = _jaccard(ea, eb)
    number_sim = _jaccard(na, nb)
    shared_entities = ea & eb
    if len(shared_entities) >= 2:
        gate = True
    elif len(shared_entities) == 1:
        gate = title_sim >= 0.15 or number_sim >= 0.22
    else:
        gate = title_sim >= 0.60
    if not gate:
        return 0.0
    return round(min(1.0, entity_sim * 0.53 + title_sim * 0.32 + number_sim * 0.15), 4)


def event_fingerprint(row: dict) -> str:
    payload = "|".join([*sorted(_entity_tokens(row))[:4], *sorted(_title_tokens(row))[:8], *sorted(_number_tokens(row))[:6]])
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


def cluster_story_candidates(resources: list[dict], similarity_threshold: float = 0.47) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for row in annotate_resources(resources):
        best_idx, best_score = -1, 0.0
        for idx, cluster in enumerate(clusters):
            comparisons = [event_similarity(row, cluster[0])]
            if len(cluster) > 1:
                comparisons.append(max(event_similarity(row, other) for other in cluster[1:3]))
            score = min(comparisons) if len(comparisons) > 1 else comparisons[0]
            if score > best_score:
                best_idx, best_score = idx, score
        if best_idx >= 0 and best_score >= similarity_threshold:
            clusters[best_idx].append(row)
        else:
            clusters.append([row])
    return clusters


def _coherence(cluster: list[dict]) -> float:
    if len(cluster) <= 1:
        return 1.0
    hero = cluster[0]
    return round(min(event_similarity(hero, row) for row in cluster[1:]), 4)


def _hero_score(row: dict, cluster_size: int, coherence: float) -> float:
    scores = _component_scores(row)
    specificity = min(100.0, scores["character_score"] * 0.45 + scores["scale_score"] * 0.30 + scores["evidence_story_score"] * 0.25)
    corroboration = min(8.0, max(0, cluster_size - 1) * 2.0) * coherence
    score = float(row.get("story_score") or 0) * 0.62 + specificity * 0.28 + scores["visuality_score"] * 0.10 + corroboration
    return round(min(100.0, score), 2)


def build_story_candidates(resources: list[dict]) -> list[dict]:
    candidates: list[StoryCandidate] = []
    for raw_cluster in cluster_story_candidates(resources):
        cluster = sorted(raw_cluster, key=lambda r: float(r.get("story_score") or 0), reverse=True)
        hero = cluster[0]
        coherence = _coherence(cluster)
        ids = [_sid(r) for r in cluster if _sid(r)]
        candidate_id = "story_" + hashlib.sha1("|".join(ids).encode("utf-8", errors="ignore")).hexdigest()[:12]
        entities = list(hero.get("story_entities") or _entities(hero))
        title = _title(hero)
        candidates.append(StoryCandidate(
            id=candidate_id,
            topic=str(hero.get("story_topic") or (entities[0] if entities else title[:90])),
            archetype="dynamic",
            entities=entities,
            entity_details=list(hero.get("story_entity_details") or _entity_details(hero)),
            resource_ids=ids,
            source_names=list(dict.fromkeys(str(r.get("source") or "") for r in cluster if r.get("source")))[:5],
            headline_seed=title,
            headline_ja=title if _japanese_text(title) else "",
            why_now_ja="", conflict_ja="", implication_ja="", visual_motifs=[],
            story_score=round(float(hero.get("story_score") or 0), 2),
            hero_story_score=_hero_score(hero, len(cluster), coherence),
            confidence=round(min(0.98, 0.70 + len(entities) * 0.035 + (0.07 if coherence >= 0.75 else 0.0)), 2),
            cluster_size=len(cluster), cluster_coherence=coherence, event_fingerprint=event_fingerprint(hero), hero_resource=hero,
        ))
    return [c.to_dict() for c in sorted(candidates, key=lambda c: (c.hero_story_score, c.story_score), reverse=True)]


def story_context(resources: list[dict]) -> dict:
    candidates = build_story_candidates(resources)
    return {
        "engine": STORY_SOURCE_ENGINE_VERSION,
        "hero_story": candidates[0] if candidates else {},
        "candidates": candidates,
        "selection_policy": "generic narrative score -> same-event clustering -> hero specificity/corroboration; no article or archetype templates",
    }
