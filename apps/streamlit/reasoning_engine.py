from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from urllib.request import Request, urlopen

from market_data import summarize_market


PROVIDER_LOCAL = "local"
PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"


DISCLAIMER = "본 자료는 공개 데이터와 선택 리소스를 분석한 브리핑이며, 투자 권유나 매수/매도 지시가 아닙니다."


BITCOIN_ILLUMINATI_VIEWPOINT = {
    "source_url": "https://www.youtube.com/@bitcoinilluminati",
    "channel_id": "UC3vBufn2MqRFyHk297at70w",
    "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC3vBufn2MqRFyHk297at70w",
    "observed_keywords": [
        "비트코인분석",
        "비트코인차트분석",
        "비트코인불장",
        "비트코인시즌종료",
        "비트코인전망",
        "알트코인분석",
        "이더리움",
        "XRP",
        "솔라나",
        "수이",
    ],
    "analysis_lens": [
        "BTC를 모든 판단의 기준축으로 놓고 알트는 후행 로테이션으로 본다.",
        "뉴스 자체보다 시장이 그 뉴스를 가격과 거래량으로 어떻게 소화하는지 본다.",
        "상승/하락 단정이 아니라 기준선, 무효화 조건, 관찰 구간을 먼저 둔다.",
        "과열과 공포를 콘텐츠 후킹으로 쓰되 포지션 판단은 구조 확인 뒤에 한다.",
        "알트 시즌은 BTC 안정, ETH 상대강도, 유동성 회복, 섹터별 거래량 확산이 같이 나와야 인정한다.",
    ],
}


def clean_text(value: object, limit: int = 2400) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def split_sentences(text: str, limit: int = 6) -> list[str]:
    cleaned = clean_text(text, 12000)
    if not cleaned:
        return []
    pieces = re.split(r"(?<=[。.!?])\s+|(?<=다\.)\s+|(?<=요\.)\s+", cleaned)
    sentences = [piece.strip() for piece in pieces if len(piece.strip()) >= 35]
    if not sentences:
        sentences = [cleaned[:420]]
    return sentences[:limit]


def as_percent(value: object) -> str:
    if value is None or value == "":
        return "데이터 미수집"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return str(value)


def trim_number(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.2f}"
    if abs(value) >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:,.6f}".rstrip("0").rstrip(".")


def as_price(value: object, unit: str = "USD") -> str:
    if value is None or value == "":
        return "데이터 미수집"
    try:
        number = float(value)
    except Exception:
        return str(value)
    prefix = "$" if unit == "USD" else ""
    suffix = "" if unit == "USD" else f" {unit}"
    return f"{prefix}{trim_number(number)}{suffix}"


def as_plain_number(value: object) -> str:
    if value is None or value == "":
        return "데이터 미수집"
    try:
        return trim_number(float(value))
    except Exception:
        return str(value)


