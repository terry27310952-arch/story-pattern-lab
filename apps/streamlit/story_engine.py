from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from typing import Iterable


STORY_ENGINE_VERSION = "story-engine-v5.0"

# These are deliberately editorial, not trading-score labels. A story can be a great
# carousel even when it is not the most important intraday trading datapoint.
ARCHETYPES = {
    "contradiction",
    "hidden_giant",
    "origin_to_now",
    "money_flow",
    "power_shift",
    "policy_change",
    "market_map",
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
    "market_map": ["hook", "market_state", "key_levels", "positioning", "catalyst", "scenario", "watch"],
    "historical_parallel": ["hook", "then", "what_happened", "now", "similarity", "difference", "watch"],
    "crisis_or_risk": ["hook", "incident", "exposure", "contagion", "evidence", "market_implication", "watch"],
    "opportunity_window": ["hook", "what_changed", "why_now", "evidence", "constraint", "market_implication", "watch"],
}

# Renderer-compatible layouts. Story role chooses the shell; the brand remains fixed.
ARCHETYPE_LAYOUTS: dict[str, list[str]] = {
    "contradiction": ["poster_center", "split_left", "data_monument", "newspaper_panel", "split_top", "full_bleed_bottom", "top_caption"],
    "hidden_giant": ["full_bleed_bottom", "poster_center", "split_left", "data_monument", "newspaper_panel", "split_top", "top_caption"],
    "origin_to_now": ["poster_center", "split_top", "newspaper_panel", "split_left", "data_monument", "full_bleed_bottom", "top_caption"],
    "money_flow": ["data_monument", "split_left", "full_bleed_bottom", "split_top", "poster_center", "newspaper_panel", "top_caption"],
    "power_shift": ["poster_center", "split_left", "newspaper_panel", "data_monument", "full_bleed_bottom", "split_top", "top_caption"],
    "policy_change": ["newspaper_panel", "poster_center", "split_left", "top_caption", "data_monument", "full_bleed_bottom", "split_top"],
    "market_map": ["data_monument", "split_top", "split_left", "newspaper_panel", "poster_center", "rule_board", "full_bleed_bottom"],
    "historical_parallel": ["newspaper_panel", "split_left", "poster_center", "split_top", "data_monument", "full_bleed_bottom", "top_caption"],
    "crisis_or_risk": ["poster_center", "newspaper_panel", "split_left", "data_monument", "split_top", "full_bleed_bottom", "top_caption"],
    "opportunity_window": ["full_bleed_bottom", "poster_center", "split_left", "data_monument", "split_top", "newspaper_panel", "top_caption"],
}

HOOK_WORDS = [
    "why", "how", "what if", "unexpected", "secret", "hidden", "record", "first", "only", "never",
    "なぜ", "どうして", "初", "過去最高", "史上", "異例", "急増", "急落", "秘密", "知られ",
    "왜", "어떻게", "사상", "최초", "급증", "급락", "의외", "숨겨진",
]
CONFLICT_WORDS = [
    "but", "yet", "despite", "while", "versus", "vs", "although", "however", "paradox",
    "しかし", "一方", "なのに", "にもかかわらず", "反対", "逆", "対立",
    "하지만", "반면", "그런데", "불구하고", "역설", "충돌",
]
CHANGE_WORDS = [
    "rise", "fall", "surge", "drop", "shift", "change", "turn", "launch", "approval", "ban", "buy", "sell",
    "acquire", "expand", "cut", "increase", "decrease", "new", "record", "first", "return", "collapse",
    "上昇", "下落", "急増", "急減", "転換", "変更", "開始", "承認", "禁止", "買収", "拡大", "縮小", "新",
    "상승", "하락", "급증", "급감", "전환", "변화", "출시", "승인", "금지", "매수", "인수", "확대", "축소", "신규",
]
MARKET_IMPLICATION_WORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "etf", "market", "liquidity", "yield", "rate", "fed", "boj",
    "sec", "regulation", "stablecoin", "exchange", "institution", "treasury", "reserve", "supply", "demand",
    "ビットコイン", "暗号資産", "市場", "流動性", "金利", "規制", "取引所", "機関", "準備金", "供給", "需要",
    "비트코인", "암호화폐", "시장", "유동성", "금리", "규제", "거래소", "기관", "준비금", "공급", "수요",
]
VISUAL_WORDS = [
    "factory", "office", "exchange", "wall street", "tokyo", "bank", "building", "data center", "mine", "server",
    "ceo", "founder", "president", "chair", "court", "parliament", "congress", "warehouse", "fund", "trading desk",
    "工場", "取引所", "東京", "銀行", "データセンター", "鉱山", "サーバー", "社長", "創業者", "議会", "倉庫",
    "공장", "거래소", "도쿄", "은행", "데이터센터", "광산", "서버", "대표", "창업자", "의회", "창고",
]
ENTITY_HINTS = [
    "blackrock", "fidelity", "microstrategy", "strategy", "metaplanet", "binance", "coinbase", "bitget", "bybit",
    "sec", "cftc", "fed", "federal reserve", "boj", "bank of japan", "jpmorgan", "goldman", "softbank", "sbi",
    "trump", "powell", "cz", "changpeng zhao", "saylor", "michael saylor", "vitalik", "buterin",
]

