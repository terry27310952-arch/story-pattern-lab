from __future__ import annotations

import re
from statistics import mean


FORBIDDEN_AI_PHRASES = [
    "안녕하세요 여러분",
    "함께 고민해보면 좋을 것 같아요",
    "그럼 시작해볼까요",
    "정말 서운하셨겠어요",
    "정말 다양한 시각이 있는 것 같아요",
    "댓글로 여러분의 의견을 한번 남겨주세요",
    "서로의 감정을 존중",
    "솔직하게 감정을 표현",
    "깊은 대화를 나눠보세요",
    "관계를 개선할 수 있는 시작",
    "오늘도 함께해 주셔서 감사",
    "다음 시간에도",
]

TEMPLATE_LEAK_PHRASES = [
    "기념일에 기대하는 기운",
    "양자리라면",
    "물고기자리라면",
    "별자리가 어떤지 모르겠지만",
    "상상해보아요",
]

DIRECT_FORTUNE_ABSOLUTES = [
    "무조건 악연",
    "운명입니다",
    "반드시 헤어",
    "100%",
    "절대적으로",
    "평생 안 맞",
    "타고난 팔자가",
]

LIVE_CHAT_PATTERNS = [
    "채팅", "댓글", "도배", "올라오", "갈리", "지금 보니까", "여러분들", "얘들아", "저기요"
]

CASUAL_REACTION_PATTERNS = [
    "아니", "야", "잠깐만", "뭐야", "이건 좀", "아 이거", "미치겠네", "맞잖아", "그니까", "얘들아", "하지 마세요", "하지마"
]

POLITE_PATTERNS = ["요", "습니다", "세요", "합니다", "했어요", "거예요", "볼게요", "드릴게요", "같아요"]

ADVICE_PATTERNS = [
    "해야", "하지 마", "하지마", "물어보", "확인", "거리", "정리", "조언", "대답보다", "태도", "말하세요", "여기까지만", "경계", "사과", "해명", "관리자", "비공개", "다시는", "상대가", "반응하면",
]

CONCRETE_ADVICE_PATTERNS = [
    "이렇게 말", "라고 말", "여기까지만", "상대가", "나오면", "반응하면", "그때는", "첫 번째", "두 번째", "세 번째", "관리자에게", "직접", "비공개로",
]

ASTRO_PATTERNS = ["사주", "점성술", "궁합", "기운", "작두", "타이밍", "운의 흐름", "리듬", "별", "예언", "월식", "비밀의 자리", "숨겨진", "사회적 얼굴"]

NARRATOR_PATTERNS = ["제가 보기", "저는", "제가", "나는", "내가", "제 기준", "저 같으면", "제가 작두"]

HOOK_CONFLICT_PATTERNS = [
    "문제", "잘못", "책임", "갈린", "아웃", "상처", "무시", "숨겨", "드러", "농담", "비밀", "죄책감", "피해", "불편", "논란",
]

SENSITIVE_SAFETY_PATTERNS = [
    "단정하면 안", "정체성", "아웃팅", "사생활", "2차", "피해 확산", "함부로", "비공개", "조심", "민감",
]


