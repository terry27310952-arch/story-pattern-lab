from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from typing import Iterable


STORY_ENGINE_VERSION = "story-engine-v7.0"

ARCHETYPES = {
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

STORY_ARCS: dict[str, list[str]] = {
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

ARCHETYPE_LAYOUTS: dict[str, list[str]] = {
    "contradiction": ["poster_center", "split_left", "data_monument", "newspaper_panel", "split_top", "full_bleed_bottom", "top_caption"],
    "hidden_giant": ["full_bleed_bottom", "poster_center", "split_left", "data_monument", "newspaper_panel", "split_top", "top_caption"],
    "origin_to_now": ["poster_center", "split_top", "newspaper_panel", "split_left", "data_monument", "full_bleed_bottom", "top_caption"],
    "money_flow": ["data_monument", "split_left", "full_bleed_bottom", "split_top", "poster_center", "newspaper_panel", "top_caption"],
    "power_shift": ["poster_center", "split_left", "newspaper_panel", "data_monument", "full_bleed_bottom", "split_top", "top_caption"],
    "policy_change": ["newspaper_panel", "poster_center", "split_left", "top_caption", "data_monument", "full_bleed_bottom", "split_top"],
    "historical_parallel": ["newspaper_panel", "split_left", "poster_center", "split_top", "data_monument", "full_bleed_bottom", "top_caption"],
    "crisis_or_risk": ["poster_center", "newspaper_panel", "split_left", "data_monument", "split_top", "full_bleed_bottom", "top_caption"],
    "opportunity_window": ["full_bleed_bottom", "poster_center", "split_left", "data_monument", "split_top", "newspaper_panel", "top_caption"],
}

HOOK_WORDS = [
    "why", "how", "unexpected", "secret", "hidden", "record", "first", "only", "never",
    "なぜ", "初", "過去最高", "史上", "異例", "急増", "急落", "秘密",
]
CONFLICT_WORDS = [
    "but", "yet", "despite", "while", "versus", "vs", "although", "however", "paradox",
    "しかし", "一方", "なのに", "にもかかわらず", "反対", "逆", "対立",
]
CHANGE_WORDS = [
    "rise", "fall", "surge", "drop", "shift", "change", "turn", "launch", "approval", "ban", "buy", "sell",
    "acquire", "expand", "cut", "increase", "decrease", "new", "record", "first", "return", "collapse",
    "上昇", "下落", "急増", "急減", "転換", "変更", "開始", "承認", "禁止", "買収", "拡大", "縮小", "新",
]
MARKET_IMPLICATION_WORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "etf", "market", "liquidity", "yield", "rate", "fed", "boj",
    "sec", "regulation", "stablecoin", "exchange", "institution", "treasury", "reserve", "supply", "demand",
    "stocks", "equity", "s&p", "nasdaq", "valuation", "earnings", "capes", "cape",
    "ビットコイン", "暗号資産", "市場", "流動性", "金利", "規制", "取引所", "機関", "準備金", "供給", "需要",
]
VISUAL_WORDS = [
    "factory", "office", "exchange", "wall street", "tokyo", "bank", "building", "data center", "mine", "server",
    "ceo", "founder", "president", "chair", "court", "parliament", "congress", "warehouse", "fund", "trading desk",
    "archive", "1929", "2000", "newspaper", "chart", "index",
    "工場", "取引所", "東京", "銀行", "データセンター", "鉱山", "サーバー", "社長", "創業者", "議会", "倉庫",
]

ENTITY_DISPLAY = {
    "blackrock": "BlackRock",
    "fidelity": "Fidelity",
    "microstrategy": "MicroStrategy",
    "strategy": "Strategy",
    "metaplanet": "Metaplanet",
    "binance": "Binance",
    "coinbase": "Coinbase",
    "bitget": "Bitget",
    "bybit": "Bybit",
    "sec": "SEC",
    "cftc": "CFTC",
    "fed": "Fed",
    "federal reserve": "Federal Reserve",
    "boj": "BOJ",
    "bank of japan": "Bank of Japan",
    "jpmorgan": "JPMorgan",
    "goldman": "Goldman Sachs",
    "softbank": "SoftBank",
    "sbi": "SBI",
    "trump": "Trump",
    "powell": "Powell",
    "changpeng zhao": "Changpeng Zhao",
    "cz": "CZ",
    "michael saylor": "Michael Saylor",
    "saylor": "Saylor",
    "vitalik": "Vitalik Buterin",
    "buterin": "Vitalik Buterin",
    "wall street": "Wall Street",
    "robert shiller": "Robert Shiller",
    "shiller": "Shiller",
    "s&p 500": "S&P 500",
    "nasdaq": "Nasdaq",
}
ENTITY_HINTS = list(ENTITY_DISPLAY)

POLICY_WORDS = ["regulation", "law", "tax", "sec", "cftc", "policy", "rule", "approval", "規制", "法律", "税制", "政策", "承認"]
FLOW_WORDS = ["flow", "inflow", "outflow", "fund", "etf", "buying", "purchase", "treasury", "reserve", "資金", "流入", "流出", "購入", "保有"]
CRISIS_WORDS = ["hack", "exploit", "liquidation", "bankrupt", "collapse", "attack", "scam", "freeze", "ハック", "破綻", "清算", "攻撃", "詐欺"]
HISTORY_WORDS = ["history", "historical", "since", "years ago", "decade", "oldest", "1929", "2000", "dot-com", "dotcom", "cape", "shiller", "歴史", "以来", "年前", "過去"]
POWER_WORDS = ["market share", "dominance", "acquire", "takeover", "rival", "challenger", "lead", "power", "シェア", "覇権", "買収", "競争", "主導"]
ORIGIN_WORDS = ["founded", "started", "began", "origin", "創業", "始ま", "起源", "設立"]
OPPORTUNITY_WORDS = ["launch", "approval", "adoption", "open", "access", "opportunity", "開始", "承認", "採用", "解禁", "機会"]

PROPER_STOPWORDS = {
    "The", "This", "That", "These", "Those", "Only", "What", "Why", "How", "When", "Where", "Who",
    "Market", "Markets", "Today", "Now", "After", "Before", "While", "Despite", "With", "Without", "From",
    "Into", "Over", "Under", "Could", "Would", "Should", "Will", "Has", "Have", "Had", "New", "Record",
}


@dataclass
class StoryCandidate:
    id: str
    topic: str
    archetype: str
    entities: list[str]
    resource_ids: list[str]
    source_names: list[str]
    headline_seed: str
    headline_ja: str
    why_now_ja: str
    conflict_ja: str
    implication_ja: str
    visual_motifs: list[str]
    story_score: float
    confidence: float
    cluster_size: int
    hero_resource: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: object, limit: int = 5000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _title(row: dict) -> str:
    return _clean(row.get("title") or row.get("short_title"), 300)


def _material(row: dict) -> str:
    return _clean(row.get("material") or row.get("full_material") or row.get("excerpt"), 7000)


def _combined(row: dict) -> str:
    return f"{_title(row)} {_clean(row.get('tags'), 300)} {_material(row)[:3500]}"


def _term_pattern(term: str) -> str:
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9 .&+/-]+", term):
        return rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    return escaped


