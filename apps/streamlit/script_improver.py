from __future__ import annotations

import json
from typing import Optional

from llm_pipeline import (
    EMBODIED_INSIGHT_ENGINE,
    INTIMACY_BOUNDARY_ENGINE,
    LIVE_NARRATOR_RULES,
    LIVE_SCRIPT_CONTRACT,
    PERSONA_EMBODIMENT_ENGINE,
    STYLE_REFERENCE_BLOCK,
    STORY_IMMERSION_ENGINE,
    VIRAL_RETENTION_ENGINE,
    clean_text,
    localization_prompt,
    openai_chat,
)


IMPROVEMENT_RULES = """
품질검사 실패 시 개선 룰:
1. 실패 항목을 우선순위로 정리한다. critical_failures > 낮은 점수 항목 > warnings 순서다.
2. 대본을 살짝 고치는 것이 아니라, 실패 원인을 해결하도록 구조를 재작성한다.
3. 분량 부족이면 전체를 10분 롱폼 수준으로 확장한다. 최소 8,500자, 권장 9,000~11,000자.
4. 후킹 약함이면 첫 700자에서 인사말을 삭제하고 사건의 폭탄, 판단 갈림, 책임 소재를 먼저 보여준다.
5. 라이브감 부족이면 채팅 의견을 최소 3회 받아치고, 단순 의견 유도가 아니라 채팅 의견 때문에 화자의 판단이 흔들리거나 보정되는 장면을 넣는다.
6. 상담성 부족이면 '대화해보세요' 같은 추상 조언을 금지한다. 실제로 말할 문장, 상대 반응별 대응, 피해야 할 행동까지 쓴다.
7. 캐릭터성 부족이면 사주/점성술 단어를 랜덤으로 꽂지 않는다. 사건 구조에 붙인다. 예: 비밀의 자리, 사회적 얼굴, 기운이 드러난 순간, 관계 궁합의 충돌.
8. 반존대 부족이면 진행은 존댓말, 감정 리액션과 채팅 받아치기는 반말이 튀어나오게 한다.
9. 로컬라이징 부족이면 미국식 표현을 한국 유튜브 사연 말투로 재작성한다. 한국에서 통용되는 외래어는 그대로 쓰고, 어색한 직역은 문장으로 푼다.
10. 민감 주제 처리 부족이면 단정하지 않는다. 정체성, 사생활, 아웃팅, 차별, 폭력, 임신, 장애 등은 행동과 정체성을 분리하고 2차 피해 방지 조언을 넣는다.
11. 사용자가 직접 입력한 디렉션은 품질검사보다 우선한다. 단, 원문 왜곡, 단정적 점술, 혐오/비하, 개인정보 노출은 하지 않는다.
12. 추가 생성 모드에서는 기존 대본을 전부 다시 쓰지 말고, 부족한 구간에 붙일 수 있는 방송 멘트 블록을 만든다.
13. 서사 몰입도 부족이면 각 타임코드마다 새 정보, 판단 변화, 반대 해석, 다음 궁금증을 넣는다.
14. 채팅 논쟁성 부족이면 찬반 채팅을 실제로 받아치며 화자의 판단이 보정되는 장면을 만든다.
15. 최종 대본에는 제작 메모, 목차, 분석 라벨이 남으면 안 된다. 타임코드와 실제 방송 멘트만 남긴다.
16. 체화형 도입이 부족하면 화자의 개인적 경험, 몸에 남은 감각, 반복 상징으로 사연의 공기를 먼저 입힌다.
17. 성향/궁합 인사이트가 부족하면 MBTI식 성향 충돌, 사주 궁합, 오행, 대운/세운 렌즈를 단정 없이 상담 문장에 녹인다.
18. 후킹 장치가 부족하면 첫 5초 결과/논쟁, 첫 30초 시청 계약, 매 타임코드 리훅을 새로 설계한다.
19. 리텐션 루프가 부족하면 최소 3개의 오픈루프와 3개의 회수 문장을 만든다. 던지기만 하고 회수하지 않으면 실패다.
20. 친밀관계/기기/프라이버시 사연은 동의, 촬영·녹화·저장 가능성, 중단 기준, 삭제/확인 문장을 중심으로 재작성한다.
21. 저품질 채팅 유도와 빈 마무리 멘트는 삭제한다. 후반부도 새 정보, 판단 변화, 현실 대응으로 채운다.
"""