POLICY_WORDS = ["regulation", "law", "tax", "sec", "cftc", "policy", "rule", "approval", "規制", "法律", "税制", "政策", "承認", "규제", "법", "세제", "정책", "승인"]
FLOW_WORDS = ["flow", "inflow", "outflow", "fund", "etf", "buying", "purchase", "treasury", "reserve", "資金", "流入", "流出", "購入", "保有", "자금", "유입", "유출", "매입", "보유"]
CRISIS_WORDS = ["hack", "exploit", "liquidation", "bankrupt", "collapse", "attack", "scam", "freeze", "ハック", "破綻", "清算", "攻撃", "詐欺", "해킹", "파산", "청산", "공격", "사기"]
HISTORY_WORDS = ["history", "historical", "since", "years ago", "decade", "oldest", "歴史", "以来", "年前", "過去", "역사", "이후", "년 전", "과거"]
POWER_WORDS = ["market share", "dominance", "acquire", "takeover", "rival", "challenger", "lead", "power", "シェア", "覇権", "買収", "競争", "主導", "점유율", "패권", "인수", "경쟁", "주도"]
ORIGIN_WORDS = ["founded", "started", "began", "origin", "from", "創業", "始ま", "起源", "設立", "창업", "시작", "설립", "기원"]
OPPORTUNITY_WORDS = ["launch", "approval", "adoption", "open", "access", "opportunity", "開始", "承認", "採用", "解禁", "機会", "출시", "승인", "채택", "개방", "기회"]


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