def to_float(value: object, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def rsi_state(value: object) -> str:
    try:
        number = float(value)
    except Exception:
        return "RSI 데이터 없음"
    if number >= 75:
        return "과열권"
    if number >= 60:
        return "상승 모멘텀 우위"
    if number >= 45:
        return "중립권"
    if number >= 35:
        return "약세 압력"
    return "과매도권"


def funding_state(value: object) -> str:
    try:
        number = float(value)
    except Exception:
        return "펀딩 데이터 없음"
    if number >= 0.05:
        return "롱 과열 경계"
    if number > 0:
        return "롱 우위이나 과열 전"
    if number <= -0.03:
        return "숏 쏠림 가능성"
    return "중립"


def btc_level_context(market_summary: dict) -> str:
    price = as_price(market_summary.get("btc_price"))
    support = as_price(market_summary.get("btc_nearest_support"))
    resistance = as_price(market_summary.get("btc_nearest_resistance"))
    support_distance = as_percent(market_summary.get("btc_support_distance_pct"))
    resistance_distance = as_percent(market_summary.get("btc_resistance_distance_pct"))
    if market_summary.get("btc_nearest_support") is None or market_summary.get("btc_nearest_resistance") is None:
        return (
            f"BTC 현재가는 {price}입니다. 다만 캔들 기반 지지/저항 산출에 필요한 차트 데이터가 부족해 "
            "시장 데이터 재갱신 또는 CoinGecko 차트 fallback 확인이 필요합니다."
        )
    return (
        f"BTC 현재가는 {price}이며, 즉시 확인할 지지는 {support}({support_distance}), "
        f"돌파 확인 저항은 {resistance}({resistance_distance})입니다."
    )


def btc_indicator_context(market_summary: dict) -> str:
    return (
        f"MA20 {as_price(market_summary.get('btc_ma20'))}, MA50 {as_price(market_summary.get('btc_ma50'))}, "
        f"MA200 {as_price(market_summary.get('btc_ma200'))}, RSI14 {as_plain_number(market_summary.get('btc_rsi14'))}"
        f"({rsi_state(market_summary.get('btc_rsi14'))}), MACD {market_summary.get('btc_macd_bias') or '데이터 미수집'}, "
        f"ATR14 {as_price(market_summary.get('btc_atr14'))}({as_percent(market_summary.get('btc_atr14_pct'))})입니다."
    )


def btc_derivatives_context(market_summary: dict) -> str:
    return (
        f"BTC 선물 마크가격 {as_price(market_summary.get('btc_mark_price'))}, "
        f"펀딩비 {as_percent(market_summary.get('btc_funding_rate'))}({funding_state(market_summary.get('btc_funding_rate'))}), "
        f"미결제약정 {as_plain_number(market_summary.get('btc_open_interest_contracts'))} contracts입니다."
    )


def eth_relative_context(market_summary: dict) -> str:
    btc_change = market_summary.get("btc_7d")
    eth_change = market_summary.get("eth_7d")
    if btc_change is None or eth_change is None:
        return "ETH 상대강도는 데이터 부족으로 보류합니다."
    relative = float(eth_change) - float(btc_change)
    return f"ETH 7D {as_percent(eth_change)} vs BTC 7D {as_percent(btc_change)}로, ETH의 7일 상대 변화율은 {as_percent(relative)}입니다."


def level_trigger(market_summary: dict, side: str) -> str:
    if side == "resistance":
        return as_price(market_summary.get("btc_nearest_resistance"))
    return as_price(market_summary.get("btc_nearest_support"))


def build_trader_stance(market_summary: dict, topics: list[str], findings: list[dict]) -> dict:
    price = to_float(market_summary.get("btc_price"))
    support = to_float(market_summary.get("btc_nearest_support"))
    resistance = to_float(market_summary.get("btc_nearest_resistance"))
    ma20 = to_float(market_summary.get("btc_ma20"))
    ma50 = to_float(market_summary.get("btc_ma50"))
    ma200 = to_float(market_summary.get("btc_ma200"))
    rsi_value = to_float(market_summary.get("btc_rsi14"))
    funding = to_float(market_summary.get("btc_funding_rate"))
    btc_7d = to_float(market_summary.get("btc_7d"), 0.0) or 0.0
    eth_7d = to_float(market_summary.get("eth_7d"), 0.0) or 0.0
    macd_bias = market_summary.get("btc_macd_bias")
    risk_points = int(to_float(market_summary.get("risk_points"), 0) or 0)

    score = 50 + risk_points * 5
    if price and ma20:
        score += 8 if price > ma20 else -8
    if price and ma50:
        score += 8 if price > ma50 else -8
    if price and ma200:
        score += 10 if price > ma200 else -10
    if rsi_value is not None:
        score += 8 if 50 <= rsi_value <= 65 else -8 if rsi_value < 42 or rsi_value > 75 else 0
    score += 8 if macd_bias == "bullish" else -8 if macd_bias == "bearish" else 0
    if funding is not None:
        score += -4 if funding > 0.04 else 3 if funding < 0 else 0
    score = max(5, min(95, score))

    above_resistance = price is not None and resistance is not None and price > resistance
    below_support = price is not None and support is not None and price < support
    below_ma200 = price is not None and ma200 is not None and price < ma200
    below_ma20 = price is not None and ma20 is not None and price < ma20
    eth_outperform = eth_7d > btc_7d

    if score >= 68 or above_resistance:
        bias = "상방 추세 재개를 우선 의심"
        posture = "돌파 확인 후 분할 롱"
        market_read = (
            "내 관점에서는 시장이 이미 공포 구간을 지나 저항 흡수 여부를 테스트하는 단계입니다. "
            "다만 돌파 직후 한 번의 되돌림은 흔하므로 첫 양봉을 추격하기보다 돌파 가격을 다시 지키는지를 봅니다."
        )
        expected_path = (
            f"내가 보는 우선 경로는 {level_trigger(market_summary, 'resistance')} 돌파 후 얕은 되돌림, "
            "그 다음 MA20/MA50 위 안착을 확인하는 흐름입니다. 이 흐름이 나오면 알트는 후행으로 붙을 가능성이 큽니다."
        )
    elif score <= 38 or below_support:
        bias = "하방 리스크 우선"
        posture = "현금 비중 우위, 반등은 짧게"
        market_read = (
            "내 관점에서는 지금 시장을 싸다고 보기보다 아직 매물이 정리되지 않은 구간으로 봅니다. "
            "호재가 나와도 지지 회복 전에는 반등 매매 이상으로 의미를 키우지 않습니다."
        )
        expected_path = (
            f"내가 보는 우선 경로는 {level_trigger(market_summary, 'support')} 재시험입니다. "
            f"여기서 빠른 회복이 나오면 {level_trigger(market_summary, 'resistance')}까지 짧은 반등, "
            "회복이 실패하면 다음 지지 확인 전까지 알트가 더 크게 흔들릴 가능성을 봅니다."
        )
    elif below_ma200 or below_ma20:
        bias = "중립-약세, 돌파 확인 전 관망"
        posture = "박스권 대응, 추격 금지"
        market_read = (
            "내 관점에서는 현재 구간을 추세 상승장으로 보지 않습니다. "
            "가격은 단기 지지 위에 있지만 주요 이동평균을 완전히 회복하지 못해, 좋은 뉴스도 박스권 안에서 소모될 가능성을 먼저 봅니다."
        )
        expected_path = (
            f"내가 보는 기본 경로는 {level_trigger(market_summary, 'support')}~{level_trigger(market_summary, 'resistance')} 박스권 소모입니다. "
            "한쪽으로 튀는 첫 움직임보다, 그 가격을 다시 지키는 두 번째 반응이 더 중요합니다."
        )
    else:
        bias = "중립-상방, 눌림 확인"
        posture = "지지 확인 후 소액 분할"
        market_read = (
            "내 관점에서는 무리하게 비관할 구간은 아니지만, 아직 확신을 크게 싣기보다 눌림이 얕은지 확인해야 하는 자리입니다. "
            "강한 종목보다 BTC가 먼저 구조를 지키는지가 우선입니다."
        )
        expected_path = (
            f"내가 보는 우선 경로는 {level_trigger(market_summary, 'support')} 위에서 눌림을 버티고 "
            f"{level_trigger(market_summary, 'resistance')}을 다시 두드리는 흐름입니다. 실패하면 관망으로 돌아갑니다."
        )

    entry_plan = (
        f"1차 진입은 {level_trigger(market_summary, 'support')} 부근에서 꼬리 회복과 거래량 반응이 같이 나올 때만 작게 봅니다. "
        f"추가 진입은 {level_trigger(market_summary, 'resistance')} 위 종가 안착 후 되돌림이 얕을 때로 제한합니다."
    )
    if below_support:
        entry_plan = (
            f"현재가가 지지 아래라면 신규 롱은 보류합니다. 먼저 {level_trigger(market_summary, 'support')} 회복을 확인하고, "
            "회복 실패 시 반등은 매도 유동성으로 봅니다."
        )
    elif above_resistance:
        entry_plan = (
            f"{level_trigger(market_summary, 'resistance')} 돌파가 이미 나온 상태라면 첫 추격보다 되돌림에서 해당 가격을 지지로 바꾸는지 봅니다. "
            "지지 전환이 확인될 때만 분할 롱을 인정합니다."
        )

    profit_plan = (
        "익절은 한 번에 맞추는 방식보다 저항 돌파 후 1차 청산, MA20/MA50 재이탈 시 잔여 축소, "
        "강한 거래량이 유지될 때만 일부를 추세 포지션으로 남기는 방식을 선호합니다."
    )
    risk_plan = (
        f"무효화는 {level_trigger(market_summary, 'support')} 이탈입니다. 이탈 후 빠른 회복이 없으면 내 시나리오는 틀린 것으로 보고, "
        "알트와 레버리지 노출을 먼저 줄입니다."
    )
    no_trade = (
        f"{level_trigger(market_summary, 'support')}와 {level_trigger(market_summary, 'resistance')} 사이에서 거래량 없이 흔들리는 구간은 내 기준에서 매매 금지에 가깝습니다. "
        "이 구간은 예측보다 기다림의 가치가 큽니다."
    )
    alt_plan = (
        "알트는 BTC보다 먼저 사지 않습니다. "
        + (
            "ETH가 BTC보다 강하므로 BTC 지지 유지가 확인되면 ETH/SOL/XRP 쪽으로 베타를 일부 열 수 있습니다."
            if eth_outperform
            else "ETH 상대강도가 아직 강하지 않으므로 알트 뉴스는 콘텐츠 소재로만 보고, 실제 비중은 BTC 구조 확인 뒤에 둡니다."
        )
    )
    subjective_note = (
        "내 매매법은 바닥 맞히기가 아니라 '틀렸을 때 빨리 나올 수 있는 자리'만 고르는 방식입니다. "
        "그래서 좋은 기사보다 더 중요한 것은 가격이 그 기사를 지지/저항에서 어떻게 소화했는가입니다."
    )

    return {
        "persona": "BTC 구조 우선 스윙 트레이더",
        "conviction_score": round(score, 1),
        "directional_bias": bias,
        "preferred_posture": posture,
        "market_read": market_read,
        "expected_path": expected_path,
        "entry_plan": entry_plan,
        "profit_plan": profit_plan,
        "risk_plan": risk_plan,
        "no_trade_zone": no_trade,
        "alt_strategy": alt_plan,
        "subjective_note": subjective_note,
    }


def source_line(row: dict, index: int) -> str:
    tags = row.get("tags") or "CRYPTO"
    material_len = len(str(row.get("material") or ""))
    return f"{index}. [{row.get('source')}] {row.get('title')} ({tags}, 원문 {material_len:,}자)"


def topic_counts(resources: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in resources:
        tags = [tag.strip() for tag in str(row.get("tags", "")).split(",") if tag.strip()]
        for tag in tags or ["CRYPTO"]:
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def top_topics(resources: list[dict], limit: int = 5) -> list[str]:
    counts = topic_counts(resources)
    return list(counts.keys())[:limit] or ["BTC", "ALT", "MACRO"]


def material_coverage(resources: list[dict]) -> dict:
    lengths = [len(str(row.get("material") or "")) for row in resources]
    full_count = sum(1 for row in resources if row.get("fetch_method") not in {"excerpt_only", "excerpt_fallback"} and len(str(row.get("material") or "")) >= 800)
    return {
        "selected_sources": len(resources),
        "full_text_sources": full_count,
        "total_material_chars": sum(lengths),
        "avg_material_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0,
    }


def resource_digest(resources: list[dict], material_limit: int = 1200) -> list[dict]:
    digest: list[dict] = []
    for row in resources:
        material = row.get("material") or row.get("excerpt") or ""
        digest.append(
            {
                "source": row.get("source", ""),
                "title": row.get("title", ""),
                "tags": row.get("tags", ""),
                "url": row.get("url", ""),
                "score": row.get("trader_score", 0),
                "fetch_method": row.get("fetch_method", ""),
                "material_chars": len(str(material)),
                "excerpt": clean_text(material, material_limit),
            }
        )
    return digest


def resource_full_material(resources: list[dict], material_limit: int = 12000) -> list[dict]:
    full: list[dict] = []
    for index, row in enumerate(resources, start=1):
        material = row.get("material") or row.get("excerpt") or ""
        full.append(
            {
                "index": index,
                "source": row.get("source", ""),
                "source_type": row.get("source_type", ""),
                "title": row.get("title", ""),
                "tags": row.get("tags", ""),
                "url": row.get("url", ""),
                "trader_score": row.get("trader_score", 0),
                "fetch_method": row.get("fetch_method", ""),
                "material_chars": len(str(material)),
                "full_material": clean_text(material, material_limit),
            }
        )
    return full


def infer_source_role(row: dict) -> str:
    tags = set(tag.strip() for tag in str(row.get("tags", "")).split(",") if tag.strip())
    source_type = row.get("source_type")
    if source_type == "community":
        return "심리/과열도 보조자료"
    if tags.intersection({"REG", "ETF"}):
        return "규제/기관 플로우 변수"
    if tags.intersection({"BTC"}):
        return "BTC 방향 기준축"
    if tags.intersection({"ETH", "SOL", "XRP", "ALT", "WEB3"}):
        return "알트 로테이션 후보"
    if tags.intersection({"STABLE", "MACRO"}):
        return "유동성/제도권 채택 변수"
    if tags.intersection({"SECURITY"}):
        return "리스크 회피 변수"
    return "시장 맥락 보조자료"


def build_source_findings(resources: list[dict], market_summary: dict) -> list[dict]:
    findings: list[dict] = []
    level_context = btc_level_context(market_summary)
    indicator_context = btc_indicator_context(market_summary)
    for index, row in enumerate(resources, start=1):
        material = row.get("material") or row.get("excerpt") or ""
        sentences = split_sentences(str(material), 4)
        tags = str(row.get("tags", ""))
        role = infer_source_role(row)
        title = clean_text(row.get("title"), 180)
        evidence = sentences[:3]
        if not evidence:
            evidence = [clean_text(row.get("excerpt"), 260)]
        if "community" == row.get("source_type"):
            trader_read = (
                "커뮤니티 반응은 사실 확정보다 과열/공포의 위치를 읽는 보조 신호입니다. "
                f"{level_context} 이 구간에서 커뮤니티 반응이 강해도 가격이 저항을 넘기 전에는 추격 근거로 격하합니다."
            )
        elif any(tag in tags for tag in ["REG", "ETF"]):
            trader_read = (
                "규제/ETF 재료는 발표 일정과 공식 문서 확인 전까지 가격 추격의 근거가 아니라 변동성 촉매로 둡니다. "
                f"{level_context} 발표 전후에는 이 지지/저항 중 어느 쪽을 종가로 확정하는지가 핵심입니다."
            )
        elif "BTC" in tags:
            trader_read = (
                "BTC 관련 재료는 알트보다 먼저 방향성을 검증해야 하는 기준축입니다. "
                f"{level_context} {indicator_context} 뉴스 강도보다 가격이 이 레벨과 보조지표를 어떻게 소화하는지가 중요합니다."
            )
        elif any(tag in tags for tag in ["ETH", "SOL", "XRP", "ALT"]):
            trader_read = (
                "알트 재료는 독립 호재로 소비하기보다 BTC 안정 이후 섹터 거래량 확산 여부로 검증해야 합니다. "
                f"{eth_relative_context(market_summary)} BTC가 {level_trigger(market_summary, 'support')}을 지키지 못하면 알트 호재는 단기 반등 소재로 낮춰 봅니다."
            )
        else:
            trader_read = (
                "이 자료는 단독 방향성보다 다른 소스와 결합해 장세 배경을 보강하는 역할입니다. "
                f"{level_context} 현재 구조 안에서 보조자료의 의미는 가격 레벨 확인 뒤에만 커집니다."
            )
        findings.append(
            {
                "index": index,
                "source": row.get("source", ""),
                "title": title,
                "role": role,
                "material_chars": len(str(material)),
                "evidence": evidence,
                "trader_read": trader_read,
                "url": row.get("url", ""),
            }
        )
    return findings


def directional_thesis(market_summary: dict, topics: list[str], findings: list[dict], trader_stance: dict | None = None) -> str:
    bias = market_summary.get("bias")
    has_reg = "REG" in topics or "ETF" in topics
    has_alt = any(topic in topics for topic in ["ETH", "SOL", "XRP", "ALT", "WEB3"])
    full_sources = sum(1 for item in findings if item.get("material_chars", 0) >= 800)
    base = f"선택 원문 {len(findings)}건 중 {full_sources}건은 본문을 길게 확보했고, 핵심 축은 {', '.join(topics)}입니다."
    level_context = btc_level_context(market_summary)
    stance_prefix = ""
    if trader_stance:
        stance_prefix = (
            f"내 주관적 포지션은 '{trader_stance.get('preferred_posture')}'이며, "
            f"방향 편향은 '{trader_stance.get('directional_bias')}'입니다. "
        )
    if bias == "risk_on" and has_alt:
        return f"{stance_prefix}{base} {level_context} 현재 해석은 BTC가 리스크 온 구조를 먼저 열어둔 뒤 알트가 후행 확산을 시도하는 국면입니다. 다만 알트는 뉴스 강도가 아니라 BTC 지지 유지와 ETH 상대강도 회복이 같이 확인될 때만 공격적으로 해석합니다."
    if bias == "risk_off":
        return f"{stance_prefix}{base} {level_context} 현재는 반등 기대보다 방어적 자금 이동을 먼저 봐야 합니다. BTC가 가까운 저항을 회복하기 전까지 알트 뉴스는 단기 반등 소재일 뿐 추세 전환 근거로 보기 어렵습니다."
    if has_reg:
        return f"{stance_prefix}{base} {level_context} 이번 묶음은 가격 차트보다 규제, ETF, 제도권 플로우가 방향을 흔드는 조합입니다. 발표 확인 전 포지션 확대보다 이벤트 전후 변동성 구간을 분리하는 판단이 우선입니다."
    return f"{stance_prefix}{base} {level_context} 현재는 BTC 기준축, 니케이의 아시아 위험자산 심리, 골드의 방어 수요가 서로 엇갈리는 혼조 장세입니다. 방향 단정보다 시나리오별 조건을 두고 대응하는 문서가 필요합니다."


def build_key_points(resources: list[dict], market_summary: dict, findings: list[dict], trader_stance: dict | None = None) -> list[str]:
    topics = top_topics(resources)
    coverage = material_coverage(resources)
    points = [
        (
            f"내 관점: {trader_stance.get('directional_bias')} / {trader_stance.get('preferred_posture')} "
            f"/ 확신도 {trader_stance.get('conviction_score')}점입니다."
            if trader_stance
            else "내 관점: 가격 레벨 확인 전까지 포지션 판단을 보류합니다."
        ),
        f"원문 취합: 선택 {coverage['selected_sources']}건, 본문 확보 {coverage['full_text_sources']}건, 총 {coverage['total_material_chars']:,}자 기준으로 분석했습니다.",
        f"시장 체제: {market_summary.get('label')} / 내부 위험선호 점수 {market_summary.get('risk_points')}입니다.",
        btc_level_context(market_summary),
        f"보조지표: {btc_indicator_context(market_summary)}",
        f"파생 포지션: {btc_derivatives_context(market_summary)}",
        f"상대 변화율: {eth_relative_context(market_summary)} 니케이 7D {as_percent(market_summary.get('nikkei_7d'))}, 골드 7D {as_percent(market_summary.get('gold_7d'))}, DXY 7D {as_percent(market_summary.get('dxy_7d'))}.",
        f"핵심 태그는 {', '.join(topics)}이며, BTC 기준축과 알트 후행 로테이션을 분리해서 봐야 합니다.",
        "뉴스는 방향을 '예측'하는 자료가 아니라 가격이 어떤 재료를 소화 중인지 판별하는 촉매로 둡니다.",
    ]
    if any(item.get("role") == "심리/과열도 보조자료" for item in findings):
        points.append("커뮤니티 자료는 과열/공포 온도계로만 쓰고 사실 판단에는 공식 출처를 우선합니다.")
    if any(item.get("role") == "규제/기관 플로우 변수" for item in findings):
        points.append("규제/ETF/기관 플로우는 단기 가격보다 이벤트 전후 변동성 관리가 핵심입니다.")
    return points


def market_structure(market_summary: dict, topics: list[str], trader_stance: dict | None = None) -> dict:
    btc = as_percent(market_summary.get("btc_7d"))
    eth = as_percent(market_summary.get("eth_7d"))
    nikkei = as_percent(market_summary.get("nikkei_7d"))
    gold = as_percent(market_summary.get("gold_7d"))
    dxy = as_percent(market_summary.get("dxy_7d"))
    price = as_price(market_summary.get("btc_price"))
    support = as_price(market_summary.get("btc_nearest_support"))
    resistance = as_price(market_summary.get("btc_nearest_resistance"))
    support_distance = as_percent(market_summary.get("btc_support_distance_pct"))
    resistance_distance = as_percent(market_summary.get("btc_resistance_distance_pct"))
    bias = market_summary.get("bias")
    if bias == "risk_on":
        regime = "BTC 우선 리스크 온 검증 구간"
    elif bias == "risk_off":
        regime = "현금화/방어자산 우위 경계 구간"
    else:
        regime = "방향성 확인 전 혼조 구간"
    stance = trader_stance or {}
    return {
        "regime": regime,
        "trader_bias": f"{stance.get('directional_bias', '데이터 확인 중')} / {stance.get('preferred_posture', '관망')} / 확신도 {stance.get('conviction_score', '데이터 미수집')}점",
        "trader_market_read": stance.get("market_read", ""),
        "trader_expected_path": stance.get("expected_path", ""),
        "trader_entry_plan": stance.get("entry_plan", ""),
        "trader_profit_plan": stance.get("profit_plan", ""),
        "trader_risk_plan": stance.get("risk_plan", ""),
        "trader_no_trade_zone": stance.get("no_trade_zone", ""),
        "trader_alt_strategy": stance.get("alt_strategy", ""),
        "trader_subjective_note": stance.get("subjective_note", ""),
        "critical_levels": f"BTC 현재가 {price}. 가까운 지지 {support}({support_distance}), 가까운 저항 {resistance}({resistance_distance})입니다. 이 두 가격이 이번 브리핑의 1차 시나리오 경계입니다.",
        "technical_indicators": btc_indicator_context(market_summary),
        "derivatives": btc_derivatives_context(market_summary),
        "btc_axis": f"BTC 7일 변화율 {btc}. {btc_level_context(market_summary)} 모든 알트 판단은 BTC가 지지를 지키거나 저항을 회복하는지 확인한 뒤에만 강화합니다.",
        "alts": f"ETH 7일 변화율 {eth}. {eth_relative_context(market_summary)} 알트는 독립 상승보다 BTC 안정, ETH 상대강도, 섹터 거래량 확산이 같이 나올 때 로테이션으로 인정합니다.",
        "japan_risk": f"니케이 7일 변화율 {nikkei}. 일본발 크립토 기사와 함께 보면 아시아 위험자산 심리의 보조축입니다.",
        "defensive_assets": f"골드 7일 변화율 {gold}, DXY 7일 변화율 {dxy}. 금/달러가 강하면 크립토 호재도 짧은 반등으로 끝날 수 있습니다.",
        "sentiment": f"Fear & Greed {market_summary.get('fear_greed')}({market_summary.get('fear_greed_label')}). 감정 지표는 후킹 소재이지만 포지션 근거로는 격하합니다.",
        "reference_lens": "Bitcoin Illuminati식 관점은 BTC 우선, 차트 무효화, 알트 시즌 조건 확인, 과열/공포 분리입니다.",
    }


def build_scenarios(market_summary: dict, topics: list[str], findings: list[dict]) -> list[dict]:
    has_alt = any(topic in topics for topic in ["ETH", "SOL", "XRP", "ALT", "WEB3"])
    has_reg = "REG" in topics or "ETF" in topics
    support = level_trigger(market_summary, "support")
    resistance = level_trigger(market_summary, "resistance")
    price = as_price(market_summary.get("btc_price"))
    indicator_context = btc_indicator_context(market_summary)
    derivative_context = btc_derivatives_context(market_summary)
    return [
        {
            "case": "Bull",
            "probability_view": "조건부 우세",
            "trigger": f"BTC가 현재 {price} 부근에서 {support}을 지키고, 4H/일봉 종가가 {resistance} 위로 회복하는 경우",
            "expected_path": "가까운 저항 회복은 단기 매물대 흡수 신호입니다. 이후 MA20/MA50 위 체류와 RSI 50선 이상 유지가 붙으면 ETH/SOL/XRP 등 선택 소스에 반복 등장한 섹터로 관심이 이동합니다.",
            "watch": f"{resistance} 위 종가, 거래량 증가, {indicator_context}, 일본 거래소/기관 관련 후속 공지",
        },
        {
            "case": "Base",
            "probability_view": "기본 경로",
            "trigger": f"BTC가 {support}~{resistance} 사이에서 체류하고 니케이와 골드 신호가 엇갈리는 경우",
            "expected_path": "뉴스가 가격을 밀어 올리기보다 단기 콘텐츠 소재로 소비됩니다. 이 구간은 강한 결론보다 관찰 리스트와 무효화 조건이 중요합니다.",
            "watch": f"뉴스 발표 시각, 공식 출처, 거래소 공지, BTC {support}/{resistance} 반응",
        },
        {
            "case": "Bear",
            "probability_view": "경계 경로",
            "trigger": f"골드/DXY가 강하고 BTC가 {support} 아래로 종가 이탈하거나 규제성 헤드라인이 공식 확인되는 경우",
            "expected_path": "알트 호재는 개별 반등에 그치고, 시장은 현금화와 변동성 축소를 우선합니다. 지지 이탈 뒤에는 MA50/MA200과 30D 저점이 다음 방어선으로 재평가됩니다.",
            "watch": f"{support} 이탈, ETF/규제 악재 확인, 커뮤니티 과열 후 급랭, {derivative_context}",
        },
        {
            "case": "Alt Season Validation",
            "probability_view": "아직 검증 필요" if has_alt else "대기",
            "trigger": f"BTC가 {support}을 지키며 {resistance} 아래에서 과열 없이 횡보하고, {eth_relative_context(market_summary)}가 개선되는 경우",
            "expected_path": "알트 시즌은 선언이 아니라 검증입니다. 단일 호재보다 여러 섹터가 동시에 거래대금 확산을 보일 때 인정합니다.",
            "watch": "ETH 7D-BTC 7D 상대 변화율, SOL/XRP/SUI 등 반복 언급 종목의 거래량, BTC 도미넌스 변화",
        },
        {
            "case": "Event Volatility",
            "probability_view": "높음" if has_reg else "보통",
            "trigger": "규제, ETF, 기관, 거래소 공지의 발표 전후",
            "expected_path": "발표 전 기대감과 발표 후 차익실현이 분리됩니다. 기사 제목만 보고 방향을 정하지 않습니다.",
            "watch": f"공식 문서 원문, 발표 시간, 시장 반응 1차/2차 파동, {support}/{resistance} 종가 확정",
        },
    ]


def build_weekly_sections(thesis: str, market: dict, scenarios: list[dict], findings: list[dict]) -> list[dict]:
    leading_sources = findings[:4]
    source_summary = " ".join(
        f"{item['source']}의 '{item['title']}'는 {item['role']}로 분류됩니다." for item in leading_sources
    )
    return [
        {
            "heading": "내 매매 관점",
            "body": (
                f"{market.get('trader_market_read', '')}\n\n"
                f"예상 경로: {market.get('trader_expected_path', '')}\n\n"
                f"진입: {market.get('trader_entry_plan', '')}\n\n"
                f"리스크: {market.get('trader_risk_plan', '')}\n\n"
                f"하지 않을 행동: {market.get('trader_no_trade_zone', '')}"
            ),
        },
        {
            "heading": "이번 주 핵심 논지",
            "body": f"{thesis}\n\n{source_summary} 따라서 이번 주 문서는 단순 가격 전망보다 BTC 기준축과 이벤트성 변동성을 분리해야 합니다.",
        },
        {
            "heading": "BTC 기준축",
            "body": f"{market['btc_axis']} BTC가 기준선을 지키면 알트 뉴스는 후행 확산 재료가 되고, 반대로 BTC가 무너지면 같은 뉴스도 단기 반등 소재로 격하됩니다. 이 관점이 브리핑 전체의 1번 필터입니다.",
        },
        {
            "heading": "중요 가격대와 보조지표",
            "body": f"{market['critical_levels']}\n\n{market['technical_indicators']}\n\n{market['derivatives']} 이 숫자들은 예측값이 아니라 시나리오 경계입니다. 저항 회복 전에는 강세 확정이 아니고, 지지 이탈 뒤에는 원문 호재도 방어적으로 재분류합니다.",
        },
        {
            "heading": "니케이, 골드, 달러로 보는 자산 이동",
            "body": f"{market['japan_risk']} {market['defensive_assets']} 일본 크립토 기사와 니케이를 같이 보는 이유는 일본발 자금/상장/제도권 채택 뉴스가 아시아 위험자산 심리와 붙어 움직일 때가 많기 때문입니다.",
        },
        {
            "heading": "알트 로테이션 판별",
            "body": f"{market['alts']} 선택 소스 중 알트성 재료는 BTC 안정 이후에만 공격적으로 해석합니다. 알트 시즌은 제목이 아니라 ETH/BTC, BTC 도미넌스, 섹터 거래대금 확산으로 검증합니다.",
        },
        {
            "heading": "시나리오와 무효화",
            "body": " / ".join(f"{case['case']}: {case['trigger']}" for case in scenarios[:3]) + "\n\n강세 시나리오의 무효화는 BTC 지지 이탈, 방어자산 강세, 공식 출처와 다른 루머 확인입니다.",
        },
    ]


def build_time_blocks(resources: list[dict], findings: list[dict], market: dict) -> list[dict]:
    sorted_rows = sorted(resources, key=lambda row: row.get("posted_at") or "", reverse=True)
    labels = [
        ("아시아 장 전후", "니케이, 일본 거래소/기관 기사, 엔화권 리스크 심리를 먼저 확인합니다."),
        ("유럽 장 진입", "미국 이벤트 전 선반영 여부와 BTC 박스 상단/하단 반응을 확인합니다."),
        ("미국 장 전후", "ETF, SEC, 금리, 달러, 나스닥과 BTC 동조/분리를 확인합니다."),
        ("익일 체크", "뉴스가 가격에 남았는지, 아니면 커뮤니티 과열만 남았는지 재평가합니다."),
    ]
    blocks: list[dict] = []
    for index, (label, guide) in enumerate(labels):
        chunk = sorted_rows[index:: len(labels)] or sorted_rows[:3]
        related = [clean_text(row.get("title"), 150) for row in chunk[:4]]
        blocks.append(
            {
                "time_zone": label,
                "watch": related,
                "trader_read": f"{guide} 관련 태그는 {', '.join(top_topics(chunk, 3))}입니다. {market.get('critical_levels', '')} 여기서 확인할 것은 뉴스 수가 아니라 BTC가 그 뉴스를 가격으로 인정하는지입니다.",
            }
        )
    return blocks


def build_invalidation_points(market_summary: dict, findings: list[dict]) -> list[str]:
    support = level_trigger(market_summary, "support")
    resistance = level_trigger(market_summary, "resistance")
    return [
        f"BTC가 {support} 아래로 종가 이탈하면 알트 강세 해석은 보류합니다.",
        f"BTC가 {resistance} 위에서 종가를 확정하지 못하면 강세 시나리오는 추격이 아니라 관찰로 낮춥니다.",
        "공식 발표가 기사 제목보다 약하거나 일정이 지연되면 이벤트 프리미엄을 낮춥니다.",
        "골드와 달러가 동시에 강해지면 크립토 호재도 단기 반등으로 제한될 수 있습니다.",
        "커뮤니티 화제성이 급등했는데 거래량이 따라오지 않으면 과열 신호로 처리합니다.",
        "선택 소스 간 주장 충돌이 있으면 가격 반응과 공식 문서 확인 전까지 중립으로 둡니다.",
    ]


def local_generate_brief(resources: list[dict], market_snapshot: dict, briefing_type: str, tone: str) -> dict:
    market_summary = summarize_market(market_snapshot)
    topics = top_topics(resources)
    findings = build_source_findings(resources, market_summary)
    trader_stance = build_trader_stance(market_summary, topics, findings)
    thesis = directional_thesis(market_summary, topics, findings, trader_stance)
    market = market_structure(market_summary, topics, trader_stance)
    scenarios = build_scenarios(market_summary, topics, findings)
    key_points = build_key_points(resources, market_summary, findings, trader_stance)
    source_lines = [source_line(row, index) for index, row in enumerate(resources[:20], start=1)]
    today = datetime.now().strftime("%Y-%m-%d")
    title_prefix = "주간 시장 방향 리서치" if briefing_type == "weekly" else "일간 시간대별 BTC 리서치"

    return {
        "provider": "무료 로컬 전문 분석 엔진",
        "briefing_type": briefing_type,
        "tone": tone,
        "generated_at": today,
        "title": f"{today} {title_prefix}",
        "one_line": thesis,
        "reference_perspective": BITCOIN_ILLUMINATI_VIEWPOINT,
        "material_coverage": material_coverage(resources),
        "market_summary": market_summary,
        "trader_stance": trader_stance,
        "market_structure": market,
        "source_findings": findings,
        "key_points": key_points,
        "trader_sentences": [
            thesis,
            trader_stance["market_read"],
            trader_stance["expected_path"],
            trader_stance["entry_plan"],
            trader_stance["risk_plan"],
            market["critical_levels"],
            market["technical_indicators"],
            market["btc_axis"],
            market["alts"],
            trader_stance["subjective_note"],
        ],
        "scenarios": scenarios,
        "invalidation_points": build_invalidation_points(market_summary, findings),
        "action_plan": [
            f"현재 입장: {trader_stance['directional_bias']} / {trader_stance['preferred_posture']} / 확신도 {trader_stance['conviction_score']}점.",
            f"1차 필터: BTC가 {level_trigger(market_summary, 'support')}을 지키는지, {level_trigger(market_summary, 'resistance')}을 회복하는지 먼저 판별합니다.",
            f"진입 계획: {trader_stance['entry_plan']}",
            f"익절 계획: {trader_stance['profit_plan']}",
            f"하지 않을 행동: {trader_stance['no_trade_zone']}",
            "2차 필터: ETH 7D-BTC 7D 상대 변화율과 주요 알트 거래대금으로 알트 로테이션 여부를 확인합니다.",
            "3차 필터: 일본/글로벌 기사에서 공식 발표, 거래소 공지, ETF/규제 일정을 분리합니다.",
            "콘텐츠화: 카드뉴스는 강세 단정이 아니라 '조건이 충족되면 무엇이 바뀌는가'를 중심으로 구성합니다.",
        ],
        "weekly_brief": build_weekly_sections(thesis, market, scenarios, findings),
        "daily_brief": build_time_blocks(resources, findings, market),
        "source_digest": resource_digest(resources),
        "source_lines": source_lines,
        "risk_notes": [
            DISCLAIMER,
            "커뮤니티 자료는 사실 확인 전 루머로 취급합니다.",
            "가격 예측 대신 조건부 시나리오, 무효화 조건, 체크포인트 중심으로 표현합니다.",
        ],
    }


def extract_json_object(text: str) -> tuple[Optional[dict], Optional[str]]:
    cleaned = (text or "").strip().removeprefix("\ufeff").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed, None
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            parsed, _ = decoder.raw_decode(cleaned[match.start() :])
            if isinstance(parsed, dict):
                return parsed, None
        except Exception:
            continue
    return None, "JSON 객체를 찾지 못했습니다."


def post_json(url: str, payload: dict, headers: dict, timeout: int = 240) -> tuple[Optional[dict], Optional[str]]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="ignore")), None
    except Exception as error:
        return None, str(error)


