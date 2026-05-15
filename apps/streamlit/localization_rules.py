from __future__ import annotations

LOCALIZATION_RULES = """
로컬라이징/번역 원칙:
- 금지어 목록으로 기계적으로 막는 방식이 아니라, 원문 표현의 기능을 파악한 뒤 한국인이 실제로 쓰는 말로 바꾼다.
- 직역 금지. 원문의 사회적 맥락, 관계 맥락, 플랫폼 말투, 농담의 기능을 한국 시청자가 자연스럽게 이해할 표현으로 옮긴다.
- 영어 → 한국어 번역 시 reddit/AITA/relationship advice 문체를 한국식 사연 상담/커뮤니티 사연 말투로 재현한다. 단, 원문 의미를 바꾸지 않는다.
- 한국어 → 영어 번역 시 한국 커뮤니티식 반응어, 반존대, 비꼼, 억울함을 영어권 storytime/reddit/TikTok 댓글 문화에 맞게 옮긴다.
- 미국 커뮤니티에서만 자연스러운 표현을 한국어로 옮길 때는 한국어권에서 실제로 쓰는 단어와 문장으로 바꾼다. 필요하면 단어 하나가 아니라 한 문장으로 풀어 쓴다.
- 다만 한국에서 이미 널리 통용되는 외래어/커뮤니티 용어는 억지로 순화하지 않는다. 가스라이팅, 알파메일, 커밍아웃, 아웃팅, 레드플래그, 플러팅, 빌런 같은 표현은 문맥에 맞으면 그대로 쓴다.
- 외래어를 쓸 때도 의미가 흐려지면 짧게 풀어준다. 예: 가스라이팅, 그러니까 사람을 예민한 사람으로 몰아서 자기 감각을 의심하게 만드는 방식.
- 민감 주제는 특히 직역하지 않는다. 성적 지향, 성별 정체성, 아웃팅, 사생활, 가족관계, 장애, 임신, 차별 표현은 과장 없이 정확히 옮긴다.
- 확실하지 않은 정체성은 단정하지 않는다. 당사자의 주장인지, 제3자의 해석인지, 실제 공개 행위인지 먼저 구분한다.
- outed는 무조건 '아웃팅됐다'로 옮기거나 무조건 금지하지 않는다. 한국 시청자에게 자연스러운 맥락이면 '아웃팅'을 쓰되, 필요한 경우 '원치 않게 알려졌다', '사적인 일이 사람들 입에 오르내리게 됐다', '그 사람은 그렇게 받아들였다'처럼 풀어 쓴다.
- 한국어 대본에서 '사생활이 터졌다' 같은 과격하고 어색한 표현은 피한다. '개인적인 일이 원치 않게 알려졌다', '사적인 부분이 사람들 입에 오르내리게 됐다', '의도치 않게 아웃팅처럼 받아들여질 수 있었다'처럼 실제 말투로 바꾼다.
- 영어 대본에서는 'privacy exploded' 같은 콩글리시 금지. 'he felt exposed', 'he felt outed', 'it may have come across as outing him', 'private information spread'처럼 자연스럽게 쓴다.
- 'sexual identity'는 맥락 없이 남발하지 않는다. 필요하면 'sexual orientation', 'gender identity', 'private relationship', 'intimate behavior' 중 정확한 표현을 고른다.
- 농담, 드립, 채팅 반응은 의미 단위로 재창작한다. 한국식 '시장가 매도하듯 손절'은 영어권에서는 'drop the friendship like a bad trade'처럼 자연화한다.
- 점성술/사주 표현은 국가별로 조정한다. 한국어는 사주/궁합/기운/작두를 써도 되고, 영어는 astrology, birth chart, compatibility, energy, timing, read the room 같은 표현으로 자연화한다.
"""