DIRECTION_GUIDE = """
사용자 디렉션 반영 방식:
- 사용자의 디렉션을 단순 참고가 아니라 재작성의 핵심 기준으로 삼는다.
- 디렉션이 '더 세게', '더 디테일하게', '후킹 강화'처럼 추상적이면 구체적 제작 행동으로 번역한다.
- 디렉션이 특정 문장/관점/톤을 요구하면 해당 방향을 반영하되, 품질검사 기준도 동시에 만족시킨다.
- 디렉션이 추가 생성이면 기존 대본과 자연스럽게 이어질 타임코드/블록을 생성한다.
"""

PERSONA_REWRITE_CORE = """
[먼저 체화할 화자]
- 연령/성별/국적: 32~38세 한국 여성. 해외 사연도 한국 유튜브 라이브 시청자에게 바로 꽂히게 번역하는 사람이다.
- 위치감: 사연자에게는 선을 지키는 상담자, 시청자에게는 "언니/누나처럼 가까운데 판단은 빠른 진행자"다.
- 직업감: 무속인이나 상담센터 직원이 아니라, 사주/점성술을 관계 패턴을 읽는 은유로 쓰는 라이브 콘텐츠 진행자다.
- 말투: 존댓말로 진행하다가 장면이 이상하거나 채팅이 과열되면 반말 리액션이 튀어나온다. 반말은 귀여운 장식이 아니라 판단의 온도다.
- 판단 방식: 한 사람을 악역으로 박기 전에 행동, 맥락, 동의, 공개 범위, 관계의 힘 차이를 나눈다. 그래야 민감한 사연도 오래 볼 수 있다.
- 방송 목표: 시청자가 "누가 맞아?"에서 멈추지 않고 "왜 이 장면이 찝찝하지?"를 계속 따라오게 만든다.
- 체화 방식: 사연을 바로 해설하지 않고, 화자가 겪은 비슷한 하루/작은 신호/몸의 감각으로 먼저 들어가 시청자가 공기를 느끼게 한다.
- 인사이트 방식: MBTI와 사주 궁합은 정답지가 아니라 관계 리듬을 읽는 렌즈다. 성향을 말하면 바로 실제 상담 문장으로 이어야 한다.
- 리텐션 방식: 첫 5초에는 결과나 논쟁, 첫 30초에는 시청 계약, 이후 매 타임코드에는 마이크로 후킹과 다음 궁금증이 있어야 한다.
- 민감관계 방식: 친밀한 상황의 사연은 자극적 묘사 대신 동의, 프라이버시, 촬영 가능성, 기기 사용 설명, 중단 기준을 먼저 본다.
"""


def compact_quality_report(quality: dict) -> dict:
    return {
        "overall_score": quality.get("overall_score"),
        "grade": quality.get("grade"),
        "passed": quality.get("passed"),
        "scores": quality.get("scores", {}),
        "critical_failures": quality.get("critical_failures", []),
        "warnings": quality.get("warnings", []),
        "rewrite_guidance": quality.get("rewrite_guidance", []),
        "metrics": quality.get("metrics", {}),
    }


def _score_value(scores: dict, key: str, default: int = 100) -> int:
    try:
        return int(scores.get(key, default))
    except (TypeError, ValueError):
        return default


def _sort_score_item(item: tuple[str, object]) -> float:
    try:
        return float(item[1])
    except (TypeError, ValueError):
        return 0.0


