from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from live_source_policy import age_minutes


TOPIC_RADAR_VERSION = "topic-radar-v1.0"

CANONICAL_ANCHORS = {
    "BTC": ["bitcoin", "btc", "ビットコイン"],
    "ETH": ["ethereum", "eth", "イーサリアム"],
    "XRP": ["xrp", "ripple", "リップル"],
    "SOL": ["solana", "sol", "ソラナ"],
    "TETHER": ["tether", "usdt", "テザー"],
    "CIRCLE": ["circle", "usdc", "サークル"],
    "SBI": ["sbi", "sbiホールディングス", "sbiグループ"],
    "BLACKROCK": ["blackrock", "ブラックロック"],
    "COINBASE": ["coinbase", "コインベース"],
    "BINANCE": ["binance", "バイナンス"],
    "BYBIT": ["bybit", "バイビット"],
    "OKX": ["okx"],
    "KRAKEN": ["kraken", "クラーケン"],
    "STRATEGY": ["microstrategy", "strategy", "マイクロストラテジー"],
    "SEC": [" sec ", "米sec", "証券取引委員会"],
    "CFTC": ["cftc"],
    "FED": ["federal reserve", "fed", "frb", "fomc", "米連邦準備"],
    "BOJ": ["bank of japan", "boj", "日銀", "日本銀行"],
    "TRUMP": ["trump", "トランプ"],
}

THEMES = {
    "ETF": ["etf", "上場投資信託"],
    "STABLECOIN": ["stablecoin", "ステーブルコイン"],
    "REGULATION": ["regulation", "rule", "law", "規制", "法案", "法制", "監督"],
    "TAX": ["tax", "taxation", "税制", "課税", "税率"],
    "HACK": ["hack", "hacked", "exploit", "breach", "ハッキング", "攻撃", "流出", "盗難"],
    "LISTING": ["listing", "listed", "上場", "取扱開始"],
    "DELISTING": ["delist", "delisting", "上場廃止", "取扱終了"],
    "ACQUISITION": ["acquire", "acquisition", "buyout", "買収", "子会社化"],
    "PARTNERSHIP": ["partnership", "partner", "提携", "協業"],
    "TREASURY": ["treasury", "reserve", "保有", "準備金", "財務戦略"],
    "PAYMENT": ["payment", "payments", "決済", "送金", "カード"],
    "BANK": ["bank", "銀行", "金融機関"],
    "IPO": ["ipo", "新規上場", "株式公開"],
    "RWA": ["rwa", "tokenization", "tokenized", "トークン化"],
    "AI": [" ai ", "artificial intelligence", "人工知能"],
    "MINING": ["mining", "miner", "マイニング", "採掘"],
    "LIQUIDATION": ["liquidation", "liquidated", "清算", "ロスカット"],
    "BANKRUPTCY": ["bankruptcy", "insolvency", "破綻", "倒産"],
    "LAWSUIT": ["lawsuit", "sues", "charged", "訴訟", "提訴", "起訴"],
    "RECORD": ["record", "all-time high", "過去最高", "最高値", "記録"],
    "DENIAL": ["deny", "denies", "否定", "事実ではない"],
}

