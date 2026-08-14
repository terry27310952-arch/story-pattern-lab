from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Optional
from urllib.parse import quote
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 StoryPatternLab/1.1; crypto-market-levels"


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


def build_price_levels(asset: str, current: float, highs: list[float], lows: list[float], closes: list[float], indicators: dict, step: float) -> list[dict]:
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
    for reason, level in candidates:
        if level is None or level <= 0:
            continue
        direction = "support" if level < current else "resistance" if level > current else "pivot"
        distance_pct = ((level - current) / current) * 100 if current else None
        levels.append(
            {
                "asset": asset,
                "direction": direction,
                "level": round_price(level),
                "distance_pct": round(distance_pct, 2) if distance_pct is not None else None,
                "reason": reason,
                "importance": level_importance(distance_pct, reason),
                "source": "Binance daily OHLC + derived indicator",
            }
        )
    return dedupe_levels(levels, current)


def nearest_levels(levels: list[dict]) -> dict:
    supports = [row for row in levels if row["direction"] == "support"]
    resistances = [row for row in levels if row["direction"] == "resistance"]
    supports.sort(key=lambda row: abs(row.get("distance_pct") or 999))
    resistances.sort(key=lambda row: abs(row.get("distance_pct") or 999))
    return {
        "nearest_support": supports[0] if supports else {},
        "next_supports": supports[:4],
        "nearest_resistance": resistances[0] if resistances else {},
        "next_resistances": resistances[:4],
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


def fetch_derivatives(pair: str) -> dict:
    premium, premium_error = fetch_json(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={pair}", timeout=12)
    oi, oi_error = fetch_json(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={pair}", timeout=12)
    row = {"pair": pair, "source": "Binance Futures public API"}
    if isinstance(premium, dict):
        row.update(
            {
                "mark_price": round_price(safe_float(premium.get("markPrice"))),
                "index_price": round_price(safe_float(premium.get("indexPrice"))),
                "last_funding_rate": round((safe_float(premium.get("lastFundingRate"), 0) or 0) * 100, 4),
                "next_funding_time": premium.get("nextFundingTime"),
            }
        )
    if isinstance(oi, dict):
        row["open_interest_contracts"] = round_price(safe_float(oi.get("openInterest")))
    errors = [error for error in [premium_error, oi_error] if error]
    if errors:
        row["error"] = " / ".join(errors)
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
        if candle_error:
            errors.append(f"{pair} candles: {candle_error}")
        closes = [row["close"] for row in candles]
        highs = [row["high"] for row in candles]
        lows = [row["low"] for row in candles]
        indicators = calculate_indicators(candles) if candles else {}
        current = safe_float(ticker.get("lastPrice")) or indicators.get("current")
        if not current:
            cg_row = cg.get(meta["coingecko_id"], {})
            current = safe_float(cg_row.get("usd"))
        levels = build_price_levels(name, float(current), highs, lows, closes, indicators, meta["step"]) if current and candles else []
        level_summary = nearest_levels(levels)
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
            "rsi14": indicators.get("rsi14"),
            "macd_bias": indicators.get("macd", {}).get("bias"),
            "source": "Binance spot OHLC + CoinGecko public API",
        }
        rows.append(row)
        technicals[name] = {
            "row": row,
            "indicators": indicators,
            "levels": level_summary,
            "all_levels": levels,
            "candles": candles[-120:],
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


def collect_market_snapshot() -> dict:
    errors: list[str] = []
    crypto_rows, technicals, levels, derivatives, crypto_errors = fetch_crypto_assets()
    errors.extend(crypto_errors)
    macro_rows, macro_errors = fetch_macro_assets()
    errors.extend(macro_errors)
    fear_greed, fear_error = fetch_fear_greed()
    if fear_error:
        errors.append(f"Fear & Greed: {fear_error}")

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "crypto": crypto_rows,
        "macro": macro_rows,
        "technicals": technicals,
        "price_levels": levels,
        "derivatives": derivatives,
        "fear_greed": fear_greed,
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
    btc_tech = snapshot.get("technicals", {}).get("Bitcoin", {})
    btc_indicators = btc_tech.get("indicators", {})
    btc_levels = btc_tech.get("levels", {})
    btc_derivative = find_derivative(snapshot, "BTCUSDT")

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
    return {
        "bias": bias,
        "label": label,
        "risk_points": risk_points,
        "btc_price": btc.get("price"),
        "btc_24h": btc.get("change_24h"),
        "btc_7d": btc.get("change_7d"),
        "btc_30d": btc.get("change_30d"),
        "btc_technical_bias": btc.get("technical_bias"),
        "btc_rsi14": btc_indicators.get("rsi14"),
        "btc_macd_bias": btc_indicators.get("macd", {}).get("bias"),
        "btc_ma20": btc_indicators.get("ma20"),
        "btc_ma50": btc_indicators.get("ma50"),
        "btc_ma200": btc_indicators.get("ma200"),
        "btc_atr14": btc_indicators.get("atr14"),
        "btc_atr14_pct": btc_indicators.get("atr14_pct"),
        "btc_nearest_support": nearest_support.get("level"),
        "btc_support_distance_pct": nearest_support.get("distance_pct"),
        "btc_nearest_resistance": nearest_resistance.get("level"),
        "btc_resistance_distance_pct": nearest_resistance.get("distance_pct"),
        "btc_mark_price": btc_derivative.get("mark_price"),
        "btc_funding_rate": btc_derivative.get("last_funding_rate"),
        "btc_open_interest_contracts": btc_derivative.get("open_interest_contracts"),
        "eth_price": eth.get("price"),
        "eth_7d": eth.get("change_7d"),
        "sol_price": sol.get("price"),
        "sol_7d": sol.get("change_7d"),
        "nikkei_7d": nikkei.get("change_7d"),
        "gold_7d": gold.get("change_7d"),
        "dxy_7d": dxy.get("change_7d"),
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
    return snapshot.get("derivatives", []) or []