def _clean(value: object, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _lower(value: object, limit: int = 5000) -> str:
    return _clean(value, limit).lower()


def _hits(text: str, words: Iterable[str]) -> int:
    low = text.lower()
    return sum(1 for word in words if word.lower() in low)


def _score_from_hits(count: int, base: float = 18.0, cap: float = 100.0) -> float:
    if count <= 0:
        return 0.0
    return min(cap, base + math.log2(count + 1) * 27.0)


def _material(row: dict) -> str:
    return _clean(row.get("material") or row.get("full_material") or row.get("excerpt") or "", 6000)


def _title(row: dict) -> str:
    return _clean(row.get("title") or row.get("short_title") or "", 300)


def _combined(row: dict) -> str:
    return f"{_title(row)} {_clean(row.get('tags'), 300)} {_material(row)[:2200]}"


def _scale_score(text: str) -> float:
    numeric = re.findall(r"(?:\$|¥|￥)?\d[\d,.]*(?:\s?(?:%|billion|million|trillion|bn|mn|億|兆|万|ドル|円))?", text, flags=re.I)
    strong = [m for m in numeric if any(ch.isdigit() for ch in m) and ("%" in m or any(unit in m.lower() for unit in ["billion", "million", "trillion", "bn", "mn", "億", "兆", "万", "$", "¥", "￥"]))]
    if strong:
        return min(100.0, 45.0 + len(strong) * 15.0)
    if numeric:
        return min(60.0, 20.0 + len(numeric) * 6.0)
    return 0.0


def _entity_list(text: str) -> list[str]:
    low = text.lower()
    entities: list[str] = []
    for hint in ENTITY_HINTS:
        if hint in low:
            display = hint.upper() if len(hint) <= 4 else hint.title()
            if display not in entities:
                entities.append(display)
    # Conservative English proper-noun extraction, useful for company/person headlines.
    for match in re.findall(r"\b(?:[A-Z][A-Za-z0-9.&-]{2,})(?:\s+[A-Z][A-Za-z0-9.&-]{2,}){0,2}\b", text):
        if match.upper() in {"BTC", "ETH", "ETF", "SEC", "CFTC", "USD"}:
            continue
        if match not in entities:
            entities.append(match)
        if len(entities) >= 6:
            break
    return entities[:6]


def _visual_motifs(text: str, archetype: str) -> list[str]:
    motifs: list[str] = []
    low = text.lower()
    mapping = [
        (["etf", "fund", "資金", "flow", "treasury", "reserve"], "institutional capital flow"),
        (["sec", "law", "tax", "regulation", "規制", "政策"], "policy document and institution"),
        (["exchange", "binance", "coinbase", "取引所"], "exchange infrastructure"),
        (["bank", "fed", "boj", "銀行", "金利"], "central bank and financial district"),
        (["mine", "miner", "mining", "鉱山", "マイニング"], "industrial mining infrastructure"),
        (["server", "data center", "データセンター", "ai"], "data center and server rows"),
        (["ceo", "founder", "president", "創業者", "社長"], "anonymous executive documentary portrait"),
    ]
    for words, motif in mapping:
        if any(word.lower() in low for word in words) and motif not in motifs:
            motifs.append(motif)
    defaults = {
        "contradiction": "opposing market signals",
        "hidden_giant": "large industrial or institutional environment",
        "origin_to_now": "timeline from archive to present",
        "money_flow": "capital moving between institutions and Bitcoin",
        "power_shift": "two competing institutions with shifting balance",
        "policy_change": "official document, chamber, and financial market",
        "market_map": "price map and market structure",
        "historical_parallel": "archive imagery contrasted with present market",
        "crisis_or_risk": "dark infrastructure under stress",
        "opportunity_window": "opening access point into institutional market",
    }
    if defaults.get(archetype) not in motifs:
        motifs.append(defaults[archetype])
    return motifs[:4]


def _story_components(row: dict) -> dict[str, float]:
    text = _combined(row)
    title = _title(row)
    material_len = len(_material(row))
    source_type = str(row.get("source_type") or "")
    hook = min(100.0, _score_from_hits(_hits(title, HOOK_WORDS), 24) + (18 if "?" in title or "？" in title else 0))
    conflict = min(100.0, _score_from_hits(_hits(text, CONFLICT_WORDS), 14))
    entities = _entity_list(f"{title} {text[:1200]}")
    character = min(100.0, len(entities) * 22.0 + (12 if any(word in text.lower() for word in ["ceo", "founder", "president", "chair", "社長", "創業者", "대표", "창업자"]) else 0))
    change = min(100.0, _score_from_hits(_hits(text, CHANGE_WORDS), 15))
    scale = _scale_score(text)
    implication = min(100.0, _score_from_hits(_hits(text, MARKET_IMPLICATION_WORDS), 22))
    visuality = min(100.0, _score_from_hits(_hits(text, VISUAL_WORDS), 12) + min(25.0, len(entities) * 5.0))
    evidence = 25.0
    if material_len >= 240:
        evidence += 15.0
    if material_len >= 800:
        evidence += 25.0
    if material_len >= 1800:
        evidence += 15.0
    if source_type in {"rss", "media"}:
        evidence += 10.0
    evidence = min(100.0, evidence)
    novelty = min(100.0, _score_from_hits(_hits(text, ["first", "record", "new", "unprecedented", "初", "過去最高", "新", "異例", "최초", "사상", "신규"]), 12))
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
    low = text.lower()
    components = components or _story_components(row)
    if _hits(text, CRISIS_WORDS) >= 1:
        return "crisis_or_risk"
    if _hits(text, POLICY_WORDS) >= 2 or ("sec" in low and any(word in low for word in ["rule", "approval", "regulation", "規制", "承認"])):
        return "policy_change"
    if _hits(text, FLOW_WORDS) >= 2:
        return "money_flow"
    if _hits(text, POWER_WORDS) >= 2:
        return "power_shift"
    if _hits(text, HISTORY_WORDS) >= 2:
        return "historical_parallel"
    if _hits(text, ORIGIN_WORDS) >= 2 and components.get("change_score", 0) >= 35:
        return "origin_to_now"
    if components.get("conflict_score", 0) >= 45:
        return "contradiction"
    if _hits(text, OPPORTUNITY_WORDS) >= 2:
        return "opportunity_window"
    if components.get("character_score", 0) >= 50 and components.get("scale_score", 0) >= 35:
        return "hidden_giant"
    return "market_map"


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
        + components["evidence_story_score"] * 0.05
        + components["novelty_score"] * 0.05
    )
    # Do not let low-quality community chatter outrank a documented source purely by drama.
    risk = float(item.get("risk_score") or 0.0)
    quality_penalty = max(0.0, min(15.0, (risk - 35.0) * 0.22))
    story_score = max(0.0, min(100.0, weighted - quality_penalty))
    item.update(components)
    item["story_score"] = round(story_score, 2)
    item["story_archetype_hint"] = archetype
    item["story_entities"] = _entity_list(_combined(item))
    item["story_topic"] = _topic_label(item)
    item["story_visual_motifs"] = _visual_motifs(_combined(item), archetype)
    item["editorial_score"] = round(story_score * 0.72 + float(item.get("trader_score") or 0.0) * 0.28, 2)
    return item