def call_openai_compatible(prompt: str, config: dict) -> tuple[Optional[str], Optional[str]]:
    api_key = config.get("api_key")
    base_url = str(config.get("base_url") or "").rstrip("/")
    model = config.get("model")
    if not api_key or not base_url or not model:
        return None, "OpenAI-compatible 설정에 base_url, api_key, model이 모두 필요합니다."
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "당신은 한국어로 쓰는 크립토 시장 리서치 애널리스트입니다. "
                    "선택된 모든 원문을 읽고 BTC 기준축, 유동성, 알트 로테이션, 규제/ETF 이벤트, 무효화 조건을 분리합니다. "
                    "내부 추론은 출력하지 말고 결론, 근거, 시나리오만 전문적인 JSON으로 출력합니다."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": float(config.get("temperature", 0.35)),
        "max_tokens": int(config.get("max_tokens", 9000)),
        "response_format": {"type": "json_object"},
    }
    result, error = post_json(
        f"{base_url}/chat/completions",
        payload,
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    if error or not result:
        return None, error or "응답이 비어 있습니다."
    try:
        return result["choices"][0]["message"]["content"], None
    except Exception as parse_error:
        return None, str(parse_error)


def call_ollama(prompt: str, config: dict) -> tuple[Optional[str], Optional[str]]:
    base_url = str(config.get("base_url") or "http://localhost:11434").rstrip("/")
    model = config.get("model") or "qwen3:4b"
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "한국어 크립토 시장 리서치 애널리스트로서 JSON만 출력합니다. "
                    "모든 선택 원문을 읽고, 라이트 요약이 아니라 BTC 중심 전문 브리핑을 작성합니다."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": float(config.get("temperature", 0.25)), "num_ctx": int(config.get("num_ctx", 24000))},
    }
    result, error = post_json(f"{base_url}/api/chat", payload, {"Content-Type": "application/json"}, timeout=300)
    if error or not result:
        return None, error or "응답이 비어 있습니다."
    try:
        return result["message"]["content"], None
    except Exception as parse_error:
        return None, str(parse_error)


