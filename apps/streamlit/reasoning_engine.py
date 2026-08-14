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


DISCLAIMER = "본 자료는 공개 데이터와 선택 리소스를 정리한 브리핑이며, 투자 권유나 매수/매도 지시가 아닙니다."


def clean_text(value: object, limit: int = 2400) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def as_percent(value: object) -> str:
    if value is None or value == "":
        return "N/A"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return str(value)


def source_line(row: dict, index: int) -> str:
    tags = row.get("tags") or "CRYPTO"
    return f"{index}. [{row.get('source')}] {row.get('title')} ({tags})"


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


def resource_digest(resources: list[dict]) -> list[dict]:
    digest: list[dict] = []
    for row in resources:
        digest.append(
            {
                "source": row.get("source", ""),
                "title": row.get("title", ""),
                "tags": row.get("tags", ""),
                "url": row.get("url", ""),
                "score": row.get("trader_score", 0),
                "excerpt": clean_text(row.get("material") or row.get("excerpt"), 360),
            }
        )
    return digest


def directional_sentence(market_summary: dict, topics: list[str]) -> str:
    bias = market_summary.get("bias")
    if bias == "risk_on":
        return "BTC가 시장의 위험자산 선호를 먼저 확인하고, 알트는 BTC가 지지선을 지킬 때 후행 확산되는 구조로 보는 편이 합리적입니다."
    if bias == "risk_off":
        return "BTC 반등보다 현금화와 방어자산 선호가 우선인 장세라, 알트 추격보다 변동성 축소 확인이 먼저입니다."
    if "REG" in topics or "ETF" in topics:
        return "가격보다 규제/ETF/기관 플로우가 방향을 정하는 구간이라, 뉴스 확인 전 포지션 확대는 기대값이 낮습니다."
    return "단일 방향 추세보다 BTC, 니케이, 골드 흐름을 같이 확인하며 구간 대응하는 혼조 장세로 보는 것이 낫습니다."


def build_key_points(resources: list[dict], market_summary: dict) -> list[str]:
    topics = top_topics(resources)
    counts = topic_counts(resources)
    points = [
        f"선택 리소스 {len(resources)}건의 핵심 태그는 {', '.join(topics)}입니다.",
        f"시장 종합 판정은 '{market_summary.get('label')}'이며 내부 점수는 {market_summary.get('risk_points')}입니다.",
        f"BTC 7일 변화율은 {as_percent(market_summary.get('btc_7d'))}, ETH 7일 변화율은 {as_percent(market_summary.get('eth_7d'))}입니다.",
        f"니케이 7일 변화율은 {as_percent(market_summary.get('nikkei_7d'))}, 골드 7일 변화율은 {as_percent(market_summary.get('gold_7d'))}입니다.",
    ]
    if counts.get("REG") or counts.get("ETF"):
        points.append("규제/ETF 재료가 섞여 있어 가격 차트만 보는 접근보다 발표 시점과 공식 출처 확인이 중요합니다.")
    if counts.get("STABLE") or counts.get("WEB3"):
        points.append("스테이블코인/Web3 재료는 즉시 가격보다 일본 내 제도권 채택과 거래소 상장 가능성 관점에서 봐야 합니다.")
    if counts.get("SECURITY"):
        points.append("보안/해킹 이슈는 단기 유동성 위축과 특정 토큰 회피 심리를 만들 수 있어 리스크 문구가 필요합니다.")
    return points[:7]


def build_time_blocks(resources: list[dict]) -> list[dict]:
    sorted_rows = sorted(resources, key=lambda row: row.get("posted_at") or "", reverse=True)
    if not sorted_rows:
        return []
    labels = ["아시아 장 전후", "유럽 장 진입", "미국 장 전후", "익일 체크"]
    blocks: list[dict] = []
    for index, label in enumerate(labels):
        chunk = sorted_rows[index:: len(labels)]
        if not chunk:
            continue
        blocks.append(
            {
                "time_zone": label,
                "watch": [clean_text(row.get("title"), 160) for row in chunk[:4]],
                "trader_read": f"{label}에는 {', '.join(top_topics(chunk, 3))} 관련 헤드라인 반응을 우선 확인합니다.",
            }
        )
    return blocks


