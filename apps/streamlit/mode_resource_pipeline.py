from __future__ import annotations

from typing import Iterable

import story_engine
from content_modes import MODE_STORY, MODE_TRADER, rank_resources
from resource_collector import (
    PUBLIC_LIST_SOURCES,
    RSS_SOURCES,
    collect_resources as collect_core_resources,
    collect_source,
)


MODE_RESOURCE_PIPELINE_VERSION = "mode-resources-v6.0"

# These are not mixed into the trader defaults. They exist specifically so story mode
# can discover policy/regulatory narratives instead of being limited to crypto market
# headlines. The generic public-list parser still filters links for crypto/digital-asset
# relevance, so unrelated regulator press releases do not flood the candidate pool.
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
        # Keep the deeper copy when two collection paths return the same URL/item.
        prev_depth = len(str(previous.get("excerpt") or previous.get("material") or ""))
        next_depth = len(str(row.get("excerpt") or row.get("material") or ""))
        if next_depth > prev_depth:
            unique[key] = row
    return list(unique.values())


def _collect_extra_public(names: list[str], limit: int) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    logs: list[str] = []
    for name in names:
        meta = STORY_EXTRA_PUBLIC_SOURCES.get(name)
        if not meta:
            continue
        items, log = collect_source(name, meta, limit)
        rows.extend(item.to_row() if hasattr(item, "to_row") else dict(item) for item in items)
        logs.append(log)
    return rows, logs


def collect_for_mode(
    mode: str,
    rss_names: list[str],
    public_names: list[str],
    limit: int,
) -> tuple[list[dict], list[str]]:
    core_public = [name for name in public_names if name in PUBLIC_LIST_SOURCES]
    extra_public = [name for name in public_names if name in STORY_EXTRA_PUBLIC_SOURCES]

    rows, logs = collect_core_resources(
        [name for name in rss_names if name in RSS_SOURCES],
        core_public,
        limit,
    )
    if mode == MODE_STORY and extra_public:
        extra_rows, extra_logs = _collect_extra_public(extra_public, limit)
        rows = [*rows, *extra_rows]
        logs = [*logs, *extra_logs]

    rows = _dedupe_rows(rows)
    if mode == MODE_STORY:
        rows = story_engine.annotate_resources(rows)
        logs.append(
            f"story mode: ranked {len(rows)} resources by story_score/editorial_score; "
            "community chatter is not a default source"
        )
    else:
        rows = rank_resources(MODE_TRADER, rows)
        logs.append(f"trader mode: ranked {len(rows)} resources by trader_score")
    return rows, logs
