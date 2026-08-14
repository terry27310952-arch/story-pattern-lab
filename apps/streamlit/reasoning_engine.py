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
        return "N/A"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return str(value)


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


def build_source_findings(resources: list[dict]) -> list[dict]:
    findings: list[dict] = []
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
            trader_read = "커뮤니티 반응은 사실 확정보다 과열/공포의 위치를 읽는 보조 신호입니다. 제목과 댓글 수만 반영하고, 루머는 시나리오 근거로 격하합니다."
        elif any(tag in tags for tag in ["REG", "ETF"]):
            trader_read = "규제/ETF 재료는 발표 일정과 공식 문서 확인 전까지 가격 추격의 근거가 아니라 변동성 촉매로 둡니다."
        elif "BTC" in tags:
            trader_read = "BTC 관련 재료는 알트보다 먼저 방향성을 검증해야 하는 기준축입니다. 뉴스 강도보다 가격이 지지/저항을 어떻게 소화하는지가 중요합니다."
        elif any(tag in tags for tag in ["ETH", "SOL", "XRP", "ALT"]):
            trader_read = "알트 재료는 독립 호재로 소비하기보다 BTC 안정 이후 섹터 거래량 확산 여부로 검증해야 합니다."
        else:
            trader_read = "이 자료는 단독 방향성보다 다른 소스와 결합해 장세 배경을 보강하는 역할입니다."
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


def directional_thesis(market_summary: dict, topics: list[str], findings: list[dict]) -> str:
    bias = market_summary.get("bias")
    has_reg = "REG" in topics or "ETF" in topics
    has_alt = any(topic in topics for topic in ["ETH", "SOL", "XRP", "ALT", "WEB3"])
    full_sources = sum(1 for item in findings if item.get("material_chars", 0) >= 800)
    base = f"선택 원문 {len(findings)}건 중 {full_sources}건은 본문을 길게 확보했고, 핵심 축은 {', '.join(topics)}입니다."
    if bias == "risk_on" and has_alt:
        return f"{base} 현재 해석은 BTC가 리스크 온 구조를 먼저 열어둔 뒤 알트가 후행 확산을 시도하는 국면입니다. 다만 알트는 뉴스 강도가 아니라 BTC 지지 유지와 ETH 상대강도 회복이 같이 확인될 때만 공격적으로 해석합니다."
    if bias == "risk_off":
        return f"{base} 현재는 반등 기대보다 방어적 자금 이동을 먼저 봐야 합니다. BTC가 기준선을 회복하기 전까지 알트 뉴스는 단기 반등 소재일 뿐 추세 전환 근거로 보기 어렵습니다."
    if has_reg:
        return f"{base} 이번 묶음은 가격 차트보다 규제, ETF, 제도권 플로우가 방향을 흔드는 조합입니다. 발표 확인 전 포지션 확대보다 이벤트 전후 변동성 구간을 분리하는 판단이 우선입니다."
    return f"{base} 현재는 BTC 기준축, 니케이의 아시아 위험자산 심리, 골드의 방어 수요가 서로 엇갈리는 혼조 장세입니다. 방향 단정보다 시나리오별 조건을 두고 대응하는 문서가 필요합니다."


def build_key_points(resources: list[dict], market_summary: dict, findings: list[dict]) -> list[str]:
    topics = top_topics(resources)
    coverage = material_coverage(resources)
    points = [
        f"원문 취합: 선택 {coverage['selected_sources']}건, 본문 확보 {coverage['full_text_sources']}건, 총 {coverage['total_material_chars']:,}자 기준으로 분석했습니다.",
        f"시장 체제: {market_summary.get('label')} / 내부 위험선호 점수 {market_summary.get('risk_points')}입니다.",
        f"BTC 7D {as_percent(market_summary.get('btc_7d'))}, ETH 7D {as_percent(market_summary.get('eth_7d'))}, 니케이 7D {as_percent(market_summary.get('nikkei_7d'))}, 골드 7D {as_percent(market_summary.get('gold_7d'))}.",
        f"핵심 태그는 {', '.join(topics)}이며, BTC 기준축과 알트 후행 로테이션을 분리해서 봐야 합니다.",
        "뉴스는 방향을 '예측'하는 자료가 아니라 가격이 어떤 재료를 소화 중인지 판별하는 촉매로 둡니다.",
    ]
    if any(item.get("role") == "심리/과열도 보조자료" for item in findings):
        points.append("커뮤니티 자료는 과열/공포 온도계로만 쓰고 사실 판단에는 공식 출처를 우선합니다.")
    if any(item.get("role") == "규제/기관 플로우 변수" for item in findings):
        points.append("규제/ETF/기관 플로우는 단기 가격보다 이벤트 전후 변동성 관리가 핵심입니다.")
    return points


