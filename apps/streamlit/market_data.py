from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Optional
from urllib.parse import quote
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 StoryPatternLab/1.1; crypto-market-levels"
MARKET_SCHEMA_VERSION = "price-level-depth-v7-level-quality-derivatives-news"


TRADING_ASSETS = {
    "Bitcoin": {"symbol": "BTC", "pair": "BTCUSDT", "coingecko_id": "bitcoin", "step": 500},
    "Ethereum": {"symbol": "ETH", "pair": "ETHUSDT", "coingecko_id": "ethereum", "step": 50},
    "Solana": {"symbol": "SOL", "pair": "SOLUSDT", "coingecko_id": "solana", "step": 5},
    "XRP": {"symbol": "XRP", "pair": "XRPUSDT", "coingecko_id": "ripple", "step": 0.05},
    "Dogecoin": {"symbol": "DOGE", "pair": "DOGEUSDT", "coingecko_id": "dogecoin", "step": 0.005},
    "Chainlink": {"symbol": "LINK", "pair": "LINKUSDT", "coingecko_id": "chainlink", "step": 0.5},
}


YAHOO_ASSETS = {
    "Nikkei 225": {"symbol": "^N225", "unit": "JPY", "asset_class": "equity_index"},
    "Gold Futures": {"symbol": "GC=F", "unit": "USD", "asset_class": "commodity"},
    "Nasdaq Composite": {"symbol": "^IXIC", "unit": "USD", "asset_class": "equity_index"},
    "US Dollar Index": {"symbol": "DX-Y.NYB", "unit": "index", "asset_class": "fx"},
    "US 10Y Yield": {"symbol": "^TNX", "unit": "% x10", "asset_class": "rates"},
}


def fetch_json(url: str, timeout: int = 18) -> tuple[object | None, Optional[str]]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore")), None
    except Exception as error:
        return None, str(error)


