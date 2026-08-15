from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

import story_engine_v3 as legacy


STORY_ENGINE_VERSION = "story-engine-v9.0"
ARCHETYPES = set(legacy.ARCHETYPES)
STORY_ARCS = dict(legacy.STORY_ARCS)
ARCHETYPE_LAYOUTS = dict(legacy.ARCHETYPE_LAYOUTS)

_GENERIC_ENTITY_NAMES = {
    "crypto", "crypto.", "editor", "reporter", "news", "market", "markets", "today", "global",
    "japan", "coin", "article", "breaking", "exclusive", "update", "updated", "analysis", "that",
    "what", "back", "million", "billion", "bitcoin", "ethereum", "btc", "eth", "etf", "ai",
}
_TITLE_STOPWORDS = {
    "bitcoin", "btc", "crypto", "market", "markets", "news", "today", "global", "japan", "update",
    "updated", "company", "companies", "deal", "report", "reports", "says", "said", "new", "after",
    "with", "from", "into", "over", "about", "仮想通貨", "暗号資産", "ビットコイン", "市場", "企業",
    "発表", "報道", "最新", "ニュース", "について", "可能性", "今後", "向け", "関連",
}


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
    return _clean(row.get("title") or row.get("short_title"), 320)


def _sid(row: dict) -> str:
    return str(row.get("id") or row.get("source_id") or row.get("url") or "")


def _safe_entity_details(row: dict) -> list[dict]:
    details = []
    for item in legacy._entity_details(row):
        name = _clean(item.get("name"), 100)
        low = name.lower().strip(" .,:;-_")
        if not name or low in _GENERIC_ENTITY_NAMES:
            continue
        if any(part.lower().strip(" .,:;-_") in _GENERIC_ENTITY_NAMES for part in name.split()):
            continue
        kind = str(item.get("type") or "proper_noun")
        confidence = float(item.get("confidence") or 0)
        mentions = int(item.get("mentions") or 0)
        if kind == "proper_noun" and not (confidence >= 0.82 and (mentions >= 2 or name.lower() in _title(row).lower())):
            continue
        details.append({"name": name, "type": kind, "confidence": round(confidence, 2), "mentions": mentions})
    # Keep one canonical row per entity name.
    unique: dict[str, dict] = {}
    for item in details:
        key = item["name"].casefold()
        if key not in unique or item["confidence"] > unique[key]["confidence"]:
            unique[key] = item
    return sorted(unique.values(), key=lambda x: (x["confidence"], x["mentions"]), reverse=True)[:6]


def _entities(row: dict) -> list[str]:
    return [item["name"] for item in _safe_entity_details(row) if float(item.get("confidence") or 0) >= 0.76][:5]


def annotate_resource(row: dict) -> dict:
    item = legacy.annotate_resource(row)
    details = _safe_entity_details(item)
    item["story_entity_details"] = details
    item["story_entities"] = [d["name"] for d in details if d["confidence"] >= 0.76][:5]
    if item["story_entities"]:
        item["story_topic"] = item["story_entities"][0]
    item["event_fingerprint"] = event_fingerprint(item)
    return item


def annotate_resources(resources: list[dict]) -> list[dict]:
    rows = [annotate_resource(dict(row)) for row in resources or [] if isinstance(row, dict)]
    return sorted(rows, key=lambda r: (float(r.get("editorial_score") or 0), float(r.get("story_score") or 0)), reverse=True)


def classify_archetype(row: dict) -> str:
    return legacy.classify_archetype(row)


def _title_tokens(row: dict) -> set[str]:
    text = _title(row).lower()
    tokens = set(re.findall(r"[a-z0-9][a-z0-9.&+-]{2,}|[ァ-ヶー一-龥]{2,}", text, flags=re.I))
    out: set[str] = set()
    for token in tokens:
        cleaned = token.strip(" .,:;!?！？()[]{}'\"")
        if not cleaned or cleaned in _TITLE_STOPWORDS:
            continue
        if cleaned.isdigit() and len(cleaned) < 3:
            continue
        out.add(cleaned)
    return out


def _numbers(row: dict) -> set[str]:
    text = f"{_title(row)} {_clean(row.get('material') or row.get('excerpt'), 1800)}"
    raw = re.findall(r"(?:\$|約)?\s?\d[\d,.]*(?:\s?(?:%|billion|million|trillion|bn|mn|億|兆|万|mw|gw|年))?", text, flags=re.I)
    out = set()
    for value in raw:
        norm = re.sub(r"\s+", "", value).lower().replace(",", "")
        if norm in {"1", "2", "3", "4", "5", "2026"}:
            continue
        out.add(norm)
    return out