def _term_present(text: str, term: str) -> bool:
    return bool(re.search(_term_pattern(term), text, flags=re.I))


def _hits(text: str, words: Iterable[str]) -> int:
    return sum(1 for word in words if _term_present(text, word))


def _score_from_hits(count: int, base: float = 18.0, cap: float = 100.0) -> float:
    if count <= 0:
        return 0.0
    return min(cap, base + math.log2(count + 1) * 27.0)


def _scale_score(text: str) -> float:
    numeric = re.findall(r"(?:\$|¥|￥)?\d[\d,.]*(?:\s?(?:%|billion|million|trillion|bn|mn|億|兆|万|ドル|円))?", text, flags=re.I)
    strong = [m for m in numeric if any(unit in m.lower() for unit in ["%", "billion", "million", "trillion", "bn", "mn", "億", "兆", "万", "$", "¥", "￥"])]
    if strong:
        return min(100.0, 48.0 + len(strong) * 14.0)
    if numeric:
        return min(60.0, 22.0 + len(numeric) * 5.0)
    return 0.0


def _clean_proper_match(value: str) -> str:
    parts = value.split()
    while parts and parts[-1] in PROPER_STOPWORDS:
        parts.pop()
    while parts and parts[0] in PROPER_STOPWORDS:
        parts.pop(0)
    return " ".join(parts).strip()