def brief_prompt(resources: list[dict], market_snapshot: dict, briefing_type: str, tone: str) -> str:
    return json.dumps(
        {
            "mission": (
                "선택된 모든 리소스의 원문 full_material을 읽고 전문 트레이더 리서치 문서를 작성한다. "
                "가벼운 요약, 단순 수치 나열, '중요합니다' 식 문장을 금지한다. "
                "각 원문별 핵심 주장과 트레이더 해석을 분리하고, BTC 기준축과 알트 로테이션 조건을 명확히 쓴다. "
                "market_snapshot.price_levels, technicals, derivatives의 숫자를 사용해 현재가, 지지, 저항, MA, RSI, MACD, ATR, 펀딩비를 반드시 포함한다. "
                "반드시 한 명의 주관적 트레이더처럼 directional_bias, entry_plan, profit_plan, risk_plan, no_trade_zone을 입장 표명 문장으로 쓴다."
            ),
            "briefing_type": briefing_type,
            "tone": tone,
            "reference_perspective": BITCOIN_ILLUMINATI_VIEWPOINT,
            "market_snapshot": market_snapshot,
            "resources": resource_full_material(resources),
            "required_schema": {
                "title": "string",
                "one_line": "2-3 sentence professional thesis",
                "material_coverage": "object",
                "market_summary": "object",
                "trader_stance": {
                    "persona": "string",
                    "conviction_score": "number",
                    "directional_bias": "subjective stance",
                    "preferred_posture": "positioning style",
                    "market_read": "first-person professional market read",
                    "expected_path": "how this trader expects price to move from here",
                    "entry_plan": "subjective entry plan",
                    "profit_plan": "subjective take-profit plan",
                    "risk_plan": "invalidation and stop plan",
                    "no_trade_zone": "what this trader refuses to trade",
                    "alt_strategy": "how this trader handles alts",
                    "subjective_note": "personal trading philosophy",
                },
                "market_structure": {
                    "regime": "string",
                    "trader_bias": "string",
                    "trader_market_read": "paragraph",
                    "trader_expected_path": "paragraph",
                    "trader_entry_plan": "paragraph",
                    "trader_profit_plan": "paragraph",
                    "trader_risk_plan": "paragraph",
                    "trader_no_trade_zone": "paragraph",
                    "trader_alt_strategy": "paragraph",
                    "trader_subjective_note": "paragraph",
                    "critical_levels": "current BTC price, nearest support/resistance and distances",
                    "technical_indicators": "MA20/50/200, RSI14, MACD, ATR14",
                    "derivatives": "funding, mark price, open interest",
                    "btc_axis": "paragraph",
                    "alts": "paragraph",
                    "japan_risk": "paragraph",
                    "defensive_assets": "paragraph",
                    "sentiment": "paragraph",
                },
                "source_findings": [
                    {
                        "source": "string",
                        "title": "string",
                        "role": "string",
                        "evidence": ["short paraphrased evidence"],
                        "trader_read": "professional interpretation",
                        "url": "string",
                    }
                ],
                "key_points": ["specific analytical bullet"],
                "trader_sentences": ["publication-ready Korean sentence"],
                "scenarios": [
                    {
                        "case": "Bull/Base/Bear/Alt Season/Event Volatility",
                        "trigger": "price-level based trigger with exact BTC support/resistance when available",
                        "expected_path": "string",
                        "watch": "string",
                    }
                ],
                "invalidation_points": ["string"],
                "action_plan": ["string"],
                "weekly_brief": [{"heading": "string", "body": "2-4 paragraph body"}],
                "daily_brief": [{"time_zone": "string", "watch": ["string"], "trader_read": "string"}],
                "source_digest": [{"source": "string", "title": "string", "url": "string", "excerpt": "string"}],
                "risk_notes": ["string"],
            },
        },
        ensure_ascii=False,
    )


