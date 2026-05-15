from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

try:
    from localization_rules import localization_prompt
except Exception:
    def localization_prompt() -> str:
        return """
로컬라이징 원칙:
- 직역하지 말고 원문의 관계 맥락과 사회적 맥락을 자연스러운 한국어/영어로 옮긴다.
- 민감 주제는 단정하지 않는다. 성 정체성, 성적 지향, 사생활, 아웃팅 표현은 특히 정확하게 쓴다.
- '사생활이 터졌다', 'privacy exploded' 같은 어색한 표현 금지.
"""

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
        with urlopen(request, timeout=180) as response:
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
- 기본 진행은 존댓말이다. 감정이 튀거나 채팅을 받아칠 때 반말이 자연스럽게 튀어나온다.
- 반말과 존댓말이 교차한다. 예: 여러분들 이거 보세요 / 아니 잠깐만 / 야 이건 아니지 / 제가 보기엔요 / 저기요 그러지 마세요.
- 사주, 점성술, 궁합, 기운, 작두, 운의 흐름, 타이밍, 리듬, 별자리 같은 표현을 자연스럽게 쓴다.
- 단, 점쟁이처럼 단정하지 않는다. 방송식 추측과 관계 상담으로 풀어낸다.
- 사연자님에게 직접 조언하고, 채팅창 반응을 중간중간 받아친다.
- 리포트체, 상담센터 문어체, 목차형 요약체, 교과서식 결론 금지.
- 실제 유튜버 라이브처럼 말이 살짝 흘러가고, 중간에 자기정정과 감정 반응이 있어야 한다.
"""

STYLE_REFERENCE_BLOCK = """
말투 기준:
- 좋은 예: 아니 잠깐만. 이건 생일을 챙겼냐 안 챙겼냐 문제가 아니야. 사연자님이 그날 자기 기분을 자기가 수습하고 있었단 말이에요.
- 좋은 예: 여러분들 지금 채팅에 이혼하라 올라오는데, 얘들아 잠깐만. 사람 관계를 그렇게 시장가 매도하듯이 던지면 안 됩니다.
- 좋은 예: 제가 작두를 막 타자는 건 아닌데요. 이건 사주로 치면 비밀의 자리가 갑자기 밝은 데로 끌려 나온 느낌이에요.
- 좋은 예: 근데 또 남편이 악마다, 이렇게 박아버리면 상담이 안 돼요. 사연자님이 지금 해야 하는 건 처벌이 아니라 확인이에요.
- 나쁜 예: 안녕하세요 여러분 오늘은 많은 분들이 공감할 수 있는 사연입니다. 함께 고민해볼까요?
- 나쁜 예: 감정을 솔직하게 표현하는 것이 중요합니다. 깊은 대화를 나눠보세요.
- 나쁜 예: 별자리가 맞지 않을 수 있으니 고려해보세요.
- 나쁜 예: 사생활이 터졌다. 성 정체성이 드러났다. privacy exploded.
"""


def analyze_story(source_text: str, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 커뮤니티 사연을 유튜브 라이브 상담 콘텐츠로 개발하는 PD다.
원문을 복제하지 말고, 개인정보와 식별 요소를 일반화한다.
대본을 쓰지 말고 사연의 구조만 해부한다.

{localization_prompt()}

반드시 JSON만 반환한다."""
    schema = {
        "story_summary": "사연 핵심 요약. 번역투 없이 자연스러운 한국어",
        "localized_context": "원문 문화권/플랫폼 맥락을 한국 시청자가 이해할 수 있게 변환한 설명",
        "translation_notes": ["직역하면 어색하거나 위험한 표현과 권장 표현"],
        "sender_problem": "사연자가 진짜 상담받고 싶은 문제",
        "main_conflict": "핵심 갈등",
        "relationship_map": ["인물 관계"],
        "emotional_trigger": "감정이 터지는 지점",
        "hidden_pattern": "반복되는 관계 패턴",
        "chat_debate_points": ["채팅이 갈릴 포인트"],
        "astrology_lens": ["사주/점성술/기운으로 볼 수 있는 해석 포인트"],
        "practical_advice_angles": ["현실 조언 방향"],
        "risk_notes": ["재가공 유의점"],
    }
    user = {"title": row.get("title"), "source": row.get("source"), "url": row.get("url"), "source_text": clean_text(source_text, 14000), "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=3500)
    if error:
        return {}, error
    parsed, parse_error = extract_json_object(raw or "")
    return parsed or {}, parse_error


def build_live_blueprint(analysis: dict, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 라이브 사연 상담형 유튜브 대본의 구성 작가다.
{LIVE_NARRATOR_RULES}
{STYLE_REFERENCE_BLOCK}
{localization_prompt()}

10분 분량 대본을 위한 비트시트를 만든다. 아직 최종 대본은 쓰지 않는다.
각 비트에는 700자 이상으로 확장될 수 있는 장면/리액션/채팅/상담 내용을 구체적으로 설계한다.
반드시 JSON만 반환한다."""
    schema = {
        "opening_hook": "00:00에서 시작할 후킹. 번역투 금지. 사건의 논점부터 시작",
        "localization_strategy": "원문 표현을 어떤 한국어 맥락으로 바꿀지",
        "beats": [
            {"timecode": "00:00", "role": "라이브 오프닝", "purpose": "", "required_length_hint": "최종 대본 700자 이상", "tone_note": ""},
            {"timecode": "00:50", "role": "사연 읽기", "purpose": "", "required_length_hint": "최종 대본 800자 이상", "tone_note": ""},
            {"timecode": "01:50", "role": "첫 반말 리액션", "purpose": "", "required_length_hint": "최종 대본 700자 이상", "tone_note": ""},
            {"timecode": "02:50", "role": "채팅 반응 받아치기", "purpose": "", "required_length_hint": "최종 대본 650자 이상", "tone_note": ""},
            {"timecode": "03:50", "role": "사연 이어읽기", "purpose": "", "required_length_hint": "최종 대본 800자 이상", "tone_note": ""},
            {"timecode": "04:50", "role": "화자 감정 반응", "purpose": "", "required_length_hint": "최종 대본 700자 이상", "tone_note": ""},
            {"timecode": "05:50", "role": "사주/점성술/기운 렌즈", "purpose": "", "required_length_hint": "최종 대본 800자 이상", "tone_note": ""},
            {"timecode": "06:50", "role": "현실 조언 3단계", "purpose": "", "required_length_hint": "최종 대본 1000자 이상", "tone_note": ""},
            {"timecode": "08:10", "role": "채팅 의견 정리", "purpose": "", "required_length_hint": "최종 대본 600자 이상", "tone_note": ""},
            {"timecode": "09:00", "role": "최종 판단", "purpose": "", "required_length_hint": "최종 대본 650자 이상", "tone_note": ""},
            {"timecode": "09:40", "role": "댓글 유도", "purpose": "", "required_length_hint": "최종 대본 450자 이상", "tone_note": ""},
        ],
        "must_use_phrases": ["여러분들", "아니 잠깐만", "사연자님", "제가 보기엔요", "작두 살짝만 탈게요", "야 이건 좀", "저기요 그러지 마세요"],
        "advice_steps": ["해결 방법 1", "해결 방법 2", "해결 방법 3"],
        "forbidden_generic_phrases": ["함께 고민해보면 좋을 것 같아요", "그럼 시작해볼까요", "정말 다양한 시각이 있는 것 같아요", "사생활이 터졌다"],
    }
    user = {"title": row.get("title"), "analysis": analysis, "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=4500)
    if error:
        return {}, error
    parsed, parse_error = extract_json_object(raw or "")
    return parsed or {}, parse_error


def write_live_longform(source_text: str, analysis: dict, blueprint: dict, row: dict, model: str, temperature: float) -> tuple[str, Optional[str]]:
    system = f"""너는 실제 한국 라이브 유튜버 말투를 잘 쓰는 대본 작가이자 고급 로컬라이징 에디터다.
{LIVE_NARRATOR_RULES}
{STYLE_REFERENCE_BLOCK}
{localization_prompt()}

절대 조건:
- 10분 롱폼 내레이션 대본을 쓴다.
- 총 8,000자 이상, 가능하면 9,000~11,000자.
- 타임코드 10개 이상 포함.
- 각 타임코드마다 최소 600자 이상 실제 말로 작성한다. 제목/요약/목차만 쓰면 실패다.
- 오프닝은 흔한 인사 금지. 바로 사연의 이상한 지점으로 들어간다.
- "안녕하세요 여러분", "함께 고민해볼까요", "다양한 시각이 있네요", "정말 서운하셨겠어요" 같은 AI식 문장 금지.
- "사생활이 터졌다", "성 정체성이 드러났다"처럼 과격하거나 부정확한 번역투 금지. 맥락에 따라 "개인적인 일이 원치 않게 알려졌다", "아웃팅처럼 받아들여질 수 있었다", "사적인 부분이 사람들 입에 오르내리게 됐다"처럼 쓴다.
- 존댓말 진행 50%, 반말 리액션 30%, 채팅 받아치기 10%, 혼잣말/자기정정 10% 정도로 섞는다.
- "사연자님" 7회 이상, "여러분" 8회 이상, "채팅" 또는 "댓글" 반응 3회 이상, 현실 조언 3개 이상 포함한다.
- "아니 잠깐만", "야 이건", "근데", "제가 보기엔요", "저기요", "작두 살짝만", "사주로 치면", "기운", "궁합", "운의 흐름" 중 여러 개를 자연스럽게 사용한다.
- 사주/점성술 표현은 허용한다. 다만 무조건 악연, 100%, 운명 확정 같은 단정은 금지한다.
- 사연 원문은 읽어주는 느낌으로 재구성하되, 원문 문장을 그대로 복제하지 않는다.
- 반드시 해결 방법을 자세히 준다. '대화해보세요' 한 줄 금지. 어떤 문장으로 물어볼지, 상대 반응별로 어떻게 할지까지 말한다.
- 반환은 대본 텍스트만. JSON 금지.

출력 구조:
00:00부터 10:00까지 작성하되, 각 구간은 실제 방송 멘트로 길게 쓴다.
각 구간은 최소 4~7문단으로 쓴다. 짧은 문단과 긴 문단을 섞는다.
"""
    user = {
        "title": row.get("title"),
        "source_text_for_context_only": clean_text(source_text, 16000),
        "analysis": analysis,
        "blueprint": blueprint,
        "mission": "짧고 점잖은 상담 대본이 아니라, 진짜 라이브 유튜버가 사연 읽으며 채팅과 티키타카하고 사주/점성술 감각으로 풀이하는 10분짜리 장문 대본을 작성하라. 번역투를 없애고 현지화 수준을 최대로 끌어올려라.",
        "minimum_length_reminder": "8,000자 미만이면 실패다. 모든 타임코드를 충분히 확장하라.",
    }
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=12000)
    return raw or "", error


def generate_derivatives(longform_script: str, analysis: dict, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 롱폼 대본을 쇼츠, Threads, 카드뉴스로 재가공하는 콘텐츠 편집자이자 고급 로컬라이징 에디터다.
{LIVE_NARRATOR_RULES}
{STYLE_REFERENCE_BLOCK}
{localization_prompt()}
롱폼의 화자 말투와 로컬라이징 수준을 유지한다. 반드시 JSON만 반환한다."""
    schema = {
        "shorts": {"30s": "", "60s": "", "90s": ""},
        "threads": {"5_post": "", "10_post": ""},
        "card_news": {"8_cards": [{"title": "", "body": "", "image_prompt": "", "design_note": ""}]},
        "titles": [""],
        "thumbnail_text": [""],
        "comment_question": "",
    }
    user = {"title": row.get("title"), "analysis": analysis, "longform_script": clean_text(longform_script, 18000), "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=5500)
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
        "localized_context": analysis.get("localized_context", ""),
        "translation_notes": analysis.get("translation_notes", []),
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
