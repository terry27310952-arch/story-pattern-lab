from __future__ import annotations

from typing import Iterable


EXPANDED_SOURCE_REGISTRY_VERSION = "expanded-sources-v1.0"

EXPANDED_RSS_SOURCES: dict[str, dict] = {
    "CoinPost JP": {
        "url": "https://coinpost.jp/?feed=rss2",
        "category": "Japan crypto breaking news",
        "region": "Japan",
        "source_type": "rss",
        "source_role": "editorial",
        "tier": 1,
    },
    "Cointelegraph Japan": {
        "url": "https://jp.cointelegraph.com/rss",
        "category": "Japan crypto and Web3 news",
        "region": "Japan",
        "source_type": "rss",
        "source_role": "editorial",
        "tier": 1,
    },
    "あたらしい経済": {
        "url": "https://www.neweconomy.jp/feed",
        "category": "Japan blockchain and digital asset business",
        "region": "Japan",
        "source_type": "rss",
        "source_role": "editorial",
        "tier": 1,
    },
    "Kraken Blog": {
        "url": "https://blog.kraken.com/feed",
        "category": "Exchange product, institutional and market updates",
        "region": "Global",
        "source_type": "rss",
        "source_role": "exchange",
        "tier": 1,
    },
    "CryptoSlate": {
        "url": "https://cryptoslate.com/feed/",
        "category": "Global crypto news and market structure",
        "region": "Global",
        "source_type": "rss",
        "source_role": "editorial",
        "tier": 2,
    },
    "Bitcoin.com News": {
        "url": "https://news.bitcoin.com/feed/",
        "category": "Global crypto news",
        "region": "Global",
        "source_type": "rss",
        "source_role": "editorial",
        "tier": 2,
    },
    "SEC Press Releases": {
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "category": "US securities regulation and enforcement",
        "region": "US",
        "source_type": "official",
        "source_role": "official",
        "tier": 1,
    },
    "CFTC Press Releases": {
        "url": "https://www.cftc.gov/RSS/RSSGP/rssgp.xml",
        "category": "US derivatives regulation and enforcement",
        "region": "US",
        "source_type": "official",
        "source_role": "official",
        "tier": 1,
    },
    "Federal Reserve Press Releases": {
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "category": "US monetary policy and financial regulation",
        "region": "US",
        "source_type": "official",
        "source_role": "official",
        "tier": 1,
    },
    "Reddit r/CryptoCurrency": {
        "url": "https://www.reddit.com/r/CryptoCurrency/.rss",
        "category": "Crypto community discussion",
        "region": "Global Community",
        "source_type": "community",
        "source_role": "community",
        "tier": 3,
        "signal_only": True,
    },
    "Reddit r/Bitcoin": {
        "url": "https://www.reddit.com/r/Bitcoin/.rss",
        "category": "Bitcoin community discussion",
        "region": "Global Community",
        "source_type": "community",
        "source_role": "community",
        "tier": 3,
        "signal_only": True,
    },
}

STORY_DISCOVERY_DEFAULTS = [
    "CoinPost JP",
    "Cointelegraph Japan",
    "あたらしい経済",
    "Kraken Blog",
    "CryptoSlate",
    "SEC Press Releases",
    "CFTC Press Releases",
    "Federal Reserve Press Releases",
    "Reddit r/CryptoCurrency",
    "Reddit r/Bitcoin",
]

TRADER_DISCOVERY_DEFAULTS = [
    "CoinPost JP",
    "Cointelegraph Japan",
    "Kraken Blog",
    "CryptoSlate",
    "SEC Press Releases",
    "CFTC Press Releases",
    "Federal Reserve Press Releases",
]


def apply_expanded_sources(resource_collector) -> None:
    registry = getattr(resource_collector, "RSS_SOURCES", None)
    if not isinstance(registry, dict):
        return
    for name, meta in EXPANDED_RSS_SOURCES.items():
        registry.setdefault(name, dict(meta))


def discovery_sources(mode: str) -> list[str]:
    return list(STORY_DISCOVERY_DEFAULTS if str(mode).lower() == "story" else TRADER_DISCOVERY_DEFAULTS)


def merge_source_names(selected: Iterable[str], automatic: Iterable[str]) -> list[str]:
    out: list[str] = []
    for name in [*(selected or []), *(automatic or [])]:
        if name and name not in out:
            out.append(name)
    return out


def source_profile(name: str) -> dict:
    return dict(EXPANDED_RSS_SOURCES.get(name) or {})


def annotate_source_metadata(rows: list[dict]) -> list[dict]:
    annotated: list[dict] = []
    for raw in rows or []:
        row = dict(raw or {})
        profile = source_profile(str(row.get("source") or ""))
        source_type = str(row.get("source_type") or "")
        if source_type == "official":
            role = "official"
        elif source_type == "community":
            role = "community"
        else:
            role = str(profile.get("source_role") or "editorial")
        row["source_role"] = role
        row["source_tier"] = int(profile.get("tier") or (1 if role in {"official", "editorial"} else 3))
        row["signal_only"] = bool(profile.get("signal_only", False))
        row["source_registry_version"] = EXPANDED_SOURCE_REGISTRY_VERSION
        annotated.append(row)
    return annotated
