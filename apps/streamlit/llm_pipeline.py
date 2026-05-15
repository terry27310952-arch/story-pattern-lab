from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    value = os.environ.get(name)
    return value if value else default


def clean_text(value: str | None, limit: int = 16000) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    return text[:limit]


def openai_chat(messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> tuple[Optional[str], Optional[str]]:
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY가 설정되어 있지 않습니다."
    base_url = (get_secret("OPENAI_API_BASE", DEFAULT_OPENAI_BASE_URL) or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    try:
        with urlopen(request, timeout=150) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"], None
    except HTTPError as error:
        try:
            body = error.read().decode("utf-8")
        except Exception:
            body = str(error)
        return None, f"OpenAI HTTP 오류: {error.code} / {body[:1200]}"
    except URLError as error:
        return None, f"OpenAI 네트워크 오류: {error}"
    except Exception as error:
        return None, f"OpenAI 호출 오류: {error}"


def extract_json_object(text: str) -> tuple[Optional[dict], Optional[str]]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned), None
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0)), None
        except Exception as error:
            return None, f"JSON 파싱 실패: {error}"
    return None, "JSON 객체를 찾지 못했습니다."


LIVE_NARRATOR_RULES = """
화자 설정:
- 라이브 사연 상담형 1인칭 여성 유튜버.
- 기본 진행은 존댓말. 감정이 튀거나 채팅을 받아칠 때 반말이 자연스럽게 튀어나온다.
- 반말과 존댓말이 교차한다. 예: 여러분들 이거 보세요 / 아니 잠깐만 / 야 이건 아니지 / 제가 보기엔요.
- 사주, 점성술, 궁합, 기운, 작두, 운의 흐름, 타이밍, 리듬, 별자리 같은 표현을 자연스럽게 쓴다.
- 단, 점쟁이처럼 단정하지 않는다. 방송식 추측과 관계 상담으로 풀어낸다.
- 사연자님에게 직접 조언하고, 채팅창 반응을 중간중간 받아친다.
- 리포트체, 상담센터 문어체, 목차형 요약체 금지.
- 실제 유튜버 라이브처럼 말이 살짝 흘러가고, 중간에 자기정정과 감정 반응이 있어야 한다.
"""


