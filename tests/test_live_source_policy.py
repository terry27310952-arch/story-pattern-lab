from datetime import datetime, timedelta, timezone

from live_source_policy import apply_live_gate, freshness_bucket


def row(name: str, hours_old=None):
    now = datetime(2026, 8, 19, 5, 30, tzinfo=timezone.utc)
    posted = "" if hours_old is None else (now - timedelta(hours=hours_old)).isoformat()
    return {"id": name, "title": name, "posted_at": posted, "trader_score": 50}


def test_primary_24h_pool_blocks_fallback_when_enough():
    now = datetime(2026, 8, 19, 5, 30, tzinfo=timezone.utc)
    rows = [row(f"fresh-{i}", 2) for i in range(3)] + [row("fallback", 30), row("stale", 72), row("unknown")]
    selected, stats = apply_live_gate(rows, now=now, min_candidates=3)
    assert [item["id"] for item in selected] == ["fresh-0", "fresh-1", "fresh-2"]
    assert stats["fallback_used"] == 0
    assert stats["stale_rejected"] == 1
    assert stats["unknown_time_rejected"] == 1


def test_24_to_48h_is_only_sparse_pool_fallback():
    now = datetime(2026, 8, 19, 5, 30, tzinfo=timezone.utc)
    rows = [row("fresh", 4), row("fallback-a", 26), row("fallback-b", 40), row("stale", 49)]
    selected, stats = apply_live_gate(rows, now=now, min_candidates=3)
    assert [item["id"] for item in selected] == ["fresh", "fallback-a", "fallback-b"]
    assert stats["fallback_used"] == 2
    assert all(item["live_eligible"] for item in selected)


def test_missing_publication_time_never_counts_as_live():
    now = datetime(2026, 8, 19, 5, 30, tzinfo=timezone.utc)
    assert freshness_bucket("", now=now) == "unknown"
    assert freshness_bucket(row("old", 80)["posted_at"], now=now) == "stale"
    assert freshness_bucket(row("new", 1)["posted_at"], now=now) == "live"


if __name__ == "__main__":
    test_primary_24h_pool_blocks_fallback_when_enough()
    test_24_to_48h_is_only_sparse_pool_fallback()
    test_missing_publication_time_never_counts_as_live()
    print("live source policy tests passed")
