from __future__ import annotations

from dataclasses import dataclass


MODE_TRADER = "trader"
MODE_STORY = "story"

MODE_LABELS = {
    MODE_TRADER: "트레이더 브리핑",
    MODE_STORY: "스토리텔링 콘텐츠",
}

TRADER_RSS_DEFAULTS = [
    "NADA NEWS / CoinDesk Japan",
    "CoinDesk Global",
    "Cointelegraph Global",
    "NewsBTC",
    "U.Today",
    "Blockworks",
    "CoinPost JP",
    "Cointelegraph Japan",
    "Kraken Blog",
    "CryptoSlate",
    "SEC Press Releases",
    "CFTC Press Releases",
    "Federal Reserve Press Releases",
]
TRADER_PUBLIC_DEFAULTS = [
    "CoinMarketCap Headlines",
    "Yahoo Finance JP Crypto",
    "Yahoo Finance JP Bitcoin",
    "5ch Crypto Board",
]

STORY_RSS_DEFAULTS = [
    "Blockworks",
    "Decrypt",
    "BeInCrypto",
    "CRYPTO TIMES JP",
    "NADA NEWS / CoinDesk Japan",
    "CoinDesk Global",
    "Cryptonews JP",
    "Coinspeaker JP",
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
STORY_PUBLIC_DEFAULTS = [
    "Japan FSA Crypto Policy",
    "SEC Press Releases",
    "CFTC Press Releases",
    "Yahoo Finance JP CoinPost",
    "Yahoo Finance JP CoinDesk Japan",
    "Yahoo Finance JP Crypto",
]


@dataclass(frozen=True)
class ModePolicy:
    mode: str
    primary_score: str
    default_select_count: int
    source_limit: int
    fetch_full_body: bool
    needs_market_snapshot: bool
    description: str


MODE_POLICIES = {
    MODE_TRADER: ModePolicy(
        mode=MODE_TRADER,
        primary_score="trader_score",
        default_select_count=20,
        source_limit=20,
        fetch_full_body=True,
        needs_market_snapshot=True,
        description="가격 영향, 최신성, BTC 기준축, 파생·거시·규제 재료를 우선합니다.",
    ),
    MODE_STORY: ModePolicy(
        mode=MODE_STORY,
        primary_score="story_score",
        default_select_count=12,
        source_limit=30,
        fetch_full_body=True,
        needs_market_snapshot=False,
        description="명확한 주체·사건·규모·변화·시각성이 있는 스토리 소재를 우선합니다.",
    ),
}


def valid_defaults(names: list[str], registry: dict) -> list[str]:
    return [name for name in names if name in registry]


def default_sources(mode: str, rss_registry: dict, public_registry: dict) -> tuple[list[str], list[str]]:
    if mode == MODE_STORY:
        return (
            valid_defaults(STORY_RSS_DEFAULTS, rss_registry),
            valid_defaults(STORY_PUBLIC_DEFAULTS, public_registry),
        )
    return (
        valid_defaults(TRADER_RSS_DEFAULTS, rss_registry),
        valid_defaults(TRADER_PUBLIC_DEFAULTS, public_registry),
    )


def mode_policy(mode: str) -> ModePolicy:
    return MODE_POLICIES.get(mode, MODE_POLICIES[MODE_TRADER])


def rank_resources(mode: str, rows: list[dict]) -> list[dict]:
    if mode == MODE_STORY:
        import story_engine_v3

        return story_engine_v3.annotate_resources([dict(row) for row in rows or []])
    return sorted(
        [dict(row) for row in rows or []],
        key=lambda row: (
            float(row.get("trader_score") or 0.0),
            -float(row.get("risk_score") or 0.0),
        ),
        reverse=True,
    )


def selection_score(mode: str, row: dict) -> float:
    key = mode_policy(mode).primary_score
    try:
        return float(row.get(key) or 0.0)
    except Exception:
        return 0.0