def _entity_list(text: str) -> list[str]:
    entities: list[str] = []
    for hint in ENTITY_HINTS:
        if _term_present(text, hint):
            display = ENTITY_DISPLAY[hint]
            if display not in entities:
                entities.append(display)
    for match in re.findall(r"\b(?:[A-Z][A-Za-z0-9.&-]{2,})(?:\s+[A-Z][A-Za-z0-9.&-]{2,}){0,2}\b", text):
        cleaned = _clean_proper_match(match)
        if len(cleaned) < 3 or cleaned.upper() in {"BTC", "ETH", "ETF", "USD"}:
            continue
        if cleaned not in entities:
            entities.append(cleaned)
        if len(entities) >= 7:
            break
    return entities[:7]


def _visual_motifs(text: str, archetype: str) -> list[str]:
    motifs: list[str] = []
    mapping = [
        (["1929", "2000", "cape", "shiller", "historical", "history"], "archival Wall Street valuation history"),
        (["etf", "fund", "flow", "treasury", "reserve", "資金"], "institutional capital flow"),
        (["sec", "cftc", "law", "tax", "regulation", "policy", "規制", "政策"], "official policy document and regulator"),
        (["exchange", "binance", "coinbase", "取引所"], "exchange infrastructure"),
        (["bank", "fed", "boj", "銀行", "金利"], "central bank and financial district"),
        (["mine", "miner", "mining", "鉱山", "マイニング"], "industrial mining infrastructure"),
        (["server", "data center", "データセンター"], "data center and server rows"),
        (["ceo", "founder", "president", "創業者", "社長"], "executive documentary portrait"),
    ]
    for words, motif in mapping:
        if any(_term_present(text, word) for word in words) and motif not in motifs:
            motifs.append(motif)
    defaults = {
        "contradiction": "opposing evidence in one market story",
        "hidden_giant": "large industrial or institutional environment",
        "origin_to_now": "archive-to-present transformation",
        "money_flow": "capital moving between institutions and market",
        "power_shift": "two institutions with shifting balance",
        "policy_change": "official document and affected market participants",
        "historical_parallel": "archive imagery contrasted with present valuation data",
        "crisis_or_risk": "infrastructure under stress and contagion map",
        "opportunity_window": "new access point into an institutional market",
    }
    default = defaults.get(archetype)
    if default and default not in motifs:
        motifs.append(default)
    return motifs[:3]


def _story_components(row: dict) -> dict:
    text = _combined(row)
    title = _title(row)
    material_len = len(_material(row))
    entities = _entity_list(f"{title} {_material(row)[:1800]}")
    hook = min(100.0, _score_from_hits(_hits(title, HOOK_WORDS), 24) + (12 if re.search(r"\d", title) else 0))
    conflict = min(100.0, _score_from_hits(_hits(text, CONFLICT_WORDS), 17))
    character = min(100.0, len(entities) * 18.0 + (12 if _hits(text, ["ceo", "founder", "president", "chair", "社長", "創業者"]) else 0))
    change = min(100.0, _score_from_hits(_hits(text, CHANGE_WORDS), 15))
    scale = _scale_score(text)
    implication = min(100.0, _score_from_hits(_hits(text, MARKET_IMPLICATION_WORDS), 20))
    visuality = min(100.0, _score_from_hits(_hits(text, VISUAL_WORDS), 15) + min(25.0, len(entities) * 5.0))
    evidence = 25.0 + (15 if material_len >= 240 else 0) + (25 if material_len >= 800 else 0) + (15 if material_len >= 1800 else 0)
    if row.get("source_type") in {"rss", "media", "official"}:
        evidence += 10
    evidence = min(100.0, evidence)
    novelty = min(100.0, _score_from_hits(_hits(text, ["first", "record", "unprecedented", "初", "過去最高", "異例"]), 12))
    return {
        "story_hook_score": round(hook, 1),
        "conflict_score": round(conflict, 1),
        "character_score": round(character, 1),
        "change_score": round(change, 1),
        "scale_score": round(scale, 1),
        "market_implication_score": round(implication, 1),
        "visuality_score": round(visuality, 1),
        "evidence_story_score": round(evidence, 1),
        "novelty_score": round(novelty, 1),
    }