def market_structure(market_summary: dict, topics: list[str]) -> dict:
    btc = as_percent(market_summary.get("btc_7d"))
    eth = as_percent(market_summary.get("eth_7d"))
    nikkei = as_percent(market_summary.get("nikkei_7d"))
    gold = as_percent(market_summary.get("gold_7d"))
    dxy = as_percent(market_summary.get("dxy_7d"))
    bias = market_summary.get("bias")
    if bias == "risk_on":
        regime = "BTC 우선 리스크 온 검증 구간"
    elif bias == "risk_off":
        regime = "현금화/방어자산 우위 경계 구간"
    else:
        regime = "방향성 확인 전 혼조 구간"
    return {
        "regime": regime,
        "btc_axis": f"BTC 7일 변화율 {btc}. 모든 알트 판단은 BTC가 단기 기준선을 지키는지 확인한 뒤에만 강화합니다.",
        "alts": f"ETH 7일 변화율 {eth}. 알트는 독립 상승보다 BTC 안정, ETH 상대강도, 섹터 거래량 확산이 같이 나올 때 로테이션으로 인정합니다.",
        "japan_risk": f"니케이 7일 변화율 {nikkei}. 일본발 크립토 기사와 함께 보면 아시아 위험자산 심리의 보조축입니다.",
        "defensive_assets": f"골드 7일 변화율 {gold}, DXY 7일 변화율 {dxy}. 금/달러가 강하면 크립토 호재도 짧은 반등으로 끝날 수 있습니다.",
        "sentiment": f"Fear & Greed {market_summary.get('fear_greed')}({market_summary.get('fear_greed_label')}). 감정 지표는 후킹 소재이지만 포지션 근거로는 격하합니다.",
        "reference_lens": "Bitcoin Illuminati식 관점은 BTC 우선, 차트 무효화, 알트 시즌 조건 확인, 과열/공포 분리입니다.",
    }


def build_scenarios(market_summary: dict, topics: list[str], findings: list[dict]) -> list[dict]:
    has_alt = any(topic in topics for topic in ["ETH", "SOL", "XRP", "ALT", "WEB3"])
    has_reg = "REG" in topics or "ETF" in topics
    return [
        {
            "case": "Bull",
            "probability_view": "조건부 우세",
            "trigger": "BTC가 단기 기준선을 지키며 ETH 상대강도와 거래량이 같이 살아나는 경우",
            "expected_path": "BTC가 먼저 반등 신뢰를 만들고, 이후 ETH/SOL/XRP 등 선택 소스에 반복 등장한 섹터로 관심이 이동합니다.",
            "watch": "BTC 종가, ETH/BTC, 알트 거래대금, 일본 거래소/기관 관련 후속 공지",
        },
        {
            "case": "Base",
            "probability_view": "기본 경로",
            "trigger": "BTC는 박스권, 니케이와 골드는 엇갈리고 뉴스만 순환하는 경우",
            "expected_path": "뉴스가 가격을 밀어 올리기보다 단기 콘텐츠 소재로 소비됩니다. 이 구간은 강한 결론보다 관찰 리스트와 무효화 조건이 중요합니다.",
            "watch": "뉴스 발표 시각, 공식 출처, 거래소 공지, BTC 박스 상단/하단 반응",
        },
        {
            "case": "Bear",
            "probability_view": "경계 경로",
            "trigger": "골드/DXY가 강하고 BTC가 기준선을 이탈하거나 규제성 헤드라인이 확인되는 경우",
            "expected_path": "알트 호재는 개별 반등에 그치고, 시장은 현금화와 변동성 축소를 우선합니다.",
            "watch": "BTC 지지 이탈, ETF/규제 악재 확인, 커뮤니티 과열 후 급랭",
        },
        {
            "case": "Alt Season Validation",
            "probability_view": "아직 검증 필요" if has_alt else "대기",
            "trigger": "BTC 횡보 안정 + ETH 상대강도 회복 + 선택 소스의 알트 재료가 거래량으로 확인되는 경우",
            "expected_path": "알트 시즌은 선언이 아니라 검증입니다. 단일 호재보다 여러 섹터가 동시에 거래대금 확산을 보일 때 인정합니다.",
            "watch": "ETH/BTC, SOL/XRP/SUI 등 반복 언급 종목의 거래량, BTC 도미넌스 변화",
        },
        {
            "case": "Event Volatility",
            "probability_view": "높음" if has_reg else "보통",
            "trigger": "규제, ETF, 기관, 거래소 공지의 발표 전후",
            "expected_path": "발표 전 기대감과 발표 후 차익실현이 분리됩니다. 기사 제목만 보고 방향을 정하지 않습니다.",
            "watch": "공식 문서 원문, 발표 시간, 시장 반응 1차/2차 파동",
        },
    ]


def build_weekly_sections(thesis: str, market: dict, scenarios: list[dict], findings: list[dict]) -> list[dict]:
    leading_sources = findings[:4]
    source_summary = " ".join(
        f"{item['source']}의 '{item['title']}'는 {item['role']}로 분류됩니다." for item in leading_sources
    )
    return [
        {
            "heading": "이번 주 핵심 논지",
            "body": f"{thesis}\n\n{source_summary} 따라서 이번 주 문서는 단순 가격 전망보다 BTC 기준축과 이벤트성 변동성을 분리해야 합니다.",
        },
        {
            "heading": "BTC 기준축",
            "body": f"{market['btc_axis']} BTC가 기준선을 지키면 알트 뉴스는 후행 확산 재료가 되고, 반대로 BTC가 무너지면 같은 뉴스도 단기 반등 소재로 격하됩니다. 이 관점이 브리핑 전체의 1번 필터입니다.",
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
            "body": " / ".join(f"{case['case']}: {case['trigger']}" for case in scenarios[:3]) + "\n\n강세 시나리오의 무효화는 BTC 기준선 이탈, 방어자산 강세, 공식 출처와 다른 루머 확인입니다.",
        },
    ]


