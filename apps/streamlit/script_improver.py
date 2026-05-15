from __future__ import annotations

import json
from typing import Optional

from llm_pipeline import (
    LIVE_NARRATOR_RULES,
    STYLE_REFERENCE_BLOCK,
    clean_text,
    localization_prompt,
    openai_chat,
)


IMPROVEMENT_RULES = """
품질검사 실패 시 개선 룰:
1. 실패 항목을 우선순위로 정리한다. critical_failures > 낮은 점수 항목 > warnings 순서다.
2. 대본을 살짝 고치는 것이 아니라, 실패 원인을 해결하도록 구조를 재작성한다.
3. 분량 부족이면 전체를 10분 롱폼 수준으로 확장한다. 최소 8,000자, 권장 9,000~11,000자.
4. 후킹 약함이면 첫 700자에서 인사말을 삭제하고 사건의 폭탄, 판단 갈림, 책임 소재를 먼저 보여준다.
5. 라이브감 부족이면 채팅 의견을 최소 3회 받아치고, 단순 의견 유도가 아니라 채팅 의견 때문에 화자의 판단이 흔들리거나 보정되는 장면을 넣는다.
6. 상담성 부족이면 '대화해보세요' 같은 추상 조언을 금지한다. 실제로 말할 문장, 상대 반응별 대응, 피해야 할 행동까지 쓴다.
7. 캐릭터성 부족이면 사주/점성술 단어를 랜덤으로 꽂지 않는다. 사건 구조에 붙인다. 예: 비밀의 자리, 사회적 얼굴, 기운이 드러난 순간, 관계 궁합의 충돌.
8. 반존대 부족이면 진행은 존댓말, 감정 리액션과 채팅 받아치기는 반말이 튀어나오게 한다.
9. 로컬라이징 부족이면 미국식 표현을 한국 유튜브 사연 말투로 재작성한다. 한국에서 통용되는 외래어는 그대로 쓰고, 어색한 직역은 문장으로 푼다.
10. 민감 주제 처리 부족이면 단정하지 않는다. 정체성, 사생활, 아웃팅, 차별, 폭력, 임신, 장애 등은 행동과 정체성을 분리하고 2차 피해 방지 조언을 넣는다.
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


def build_rewrite_brief(quality: dict) -> str:
    scores = quality.get("scores", {}) or {}
    low_scores = sorted(scores.items(), key=lambda item: item[1])[:5]
    parts: list[str] = []
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
) -> tuple[str, Optional[str]]:
    """Rewrite a failed script using quality-check diagnostics."""
    if not current_script:
        return "", "개선할 기존 대본이 없습니다."

    brief = build_rewrite_brief(quality)
    system = f"""너는 유튜브 라이브 사연 상담 대본의 재작성 전문 작가다.
기존 대본이 품질검사를 통과하지 못했다. 아래 품질검사 리포트를 반영해 전면 개선한다.

{LIVE_NARRATOR_RULES}
{STYLE_REFERENCE_BLOCK}
{localization_prompt()}
{IMPROVEMENT_RULES}

재작성 절대 조건:
- 기존 대본을 문장 몇 개만 수정하지 말고, 실패 원인을 해결하도록 다시 쓴다.
- 총 8,000자 이상, 권장 9,000~11,000자.
- 타임코드 10개 이상.
- 각 타임코드마다 실제 방송 멘트를 길게 작성한다. 요약/목차 금지.
- 품질검사 리포트의 critical_failures는 반드시 해결한다.
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
        "improvement_mode": improvement_mode,
        "mission": "품질검사 통과를 목표로 대본을 전면 개선하라. 특히 후킹, 라이브감, 상담성, 캐릭터성, 로컬라이징, 타임코드 밀도를 강화하라.",
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
