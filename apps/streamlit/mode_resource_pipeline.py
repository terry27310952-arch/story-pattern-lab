from __future__ import annotations

from html import unescape
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import story_engine_v3 as story_engine
from content_modes import MODE_STORY, MODE_TRADER, rank_resources
from resource_collector import (
    PUBLIC_LIST_SOURCES,
    RSS_SOURCES,
    LinkTextParser,
    USER_AGENT,
    clean_html,
    collect_resources as collect_core_resources,
    decode_html,
    make_resource,
)


MODE_RESOURCE_PIPELINE_VERSION = "mode-resources-v8.0"

STORY_EXTRA_PUBLIC_SOURCES = {
    "SEC Press Releases": {
        "url": "https://www.sec.gov/newsroom/press-releases",
        "category": "US securities policy and enforcement",
        "region": "US",
        "source_type": "official",
        "parser": "story_public",
    },
    "CFTC Press Releases": {
        "url": "https://www.cftc.gov/PressRoom/PressReleases",
        "category": "US derivatives policy and enforcement",
        "region": "US",
        "source_type": "official",
        "parser": "story_public",
    },
    "Japan FSA Crypto Policy": {
        "url": "https://www.fsa.go.jp/policy/virtual_currency02/index.html",
        "category": "Japan crypto and payment regulation",
        "region": "Japan",
        "source_type": "official",
        "parser": "story_public",
    },
}

STORY_LINK_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "crypto", "digital asset", "stablecoin", "token",
    "blockchain", "etf", "exchange", "custody", "mining", "sec", "cftc", "data center", "ai infrastructure",
    "wall street", "valuation", "shiller", "cape", "institution", "treasury",
    "暗号資産", "仮想通貨", "ビットコイン", "イーサリアム", "ステーブルコイン", "データセンター", "マイニング",
    "ブロックチェーン", "交換業", "電子決済", "資金決済", "規制", "金融庁",
]


def story_public_registry() -> dict[str, dict]:
    return {**PUBLIC_LIST_SOURCES, **STORY_EXTRA_PUBLIC_SOURCES}


def available_public_registry(mode: str) -> dict[str, dict]:
    return story_public_registry() if mode == MODE_STORY else dict(PUBLIC_LIST_SOURCES)


def _dedupe_rows(rows: Iterable[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for raw in rows:
        row = dict(raw or {})
        key = str(row.get("id") or row.get("url") or row.get("title") or "")
        if not key:
            continue
        previous = unique.get(key)
        if previous is None:
            unique[key] = row
            continue
        prev_depth = len(str(previous.get("excerpt") or previous.get("material") or ""))
        next_depth = len(str(row.get("excerpt") or row.get("material") or ""))
        if next_depth > prev_depth:
            unique[key] = row
    return list(unique.values())


def _story_link_relevant(text: str) -> bool:
    lower = unescape(str(text or "")).lower()
    return any(keyword.lower() in lower for keyword in STORY_LINK_KEYWORDS)


def _collect_story_public_source(source_name: str, meta: dict, limit: int) -> tuple[list[dict], str]:
    request = Request(
        meta["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7,ko;q=0.6",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            html = decode_html(response.read(), response.headers.get("Content-Type", ""))
    except Exception as error:
        return [], f"{source_name}: failed - {error}"

    parser = LinkTextParser()
    parser.feed(html)
    seen: set[str] = set()
    rows: list[dict] = []
    for href, raw_text in parser.links:
        text = clean_html(raw_text, limit=300)
        if len(text) < 8 or not _story_link_relevant(text):
            continue
        url = urljoin(meta["url"], href)
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        item = make_resource(
            source=source_name,
            meta=meta,
            title=text,
            url=url,
            excerpt="Official policy/regulatory source collected for story-mode evidence enrichment.",
            posted_at=None,
            rank=len(rows) + 1,
        )
        rows.append(item.to_row())
        if len(rows) >= limit:
            break
    return rows, f"{source_name}: collected {len(rows)} story-relevant official links"


def _collect_extra_public(names: list[str], limit: int) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    logs: list[str] = []
    for name in names:
        meta = STORY_EXTRA_PUBLIC_SOURCES.get(name)
        if not meta:
            continue
        source_rows, log = _collect_story_public_source(name, meta, limit)
        rows.extend(source_rows)
        logs.append(log)
    return rows, logs


def collect_for_mode(mode: str, rss_names: list[str], public_names: list[str], limit: int) -> tuple[list[dict], list[str]]:
    core_public = [name for name in public_names if name in PUBLIC_LIST_SOURCES]
    extra_public = [name for name in public_names if name in STORY_EXTRA_PUBLIC_SOURCES]

    rows, logs = collect_core_resources([name for name in rss_names if name in RSS_SOURCES], core_public, limit)
    if mode == MODE_STORY and extra_public:
        extra_rows, extra_logs = _collect_extra_public(extra_public, limit)
        rows = [*rows, *extra_rows]
        logs = [*logs, *extra_logs]

    rows = _dedupe_rows(rows)
    if mode == MODE_STORY:
        rows = story_engine.annotate_resources(rows)
        logs.append(
            f"story mode: ranked {len(rows)} resources by {story_engine.STORY_ENGINE_VERSION}; "
            "narrative specificity, transformation, evidence and visual potential are prioritized"
        )
    else:
        rows = rank_resources(MODE_TRADER, rows)
        logs.append(f"trader mode: ranked {len(rows)} resources by trader_score")
    return rows, logs