def local_generate_brief(resources: list[dict], market_snapshot: dict, briefing_type: str, tone: str) -> dict:
    market_summary = summarize_market(market_snapshot)
    topics = top_topics(resources)
    direction = directional_sentence(market_summary, topics)
    key_points = build_key_points(resources, market_summary)
    source_lines = [source_line(row, index) for index, row in enumerate(resources[:12], start=1)]
    today = datetime.now().strftime("%Y-%m-%d")
    title_prefix = "주간 방향 브리핑" if briefing_type == "weekly" else "일간 시간대 브리핑"

    weekly_sections = [
        {
            "heading": "이번 주 방향",
            "body": direction,
        },
        {
            "heading": "자산 이동",
            "body": (
                f"BTC {as_percent(market_summary.get('btc_7d'))}, 니케이 {as_percent(market_summary.get('nikkei_7d'))}, "
                f"골드 {as_percent(market_summary.get('gold_7d'))}를 함께 보면 현재 판정은 {market_summary.get('label')}입니다."
            ),
        },
        {
            "heading": "알트 대응",
            "body": "알트는 BTC가 먼저 방향을 확인한 뒤 거래량이 붙는 섹터만 선별하는 접근이 유리합니다.",
        },
        {
            "heading": "리스크",
            "body": "공식 발표, 거래소 공지, ETF/규제 일정이 확인되기 전에는 헤드라인 추격을 낮춰야 합니다.",
        },
    ]
    daily_blocks = build_time_blocks(resources)

    return {
        "provider": "무료 로컬 추론 엔진",
        "briefing_type": briefing_type,
        "tone": tone,
        "generated_at": today,
        "title": f"{today} {title_prefix}",
        "one_line": direction,
        "market_summary": market_summary,
        "key_points": key_points,
        "trader_sentences": [
            direction,
            "BTC는 리스크 온/오프를 판별하는 기준축, 니케이는 아시아 위험자산 심리, 골드는 방어 수요의 강도를 보는 보조축입니다.",
            "알트는 독립 상승보다 BTC 안정과 유동성 회복이 확인될 때 카드뉴스 소재로 전환하는 편이 낫습니다.",
            "커뮤니티 반응은 방향 예측보다 과열/공포의 강도를 읽는 보조 데이터로만 사용합니다.",
        ],
        "weekly_brief": weekly_sections,
        "daily_brief": daily_blocks,
        "source_digest": resource_digest(resources),
        "source_lines": source_lines,
        "risk_notes": [
            DISCLAIMER,
            "커뮤니티 자료는 사실 확인 전 루머로 취급합니다.",
            "가격 예측 대신 조건부 시나리오와 체크포인트 중심으로 표현합니다.",
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


def post_json(url: str, payload: dict, headers: dict, timeout: int = 180) -> tuple[Optional[dict], Optional[str]]:
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
            {"role": "system", "content": "당신은 한국어로 쓰는 크립토 시장 브리핑 애널리스트입니다. 내부 추론 후 결론과 근거만 JSON으로 출력합니다."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(config.get("temperature", 0.45)),
        "max_tokens": int(config.get("max_tokens", 5000)),
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
            {"role": "system", "content": "한국어 크립토 시장 브리핑 애널리스트로서 결과를 JSON만 출력합니다."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": float(config.get("temperature", 0.35))},
    }
    result, error = post_json(f"{base_url}/api/chat", payload, {"Content-Type": "application/json"})
    if error or not result:
        return None, error or "응답이 비어 있습니다."
    try:
        return result["message"]["content"], None
    except Exception as parse_error:
        return None, str(parse_error)


def brief_prompt(resources: list[dict], market_snapshot: dict, briefing_type: str, tone: str) -> str:
    return json.dumps(
        {
            "mission": "선택된 다중 리소스와 시장 데이터를 합쳐 트레이더 관점의 한국어 브리핑을 작성한다. 투자 권유가 아니라 조건부 판단과 체크포인트로 쓴다.",
            "briefing_type": briefing_type,
            "tone": tone,
            "market_snapshot": market_snapshot,
            "resources": resource_digest(resources),
            "required_schema": {
                "title": "string",
                "one_line": "string",
                "market_summary": "object",
                "key_points": ["string"],
                "trader_sentences": ["string"],
                "weekly_brief": [{"heading": "string", "body": "string"}],
                "daily_brief": [{"time_zone": "string", "watch": ["string"], "trader_read": "string"}],
                "source_digest": [{"source": "string", "title": "string", "url": "string", "excerpt": "string"}],
                "risk_notes": ["string"],
            },
        },
        ensure_ascii=False,
    )


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
        local["_provider_warning"] = f"외부 추론 실패로 로컬 추론을 사용했습니다: {error}"
        return local, None
    parsed, parse_error = extract_json_object(raw)
    if parse_error or not parsed:
        local["_provider_warning"] = f"외부 추론 JSON 파싱 실패로 로컬 추론을 사용했습니다: {parse_error}"
        return local, None
    parsed.setdefault("provider", provider)
    parsed.setdefault("source_digest", local["source_digest"])
    parsed.setdefault("risk_notes", local["risk_notes"])
    return parsed, None


def card_blueprint(count: int) -> list[str]:
    base = [
        "오늘의 시장 한 줄",
        "BTC 기준축",
        "니케이/골드/달러 맥락",
        "알트와 섹터 반응",
        "트레이더 체크포인트",
        "리스크와 확인할 출처",
        "내일 볼 가격/뉴스 조건",
        "콘텐츠 후킹 문장",
    ]
    return base[:count]


def make_card_set(brief: dict, resources: list[dict], count: int, label: str) -> list[dict]:
    key_points = brief.get("key_points") or []
    trader_sentences = brief.get("trader_sentences") or []
    headings = card_blueprint(count)
    cards: list[dict] = []
    for index, heading in enumerate(headings, start=1):
        point = key_points[(index - 1) % len(key_points)] if key_points else brief.get("one_line", "")
        sentence = trader_sentences[(index - 1) % len(trader_sentences)] if trader_sentences else brief.get("one_line", "")
        source = resources[(index - 1) % len(resources)] if resources else {}
        cards.append(
            {
                "set": label,
                "slide": index,
                "headline": heading,
                "body": clean_text(point if index % 2 else sentence, 160),
                "visual_direction": "BTC 캔들, 니케이 라인, 골드 아이콘, 뉴스 헤드라인을 한 화면에 배치",
                "source_hint": f"{source.get('source', '')} / {source.get('title', '')}"[:180],
                "caption": clean_text(sentence, 180),
            }
        )
    return cards


def build_note_markdown(brief: dict, resources: list[dict]) -> str:
    lines = [f"# {brief.get('title', 'Crypto Trader Briefing')}", "", brief.get("one_line", ""), ""]
    lines.append("## 핵심 요약")
    for point in brief.get("key_points", []):
        lines.append(f"- {point}")
    lines.append("")
    lines.append("## 트레이더 관점")
    for sentence in brief.get("trader_sentences", []):
        lines.append(f"- {sentence}")
    lines.append("")
    lines.append("## 참고 리소스")
    for row in resources[:12]:
        lines.append(f"- [{row.get('source')}] {row.get('title')} - {row.get('url')}")
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    return "\n".join(lines)


def generate_content_package(brief: dict, resources: list[dict], custom_count: int = 8) -> dict:
    suggested = max(5, min(9, custom_count or (7 if len(resources) >= 7 else 6)))
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
            "x_thread": brief.get("trader_sentences", [])[:5],
            "thumbnail": brief.get("one_line", ""),
            "comment_question": "이번 주 BTC 방향은 니케이와 골드 중 어느 쪽 신호를 더 따라갈까요?",
        },
    }