CONTEXTUAL_LOCALIZATION_GUIDE = """
미국 커뮤니티 표현 → 한국어 로컬라이징 방향:
- AITA? → 내가 너무한 건가요? / 제가 잘못한 건가요? / 이거 제가 이상한 건가요?
- OP → 사연자님 / 글쓴이 / 이분
- throwaway account → 부계로 올린 글 / 익명으로 쓴 글
- no contact → 연락을 끊다 / 아예 거리를 두다 / 선을 긋다
- low contact → 연락을 줄이다 / 적당히 거리 두다
- boundaries → 선 / 경계 / 여기까지만 허용하는 기준
- red flag → 레드플래그 / 이상 신호 / 찝찝한 포인트 / 이건 좀 걸리는 지점
- gaslighting → 가스라이팅 / 사람을 예민한 사람으로 몰아가는 말 / 내 감각을 의심하게 만드는 방식
- closure → 마지막으로 정리할 말 / 마음 정리 / 납득할 수 있는 마무리
- come out → 커밍아웃하다 / 스스로 밝히다 / 본인이 직접 말하다
- outed / outing → 아웃팅 / 원치 않게 알려짐 / 본인의 의사와 상관없이 사적인 부분이 알려지는 일
- closet / closeted → 아직 커밍아웃하지 않은 상태 / 주변에 말하지 않은 상태 / 본인이 숨기고 있던 부분
- private life was exposed → 사적인 일이 사람들 입에 오르내리게 됐다 / 개인적인 부분이 원치 않게 알려졌다
- accused me of outing him → 제 말 때문에 본인이 아웃팅당한 것처럼 느꼈다고 항의했다 / 제 말이 사적인 부분을 퍼뜨린 것처럼 됐다고 따졌다
- inappropriate behavior in a shared space → 공용 공간에서 다른 사람이 불편할 수 있는 행동 / 시설 이용 매너 문제
- read the room → 분위기 좀 봐라 / 그 자리의 공기를 봐야 한다
- get over it → 그냥 넘겨 / 왜 아직도 그러냐 / 이제 그만 좀 해
- entitled → 당연한 줄 아는 / 자기가 받을 자격이 있다고 여기는 / 너무 자기중심적인
- weaponized incompetence → 일부러 못하는 척하는 것 / 모르는 척 떠넘기는 것
- people pleaser → 남 눈치 많이 보는 사람 / 남 맞춰주느라 자기 마음을 미루는 사람
- alpha male → 알파메일 / 상남자 이미지에 집착하는 사람 / 센 척하는 남성성 캐릭터
- flirting → 플러팅 / 은근히 꼬시는 말 / 이성적 신호를 보내는 행동
- villain → 빌런 / 문제 인물 / 판을 흐리는 사람
"""

COMMON_KOREAN_LOANWORDS = """
한국어 대본에서 그대로 써도 자연스러운 외래어/커뮤니티 용어:
- 가스라이팅
- 알파메일
- 커밍아웃
- 아웃팅
- 레드플래그
- 플러팅
- 빌런
- 손절
- TMI
- 썸
- 멘탈

사용 원칙:
- 한국 시청자가 실제로 쓰는 외래어는 그대로 사용한다.
- 단어만 던지지 말고, 필요하면 바로 뒤에 한국어식 설명을 붙인다.
- 예: 이건 가스라이팅까지는 아니어도, 사연자님이 자기 감각을 의심하게 만드는 말이긴 해요.
- 예: 이 사람은 그냥 알파메일이라기보다, 센 척하는 남성성 캐릭터에 너무 갇혀 있는 느낌이에요.
"""

# 이 목록은 '무조건 금지어'가 아니라, 직역 냄새가 강하거나 맥락 없이 쓰이면 위험한 표현이다.
# LLM은 이 표현을 발견하면 바로 삭제하기보다 실제 한국어 맥락에 맞게 다시 풀어 쓴다.
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
- he felt outed → 본인은 그 말 때문에 사적인 부분이 원치 않게 알려졌다고 느낀 거예요
- I accidentally outed him → 제 말이 의도치 않게 아웃팅처럼 받아들여졌을 수 있어요
- he accused me of outing him → 그 사람은 제 말 때문에 본인이 아웃팅당한 것처럼 느꼈다고 항의했어요
- private life was exposed → 사적인 부분이 사람들 입에 오르내리게 됐다
- sexual orientation → 성적 지향
- gender identity → 성별 정체성
- intimate behavior → 사적인 행동 / 친밀한 행동
- read the room → 분위기 좀 봐라 / 그 자리의 공기를 봐야 한다
- AITA? → 내가 너무한 건가요? / 제가 잘못한 건가요?
- go no contact → 연락을 끊다 / 거리를 두다 / 선을 긋다
- boundaries → 선 / 경계 / 여기까지만 허용하는 기준
- gaslighting → 가스라이팅
- alpha male → 알파메일
- red flag → 레드플래그

나쁜 로컬라이징 예시:
- outed → 무조건 아웃팅됐다로 박아버리기
- privacy exploded → 사생활이 터졌다
- sexual identity was revealed → 성 정체성이 폭로됐다
- read the room → 방을 읽어라
- boundaries → 경계선들
- gaslighting → 가스 조명
- alpha male → 알파 남성 동물
"""

LOCALIZATION_DECISION_STEPS = """
로컬라이징 판단 순서:
1. 원문 표현이 사실 서술인지, 당사자의 주장인지, 농담인지, 비난인지 구분한다.
2. 그 표현이 한국 시청자에게 어떤 감정으로 들려야 하는지 정한다.
3. 한국어권에서 실제로 쓰는 말인지 확인한다. 통용되는 외래어면 그대로 쓰고, 어색한 직역이면 문장으로 푼다.
4. 민감 주제는 단정형보다 맥락형을 우선한다.
5. 번역투, 직역투, 과장된 커뮤니티 표현이 있으면 자연스러운 방송 멘트로 다시 쓴다.
"""


def localization_prompt() -> str:
    return LOCALIZATION_RULES + "\n" + CONTEXTUAL_LOCALIZATION_GUIDE + "\n" + COMMON_KOREAN_LOANWORDS + "\n" + GOOD_LOCALIZATION_EXAMPLES + "\n" + LOCALIZATION_DECISION_STEPS