def _format_analysis_value(value: object, limit: int = 180) -> str:
    if isinstance(value, list):
        value = " / ".join(str(item) for item in value[:3])
    elif isinstance(value, dict):
        value = " / ".join(f"{key}: {val}" for key, val in list(value.items())[:3])
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def build_persona_rewrite_diagnostic(
    quality: dict,
    analysis: Optional[dict] = None,
    row: Optional[dict] = None,
) -> str:
    """Create a persona-first diagnostic that turns numeric failures into writer behavior."""
    analysis = analysis or {}
    row = row or {}
    scores = quality.get("scores", {}) or {}
    metrics = quality.get("metrics", {}) or {}

    parts: list[str] = [PERSONA_REWRITE_CORE.strip()]

    title = _format_analysis_value(row.get("title"), 120)
    if title:
        parts.append(f"[오늘 이 화자가 손에 든 사연]\n- {title}")

    story_lines: list[str] = []
    for label, key in [
        ("화자가 체화할 개인 경험 도입", "embodied_entry_seed"),
        ("첫 판단 질문", "judgment_question"),
        ("핵심 갈등", "main_conflict"),
        ("감정이 터지는 지점", "emotional_trigger"),
        ("반복되는 관계 패턴", "hidden_pattern"),
        ("사연자가 진짜 받고 싶은 상담", "sender_problem"),
        ("반복 상징", "symbolic_motif"),
        ("내담자 성향/궁합 렌즈", "client_tendency_read"),
        ("첫 5초 후킹 cue", "first_5_second_cue"),
        ("첫 30초 시청 계약", "first_30_second_contract"),
        ("오픈루프", "open_loops"),
        ("루프 회수", "loop_payoffs"),
        ("패턴 인터럽트", "pattern_interrupts"),
    ]:
        value = _format_analysis_value(analysis.get(key))
        if value:
            story_lines.append(f"- {label}: {value}")
    insight_lines = analysis.get("implicit_insight_lines")
    if isinstance(insight_lines, list) and insight_lines:
        story_lines.append("- 은근히 넣을 인사이트: " + " / ".join(str(item) for item in insight_lines[:3]))
    if story_lines:
        parts.append("[이 사연 앞에서 화자가 먼저 붙잡을 것]\n" + "\n".join(story_lines))

    diagnosis: list[str] = []
    if _score_value(scores, "캐릭터성") < 65:
        diagnosis.append("- 캐릭터성 낮음: 사주/점성술 단어를 더 넣는 문제가 아니다. 화자의 나이, 성별, 플랫폼 감각이 문장마다 느껴지게 다시 써야 한다.")
    if _score_value(scores, "반존대_자연스러움") < 65:
        diagnosis.append("- 반존대 약함: 존댓말 설명만 이어지면 상담센터 문서가 된다. 장면이 이상한 순간, 채팅이 과열되는 순간에 짧은 반말 리액션을 넣어야 한다.")
    if _score_value(scores, "라이브감") < 65 or _score_value(scores, "채팅_논쟁성") < 65:
        diagnosis.append("- 라이브감/논쟁성 약함: 채팅은 배경음이 아니라 화자의 판단을 흔드는 상대역이다. 찬반 채팅을 받아치며 판단이 보정되는 장면을 만든다.")
    if _score_value(scores, "서사_몰입도") < 70:
        diagnosis.append("- 서사 몰입도 낮음: 사건 요약을 끊고, 60~90초마다 새 정보나 반대 해석을 열어 시청자의 판단을 흔든다.")
    if _score_value(scores, "상담성") < 70:
        diagnosis.append("- 상담성 낮음: 위로나 총평이 아니라 사연자가 실제로 보낼 문장, 상대가 회피/역공/사과할 때의 다음 말을 써야 한다.")
    if _score_value(scores, "후킹_강도") < 65:
        diagnosis.append("- 후킹 약함: 인사와 주제 소개를 버리고, 첫 문장부터 사건의 폭탄과 책임 갈림을 보여준다.")
    if _score_value(scores, "민감주제_처리") < 70:
        diagnosis.append("- 민감 주제 처리 약함: 정체성이나 사생활을 평가하지 말고, 행동/동의/공개 범위/2차 피해 방지로 분리해 말한다.")
    if _score_value(scores, "대본_분량") < 78 or _score_value(scores, "타임코드_구조") < 72:
        diagnosis.append("- 분량/구조 부족: 화자의 숨과 장면이 들어갈 공간이 없다. 11개 이상 타임코드마다 장면, 채팅, 패턴 읽기, 실제 상담 문장을 길게 펼친다.")
    if _score_value(scores, "체화형_도입") < 60:
        diagnosis.append("- 체화형 도입 낮음: 사연을 설명하기 전에 화자의 개인적 경험, 반복된 신호, 몸에 남은 감각으로 공기를 먼저 입혀야 한다.")
    if _score_value(scores, "성향궁합_인사이트") < 60:
        diagnosis.append("- 성향/궁합 인사이트 낮음: MBTI나 사주를 딱지처럼 붙이지 말고, 감정 처리 속도·표현 방식·궁합의 온도 차이를 은근히 상담에 붙여야 한다.")
    if _score_value(scores, "후킹장치_밀도") < 65:
        diagnosis.append("- 후킹 장치 밀도 낮음: 첫 5초 결과/논쟁, 첫 30초 시청 계약, 타임코드별 리훅이 부족하다.")
    if _score_value(scores, "리텐션_루프") < 65:
        diagnosis.append("- 리텐션 루프 낮음: 궁금증을 열고 회수하는 구조가 약하다. 오픈루프 3개와 회수 3개를 명시적으로 심어야 한다.")
    if int(metrics.get("low_value_cta_markers", 0) or 0) >= 1:
        diagnosis.append("- 저품질 CTA 감지: 채팅창에 써달라는 요청을 지우고, 찬반이 갈리는 실제 질문과 화자의 반응으로 바꿔야 한다.")
    if int(metrics.get("generic_outro_markers", 0) or 0) >= 2:
        diagnosis.append("- 빈 마무리 감지: 후반부가 종료 멘트로 분량을 채우고 있다. 새 정보, 판단 변화, 상대 반응별 대응으로 다시 채운다.")
    if int(metrics.get("intimacy_topic_markers", 0) or 0) >= 1 and int(metrics.get("boundary_advice_markers", 0) or 0) < 3:
        diagnosis.append("- 친밀관계 민감 처리 부족: 동의, 촬영/저장 가능성, 프라이버시, 중단 기준, 삭제 요구 문장을 중심으로 다시 써야 한다.")

    if metrics:
        metric_lines = []
        for label, key in [
            ("현재 글자 수", "length"),
            ("타임코드 수", "timecodes"),
            ("채팅 충돌 표식", "chat_collision_markers"),
            ("현실 상담 표식", "exact_advice_markers"),
            ("사주/점성술 표식", "astro_markers"),
            ("체화형 도입 표식", "embodied_markers"),
            ("반복 상징 표식", "symbolic_motif_markers"),
            ("성향/궁합 인사이트 표식", "profile_insight_markers"),
            ("후킹 장치 표식", "hook_device_markers"),
            ("오픈루프 표식", "open_loop_markers"),
            ("회수 표식", "payoff_markers"),
            ("패턴 인터럽트 표식", "pattern_interrupt_markers"),
            ("저품질 CTA", "low_value_cta_markers"),
            ("빈 마무리", "generic_outro_markers"),
            ("친밀관계 경계 문장", "boundary_advice_markers"),
            ("AI식 문장", "forbidden_ai_phrases"),
        ]:
            if key in metrics:
                metric_lines.append(f"- {label}: {metrics.get(key)}")
        if metric_lines:
            diagnosis.append("[숫자가 말하는 결핍]\n" + "\n".join(metric_lines))

    if diagnosis:
        parts.append("[대본이 페르소나를 놓친 방식]\n" + "\n".join(diagnosis))

    parts.append(
        "[재작성 순서]\n"
        "- 1단계: 화자의 개인 경험이나 몸의 감각으로 사연의 공기를 먼저 입힌다.\n"
        "- 2단계: 반복 상징을 세운다. 처음엔 일상 신호, 중간엔 관계 패턴, 후반엔 사회적 공기로 확장한다.\n"
        "- 3단계: 첫 5초 cue와 첫 30초 시청 계약을 새로 쓴다.\n"
        "- 4단계: 사연자 편/상대 편/채팅 반론을 나눠 판단이 흔들리는 구조를 만든다.\n"
        "- 5단계: MBTI식 성향과 사주·궁합 렌즈를 단정 없이 상담 문장에 스며들게 한다.\n"
        "- 6단계: 매 타임코드 첫 문장에 리훅을 넣고, 오픈루프를 열었다면 반드시 회수한다.\n"
        "- 7단계: 마지막에는 사연자가 실제로 말할 문장과 댓글에서 갈릴 질문으로 닫는다."
    )
    return "\n\n".join(parts).strip()