def normalize_external_brief(parsed: dict, local: dict, provider: str) -> dict:
    parsed.setdefault("provider", provider)
    parsed.setdefault("reference_perspective", BITCOIN_ILLUMINATI_VIEWPOINT)
    parsed.setdefault("material_coverage", local["material_coverage"])
    parsed.setdefault("market_summary", local["market_summary"])
    parsed.setdefault("trader_stance", local["trader_stance"])
    parsed.setdefault("market_structure", local["market_structure"])
    parsed.setdefault("source_findings", local["source_findings"])
    parsed.setdefault("source_digest", local["source_digest"])
    parsed.setdefault("source_lines", local["source_lines"])
    parsed.setdefault("risk_notes", local["risk_notes"])
    parsed.setdefault("scenarios", local["scenarios"])
    parsed.setdefault("invalidation_points", local["invalidation_points"])
    parsed.setdefault("action_plan", local["action_plan"])
    return parsed


def generate_trader_brief(resources: list[dict], market_snapshot: dict, briefing_type: str, tone: str, config: dict) -> tuple[dict, Optional[str]]:
    local = local_generate_brief(resources, market_snapshot, briefing_type, tone)
    provider = config.get("provider", PROVIDER_LOCAL)
    if provider == PROVIDER_LOCAL:
        return local, None

    prompt = brief_prompt(resources, market_snapshot, briefing_type, tone)
    if provider == PROVIDER_OLLAMA:
        raw, error = call_ollama(prompt, config)
    else:
        raw, error = call_openai_compatible(prompt, config)
    if error or not raw:
        local["_provider_warning"] = f"외부 추론 실패로 로컬 전문 분석 엔진을 사용했습니다: {error}"
        return local, None
    parsed, parse_error = extract_json_object(raw)
    if parse_error or not parsed:
        local["_provider_warning"] = f"외부 추론 JSON 파싱 실패로 로컬 전문 분석 엔진을 사용했습니다: {parse_error}"
        return local, None
    return normalize_external_brief(parsed, local, provider), None


