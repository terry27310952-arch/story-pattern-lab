from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.request import Request, urlopen


LIVE_SOURCE_POLICY_VERSION = "live-source-v1.0"
LIVE_PRIMARY_HOURS = 24
LIVE_FALLBACK_HOURS = 48
LIVE_MIN_CANDIDATES = 12


def _now_utc(now: Optional[datetime] = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def parse_row_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            from dateutil import parser as date_parser

            parsed = date_parser.parse(str(value))
        except Exception:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_minutes(value: Any, now: Optional[datetime] = None) -> Optional[int]:
    posted_at = parse_row_datetime(value)
    if posted_at is None:
        return None
    delta = (_now_utc(now) - posted_at).total_seconds() / 60
    # Small publisher clock skews must not turn a fresh article into an error.
    return max(0, int(delta))


def freshness_bucket(
    value: Any,
    *,
    now: Optional[datetime] = None,
    primary_hours: int = LIVE_PRIMARY_HOURS,
    fallback_hours: int = LIVE_FALLBACK_HOURS,
) -> str:
    age = age_minutes(value, now=now)
    if age is None:
        return "unknown"
    if age <= primary_hours * 60:
        return "live"
    if age <= fallback_hours * 60:
        return "fallback"
    return "stale"


def freshness_label(age: Optional[int], bucket: str) -> str:
    if age is None:
        return "시간 미확인"
    if age < 60:
        base = f"{age}분 전"
    else:
        hours = age // 60
        base = f"{hours}시간 전"
    return f"{base} · 48h fallback" if bucket == "fallback" else base


def annotate_freshness(
    row: dict,
    *,
    now: Optional[datetime] = None,
    primary_hours: int = LIVE_PRIMARY_HOURS,
    fallback_hours: int = LIVE_FALLBACK_HOURS,
) -> dict:
    copied = dict(row or {})
    age = age_minutes(copied.get("posted_at"), now=now)
    bucket = freshness_bucket(
        copied.get("posted_at"),
        now=now,
        primary_hours=primary_hours,
        fallback_hours=fallback_hours,
    )
    copied["freshness_min"] = age
    copied["freshness_bucket"] = bucket
    copied["freshness_label"] = freshness_label(age, bucket)
    copied["live_eligible"] = bucket in {"live", "fallback"}
    copied["live_primary"] = bucket == "live"
    copied["live_policy_version"] = LIVE_SOURCE_POLICY_VERSION
    return copied


def apply_live_gate(
    rows: list[dict],
    *,
    now: Optional[datetime] = None,
    primary_hours: int = LIVE_PRIMARY_HOURS,
    fallback_hours: int = LIVE_FALLBACK_HOURS,
    min_candidates: int = LIVE_MIN_CANDIDATES,
) -> tuple[list[dict], dict]:
    """Return only verifiably recent rows.

    Freshness is a gate, not a score bonus:
    - <= 24h: primary live pool
    - 24-48h: used only when the primary pool is sparse
    - > 48h: rejected
    - missing/invalid publication time: rejected from live candidates
    """

    annotated = [
        annotate_freshness(
            row,
            now=now,
            primary_hours=primary_hours,
            fallback_hours=fallback_hours,
        )
        for row in (rows or [])
        if isinstance(row, dict)
    ]
    primary = [row for row in annotated if row.get("freshness_bucket") == "live"]
    fallback = [row for row in annotated if row.get("freshness_bucket") == "fallback"]
    stale = [row for row in annotated if row.get("freshness_bucket") == "stale"]
    unknown = [row for row in annotated if row.get("freshness_bucket") == "unknown"]

    target = max(1, int(min_candidates or 1))
    selected = list(primary)
    fallback_used = False
    if len(selected) < target and fallback:
        fallback_used = True
        needed = target - len(selected)
        selected.extend(fallback[:needed])

    stats = {
        "policy": LIVE_SOURCE_POLICY_VERSION,
        "primary_hours": primary_hours,
        "fallback_hours": fallback_hours,
        "min_candidates": target,
        "input": len(annotated),
        "primary": len(primary),
        "fallback_available": len(fallback),
        "fallback_used": max(0, len(selected) - len(primary)),
        "stale_rejected": len(stale),
        "unknown_time_rejected": len(unknown),
        "output": len(selected),
        "window": "24h" if not fallback_used else "48h fallback",
    }
    return selected, stats


def live_gate_log(stats: dict) -> str:
    return (
        f"LIVE FIRST {stats.get('policy')}: {stats.get('output', 0)} candidates · "
        f"primary<=24h {stats.get('primary', 0)} · "
        f"fallback24-48h {stats.get('fallback_used', 0)} · "
        f"stale>48h rejected {stats.get('stale_rejected', 0)} · "
        f"time-unknown rejected {stats.get('unknown_time_rejected', 0)}"
    )


def _entry_datetime(entry: Any, resource_collector) -> Optional[datetime]:
    for field in ("published", "updated", "created", "date"):
        parsed = resource_collector.parse_datetime(getattr(entry, field, None))
        if parsed is not None:
            return parsed
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, field, None)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
            except Exception:
                continue
    return None


def apply_live_patch(resource_collector) -> None:
    """Force RSS collection to perform an uncached request and reject stale entries early."""

    if getattr(resource_collector, "_kiyosaki_live_source_policy", None) == LIVE_SOURCE_POLICY_VERSION:
        return

    def collect_rss_live(source_name: str, meta: dict, limit: int):
        request = Request(
            meta["url"],
            headers={
                "User-Agent": resource_collector.USER_AGENT,
                "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8,ko;q=0.6",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                payload = response.read()
        except Exception as error:
            return [], f"{source_name}: LIVE RSS fetch failed - {error}"

        feed = resource_collector.feedparser.parse(payload)
        entries = list(getattr(feed, "entries", []) or [])
        if getattr(feed, "bozo", False) and not entries:
            return [], f"{source_name}: LIVE RSS parse failed"

        items = []
        missing_time = 0
        stale = 0
        scanned = 0
        # Scan beyond the requested result count so pinned/stale entries cannot crowd out fresh ones.
        scan_limit = min(len(entries), max(int(limit) * 4, 80))
        for index, entry in enumerate(entries[:scan_limit], start=1):
            scanned += 1
            title = getattr(entry, "title", "")
            url = getattr(entry, "link", "")
            if not title or not url:
                continue
            posted_at = _entry_datetime(entry, resource_collector)
            age = age_minutes(posted_at)
            if age is None:
                missing_time += 1
                continue
            if age > LIVE_FALLBACK_HOURS * 60:
                stale += 1
                continue

            content_values = []
            for content_item in getattr(entry, "content", []) or []:
                value = getattr(content_item, "value", "")
                if value:
                    content_values.append(value)
            summary_source = max(
                [getattr(entry, "summary", ""), *content_values],
                key=lambda value: len(str(value)),
                default="",
            )
            items.append(
                resource_collector.make_resource(
                    source=source_name,
                    meta=meta,
                    title=title,
                    url=url,
                    excerpt=summary_source,
                    posted_at=posted_at,
                    rank=index,
                )
            )
            if len(items) >= int(limit):
                break

        return (
            items,
            f"{source_name}: LIVE fetched {len(items)} <=48h "
            f"(scanned {scanned}, stale {stale}, time-unknown {missing_time})",
        )

    resource_collector.collect_rss = collect_rss_live
    resource_collector._kiyosaki_live_source_policy = LIVE_SOURCE_POLICY_VERSION