def classify_archetype(row: dict, components: dict | None = None) -> str:
    text = _combined(row)
    components = components or _story_components(row)
    if _hits(text, CRISIS_WORDS) >= 1:
        return "crisis_or_risk"
    if _hits(text, POLICY_WORDS) >= 2:
        return "policy_change"
    if _hits(text, FLOW_WORDS) >= 2:
        return "money_flow"
    if _hits(text, POWER_WORDS) >= 2:
        return "power_shift"
    if _hits(text, HISTORY_WORDS) >= 2 or (re.search(r"\b(?:18|19|20)\d{2}\b", text) and _hits(text, ["cape", "valuation", "history", "historical"])):
        return "historical_parallel"
    if _hits(text, ORIGIN_WORDS) >= 2 and components.get("change_score", 0) >= 35:
        return "origin_to_now"
    if components.get("conflict_score", 0) >= 45:
        return "contradiction"
    if _hits(text, OPPORTUNITY_WORDS) >= 2:
        return "opportunity_window"
    if components.get("character_score", 0) >= 50 and components.get("scale_score", 0) >= 35:
        return "hidden_giant"
    return "contradiction" if components.get("conflict_score", 0) >= 25 else "opportunity_window"


def _topic_label(row: dict) -> str:
    tags = [part.strip() for part in str(row.get("tags") or "").split(",") if part.strip()]
    if tags:
        return "/".join(tags[:2])
    entities = _entity_list(_title(row) + " " + _material(row)[:700])
    return entities[0] if entities else "MARKET"


def annotate_resource(row: dict) -> dict:
    item = dict(row or {})
    components = _story_components(item)
    archetype = classify_archetype(item, components)
    weighted = (
        components["story_hook_score"] * 0.15
        + components["conflict_score"] * 0.15
        + components["character_score"] * 0.10
        + components["change_score"] * 0.15
        + components["scale_score"] * 0.10
        + components["market_implication_score"] * 0.15
        + components["visuality_score"] * 0.10
        + components["evidence_story_score"] * 0.07
        + components["novelty_score"] * 0.03
    )
    risk = float(item.get("risk_score") or 0.0)
    quality_penalty = max(0.0, min(18.0, (risk - 35.0) * 0.25))
    story_score = max(0.0, min(100.0, weighted - quality_penalty))
    item.update(components)
    item["story_score"] = round(story_score, 2)
    item["story_archetype_hint"] = archetype
    item["story_entities"] = _entity_list(_title(item) + " " + _material(item)[:1800])
    item["story_topic"] = _topic_label(item)
    item["story_visual_motifs"] = _visual_motifs(_combined(item), archetype)
    item["editorial_score"] = round(story_score * 0.82 + float(item.get("trader_score") or 0.0) * 0.18, 2)
    return item


def annotate_resources(resources: list[dict]) -> list[dict]:
    rows = [annotate_resource(row) for row in (resources or []) if isinstance(row, dict)]
    return sorted(rows, key=lambda row: (float(row.get("story_score") or 0), float(row.get("trader_score") or 0)), reverse=True)


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]{3,}|[ァ-ヶ一-龥]{2,}", text.lower())
    stop = {"bitcoin", "btc", "crypto", "market", "news", "today", "ビットコイン", "暗号資産"}
    return {token for token in tokens if token not in stop}


def _similarity(left: dict, right: dict) -> float:
    lt = _tokenize(_title(left))
    rt = _tokenize(_title(right))
    if not lt or not rt:
        return 0.0
    jaccard = len(lt & rt) / max(1, len(lt | rt))
    le = set(left.get("story_entities") or [])
    re_ = set(right.get("story_entities") or [])
    entity_overlap = len(le & re_) / max(1, len(le | re_)) if le or re_ else 0.0
    same_hint = 0.12 if left.get("story_archetype_hint") == right.get("story_archetype_hint") else 0.0
    return jaccard * 0.70 + entity_overlap * 0.18 + same_hint


def cluster_story_candidates(resources: list[dict], similarity_threshold: float = 0.34) -> list[list[dict]]:
    annotated = annotate_resources(resources)
    clusters: list[list[dict]] = []
    for row in annotated:
        best_index, best_score = -1, 0.0
        for index, cluster in enumerate(clusters):
            score = max((_similarity(row, other) for other in cluster[:4]), default=0.0)
            if score > best_score:
                best_index, best_score = index, score
        if best_index >= 0 and best_score >= similarity_threshold:
            clusters[best_index].append(row)
        else:
            clusters.append([row])
    return clusters