def build_time_blocks(resources: list[dict], findings: list[dict]) -> list[dict]:
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
                "trader_read": f"{guide} 관련 태그는 {', '.join(top_topics(chunk, 3))}입니다. 여기서 확인할 것은 뉴스 수가 아니라 BTC가 그 뉴스를 가격으로 인정하는지입니다.",
            }
        )
    return blocks


def build_invalidation_points(market: dict, findings: list[dict]) -> list[str]:
    return [
        "BTC가 단기 기준선을 이탈하면 알트 강세 해석은 보류합니다.",
        "공식 발표가 기사 제목보다 약하거나 일정이 지연되면 이벤트 프리미엄을 낮춥니다.",
        "골드와 달러가 동시에 강해지면 크립토 호재도 단기 반등으로 제한될 수 있습니다.",
        "커뮤니티 화제성이 급등했는데 거래량이 따라오지 않으면 과열 신호로 처리합니다.",
        "선택 소스 간 주장 충돌이 있으면 가격 반응과 공식 문서 확인 전까지 중립으로 둡니다.",
    ]


def local_generate_brief(resources: list[dict], market_snapshot: dict, briefing_type: str, tone: str) -> dict:
    market_summary = summarize_market(market_snapshot)
    topics = top_topics(resources)
    findings = build_source_findings(resources)
    thesis = directional_thesis(market_summary, topics, findings)
    market = market_structure(market_summary, topics)
    scenarios = build_scenarios(market_summary, topics, findings)
    key_points = build_key_points(resources, market_summary, findings)
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
        "market_structure": market,
        "source_findings": findings,
        "key_points": key_points,
        "trader_sentences": [
            thesis,
            market["btc_axis"],
            market["alts"],
            market["defensive_assets"],
            "핵심은 예측이 아니라 조건입니다. BTC가 구조를 지키면 알트 뉴스는 로테이션으로 승격되고, BTC가 무너지면 같은 뉴스도 단기 노이즈로 내려갑니다.",
        ],
        "scenarios": scenarios,
        "invalidation_points": build_invalidation_points(market, findings),
        "action_plan": [
            "1차 필터: BTC 종가와 거래량으로 리스크 온/오프를 먼저 판별합니다.",
            "2차 필터: ETH/BTC와 주요 알트 거래대금으로 알트 로테이션 여부를 확인합니다.",
            "3차 필터: 일본/글로벌 기사에서 공식 발표, 거래소 공지, ETF/규제 일정을 분리합니다.",
            "콘텐츠화: 카드뉴스는 강세 단정이 아니라 '조건이 충족되면 무엇이 바뀌는가'를 중심으로 구성합니다.",
        ],
        "weekly_brief": build_weekly_sections(thesis, market, scenarios, findings),
        "daily_brief": build_time_blocks(resources, findings),
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
                "각 원문별 핵심 주장과 트레이더 해석을 분리하고, BTC 기준축과 알트 로테이션 조건을 명확히 쓴다."
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
                "market_structure": {
                    "regime": "string",
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
                        "trigger": "string",
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
        "시장 논지",
        "BTC 기준축",
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
    for index, heading in enumerate(headings, start=1):
        finding = findings[(index - 1) % len(findings)] if findings else {}
        scenario = scenarios[(index - 1) % len(scenarios)] if scenarios else {}
        if "원문 근거" in heading and finding:
            body = f"{finding.get('source')}의 원문은 {finding.get('role')}로 읽힙니다. 핵심은 {clean_text(finding.get('trader_read'), 140)}"
            caption = clean_text(" / ".join(finding.get("evidence", [])[:2]), 180)
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
    lines.append("## 1. 결론")
    for point in brief.get("key_points", []):
        lines.append(f"- {point}")
    lines.append("")
    lines.append("## 2. 원문별 해석")
    for item in brief.get("source_findings", []):
        lines.append(f"### {item.get('source')} - {item.get('title')}")
        lines.append(f"- 역할: {item.get('role')}")
        for evidence in item.get("evidence", []):
            lines.append(f"- 근거: {evidence}")
        lines.append(f"- 트레이더 해석: {item.get('trader_read')}")
        lines.append("")
    lines.append("## 3. 시장 구조")
    for key, value in (brief.get("market_structure") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## 4. 시나리오")
    for scenario in brief.get("scenarios", []):
        lines.append(f"### {scenario.get('case')}")
        lines.append(f"- 조건: {scenario.get('trigger')}")
        lines.append(f"- 경로: {scenario.get('expected_path')}")
        lines.append(f"- 체크: {scenario.get('watch')}")
    lines.append("")
    lines.append("## 5. 무효화 조건")
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
