from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import resource_collector as core_collector
import story_source_engine_v5 as story_engine
from content_modes import MODE_STORY, MODE_TRADER, rank_resources
from expanded_source_registry import (
    EXPANDED_SOURCE_REGISTRY_VERSION,
    annotate_source_metadata,
    apply_expanded_sources,
    discovery_sources,
    merge_source_names,
)
from live_source_policy import (
    LIVE_MIN_CANDIDATES,
    LIVE_SOURCE_POLICY_VERSION,
    apply_live_gate,
    apply_live_patch,
    live_gate_log,
)
from topic_radar import (
    TOPIC_RADAR_VERSION,
    apply_story_heat_blend,
    apply_topic_radar,
    apply_trader_heat_blend,
)
from topic_signal_collector import TOPIC_SIGNAL_COLLECTOR_VERSION, collect_topic_signals
from resource_collector import (
    PUBLIC_LIST_SOURCES,
    RSS_SOURCES,
    LinkTextParser,
    USER_AGENT,
    clean_html,
    decode_html,
    make_resource,
)


MODE_RESOURCE_PIPELINE_VERSION = "mode-resources-v11.2-radar-visible"
MAX_DIRECT_WORKERS = 12
_STREAMLIT_STATE_VERSION_KEY = "_mode_resource_pipeline_version"

apply_expanded_sources(core_collector)
apply_live_patch(core_collector)