def build_rewrite_brief(
    quality: dict,
    analysis: Optional[dict] = None,
    row: Optional[dict] = None,
) -> str:
    scores = quality.get("scores", {}) or {}
    low_scores = sorted(scores.items(), key=_sort_score_item)[:5]
    parts: list[str] = [build_persona_rewrite_diagnostic(quality, analysis=analysis, row=row)]
    if quality.get("critical_failures"):
        parts.append("[치명 실패]\n" + "\n".join(f"- {x}" for x in quality.get("critical_failures", [])))
    if low_scores:
        parts.append("[낮은 점수]\n" + "\n".join(f"- {k}: {v}" for k, v in low_scores))
    if quality.get("warnings"):
        parts.append("[경고]\n" + "\n".join(f"- {x}" for x in quality.get("warnings", [])))
    if quality.get("rewrite_guidance"):
        parts.append("[재작성 지시]\n" + "\n".join(f"- {x}" for x in quality.get("rewrite_guidance", [])))
    return "\n\n".join(parts).strip()


def improve_failed_script(
    source_text: str,
    analysis: dict,
    blueprint: dict,
    current_script: str,
    quality: dict,
    row: dict,
    model: str,
    temperature: float,
    improvement_mode: str = "품질검사 기준 통과용 전면 재작성",
    user_direction: str = "",
) -> tuple[str, Optional[str]]:
    """Rewrite a failed script using quality-check diagnostics and optional user direction."""
    if not current_script:
        return "", "개선할 기존 대본이 없습니다."

    brief = build_rewrite_brief(quality, analysis=analysis, row=row)
    system = f"""너는 유튜브 라이브 사연 상담 대본의 재작성 전문 작가다.
기존 대본이 품질검사를 통과하지 못했다. 아래 품질검사 리포트와 사용자 디렉션을 반영해 전면 개선한다.

{LIVE_NARRATOR_RULES}
{PERSONA_EMBODIMENT_ENGINE}
{EMBODIED_INSIGHT_ENGINE}
{VIRAL_RETENTION_ENGINE}
{INTIMACY_BOUNDARY_ENGINE}
{STYLE_REFERENCE_BLOCK}
{STORY_IMMERSION_ENGINE}
{LIVE_SCRIPT_CONTRACT}
{localization_prompt()}
{IMPROVEMENT_RULES}
{DIRECTION_GUIDE}

재작성 절대 조건:
- 기존 대본을 문장 몇 개만 수정하지 말고, 실패 원인을 해결하도록 다시 쓴다.
- 총 8,500자 이상, 권장 9,000~11,000자.
- 타임코드 11개 이상. 타임코드 줄은 00:00 형식만 쓴다.
- 각 타임코드마다 실제 방송 멘트를 길게 작성한다. 요약/목차 금지.
- 품질검사 리포트의 critical_failures는 반드시 해결한다.
- 사용자 디렉션이 있으면 반드시 눈에 보이게 반영한다.
- 재작성 브리프의 페르소나를 먼저 체화하고, 그 화자가 실제 라이브에서 말할 수 없는 문장은 버린다.
- 개인 경험형 도입과 반복 상징을 넣는다. "나도 그런 날이 있었어"에서 멈추지 말고 감각 디테일이 있어야 한다.
- MBTI/사주 궁합/오행 인사이트를 은근히 넣되, 확정 진단·예언처럼 말하지 않는다.
- 첫 5초는 결과/논쟁/책임 갈림으로 시작한다. 첫 30초 안에는 끝까지 봐야 하는 이유를 만든다.
- 매 타임코드 첫 문장에 리훅을 넣고, 오픈루프 3개 이상과 회수 3개 이상을 설계한다.
- 친밀관계/기기/프라이버시 사연이면 몸 평가나 노출 적응 조언을 버리고, 동의/촬영 가능성/저장 여부/삭제 요구/중단 기준을 실제 문장으로 넣는다.
- "채팅창에 써보세요", "화이팅", "다음에 또 만나요" 같은 저품질 CTA와 빈 마무리는 삭제한다.
- 서사 몰입도, 채팅 논쟁성, 상담성 점수가 낮으면 해당 항목을 구조적으로 보강한다.
- 각 구간은 장면 재구성, 화자 리액션, 채팅 충돌, 사주/점성술 패턴 읽기, 현실 상담 문장 중 최소 4개 이상을 포함한다.
- AI식 일반 멘트 금지: 안녕하세요 여러분, 함께 고민해볼까요, 다양한 시각이 있네요, 깊은 대화를 나눠보세요.
- 반환은 개선된 대본 텍스트만. JSON 금지."""

    user = {
        "title": row.get("title"),
        "source_text_for_context_only": clean_text(source_text, 16000),
        "analysis": analysis,
        "blueprint": blueprint,
        "current_script": clean_text(current_script, 18000),
        "quality_report": compact_quality_report(quality),
        "rewrite_brief": brief,
        "persona_first_instruction": "대본을 쓰기 전에 32~38세 한국 여성 라이브 상담 유튜버의 입장에서 이 사연을 어떻게 받아칠지 먼저 내면화하라. 화자의 개인 경험형 도입과 반복 상징, 은근한 MBTI/사주 궁합 인사이트, 첫 5초 cue, 첫 30초 시청 계약, 오픈루프와 회수를 설계하되 출력에는 분석 메모를 남기지 말고 체화된 말투만 남겨라.",
        "user_direction": user_direction.strip(),
        "improvement_mode": improvement_mode,
        "mission": "품질검사 통과를 목표로 대본을 전면 개선하라. 특히 후킹, 서사 몰입도, 채팅 논쟁성, 라이브감, 상담성, 캐릭터성, 로컬라이징, 타임코드 밀도를 강화하라. 사용자가 준 디렉션이 있으면 최우선으로 반영하라.",
        "repair_contract": {
            "minimum_total_chars": 8500,
            "minimum_timecodes": 11,
            "required_chat_collisions": 5,
            "required_exact_advice_sentences": 4,
            "required_embodied_personal_anchor": 1,
            "required_implicit_profile_insights": 3,
            "required_open_loops": 3,
            "required_loop_payoffs": 3,
            "required_micro_hooks_per_timecode": True,
            "required_boundary_or_privacy_checks_when_relevant": 4,
            "forbidden_output": ["목차", "제작 메모", "분석 라벨", "요약형 비트"],
        },
    }
    raw, error = openai_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        model=model,
        temperature=max(0.55, min(temperature, 0.95)),
        max_tokens=12000,
    )
    return raw or "", error


