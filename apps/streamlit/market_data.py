from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 StoryPatternLab/1.0; crypto-market-snapshot"


COINGECKO_IDS = {
    "Bitcoin": "bitcoin",
    "Ethereum": "ethereum",
    "Solana": "solana",
    "XRP": "ripple",
    "Dogecoin": "dogecoin",
    "Chainlink": "chainlink",
}


YAHOO_ASSETS = {
    "Nikkei 225": {"symbol": "^N225", "unit": "JPY", "asset_class": "equity_index"},
    "Gold Futures": {"symbol": "GC=F", "unit": "USD", "asset_class": "commodity"},
    "Nasdaq Composite": {"symbol": "^IXIC", "unit": "USD", "asset_class": "equity_index"},
    "US Dollar Index": {"symbol": "DX-Y.NYB", "unit": "index", "asset_class": "fx"},
    "US 10Y Yield": {"symbol": "^TNX", "unit": "% x10", "asset_class": "rates"},
}


def fetch_json(url: str, timeout: int = 15) -> tuple[Optional[dict], Optional[str]]:
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


def pct_change(first: float | None, last: float | None) -> Optional[float]:
    if first in (None, 0) or last is None:
        return None
    return round(((last - first) / first) * 100, 2)


def fetch_crypto_assets() -> tuple[list[dict], Optional[str]]:
    ids = ",".join(COINGECKO_IDS.values())
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids}&vs_currencies=usd,jpy"
        "&include_24hr_change=true&include_7d_change=true&include_market_cap=true"
    )
    payload, error = fetch_json(url)
    if error or not payload:
        return [], error or "CoinGecko 응답이 비어 있습니다."

    rows: list[dict] = []
    reverse_ids = {value: key for key, value in COINGECKO_IDS.items()}
    for coin_id, values in payload.items():
        rows.append(
            {
                "name": reverse_ids.get(coin_id, coin_id),
                "symbol": coin_id.upper(),
                "asset_class": "crypto",
                "price": values.get("usd"),
                "unit": "USD",
                "jpy_price": values.get("jpy"),
                "change_24h": round(float(values.get("usd_24h_change", 0) or 0), 2),
                "change_7d": round(float(values.get("usd_7d_change", 0) or 0), 2),
                "market_cap": values.get("usd_market_cap"),
                "source": "CoinGecko public API",
            }
        )
    return rows, None


def fetch_yahoo_asset(label: str, symbol: str, unit: str, asset_class: str) -> tuple[Optional[dict], Optional[str]]:
    encoded = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=7d&interval=1d"
    payload, error = fetch_json(url)
    if error or not payload:
        return None, error or "Yahoo chart 응답이 비어 있습니다."
    try:
        result = payload["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        clean_closes = [float(value) for value in closes if value is not None]
        if not clean_closes:
            return None, "종가 데이터가 없습니다."
        meta = result.get("meta", {})
        price = clean_closes[-1]
        return (
            {
                "name": label,
                "symbol": symbol,
                "asset_class": asset_class,
                "price": round(price, 4),
                "unit": unit,
                "jpy_price": None,
                "change_24h": pct_change(clean_closes[-2], clean_closes[-1]) if len(clean_closes) >= 2 else None,
                "change_7d": pct_change(clean_closes[0], clean_closes[-1]) if len(clean_closes) >= 2 else None,
                "market_cap": None,
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
    if error or not payload:
        return {}, error or "Fear & Greed 응답이 비어 있습니다."
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
    crypto_rows, crypto_error = fetch_crypto_assets()
    if crypto_error:
        errors.append(f"CoinGecko: {crypto_error}")
    macro_rows, macro_errors = fetch_macro_assets()
    errors.extend(macro_errors)
    fear_greed, fear_error = fetch_fear_greed()
    if fear_error:
        errors.append(f"Fear & Greed: {fear_error}")

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "crypto": crypto_rows,
        "macro": macro_rows,
        "fear_greed": fear_greed,
        "errors": errors,
    }


def find_asset(snapshot: dict, name: str) -> dict:
    for section in ("crypto", "macro"):
        for row in snapshot.get(section, []):
            if row.get("name") == name:
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

    risk_points = 0
    risk_points += 2 if (btc.get("change_7d") or 0) > 3 else -2 if (btc.get("change_7d") or 0) < -3 else 0
    risk_points += 1 if (eth.get("change_7d") or 0) > (btc.get("change_7d") or 0) else 0
    risk_points += 1 if (sol.get("change_7d") or 0) > 0 else 0
    risk_points += 1 if (nikkei.get("change_7d") or 0) > 0 else -1 if (nikkei.get("change_7d") or 0) < -2 else 0
    risk_points += -1 if (gold.get("change_7d") or 0) > 2 else 0
    risk_points += -1 if (dxy.get("change_7d") or 0) > 1 else 0
    risk_points += 1 if (fear.get("value") or 0) >= 55 else -1 if (fear.get("value") or 0) <= 35 else 0

    if risk_points >= 3:
        bias = "risk_on"
        label = "위험자산 선호가 우세"
    elif risk_points <= -2:
        bias = "risk_off"
        label = "방어적 자산 이동 경계"
    else:
        bias = "mixed"
        label = "혼조/선별 장세"

    return {
        "bias": bias,
        "label": label,
        "risk_points": risk_points,
        "btc_7d": btc.get("change_7d"),
        "eth_7d": eth.get("change_7d"),
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
                "market_cap": None,
                "source": fear.get("source", ""),
            }
        )
    return rows