def analyze_story(source_text: str, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = """너는 커뮤니티 사연을 유튜브 라이브 상담 콘텐츠로 개발하는 PD다.
원문을 복제하지 말고, 개인정보와 식별 요소를 일반화한다.
대본을 쓰지 말고 사연의 구조만 해부한다. 반드시 JSON만 반환한다."""
    schema = {
        "story_summary": "사연 핵심 요약",
        "sender_problem": "사연자가 진짜 상담받고 싶은 문제",
        "main_conflict": "핵심 갈등",
        "relationship_map": ["인물 관계"],
        "emotional_trigger": "감정이 터지는 지점",
        "hidden_pattern": "반복되는 관계 패턴",
        "chat_debate_points": ["채팅이 갈릴 포인트"],
        "astrology_lens": ["사주/점성술/기운으로 볼 수 있는 해석 포인트"],
        "practical_advice_angles": ["현실 조언 방향"],
        "risk_notes": ["재가공 유의점"]
    }
    user = {"title": row.get("title"), "source": row.get("source"), "url": row.get("url"), "source_text": clean_text(source_text, 14000), "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=2500)
    if error:
        return {}, error
    parsed, parse_error = extract_json_object(raw or "")
    return parsed or {}, parse_error


def build_live_blueprint(analysis: dict, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 라이브 사연 상담형 유튜브 대본의 구성 작가다.
{LIVE_NARRATOR_RULES}
10분 분량 대본을 위한 비트시트를 만든다. 아직 최종 대본은 쓰지 않는다. 반드시 JSON만 반환한다."""
    schema = {
        "opening_hook": "00:00에서 시작할 후킹",
        "beats": [
            {"timecode": "00:00", "role": "라이브 오프닝", "purpose": "", "tone_note": ""},
            {"timecode": "00:40", "role": "사연 읽기", "purpose": "", "tone_note": ""},
            {"timecode": "01:40", "role": "첫 리액션", "purpose": "", "tone_note": ""},
            {"timecode": "02:30", "role": "채팅 반응", "purpose": "", "tone_note": ""},
            {"timecode": "03:30", "role": "사연 이어읽기", "purpose": "", "tone_note": ""},
            {"timecode": "04:30", "role": "감정 반응", "purpose": "", "tone_note": ""},
            {"timecode": "05:30", "role": "사주/점성술 렌즈", "purpose": "", "tone_note": ""},
            {"timecode": "06:30", "role": "현실 조언", "purpose": "", "tone_note": ""},
            {"timecode": "07:40", "role": "채팅 의견 정리", "purpose": "", "tone_note": ""},
            {"timecode": "08:40", "role": "최종 판단", "purpose": "", "tone_note": ""},
            {"timecode": "09:30", "role": "댓글 유도", "purpose": "", "tone_note": ""}
        ],
        "must_use_phrases": ["여러분들", "아니 잠깐만", "사연자님", "제가 보기엔요", "작두 살짝만 탈게요"],
        "advice_steps": ["해결 방법 1", "해결 방법 2", "해결 방법 3"]
    }
    user = {"title": row.get("title"), "analysis": analysis, "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=3000)
    if error:
        return {}, error
    parsed, parse_error = extract_json_object(raw or "")
    return parsed or {}, parse_error


def write_live_longform(source_text: str, analysis: dict, blueprint: dict, row: dict, model: str, temperature: float) -> tuple[str, Optional[str]]:
    system = f"""너는 실제 라이브 유튜버 말투를 잘 쓰는 대본 작가다.
{LIVE_NARRATOR_RULES}

작성 규칙:
- 10분 롱폼 내레이션 대본을 쓴다.
- 최소 5,500자 이상.
- 타임코드 8개 이상 포함.
- 각 타임코드는 제목이 아니라 실제 말로 길게 작성한다.
- 존댓말 진행 55%, 반말 리액션 25%, 채팅 받아치기 10%, 혼잣말/자기정정 10% 정도로 섞는다.
- "사연자님" 5회 이상, "여러분" 5회 이상, 채팅 반응 2회 이상, 현실 조언 3개 이상 포함.
- 사주/점성술/궁합/기운/작두/운의 흐름 표현을 3~8회 정도 자연스럽게 사용한다.
- 단정적 점술 금지. 무조건 악연, 100% 운명 같은 표현 금지.
- 원문을 그대로 베끼지 말고, 사연 내용은 비식별화해서 재구성한다.
- 반환은 대본 텍스트만. JSON 금지."""
    user = {
        "title": row.get("title"),
        "source_text_for_context_only": clean_text(source_text, 14000),
        "analysis": analysis,
        "blueprint": blueprint,
        "style_reference_summary": "반말과 존댓말이 교차하는 라이브 유튜버. 채팅을 받아치고, 감정이 튀면 반말, 상담 정리는 존댓말. 사주/작두/기운 표현을 방송식으로 사용.",
    }
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=7500)
    return raw or "", error


def generate_derivatives(longform_script: str, analysis: dict, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 롱폼 대본을 쇼츠, Threads, 카드뉴스로 재가공하는 콘텐츠 편집자다.
{LIVE_NARRATOR_RULES}
롱폼의 화자 말투를 유지한다. 반드시 JSON만 반환한다."""
    schema = {
        "shorts": {"30s": "", "60s": "", "90s": ""},
        "threads": {"5_post": "", "10_post": ""},
        "card_news": {"8_cards": [{"title": "", "body": "", "image_prompt": "", "design_note": ""}]},
        "titles": [""],
        "thumbnail_text": [""],
        "comment_question": ""
    }
    user = {"title": row.get("title"), "analysis": analysis, "longform_script": clean_text(longform_script, 16000), "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=4500)
    if error:
        return {}, error
    parsed, parse_error = extract_json_object(raw or "")
    return parsed or {}, parse_error


def build_package(row: dict, source_text: str, analysis: dict, blueprint: dict, longform_script: str, quality: dict, derivatives: dict) -> dict:
    return {
        "source": "openai_live_advice_pipeline",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "source_text_meta": {
            "body_fetched": bool(source_text),
            "body_length": len(source_text or ""),
            "body_saved": False,
        },
        "overview_ko": analysis.get("story_summary", ""),
        "analysis": analysis,
        "live_blueprint": blueprint,
        "longform_script": longform_script,
        "quality_check": quality,
        "shorts": derivatives.get("shorts", {}),
        "threads": derivatives.get("threads", {}),
        "card_news": derivatives.get("card_news", {}),
        "titles": derivatives.get("titles", []),
        "thumbnail_text": derivatives.get("thumbnail_text", []),
        "comment_question": derivatives.get("comment_question", ""),
    }
