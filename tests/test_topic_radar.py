from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "apps" / "streamlit"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from expanded_source_registry import EXPANDED_RSS_SOURCES, annotate_source_metadata  # noqa: E402
from topic_radar import apply_story_heat_blend, apply_topic_radar  # noqa: E402


def _row(rid: str, title: str, hours: float, *, source: str, source_type: str = "rss", signal_only: bool = False, signal_type: str = "", role: str = "editorial") -> dict:
    now = datetime(2026, 8, 19, 6, 0, tzinfo=timezone.utc)
    return {
        "id": rid,
        "title": title,
        "source": source,
        "source_type": source_type,
        "source_role": role,
        "signal_only": signal_only,
        "signal_type": signal_type,
        "posted_at": (now - timedelta(hours=hours)).isoformat(),
        "excerpt": title,
        "story_score": 60.0,
    }


def test_registry_expanded():
    required = {"CoinPost JP", "Cointelegraph Japan", "SEC Press Releases", "Federal Reserve Press Releases", "Reddit r/CryptoCurrency"}
    assert required.issubset(EXPANDED_RSS_SOURCES)
    assert len(EXPANDED_RSS_SOURCES) >= 10


def test_signal_only_metadata():
    rows = annotate_source_metadata([
        {"id": "r", "source": "Reddit r/CryptoCurrency", "source_type": "community"},
        {"id": "c", "source": "CoinPost JP", "source_type": "rss"},
    ])
    lookup = {row["id"]: row for row in rows}
    assert lookup["r"]["signal_only"] is True
    assert lookup["r"]["source_role"] == "community"
    assert lookup["c"]["signal_only"] is False


def test_cross_source_topic_heat_beats_single_source():
    now = datetime(2026, 8, 19, 6, 0, tzinfo=timezone.utc)
    rows = [
        _row("direct-hot", "Tether USDT stablecoin regulation plan draws new scrutiny", 1.0, source="CoinPost JP"),
        _row("signal-news", "Tether USDT stablecoin regulation faces fresh policy debate", 0.5, source="Google News Radar · Reuters", source_type="signal", signal_only=True, signal_type="google_news", role="aggregator"),
        _row("signal-community", "Tether USDT stablecoin regulation discussion", 2.0, source="Reddit r/CryptoCurrency", source_type="community", signal_only=True, role="community"),
        _row("direct-cold", "Solana developer tooling update improves local test workflow", 0.5, source="CryptoSlate"),
    ]
    annotated, clusters = apply_topic_radar(rows, now=now)
    lookup = {row["id"]: row for row in annotated}
    assert lookup["direct-hot"]["topic_heat_score"] > lookup["direct-cold"]["topic_heat_score"]
    assert lookup["direct-hot"]["topic_source_count"] >= 3
    assert lookup["direct-hot"]["topic_signal_count"] >= 2
    assert clusters[0]["topic_heat_score"] >= lookup["direct-hot"]["topic_heat_score"]


def test_story_blend_rewards_audience_heat_without_replacing_quality():
    rows = [
        {"id": "hot", "story_score": 60, "topic_heat_score": 92, "audience_pull_score": 84},
        {"id": "cold", "story_score": 60, "topic_heat_score": 25, "audience_pull_score": 30},
        {"id": "quality", "story_score": 90, "topic_heat_score": 20, "audience_pull_score": 20},
    ]
    blended = apply_story_heat_blend(rows)
    lookup = {row["id"]: row for row in blended}
    assert lookup["hot"]["story_score"] > lookup["cold"]["story_score"]
    assert lookup["quality"]["story_score"] > 55
    assert lookup["hot"]["base_story_score"] == 60


def main():
    test_registry_expanded()
    test_signal_only_metadata()
    test_cross_source_topic_heat_beats_single_source()
    test_story_blend_rewards_audience_heat_without_replacing_quality()
    print("topic radar tests: 4/4 passed")


if __name__ == "__main__":
    main()
