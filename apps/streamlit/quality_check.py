from __future__ import annotations

import re
from statistics import mean


FORBIDDEN_AI_PHRASES = [
    "안녕하세요 여러분",
    "여러분, 오늘은",
    "오늘은 정말 복잡한 사연",
    "오늘은 많은 분들이",
    "함께 고민해보면 좋을 것 같아요",
    "그럼 시작해볼까요",
    "자, 그럼 같이 살펴보죠",
    "정말 서운하셨겠어요",
    "정말 다양한 시각이 있는 것 같아요",
    "댓글로 여러분의 의견을 한번 남겨주세요",
    "채팅창에 한 번 써보세요",
    "댓글로 이야기해보세요",
    "비슷한 경험 있으신가요",
    "서로의 감정을 존중",
    "솔직하게 감정을 표현",
    "솔직한 대화가 필요",
    "깊은 대화를 나눠보세요",
    "대화는 진짜 중요",
    "관계를 개선할 수 있는 시작",
    "작은 변화부터",
    "많은 걸 느끼고 배울",
    "사연자님, 화이팅",
    "오늘도 함께해 주셔서 감사",
    "궁금한 점이나 고민",
    "다음 시간에도",
    "다음에 또 새로운 사연",
    "안녕히 주무세요",
    "좋은 하루 되세요",
    "기운 좋게 하루를 마무리",
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

LOW_VALUE_CTA_PATTERNS = [
    "채팅창에 한 번 써보세요", "채팅에 적어보세요", "댓글로 이야기해보세요", "댓글로 남겨주세요",
    "공유해주시면 좋겠어요", "화이팅", "응원해주면", "여러분의 생각을 댓글",
]

GENERIC_OUTRO_PATTERNS = [
    "다음에 또", "오늘도 함께", "궁금한 점이나 고민", "서로의 이야기", "더 많은 걸 배울",
    "안녕히 주무세요", "좋은 하루", "하루를 마무리", "다음 방송", "새로운 사연",
]

INTIMACY_TOPIC_PATTERNS = [
    "성관계", "성적인", "몸", "벗은", "나체", "불을 끄", "침대", "관계 중", "친밀한",
    "메타 글라스", "스마트 안경", "안경", "카메라", "촬영", "녹화", "기록", "보여주는",
]

INTIMACY_SAFETY_PATTERNS = [
    "동의", "사전 설명", "허락", "촬영", "녹화", "기록", "저장", "삭제", "프라이버시",
    "경계", "중단", "멈춰", "거절", "불편", "압박", "수치심", "안전", "비공개",
    "확인", "합의", "공개 범위", "민감",
]

BAD_INTIMACY_HANDLING_PATTERNS = [
    "성관계 중에 그를 쫓아낸", "완전히 벗은 모습을", "시각적 자극", "몸에 대한 불안감",
    "관계를 더 깊게", "성적인 경계를 다시 설정", "취향을 공유",
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

EMBODIED_EXPERIENCE_PATTERNS = [
    "나도", "저도", "제가 겪", "내가 겪", "그날", "그때", "하루", "아침", "밤에", "집에 와서",
    "몸으로", "몸에", "눈에 남", "계속 남", "유난히", "이상하게", "찝찝", "공기", "느낌",
]

SYMBOLIC_MOTIF_PATTERNS = [
    "신호", "빨간", "멈춰", "조심", "불씨", "상징", "징조", "흐름", "반복", "계속", "작은 게",
    "커지", "번지", "켜져", "경고", "알림", "문", "계단", "배터리", "색",
]

PROFILE_INSIGHT_PATTERNS = [
    "MBTI", "성향", "타입", "기질", "감정형", "사고형", "직관형", "감각형", "계획형", "즉흥형",
    "회피형", "불안형", "확인형", "표현 방식", "처리 속도", "감정 처리", "감정 확인", "맥락 확인",
    "성격 문제", "관계 리듬", "속도 차이", "온도 차이", "관계 속도",
]

COMPATIBILITY_INSIGHT_PATTERNS = [
    "궁합", "일간", "오행", "대운", "세운", "화기", "수기", "목 기운", "금 기운", "토 기운",
    "온도", "속도", "리듬", "기운이 맞", "기운이 안 맞", "합이", "충돌",
]

INSIGHT_CAUTION_PATTERNS = [
    "단정", "확정", "정답은 아니", "가능성", "처럼 보", "느껴질 수", "쪽에 가까", "모르는 상태",
    "말할 수는 없", "볼 수 있",
]

HOOK_DEVICE_PATTERNS = [
    "결론부터", "먼저 결론", "한 줄로", "딱 하나", "진짜 문제", "문제는", "핵심은",
    "왜냐면", "왜 이게", "이게 왜", "끝까지", "지금부터", "여기서 갈", "댓글 갈",
    "책임", "논쟁", "반전", "폭탄", "선 넘", "말 한마디", "그 다음",
]

OPEN_LOOP_PATTERNS = [
    "뒤에서", "이 뒤", "나중에", "마지막에", "잠시 후", "조금 있다", "아직", "끝이 아니",
    "이 다음", "그 다음", "기다려", "보셔야", "풀립니다", "나옵니다",
]

PAYOFF_PATTERNS = [
    "아까", "초반에", "처음에", "앞에서", "방금", "말했죠", "얘기했죠", "회수", "연결",
    "그래서", "결국", "이게 바로", "여기서 풀",
]

PATTERN_INTERRUPT_PATTERNS = [
    "아니", "잠깐만", "근데", "그런데", "반대로", "오히려", "다시 보면", "여기서",
    "멈춰", "틀렸", "그 말은", "채팅", "댓글", "잠깐",
]

STAKES_PATTERNS = [
    "위험", "손해", "잃", "무너", "커지", "번지", "폭발", "구설", "낙인", "피해",
    "책임", "갈등", "선 넘", "돌아오", "망가",
]

HOOK_CONFLICT_PATTERNS = [
    "문제", "잘못", "책임", "갈린", "아웃", "상처", "무시", "숨겨", "드러", "농담", "비밀", "죄책감", "피해", "불편", "논란",
]

SENSITIVE_SAFETY_PATTERNS = [
    "단정하면 안", "정체성", "아웃팅", "사생활", "2차", "피해 확산", "함부로", "비공개", "조심", "민감",
]

IMMERSION_TURN_PATTERNS = [
    "근데", "그런데", "여기서", "문제는", "더 이상한", "여기서부터", "반대로", "그렇다고", "사실은", "그 순간",
    "이 지점", "판단", "흔들", "걸리는", "불편", "찝찝", "갈리는", "다시 보면", "처음에는", "나중에",
]

SCENE_DETAIL_PATTERNS = [
    "그 자리", "그때", "순간", "장면", "공기", "말투", "표정", "메시지", "카톡", "전화", "대화", "댓글창",
    "사람들 앞", "둘만", "공용", "방송", "글을 보면", "사연을 보면", "상황",
]

CHAT_COLLISION_PATTERNS = [
    "채팅에", "댓글에", "도배", "올라오", "갈리", "반은 맞", "그 말", "잠깐만", "얘들아", "여러분들 지금",
    "그렇게 보면", "아니라는 분", "맞다는 분", "지금 보니까",
]

EXACT_ADVICE_PATTERNS = [
    "이렇게 말", "라고 물어", "라고 말", "이 문장", "첫 문장", "상대가", "회피하면", "역공하면", "사과하면",
    "그때는", "여기까지만", "기준을", "보내세요", "물어보세요",
]

BOUNDARY_ADVICE_PATTERNS = [
    "기기를 벗", "안경을 벗", "촬영되는지", "녹화되는지", "저장되는지", "삭제해",
    "동의 없이", "동의한 적 없", "지금은 멈춰", "여기서 중단", "불편하면 중단",
    "사전에 말", "먼저 확인", "경계를 다시", "허락 없이는", "비공개로",
]

OUTLINE_LEAK_PATTERNS = [
    "이 구간에서는", "핵심 포인트", "요약하자면", "다음 단계", "목표는", "분석:", "상담:", "채팅 반응:",
]


def count_any(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def count_sections_with(sections: list[tuple[str, str]], words: list[str]) -> int:
    return sum(1 for _, section in sections if count_any(section, words) > 0)


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
    short_sections = sum(1 for length in lengths if length < 550)
    old_short_sections = sum(1 for length in lengths if length < 450)
    very_short_sections = sum(1 for length in lengths if length < 400)

    count_part = ratio_score(len(sections), 10, 5)
    avg_part = ratio_score(mean(lengths), 650, 250)
    short_penalty = min(45, short_sections * 7 + very_short_sections * 10)
    score = clamp_score((count_part * 0.45) + (avg_part * 0.55) - short_penalty)
    return score, {
        "section_count": len(sections),
        "avg_section_length": round(mean(lengths), 1),
        "min_section_length": min(lengths),
        "short_sections_under_550": short_sections,
        "short_sections_under_450": old_short_sections,
        "very_short_sections_under_400": very_short_sections,
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
    low_value_cta = count_any(text, LOW_VALUE_CTA_PATTERNS)
    generic_outro = count_any(text, GENERIC_OUTRO_PATTERNS)
    template_leak = count_any(text, TEMPLATE_LEAK_PHRASES)
    fortune_absolute = count_any(text, DIRECT_FORTUNE_ABSOLUTES)
    sensitive_safety = count_any(text, SENSITIVE_SAFETY_PATTERNS)
    immersion_turns = count_any(text, IMMERSION_TURN_PATTERNS)
    scene_details = count_any(text, SCENE_DETAIL_PATTERNS)
    chat_collisions = count_any(text, CHAT_COLLISION_PATTERNS)
    exact_advice = count_any(text, EXACT_ADVICE_PATTERNS)
    embodied = count_any(text, EMBODIED_EXPERIENCE_PATTERNS)
    symbolic_motif = count_any(text, SYMBOLIC_MOTIF_PATTERNS)
    profile_insight = count_any(text, PROFILE_INSIGHT_PATTERNS)
    compatibility_insight = count_any(text, COMPATIBILITY_INSIGHT_PATTERNS)
    insight_caution = count_any(text, INSIGHT_CAUTION_PATTERNS)
    hook_devices = count_any(text, HOOK_DEVICE_PATTERNS)
    open_loops = count_any(text, OPEN_LOOP_PATTERNS)
    payoffs = count_any(text, PAYOFF_PATTERNS)
    pattern_interrupts = count_any(text, PATTERN_INTERRUPT_PATTERNS)
    stakes = count_any(text, STAKES_PATTERNS)
    intimacy_topic = count_any(text, INTIMACY_TOPIC_PATTERNS)
    intimacy_safety = count_any(text, INTIMACY_SAFETY_PATTERNS)
    bad_intimacy_handling = count_any(text, BAD_INTIMACY_HANDLING_PATTERNS)
    boundary_advice = count_any(text, BOUNDARY_ADVICE_PATTERNS)
    outline_leak = count_any(text, OUTLINE_LEAK_PATTERNS)

    section_structure_score, section_metrics = section_score(sections)
    opening_score, opening_metrics = hook_score(text)
    sections_with_turns = count_sections_with(sections, IMMERSION_TURN_PATTERNS)
    sections_with_scenes = count_sections_with(sections, SCENE_DETAIL_PATTERNS)
    sections_with_chat = count_sections_with(sections, CHAT_COLLISION_PATTERNS)
    sections_with_embodied = count_sections_with(sections, EMBODIED_EXPERIENCE_PATTERNS)
    sections_with_profile_insight = count_sections_with(sections, PROFILE_INSIGHT_PATTERNS + COMPATIBILITY_INSIGHT_PATTERNS)
    sections_with_rehook = count_sections_with(sections, HOOK_DEVICE_PATTERNS + OPEN_LOOP_PATTERNS + PATTERN_INTERRUPT_PATTERNS)
    sections_with_open_loop_or_payoff = count_sections_with(sections, OPEN_LOOP_PATTERNS + PAYOFF_PATTERNS)
    sections_with_boundary_advice = count_sections_with(sections, BOUNDARY_ADVICE_PATTERNS)

    length_score = ratio_score(length, 9000, 3000)
    timecode_structure_score = section_structure_score

    polite_part = ratio_score(polite, 120, 30)
    casual_part = ratio_score(casual, 35, 8)
    mixed_bonus = 18 if polite >= 60 and casual >= 18 else 0
    banality_penalty = min(55, forbidden_ai * 10 + low_value_cta * 8 + generic_outro * 8 + template_leak * 18)
    banter_score = clamp_score((polite_part * 0.35) + (casual_part * 0.50) + mixed_bonus - banality_penalty)

    chat_part = ratio_score(chat, 18, 3)
    viewer_part = ratio_score(viewer, 12, 4)
    reactive_part = ratio_score(casual, 30, 6)
    live_score = clamp_score((chat_part * 0.42) + (viewer_part * 0.28) + (reactive_part * 0.30) - forbidden_ai * 7 - low_value_cta * 8)

    turn_part = ratio_score(sections_with_turns, 8, 2)
    scene_part = ratio_score(sections_with_scenes, 8, 2)
    curiosity_part = ratio_score(immersion_turns, 28, 6)
    filler_penalty = min(35, generic_outro * 7 + low_value_cta * 6)
    immersion_score = clamp_score((turn_part * 0.36) + (scene_part * 0.34) + (curiosity_part * 0.30) - outline_leak * 18 - filler_penalty)

    chat_collision_part = ratio_score(chat_collisions, 10, 2)
    chat_section_part = ratio_score(sections_with_chat, 5, 1)
    debate_design_score = clamp_score((chat_collision_part * 0.56) + (chat_section_part * 0.44) - forbidden_ai * 5 - low_value_cta * 10)

    sender_part = ratio_score(sender, 9, 3)
    advice_part = ratio_score(advice, 24, 6)
    concrete_part = ratio_score(concrete_advice, 12, 2)
    exact_advice_part = ratio_score(exact_advice, 9, 2)
    safety_bonus = min(15, sensitive_safety * 3)
    boundary_part = ratio_score(boundary_advice, 7, 1)
    counseling_score = clamp_score((sender_part * 0.14) + (advice_part * 0.20) + (concrete_part * 0.24) + (exact_advice_part * 0.18) + (boundary_part * 0.14) + safety_bonus - forbidden_ai * 5 - low_value_cta * 5)

    narrator_part = ratio_score(narrator, 14, 3)
    astro_part = ratio_score(astro, 10, 2)
    too_much_astro_penalty = max(0, astro - 18) * 4
    absolute_penalty = fortune_absolute * 22
    character_score = clamp_score((narrator_part * 0.42) + (astro_part * 0.40) + (opening_score * 0.18) - too_much_astro_penalty - absolute_penalty - template_leak * 15)

    first_1800 = text[:1800]
    opening_embodied = count_any(first_1800, EMBODIED_EXPERIENCE_PATTERNS)
    opening_symbolic = count_any(first_1800, SYMBOLIC_MOTIF_PATTERNS)
    embodied_score = clamp_score(
        (ratio_score(opening_embodied, 8, 1) * 0.45)
        + (ratio_score(symbolic_motif, 14, 2) * 0.25)
        + (ratio_score(sections_with_embodied, 4, 1) * 0.20)
        + (ratio_score(opening_symbolic, 5, 1) * 0.10)
        - outline_leak * 8
    )
    profile_insight_score = clamp_score(
        (ratio_score(profile_insight, 5, 1) * 0.30)
        + (ratio_score(compatibility_insight, 5, 1) * 0.32)
        + (ratio_score(sections_with_profile_insight, 3, 1) * 0.20)
        + (ratio_score(insight_caution, 3, 1) * 0.18)
        - fortune_absolute * 14
    )

    hook_quality_score = opening_score
    first_700 = text[:700]
    first_700_hook_devices = count_any(first_700, HOOK_DEVICE_PATTERNS)
    first_700_open_loops = count_any(first_700, OPEN_LOOP_PATTERNS)
    first_700_stakes = count_any(first_700, STAKES_PATTERNS)
    first_1800_pattern_interrupts = count_any(first_1800, PATTERN_INTERRUPT_PATTERNS)
    hook_device_density_score = clamp_score(
        (ratio_score(first_700_hook_devices, 5, 1) * 0.30)
        + (ratio_score(first_700_open_loops, 2, 0) * 0.18)
        + (ratio_score(first_700_stakes, 4, 1) * 0.20)
        + (ratio_score(hook_devices, 24, 5) * 0.18)
        + (ratio_score(first_1800_pattern_interrupts, 8, 2) * 0.14)
        - forbidden_ai * 8
    )
    retention_loop_score = clamp_score(
        (ratio_score(sections_with_rehook, 9, 3) * 0.32)
        + (ratio_score(open_loops, 8, 2) * 0.22)
        + (ratio_score(payoffs, 6, 1) * 0.18)
        + (ratio_score(sections_with_open_loop_or_payoff, 6, 2) * 0.16)
        + (ratio_score(pattern_interrupts, 28, 8) * 0.12)
        - outline_leak * 10
    )

    sensitive_topic_detected = count_any(text, ["정체성", "아웃", "성", "사생활", "헬스장", "스팀", "폭력", "임신", "장애", "차별"]) > 0 or intimacy_topic > 0
    if sensitive_topic_detected:
        sensitive_score = clamp_score(
            (ratio_score(sensitive_safety + intimacy_safety, 11, 2) * 0.45)
            + (ratio_score(boundary_advice, 7, 1) * 0.35)
            + (ratio_score(sections_with_boundary_advice, 3, 1) * 0.20)
            - fortune_absolute * 10
            - bad_intimacy_handling * 12
        )
    else:
        sensitive_score = 100

    scores = {
        "대본_분량": length_score,
        "타임코드_구조": timecode_structure_score,
        "후킹_강도": hook_quality_score,
        "서사_몰입도": immersion_score,
        "채팅_논쟁성": debate_design_score,
        "반존대_자연스러움": banter_score,
        "라이브감": live_score,
        "상담성": counseling_score,
        "캐릭터성": character_score,
        "체화형_도입": embodied_score,
        "성향궁합_인사이트": profile_insight_score,
        "후킹장치_밀도": hook_device_density_score,
        "리텐션_루프": retention_loop_score,
        "민감주제_처리": sensitive_score,
    }

    weights = {
        "대본_분량": 0.08,
        "타임코드_구조": 0.08,
        "후킹_강도": 0.08,
        "서사_몰입도": 0.10,
        "채팅_논쟁성": 0.08,
        "반존대_자연스러움": 0.07,
        "라이브감": 0.07,
        "상담성": 0.09,
        "캐릭터성": 0.07,
        "체화형_도입": 0.06,
        "성향궁합_인사이트": 0.04,
        "후킹장치_밀도": 0.08,
        "리텐션_루프": 0.08,
        "민감주제_처리": 0.02,
    }
    weighted = sum(scores[name] * weight for name, weight in weights.items())
    hard_penalty = min(55, forbidden_ai * 4 + low_value_cta * 6 + generic_outro * 6 + template_leak * 12 + fortune_absolute * 12 + outline_leak * 10 + bad_intimacy_handling * 8)
    overall = clamp_score(weighted - hard_penalty)

    outline_only = length < 3500 or (timecodes >= 6 and length / max(timecodes, 1) < 520)

    critical_failures: list[str] = []
    warnings: list[str] = []
    rewrite_guidance: list[str] = []

    if length < 8500:
        critical_failures.append("분량 부족: 10분 롱폼은 최소 8,500자 이상이어야 합니다.")
        rewrite_guidance.append("롱폼을 11개 타임코드로 나눠 각 구간 650자 이상 생성하세요.")
    if timecodes < 11:
        critical_failures.append("타임코드 부족: 최소 11개 이상 필요합니다.")
    if section_metrics.get("short_sections_under_550", 0) > 2:
        critical_failures.append("짧은 타임코드 구간이 많습니다. 각 구간을 실제 방송 멘트로 확장해야 합니다.")
    if outline_only:
        critical_failures.append("목차형 출력: 타임코드마다 말이 너무 짧습니다.")
    if low_value_cta >= 2:
        critical_failures.append("저품질 채팅 유도: 채팅/댓글 요청이 실제 논쟁을 만들지 못하고 응원/반응 구걸처럼 보입니다.")
        rewrite_guidance.append("채팅 유도 대신 찬반이 갈리는 실제 질문과 화자의 즉시 반박/보정을 넣으세요.")
    if generic_outro >= 3:
        critical_failures.append("후반부 빈말 반복: 방송 종료/감사/다음 사연 멘트가 분량을 채우고 있습니다.")
        rewrite_guidance.append("05:30 이후에도 새 정보, 판단 변화, 상대 반응별 대응, 오픈루프 회수를 넣으세요.")
    if intimacy_topic and (intimacy_safety < 5 or boundary_advice < 3):
        critical_failures.append("친밀관계 민감 사연 처리 실패: 동의, 촬영/녹화 가능성, 기기 사용, 프라이버시, 중단 기준을 충분히 다루지 않았습니다.")
        rewrite_guidance.append("몸 평가나 성적 디테일보다 '기기 착용 동의 여부, 촬영/저장 여부 확인, 즉시 중단할 기준, 삭제/확인 문장'을 중심으로 재작성하세요.")
    if opening_score < 60:
        critical_failures.append("후킹 약함: 첫 700자 안에 갈등/책임/논란이 선명하게 들어가야 합니다.")
        rewrite_guidance.append("오프닝 인사 삭제 후 사건 폭탄부터 시작하세요.")
    if banter_score < 65:
        warnings.append("반존대 약함: 존댓말 진행과 반말 리액션의 교차가 부족합니다.")
        rewrite_guidance.append("감정이 튀는 구간에 '아니 잠깐만', '야 이건 좀', '저기요' 류를 자연스럽게 추가하세요.")
    if live_score < 65:
        warnings.append("라이브감 부족: 채팅/댓글을 받아치는 장면이 부족하거나 너무 형식적입니다.")
        rewrite_guidance.append("채팅 의견을 3회 이상 받아치고, 그 의견에 반박/수정/동의하는 멘트를 넣으세요.")
    if immersion_score < 70:
        warnings.append("서사 몰입도 부족: 구간마다 새 정보, 판단 변화, 장면 디테일이 충분히 열리지 않았습니다.")
        rewrite_guidance.append("각 타임코드에 장면 재구성 → 화자 리액션 → 반대 해석 → 다음 궁금증을 넣어 판단이 흔들리게 만드세요.")
    if debate_design_score < 65:
        warnings.append("채팅 논쟁성 부족: 찬반이 갈리는 실제 라이브 충돌이 약합니다.")
        rewrite_guidance.append("채팅에 올라온 반대 의견을 5회 이상 받아치고, '반은 맞고 반은 위험하다'처럼 판단을 보정하는 멘트를 넣으세요.")
    if counseling_score < 70:
        warnings.append("상담성 부족: 현실 조언이 추상적입니다.")
        rewrite_guidance.append("상대에게 실제로 말할 문장, 상대 반응별 대응, 피해야 할 행동을 구체적으로 제시하세요.")
    if character_score < 65:
        warnings.append("캐릭터성 부족: 사주/점성술 화자의 언어가 사연 구조에 잘 붙지 않았습니다.")
        rewrite_guidance.append("별자리 랜덤 추측 대신 '비밀의 자리', '사회적 얼굴', '기운이 드러난 순간'처럼 사건 구조와 연결하세요.")
    if embodied_score < 60:
        warnings.append("체화형 도입 부족: 화자의 개인 경험, 몸의 감각, 반복 상징이 약합니다.")
        rewrite_guidance.append("사연 요약 전에 개인적 하루의 작은 신호를 3개 이상 보여주고, 그 상징을 관계 패턴으로 확장하세요.")
    if profile_insight_score < 60:
        warnings.append("성향/궁합 인사이트 부족: 내담자의 MBTI식 성향, 사주 궁합, 오행 렌즈가 은근히 녹지 않았습니다.")
        rewrite_guidance.append("확정 진단을 피하면서 감정 처리 속도, 표현 방식, 궁합의 온도 차이를 실제 상담 문장으로 연결하세요.")
    if hook_device_density_score < 65:
        warnings.append("후킹 장치 부족: 첫 5초/첫 30초에 결과, 논쟁, 시청 계약, 책임 갈림이 충분히 박히지 않았습니다.")
        rewrite_guidance.append("첫 700자 안에 결과 먼저 제시, 논쟁 질문, 뒤에 남은 반전, 끝까지 봐야 하는 이유를 넣으세요.")
    if retention_loop_score < 65:
        warnings.append("리텐션 루프 부족: 구간마다 다음을 보게 만드는 오픈루프와 회수가 약합니다.")
        rewrite_guidance.append("각 타임코드 첫 문장에 리훅을 넣고, 오픈루프 3개 이상과 그 회수 문장 3개 이상을 배치하세요.")
    if sensitive_topic_detected and sensitive_score < 70:
        warnings.append("민감 주제 처리 부족: 정체성/사생활/아웃팅/차별 이슈를 더 조심스럽게 다뤄야 합니다.")
        rewrite_guidance.append("정체성 단정 금지, 2차 피해 방지, 비공개 사과, 관리자에게는 행동 기준으로만 말하기를 포함하세요.")
    if forbidden_ai:
        warnings.append(f"AI식 일반 문장 감지: {forbidden_ai}개. 금지 문장류를 제거하세요.")
    if low_value_cta:
        warnings.append(f"저품질 채팅/댓글 유도 감지: {low_value_cta}개. 참여 요청을 실제 논쟁 질문으로 바꾸세요.")
    if generic_outro:
        warnings.append(f"빈 마무리 멘트 감지: {generic_outro}개. 후반부를 새 정보와 상담 대응으로 채우세요.")
    if bad_intimacy_handling:
        warnings.append("친밀관계 사연에서 자극적이거나 초점이 흐린 표현이 있습니다. 동의와 프라이버시 중심으로 바꾸세요.")
    if template_leak:
        critical_failures.append(f"템플릿 찌꺼기 감지: {template_leak}개. 이전 사연 문맥이 섞였습니다.")
    if fortune_absolute:
        warnings.append("단정적 점술 표현이 있습니다. 방송식 추측으로 완화하세요.")
    if outline_leak:
        critical_failures.append(f"제작 메모/목차형 표현 감지: {outline_leak}개. 최종 대본에는 실제 방송 멘트만 남겨야 합니다.")

    passed = (
        overall >= 82
        and not critical_failures
        and scores["대본_분량"] >= 78
        and scores["타임코드_구조"] >= 72
        and scores["후킹_강도"] >= 65
        and scores["서사_몰입도"] >= 70
        and scores["채팅_논쟁성"] >= 65
        and scores["라이브감"] >= 65
        and scores["상담성"] >= 70
        and scores["캐릭터성"] >= 65
        and scores["체화형_도입"] >= 60
        and scores["성향궁합_인사이트"] >= 60
        and scores["후킹장치_밀도"] >= 65
        and scores["리텐션_루프"] >= 65
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
            "embodied_markers": embodied,
            "symbolic_motif_markers": symbolic_motif,
            "profile_insight_markers": profile_insight,
            "compatibility_insight_markers": compatibility_insight,
            "insight_caution_markers": insight_caution,
            "hook_device_markers": hook_devices,
            "open_loop_markers": open_loops,
            "payoff_markers": payoffs,
            "pattern_interrupt_markers": pattern_interrupts,
            "stakes_markers": stakes,
            "sender_mentions": sender,
            "forbidden_ai_phrases": forbidden_ai,
            "low_value_cta_markers": low_value_cta,
            "generic_outro_markers": generic_outro,
            "template_leaks": template_leak,
            "fortune_absolutes": fortune_absolute,
            "intimacy_topic_markers": intimacy_topic,
            "intimacy_safety_markers": intimacy_safety,
            "bad_intimacy_handling_markers": bad_intimacy_handling,
            "boundary_advice_markers": boundary_advice,
            "sensitive_safety_markers": sensitive_safety,
            "immersion_turn_markers": immersion_turns,
            "scene_detail_markers": scene_details,
            "chat_collision_markers": chat_collisions,
            "exact_advice_markers": exact_advice,
            "outline_leak_markers": outline_leak,
            "sections_with_turns": sections_with_turns,
            "sections_with_scenes": sections_with_scenes,
            "sections_with_chat_collision": sections_with_chat,
            "sections_with_embodied": sections_with_embodied,
            "sections_with_profile_insight": sections_with_profile_insight,
            "sections_with_rehook": sections_with_rehook,
            "sections_with_open_loop_or_payoff": sections_with_open_loop_or_payoff,
            "sections_with_boundary_advice": sections_with_boundary_advice,
            "first_1800_embodied_markers": opening_embodied,
            "first_1800_symbolic_markers": opening_symbolic,
            "first_700_hook_device_markers": first_700_hook_devices,
            "first_700_open_loop_markers": first_700_open_loops,
            "first_700_stakes_markers": first_700_stakes,
            "first_1800_pattern_interrupt_markers": first_1800_pattern_interrupts,
            **section_metrics,
            **opening_metrics,
        },
        "critical_failures": critical_failures,
        "warnings": warnings,
        "rewrite_guidance": rewrite_guidance,
    }