def _cluster_archetype(cluster: list[dict]) -> str:
    votes: dict[str, float] = {}
    for row in cluster:
        key = str(row.get("story_archetype_hint") or "opportunity_window")
        votes[key] = votes.get(key, 0.0) + max(1.0, float(row.get("story_score") or 0))
    return max(votes, key=votes.get) if votes else "opportunity_window"


def _years(row: dict) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\b(?:18|19|20)\d{2}\b", _combined(row))))[:4]


def _headline_ja(hero: dict, archetype: str) -> str:
    supplied = _clean(hero.get("display_headline_ja"), 70)
    if supplied and supplied not in {"BTC材料を価格で確認", "市場材料を確認"}:
        return supplied
    entity = (hero.get("story_entities") or [""])[0]
    topic = hero.get("story_topic") or "市場"
    years = _years(hero)
    if archetype == "historical_parallel" and len(years) >= 2:
        return f"{years[0]}年と{years[1]}年。いま再び同じ警戒線へ。"
    if archetype == "money_flow":
        return f"{entity or topic}に資金は入った。価格は追いついたか。"
    if archetype == "policy_change":
        return f"{entity or topic}をめぐるルールが変わる。"
    if archetype == "crisis_or_risk":
        return f"{entity or topic}の異変。どこまで波及する？"
    if archetype == "power_shift":
        return f"主導権が動く。{entity or topic}の次に来るのは誰か。"
    if archetype == "origin_to_now":
        return f"小さく始まった{entity or topic}が、いま市場を動かす。"
    if archetype == "hidden_giant":
        return f"目立たない{entity or topic}が、市場の重要地点を握っている。"
    if archetype == "contradiction":
        return "数字と反応が噛み合わない。そのズレが今日の主役。"
    return f"{entity or topic}で、新しい入口が開いている。"


def _why_now_ja(archetype: str, hero: dict) -> str:
    years = _years(hero)
    if archetype == "historical_parallel" and len(years) >= 2:
        return f"資料は現在の状況を{years[0]}年と{years[1]}年の局面と比較している。似た形より、同じ指標がどこまで重なるかを見る。"
    mapping = {
        "money_flow": "見出しより、資金がどこから入り、価格にどこまで伝わったかを見る。",
        "policy_change": "発表内容より、誰の行動がいつ変わるのかが市場への影響を決める。",
        "crisis_or_risk": "最初の事故より、露出先と二次波及を切り分ける必要がある。",
        "power_shift": "主導権が移ると、同じ材料でも資金経路と反応速度が変わる。",
        "origin_to_now": "小さな変化が、現在の資金や市場構造にどうつながったかを見る。",
        "hidden_giant": "知名度ではなく、実際に何を握っているかを見る。",
        "opportunity_window": "入口が開いた直後は期待より、実際の参加者と資金の定着を見る。",
        "contradiction": "相反する事実が同時に出る時ほど、次に確認すべき条件が明確になる。",
    }
    return mapping.get(archetype, "確認できた事実から、次に変わる条件を追う。")


def _conflict_ja(archetype: str) -> str:
    return {
        "money_flow": "資金流入と価格反応が一致しているとは限らない。",
        "policy_change": "好材料でも、適用範囲と時期がずれれば実際の資金移動は遅れる。",
        "crisis_or_risk": "被害規模と市場全体のリスクは同じではない。",
        "power_shift": "シェアが動いても、利益と価格が同時に動くとは限らない。",
        "historical_parallel": "同じ指標が似た水準でも、同じ値動きを意味するわけではない。",
        "origin_to_now": "物語が大きくなっても、需要が続くとは限らない。",
        "hidden_giant": "知名度の低さと市場での重要度は別物だ。",
        "opportunity_window": "アクセスが増えることと、資金が定着することは同じではない。",
        "contradiction": "数字と価格、ニュースと資金。そのズレ自体が情報になる。",
    }.get(archetype, "確認できた事実と市場の反応を分けて見る。")


def _implication_ja(archetype: str) -> str:
    return {
        "money_flow": "フローの継続と、遅れて価格が追随するかを確認する。",
        "policy_change": "実施時期、対象、実際の資金移動が揃って初めて相場材料になる。",
        "crisis_or_risk": "資金流出や信用不安が他の主体へ広がるかを見る。",
        "power_shift": "主導権の移動が出来高と資金調達にまで波及するかを見る。",
        "historical_parallel": "過去の再演を決めつけず、比較に使われた指標と現在の反応を分けて追う。",
        "origin_to_now": "成長物語が続くかは、次の需要と資金が証明する。",
        "hidden_giant": "市場が重要度を再評価すると、周辺資産や資金配分まで変わり得る。",
        "opportunity_window": "新規参加が実需につながるか、最初の数週間の動きを見る。",
        "contradiction": "ズレがどちら向きに解消されるかが、次の方向を示す。",
    }.get(archetype, "次に確認できる事実を待つ。")