def card_blueprint(count: int) -> list[str]:
    base = [
        "내 관점",
        "매매 계획",
        "BTC 가격 레벨",
        "보조지표",
        "원문 근거 1",
        "원문 근거 2",
        "니케이/골드/달러",
        "알트 로테이션 조건",
        "Bull/Base/Bear",
        "무효화 조건",
        "오늘의 체크리스트",
    ]
    return base[:count]


def make_card_set(brief: dict, resources: list[dict], count: int, label: str) -> list[dict]:
    findings = brief.get("source_findings") or []
    scenarios = brief.get("scenarios") or []
    market = brief.get("market_structure") or {}
    headings = card_blueprint(count)
    cards: list[dict] = []
    stance = brief.get("trader_stance") or {}
    for index, heading in enumerate(headings, start=1):
        finding = findings[(index - 1) % len(findings)] if findings else {}
        scenario = scenarios[(index - 1) % len(scenarios)] if scenarios else {}
        if heading == "내 관점":
            body = clean_text(
                f"{stance.get('directional_bias', '')} / {stance.get('preferred_posture', '')}. {stance.get('market_read', brief.get('one_line', ''))}",
                220,
            )
            caption = clean_text(f"예상 경로: {stance.get('expected_path', '')}", 180)
        elif heading == "매매 계획":
            body = clean_text(f"{stance.get('entry_plan', '')} {stance.get('risk_plan', '')}", 220)
            caption = clean_text(stance.get("no_trade_zone", ""), 180)
        elif "원문 근거" in heading and finding:
            body = f"{finding.get('source')}의 원문은 {finding.get('role')}로 읽힙니다. 핵심은 {clean_text(finding.get('trader_read'), 140)}"
            caption = clean_text(" / ".join(finding.get("evidence", [])[:2]), 180)
        elif heading == "BTC 가격 레벨":
            body = clean_text(market.get("critical_levels") or market.get("btc_axis") or brief.get("one_line"), 190)
            caption = "현재가가 가까운 지지와 저항 중 어느 쪽을 종가로 확정하는지가 시나리오 경계입니다."
        elif heading == "보조지표":
            body = clean_text(f"{market.get('technical_indicators', '')} {market.get('derivatives', '')}", 210)
            caption = "MA, RSI, MACD, ATR, 펀딩비를 함께 봐야 가격 레벨의 신뢰도를 구분할 수 있습니다."
        elif heading == "BTC 기준축":
            body = clean_text(market.get("btc_axis") or brief.get("one_line"), 190)
            caption = "BTC가 구조를 지키는지 먼저 확인한 뒤 알트 해석을 붙입니다."
        elif heading == "니케이/골드/달러":
            body = clean_text(f"{market.get('japan_risk', '')} {market.get('defensive_assets', '')}", 190)
            caption = "크립토 단독이 아니라 위험자산과 방어자산의 자금 이동을 함께 봅니다."
        elif heading == "알트 로테이션 조건":
            body = clean_text(market.get("alts") or "", 190)
            caption = "알트 시즌은 선언이 아니라 BTC 안정, ETH 상대강도, 거래량 확산으로 검증합니다."
        elif heading == "Bull/Base/Bear" and scenario:
            body = clean_text(f"{scenario.get('case', 'Scenario')}: {scenario.get('expected_path', brief.get('one_line', ''))}", 190)
            caption = clean_text(scenario.get("trigger", ""), 160)
        else:
            body = clean_text(brief.get("one_line", ""), 190)
            caption = clean_text((brief.get("key_points") or [""])[0], 160)
        source = resources[(index - 1) % len(resources)] if resources else {}
        cards.append(
            {
                "set": label,
                "slide": index,
                "headline": heading,
                "body": body,
                "visual_direction": "BTC 캔들 중심에 니케이/골드/DXY 보조축을 얹고, 원문 출처는 하단 작은 라벨로 배치",
                "source_hint": f"{source.get('source', '')} / {source.get('title', '')}"[:180],
                "caption": caption,
            }
        )
    return cards