HIGH_PULL_ACTORS = {
    "BLACKROCK", "SBI", "TETHER", "CIRCLE", "COINBASE", "BINANCE", "BYBIT", "OKX", "KRAKEN",
    "STRATEGY", "SEC", "CFTC", "FED", "BOJ", "TRUMP",
}
GENERIC_ASSETS = {"BTC", "ETH", "XRP", "SOL"}
CONSEQUENCE_THEMES = {
    "ETF", "REGULATION", "TAX", "HACK", "DELISTING", "ACQUISITION", "IPO", "LIQUIDATION",
    "BANKRUPTCY", "LAWSUIT", "RECORD", "TREASURY", "PAYMENT",
}
PERSONAL_RELEVANCE_TERMS = [
    "fee", "withdraw", "deposit", "card", "tax", "payment", "yield", "interest", "bank",
    "手数料", "出金", "入金", "カード", "税", "決済", "利回り", "金利", "銀行", "口座",
]
CONTRADICTION_TERMS = [
    "but", "yet", "despite", "however", "while", "deny", "versus", "vs", "surprise",
    "一方", "しかし", "だが", "なのに", "否定", "実は", "逆に", "対して",
]
STOP_TOKENS = {
    "crypto", "cryptocurrency", "news", "market", "markets", "bitcoin", "ethereum", "btc", "eth",
    "仮想通貨", "暗号資産", "ビットコイン", "市場", "ニュース", "最新", "発表", "について", "今後",
    "the", "and", "for", "with", "from", "this", "that", "will", "new", "after", "into", "says",
}


def _text(row: dict) -> str:
    return " ".join(str(row.get(key) or "") for key in ("title", "excerpt", "material", "tags", "signal_query"))[:10000]


def _contains(text: str, variant: str) -> bool:
    low = text.lower()
    needle = variant.lower()
    if needle.startswith(" ") or needle.endswith(" "):
        return needle.strip() in f" {low} "
    if re.fullmatch(r"[a-z0-9.+_-]+", needle):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", low))
    return needle in low


def _extract_map_hits(text: str, mapping: dict[str, list[str]]) -> set[str]:
    return {key for key, variants in mapping.items() if any(_contains(text, variant) for variant in variants)}


def _lexical_tokens(text: str) -> set[str]:
    low = text.lower()
    out: set[str] = set()
    for token in re.findall(r"[a-z][a-z0-9.+_-]{2,}|[ァ-ヶー]{3,}|[一-龥]{2,8}", low):
        if token not in STOP_TOKENS and len(token) >= 3:
            out.add(token)
    return set(list(out)[:80])


def signature(row: dict) -> dict:
    text = _text(row)
    return {
        "anchors": _extract_map_hits(text, CANONICAL_ANCHORS),
        "themes": _extract_map_hits(text, THEMES),
        "tokens": _lexical_tokens(str(row.get("title") or "")),
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def similarity(a: dict, b: dict) -> float:
    shared_anchors = a["anchors"] & b["anchors"]
    shared_named = shared_anchors - GENERIC_ASSETS
    shared_assets = shared_anchors & GENERIC_ASSETS
    shared_themes = a["themes"] & b["themes"]
    lexical = _jaccard(a["tokens"], b["tokens"])
    score = min(0.42, len(shared_named) * 0.30)
    score += min(0.24, len(shared_themes) * 0.16)
    score += min(0.14, len(shared_assets) * 0.10)
    score += lexical * 0.32
    if shared_assets and not shared_named and not shared_themes and lexical < 0.22:
        return 0.0
    return min(1.0, score)


def audience_pull_score(row: dict, sig: dict | None = None) -> float:
    sig = sig or signature(row)
    lower = _text(row).lower()
    score = 20.0
    score += min(22.0, len(sig["anchors"] & HIGH_PULL_ACTORS) * 11.0)
    score += min(24.0, len(sig["themes"] & CONSEQUENCE_THEMES) * 8.0)
    numbers = re.findall(r"(?:[$¥￥€£]\s*)?\d[\d,.]*(?:\.\d+)?\s*(?:%|億|兆|万|million|billion|trillion|ドル|円|usd|jpy)?", lower)
    meaningful = [n for n in numbers if re.search(r"[%$¥￥€£億兆万]|million|billion|trillion|ドル|円|usd|jpy", n)]
    score += min(14.0, len(meaningful) * 5.0)
    if any(term in lower for term in CONTRADICTION_TERMS):
        score += 10.0
    if any(term in lower for term in PERSONAL_RELEVANCE_TERMS):
        score += 10.0
    if row.get("signal_type") == "search_trend":
        score += 18.0
    elif row.get("source_role") == "community":
        score += 8.0
    return round(min(100.0, score), 2)


def _recency_score(row: dict, now: datetime) -> float:
    age = age_minutes(row.get("posted_at"), now=now)
    if age is None:
        return 0.0
    if age <= 60:
        return 100.0
    if age <= 180:
        return 92.0
    if age <= 360:
        return 84.0
    if age <= 720:
        return 74.0
    if age <= 1440:
        return 62.0
    return 38.0


def _publisher_key(row: dict) -> str:
    return str(row.get("origin_publisher") or row.get("source") or "unknown").strip().lower()


def _cluster_id(member_ids: Iterable[str]) -> str:
    raw = "|".join(sorted(str(value) for value in member_ids if value))
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:14]