STORY_EXTRA_PUBLIC_SOURCES = {
    "SEC Press Releases (HTML fallback)": {
        "url": "https://www.sec.gov/newsroom/press-releases",
        "category": "US securities policy and enforcement",
        "region": "US",
        "source_type": "official",
        "parser": "story_public",
    },
    "CFTC Press Releases (HTML fallback)": {
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


def _invalidate_stale_streamlit_collection_state() -> None:
    """Make a newly deployed collector unmistakable in the UI.

    Streamlit sessions can preserve old resources while the code reruns. When the
    source-pipeline version changes, throw away previously collected candidates so
    an old four-day-old list cannot masquerade as a successful new deployment.
    """
    try:
        import streamlit as st

        current = st.session_state.get(_STREAMLIT_STATE_VERSION_KEY)
        if current != MODE_RESOURCE_PIPELINE_VERSION:
            stale_keys = [
                "resources_trader", "resources_story",
                "logs_trader", "logs_story",
                "selected_ids_trader", "selected_ids_story",
                "story_event_candidates", "selected_story_event_id",
                "enriched_trader", "enriched_story",
                "trader_brief", "trader_package", "story_package",
            ]
            for key in stale_keys:
                st.session_state.pop(key, None)
            st.session_state[_STREAMLIT_STATE_VERSION_KEY] = MODE_RESOURCE_PIPELINE_VERSION
            st.session_state["_live_source_refresh_required"] = True

        st.sidebar.success("LIVE FIRST + TOPIC RADAR 활성화")
        st.sidebar.caption(
            f"Source Pipeline · {MODE_RESOURCE_PIPELINE_VERSION} · "
            f"LIVE {LIVE_SOURCE_POLICY_VERSION} · Radar {TOPIC_RADAR_VERSION}"
        )
        st.sidebar.caption(
            "자동 탐색 · " + ", ".join(discovery_sources(MODE_STORY)[:8]) + " …"
        )
        if st.session_state.get("_live_source_refresh_required"):
            st.sidebar.warning("수집기 버전이 변경되었습니다. 최신 리소스를 다시 수집하세요.")
    except Exception:
        return


def story_public_registry() -> dict[str, dict]:
    return {**PUBLIC_LIST_SOURCES, **STORY_EXTRA_PUBLIC_SOURCES}


def available_public_registry(mode: str) -> dict[str, dict]:
    _invalidate_stale_streamlit_collection_state()
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
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
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
        row = item.to_row()
        row["source_role"] = "official"
        row["source_tier"] = 1
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows, f"{source_name}: collected {len(rows)} story-relevant official links (time verification required)"


def _collect_extra_public(names: list[str], limit: int) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    logs: list[str] = []
    if not names:
        return rows, logs
    workers = min(4, len(names))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_collect_story_public_source, name, STORY_EXTRA_PUBLIC_SOURCES[name], limit): name
            for name in names
            if name in STORY_EXTRA_PUBLIC_SOURCES
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                source_rows, log = future.result()
                rows.extend(source_rows)
                logs.append(log)
            except Exception as error:
                logs.append(f"{name}: failed - {error}")
    return rows, logs


def _collect_core_parallel(rss_names: list[str], public_names: list[str], limit: int) -> tuple[list[dict], list[str]]:
    tasks: list[tuple[str, dict]] = []
    for name in rss_names:
        if name in RSS_SOURCES:
            tasks.append((name, RSS_SOURCES[name]))
    for name in public_names:
        if name in PUBLIC_LIST_SOURCES:
            tasks.append((name, PUBLIC_LIST_SOURCES[name]))
    if not tasks:
        return [], []

    started = time.monotonic()
    collected = []
    logs: list[str] = []
    workers = min(MAX_DIRECT_WORKERS, max(1, len(tasks)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(core_collector.collect_source, name, meta, limit): name
            for name, meta in tasks
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                items, log = future.result()
                collected.extend(items or [])
                logs.append(log)
            except Exception as error:
                logs.append(f"{name}: parallel collection failed - {error}")

    unique = {}
    for item in collected:
        row = item.to_row() if hasattr(item, "to_row") else dict(item or {})
        key = str(row.get("id") or row.get("url") or row.get("title") or "")
        if not key:
            continue
        previous = unique.get(key)
        if previous is None:
            unique[key] = row
            continue
        prev_depth = len(str(previous.get("excerpt") or ""))
        next_depth = len(str(row.get("excerpt") or ""))
        if next_depth > prev_depth:
            unique[key] = row

    rows = list(unique.values())
    rows.sort(key=lambda row: float(row.get("trader_score") or 0), reverse=True)
    elapsed = time.monotonic() - started
    logs.append(
        f"parallel collector: {len(tasks)} sources · {workers} workers · "
        f"{len(rows)} unique rows · {elapsed:.2f}s"
    )
    return rows, logs


def _top_radar_logs(clusters: list[dict], limit: int = 5) -> list[str]:
    logs: list[str] = []
    for index, cluster in enumerate((clusters or [])[:limit], start=1):
        anchors = ",".join(cluster.get("anchors") or []) or "unlabeled"
        themes = ",".join(cluster.get("themes") or []) or "general"
        reasons = " / ".join(cluster.get("reasons") or [])
        logs.append(
            f"topic radar #{index}: heat {cluster.get('topic_heat_score', 0):.1f} · "
            f"{anchors} · {themes} · sources {cluster.get('source_count', 0)} · {reasons}"
        )
    return logs


def collect_for_mode(mode: str, rss_names: list[str], public_names: list[str], limit: int) -> tuple[list[dict], list[str]]:
    expanded_rss = merge_source_names(rss_names, discovery_sources(mode))
    expanded_rss = [name for name in expanded_rss if name in RSS_SOURCES]

    core_public = [name for name in public_names if name in PUBLIC_LIST_SOURCES]
    extra_public = [name for name in public_names if name in STORY_EXTRA_PUBLIC_SOURCES]

    direct_rows, logs = _collect_core_parallel(expanded_rss, core_public, limit)
    if mode == MODE_STORY and extra_public:
        extra_rows, extra_logs = _collect_extra_public(extra_public, limit)
        direct_rows = [*direct_rows, *extra_rows]
        logs = [*logs, *extra_logs]

    direct_rows = annotate_source_metadata(_dedupe_rows(direct_rows))

    embedded_signal_rows = [row for row in direct_rows if row.get("signal_only")]
    evidence_rows = [row for row in direct_rows if not row.get("signal_only")]
    evidence_rows, freshness_stats = apply_live_gate(evidence_rows, min_candidates=LIVE_MIN_CANDIDATES)
    embedded_signal_rows, embedded_signal_stats = apply_live_gate(embedded_signal_rows, min_candidates=1)
    logs.append(live_gate_log(freshness_stats))
    if embedded_signal_rows or embedded_signal_stats.get("input"):
        logs.append(
            f"embedded attention signals: {embedded_signal_stats.get('output', 0)} live · "
            f"stale rejected {embedded_signal_stats.get('stale_rejected', 0)}"
        )

    signal_limit = max(6, min(18, int(limit) // 2))
    signal_rows, signal_logs = collect_topic_signals(mode, signal_limit, core_collector)
    signal_rows = _dedupe_rows([*embedded_signal_rows, *signal_rows])
    signal_rows, signal_freshness = apply_live_gate(signal_rows, min_candidates=1)
    logs.extend(signal_logs)
    logs.append(
        f"topic signals LIVE: {signal_freshness.get('output', 0)} · "
        f"stale rejected {signal_freshness.get('stale_rejected', 0)} · "
        f"time unknown rejected {signal_freshness.get('unknown_time_rejected', 0)}"
    )

    radar_rows, clusters = apply_topic_radar([*evidence_rows, *signal_rows])
    evidence_ids = {str(row.get("id") or "") for row in evidence_rows}
    rows = [row for row in radar_rows if str(row.get("id") or "") in evidence_ids]

    logs.append(
        f"source expansion: {EXPANDED_SOURCE_REGISTRY_VERSION} · direct feeds {len(expanded_rss)} · "
        f"topic signals {TOPIC_SIGNAL_COLLECTOR_VERSION}"
    )
    logs.append(
        f"topic radar: {TOPIC_RADAR_VERSION} · {len(clusters)} clusters · "
        "cross-source burst + audience pull + search/community attention blended before ranking"
    )
    logs.extend(_top_radar_logs(clusters))
    logs.append(f"live source policy: {LIVE_SOURCE_POLICY_VERSION}; latest-first gate applied before ranking")

    if mode == MODE_STORY:
        rows = story_engine.annotate_resources(rows)
        rows = apply_story_heat_blend(rows)
        logs.append(
            f"story mode: ranked {len(rows)} LIVE resources by {story_engine.STORY_ENGINE_VERSION} + {TOPIC_RADAR_VERSION}; "
            "story quality remains primary, with cross-site topic heat and audience pull as discovery multipliers"
        )
    else:
        rows = rank_resources(MODE_TRADER, rows)
        rows = apply_trader_heat_blend(rows)
        logs.append(
            f"trader mode: ranked {len(rows)} LIVE resources by trader_score + light {TOPIC_RADAR_VERSION} blend"
        )

    try:
        import streamlit as st
        st.session_state["_live_source_refresh_required"] = False
    except Exception:
        pass

    return rows, logs
