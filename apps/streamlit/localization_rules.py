from __future__ import annotations

LOCALIZATION_RULES = """
로컬라이징/번역 원칙:
- 직역 금지. 원문의 사회적 맥락, 관계 맥락, 플랫폼 말투를 한국 시청자가 자연스럽게 이해할 표현으로 옮긴다.
- 영어 → 한국어 번역 시 reddit/AITA/relationship advice 문체를 한국식 사연 상담 말투로 재현한다. 단, 원문 의미를 바꾸지 않는다.
- 한국어 → 영어 번역 시 한국 커뮤니티식 반응어, 반존대, 비꼼, 억울함을 영어권 storytime/reddit/TikTok 댓글 문화에 맞게 옮긴다.
- 민감 주제는 특히 직역하지 않는다. 성 정체성, 성적 지향, 아웃팅, 사생활, 가족관계, 장애, 임신, 차별 표현은 과장 없이 정확히 옮긴다.
- 확실하지 않은 정체성은 단정하지 않는다. '성 정체성이 드러났다'보다 '그렇게 받아들여질 수 있는 말이 퍼졌다', '사적인 관계/행동이 원치 않게 알려졌다'처럼 맥락화한다.
- 한국어 대본에서 '사생활이 터졌다' 같은 과격하고 어색한 표현 금지. '개인적인 일이 원치 않게 알려졌다', '사적인 부분이 사람들 입에 오르내리게 됐다', '의도치 않게 아웃팅처럼 번질 수 있었다'로 쓴다.
- 영어 대본에서는 'privacy exploded' 같은 콩글리시 금지. 'his private life was exposed', 'he felt outed', 'it may have come across as outing him', 'private information spread'처럼 자연스럽게 쓴다.
- 'sexual identity'는 맥락 없이 남발하지 않는다. 필요하면 'sexual orientation', 'gender identity', 'private relationship', 'intimate behavior' 중 정확한 표현을 고른다.
- 농담, 드립, 채팅 반응은 의미 단위로 재창작한다. 한국식 '시장가 매도하듯 손절'은 영어권에서는 'drop the friendship like a bad trade'처럼 자연화한다.
- 점성술/사주 표현은 국가별로 조정한다. 한국어는 사주/궁합/기운/작두를 써도 되고, 영어는 astrology, birth chart, compatibility, energy, timing, read the room 같은 표현으로 자연화한다.
"""

BAD_LOCALIZATION_PHRASES = [
    "사생활이 터진",
    "사생활이 터졌다",
    "사생활 터짐",
    "정체성이 폭발",
    "성 정체성이 폭로됐다",
    "성 정체성을 드러내게 됐다",
    "privacy exploded",
    "private life exploded",
    "sexual identity was exploded",
    "his identity exploded",
    "her identity exploded",
    "기념일에 기대하는 기운",
]

GOOD_LOCALIZATION_EXAMPLES = """
좋은 로컬라이징 예시:
- outed → 아웃팅됐다 / 원치 않게 알려졌다 / 그렇게 받아들여질 수 있었다
- he felt outed → 본인은 아웃팅당했다고 느낀 거예요
- I accidentally outed him → 제 말이 의도치 않게 아웃팅처럼 번졌을 수 있어요
- private life was exposed → 사적인 부분이 사람들 입에 오르내리게 됐다
- sexual orientation → 성적 지향
- gender identity → 성별 정체성
- intimate behavior → 사적인 행동 / 친밀한 행동
- read the room → 분위기 좀 봐라 / 그 자리의 공기를 봐야 한다
- AITA? → 내가 너무한 건가요? / 제가 잘못한 건가요?
- go no contact → 연락을 끊다 / 거리를 두다 / 선을 긋다
- boundaries → 선 / 경계 / 여기까지만 허용하는 기준
"""


def localization_prompt() -> str:
    return LOCALIZATION_RULES + "\n" + GOOD_LOCALIZATION_EXAMPLES