def annotate_resources(resources: list[dict]) -> list[dict]:
    annotated = [annotate_resource(row) for row in (resources or []) if isinstance(row, dict)]
    return sorted(
        annotated,
        key=lambda row: (
            float(row.get("editorial_score") or 0),
            float(row.get("story_score") or 0),
            float(row.get("trader_score") or 0),
        ),
        reverse=True,
    )


def _topic_label(row: dict) -> str:
    tags = [part.strip() for part in str(row.get("tags") or "").split(",") if part.strip()]
    if tags:
        return "/".join(tags[:2])
    entities = _entity_list(_combined(row))
    return entities[0] if entities else "CRYPTO"


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]{3,}|[ァ-ヶ一-龥]{2,}|[가-힣]{2,}", text.lower())
    stop = {"bitcoin", "btc", "crypto", "market", "ビットコイン", "暗号資産", "시장", "비트코인", "news", "today"}
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
    return jaccard * 0.72 + entity_overlap * 0.16 + same_hint


def cluster_story_candidates(resources: list[dict], similarity_threshold: float = 0.34) -> list[list[dict]]:
    annotated = annotate_resources(resources)
    clusters: list[list[dict]] = []
    for row in annotated:
        best_index = -1
        best_score = 0.0
        for index, cluster in enumerate(clusters):
            score = max((_similarity(row, other) for other in cluster[:4]), default=0.0)
            if score > best_score:
                best_index = index
                best_score = score
        if best_index >= 0 and best_score >= similarity_threshold:
            clusters[best_index].append(row)
        else:
            clusters.append([row])
    return clusters


def _cluster_archetype(cluster: list[dict]) -> str:
    votes: dict[str, float] = {}
    for row in cluster:
        key = str(row.get("story_archetype_hint") or "market_map")
        votes[key] = votes.get(key, 0.0) + max(1.0, float(row.get("story_score") or 0.0))
    return max(votes, key=votes.get) if votes else "market_map"


