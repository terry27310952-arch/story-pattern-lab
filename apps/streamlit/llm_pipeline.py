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
DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_OPENAI_REASONING_EFFORT = "medium"

GENERIC_JSON_PLACEHOLDERS = [
    "required_schema",
    "해결 방법 1",
    "해결 방법 2",
    "해결 방법 3",
    "최종 대본",
    "사건의 배경과 핵심 문제",
    "상황을 더 깊이 파악",
    "다양한 의견을 정리",
    "최종 의견을 제시",
    "적극적인 참여를 유도",
    "진지하면서도 친근한 톤",
    "감정을 담아 전달",
    "원문 표현을 그대로 쓰지 않고",
    "시청자들이 댓글로 자신의 의견",
    "핵심 문제에 대한 간단한 도입",
]


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


def post_chat_completion(endpoint: str, api_key: str, payload: dict) -> tuple[Optional[str], Optional[str]]:
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    try:
        with urlopen(request, timeout=300) as response:
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


def error_is_for_param(error: str, param: str) -> bool:
    return (
        f"Unsupported parameter: '{param}'" in error
        or f'"param": "{param}"' in error
        or f'"param":"{param}"' in error
    )


def openai_chat(messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int, json_mode: bool = False) -> tuple[Optional[str], Optional[str]]:
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY가 설정되어 있지 않습니다."
    base_url = (get_secret("OPENAI_API_BASE", DEFAULT_OPENAI_BASE_URL) or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_completion_tokens": max_tokens}
    effort = get_secret("OPENAI_REASONING_EFFORT", DEFAULT_OPENAI_REASONING_EFFORT)
    if effort:
        payload["reasoning_effort"] = effort
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    content, error = post_chat_completion(endpoint, api_key, payload)
    if not error:
        return content, None

    retry_payload = dict(payload)
    if "max_tokens" in retry_payload and error_is_for_param(error, "max_tokens"):
        retry_payload["max_completion_tokens"] = retry_payload.pop("max_tokens")
        content, retry_error = post_chat_completion(endpoint, api_key, retry_payload)
        if not retry_error:
            return content, None
        error = retry_error
    if "max_completion_tokens" in retry_payload and error_is_for_param(error, "max_completion_tokens"):
        retry_payload["max_tokens"] = retry_payload.pop("max_completion_tokens")
        content, retry_error = post_chat_completion(endpoint, api_key, retry_payload)
        if not retry_error:
            return content, None
        error = retry_error
    if "reasoning_effort" in retry_payload and "reasoning_effort" in error:
        retry_payload.pop("reasoning_effort", None)
        content, retry_error = post_chat_completion(endpoint, api_key, retry_payload)
        if not retry_error:
            return content, None
        error = retry_error
    if "temperature" in retry_payload and "temperature" in error:
        retry_payload.pop("temperature", None)
        content, retry_error = post_chat_completion(endpoint, api_key, retry_payload)
        if not retry_error:
            return content, None
        error = retry_error
    if "response_format" in retry_payload and ("response_format" in error or "json_object" in error):
        retry_payload.pop("response_format", None)
        content, retry_error = post_chat_completion(endpoint, api_key, retry_payload)
        if not retry_error:
            return content, None
        error = retry_error
    return None, error


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


def flatten_json_text(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def find_structural_json_issues(parsed: dict | None, stage: str) -> list[str]:
    if not parsed:
        return ["JSON이 비어 있습니다."]
    issues: list[str] = []
    text = flatten_json_text(parsed)
    if "required_schema" in parsed:
        issues.append("required_schema를 결과에 그대로 포함했습니다.")
    placeholder_hits = [phrase for phrase in GENERIC_JSON_PLACEHOLDERS if phrase in text]
    if len(placeholder_hits) >= 2:
        issues.append("스키마 설명문이나 자리표시자 문장이 결과에 섞였습니다.")
    if stage == "story_analysis":
        summary = str(parsed.get("story_summary", ""))
        premise = str(parsed.get("one_line_viral_premise", ""))
        if len(summary) < 35 or len(premise) < 35:
            issues.append("사연 해부의 핵심 요약/바이럴 전제가 너무 얕습니다.")
        if not parsed.get("viral_angle_bank") and not parsed.get("audience_camps"):
            issues.append("시청자가 갈릴 바이럴 각도와 댓글 진영이 부족합니다.")
        if not parsed.get("counseling_targets"):
            issues.append("실제 상담 문장과 상대 반응별 대응이 부족합니다.")
    if stage == "live_blueprint":
        beats = parsed.get("beats")
        if not isinstance(beats, list) or len(beats) < 10:
            issues.append("비트시트 타임코드가 부족합니다.")
        else:
            weak_beats = 0
            for beat in beats:
                beat_text = flatten_json_text(beat)
                if len(beat_text) < 260 or beat_text.count("문장") + beat_text.count("구체") + beat_text.count("채움") >= 3:
                    weak_beats += 1
            if weak_beats >= 3:
                issues.append("비트시트가 실제 연출 설계가 아니라 빈 설명문에 가깝습니다.")
    return issues


def repair_json_if_needed(
    stage: str,
    parsed: dict,
    raw: str,
    context: dict,
    model: str,
    temperature: float,
    max_tokens: int,
) -> tuple[dict, Optional[str]]:
    issues = find_structural_json_issues(parsed, stage)
    if not issues:
        return parsed, None

    system = f"""너는 유튜브 라이브 상담 콘텐츠의 수석 PD다.
앞선 JSON이 너무 얕거나 required_schema를 그대로 따라 했다. 같은 키 구조를 최대한 유지하되, 빈 양식이 아니라 방송 작가가 바로 쓸 수 있는 완성된 PD 노트로 수리한다.

{STORY_BRAIN_ENGINE}
{STRUCTURAL_OUTPUT_GUARD}
{STYLE_REFERENCE_BLOCK}

반드시 JSON만 반환한다."""
    user = {
        "stage": stage,
        "repair_issues": issues,
        "story_context": context,
        "bad_output": parsed or raw,
        "repair_mission": "자리표시자와 일반론을 제거하고, 이 사연만의 돈/권력/수치심/관계 리듬/댓글 갈등/상담 문장으로 다시 채워라.",
    }
    repaired_raw, repair_error = openai_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        model=model,
        temperature=max(0.45, min(temperature, 0.75)),
        max_tokens=max_tokens,
        json_mode=True,
    )
    if repair_error:
        parsed["_quality_warning"] = f"구조화 JSON 수리 실패: {repair_error}"
        parsed["_quality_issues"] = issues
        return parsed, None
    repaired, parse_error = extract_json_object(repaired_raw or "")
    if parse_error or not repaired:
        parsed["_quality_warning"] = f"구조화 JSON 수리 결과 파싱 실패: {parse_error}"
        parsed["_quality_issues"] = issues
        return parsed, None
    repaired_issues = find_structural_json_issues(repaired, stage)
    if len(repaired_issues) < len(issues):
        return repaired, None
    repaired["_quality_warning"] = "구조화 JSON이 아직 얕을 수 있습니다."
    repaired["_quality_issues"] = repaired_issues
    return repaired, None


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

PERSONA_EMBODIMENT_ENGINE = """
페르소나 체화 엔진:
- 추론된 화자는 한국 국적의 30대 초중반~후반 여성 라이브 유튜버다. 20대 초반처럼 가볍지 않고, 50대 역술인처럼 권위적이지 않다.
- 시청자에게는 "언니/누나 같은데 말은 꽤 날카로운 사람"으로 느껴져야 한다. 사연자에게는 존중을 주고, 채팅에는 더 빠르게 반응한다.
- 직업 정체성은 점쟁이가 아니라 사주/점성술을 관계 패턴을 읽는 은유로 쓰는 상담형 방송 진행자다. 운명 확정, 저주, 악연 단정은 금지한다.
- 국적성과 플랫폼 감각은 한국 유튜브 라이브다. 해외 커뮤니티 사연도 한국 시청자가 바로 이해할 말투, 관계 감각, 댓글 싸움으로 현지화한다.
- 성별과 연령은 말투에 반영된다. 훈계형 아저씨, 뉴스 앵커, 상담센터 직원, 무속인, 10대 틱톡커 톤으로 흐르면 실패다.
- 말의 리듬은 존댓말 뼈대, 반말 리액션, 채팅 받아치기, 자기정정이 섞인다. "아니 잠깐만"은 장식이 아니라 판단이 흔들리는 순간에만 쓴다.
- 화자는 사연자를 대신해 분노할 수 있지만 사람을 조롱하지 않는다. 특히 정체성, 사생활, 아웃팅, 차별, 폭력, 임신, 장애 이슈는 행동/맥락/동의/공개 범위로 분리한다.
- 매 구간에서 화자는 세 가지를 동시에 해야 한다: 장면을 눈앞에 보이게 재구성하기, 채팅의 반대 의견을 받아 판단을 보정하기, 사연자에게 실제로 말할 문장을 주기.
"""

EMBODIED_INSIGHT_ENGINE = """
체화형 개인 경험 + 은근한 성향 인사이트 엔진:
- 대본은 사연 요약으로 시작하지 않는다. 화자가 비슷한 공기를 겪은 개인적 하루, 몸에 남은 감각, 반복해서 보인 상징으로 먼저 들어간다.
- 개인 경험은 과시용 일기가 아니라 사연을 이해시키는 감각의 다리다. 예: 빨간불, 멈춘 엘리베이터, 배터리 경고, 어긋난 메시지처럼 작은 신호가 반복되다가 관계 해석으로 확장되는 구조.
- 화자의 경험은 현실감 있게 창작할 수 있지만, 외부 사건·역사·통계·실명 사실은 원문에 있거나 사용자가 준 경우에만 구체적으로 말한다. 모르면 "기록을 보면" 식으로 꾸미지 않는다.
- 상징은 최소 3번 변주한다. 처음엔 일상의 감각, 중간엔 관계의 패턴, 후반엔 사주/점성술식 해석으로 의미가 바뀌어야 한다.
- MBTI, 사주 궁합, 오행, 일간, 대운/세운은 대놓고 판정하지 않는다. "이 사람은 ENFP다"가 아니라 "MBTI식으로 보면 감정 확인이 먼저인 쪽과 맥락 확인이 먼저인 쪽이 부딪힌 느낌"처럼 은근히 말한다.
- 생년월일이나 확정 정보가 없으면 사주를 단정하지 않는다. "일간을 모르는 상태에서 확정은 못 하지만", "궁합으로 치면 속도와 온도가 안 맞는 그림"처럼 가능성의 언어로 쓴다.
- 내담자 인사이트는 상담에 붙어야 한다. 성향을 말한 뒤 바로 "그래서 이 사람에게는 이렇게 물어봐야 한다"는 실제 문장으로 연결한다.
- 좋은 흐름: 개인 경험의 감각 -> 사연의 장면 -> 성향/궁합의 은근한 해석 -> 채팅 반론 -> 실제 상담 문장 -> 사회적 패턴 확장.
- 실패 흐름: "당신의 MBTI는", "이 궁합은 무조건", "올해는 반드시", "제 경험상 모든 사람은"처럼 딱지 붙이거나 예언처럼 말하는 것.
"""

VIRAL_RETENTION_ENGINE = """
100만 뷰급 후킹/리텐션 엔진:
- 첫 5초는 결과나 논쟁부터 보여준다. 배경 설명, 인사, 사연 제목 낭독은 뒤로 뺀다. 첫 문장은 "무슨 일이 있었는지"보다 "왜 이걸 끝까지 봐야 하는지"를 만든다.
- 첫 30초 안에는 시청자에게 계약을 건다: 오늘 끝까지 보면 무엇을 판단하게 되는지, 어떤 반전이 남아 있는지, 어떤 현실 조언을 가져갈 수 있는지 분명히 약속한다.
- 45~60초마다 리훅을 넣는다. 리훅은 새 정보, 반대 해석, 채팅 충돌, 사주/점성술 패턴, 개인 경험의 회수, 실제 상담 문장 중 하나여야 한다.
- 오픈루프를 최소 3개 연다. 예: "근데 진짜 문제는 이 다음이에요", "이 말이 왜 위험한지는 뒤에서 바로 나와요", "아까 그 빨간불 얘기가 여기서 다시 연결됩니다."
- 열어둔 루프는 반드시 회수한다. 회수 문장은 "아까 제가 말한 빨간불이 이거예요", "초반에 찝찝했던 지점이 여기서 풀립니다"처럼 시청자가 따라온 보상을 느끼게 한다.
- 패턴 인터럽트를 자주 넣는다. 4~5문장 이상 같은 톤으로 설명하지 말고, "아니 근데 잠깐만", "반대로 보면요", "여기서 채팅 갈릴 거 알아요"처럼 리듬을 꺾는다.
- 100만 뷰급 팟캐스트/라이브의 공통 장치는 큰 자극이 아니라 명확한 긴장이다: 개인적 공감, 이해관계 충돌, 책임 소재, 숨은 반전, 말 한마디의 대가, 댓글에서 싸울 질문.
- 각 타임코드는 작은 에피소드처럼 움직인다: 마이크로 후킹 -> 새 정보 -> 판단 흔들기 -> 상담/해석 가치 -> 다음 구간 궁금증.
- 결말 직전에는 댓글을 부르는 마지막 갈림 질문을 남긴다. 단순 정답 발표가 아니라 "여기서 여러분은 어디까지가 선이라고 보세요?"처럼 참여 욕구를 남긴다.
"""

INTIMACY_BOUNDARY_ENGINE = """
친밀관계/프라이버시 민감 사연 처리 엔진:
- 성관계, 몸 노출, 기기 착용, 촬영·녹화 가능성, 사생활이 얽힌 사연은 자극적 묘사보다 동의·경계·프라이버시·중단 기준이 중심이다.
- "성관계 중에 쫓아냈다"처럼 사건을 선정적으로 요약하지 않는다. "친밀한 상황에서 기기 착용과 공개/기록 가능성 때문에 경계가 무너진 사연"처럼 구조로 말한다.
- 핵심 질문은 "누가 예민한가"가 아니라 "기기 사용에 대해 충분히 설명하고 동의를 받았나", "촬영/저장/공유 가능성을 확인했나", "불편하다고 느낀 순간 멈출 수 있었나"다.
- 사연자가 10대 후반/어린 성인으로 나오면 더 조심한다. 미성숙함을 조롱하거나 성적 디테일을 반복하지 말고, 안전감과 동의의 언어를 준다.
- 실제 상담 문장은 구체적이어야 한다. 예: "그 안경이 촬영이나 저장을 하는 상태였는지 지금 확인하고 싶어. 동의 없이 기록된 게 있다면 바로 삭제해줘."
- 상대가 "그런 의도 아니었다"고 말할 때의 대응도 준다. 예: "의도보다 중요한 건 내가 그 순간 동의하지 않은 기기를 몸 가까이에 두었다는 점이야."
- 채팅 유도는 응원 구걸이 아니라 경계 질문이어야 한다. 예: "여러분은 친밀한 상황에서 스마트 기기 착용, 어디까지 사전 설명이 필요하다고 보세요?"
- 금지: 몸 평가, 성적 취향 훈수, 불 켜보기 같은 노출 적응 조언, "관계를 더 깊게" 같은 미화, "대화가 중요해요"로 끝내기.
"""

STORY_BRAIN_ENGINE = """
사연 해부/라이브 설계 브레인:
- 해부의 목표는 요약이 아니라 "왜 사람들이 이 사연을 끝까지 듣고 싸우는지"를 찾아내는 것이다.
- 모든 사연은 표면 사건, 숨은 욕망, 권력/돈/수치심/가족/몸/비밀 중 어떤 축에서 터졌는지 분리한다.
- "남자친구가 울었다", "돈을 보여줬다"처럼 사건명만 말하지 않는다. 예: 돈이 숫자가 아니라 자존심, 생존감, 역할 기대, 관계 권력의 증거로 바뀐 순간.
- 댓글이 갈리는 두 진영을 만든다. 한쪽은 감정적으로 왜 끌리는지, 반대쪽은 왜 반박하는지까지 쓴다.
- 방송 구조는 매 구간 판단이 움직여야 한다. 00:00의 판단, 03:00의 흔들림, 06:00의 재해석, 09:00의 상담 결론이 서로 달라야 한다.
- 상담 설계는 "대화해보세요"가 아니라 확인 질문, 상대 반응별 다음 문장, 멈춰야 할 기준, 관계를 계속할 조건을 준다.
- 사주/점성술/MBTI 렌즈는 장식이 아니다. 감정 처리 속도, 돈의 온도, 비밀의 자리, 사회적 얼굴, 자존심의 화기처럼 사건의 구조를 읽는 비유로 쓴다.
- 좋은 분석은 PD, 작가, 진행자가 바로 쓸 수 있어야 한다. 추상어 하나를 쓰면 반드시 장면, 실제 멘트, 채팅 갈등 중 하나로 내려앉힌다.
"""

STRUCTURAL_OUTPUT_GUARD = """
구조화 산출물 품질 가드:
- required_schema를 절대 되돌려주지 않는다. 스키마 설명문, 자리표시자, "해결 방법 1" 같은 빈 값은 실패다.
- 모든 값은 이 사연의 제목/본문에서 나온 구체 정보와 연결되어야 한다. 최소 2개 이상의 사건 디테일, 관계 디테일, 감정 디테일을 넣는다.
- role/purpose/tone_note 같은 설계 필드는 "라이브 오프닝", "사연 읽기", "최종 판단"처럼 일반 라벨로 끝내지 말고, 이 사연에서 그 구간이 무엇을 새로 뒤집는지 써야 한다.
- beats의 각 항목은 새 정보, 판단 변화, 채팅 충돌, 실제 상담 문장 중 최소 3개를 반드시 가진다.
- 모르면 빈칸을 두지 말고 "본문에 없어 단정하지 않음. 대신 방송에서는 이렇게 질문한다"로 처리한다.
- JSON은 완성된 PD 노트여야 한다. 앱 화면에 그대로 보여줘도 민망하지 않은 밀도로 작성한다.
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
- 나쁜 예: 채팅창에 "사연자님 화이팅"이라고 써주세요. 다음에 또 새로운 사연으로 만나요.
- 나쁜 예: 작은 변화로 조명을 켜고 서로의 취향을 공유해보세요.
"""

STORY_IMMERSION_ENGINE = """
몰입 구조 엔진:
- 이 앱의 결과물은 정보 요약이 아니라 '사람들이 채팅창에서 판단을 나누고 계속 보게 되는 상담 라이브'여야 한다.
- 모든 대본은 사건을 한 번에 설명하지 않는다. 60~90초마다 새 정보, 새 의심, 새 반론, 새 조언을 열어 시청자의 판단을 흔든다.
- 핵심 질문은 항상 하나다. "누가 맞나?"보다 "왜 이 관계에서 이 장면이 이렇게 불편하게 느껴졌나?"를 추적한다.
- 오프닝은 3초 안에 논쟁 폭탄을 던진다. 인사, 오늘의 주제 소개, 사연 제목 낭독으로 시작하지 않는다.
- 각 구간은 장면 재구성 -> 화자 감정 리액션 -> 채팅 반론 -> 사주/점성술식 패턴 읽기 -> 현실 상담 문장 -> 다음 궁금증 순서로 굴러간다.
- 사주/점성술은 장식어가 아니다. 비밀의 자리, 사회적 얼굴, 관계 궁합의 충돌, 타이밍이 어긋난 순간처럼 사건 구조를 읽는 렌즈로만 쓴다.
- 채팅 반응은 "여러분 의견 주세요"가 아니라 실제 라이브의 충돌이어야 한다. 예: "채팅에 지금 사연자님도 잘못했다 올라오는데, 잠깐만 그 말은 반은 맞고 반은 위험해요."
- 상담 파트는 감정 위로가 아니라 실행 가능한 문장이다. 상대에게 보낼 문장, 상대가 회피할 때의 다음 말, 여기서 멈춰야 하는 기준을 준다.
- 민감 주제는 정체성을 판단하지 않고 행동, 맥락, 동의, 공개 범위, 2차 피해 방지로 분리해서 다룬다.
"""

LIVE_SCRIPT_CONTRACT = """
대본 출력 계약:
- 타임코드는 줄 하나에 00:00 형식으로만 쓴다. "00:00 오프닝"처럼 제목을 붙이지 않는다.
- 최소 11개 구간을 쓴다: 00:00, 00:45, 01:35, 02:30, 03:25, 04:20, 05:20, 06:20, 07:25, 08:25, 09:20.
- 00:00~08:25 구간은 각각 650자 이상, 09:20 구간은 500자 이상으로 쓴다.
- 각 구간에는 실제 방송 멘트만 쓴다. 목차, bullet, 분석 라벨, 괄호 지시문, "이 구간에서는" 같은 제작 메모를 쓰지 않는다.
- 각 구간마다 최소 하나의 구체 장면, 하나의 화자 리액션, 하나의 판단 문장, 하나의 다음 구간 연결 멘트가 있어야 한다.
- 전체 대본 안에 채팅을 받아치는 장면 5회 이상, 상담자가 직접 제시하는 실제 발화 문장 4개 이상, 사주/점성술 패턴 읽기 4회 이상을 넣는다.
- 시청자 몰입을 위해 초반 3분 안에 서로 반대되는 두 해석을 모두 제시한다.
- 결말은 단순 정답 발표가 아니라 "지금 당장 할 행동", "하지 말아야 할 행동", "댓글에서 갈릴 질문"으로 닫는다.
"""


def analyze_story(source_text: str, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 커뮤니티 사연을 유튜브 라이브 상담 콘텐츠로 개발하는 PD다.
원문을 복제하지 말고, 개인정보와 식별 요소를 일반화한다.
대본을 쓰지 말고, 사람들이 끝까지 보게 만드는 판단 구조와 상담 구조만 해부한다.

{STORY_IMMERSION_ENGINE}
{PERSONA_EMBODIMENT_ENGINE}
{EMBODIED_INSIGHT_ENGINE}
{VIRAL_RETENTION_ENGINE}
{INTIMACY_BOUNDARY_ENGINE}
{STORY_BRAIN_ENGINE}
{STRUCTURAL_OUTPUT_GUARD}

{localization_prompt()}

반드시 JSON만 반환한다."""
    schema = {
        "story_summary": "사연 핵심 요약. 번역투 없이 자연스러운 한국어",
        "case_thesis": "이 사연을 한 문장으로 해부한 PD 관점. 표면 사건이 아니라 숨은 관계 엔진을 말한다",
        "surface_event": "겉으로 보이는 사건",
        "real_engine": "실제로 사람을 붙잡는 돈/수치심/권력/비밀/가족/몸/역할 기대 중 핵심 작동축",
        "one_line_viral_premise": "시청자가 3초 안에 이해할 바이럴 전제. 누가 무엇을 했고 왜 갈리는지",
        "episode_title_candidates": ["한국 라이브 제목 후보. 자극보다 갈등 구조가 보이게"],
        "cold_open_bomb": "대본 첫 문장으로 쓸 수 있는 사건 폭탄. 인사 금지",
        "first_5_second_cue": "첫 5초 안에 들어갈 결과/논쟁/감정 폭탄. 배경 설명 금지",
        "first_30_second_contract": "시청자가 30초 안에 이해할 시청 계약: 끝까지 보면 무엇을 판단/해결하게 되는지",
        "embodied_entry_seed": "화자가 자신의 개인적 하루나 몸의 감각으로 들어갈 수 있는 도입 소재. 사연의 상징과 연결",
        "judgment_question": "댓글이 갈릴 핵심 질문. 예: 이건 예민함인가, 선 넘은 행동인가",
        "curiosity_gap": "시청자가 다음 내용을 기다리게 만드는 미해결 의문",
        "localized_context": "원문 문화권/플랫폼 맥락을 한국 시청자가 이해할 수 있게 변환한 설명",
        "translation_notes": ["직역하면 어색하거나 위험한 표현과 권장 표현"],
        "sender_problem": "사연자가 진짜 상담받고 싶은 문제",
        "main_conflict": "핵심 갈등",
        "relationship_map": ["인물 관계. 이름/직장/지역 등 식별 요소는 일반화"],
        "character_cards": [
            {
                "role": "사연자/상대/주변 인물",
                "surface_claim": "겉으로 내세우는 주장",
                "hidden_pressure": "관계 안에서 실제로 작동하는 압박",
                "audience_suspicion": "시청자가 의심할 지점",
            }
        ],
        "timeline": ["사건 순서. 각 항목은 장면으로 재구성 가능한 수준"],
        "emotional_trigger": "감정이 터지는 지점",
        "hidden_pattern": "반복되는 관계 패턴",
        "money_status_power_axis": "돈, 저축, 직업, 성취, 자존심, 역할 기대가 얽힌 사연이면 그 축을 분석. 없으면 해당 없음",
        "shame_or_pride_trigger": "상대가 울거나 화내거나 얼어붙은 이유를 수치심/자존심/비교감/통제감 관점에서 추론",
        "symbolic_motif": {
            "motif": "대본 전체에 반복할 상징. 예: 빨간불/문/침묵/알림/계단",
            "sensory_details": ["눈에 남는 색, 소리, 몸의 반응 같은 감각 디테일"],
            "meaning_shift": "일상 신호가 관계 패턴이나 시대 공기로 확장되는 방식",
        },
        "viral_angle_bank": [
            {
                "angle_name": "바이럴 각도 이름",
                "why_people_watch": "사람들이 왜 계속 보게 되는지",
                "comment_fight": "댓글에서 싸울 질문",
                "hook_line": "이 각도로 시작할 때의 실제 후킹 문장",
            }
        ],
        "moral_tension_matrix": [
            {
                "frame": "돈/사랑/자존심/통제/안전/가족 등 판단 프레임",
                "pro_argument": "이 프레임에서 한쪽이 맞아 보이는 이유",
                "counter_argument": "바로 반박되는 이유",
                "host_position": "화자가 중간에서 잡아줄 판단",
            }
        ],
        "client_tendency_read": {
            "mbti_style_hypothesis": "MBTI 확정이 아니라 감정형/사고형, 직관형/감각형, 계획형/즉흥형처럼 보이는 성향 충돌",
            "saju_compatibility_lens": "생년월일 없이 단정하지 않는 사주/오행/궁합 렌즈. 속도, 온도, 표현 방식의 충돌로 설명",
            "relationship_tempo": "두 사람이 감정을 처리하는 속도와 확인 방식의 차이",
            "safe_caveat": "단정하지 않기 위한 방송 멘트",
        },
        "implicit_insight_lines": ["대놓고 진단하지 않고 방송 멘트 속에 은근히 넣을 성향/궁합 인사이트 문장"],
        "open_loops": ["초반에 열고 중후반에 회수할 궁금증. 최소 3개"],
        "loop_payoffs": ["열어둔 궁금증을 어느 지점에서 어떤 문장으로 회수할지"],
        "pattern_interrupts": ["설명 흐름을 끊고 다시 보게 만드는 반전/질문/채팅 충돌 장치"],
        "turning_points": ["판단이 바뀌거나 더 복잡해지는 반전/추가 정보"],
        "host_take_evolution": [
            {"time": "00:00", "take": "초반 판단", "why_it_changes": "뒤에서 무엇 때문에 흔들리는지"},
            {"time": "04:00", "take": "중반 재해석", "why_it_changes": "새 정보나 채팅 반론"},
            {"time": "09:00", "take": "최종 상담 판단", "why_it_changes": "상담 기준"},
        ],
        "audience_camps": [
            {"camp": "시청자 진영 이름", "argument": "이 진영의 주장", "emotional_payoff": "왜 이 주장에 끌리는지"}
        ],
        "chat_debate_points": ["채팅이 갈릴 포인트. 찬반 양쪽 논리 포함"],
        "scene_reconstruction_notes": ["대본에서 장면처럼 풀어쓸 수 있는 디테일"],
        "scene_bank": [
            {
                "scene": "방송에서 장면처럼 재구성할 순간",
                "sensory_anchor": "눈/소리/몸감각",
                "host_reaction": "화자의 실제 반응 멘트",
                "why_it_matters": "이 장면이 판단을 바꾸는 이유",
            }
        ],
        "quote_bank": ["대본에 바로 쓸 수 있는 화자 멘트. 일반론 금지"],
        "astrology_lens": ["사주/점성술/기운으로 볼 수 있는 해석 포인트"],
        "occult_pattern_map": [
            {"symbol": "비밀의 자리/사회적 얼굴/운의 흐름 등", "relationship_read": "관계 구조 해석", "safe_language": "단정하지 않는 표현"}
        ],
        "practical_advice_angles": ["현실 조언 방향"],
        "counseling_targets": [
            {
                "goal": "확인/사과 요구/경계 설정/거리두기 등",
                "exact_sentence": "사연자님이 실제로 말할 수 있는 문장",
                "if_they_deflect": "상대가 회피할 때 다음 대응",
            }
        ],
        "risk_notes": ["재가공 유의점"],
        "intimacy_boundary_notes": {
            "consent_question": "친밀관계/기기/사생활 이슈가 있다면 동의 여부를 어떻게 질문할지",
            "privacy_or_recording_risk": "촬영/녹화/저장/공유 가능성을 안전하게 다루는 방식",
            "boundary_sentences": ["사연자님이 실제로 말할 수 있는 중단/확인/삭제 요구 문장"],
        },
        "do_not_say": ["민감하거나 번역투라 피해야 하는 문장"],
    }
    user = {"title": row.get("title"), "source": row.get("source"), "url": row.get("url"), "source_text": clean_text(source_text, 14000), "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=7500, json_mode=True)
    if error:
        return {}, error
    parsed, parse_error = extract_json_object(raw or "")
    if parse_error:
        return parsed or {}, parse_error
    return repair_json_if_needed("story_analysis", parsed or {}, raw or "", user, model, temperature, 8000)


def build_live_blueprint(analysis: dict, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 라이브 사연 상담형 유튜브 대본의 구성 작가다.
{LIVE_NARRATOR_RULES}
{PERSONA_EMBODIMENT_ENGINE}
{EMBODIED_INSIGHT_ENGINE}
{VIRAL_RETENTION_ENGINE}
{INTIMACY_BOUNDARY_ENGINE}
{STORY_BRAIN_ENGINE}
{STRUCTURAL_OUTPUT_GUARD}
{STYLE_REFERENCE_BLOCK}
{STORY_IMMERSION_ENGINE}
{localization_prompt()}

10분 분량 대본을 위한 연출 비트시트를 만든다. 아직 최종 대본은 쓰지 않는다.
각 비트는 최종 대본에서 긴 실제 멘트로 확장될 수 있도록 장면, 갈등, 채팅 충돌, 사주/점성술 렌즈, 상담 행동을 구체적으로 설계한다.
타임코드마다 새 정보나 새 판단 변화를 넣어야 한다. 같은 이야기를 반복하는 비트는 실패다.
role/purpose/tone_note만 있는 빈 설계는 실패다. 각 비트는 실제 방송 멘트 샘플, 채팅 반론, 상담 문장, 다음 궁금증을 포함해야 한다.
반드시 JSON만 반환한다."""
    schema = {
        "production_thesis": "이 사연을 라이브 상담으로 만들 때 끝까지 붙잡을 핵심 관점",
        "episode_arc": {
            "start_judgment": "00:00에서 시청자가 처음 내릴 판단",
            "midpoint_complication": "중반에 그 판단을 흔드는 정보/반론",
            "final_counseling_standard": "마지막에 남길 현실 상담 기준",
        },
        "retention_thesis": "이 영상이 10분 동안 버틸 긴장. 단순 사건 설명이 아니라 무엇이 계속 궁금한지",
        "host_persona_anchor": "이 사연 앞에서 30대 한국 여성 라이브 상담 화자가 먼저 느끼는 불편함, 조심할 선, 채팅을 받아칠 태도",
        "host_personal_entry": "00:00에서 화자가 자기 경험처럼 체화해서 꺼낼 도입. 일상 감각 3개 이상 포함",
        "motif_ladder": ["개인 경험 속 상징", "사연 속 같은 상징", "관계/사회 패턴으로 확장된 상징"],
        "implicit_profile_insights": ["MBTI/사주 궁합/오행 렌즈를 단정 없이 상담 멘트에 녹일 문장"],
        "boundary_safety_plan": {
            "consent_frame": "동의/사전 설명/중단 기준을 어떤 구간에 넣을지",
            "device_or_privacy_checks": ["촬영/녹화/저장/공유 가능성 확인 문장"],
            "what_not_to_advise": ["노출 적응, 몸 평가, 성적 취향 훈수처럼 피할 조언"],
        },
        "first_5_second_cue": "대본 첫 1~2문장. 결과/논쟁/책임 갈림부터 시작",
        "first_30_second_contract": "30초 안에 줄 시청 보상과 남겨둘 반전",
        "segment_escalation_rules": [
            "각 구간에서 새로 공개할 정보나 새로 바뀌는 판단",
            "이전 구간과 같은 말이 반복되지 않게 막는 규칙",
            "상담 가치가 누적되는 순서",
        ],
        "retention_loop_plan": [
            {
                "timecode": "00:45",
                "rehook_type": "새 정보/반대 해석/채팅 충돌/개인 경험 회수/상담 문장 중 하나",
                "open_loop": "이 구간에서 새로 여는 궁금증",
                "payoff_later": "어느 뒤 구간에서 회수할지",
                "pattern_interrupt_line": "톤을 꺾는 실제 멘트 샘플",
            }
        ],
        "opening_hook": "00:00에서 시작할 후킹. 번역투 금지. 사건의 논점부터 시작",
        "cold_open_script_seed": "첫 2~3문장 샘플. 인사 금지",
        "localization_strategy": "원문 표현을 어떤 한국어 맥락으로 바꿀지",
        "judgment_ladder": [
            "초반 판단",
            "새 정보로 흔들리는 판단",
            "채팅 반론으로 보정되는 판단",
            "최종 상담 판단",
        ],
        "open_loops": ["초반에 열고 후반에 회수할 궁금증"],
        "chat_camps": [
            {"camp": "채팅 진영", "claim": "이들이 밀 주장", "why_they_feel_that": "감정적으로 끌리는 이유", "host_response": "화자가 받아칠 방식"}
        ],
        "beats": [
            {
                "timecode": "00:00",
                "role": "콜드오픈 폭탄",
                "segment_goal": "3초 안에 논쟁과 불편함 제시",
                "micro_hook": "해당 타임코드 첫 문장에 들어갈 리훅",
                "new_reveal": "",
                "emotional_turn": "",
                "embodied_scene": "화자의 몸에 남은 개인 경험/감각과 연결할 장면",
                "chat_collision": "",
                "open_loop_or_payoff": "새로 열 궁금증 또는 앞에서 연 궁금증 회수",
                "pattern_interrupt": "설명 리듬을 깨는 반전/질문/채팅 충돌",
                "astrology_bridge": "",
                "implicit_profile_or_compatibility_insight": "MBTI식 성향/사주 궁합/오행 렌즈를 은근히 넣을 지점",
                "counseling_value": "",
                "cliffhanger_to_next": "",
                "must_include_lines": ["실제 멘트 샘플 2개"],
                "min_chars": 750,
            },
            {"timecode": "00:45", "role": "사연자 입장 재구성", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 700},
            {"timecode": "01:35", "role": "첫 번째 이상 신호", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 700},
            {"timecode": "02:30", "role": "채팅 1차 분열", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 700},
            {"timecode": "03:25", "role": "상대 입장까지 열어보기", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 700},
            {"timecode": "04:20", "role": "판단이 흔들리는 반전", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 750},
            {"timecode": "05:20", "role": "사주/점성술 패턴 읽기", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 750},
            {"timecode": "06:20", "role": "현실 상담 1단계", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 800},
            {"timecode": "07:25", "role": "상대 반응별 대응", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 800},
            {"timecode": "08:25", "role": "최종 판단 직전 채팅 정리", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 700},
            {"timecode": "09:20", "role": "최종 상담 판단과 댓글 질문", "segment_goal": "", "new_reveal": "", "emotional_turn": "", "chat_collision": "", "astrology_bridge": "", "counseling_value": "", "cliffhanger_to_next": "", "must_include_lines": [], "min_chars": 550},
        ],
        "voice_toolkit": {
            "reaction_lines": ["이 사연에 맞춘 화자 리액션 문장. 일반 유행어 나열 금지"],
            "chat_pushback_lines": ["채팅 반론을 받아치는 실제 문장"],
            "astrology_bridge_lines": ["사주/점성술 렌즈를 사건 구조와 연결하는 문장"],
            "quiet_lines": ["감정이 가라앉는 순간에 쓸 낮은 톤의 문장"],
        },
        "advice_steps": [
            {"step": "확인 질문", "exact_sentence": "실제로 말할 문장", "do_not_do": "피해야 할 말"},
            {"step": "상대 반응별 대응", "exact_sentence": "회피/사과/역공 시 대응 문장", "do_not_do": "피해야 할 행동"},
            {"step": "경계 설정", "exact_sentence": "여기까지만 허용한다는 문장", "do_not_do": "피해야 할 행동"},
        ],
        "if_then_response_tree": [
            {"if_partner_says": "상대가 이렇게 반응하면", "host_read": "그 반응의 의미", "sender_sentence": "사연자가 다음에 할 말", "stop_line": "여기서 멈춰야 할 기준"}
        ],
        "forbidden_generic_phrases": ["함께 고민해보면 좋을 것 같아요", "그럼 시작해볼까요", "정말 다양한 시각이 있는 것 같아요", "사생활이 터졌다"],
        "continuity_notes": ["구간 사이를 자연스럽게 연결하기 위한 멘트"],
    }
    user = {"title": row.get("title"), "analysis": analysis, "required_schema": schema}
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=temperature, max_tokens=8500, json_mode=True)
    if error:
        return {}, error
    parsed, parse_error = extract_json_object(raw or "")
    if parse_error:
        return parsed or {}, parse_error
    return repair_json_if_needed("live_blueprint", parsed or {}, raw or "", user, model, temperature, 9000)


def write_live_longform(source_text: str, analysis: dict, blueprint: dict, row: dict, model: str, temperature: float) -> tuple[str, Optional[str]]:
    system = f"""너는 실제 한국 라이브 유튜버 말투를 잘 쓰는 대본 작가이자 고급 로컬라이징 에디터다.
{LIVE_NARRATOR_RULES}
{PERSONA_EMBODIMENT_ENGINE}
{EMBODIED_INSIGHT_ENGINE}
{VIRAL_RETENTION_ENGINE}
{INTIMACY_BOUNDARY_ENGINE}
{STORY_BRAIN_ENGINE}
{STYLE_REFERENCE_BLOCK}
{STORY_IMMERSION_ENGINE}
{LIVE_SCRIPT_CONTRACT}
{localization_prompt()}

절대 조건:
- 10분 롱폼 내레이션 대본을 쓴다.
- 총 8,500자 이상, 가능하면 9,000~11,000자.
- 타임코드 11개 이상 포함. 타임코드 줄은 반드시 00:00 형식만 쓴다.
- 각 타임코드마다 최소 650자 이상 실제 말로 작성한다. 제목/요약/목차만 쓰면 실패다.
- 오프닝은 흔한 인사 금지. 바로 사연의 이상한 지점으로 들어간다.
- 첫 5초는 결과/논쟁/책임 갈림 중 하나로 시작한다. 인사, 맥락 설명, 사연 제목 낭독 금지.
- 첫 30초 안에 "끝까지 봐야 하는 이유"를 만든다. 오늘 판단할 질문, 뒤에 남은 반전, 얻어갈 상담 문장을 약속한다.
- 00:00~01:35 안에 화자의 개인적 경험형 도입을 넣는다. "나도 그런 날이 있었거든" 수준이 아니라 몸에 남은 감각, 반복된 상징, 말이 꼬이는 순간을 구체적으로 보여준다.
- "안녕하세요 여러분", "함께 고민해볼까요", "다양한 시각이 있네요", "정말 서운하셨겠어요" 같은 AI식 문장 금지.
- "사생활이 터졌다", "성 정체성이 드러났다"처럼 과격하거나 부정확한 번역투 금지. 맥락에 따라 "개인적인 일이 원치 않게 알려졌다", "아웃팅처럼 받아들여질 수 있었다", "사적인 부분이 사람들 입에 오르내리게 됐다"처럼 쓴다.
- 친밀관계/몸/기기/촬영 가능성이 있는 사연은 동의, 사전 설명, 촬영·녹화·저장 여부, 프라이버시, 즉시 중단 기준을 반드시 다룬다.
- "불을 켜보세요", "취향을 공유해보세요", "관계를 더 깊게" 같은 노출 적응/미화 조언 금지. 불편함을 느낀 사람에게 적응을 요구하지 않는다.
- 존댓말 진행 50%, 반말 리액션 30%, 채팅 받아치기 10%, 혼잣말/자기정정 10% 정도로 섞는다.
- "사연자님" 8회 이상, "여러분" 10회 이상, "채팅" 또는 "댓글" 반응 5회 이상, 현실 조언 4개 이상 포함한다.
- "아니 잠깐만", "야 이건", "근데", "제가 보기엔요", "저기요", "작두 살짝만", "사주로 치면", "기운", "궁합", "운의 흐름" 중 여러 개를 자연스럽게 사용한다.
- 사주/점성술 표현은 허용한다. 다만 무조건 악연, 100%, 운명 확정 같은 단정은 금지한다.
- MBTI/사주 궁합/오행 인사이트는 은근히 넣는다. 내담자를 확정 진단하지 말고, 성향 충돌과 관계 리듬을 설명한 뒤 바로 실제 상담 문장으로 연결한다.
- 대본 전체에 반복 상징을 하나 세운다. 처음엔 개인 경험, 중간엔 사연의 관계 패턴, 후반엔 시대/댓글/구설의 공기로 확장한다.
- 사연 원문은 읽어주는 느낌으로 재구성하되, 원문 문장을 그대로 복제하지 않는다.
- 반드시 해결 방법을 자세히 준다. '대화해보세요' 한 줄 금지. 어떤 문장으로 물어볼지, 상대 반응별로 어떻게 할지까지 말한다.
- 초반 3분 안에 시청자들이 갈릴 해석 두 개를 모두 제시한다.
- 중반에는 화자 판단이 한 번 흔들려야 한다. 처음부터 끝까지 같은 주장만 밀면 실패다.
- 후반 상담 파트에는 상대가 사과할 때, 회피할 때, 역공할 때의 대응 문장을 분리해서 말한다.
- 매 타임코드 첫 1~2문장에는 마이크로 후킹을 넣는다. 새 정보, 반대 해석, 채팅 충돌, "아까 말한 것" 회수, 다음 구간 궁금증 중 하나가 있어야 한다.
- 설명문이 4~5문장 이상 같은 톤으로 이어지면 실패다. 패턴 인터럽트로 리듬을 꺾어라.
- 오픈루프 3개 이상을 열고 반드시 회수한다. 회수 없이 궁금증만 던지는 것은 실패다.
- 반환은 대본 텍스트만. JSON 금지.

출력 구조:
00:00부터 09:20 이후까지 작성하되, 각 구간은 실제 방송 멘트로 길게 쓴다.
각 구간은 최소 5~8문단으로 쓴다. 짧은 문단과 긴 문단을 섞는다.
타임코드 외의 소제목은 쓰지 않는다.
"""
    user = {
        "title": row.get("title"),
        "source_text_for_context_only": clean_text(source_text, 16000),
        "analysis": analysis,
        "blueprint": blueprint,
        "mission": "짧고 점잖은 상담 대본이 아니라, 진짜 라이브 유튜버가 사연 읽으며 채팅과 티키타카하고 사주/점성술 감각으로 풀이하는 10분짜리 장문 대본을 작성하라. 번역투를 없애고 현지화 수준을 최대로 끌어올려라.",
        "embodied_insight_mission": "화자의 개인 경험형 도입으로 사연의 공기를 먼저 몸에 입힌 뒤, MBTI식 성향/사주 궁합/오행 렌즈를 은근한 상담 인사이트로 녹여라. 확정 진단이나 예언처럼 쓰지 말고 관계 리듬 설명으로 처리하라.",
        "retention_mission": "100만 뷰급 팟캐스트/라이브처럼 첫 5초 cue, 첫 30초 시청 계약, 매 타임코드 리훅, 오픈루프와 회수를 설계하라. 모든 구간은 시청자가 다음 구간을 궁금해하도록 끝나야 한다.",
        "script_contract": {
            "timecodes": ["00:00", "00:45", "01:35", "02:30", "03:25", "04:20", "05:20", "06:20", "07:25", "08:25", "09:20"],
            "minimum_total_chars": 8500,
            "recommended_total_chars": "9000~11000",
            "minimum_section_chars": 650,
            "required_chat_reactions": 5,
            "required_exact_advice_sentences": 4,
            "required_astrology_pattern_reads": 4,
            "required_embodied_personal_anchor": 1,
            "required_implicit_profile_insights": 3,
            "required_open_loops": 3,
            "required_loop_payoffs": 3,
            "required_micro_hooks_per_timecode": True,
            "required_boundary_or_privacy_checks_when_relevant": 4,
        },
        "section_fill_rule": "각 타임코드는 마이크로 후킹, 장면 재구성, 화자 리액션, 채팅 충돌, 사주/점성술 패턴 읽기, 현실 상담 문장, 다음 궁금증 연결 중 최소 5개 이상을 포함해야 한다.",
        "minimum_length_reminder": "8,500자 미만이면 실패다. 모든 타임코드를 충분히 확장하라.",
    }
    raw, error = openai_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ], model=model, temperature=max(0.62, min(temperature, 0.9)), max_tokens=12000)
    return raw or "", error


def generate_derivatives(longform_script: str, analysis: dict, row: dict, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    system = f"""너는 롱폼 대본을 쇼츠, Threads, 카드뉴스로 재가공하는 콘텐츠 편집자이자 고급 로컬라이징 에디터다.
{LIVE_NARRATOR_RULES}
{PERSONA_EMBODIMENT_ENGINE}
{EMBODIED_INSIGHT_ENGINE}
{VIRAL_RETENTION_ENGINE}
{INTIMACY_BOUNDARY_ENGINE}
{STORY_BRAIN_ENGINE}
{STRUCTURAL_OUTPUT_GUARD}
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
    ], model=model, temperature=temperature, max_tokens=5500, json_mode=True)
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