def generate_directed_addition(
    source_text: str,
    analysis: dict,
    blueprint: dict,
    current_script: str,
    quality: dict,
    row: dict,
    model: str,
    temperature: float,
    user_direction: str,
    target_section: str = "부족한 구간 자동 판단",
    target_length: str = "1,500~2,500자",
) -> tuple[str, Optional[str]]:
    """Generate an additive block that can be appended or inserted by the user."""
    if not current_script:
        return "", "추가 생성의 기준이 될 기존 대본이 없습니다."
    if not user_direction.strip():
        return "", "추가 생성할 디렉션을 입력해주세요."

    brief = build_rewrite_brief(quality, analysis=analysis, row=row)
    system = f"""너는 유튜브 라이브 사연 상담 대본의 추가 블록을 만드는 작가다.
기존 대본이 품질검사를 통과하지 못했거나 사용자가 더 보강하고 싶어 한다.
사용자 디렉션에 맞춰 기존 대본에 붙일 수 있는 추가 방송 멘트 블록을 생성한다.

{LIVE_NARRATOR_RULES}
{PERSONA_EMBODIMENT_ENGINE}
{EMBODIED_INSIGHT_ENGINE}
{VIRAL_RETENTION_ENGINE}
{INTIMACY_BOUNDARY_ENGINE}
{STYLE_REFERENCE_BLOCK}
{STORY_IMMERSION_ENGINE}
{LIVE_SCRIPT_CONTRACT}
{localization_prompt()}
{IMPROVEMENT_RULES}
{DIRECTION_GUIDE}

추가 생성 절대 조건:
- 기존 대본 전체를 다시 쓰지 않는다.
- 사용자가 지정한 보강 방향에 맞는 추가 구간만 만든다.
- 재작성 브리프의 화자 페르소나를 먼저 체화한다. 추가 블록만 따로 튀는 문어체가 되면 실패다.
- 부족한 부분이 체화/인사이트라면 화자의 개인 경험, 반복 상징, MBTI식 성향/사주 궁합 렌즈를 한 블록 안에 자연스럽게 넣는다.
- 부족한 부분이 후킹/몰입이라면 해당 추가 블록 자체도 첫 문장에 마이크로 후킹, 중간에 패턴 인터럽트, 끝에 다음 궁금증을 넣는다.
- 부족한 부분이 민감한 친밀관계 처리라면 동의/촬영 가능성/프라이버시/중단 기준/삭제 요구 문장을 넣는다.
- 타임코드를 포함한다. 예: 04:20 추가 / 06:50 보강 / 09:10 보강.
- 기존 대본에 자연스럽게 삽입될 수 있게 시작과 끝을 연결형 멘트로 쓴다.
- 추상 조언 금지. 디테일한 방송 멘트와 실제 상담 문장을 넣는다.
- 보강 블록 안에도 장면, 채팅 충돌, 판단 변화, 실제 상담 문장 중 최소 3개 이상을 넣는다.
- 반환은 추가 생성 블록 텍스트만. JSON 금지."""

    user = {
        "title": row.get("title"),
        "source_text_for_context_only": clean_text(source_text, 16000),
        "analysis": analysis,
        "blueprint": blueprint,
        "current_script": clean_text(current_script, 18000),
        "quality_report": compact_quality_report(quality),
        "rewrite_brief": brief,
        "persona_first_instruction": "추가 블록도 같은 32~38세 한국 여성 라이브 상담 유튜버가 이어서 말하는 것처럼 써라. 필요하면 개인 경험형 감각, MBTI/사주 궁합 인사이트, 리훅과 오픈루프 회수를 은근히 보강하라.",
        "user_direction": user_direction.strip(),
        "target_section": target_section,
        "target_length": target_length,
        "mission": "기존 대본에서 부족한 부분을 보강하는 추가 방송 멘트 블록을 만든다. 사용자의 디렉션을 최우선 반영한다.",
    }
    raw, error = openai_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        model=model,
        temperature=max(0.55, min(temperature, 1.0)),
        max_tokens=5000,
    )
    return raw or "", error


def merge_addition(current_script: str, addition: str, mode: str = "append") -> str:
    if not current_script:
        return addition
    if not addition:
        return current_script
    if mode == "prepend":
        return addition.strip() + "\n\n" + current_script.strip()
    return current_script.strip() + "\n\n" + addition.strip()