def _headline_ja(hero: dict, archetype: str) -> str:
    entity = (hero.get("story_entities") or [""])[0]
    topic = hero.get("story_topic") or "BTC"
    supplied = _clean(hero.get("display_headline_ja"), 70)
    if supplied and supplied not in {"BTC材料を価格で確認", "市場材料を確認"}:
        return supplied
    if archetype == "money_flow":
        return "資金は動いた。価格は、まだ同じ方向を向いていない。"
    if archetype == "policy_change":
        return f"{entity or topic}をめぐるルールが変わる。"
    if archetype == "crisis_or_risk":
        return f"{entity or topic}で起きた異変。どこまで波及する？"
    if archetype == "power_shift":
        return f"主導権が動いている。{entity or topic}の次は誰か。"
    if archetype == "historical_parallel":
        return "いまの市場、過去のあの局面と似ている。"
    if archetype == "origin_to_now":
        return f"小さく始まった{entity or topic}が、いま市場を動かす。"
    if archetype == "hidden_giant":
        return f"目立たない{entity or topic}が、実は大きな位置を占めている。"
    if archetype == "opportunity_window":
        return "新しい入口が開いた。市場が先に見るのは何か。"
    if archetype == "contradiction":
        return "数字は弱い。なのに、価格は崩れていない。"
    return "いま市場で、一番先に見るべきこと。"


def _why_now_ja(archetype: str, hero: dict) -> str:
    topic = hero.get("story_topic") or "市場"
    mapping = {
        "money_flow": "ニュースそのものより、資金がどこから入り、どこで止まっているかが次の価格を決める。",
        "policy_change": "制度変更は発表日より、誰の行動を変えるかで市場への影響が決まる。",
        "crisis_or_risk": "最初の見出しより、露出先と二次波及を切り分ける必要がある。",
        "power_shift": "取引量や資金の主導権が移ると、同じ材料でも市場の反応速度が変わる。",
        "historical_parallel": "似ている点だけでなく、当時と違う条件まで見ると現在地が見えやすい。",
        "origin_to_now": "過去の小さな変化が、いま資金や市場構造にどうつながったかを見る。",
        "hidden_giant": "知名度より、実際にどこを握っているかを見ると市場の構造が変わって見える。",
        "opportunity_window": "入口が開いた直後は期待より、実際の参加者と資金の定着を見る。",
        "contradiction": "相反する数字が同時に出る時ほど、次のブレイクの条件が明確になる。",
        "market_map": f"{topic}の材料を並べるより、価格とポジションがどこで一致するかを見る。",
    }
    return mapping.get(archetype, mapping["market_map"])


def _conflict_ja(archetype: str) -> str:
    return {
        "money_flow": "資金流入と価格反応が一致しているとは限らない。",
        "policy_change": "好材料に見えても、適用範囲と時期がずれれば価格は先に織り込めない。",
        "crisis_or_risk": "被害規模と市場全体のリスクは同じではない。",
        "power_shift": "シェアが動いても、利益と価格が同時に動くとは限らない。",
        "historical_parallel": "チャートは似ても、流動性と参加者は当時と違う。",
        "origin_to_now": "物語が大きくなっても、現在の価格に全部織り込まれているとは限らない。",
        "hidden_giant": "知名度の低さと市場での重要度は別物だ。",
        "opportunity_window": "アクセスが増えることと、すぐ資金が入ることは同じではない。",
        "contradiction": "センチメントと価格、ニュースとフロー。そのズレ自体が今日の主役だ。",
        "market_map": "予想より、境界をどちら側で確定するかが先。",
    }.get(archetype, "材料と価格反応を分けて見る。")


def _implication_ja(archetype: str) -> str:
    return {
        "money_flow": "フローが継続し、価格が遅れて追随するかを確認する。",
        "policy_change": "実施時期、対象企業、資金移動の3点が確認できて初めて相場材料になる。",
        "crisis_or_risk": "連鎖が限定的なら過度な悲観は不要。資金流出が広がれば別の話になる。",
        "power_shift": "主導権の移動が出来高と資金調達にまで波及するかを見る。",
        "historical_parallel": "同じ形を期待するのではなく、違う条件が崩れる瞬間を確認する。",
        "origin_to_now": "成長物語が今後も続くかは、次の資金と需要が証明する。",
        "hidden_giant": "市場がその重要度を再評価し始めると、周辺銘柄や資金配分まで変わる可能性がある。",
        "opportunity_window": "新規参加が実需につながるか、最初の数週間のフローを見る。",
        "contradiction": "ズレが解消される方向が、次のトレンドのヒントになる。",
        "market_map": "価格、OI、資金フローが同じ方向を向くまで結論を固定しない。",
    }.get(archetype, "価格と資金の確認が次の判断材料になる。")


