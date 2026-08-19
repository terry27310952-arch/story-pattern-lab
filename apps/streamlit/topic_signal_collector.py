from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import feedparser

from live_source_policy import LIVE_FALLBACK_HOURS, age_minutes


TOPIC_SIGNAL_COLLECTOR_VERSION = "topic-signals-v1.0"
USER_AGENT = "Mozilla/5.0 StoryPatternLab/1.2; topic-radar"

GOOGLE_NEWS_QUERIES = {
    "JP_CRYPTO": {
        "query": "暗号資産 OR 仮想通貨 OR ビットコイン OR イーサリアム",
        "hl": "ja",
        "gl": "JP",
        "ceid": "JP:ja",
    },
    "JP_STABLE_POLICY": {
        "query": "ステーブルコイン OR USDT OR USDC OR 暗号資産 ETF OR 仮想通貨 税制",
        "hl": "ja",
        "gl": "JP",
        "ceid": "JP:ja",
    },
    "JP_INSTITUTION": {
        "query": "SBI 暗号資産 OR ブラックロック ビットコイン OR テザー OR サークル USDC",
        "hl": "ja",
        "gl": "JP",
        "ceid": "JP:ja",
    },
    "GLOBAL_INSTITUTION": {
        "query": "\"bitcoin ETF\" OR \"crypto treasury\" OR stablecoin OR tokenization",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    "GLOBAL_RISK": {
        "query": "\"crypto hack\" OR \"exchange hack\" OR exploit OR liquidation OR bankruptcy",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
    "GLOBAL_POLICY": {
        "query": "\"crypto regulation\" OR SEC crypto OR CFTC crypto OR stablecoin regulation",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    },
}

TREND_RELEVANCE_TERMS = [
    "bitcoin", "btc", "ethereum", "eth", "xrp", "solana", "crypto", "stablecoin",
    "binance", "coinbase", "tether", "usdt", "usdc", "blackrock", "sbi", "etf",
    "ビットコイン", "イーサリアム", "リップル", "ソラナ", "暗号資産", "仮想通貨",
    "ステーブルコイン", "テザー", "サークル", "株価", "株式", "金融", "銀行", "金利",
    "日銀", "fomc", "fed", "frb", "ドル", "円相場", "ゴールド", "金価格", "国債",
    "税制", "規制", "経営破綻", "ipo", "上場", "証券", "投資", "資産運用",
]


def _request_bytes(url: str, timeout: int = 12) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _entry_datetime(entry: Any, resource_collector):
    for field in ("published", "updated", "created", "date"):
        parsed = resource_collector.parse_datetime(getattr(entry, field, None))
        if parsed is not None:
            return parsed
    return None


def _publisher(entry: Any) -> str:
    source = getattr(entry, "source", None)
    if isinstance(source, dict):
        return str(source.get("title") or "")
    if source is not None:
        return str(getattr(source, "title", "") or "")
    return ""


def _google_news_url(spec: dict) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(str(spec["query"]))
        + f"&hl={quote_plus(str(spec['hl']))}&gl={quote_plus(str(spec['gl']))}&ceid={quote_plus(str(spec['ceid']))}"
    )


def collect_google_news_query(label: str, spec: dict, limit: int, resource_collector) -> tuple[list[dict], str]:
    url = _google_news_url(spec)
    try:
        payload = _request_bytes(url)
    except Exception as error:
        return [], f"Google News {label}: failed - {error}"
    feed = feedparser.parse(payload)
    rows: list[dict] = []
    for index, entry in enumerate(list(getattr(feed, "entries", []) or []), start=1):
        title = str(getattr(entry, "title", "") or "").strip()
        link = str(getattr(entry, "link", "") or "").strip()
        if not title or not link:
            continue
        posted_at = _entry_datetime(entry, resource_collector)
        age = age_minutes(posted_at)
        if age is None or age > LIVE_FALLBACK_HOURS * 60:
            continue
        publisher = _publisher(entry)
        summary = str(getattr(entry, "summary", "") or "")
        item = resource_collector.make_resource(
            source=f"Google News Radar · {publisher or label}",
            meta={
                "source_type": "signal",
                "region": spec.get("gl", "Global"),
                "category": "Cross-site topic discovery",
            },
            title=title,
            url=link,
            excerpt=summary,
            posted_at=posted_at,
            rank=index,
        )
        row = item.to_row()
        row.update(
            {
                "signal_only": True,
                "signal_type": "google_news",
                "source_role": "aggregator",
                "source_tier": 3,
                "signal_query": label,
                "origin_publisher": publisher,
                "topic_signal_version": TOPIC_SIGNAL_COLLECTOR_VERSION,
            }
        )
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows, f"Google News {label}: {len(rows)} live signals"


def _entry_text(entry: Any) -> str:
    parts = [str(getattr(entry, "title", "") or ""), str(getattr(entry, "summary", "") or "")]
    try:
        for item in entry.items():
            key, value = item
            if "news_item" in str(key).lower():
                parts.append(str(value or ""))
    except Exception:
        pass
    return " ".join(parts)


def _finance_relevant(text: str) -> bool:
    lower = str(text or "").lower()
    return any(term.lower() in lower for term in TREND_RELEVANCE_TERMS)


def _traffic_value(entry: Any) -> str:
    try:
        for key, value in entry.items():
            if "traffic" in str(key).lower() and value:
                return str(value)
    except Exception:
        pass
    return ""


def collect_google_trends_jp(limit: int, resource_collector) -> tuple[list[dict], str]:
    url = "https://trends.google.com/trending/rss?geo=JP"
    try:
        payload = _request_bytes(url)
    except Exception as error:
        return [], f"Google Trends JP: failed - {error}"
    feed = feedparser.parse(payload)
    rows: list[dict] = []
    for index, entry in enumerate(list(getattr(feed, "entries", []) or []), start=1):
        title = str(getattr(entry, "title", "") or "").strip()
        if not title or not _finance_relevant(_entry_text(entry)):
            continue
        posted_at = _entry_datetime(entry, resource_collector) or datetime.now(timezone.utc)
        traffic = _traffic_value(entry)
        item = resource_collector.make_resource(
            source="Google Trends JP",
            meta={"source_type": "signal", "region": "Japan", "category": "Search attention"},
            title=title,
            url=str(getattr(entry, "link", "") or url),
            excerpt=f"Google Trending Now Japan attention signal. Approx traffic: {traffic or 'n/a'}",
            posted_at=posted_at,
            rank=index,
        )
        row = item.to_row()
        row.update(
            {
                "signal_only": True,
                "signal_type": "search_trend",
                "source_role": "search",
                "source_tier": 3,
                "trend_traffic": traffic,
                "origin_publisher": "Google Trends",
                "topic_signal_version": TOPIC_SIGNAL_COLLECTOR_VERSION,
            }
        )
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows, f"Google Trends JP: {len(rows)} finance/crypto attention signals"


def collect_topic_signals(mode: str, limit_per_query: int, resource_collector) -> tuple[list[dict], list[str]]:
    labels = list(GOOGLE_NEWS_QUERIES.keys())
    if str(mode).lower() != "story":
        labels = ["JP_CRYPTO", "JP_STABLE_POLICY", "GLOBAL_INSTITUTION", "GLOBAL_RISK"]

    rows: list[dict] = []
    logs: list[str] = []
    workers = min(8, len(labels) + 1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(collect_google_news_query, label, GOOGLE_NEWS_QUERIES[label], limit_per_query, resource_collector): label
            for label in labels
        }
        futures[pool.submit(collect_google_trends_jp, max(8, limit_per_query), resource_collector)] = "GOOGLE_TRENDS_JP"
        for future in as_completed(futures):
            try:
                found, log = future.result()
                rows.extend(found)
                logs.append(log)
            except Exception as error:
                logs.append(f"topic signal {futures[future]}: failed - {error}")

    unique: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("url") or row.get("title") or row.get("id") or "")
        if key and key not in unique:
            unique[key] = row
    return list(unique.values()), logs
