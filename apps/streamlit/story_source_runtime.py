from __future__ import annotations

from typing import Any

import story_engine


STORY_SOURCE_RUNTIME_VERSION = "story-source-v5.0"

# These sources already exist in resource_collector.RSS_SOURCES. They are added to the
# collection set because they more often publish institutional, company, policy and
# structural stories that can support a narrative carousel. This does not exclude any
# user-selected source.
STORY_RICH_DEFAULTS = [
    "Blockworks",
    "BeInCrypto",
    "CRYPTO TIMES JP",
]

# A small editorial prior. The actual article story score still dominates. This avoids
# letting a weak article from a preferred publisher outrank a genuinely strong story.
SOURCE_EDITORIAL_BONUS = {
    "Blockworks": 8.0,
    "NADA NEWS / CoinDesk Japan": 6.0,
    "CoinDesk Global": 6.0,
    "Decrypt": 5.0,
    "CRYPTO TIMES JP": 4.0,
    "BeInCrypto": 3.0,
    "U.Today": -2.0,
}


def _rows(result: Any) -> tuple[list[dict] | None, str | None]:
    if isinstance(result, list) and all(isinstance(item, dict) for item in result):
        return result, "list"
    if isinstance(result, tuple) and result and isinstance(result[0], list) and all(isinstance(item, dict) for item in result[0]):
        return result[0], "tuple"
    if isinstance(result, dict):
        for key in ["resources", "items", "rows"]:
            value = result.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value, f"dict:{key}"
    return None, None


def _replace_rows(result: Any, kind: str | None, rows: list[dict]):
    if kind == "list":
        return rows
    if kind == "tuple":
        parts = list(result)
        parts[0] = rows
        return tuple(parts)
    if kind and kind.startswith("dict:"):
        key = kind.split(":", 1)[1]
        copied = dict(result)
        copied[key] = rows
        return copied
    return result


def _apply_source_prior(rows: list[dict]) -> list[dict]:
    ranked: list[dict] = []
    for raw in rows:
        row = story_engine.annotate_resource(raw)
        bonus = SOURCE_EDITORIAL_BONUS.get(str(row.get("source") or ""), 0.0)
        row["story_source_bonus"] = bonus
        row["editorial_score"] = round(
            max(0.0, min(100.0, float(row.get("editorial_score") or 0.0) + bonus)),
            2,
        )
        ranked.append(row)
    return sorted(
        ranked,
        key=lambda row: (
            float(row.get("editorial_score") or 0.0),
            float(row.get("story_score") or 0.0),
            float(row.get("trader_score") or 0.0),
        ),
        reverse=True,
    )


def apply_source_patch(resource_collector) -> None:
    if getattr(resource_collector, "_kiyosaki_story_source_version", None) == STORY_SOURCE_RUNTIME_VERSION:
        return

    original_collect = resource_collector.collect_resources

    def collect_resources(*args, **kwargs):
        mutable_args = list(args)
        if mutable_args:
            selected_rss = list(mutable_args[0] or [])
            for source in STORY_RICH_DEFAULTS:
                if source in getattr(resource_collector, "RSS_SOURCES", {}) and source not in selected_rss:
                    selected_rss.append(source)
            mutable_args[0] = selected_rss
        elif "selected_rss" in kwargs:
            selected_rss = list(kwargs.get("selected_rss") or [])
            for source in STORY_RICH_DEFAULTS:
                if source in getattr(resource_collector, "RSS_SOURCES", {}) and source not in selected_rss:
                    selected_rss.append(source)
            kwargs["selected_rss"] = selected_rss
        elif "rss_sources" in kwargs:
            selected_rss = list(kwargs.get("rss_sources") or [])
            for source in STORY_RICH_DEFAULTS:
                if source in getattr(resource_collector, "RSS_SOURCES", {}) and source not in selected_rss:
                    selected_rss.append(source)
            kwargs["rss_sources"] = selected_rss

        result = original_collect(*tuple(mutable_args), **kwargs)
        rows, kind = _rows(result)
        if rows is None:
            return result
        return _replace_rows(result, kind, _apply_source_prior(rows))

    resource_collector.collect_resources = collect_resources
    resource_collector._kiyosaki_story_source_version = STORY_SOURCE_RUNTIME_VERSION