def _core_entities(row: dict) -> set[str]:
    return {
        str(item.get("name") or "").casefold()
        for item in row.get("story_entity_details") or _safe_entity_details(row)
        if float(item.get("confidence") or 0) >= 0.82
        and str(item.get("name") or "").casefold() not in _GENERIC_ENTITY_NAMES
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def event_similarity(a: dict, b: dict) -> float:
    """Return same-event confidence, not broad topical similarity.

    Sharing a publisher, BTC, AI, or crypto is never enough. We require either a
    concrete shared entity plus event detail, or very high title overlap.
    """
    if _sid(a) and _sid(a) == _sid(b):
        return 1.0
    ua, ub = str(a.get("url") or ""), str(b.get("url") or "")
    if ua and ub and ua == ub:
        return 1.0

    ta, tb = _title_tokens(a), _title_tokens(b)
    ea, eb = _core_entities(a), _core_entities(b)
    na, nb = _numbers(a), _numbers(b)
    title_sim = _jaccard(ta, tb)
    entity_sim = _jaccard(ea, eb)
    number_sim = _jaccard(na, nb)
    shared_entities = ea & eb

    # Hard gate. A broad category or same publisher cannot create a cluster.
    if len(shared_entities) >= 2:
        gate = True
    elif len(shared_entities) == 1:
        gate = title_sim >= 0.16 or number_sim >= 0.24
    else:
        gate = title_sim >= 0.58
    if not gate:
        return 0.0

    archetype_bonus = 0.05 if str(a.get("story_archetype_hint")) == str(b.get("story_archetype_hint")) else 0.0
    score = entity_sim * 0.52 + title_sim * 0.31 + number_sim * 0.17 + archetype_bonus
    return round(min(1.0, score), 4)


def event_fingerprint(row: dict) -> str:
    entities = sorted(_core_entities(row))[:3]
    tokens = sorted(_title_tokens(row))[:8]
    numbers = sorted(_numbers(row))[:5]
    payload = "|".join([str(row.get("story_archetype_hint") or classify_archetype(row)), *entities, *tokens, *numbers])
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


def cluster_story_candidates(resources: list[dict], similarity_threshold: float = 0.47) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for row in annotate_resources(resources):
        best_idx = -1
        best_score = 0.0
        for idx, cluster in enumerate(clusters):
            # Compare with the cluster hero and one corroborating member. A single
            # accidental pair may not pull an unrelated article into the cluster.
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


def cluster_coherence(cluster: list[dict]) -> float:
    if len(cluster) <= 1:
        return 1.0
    hero = cluster[0]
    scores = [event_similarity(hero, row) for row in cluster[1:]]
    return round(min(scores) if scores else 1.0, 4)


def _hero_score(row: dict, cluster_size: int, coherence: float) -> float:
    base = legacy._hero_score(row, cluster_size)
    # Corroboration only helps when the cluster is actually the same event.
    if cluster_size > 1:
        base += max(-12.0, min(5.0, (coherence - 0.70) * 20.0))
    return round(max(0.0, min(100.0, base)), 2)


def build_story_candidates(resources: list[dict]) -> list[dict]:
    candidates: list[StoryCandidate] = []
    for raw_cluster in cluster_story_candidates(resources):
        cluster = sorted(raw_cluster, key=lambda r: float(r.get("story_score") or 0), reverse=True)
        hero = cluster[0]
        archetype = str(hero.get("story_archetype_hint") or classify_archetype(hero))
        coherence = cluster_coherence(cluster)
        rid = [_sid(r) for r in cluster if _sid(r)]
        cid = "story_" + hashlib.sha1("|".join(rid + [archetype]).encode("utf-8", errors="ignore")).hexdigest()[:12]
        entities = list(hero.get("story_entities") or _entities(hero))
        candidate = StoryCandidate(
            id=cid,
            topic=str(hero.get("story_topic") or (entities[0] if entities else "STORY")),
            archetype=archetype,
            entities=entities,
            entity_details=list(hero.get("story_entity_details") or _safe_entity_details(hero)),
            resource_ids=rid,
            source_names=list(dict.fromkeys(str(r.get("source") or "") for r in cluster if r.get("source")))[:5],
            headline_seed=_title(hero),
            headline_ja=legacy._headline_ja(hero, archetype),
            why_now_ja=legacy._why_now(archetype, hero),
            conflict_ja=legacy._conflict(archetype),
            implication_ja=legacy._implication(archetype),
            visual_motifs=list(hero.get("story_visual_motifs") or legacy._visual_motifs(hero, archetype)),
            story_score=round(float(hero.get("story_score") or 0), 2),
            hero_story_score=_hero_score(hero, len(cluster), coherence),
            confidence=round(min(0.99, 0.72 + len(entities) * 0.035 + (0.06 if coherence >= 0.75 else 0.0)), 2),
            cluster_size=len(cluster),
            cluster_coherence=coherence,
            event_fingerprint=event_fingerprint(hero),
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
        "selection_policy": "same-event clustering first; hero_score second; evidence may only come from the coherent hero cluster",
    }


def story_arc(archetype: str, count: int) -> list[str]:
    return legacy.story_arc(archetype, count)


def layout_for_story(archetype: str, index: int, seed: str) -> str:
    return legacy.layout_for_story(archetype, index, seed)