def count_any(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def timecode_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^\s*(\d{1,2}:\d{2})\s*$", text))
    if not matches:
        return []
    sections: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((match.group(1), text[start:end].strip()))
    return sections


def ratio_score(value: float, target: float, floor: float = 0.0) -> int:
    if value <= floor:
        return 0
    return clamp_score((value - floor) / (target - floor) * 100)


def section_score(sections: list[tuple[str, str]]) -> tuple[int, dict]:
    if not sections:
        return 0, {"section_count": 0, "avg_section_length": 0, "short_sections": 0}
    lengths = [len(section) for _, section in sections]
    short_sections = sum(1 for length in lengths if length < 450)
    very_short_sections = sum(1 for length in lengths if length < 300)

    count_part = ratio_score(len(sections), 10, 5)
    avg_part = ratio_score(mean(lengths), 650, 250)
    short_penalty = min(45, short_sections * 7 + very_short_sections * 10)
    score = clamp_score((count_part * 0.45) + (avg_part * 0.55) - short_penalty)
    return score, {
        "section_count": len(sections),
        "avg_section_length": round(mean(lengths), 1),
        "min_section_length": min(lengths),
        "short_sections_under_450": short_sections,
        "very_short_sections_under_300": very_short_sections,
    }


def hook_score(text: str) -> tuple[int, dict]:
    first_700 = text[:700]
    forbidden = count_any(first_700, ["안녕하세요", "오늘은", "가지고 왔어요", "시작해볼까요"])
    conflict_hits = count_any(first_700, HOOK_CONFLICT_PATTERNS)
    casual_hits = count_any(first_700, ["아니", "잠깐만", "근데", "야", "이건"])
    question_hits = first_700.count("?")
    score = clamp_score(conflict_hits * 16 + casual_hits * 12 + question_hits * 6 - forbidden * 22)
    return score, {
        "first_700_conflict_hits": conflict_hits,
        "first_700_casual_hits": casual_hits,
        "first_700_questions": question_hits,
        "first_700_forbidden_opening_hits": forbidden,
    }


def quality_check_live_script(script: str) -> dict:
    text = script or ""
    length = len(text)
    sections = timecode_sections(text)
    timecodes = len(sections)

    polite = count_any(text, POLITE_PATTERNS)
    casual = count_any(text, CASUAL_REACTION_PATTERNS)
    chat = count_any(text, LIVE_CHAT_PATTERNS)
    advice = count_any(text, ADVICE_PATTERNS)
    concrete_advice = count_any(text, CONCRETE_ADVICE_PATTERNS)
    astro = count_any(text, ASTRO_PATTERNS)
    narrator = count_any(text, NARRATOR_PATTERNS)
    sender = text.count("사연자님")
    viewer = text.count("여러분")
    forbidden_ai = count_any(text, FORBIDDEN_AI_PHRASES)
    template_leak = count_any(text, TEMPLATE_LEAK_PHRASES)
    fortune_absolute = count_any(text, DIRECT_FORTUNE_ABSOLUTES)
    sensitive_safety = count_any(text, SENSITIVE_SAFETY_PATTERNS)

    section_structure_score, section_metrics = section_score(sections)
    opening_score, opening_metrics = hook_score(text)

    length_score = ratio_score(length, 9000, 3000)
    timecode_structure_score = section_structure_score

    polite_part = ratio_score(polite, 120, 30)
    casual_part = ratio_score(casual, 35, 8)
    mixed_bonus = 18 if polite >= 60 and casual >= 18 else 0
    banality_penalty = min(45, forbidden_ai * 10 + template_leak * 18)
    banter_score = clamp_score((polite_part * 0.35) + (casual_part * 0.50) + mixed_bonus - banality_penalty)

    chat_part = ratio_score(chat, 18, 3)
    viewer_part = ratio_score(viewer, 12, 4)
    reactive_part = ratio_score(casual, 30, 6)
    live_score = clamp_score((chat_part * 0.42) + (viewer_part * 0.28) + (reactive_part * 0.30) - forbidden_ai * 7)

    sender_part = ratio_score(sender, 9, 3)
    advice_part = ratio_score(advice, 24, 6)
    concrete_part = ratio_score(concrete_advice, 12, 2)
    safety_bonus = min(15, sensitive_safety * 3)
    counseling_score = clamp_score((sender_part * 0.22) + (advice_part * 0.33) + (concrete_part * 0.35) + safety_bonus - forbidden_ai * 5)

    narrator_part = ratio_score(narrator, 14, 3)
    astro_part = ratio_score(astro, 10, 2)
    too_much_astro_penalty = max(0, astro - 18) * 4
    absolute_penalty = fortune_absolute * 22
    character_score = clamp_score((narrator_part * 0.42) + (astro_part * 0.40) + (opening_score * 0.18) - too_much_astro_penalty - absolute_penalty - template_leak * 15)

    hook_quality_score = opening_score

    sensitive_topic_detected = count_any(text, ["정체성", "아웃", "성", "사생활", "헬스장", "스팀", "폭력", "임신", "장애", "차별"]) > 0
    if sensitive_topic_detected:
        sensitive_score = clamp_score(ratio_score(sensitive_safety, 7, 1) - fortune_absolute * 10)
    else:
        sensitive_score = 100

    scores = {
        "대본_분량": length_score,
        "타임코드_구조": timecode_structure_score,
        "후킹_강도": hook_quality_score,
        "반존대_자연스러움": banter_score,
        "라이브감": live_score,
        "상담성": counseling_score,
        "캐릭터성": character_score,
        "민감주제_처리": sensitive_score,
    }

    weights = {
        "대본_분량": 0.15,
        "타임코드_구조": 0.14,
        "후킹_강도": 0.12,
        "반존대_자연스러움": 0.14,
        "라이브감": 0.13,
        "상담성": 0.15,
        "캐릭터성": 0.12,
        "민감주제_처리": 0.05,
    }
    weighted = sum(scores[name] * weight for name, weight in weights.items())
    hard_penalty = min(35, forbidden_ai * 4 + template_leak * 12 + fortune_absolute * 12)
    overall = clamp_score(weighted - hard_penalty)

    outline_only = length < 3500 or (timecodes >= 6 and length / max(timecodes, 1) < 520)

    critical_failures: list[str] = []
    warnings: list[str] = []
    rewrite_guidance: list[str] = []

    if length < 8000:
        critical_failures.append("분량 부족: 10분 롱폼은 최소 8,000자 이상이어야 합니다.")
        rewrite_guidance.append("롱폼을 3파트로 나눠 각 파트 2,500자 이상 생성하세요.")
    if timecodes < 10:
        critical_failures.append("타임코드 부족: 최소 10개 이상 필요합니다.")
    if section_metrics.get("short_sections_under_450", 0) > 2:
        critical_failures.append("짧은 타임코드 구간이 많습니다. 각 구간을 실제 방송 멘트로 확장해야 합니다.")
    if outline_only:
        critical_failures.append("목차형 출력: 타임코드마다 말이 너무 짧습니다.")
    if opening_score < 60:
        critical_failures.append("후킹 약함: 첫 700자 안에 갈등/책임/논란이 선명하게 들어가야 합니다.")
        rewrite_guidance.append("오프닝 인사 삭제 후 사건 폭탄부터 시작하세요.")
    if banter_score < 65:
        warnings.append("반존대 약함: 존댓말 진행과 반말 리액션의 교차가 부족합니다.")
        rewrite_guidance.append("감정이 튀는 구간에 '아니 잠깐만', '야 이건 좀', '저기요' 류를 자연스럽게 추가하세요.")
    if live_score < 65:
        warnings.append("라이브감 부족: 채팅/댓글을 받아치는 장면이 부족하거나 너무 형식적입니다.")
        rewrite_guidance.append("채팅 의견을 3회 이상 받아치고, 그 의견에 반박/수정/동의하는 멘트를 넣으세요.")
    if counseling_score < 70:
        warnings.append("상담성 부족: 현실 조언이 추상적입니다.")
        rewrite_guidance.append("상대에게 실제로 말할 문장, 상대 반응별 대응, 피해야 할 행동을 구체적으로 제시하세요.")
    if character_score < 65:
        warnings.append("캐릭터성 부족: 사주/점성술 화자의 언어가 사연 구조에 잘 붙지 않았습니다.")
        rewrite_guidance.append("별자리 랜덤 추측 대신 '비밀의 자리', '사회적 얼굴', '기운이 드러난 순간'처럼 사건 구조와 연결하세요.")
    if sensitive_topic_detected and sensitive_score < 70:
        warnings.append("민감 주제 처리 부족: 정체성/사생활/아웃팅/차별 이슈를 더 조심스럽게 다뤄야 합니다.")
        rewrite_guidance.append("정체성 단정 금지, 2차 피해 방지, 비공개 사과, 관리자에게는 행동 기준으로만 말하기를 포함하세요.")
    if forbidden_ai:
        warnings.append(f"AI식 일반 문장 감지: {forbidden_ai}개. 금지 문장류를 제거하세요.")
    if template_leak:
        critical_failures.append(f"템플릿 찌꺼기 감지: {template_leak}개. 이전 사연 문맥이 섞였습니다.")
    if fortune_absolute:
        warnings.append("단정적 점술 표현이 있습니다. 방송식 추측으로 완화하세요.")

    passed = (
        overall >= 82
        and not critical_failures
        and scores["대본_분량"] >= 78
        and scores["타임코드_구조"] >= 72
        and scores["후킹_강도"] >= 65
        and scores["라이브감"] >= 65
        and scores["상담성"] >= 70
        and scores["캐릭터성"] >= 65
    )

    if overall >= 90 and passed:
        grade = "A"
    elif overall >= 82 and not critical_failures:
        grade = "B"
    elif overall >= 70:
        grade = "C"
    elif overall >= 55:
        grade = "D"
    else:
        grade = "F"

    return {
        "overall_score": overall,
        "grade": grade,
        "passed": passed,
        "scores": scores,
        "weights": weights,
        "metrics": {
            "length": length,
            "timecodes": timecodes,
            "polite_markers": polite,
            "casual_markers": casual,
            "chat_markers": chat,
            "viewer_mentions": viewer,
            "advice_markers": advice,
            "concrete_advice_markers": concrete_advice,
            "astro_markers": astro,
            "narrator_markers": narrator,
            "sender_mentions": sender,
            "forbidden_ai_phrases": forbidden_ai,
            "template_leaks": template_leak,
            "fortune_absolutes": fortune_absolute,
            "sensitive_safety_markers": sensitive_safety,
            **section_metrics,
            **opening_metrics,
        },
        "critical_failures": critical_failures,
        "warnings": warnings,
        "rewrite_guidance": rewrite_guidance,
    }
