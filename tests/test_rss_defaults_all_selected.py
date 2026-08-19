from __future__ import annotations

from content_modes import MODE_STORY, MODE_TRADER, default_sources


def test_all_rss_sources_are_selected_by_default() -> None:
    rss = {"A": {}, "B": {}, "C": {}}
    public = {"Japan FSA Crypto Policy": {}, "CoinMarketCap Headlines": {}}

    story_rss, _ = default_sources(MODE_STORY, rss, public)
    trader_rss, _ = default_sources(MODE_TRADER, rss, public)

    assert set(story_rss) == set(rss.keys())
    assert set(trader_rss) == set(rss.keys())
    assert len(story_rss) == len(rss)
    assert len(trader_rss) == len(rss)