def build_story_candidates(resources: list[dict]) -> list[dict]:
    candidates: list[StoryCandidate] = []
    for cluster in cluster_story_candidates(resources):
        if not cluster:
            continue
        cluster = sorted(cluster, key=lambda row: float(row.get("story_score") or 0), reverse=True)
        hero = cluster[0]
        archetype = _cluster_archetype(cluster)
        avg_story = sum(float(row.get("story_score") or 0) for row in cluster[:4]) / min(4, len(cluster))
        corroboration_bonus = min(12.0, max(0, len({row.get('source') for row in cluster}) - 1) * 4.0)
        score = min(100.0, float(hero.get("story_score") or 0) * 0.76 + avg_story * 0.18 + corroboration_bonus)
        resource_ids = [str(row.get("id") or row.get("source_id") or row.get("url") or "") for row in cluster]
        candidate_id = "story_" + hashlib.sha1("|".join(resource_ids + [archetype, _title(hero)]).encode("utf-8", errors="ignore")).hexdigest()[:12]
        candidates.append(StoryCandidate(
            id=candidate_id,
            topic=str(hero.get("story_topic") or _topic_label(hero)),
            archetype=archetype,
            entities=list(hero.get("story_entities") or []),
            resource_ids=resource_ids,
            source_names=list(dict.fromkeys(str(row.get("source") or "") for row in cluster if row.get("source")))[:5],
            headline_seed=_title(hero),
            headline_ja=_headline_ja(hero, archetype),
            why_now_ja=_why_now_ja(archetype, hero),
            conflict_ja=_conflict_ja(archetype),
            implication_ja=_implication_ja(archetype),
            visual_motifs=_visual_motifs(_combined(hero), archetype),
            story_score=round(score, 2),
            confidence=round(min(1.0, 0.48 + float(hero.get("evidence_story_score") or 0) / 250 + min(0.18, (len(cluster) - 1) * 0.06)), 2),
            cluster_size=len(cluster),
            hero_resource=hero,
        ))
    return [candidate.to_dict() for candidate in sorted(candidates, key=lambda item: item.story_score, reverse=True)]


def select_hero_story(resources: list[dict]) -> dict:
    candidates = build_story_candidates(resources)
    if not candidates:
        return {}
    hero = dict(candidates[0])
    hero["candidates"] = candidates[:8]
    hero["fallback"] = False
    return hero


def story_arc(archetype: str, content_count: int) -> list[str]:
    base = list(STORY_ARCS.get(archetype) or STORY_ARCS["opportunity_window"])
    count = max(1, min(7, int(content_count or 6)))
    if count == 1:
        return [base[0]]
    if count >= len(base):
        return base[:count]
    middle = base[1:-1]
    needed = max(0, count - 2)
    if needed >= len(middle):
        chosen = middle
    elif needed == 1:
        chosen = [middle[len(middle) // 2]]
    else:
        indices = [round(i * (len(middle) - 1) / max(1, needed - 1)) for i in range(needed)]
        chosen = [middle[index] for index in indices]
    return [base[0], *chosen, base[-1]][:count]


def layout_for_story(archetype: str, role_index: int, seed: str = "") -> str:
    layouts = ARCHETYPE_LAYOUTS.get(archetype) or ARCHETYPE_LAYOUTS["opportunity_window"]
    offset = int(hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:4], 16) % len(layouts) if seed else 0
    return layouts[(role_index + offset) % len(layouts)]


def story_context(resources: list[dict]) -> dict:
    annotated = annotate_resources(resources)
    hero = select_hero_story(annotated)
    return {
        "version": STORY_ENGINE_VERSION,
        "hero_story": {key: value for key, value in hero.items() if key != "candidates"},
        "candidates": hero.get("candidates", []),
        "ranked_resource_ids": [row.get("id") or row.get("source_id") or row.get("url") for row in annotated],
        "resource_count": len(annotated),
        "policy": "evidence-first story selection; exact token matching; no implicit technical-market-map fallback",
    }