def build_note_markdown(brief: dict, resources: list[dict]) -> str:
    lines = [f"# {brief.get('title', 'Crypto Trader Briefing')}", "", brief.get("one_line", ""), ""]
    stance = brief.get("trader_stance") or {}
    lines.append("## 1. 내 매매 관점")
    for key, label in [
        ("persona", "관점"),
        ("directional_bias", "방향 편향"),
        ("preferred_posture", "선호 포지션"),
        ("conviction_score", "확신도"),
        ("market_read", "시장 해석"),
        ("expected_path", "예상 경로"),
        ("entry_plan", "진입 계획"),
        ("profit_plan", "익절 계획"),
        ("risk_plan", "무효화/리스크"),
        ("no_trade_zone", "매매 금지 구간"),
        ("alt_strategy", "알트 대응"),
        ("subjective_note", "매매 철학"),
    ]:
        if stance.get(key) != "":
            lines.append(f"- {label}: {stance.get(key)}")
    lines.append("")
    lines.append("## 2. 결론")
    for point in brief.get("key_points", []):
        lines.append(f"- {point}")
    lines.append("")
    lines.append("## 3. 현재 가격·핵심 레벨")
    market = brief.get("market_structure") or {}
    for key in ["critical_levels", "technical_indicators", "derivatives", "btc_axis", "alts"]:
        if market.get(key):
            lines.append(f"- {key}: {market.get(key)}")
    lines.append("")
    lines.append("## 4. 원문별 해석")
    for item in brief.get("source_findings", []):
        lines.append(f"### {item.get('source')} - {item.get('title')}")
        lines.append(f"- 역할: {item.get('role')}")
        for evidence in item.get("evidence", []):
            lines.append(f"- 근거: {evidence}")
        lines.append(f"- 트레이더 해석: {item.get('trader_read')}")
        lines.append("")
    lines.append("## 5. 시장 구조")
    for key, value in (brief.get("market_structure") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## 6. 시나리오")
    for scenario in brief.get("scenarios", []):
        lines.append(f"### {scenario.get('case')}")
        lines.append(f"- 조건: {scenario.get('trigger')}")
        lines.append(f"- 경로: {scenario.get('expected_path')}")
        lines.append(f"- 체크: {scenario.get('watch')}")
    lines.append("")
    lines.append("## 7. 무효화 조건")
    for item in brief.get("invalidation_points", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 참고 리소스")
    for row in resources[:20]:
        lines.append(f"- [{row.get('source')}] {row.get('title')} - {row.get('url')}")
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    return "\n".join(lines)


def generate_content_package(brief: dict, resources: list[dict], custom_count: int = 8) -> dict:
    suggested = max(5, min(9, custom_count or 8))
    cards = {
        "5장": make_card_set(brief, resources, 5, "5장"),
        "6장": make_card_set(brief, resources, 6, "6장"),
        "7장": make_card_set(brief, resources, 7, "7장"),
        "자율제안": make_card_set(brief, resources, suggested, "자율제안"),
    }
    return {
        "cards": cards,
        "note_markdown": build_note_markdown(brief, resources),
        "short_copy": {
            "x_thread": brief.get("trader_sentences", [])[:6],
            "thumbnail": brief.get("one_line", ""),
            "comment_question": "이번 장세는 BTC 기준축이 알트를 살리는 구조인가, 아니면 뉴스만 순환하는 박스권인가?",
        },
    }