def _cluster_reason(cluster: dict) -> list[str]:
    reasons: list[str] = []
    if cluster["source_count"] >= 3:
        reasons.append(f"{cluster['source_count']}개 출처 동시 포착")
    if cluster["role_count"] >= 2:
        reasons.append(f"{cluster['role_count']}개 신호층 교차")
    if cluster["signal_count"]:
        reasons.append(f"관심도 센서 {cluster['signal_count']}건")
    if cluster["max_audience"] >= 75:
        reasons.append("대중 관심 훅 강함")
    if cluster["fresh_3h"] >= 2:
        reasons.append(f"3시간 내 {cluster['fresh_3h']}건 확산")
    return reasons[:4]


def apply_topic_radar(rows: list[dict], *, now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    current = now or datetime.now(timezone.utc)
    prepared: list[dict] = []
    signatures: dict[str, dict] = {}
    trend_anchor_interest: defaultdict[str, int] = defaultdict(int)
    for raw in rows or []:
        row = dict(raw or {})
        rid = str(row.get("id") or row.get("url") or hashlib.sha1(_text(row).encode()).hexdigest()[:16])
        row["id"] = rid
        sig = signature(row)
        signatures[rid] = sig
        row["audience_pull_score"] = audience_pull_score(row, sig)
        row["topic_radar_version"] = TOPIC_RADAR_VERSION
        prepared.append(row)
        if row.get("signal_type") == "search_trend":
            for anchor in sig["anchors"]:
                trend_anchor_interest[anchor] += 1

    clusters: list[dict] = []
    index: defaultdict[str, set[int]] = defaultdict(set)
    for row in sorted(prepared, key=lambda item: age_minutes(item.get("posted_at"), now=current) or 10**9):
        rid = row["id"]
        sig = signatures[rid]
        keys = {f"a:{v}" for v in sig["anchors"]} | {f"t:{v}" for v in sig["themes"]}
        candidate_ids: set[int] = set()
        for key in keys:
            candidate_ids.update(index.get(key, set()))
        best_idx = None
        best_score = 0.0
        for idx in candidate_ids:
            score = similarity(sig, clusters[idx]["signature"])
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is None or best_score < 0.32:
            best_idx = len(clusters)
            clusters.append({"members": [], "signature": {"anchors": set(), "themes": set(), "tokens": set()}})
        cluster = clusters[best_idx]
        cluster["members"].append(row)
        cluster["signature"]["anchors"].update(sig["anchors"])
        cluster["signature"]["themes"].update(sig["themes"])
        cluster["signature"]["tokens"].update(list(sig["tokens"])[:30])
        for key in keys:
            index[key].add(best_idx)

    summaries: list[dict] = []
    for cluster in clusters:
        members = cluster["members"]
        if not members:
            continue
        source_keys = {_publisher_key(row) for row in members}
        roles = {str(row.get("source_role") or row.get("source_type") or "editorial") for row in members}
        signals = [row for row in members if row.get("signal_only")]
        direct = [row for row in members if not row.get("signal_only")]
        recencies = [_recency_score(row, current) for row in members]
        audience_values = [float(row.get("audience_pull_score") or 0) for row in members]
        fresh_3h = sum(1 for row in members if (age_minutes(row.get("posted_at"), now=current) or 10**9) <= 180)
        source_count = len(source_keys)
        role_count = len(roles)
        cross_source = min(100.0, 22.0 + max(0, source_count - 1) * 18.0)
        role_diversity = min(100.0, 25.0 + max(0, role_count - 1) * 24.0)
        burst = min(100.0, 18.0 + fresh_3h * 18.0)
        recency = max(recencies or [0.0])
        max_audience = max(audience_values or [0.0])
        avg_audience = sum(audience_values) / max(1, len(audience_values))
        audience = min(100.0, max_audience * 0.7 + avg_audience * 0.3)
        interest_bonus = 0.0
        for anchor in cluster["signature"]["anchors"]:
            interest_bonus += min(8.0, trend_anchor_interest.get(anchor, 0) * 4.0)
        interest_bonus = min(14.0, interest_bonus)
        heat = min(100.0, recency * 0.27 + cross_source * 0.25 + audience * 0.23 + role_diversity * 0.13 + burst * 0.12 + interest_bonus)
        cluster_id = _cluster_id(row["id"] for row in members)
        summary = {
            "cluster_id": cluster_id,
            "topic_heat_score": round(heat, 2),
            "source_count": source_count,
            "role_count": role_count,
            "signal_count": len(signals),
            "direct_count": len(direct),
            "fresh_3h": fresh_3h,
            "max_audience": round(max_audience, 2),
            "anchors": sorted(cluster["signature"]["anchors"]),
            "themes": sorted(cluster["signature"]["themes"]),
            "member_ids": [row["id"] for row in members],
        }
        summary["reasons"] = _cluster_reason(summary)
        summaries.append(summary)
        for row in members:
            row["topic_cluster_id"] = cluster_id
            row["topic_heat_score"] = round(heat, 2)
            row["topic_source_count"] = source_count
            row["topic_role_count"] = role_count
            row["topic_signal_count"] = len(signals)
            row["topic_heat_reasons"] = " · ".join(summary["reasons"])
            row["search_interest_bonus"] = round(interest_bonus, 2)

    summaries.sort(key=lambda item: (item["topic_heat_score"], item["source_count"], item["max_audience"]), reverse=True)
    prepared.sort(key=lambda row: (float(row.get("topic_heat_score") or 0), float(row.get("audience_pull_score") or 0)), reverse=True)
    return prepared, summaries


def apply_story_heat_blend(rows: list[dict]) -> list[dict]:
    blended: list[dict] = []
    for raw in rows or []:
        row = dict(raw or {})
        base = float(row.get("story_score") or 0)
        heat = float(row.get("topic_heat_score") or 0)
        pull = float(row.get("audience_pull_score") or 0)
        row["base_story_score"] = round(base, 2)
        row["story_score"] = round(min(100.0, base * 0.58 + heat * 0.27 + pull * 0.15), 2)
        row["editorial_score"] = round(max(float(row.get("editorial_score") or 0), row["story_score"]), 2)
        blended.append(row)
    return sorted(blended, key=lambda row: (float(row.get("story_score") or 0), float(row.get("topic_heat_score") or 0), float(row.get("audience_pull_score") or 0)), reverse=True)


def apply_trader_heat_blend(rows: list[dict]) -> list[dict]:
    blended: list[dict] = []
    for raw in rows or []:
        row = dict(raw or {})
        base = float(row.get("trader_score") or 0)
        heat = float(row.get("topic_heat_score") or 0)
        row["base_trader_score"] = round(base, 2)
        row["trader_score"] = round(min(100.0, base * 0.86 + heat * 0.14), 2)
        blended.append(row)
    return sorted(blended, key=lambda row: (float(row.get("trader_score") or 0), float(row.get("topic_heat_score") or 0)), reverse=True)
