from __future__ import annotations

import re


def count_any(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def quality_check_live_script(script: str) -> dict:
    text = script or ""
    length = len(text)
    timecodes = len(re.findall(r"\b\d{1,2}:\d{2}\b", text))
    polite = count_any(text, ["요", "습니다", "세요", "합니다", "했어요", "거예요", "볼게요"])
    casual = count_any(text, ["아니", "야", "잠깐만", "뭐야", "이건", "하지마", "맞잖아", "그니까", "얘들아"])
    chat = count_any(text, ["채팅", "댓글", "여러분", "도배", "올라오", "갈리"])
    advice = count_any(text, ["해야", "하지 마", "물어보", "확인", "거리", "정리", "조언", "대답보다", "태도"])
    astro = count_any(text, ["사주", "점성술", "궁합", "기운", "운", "작두", "타이밍", "흐름", "리듬", "별", "예언"])
    narrator = count_any(text, ["제가 보기", "저는", "제가", "나는", "내가"])
    sender = text.count("사연자님")
    outline_only = length < 2200 or (timecodes >= 6 and length / max(timecodes, 1) < 260)

    scores = {
        "대본_분량": clamp_score(length / 5500 * 100),
        "타임코드_구조": clamp_score(timecodes / 8 * 100),
        "반존대_자연스러움": clamp_score(min(polite, 45) * 1.4 + min(casual, 35) * 1.2),
        "라이브감": clamp_score(chat * 12 + casual * 1.5),
        "상담성": clamp_score(sender * 10 + advice * 8),
        "화자성": clamp_score(narrator * 6 + astro * 5),
        "사주점성술_캐릭터성": clamp_score(astro * 12),
    }
    overall = clamp_score(sum(scores.values()) / len(scores))

    warnings: list[str] = []
    if length < 5500:
        warnings.append("10분 롱폼치고 분량이 짧습니다. 최소 5,500자 이상 권장.")
    if outline_only:
        warnings.append("목차형 출력 가능성이 높습니다. 각 타임코드마다 실제 내레이션 문장이 길게 필요합니다.")
    if sender < 5:
        warnings.append("사연자님에게 직접 말하는 상담 구간이 부족합니다.")
    if text.count("여러분") < 5:
        warnings.append("시청자에게 말 거는 라이브감이 부족합니다.")
    if chat < 2:
        warnings.append("채팅/댓글 반응을 받아치는 장면이 부족합니다.")
    if casual < 8:
        warnings.append("감정이 튀는 반말 리액션이 부족합니다.")
    if advice < 3:
        warnings.append("현실적인 해결 방법이 부족합니다.")
    if astro < 3:
        warnings.append("사주/점성술/기운/작두 같은 화자 고유 언어가 부족합니다.")
    if count_any(text, ["무조건 악연", "운명입니다", "반드시 헤어", "100%", "절대적으로"]) > 0:
        warnings.append("점술 표현이 단정적으로 들릴 수 있습니다. 방송식 추측으로 완화하세요.")

    return {
        "overall_score": overall,
        "scores": scores,
        "metrics": {
            "length": length,
            "timecodes": timecodes,
            "polite_markers": polite,
            "casual_markers": casual,
            "chat_markers": chat,
            "advice_markers": advice,
            "astro_markers": astro,
            "sender_mentions": sender,
        },
        "warnings": warnings,
        "passed": overall >= 70 and not outline_only and length >= 5000,
    }