def safe_float(value: object, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def pct_change(first: float | None, last: float | None) -> Optional[float]:
    if first in (None, 0) or last is None:
        return None
    return round(((last - first) / first) * 100, 2)


def distance_pct(level: float | None, current: float | None) -> Optional[float]:
    if level is None or current in (None, 0):
        return None
    return round(((level - current) / current) * 100, 2)


def round_price(value: float | None) -> float | None:
    if value is None:
        return None
    if abs(value) >= 1000:
        return round(value, 0)
    if abs(value) >= 100:
        return round(value, 2)
    if abs(value) >= 1:
        return round(value, 4)
    return round(value, 6)


def sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return mean(values[-period:])


def ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def rsi(values: list[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, cur in zip(values[-period - 1 : -1], values[-period:]):
        change = cur - prev
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def macd(values: list[float]) -> dict:
    if len(values) < 35:
        return {"macd": None, "signal": None, "histogram": None, "bias": "insufficient"}
    ema12 = ema_series(values, 12)
    ema26 = ema_series(values, 26)
    macd_line = [a - b for a, b in zip(ema12[-len(ema26) :], ema26)]
    signal = ema_series(macd_line, 9)
    histogram = macd_line[-1] - signal[-1]
    bias = "bullish" if histogram > 0 and macd_line[-1] > signal[-1] else "bearish" if histogram < 0 else "neutral"
    return {
        "macd": round(macd_line[-1], 4),
        "signal": round(signal[-1], 4),
        "histogram": round(histogram, 4),
        "bias": bias,
    }


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) <= period:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(closes)):
        true_ranges.append(max(highs[index] - lows[index], abs(highs[index] - closes[index - 1]), abs(lows[index] - closes[index - 1])))
    return mean(true_ranges[-period:])


def bollinger(values: list[float], period: int = 20, width: float = 2.0) -> dict:
    if len(values) < period:
        return {"middle": None, "upper": None, "lower": None, "bandwidth_pct": None}
    window = values[-period:]
    middle = mean(window)
    stdev = pstdev(window)
    upper = middle + width * stdev
    lower = middle - width * stdev
    return {
        "middle": round_price(middle),
        "upper": round_price(upper),
        "lower": round_price(lower),
        "bandwidth_pct": round(((upper - lower) / middle) * 100, 2) if middle else None,
    }


def parse_binance_klines(payload: object) -> list[dict]:
    candles: list[dict] = []
    if not isinstance(payload, list):
        return candles
    for row in payload:
        try:
            candles.append(
                {
                    "open_time": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        except Exception:
            continue
    return candles


def parse_coingecko_market_chart(payload: object) -> list[dict]:
    candles: list[dict] = []
    if not isinstance(payload, dict):
        return candles
    prices = payload.get("prices", [])
    volumes = payload.get("total_volumes", [])
    volume_by_time = {int(row[0]): safe_float(row[1], 0.0) or 0.0 for row in volumes if isinstance(row, list) and len(row) >= 2}
    previous_close: float | None = None
    for row in prices:
        if not isinstance(row, list) or len(row) < 2:
            continue
        timestamp = int(row[0])
        close = safe_float(row[1])
        if close is None:
            continue
        open_price = previous_close if previous_close is not None else close
        candles.append(
            {
                "open_time": timestamp,
                "open": open_price,
                "high": max(open_price, close),
                "low": min(open_price, close),
                "close": close,
                "volume": volume_by_time.get(timestamp, 0.0),
            }
        )
        previous_close = close
    return candles


def level_importance(distance_pct: float | None, reason: str) -> str:
    if distance_pct is None:
        return "watch"
    if abs(distance_pct) <= 1.0:
        return "immediate"
    if abs(distance_pct) <= 3.0:
        return "near"
    if any(word in reason for word in ["MA200", "90D", "30D"]):
        return "major"
    return "watch"


def dedupe_levels(levels: list[dict], current: float, tolerance_pct: float = 0.35) -> list[dict]:
    result: list[dict] = []
    for level in sorted(levels, key=lambda item: abs(item["level"] - current)):
        if any(abs(level["level"] - existing["level"]) / current * 100 <= tolerance_pct for existing in result):
            continue
        result.append(level)
    return result


def level_member_type(reason: str) -> str:
    lowered = reason.lower()
    if "ma" in lowered:
        return reason.replace(" ", "_").lower()
    if "bollinger" in lowered:
        return "bollinger"
    if "fib" in lowered:
        return "fibonacci"
    if "round" in lowered:
        return "round_number"
    if any(token in lowered for token in ["low", "high"]):
        return "horizontal_level"
    return "derived_level"


def candle_touch_count(level: float, highs: list[float], lows: list[float], tolerance: float) -> int:
    if tolerance <= 0:
        return 0
    touches = 0
    for high, low in zip(highs[-90:], lows[-90:]):
        if abs(high - level) <= tolerance or abs(low - level) <= tolerance or low <= level <= high:
            touches += 1
    return touches


def reaction_strength_for_level(level: float, current: float, highs: list[float], lows: list[float], closes: list[float], tolerance: float) -> float:
    if not closes or tolerance <= 0:
        return 0.0
    reactions: list[float] = []
    for index in range(max(1, len(closes) - 90), len(closes)):
        touched = abs(highs[index] - level) <= tolerance or abs(lows[index] - level) <= tolerance or lows[index] <= level <= highs[index]
        if touched:
            reactions.append(abs(closes[index] - level) / current)
    return round(min(1.0, mean(reactions) * 35), 3) if reactions else 0.0


def volume_confirmation_for_level(level: float, highs: list[float], lows: list[float], volumes: list[float], tolerance: float) -> float:
    if len(volumes) < 20 or tolerance <= 0:
        return 0.0
    avg_volume = mean([value for value in volumes[-30:] if value is not None] or [0.0])
    if avg_volume <= 0:
        return 0.0
    touch_volumes = [
        volumes[index]
        for index in range(max(0, len(volumes) - 90), len(volumes))
        if index < len(highs)
        and (abs(highs[index] - level) <= tolerance or abs(lows[index] - level) <= tolerance or lows[index] <= level <= highs[index])
    ]
    if not touch_volumes:
        return 0.0
    return round(min(1.0, mean(touch_volumes) / avg_volume - 0.75), 3)


def structural_reason_score(reason: str) -> float:
    reason_upper = reason.upper()
    score = 0.18
    if "90D" in reason_upper:
        score += 0.22
    if "30D" in reason_upper:
        score += 0.16
    if "7D" in reason_upper:
        score += 0.08
    if "MA200" in reason_upper:
        score += 0.2
    if "MA50" in reason_upper or "MA20" in reason_upper:
        score += 0.14
    if "FIB" in reason_upper:
        score += 0.16
    if "BOLLINGER" in reason_upper:
        score += 0.1
    if "ROUND" in reason_upper:
        score += 0.08
    return min(1.0, score)


def enrich_level_quality(
    level_row: dict,
    current: float,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    atr14: float | None,
) -> dict:
    level = safe_float(level_row.get("level"))
    if level is None:
        return level_row
    atr_value = atr14 if atr14 not in (None, 0) else None
    tolerance = max((atr_value or current * 0.005) * 0.25, current * 0.001)
    distance_atr = round(abs(level - current) / atr_value, 3) if atr_value else None
    touch_count = candle_touch_count(level, highs, lows, tolerance)
    reaction_strength = reaction_strength_for_level(level, current, highs, lows, closes, tolerance)
    volume_confirmation = volume_confirmation_for_level(level, highs, lows, volumes, tolerance)
    indicator_cluster = 1.0 if any(token in str(level_row.get("reason", "")).upper() for token in ["MA", "BOLLINGER", "FIB", "ROUND"]) else 0.0
    swing_significance = structural_reason_score(str(level_row.get("reason", "")))
    touch_score = min(1.0, touch_count / 4)
    distance_score = 0.05
    if distance_atr is not None:
        if distance_atr < 0.1:
            distance_score = 0.02
        elif distance_atr <= 2.5:
            distance_score = 0.16
        elif distance_atr <= 6:
            distance_score = 0.1
    quality = (
        swing_significance * 0.34
        + touch_score * 0.18
        + reaction_strength * 0.18
        + max(0.0, volume_confirmation) * 0.1
        + indicator_cluster * 0.12
        + distance_score
    )
    structural_support = swing_significance + touch_score + reaction_strength + indicator_cluster
    level_type = "micro_level" if distance_atr is not None and distance_atr < 0.1 and structural_support < 0.85 else "structural_level"
    level_row.update(
        {
            "distance_atr": distance_atr,
            "touch_count": touch_count,
            "reaction_strength": reaction_strength,
            "volume_confirmation": volume_confirmation,
            "indicator_cluster": indicator_cluster,
            "swing_significance": round(swing_significance, 3),
            "level_quality_score": round(min(1.0, max(0.0, quality)), 3),
            "level_type": level_type,
            "member_type": level_member_type(str(level_row.get("reason", ""))),
        }
    )
    return level_row


def build_level_clusters(levels: list[dict], current: float, atr14: float | None) -> list[dict]:
    clusters: list[dict] = []
    tolerance = max((atr14 or current * 0.005) * 0.35, current * 0.0025)
    for direction in ["support", "resistance"]:
        candidates = sorted([row for row in levels if row.get("direction") == direction], key=lambda row: row.get("level") or 0)
        current_cluster: list[dict] = []
        for row in candidates:
            if not current_cluster:
                current_cluster = [row]
                continue
            if abs((row.get("level") or 0) - (current_cluster[-1].get("level") or 0)) <= tolerance:
                current_cluster.append(row)
            else:
                if len(current_cluster) >= 2:
                    clusters.append(make_level_cluster(direction, current_cluster))
                current_cluster = [row]
        if len(current_cluster) >= 2:
            clusters.append(make_level_cluster(direction, current_cluster))
    return sorted(clusters, key=lambda item: (-item.get("quality_score", 0), abs(((item.get("lower") or 0) + (item.get("upper") or 0)) / 2 - current)))


def make_level_cluster(direction: str, members: list[dict]) -> dict:
    levels = [safe_float(row.get("level")) for row in members if safe_float(row.get("level")) is not None]
    scores = [safe_float(row.get("level_quality_score"), 0.0) or 0.0 for row in members]
    return {
        "cluster_type": direction,
        "lower": round_price(min(levels)) if levels else None,
        "upper": round_price(max(levels)) if levels else None,
        "members": sorted({row.get("member_type") or level_member_type(str(row.get("reason", ""))) for row in members}),
        "member_reasons": [row.get("reason") for row in members],
        "quality_score": round(min(1.0, (mean(scores) if scores else 0.0) + min(0.18, len(members) * 0.04)), 3),
    }


def build_price_levels(
    asset: str,
    current: float,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    indicators: dict,
    step: float,
    source_label: str = "Binance spot daily OHLC",
    volumes: list[float] | None = None,
) -> list[dict]:
    candidates: list[tuple[str, float | None]] = [
        ("24H low", min(lows[-2:]) if len(lows) >= 2 else None),
        ("24H high", max(highs[-2:]) if len(highs) >= 2 else None),
        ("7D low", min(lows[-7:]) if len(lows) >= 7 else None),
        ("7D high", max(highs[-7:]) if len(highs) >= 7 else None),
        ("30D low", min(lows[-30:]) if len(lows) >= 30 else None),
        ("30D high", max(highs[-30:]) if len(highs) >= 30 else None),
        ("90D low", min(lows[-90:]) if len(lows) >= 90 else None),
        ("90D high", max(highs[-90:]) if len(highs) >= 90 else None),
        ("MA20", indicators.get("ma20")),
        ("MA50", indicators.get("ma50")),
        ("MA100", indicators.get("ma100")),
        ("MA200", indicators.get("ma200")),
        ("Bollinger lower", indicators.get("bollinger", {}).get("lower")),
        ("Bollinger upper", indicators.get("bollinger", {}).get("upper")),
    ]
    if len(highs) >= 90 and len(lows) >= 90:
        high_90 = max(highs[-90:])
        low_90 = min(lows[-90:])
        diff = high_90 - low_90
        for ratio in [0.236, 0.382, 0.5, 0.618, 0.786]:
            candidates.append((f"90D fib {ratio:.3f}", low_90 + diff * ratio))

    if step > 0:
        lower_round = math.floor(current / step) * step
        upper_round = math.ceil(current / step) * step
        candidates.extend([("round-number floor", lower_round), ("round-number ceiling", upper_round)])

    levels: list[dict] = []
    volume_values = volumes or []
    atr14 = safe_float(indicators.get("atr14"))
    for reason, level in candidates:
        if level is None or level <= 0:
            continue
        direction = "support" if level < current else "resistance" if level > current else "pivot"
        distance_pct = ((level - current) / current) * 100 if current else None
        levels.append(
            enrich_level_quality(
            {
                "asset": asset,
                "direction": direction,
                "level": round_price(level),
                "distance_pct": round(distance_pct, 2) if distance_pct is not None else None,
                "reason": reason,
                "importance": level_importance(distance_pct, reason),
                "source": f"{source_label} + derived indicator",
            },
                current,
                highs,
                lows,
                closes,
                volume_values,
                atr14,
            )
        )
    return dedupe_levels(levels, current)


def nearest_levels(levels: list[dict], current: float | None = None, atr14: float | None = None) -> dict:
    supports = [row for row in levels if row["direction"] == "support"]
    resistances = [row for row in levels if row["direction"] == "resistance"]
    supports.sort(key=lambda row: abs(row.get("distance_pct") or 999))
    resistances.sort(key=lambda row: abs(row.get("distance_pct") or 999))
    quality_supports = sorted(
        [row for row in supports if row.get("level_type") != "micro_level"],
        key=lambda row: (-(row.get("level_quality_score") or 0), abs(row.get("distance_pct") or 999)),
    )
    quality_resistances = sorted(
        [row for row in resistances if row.get("level_type") != "micro_level"],
        key=lambda row: (-(row.get("level_quality_score") or 0), abs(row.get("distance_pct") or 999)),
    )
    resolved_current = current
    if resolved_current is None and (supports or resistances):
        # Reconstruct current approximately from level and signed distance.
        sample = (supports or resistances)[0]
        distance = safe_float(sample.get("distance_pct"))
        level = safe_float(sample.get("level"))
        if distance is not None and level is not None:
            resolved_current = level / (1 + distance / 100)
    clusters = build_level_clusters(levels, resolved_current or 0.0, atr14) if resolved_current else []
    return {
        "nearest_support": supports[0] if supports else {},
        "primary_support": quality_supports[0] if quality_supports else supports[0] if supports else {},
        "next_supports": supports[:4],
        "nearest_resistance": resistances[0] if resistances else {},
        "primary_resistance": quality_resistances[0] if quality_resistances else resistances[0] if resistances else {},
        "next_resistances": resistances[:4],
        "support_clusters": [item for item in clusters if item.get("cluster_type") == "support"][:3],
        "resistance_clusters": [item for item in clusters if item.get("cluster_type") == "resistance"][:3],
    }


def fetch_binance_ticker(pair: str) -> dict:
    payload, error = fetch_json(f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}")
    if error or not isinstance(payload, dict):
        return {"error": error or "empty ticker"}
    return payload


def fetch_binance_candles(pair: str, interval: str = "1d", limit: int = 220) -> tuple[list[dict], Optional[str]]:
    payload, error = fetch_json(f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={interval}&limit={limit}", timeout=25)
    if error:
        return [], error
    return parse_binance_klines(payload), None


def fetch_coingecko_market_chart(coin_id: str, days: int = 365) -> tuple[list[dict], Optional[str]]:
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
    payload, error = fetch_json(url, timeout=25)
    if error:
        return [], error
    candles = parse_coingecko_market_chart(payload)
    if not candles:
        return [], "CoinGecko market_chart returned no candles"
    return candles, None


def okx_inst_id(pair: str) -> str:
    if not pair.endswith("USDT"):
        return pair
    return f"{pair[:-4]}-USDT-SWAP"


def fill_derivative_field(row: dict, field: str, value: object, provider: str) -> None:
    if value is None or value == "":
        return
    if row.get(field) is None:
        row[field] = value
        row.setdefault("field_sources", {})[field] = provider


def derivative_complete(row: dict) -> bool:
    oi_available = any(row.get(field) is not None for field in ["open_interest_contracts", "open_interest_value_usd", "open_interest_base"])
    return row.get("mark_price") is not None and row.get("last_funding_rate") is not None and oi_available


def funding_percent(value: object) -> float | None:
    decimal_rate = safe_float(value)
    if decimal_rate is None:
        return None
    return round(decimal_rate * 100, 4)


def change_from_history(values: list[float], periods_back: int) -> float | None:
    if len(values) <= periods_back:
        return None
    previous = values[-periods_back - 1]
    current = values[-1]
    return pct_change(previous, current)


def fetch_binance_derivative_context(pair: str) -> tuple[dict, list[str]]:
    context = {
        "oi": {"current": None, "change_1h": None, "change_4h": None, "change_24h": None},
        "funding": {"current": None, "average_24h": None, "percentile": None},
        "price_change": {"change_1h": None, "change_4h": None, "change_24h": None},
        "source": "Binance Futures public data",
    }
    errors: list[str] = []
    oi_payload, oi_error = fetch_json(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={pair}&period=1h&limit=30", timeout=12)
    if isinstance(oi_payload, list):
        oi_values = [safe_float(row.get("sumOpenInterest")) for row in oi_payload if isinstance(row, dict)]
        oi_values = [value for value in oi_values if value is not None]
        if oi_values:
            context["oi"]["current"] = round_price(oi_values[-1])
            context["oi"]["change_1h"] = change_from_history(oi_values, 1)
            context["oi"]["change_4h"] = change_from_history(oi_values, 4)
            context["oi"]["change_24h"] = change_from_history(oi_values, 24)
    elif oi_error:
        errors.append(f"Binance OI history: {oi_error}")

    funding_payload, funding_error = fetch_json(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={pair}&limit=30", timeout=12)
    if isinstance(funding_payload, list):
        rates = [funding_percent(row.get("fundingRate")) for row in funding_payload if isinstance(row, dict)]
        rates = [value for value in rates if value is not None]
        if rates:
            context["funding"]["current"] = rates[-1]
            context["funding"]["average_24h"] = round(mean(rates[-3:]), 4) if len(rates) >= 3 else rates[-1]
            sorted_rates = sorted(rates)
            rank = sum(1 for value in sorted_rates if value <= rates[-1])
            context["funding"]["percentile"] = round(rank / len(sorted_rates), 3) if sorted_rates else None
    elif funding_error:
        errors.append(f"Binance funding history: {funding_error}")

    price_payload, price_error = fetch_json(f"https://fapi.binance.com/fapi/v1/klines?symbol={pair}&interval=1h&limit=30", timeout=12)
    candles = parse_binance_klines(price_payload)
    closes = [row["close"] for row in candles]
    if closes:
        context["price_change"]["change_1h"] = change_from_history(closes, 1)
        context["price_change"]["change_4h"] = change_from_history(closes, 4)
        context["price_change"]["change_24h"] = change_from_history(closes, 24)
    elif price_error:
        errors.append(f"Binance futures 1H price candles: {price_error}")
    return context, errors


def fetch_binance_derivatives(pair: str) -> tuple[dict, list[str]]:
    premium, premium_error = fetch_json(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={pair}", timeout=12)
    oi, oi_error = fetch_json(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={pair}", timeout=12)
    row: dict = {"provider": "Binance Futures"}
    if isinstance(premium, dict):
        row.update(
            {
                "mark_price": round_price(safe_float(premium.get("markPrice"))),
                "index_price": round_price(safe_float(premium.get("indexPrice"))),
                "last_funding_rate": funding_percent(premium.get("lastFundingRate")),
                "next_funding_time": premium.get("nextFundingTime"),
            }
        )
    if isinstance(oi, dict):
        row["open_interest_contracts"] = round_price(safe_float(oi.get("openInterest")))
    return row, [error for error in [premium_error, oi_error] if error]


def fetch_bybit_derivatives(pair: str) -> tuple[dict, list[str]]:
    payload, error = fetch_json(f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={pair}", timeout=12)
    if error or not isinstance(payload, dict):
        return {"provider": "Bybit"}, [error or "Bybit ticker response is empty"]
    if payload.get("retCode") != 0:
        return {"provider": "Bybit"}, [f"Bybit retCode {payload.get('retCode')}: {payload.get('retMsg')}"]
    items = payload.get("result", {}).get("list", [])
    item = items[0] if items else {}
    if not item:
        return {"provider": "Bybit"}, ["Bybit ticker list is empty"]
    return (
        {
            "provider": "Bybit",
            "mark_price": round_price(safe_float(item.get("markPrice"))),
            "index_price": round_price(safe_float(item.get("indexPrice"))),
            "last_funding_rate": funding_percent(item.get("fundingRate")),
            "next_funding_time": item.get("nextFundingTime"),
            "open_interest_contracts": round_price(safe_float(item.get("openInterest"))),
            "open_interest_value_usd": round_price(safe_float(item.get("openInterestValue"))),
        },
        [],
    )


def fetch_okx_derivatives(pair: str) -> tuple[dict, list[str]]:
    inst_id = okx_inst_id(pair)
    mark, mark_error = fetch_json(f"https://www.okx.com/api/v5/public/mark-price?instType=SWAP&instId={inst_id}", timeout=12)
    funding, funding_error = fetch_json(f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}", timeout=12)
    oi, oi_error = fetch_json(f"https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId={inst_id}", timeout=12)
    row: dict = {"provider": "OKX"}
    if isinstance(mark, dict) and mark.get("code") == "0":
        item = (mark.get("data") or [{}])[0]
        row["mark_price"] = round_price(safe_float(item.get("markPx")))
    if isinstance(funding, dict) and funding.get("code") == "0":
        item = (funding.get("data") or [{}])[0]
        row["last_funding_rate"] = funding_percent(item.get("fundingRate"))
        row["next_funding_time"] = item.get("fundingTime") or item.get("nextFundingTime")
    if isinstance(oi, dict) and oi.get("code") == "0":
        item = (oi.get("data") or [{}])[0]
        row["open_interest_contracts"] = round_price(safe_float(item.get("oi")))
        row["open_interest_base"] = round_price(safe_float(item.get("oiCcy")))
        row["open_interest_value_usd"] = round_price(safe_float(item.get("oiUsd")))
    errors = [error for error in [mark_error, funding_error, oi_error] if error]
    for label, payload in [("mark", mark), ("funding", funding), ("oi", oi)]:
        if isinstance(payload, dict) and payload.get("code") not in {None, "0"}:
            errors.append(f"OKX {label} code {payload.get('code')}: {payload.get('msg')}")
    return row, errors


def fetch_derivatives(pair: str) -> dict:
    row: dict = {
        "pair": pair,
        "mark_price": None,
        "index_price": None,
        "last_funding_rate": None,
        "next_funding_time": None,
        "open_interest_contracts": None,
        "open_interest_value_usd": None,
        "open_interest_base": None,
        "providers_tried": [],
        "field_sources": {},
    }
    errors: list[str] = []
    for provider_fetcher in [fetch_binance_derivatives, fetch_bybit_derivatives, fetch_okx_derivatives]:
        provider_row, provider_errors = provider_fetcher(pair)
        provider = provider_row.get("provider", provider_fetcher.__name__)
        row["providers_tried"].append(provider)
        errors.extend(f"{provider}: {error}" for error in provider_errors if error)
        for field in [
            "mark_price",
            "index_price",
            "last_funding_rate",
            "next_funding_time",
            "open_interest_contracts",
            "open_interest_value_usd",
            "open_interest_base",
        ]:
            fill_derivative_field(row, field, provider_row.get(field), provider)
        if derivative_complete(row):
            break
    derivative_context, context_errors = fetch_binance_derivative_context(pair)
    row["derivative_context"] = derivative_context
    if derivative_context.get("oi", {}).get("current") is not None and row.get("open_interest_contracts") is None:
        row["open_interest_contracts"] = derivative_context["oi"]["current"]
        row.setdefault("field_sources", {})["open_interest_contracts"] = derivative_context.get("source")
    if derivative_context.get("funding", {}).get("current") is not None and row.get("last_funding_rate") is None:
        row["last_funding_rate"] = derivative_context["funding"]["current"]
        row.setdefault("field_sources", {})["last_funding_rate"] = derivative_context.get("source")
    errors.extend(context_errors)
    used_sources = sorted(set(row.get("field_sources", {}).values()))
    row["source"] = " + ".join(used_sources) if used_sources else "Derivatives public API unavailable"
    if errors and not derivative_complete(row):
        row["error"] = " / ".join(errors)
    elif errors:
        row["fallback_notes"] = " / ".join(errors)
    return row


def calculate_indicators(candles: list[dict]) -> dict:
    closes = [row["close"] for row in candles]
    highs = [row["high"] for row in candles]
    lows = [row["low"] for row in candles]
    bb = bollinger(closes)
    macd_values = macd(closes)
    atr_value = atr(highs, lows, closes)
    last_close = closes[-1] if closes else None
    return {
        "current": round_price(last_close),
        "ma20": round_price(sma(closes, 20)),
        "ma50": round_price(sma(closes, 50)),
        "ma100": round_price(sma(closes, 100)),
        "ma200": round_price(sma(closes, 200)),
        "ema20": round_price(ema_series(closes, 20)[-1]) if closes else None,
        "rsi14": rsi(closes, 14),
        "macd": macd_values,
        "bollinger": bb,
        "atr14": round_price(atr_value),
        "atr14_pct": round((atr_value / last_close) * 100, 2) if atr_value and last_close else None,
        "volume_20d_avg": round(mean([row["volume"] for row in candles[-20:]]), 2) if len(candles) >= 20 else None,
    }


def technical_bias(indicators: dict, current: float | None) -> str:
    if not current:
        return "unknown"
    score = 0
    for key in ["ma20", "ma50", "ma200"]:
        value = indicators.get(key)
        if value:
            score += 1 if current > value else -1
    rsi_value = indicators.get("rsi14")
    if rsi_value is not None:
        score += 1 if 50 <= rsi_value <= 68 else -1 if rsi_value < 40 or rsi_value > 75 else 0
    macd_bias = indicators.get("macd", {}).get("bias")
    score += 1 if macd_bias == "bullish" else -1 if macd_bias == "bearish" else 0
    if score >= 3:
        return "bullish"
    if score <= -2:
        return "bearish"
    return "mixed"


def fetch_coingecko_simple() -> dict:
    ids = ",".join(meta["coingecko_id"] for meta in TRADING_ASSETS.values())
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids}&vs_currencies=usd,jpy"
        "&include_24hr_change=true&include_7d_change=true&include_market_cap=true"
    )
    payload, error = fetch_json(url)
    if error or not isinstance(payload, dict):
        return {}
    return payload


def fetch_crypto_assets() -> tuple[list[dict], dict, list[dict], list[dict], list[str]]:
    errors: list[str] = []
    rows: list[dict] = []
    technicals: dict = {}
    all_levels: list[dict] = []
    derivatives: list[dict] = []
    cg = fetch_coingecko_simple()

    for name, meta in TRADING_ASSETS.items():
        pair = meta["pair"]
        ticker = fetch_binance_ticker(pair)
        candles, candle_error = fetch_binance_candles(pair)
        candle_source = "Binance spot daily OHLC"
        if candle_error:
            errors.append(f"{pair} candles: {candle_error}")
        if len(candles) < 60:
            fallback_candles, fallback_error = fetch_coingecko_market_chart(meta["coingecko_id"])
            if fallback_candles:
                candles = fallback_candles
                candle_source = "CoinGecko market_chart daily close fallback"
                if candle_error:
                    errors.append(f"{pair} candles fallback: CoinGecko market_chart used")
            elif fallback_error:
                errors.append(f"{pair} CoinGecko chart fallback: {fallback_error}")
        closes = [row["close"] for row in candles]
        highs = [row["high"] for row in candles]
        lows = [row["low"] for row in candles]
        volumes = [row.get("volume", 0.0) for row in candles]
        indicators = calculate_indicators(candles) if candles else {}
        current = safe_float(ticker.get("lastPrice")) or indicators.get("current")
        if not current:
            cg_row = cg.get(meta["coingecko_id"], {})
            current = safe_float(cg_row.get("usd"))
        levels = build_price_levels(name, float(current), highs, lows, closes, indicators, meta["step"], candle_source, volumes) if current and candles else []
        level_summary = nearest_levels(levels, float(current) if current else None, indicators.get("atr14"))
        all_levels.extend(levels[:10])
        cg_row = cg.get(meta["coingecko_id"], {})
        change_24h = safe_float(ticker.get("priceChangePercent"))
        change_7d = pct_change(closes[-8], closes[-1]) if len(closes) >= 8 else safe_float(cg_row.get("usd_7d_change"))
        change_30d = pct_change(closes[-31], closes[-1]) if len(closes) >= 31 else None
        row = {
            "name": name,
            "symbol": meta["symbol"],
            "pair": pair,
            "asset_class": "crypto",
            "price": round_price(current),
            "unit": "USD",
            "jpy_price": cg_row.get("jpy"),
            "change_24h": round(change_24h, 2) if change_24h is not None else None,
            "change_7d": change_7d,
            "change_30d": change_30d,
            "market_cap": cg_row.get("usd_market_cap"),
            "technical_bias": technical_bias(indicators, current),
            "nearest_support": level_summary.get("nearest_support", {}).get("level"),
            "nearest_resistance": level_summary.get("nearest_resistance", {}).get("level"),
            "primary_support": level_summary.get("primary_support", {}).get("level"),
            "primary_resistance": level_summary.get("primary_resistance", {}).get("level"),
            "rsi14": indicators.get("rsi14"),
            "macd_bias": indicators.get("macd", {}).get("bias"),
            "source": f"{candle_source} + CoinGecko public API",
        }
        rows.append(row)
        technicals[name] = {
            "row": row,
            "indicators": indicators,
            "levels": level_summary,
            "all_levels": levels,
            "candles": candles[-120:],
            "candle_source": candle_source,
        }
        if meta["symbol"] in {"BTC", "ETH", "SOL", "XRP"}:
            derivatives.append(fetch_derivatives(pair))

    return rows, technicals, all_levels, derivatives, errors


def fetch_yahoo_asset(label: str, symbol: str, unit: str, asset_class: str) -> tuple[Optional[dict], Optional[str]]:
    encoded = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=6mo&interval=1d"
    payload, error = fetch_json(url)
    if error or not isinstance(payload, dict):
        return None, error or "Yahoo chart response is empty."
    try:
        result = payload["chart"]["result"][0]
        quotes = result["indicators"]["quote"][0]
        closes = [float(value) for value in quotes["close"] if value is not None]
        highs = [float(value) for value in quotes["high"] if value is not None]
        lows = [float(value) for value in quotes["low"] if value is not None]
        if not closes:
            return None, "close data unavailable."
        meta = result.get("meta", {})
        price = closes[-1]
        indicators = calculate_indicators([
            {"close": close, "high": high, "low": low, "volume": 0.0}
            for close, high, low in zip(closes, highs, lows)
        ])
        return (
            {
                "name": label,
                "symbol": symbol,
                "asset_class": asset_class,
                "price": round_price(price),
                "unit": unit,
                "jpy_price": None,
                "change_24h": pct_change(closes[-2], closes[-1]) if len(closes) >= 2 else None,
                "change_7d": pct_change(closes[-8], closes[-1]) if len(closes) >= 8 else None,
                "change_30d": pct_change(closes[-31], closes[-1]) if len(closes) >= 31 else None,
                "market_cap": None,
                "technical_bias": technical_bias(indicators, price),
                "rsi14": indicators.get("rsi14"),
                "macd_bias": indicators.get("macd", {}).get("bias"),
                "source": "Yahoo Finance chart API",
                "exchange": meta.get("exchangeName", ""),
            },
            None,
        )
    except Exception as parse_error:
        return None, str(parse_error)


def fetch_macro_assets() -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for label, meta in YAHOO_ASSETS.items():
        row, error = fetch_yahoo_asset(label, meta["symbol"], meta["unit"], meta["asset_class"])
        if row:
            rows.append(row)
        else:
            errors.append(f"{label}: {error}")
    return rows, errors


def fetch_fear_greed() -> tuple[dict, Optional[str]]:
    payload, error = fetch_json("https://api.alternative.me/fng/?limit=7")
    if error or not isinstance(payload, dict):
        return {}, error or "Fear & Greed response is empty."
    try:
        data = payload.get("data", [])
        latest = data[0] if data else {}
        previous = data[1] if len(data) > 1 else {}
        return (
            {
                "value": int(latest.get("value", 0) or 0),
                "classification": latest.get("value_classification", ""),
                "previous_value": int(previous.get("value", 0) or 0) if previous else None,
                "source": "Alternative.me Fear & Greed Index",
            },
            None,
        )
    except Exception as parse_error:
        return {}, str(parse_error)


def fetch_global_context(crypto_rows: list[dict]) -> tuple[dict, Optional[str]]:
    """Collect crypto-wide context without inventing missing values.

    TOTAL2 is total crypto market cap minus BTC market cap.
    TOTAL3 is total crypto market cap minus BTC and ETH market caps.
    BTC dominance comes from CoinGecko global public data when available.
    ETH/BTC is calculated deterministically from canonical BTC and ETH spot
    prices collected in the same market snapshot.
    """
    by_symbol = {row.get("symbol"): row for row in crypto_rows}
    btc = by_symbol.get("BTC", {})
    eth = by_symbol.get("ETH", {})
    btc_price = safe_float(btc.get("price"))
    eth_price = safe_float(eth.get("price"))
    btc_market_cap = safe_float(btc.get("market_cap"))
    eth_market_cap = safe_float(eth.get("market_cap"))
    eth_btc = round(eth_price / btc_price, 8) if eth_price is not None and btc_price not in (None, 0) else None

    context = {
        "btc_dominance": None,
        "eth_btc": eth_btc,
        "total_market_cap": None,
        "total2_market_cap": None,
        "total3_market_cap": None,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "field_sources": {
            "eth_btc": "calculated: ETH spot price / BTC spot price" if eth_btc is not None else None,
        },
        "provenance": {
            "total2_market_cap": "total crypto market cap - BTC market cap",
            "total3_market_cap": "total crypto market cap - BTC market cap - ETH market cap",
        },
    }

    payload, error = fetch_json("https://api.coingecko.com/api/v3/global", timeout=18)
    if error or not isinstance(payload, dict):
        return context, error or "CoinGecko global response is empty."
    data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
    total_market_cap = safe_float((data.get("total_market_cap") or {}).get("usd"))
    btc_dominance = safe_float((data.get("market_cap_percentage") or {}).get("btc"))
    context["btc_dominance"] = round(btc_dominance, 4) if btc_dominance is not None else None
    context["total_market_cap"] = round_price(total_market_cap)
    if total_market_cap is not None and btc_market_cap is not None:
        context["total2_market_cap"] = round_price(total_market_cap - btc_market_cap)
    if total_market_cap is not None and btc_market_cap is not None and eth_market_cap is not None:
        context["total3_market_cap"] = round_price(total_market_cap - btc_market_cap - eth_market_cap)
    context["field_sources"].update(
        {
            "btc_dominance": "CoinGecko global market_cap_percentage.btc" if context["btc_dominance"] is not None else None,
            "total_market_cap": "CoinGecko global total_market_cap.usd" if context["total_market_cap"] is not None else None,
            "total2_market_cap": "CoinGecko global total_market_cap.usd - CoinGecko BTC market cap"
            if context["total2_market_cap"] is not None
            else None,
            "total3_market_cap": "CoinGecko global total_market_cap.usd - CoinGecko BTC market cap - CoinGecko ETH market cap"
            if context["total3_market_cap"] is not None
            else None,
        }
    )
    return context, None


def collect_market_snapshot() -> dict:
    errors: list[str] = []
    crypto_rows, technicals, levels, derivatives, crypto_errors = fetch_crypto_assets()
    errors.extend(crypto_errors)
    macro_rows, macro_errors = fetch_macro_assets()
    errors.extend(macro_errors)
    fear_greed, fear_error = fetch_fear_greed()
    if fear_error:
        errors.append(f"Fear & Greed: {fear_error}")
    global_context, global_error = fetch_global_context(crypto_rows)
    if global_error:
        errors.append(f"Global context: {global_error}")

    return {
        "schema_version": MARKET_SCHEMA_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "crypto": crypto_rows,
        "macro": macro_rows,
        "technicals": technicals,
        "price_levels": levels,
        "derivatives": derivatives,
        "fear_greed": fear_greed,
        "global_context": global_context,
        "errors": errors,
    }


def find_asset(snapshot: dict, name: str) -> dict:
    for section in ("crypto", "macro"):
        for row in snapshot.get(section, []):
            if row.get("name") == name:
                return row
    return {}


def find_derivative(snapshot: dict, pair: str) -> dict:
    for row in snapshot.get("derivatives", []) or []:
        if row.get("pair") == pair:
            return row
    return {}


def summarize_market(snapshot: dict) -> dict:
    btc = find_asset(snapshot, "Bitcoin")
    eth = find_asset(snapshot, "Ethereum")
    sol = find_asset(snapshot, "Solana")
    nikkei = find_asset(snapshot, "Nikkei 225")
    gold = find_asset(snapshot, "Gold Futures")
    dxy = find_asset(snapshot, "US Dollar Index")
    fear = snapshot.get("fear_greed", {})
    global_context = snapshot.get("global_context", {}) or {}
    btc_tech = snapshot.get("technicals", {}).get("Bitcoin", {})
    btc_indicators = btc_tech.get("indicators", {})
    btc_levels = btc_tech.get("levels", {})
    btc_derivative = find_derivative(snapshot, "BTCUSDT")
    btc_derivative_context = btc_derivative.get("derivative_context") or {}

    risk_points = 0
    risk_points += 2 if (btc.get("change_7d") or 0) > 3 else -2 if (btc.get("change_7d") or 0) < -3 else 0
    risk_points += 1 if (eth.get("change_7d") or 0) > (btc.get("change_7d") or 0) else 0
    risk_points += 1 if (sol.get("change_7d") or 0) > 0 else 0
    risk_points += 1 if (nikkei.get("change_7d") or 0) > 0 else -1 if (nikkei.get("change_7d") or 0) < -2 else 0
    risk_points += -1 if (gold.get("change_7d") or 0) > 2 else 0
    risk_points += -1 if (dxy.get("change_7d") or 0) > 1 else 0
    risk_points += 1 if (fear.get("value") or 0) >= 55 else -1 if (fear.get("value") or 0) <= 35 else 0
    risk_points += 1 if btc.get("technical_bias") == "bullish" else -1 if btc.get("technical_bias") == "bearish" else 0

    if risk_points >= 3:
        bias = "risk_on"
        label = "위험자산 선호 우세"
    elif risk_points <= -2:
        bias = "risk_off"
        label = "방어적 자산 이동 경계"
    else:
        bias = "mixed"
        label = "혼조/선별 장세"

    nearest_support = btc_levels.get("nearest_support", {})
    nearest_resistance = btc_levels.get("nearest_resistance", {})
    primary_support = btc_levels.get("primary_support", {}) or nearest_support
    primary_resistance = btc_levels.get("primary_resistance", {}) or nearest_resistance
    btc_support_level = nearest_support.get("level") or btc.get("nearest_support")
    btc_resistance_level = nearest_resistance.get("level") or btc.get("nearest_resistance")
    btc_primary_support_level = primary_support.get("level") or btc.get("primary_support") or btc_support_level
    btc_primary_resistance_level = primary_resistance.get("level") or btc.get("primary_resistance") or btc_resistance_level
    btc_price = btc.get("price")
    support_distance = nearest_support.get("distance_pct")
    resistance_distance = nearest_resistance.get("distance_pct")
    if support_distance is None:
        support_distance = distance_pct(safe_float(btc_support_level), safe_float(btc_price))
    if resistance_distance is None:
        resistance_distance = distance_pct(safe_float(btc_resistance_level), safe_float(btc_price))
    eth_btc = None
    if safe_float(eth.get("price")) is not None and safe_float(btc_price) not in (None, 0):
        eth_btc = round(safe_float(eth.get("price")) / safe_float(btc_price), 8)

    return {
        "bias": bias,
        "label": label,
        "risk_points": risk_points,
        "btc_price": btc_price,
        "btc_24h": btc.get("change_24h"),
        "btc_7d": btc.get("change_7d"),
        "btc_30d": btc.get("change_30d"),
        "btc_technical_bias": btc.get("technical_bias"),
        "btc_rsi14": btc_indicators.get("rsi14") or btc.get("rsi14"),
        "btc_macd_bias": btc_indicators.get("macd", {}).get("bias") or btc.get("macd_bias"),
        "btc_ma20": btc_indicators.get("ma20"),
        "btc_ma50": btc_indicators.get("ma50"),
        "btc_ma200": btc_indicators.get("ma200"),
        "btc_atr14": btc_indicators.get("atr14"),
        "btc_atr14_pct": btc_indicators.get("atr14_pct"),
        "btc_nearest_support": btc_support_level,
        "btc_primary_support": btc_primary_support_level,
        "btc_primary_support_profile": primary_support,
        "btc_support_distance_pct": support_distance,
        "btc_nearest_resistance": btc_resistance_level,
        "btc_primary_resistance": btc_primary_resistance_level,
        "btc_primary_resistance_profile": primary_resistance,
        "btc_resistance_distance_pct": resistance_distance,
        "btc_support_clusters": btc_levels.get("support_clusters", []),
        "btc_resistance_clusters": btc_levels.get("resistance_clusters", []),
        "btc_next_supports": btc_levels.get("next_supports", []),
        "btc_next_resistances": btc_levels.get("next_resistances", []),
        "btc_mark_price": btc_derivative.get("mark_price"),
        "btc_funding_rate": btc_derivative.get("last_funding_rate"),
        "btc_funding_average_24h": (btc_derivative_context.get("funding") or {}).get("average_24h"),
        "btc_funding_percentile": (btc_derivative_context.get("funding") or {}).get("percentile"),
        "btc_open_interest_contracts": btc_derivative.get("open_interest_contracts"),
        "btc_oi_change_1h": (btc_derivative_context.get("oi") or {}).get("change_1h"),
        "btc_oi_change_4h": (btc_derivative_context.get("oi") or {}).get("change_4h"),
        "btc_oi_change_24h": (btc_derivative_context.get("oi") or {}).get("change_24h"),
        "btc_price_change_1h": (btc_derivative_context.get("price_change") or {}).get("change_1h"),
        "btc_price_change_4h": (btc_derivative_context.get("price_change") or {}).get("change_4h"),
        "btc_price_change_24h": (btc_derivative_context.get("price_change") or {}).get("change_24h"),
        "btc_derivative_context": btc_derivative_context,
        "btc_open_interest_value_usd": btc_derivative.get("open_interest_value_usd"),
        "btc_open_interest_base": btc_derivative.get("open_interest_base"),
        "btc_derivatives_source": btc_derivative.get("source"),
        "eth_price": eth.get("price"),
        "eth_7d": eth.get("change_7d"),
        "eth_btc": global_context.get("eth_btc") or eth_btc,
        "sol_price": sol.get("price"),
        "sol_7d": sol.get("change_7d"),
        "nikkei_7d": nikkei.get("change_7d"),
        "gold_7d": gold.get("change_7d"),
        "dxy_7d": dxy.get("change_7d"),
        "btc_dominance": global_context.get("btc_dominance"),
        "total2_market_cap": global_context.get("total2_market_cap"),
        "total3_market_cap": global_context.get("total3_market_cap"),
        "global_context_sources": global_context.get("field_sources", {}),
        "global_context_provenance": global_context.get("provenance", {}),
        "fear_greed": fear.get("value"),
        "fear_greed_label": fear.get("classification"),
    }


def flatten_market_rows(snapshot: dict) -> list[dict]:
    rows: list[dict] = []
    for section in ("crypto", "macro"):
        rows.extend(snapshot.get(section, []))
    fear = snapshot.get("fear_greed", {})
    if fear:
        rows.append(
            {
                "name": "Crypto Fear & Greed",
                "symbol": "FNG",
                "asset_class": "sentiment",
                "price": fear.get("value"),
                "unit": fear.get("classification", ""),
                "jpy_price": None,
                "change_24h": None,
                "change_7d": None,
                "change_30d": None,
                "market_cap": None,
                "technical_bias": None,
                "source": fear.get("source", ""),
            }
        )
    return rows


def flatten_level_rows(snapshot: dict) -> list[dict]:
    return snapshot.get("price_levels", []) or []


def flatten_indicator_rows(snapshot: dict) -> list[dict]:
    rows: list[dict] = []
    for asset, payload in (snapshot.get("technicals", {}) or {}).items():
        indicators = payload.get("indicators", {})
        macd_values = indicators.get("macd", {})
        bollinger_values = indicators.get("bollinger", {})
        rows.append(
            {
                "asset": asset,
                "current": indicators.get("current"),
                "ma20": indicators.get("ma20"),
                "ma50": indicators.get("ma50"),
                "ma100": indicators.get("ma100"),
                "ma200": indicators.get("ma200"),
                "ema20": indicators.get("ema20"),
                "rsi14": indicators.get("rsi14"),
                "macd": macd_values.get("macd"),
                "macd_signal": macd_values.get("signal"),
                "macd_histogram": macd_values.get("histogram"),
                "macd_bias": macd_values.get("bias"),
                "bollinger_upper": bollinger_values.get("upper"),
                "bollinger_middle": bollinger_values.get("middle"),
                "bollinger_lower": bollinger_values.get("lower"),
                "bollinger_bandwidth_pct": bollinger_values.get("bandwidth_pct"),
                "atr14": indicators.get("atr14"),
                "atr14_pct": indicators.get("atr14_pct"),
                "volume_20d_avg": indicators.get("volume_20d_avg"),
            }
        )
    return rows


def flatten_derivatives_rows(snapshot: dict) -> list[dict]:
    rows = []
    for row in snapshot.get("derivatives", []) or []:
        item = dict(row)
        context = item.get("derivative_context") or {}
        oi = context.get("oi") or {}
        funding = context.get("funding") or {}
        price_change = context.get("price_change") or {}
        item.update(
            {
                "oi_change_1h": oi.get("change_1h"),
                "oi_change_4h": oi.get("change_4h"),
                "oi_change_24h": oi.get("change_24h"),
                "funding_average_24h": funding.get("average_24h"),
                "funding_percentile": funding.get("percentile"),
                "futures_price_change_1h": price_change.get("change_1h"),
                "futures_price_change_4h": price_change.get("change_4h"),
                "futures_price_change_24h": price_change.get("change_24h"),
            }
        )
        rows.append(item)
    return rows