def build_story_candidates(resources: list[dict]) -> list[dict]:
    clusters = cluster_story_candidates(resources)
    candidates: list[StoryCandidate] = []
    for cluster in clusters:
        if not cluster:
            continue
        cluster = sorted(cluster, key=lambda row: float(row.get("story_score") or 0), reverse=True)
        hero = cluster[0]
        archetype = _cluster_archetype(cluster)
        avg_story = sum(float(row.get("story_score") or 0) for row in cluster[:4]) / min(4, len(cluster))
        corroboration_bonus = min(12.0, max(0, len({row.get('source') for row in cluster}) - 1) * 4.0)
        score = min(100.0, float(hero.get("story_score") or 0) * 0.72 + avg_story * 0.20 + corroboration_bonus)
        resource_ids = [str(row.get("id") or row.get("source_id") or row.get("url") or "") for row in cluster]
        seed = "|".join(resource_ids + [archetype, _title(hero)])
        candidate_id = "story_" + hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:12]
        candidate = StoryCandidate(
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
            confidence=round(min(1.0, 0.48 + float(hero.get("evidence_story_score") or 0) / 250 + min(0.18, (len(cluster)-1)*0.06)), 2),
            cluster_size=len(cluster),
            hero_resource=hero,
        )
        candidates.append(candidate)
    return [candidate.to_dict() for candidate in sorted(candidates, key=lambda item: item.story_score, reverse=True)]


def select_hero_story(resources: list[dict]) -> dict:
    candidates = build_story_candidates(resources)
    if not candidates:
        return {
            "id": "story_fallback_market_map",
            "topic": "BTC",
            "archetype": "market_map",
            "headline_ja": "いま市場で、一番先に見るべきこと。",
            "why_now_ja": _why_now_ja("market_map", {}),
            "conflict_ja": _conflict_ja("market_map"),
            "implication_ja": _implication_ja("market_map"),
            "visual_motifs": ["price map and market structure"],
            "story_score": 0.0,
            "confidence": 0.35,
            "cluster_size": 0,
            "hero_resource": {},
            "candidates": [],
            "fallback": True,
        }
    hero = dict(candidates[0])
    # If the best available item has very little narrative structure, deliberately fall
    # back to a market-map story rather than forcing a weak "documentary" claim.
    if float(hero.get("story_score") or 0) < 35:
        hero["archetype"] = "market_map"
        hero["headline_ja"] = "いま市場で、一番先に見るべきこと。"
        hero["why_now_ja"] = _why_now_ja("market_map", hero.get("hero_resource") or {})
        hero["conflict_ja"] = _conflict_ja("market_map")
        hero["implication_ja"] = _implication_ja("market_map")
        hero["fallback"] = True
    else:
        hero["fallback"] = False
    hero["candidates"] = candidates[:8]
    return hero


def story_arc(archetype: str, content_count: int) -> list[str]:
    archetype = archetype if archetype in STORY_ARCS else "market_map"
    base = list(STORY_ARCS[archetype])
    count = max(1, min(7, int(content_count or 6)))
    if count == 1:
        return [base[0]]
    if count >= len(base):
        return base[:count]
    # Keep hook and watch; sample the middle so 5/6/7-card variants are not merely the
    # same list truncated from the end.
    middle = base[1:-1]
    needed = max(0, count - 2)
    if needed >= len(middle):
        chosen = middle
    elif needed == 1:
        chosen = [middle[len(middle)//2]]
    else:
        indices = [round(i * (len(middle)-1) / max(1, needed-1)) for i in range(needed)]
        chosen = [middle[index] for index in indices]
    return [base[0], *chosen, base[-1]][:count]


def layout_for_story(archetype: str, role_index: int, seed: str = "") -> str:
    archetype = archetype if archetype in ARCHETYPE_LAYOUTS else "market_map"
    layouts = ARCHETYPE_LAYOUTS[archetype]
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
        "policy": "story_score first for editorial selection; trader_score remains a secondary market-importance signal",
    }
