from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from math import log10
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import feedparser
import streamlit as st
from dateutil import parser as date_parser

try:
    from supabase_store import is_configured as db_is_configured
    from supabase_store import load_packages, save_package
except Exception:
    db_is_configured = lambda: False

    def save_package(row: dict, package: dict, status: str = "scripted_longform"):
        return None, "supabase_store.py 모듈을 불러오지 못했습니다."

    def load_packages(limit: int = 30):
        return [], "supabase_store.py 모듈을 불러오지 못했습니다."


st.set_page_config(page_title="Story Pattern Lab", page_icon="🔮", layout="wide")

st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        background-color: #F3F6FA !important;
        border: 1px solid #DDE5ED !important;
        border-radius: 8px !important;
        padding: 12px !important;
        color: #222222 !important;
    }
    div[data-testid="stMetric"] > label {
        color: #333333 !important;
        font-weight: 700 !important;
    }
    div[data-testid="stMetric"] > div {
        color: #005DAA !important;
        font-size: 25px !important;
        font-weight: 800 !important;
    }
    .block-container { padding-top: 1.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

USER_AGENT = "Mozilla/5.0 StoryPatternLab/0.4; public-list-metadata-only"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

OVERSEAS_SOURCES = {
    "Reddit AITA": {"url": "https://www.reddit.com/r/AmItheAsshole/.rss", "category": "AITA / Moral Debate", "status": "Active RSS", "region": "해외"},
    "Reddit Relationship Advice": {"url": "https://www.reddit.com/r/relationship_advice/.rss", "category": "Relationship Drama", "status": "Active RSS", "region": "해외"},
    "Reddit TrueOffMyChest": {"url": "https://www.reddit.com/r/TrueOffMyChest/.rss", "category": "Confession / Personal Story", "status": "Active RSS", "region": "해외"},
    "Reddit BestOfRedditorUpdates": {"url": "https://www.reddit.com/r/BestofRedditorUpdates/.rss", "category": "Update Story / Longform", "status": "Active RSS", "region": "해외"},
}

DOMESTIC_COLLECTABLE_SOURCES = {
    "네이트판 랭킹": {"url": "https://pann.nate.com/talk/ranking", "category": "연애/결혼/가족 사연", "status": "실험 수집", "region": "국내", "parser": "nate_pann", "note": "공개 랭킹 목록에서 제목/URL 중심 수집"},
    "보배드림 베스트": {"url": "https://www.bobaedream.co.kr/list?code=best", "category": "사건/가족/직장/이슈", "status": "실험 수집", "region": "국내", "parser": "bobaedream", "note": "공개 베스트 목록에서 제목/URL 중심 수집"},
}

DOMESTIC_SOURCES = [
    {"site": "디시인사이드", "category": "익명 커뮤니티", "status": "검토 필요", "note": "약관/자동수집 제한 검토 후 결정"},
    {"site": "네이트판", "category": "연애/결혼/가족 사연", "status": "실험 수집", "note": "공개 랭킹 목록에서 제목/URL 중심 수집"},
    {"site": "더쿠", "category": "이슈/썰", "status": "보류", "note": "원문 저장 금지 원칙과 접근 구조 검토 필요"},
    {"site": "인스티즈", "category": "커뮤니티 썰", "status": "보류", "note": "로그인/약관 검토 필요"},
    {"site": "쭉빵닷컴", "category": "여성 커뮤니티", "status": "보류", "note": "접근/약관/개인정보 위험도 확인 필요"},
    {"site": "보배드림", "category": "사건/가족/직장", "status": "실험 수집", "note": "공개 베스트 목록에서 제목/URL 중심 수집"},
    {"site": "블라인드", "category": "직장 썰", "status": "제외/보류", "note": "로그인 기반, 자동 수집 부적합 가능성 높음"},
]

STATUS_OPTIONS = ["collected", "analyzed", "candidate", "approved", "scripted_longform", "expanded_shorts", "expanded_threads", "expanded_cardnews", "rejected", "archived"]

REWRITE_PRINCIPLES = [
    "원문 문장 구조를 그대로 복제하지 않는다.",
    "댓글 원문과 사용자 식별 정보를 대량 저장하지 않는다.",
    "이름, 회사, 지역, 학교, 계정명 등 식별 가능한 정보는 일반화한다.",
    "사주/점성술은 전면에 내세우지 않고 pattern, timing, karma 표현으로 치환한다.",
    "구성 비율은 썰 80%, 패턴 분석 15%, 타이밍/카르마 인사이트 5%를 기준으로 한다.",
    "롱폼 대본을 먼저 만들고, 쇼츠/쓰레드/카드뉴스는 파생물로 확장한다.",
]


@dataclass
class StoryItem:
    source: str
    region: str
    category: str
    title: str
    url: str
    original_excerpt: str
    posted_at: Optional[datetime]
    collected_at: datetime
    rank_position: int
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href_stack: list[str] = []
        self._text_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        href = ""
        for key, value in attrs:
            if key.lower() == "href" and value:
                href = value
                break
        self._href_stack.append(href)
        self._text_stack.append("")

    def handle_data(self, data: str) -> None:
        if self._text_stack:
            self._text_stack[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href_stack:
            return
        href = self._href_stack.pop()
        text = self._text_stack.pop() if self._text_stack else ""
        text = clean_html(text)
        if href and text:
            self.links.append((href, text))


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    value = os.environ.get(name)
    return value if value else default


def openai_is_configured() -> bool:
    return bool(get_secret("OPENAI_API_KEY"))


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1200]


def decode_html(raw: bytes, content_type: str = "") -> str:
    charset_match = re.search(r"charset=([\w-]+)", content_type or "")
    candidates = []
    if charset_match:
        candidates.append(charset_match.group(1))
    candidates.extend(["utf-8", "cp949", "euc-kr"])
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def parse_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def minutes_since(value: Optional[datetime]) -> Optional[int]:
    if not value:
        return None
    now = datetime.now(timezone.utc)
    return max(0, int((now - value).total_seconds() / 60))


def log_score(value: int, scale: float) -> float:
    if value <= 0:
        return 0
    return max(0, min(100, log10(value + 1) * scale))


def story_angle(title: str) -> str:
    lower = title.lower()
    korean = title
    if any(word in lower for word in ["wedding", "fiancé", "fiance", "husband", "wife"]) or any(word in korean for word in ["결혼", "파혼", "신랑", "신부", "남편", "아내"]):
        return "Wedding / Relationship Drama"
    if any(word in lower for word in ["mother", "father", "parent", "family"]) or any(word in korean for word in ["엄마", "아빠", "부모", "가족", "시댁", "장모"]):
        return "Family Conflict"
    if any(word in lower for word in ["work", "boss", "coworker", "job"]) or any(word in korean for word in ["회사", "직장", "상사", "동료", "퇴사"]):
        return "Workplace Betrayal"
    if any(word in lower for word in ["friend", "roommate"]) or any(word in korean for word in ["친구", "룸메", "동창"]):
        return "Friend / Roommate Drama"
    if "update" in lower or "final update" in lower:
        return "Update / Longform Story"
    return "General Storytime"


def calculate_scores(item: StoryItem) -> dict[str, float]:
    rank_score = max(0, min(100, 100 - (item.rank_position - 1) * 3))
    freshness_minutes = minutes_since(item.posted_at)
    freshness_score = 50 if freshness_minutes is None else max(0, min(100, 100 - freshness_minutes / 18))
    like_score = log_score(item.like_count, 18)
    comment_score = log_score(item.comment_count, 22)
    view_score = log_score(item.view_count, 12)
    reaction_score = like_score * 0.35 + comment_score * 0.45 + view_score * 0.20
    debate_score = min(100, comment_score * 0.25 + (100 - rank_score) * 0.05)
    velocity_score = round((freshness_score * 0.55) + (rank_score * 0.45), 2)
    viral_score = min(100, reaction_score * 0.20 + debate_score * 0.15 + rank_score * 0.35 + freshness_score * 0.30)
    production_score = min(100, viral_score * 0.45 + debate_score * 0.20 + velocity_score * 0.20 + 15)
    risk_score = 35 if item.region == "해외" else 60
    return {"viral_score": round(viral_score, 2), "velocity_score": round(velocity_score, 2), "debate_score": round(debate_score, 2), "production_score": round(production_score, 2), "risk_score": round(risk_score, 2), "freshness_score": round(freshness_score, 2), "rank_score": round(rank_score, 2)}


def collect_rss(source_name: str, source_meta: dict[str, str], limit: int) -> list[StoryItem]:
    feed = feedparser.parse(source_meta["url"])
    items: list[StoryItem] = []
    collected_at = datetime.now(timezone.utc)
    for index, entry in enumerate(feed.entries[:limit], start=1):
        title = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()
        if not title or not url:
            continue
        published = getattr(entry, "published", None) or getattr(entry, "updated", None)
        summary = clean_html(getattr(entry, "summary", ""))
        items.append(StoryItem(source=source_name, region=source_meta["region"], category=source_meta["category"], title=title, url=url, original_excerpt=summary, posted_at=parse_datetime(published), collected_at=collected_at, rank_position=index))
    return items


def is_domestic_story_link(parser_type: str, href: str, text: str) -> bool:
    if len(text) < 8:
        return False
    bad_words = ["로그인", "회원가입", "검색", "이전", "다음", "공지", "광고", "이벤트", "고객센터", "댓글", "추천"]
    if any(word in text for word in bad_words):
        return False
    if parser_type == "nate_pann":
        return "/talk/" in href and "ranking" not in href
    if parser_type == "bobaedream":
        return "view" in href and ("No=" in href or "code=" in href)
    return False


def collect_public_list(source_name: str, source_meta: dict[str, str], limit: int) -> tuple[list[StoryItem], str]:
    collected_at = datetime.now(timezone.utc)
    request = Request(source_meta["url"], headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"})
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read()
            html = decode_html(raw, response.headers.get("Content-Type", ""))
    except Exception as error:
        return [], f"{source_name} 수집 실패: {error}"
    parser = LinkTextParser()
    parser.feed(html)
    items: list[StoryItem] = []
    seen_urls: set[str] = set()
    for href, text in parser.links:
        if not is_domestic_story_link(source_meta["parser"], href, text):
            continue
        url = urljoin(source_meta["url"], href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(StoryItem(source=source_name, region=source_meta["region"], category=source_meta["category"], title=text[:180], url=url, original_excerpt="공개 목록에서 제목과 링크만 수집했습니다. 원문 확인은 원문 링크에서 진행합니다.", posted_at=None, collected_at=collected_at, rank_position=len(items) + 1))
        if len(items) >= limit:
            break
    return items, f"{source_name} 수집 완료: {len(items)}개"


def pseudo_translate(text: str) -> str:
    if not text:
        return "번역할 원문 요약이 없습니다. LLM API 생성 버튼을 눌러 번역/요약을 생성하세요."
    return "[운영자 확인용 번역은 LLM API 생성 후 제공됩니다] " + text[:600]


def infer_analysis(row: dict) -> dict[str, str]:
    return {"core_summary": f"이 소재는 '{row['title']}'에서 시작되는 {row['angle']} 유형의 사연입니다.", "core_conflict": "주인공이 불편함을 감지했지만 주변 인물의 반응 때문에 스스로를 의심하게 되는 구조입니다.", "relationship_map": "주인공 / 갈등 유발 인물 / 주변 압박 인물의 삼각 구도로 재구성할 수 있습니다.", "red_flag": "문제의 사건 자체보다, 사건 이후 상대가 책임을 회피하거나 감정을 축소하는 태도가 핵심 레드플래그입니다.", "comment_trigger": "시청자는 '예민한 반응인가, 조기 경고를 본 것인가'로 갈릴 가능성이 높습니다.", "pattern_insight": "Most people saw drama. She saw the pattern. 이 방향으로 관계 패턴을 해석합니다.", "risk_note": "원문 표현을 그대로 쓰지 않고, 인물·장소·관계 디테일을 일반화해서 재창작해야 합니다."}


def status_badge(score: float) -> str:
    if score >= 75:
        return "🔥 제작 우선"
    if score >= 55:
        return "🟡 후보"
    return "⚪ 관찰"


def make_template_script(row: dict, analysis: dict[str, str]) -> str:
    return f"""0:00 Cold Open
She thought this was just one strange moment. But the pattern was already there.

0:30 Context Setup
The story begins with this title: {row['title']}

1:30 First Red Flag
The first red flag is not always loud. Sometimes it is the moment someone makes the main character feel dramatic for noticing something uncomfortable.

3:00 Escalation
As the situation grows, the audience starts looking for one thing: did the main character miss the warning signs, or were they trained to ignore them?

5:00 Turning Point
This is where the story reveals the real conflict. {analysis['core_conflict']}

6:30 Hidden Pattern Analysis
Most people will focus on the drama. But the stronger angle is this: {analysis['pattern_insight']}

8:00 Emotional Climax
The ending should not simply say who was right or wrong. It should show what this moment reveals about the relationship dynamic.

9:30 Comment-Triggering Question
Was this an overreaction, or did they see the pattern before everyone else?
"""


def fallback_package(row: dict, analysis: dict[str, str]) -> dict:
    script = make_template_script(row, analysis)
    return {"source": "template_fallback", "overview_ko": analysis["core_summary"], "translation_ko": pseudo_translate(row.get("original_excerpt") or row.get("title", "")), "analysis": analysis, "risk_filter": ["원문 직접 복제 금지", "인물/장소/직장명 일반화", "댓글 원문 대량 저장 금지"], "longform_script": script, "shorts": {"30s": f"Everyone focused on the drama.\nBut the real story was the pattern behind it.\n{row['title']}\nWould you walk away?", "60s": f"She thought it was one small problem.\nBut it started with this: {row['title']}\nMost people saw drama. She saw the pattern.\nWas it an overreaction, or an early warning?", "90s": script[:900]}, "threads": {"5_post": "1. Most people saw this as drama.\n2. But the pattern was louder.\n3. The first red flag was subtle.\n4. The conflict escalated because nobody named it.\n5. Would you have noticed it earlier?", "10_post": "템플릿 기반 Threads 초안입니다. LLM API 연결 후 확장됩니다."}, "card_news": {"8_cards": [{"title": "The First Moment", "body": row["title"], "image_prompt": "cinematic storytime thumbnail, tense domestic drama", "design_note": "dark text on clean background"}]}, "titles": ["Everyone Saw Drama. She Saw the Pattern.", "They Called Her Dramatic Until the Truth Came Out", "This Was Not the Real Problem", "She Noticed the Red Flag Early", "The Pattern Was There the Whole Time"], "thumbnail_text": ["SHE WAS RIGHT", "NOT JUST DRAMA", "THE PATTERN", "RED FLAG?"], "comment_question": "Was this an overreaction, or did they see the pattern before everyone else?"}


def build_llm_messages(row: dict, analysis: dict[str, str], tone: str, structure: str, voice: str, output_language: str, pattern_pct: int) -> list[dict[str, str]]:
    safe_excerpt = clean_html(row.get("original_excerpt", ""))[:900]
    schema = {"overview_ko": "운영자용 한글 요약 3문장", "translation_ko": "원문/요약의 운영자용 한글 번역", "analysis": {"story_summary": "짧은 요약", "core_conflict": "핵심 갈등", "emotional_trigger": "감정 트리거", "hidden_pattern": "숨겨진 관계 패턴", "red_flags": ["레드플래그 1"], "timeline": ["사건 순서 1"], "character_roles": ["주인공", "갈등 유발 인물"], "audience_reaction": "시청자가 댓글을 달 이유", "cultural_localization": "해외 시청자 유의점", "risk_notes": ["비식별화/저작권/명예훼손 유의점"], "production_recommendation": "제작 추천/보류 이유"}, "risk_filter": ["원문 재사용 방지 규칙"], "longform_script": "10-minute YouTube storytime script with time markers", "shorts": {"30s": "30-second short script", "60s": "60-second short script", "90s": "90-second short script"}, "threads": {"5_post": "5-post thread", "10_post": "10-post thread", "controversy_version": "controversy hook version", "question_led_version": "question-led version"}, "card_news": {"8_cards": [{"title": "card title", "body": "card body", "image_prompt": "image prompt", "design_note": "design note"}]}, "titles": ["title option 1", "title option 2"], "thumbnail_text": ["thumbnail phrase 1"], "comment_question": "comment question"}
    system = f"""You are a senior YouTube storytime producer and safety-aware rewriting editor.
Create a production package from a public story candidate.
The final content must be transformed and original. Do not copy source sentence structure.
Do not store or reproduce names, account IDs, workplaces, schools, exact locations, or identifying details.
Use astrology/saju only as a subtle pattern/timing lens. Do not make it the main topic.
Target overseas storytime viewers.
Story ratio: story 80%, relationship/pattern analysis {pattern_pct}%, timing/karma insight minimal.
Output language for final scripts: {output_language}.
Return ONLY valid JSON. No markdown fences."""
    user = {"source": row.get("source"), "region": row.get("region"), "url": row.get("url"), "title": row.get("title"), "angle": row.get("angle"), "excerpt": safe_excerpt, "metric_hint": {"production_score": row.get("production_score"), "viral_score": row.get("viral_score"), "debate_score": row.get("debate_score"), "comment_count": row.get("comment_count"), "like_count": row.get("like_count")}, "draft_analysis": analysis, "desired_tone": tone, "desired_structure": structure, "desired_voice": voice, "required_longform_structure": ["Cold open", "Context setup", "First red flag", "Escalation", "Turning point", "Hidden pattern analysis", "Emotional climax", "Comment-triggering question", "Closing line"], "json_schema": schema}
    return [{"role": "system", "content": system.strip()}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]


def openai_chat(messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> tuple[Optional[str], Optional[str]]:
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY가 Streamlit secrets 또는 환경변수에 없습니다."
    base_url = (get_secret("OPENAI_API_BASE", DEFAULT_OPENAI_BASE_URL) or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
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


def extract_json_object(text: str) -> Optional[dict]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def generate_llm_package(row: dict, analysis: dict[str, str], tone: str, structure: str, voice: str, output_language: str, pattern_pct: int, model: str, temperature: float) -> tuple[dict, Optional[str]]:
    messages = build_llm_messages(row, analysis, tone, structure, voice, output_language, pattern_pct)
    raw, error = openai_chat(messages, model=model, temperature=temperature, max_tokens=6500)
    if error:
        package = fallback_package(row, analysis)
        package["source"] = "template_fallback_after_api_error"
        package["api_error"] = error
        return package, error
    parsed = extract_json_object(raw or "")
    if not parsed:
        package = fallback_package(row, analysis)
        package["source"] = "raw_llm_unparsed"
        package["raw_llm_output"] = raw
        return package, "LLM 응답을 JSON으로 파싱하지 못해 원문 응답을 보관했습니다."
    parsed["source"] = "openai_api"
    parsed["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return parsed, None


def package_to_text(package: dict, key: str, default: str = "") -> str:
    value = package.get(key, default)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def package_key(row: dict, tone: str, structure: str, voice: str, output_language: str, pattern_pct: int, model: str) -> str:
    return "|".join([row.get("url", row.get("id", row.get("title", ""))), tone, structure, voice, output_language, str(pattern_pct), model])


def expansions_from_package(package: dict) -> dict[str, str]:
    shorts = package.get("shorts", {}) if isinstance(package.get("shorts"), dict) else {}
    threads = package.get("threads", {}) if isinstance(package.get("threads"), dict) else {}
    return {"30초 쇼츠": shorts.get("30s", ""), "60초 쇼츠": shorts.get("60s", ""), "90초 쇼츠": shorts.get("90s", ""), "Threads 5": threads.get("5_post", ""), "Threads 10": threads.get("10_post", ""), "카드뉴스": json.dumps(package.get("card_news", {}), ensure_ascii=False, indent=2), "썸네일": "\n".join(package.get("thumbnail_text", [])) if isinstance(package.get("thumbnail_text"), list) else str(package.get("thumbnail_text", "")), "제목": "\n".join(package.get("titles", [])) if isinstance(package.get("titles"), list) else str(package.get("titles", ""))}


st.title("Story Pattern Lab")
st.caption("실시간 점수 · 소재 확정 · LLM 제작 패키지 · Supabase 히스토리")

for key, value in {"stories": [], "approved": [], "statuses": {}, "collection_logs": [], "rows": [], "production_packages": {}, "history_rows": []}.items():
    if key not in st.session_state:
        st.session_state[key] = value

with st.sidebar:
    st.header("수집 설정")
    selected_sources = st.multiselect("해외 RSS 소스", options=list(OVERSEAS_SOURCES.keys()), default=["Reddit AITA", "Reddit Relationship Advice"])
    selected_domestic_sources = st.multiselect("국내 공개목록 실험 소스", options=list(DOMESTIC_COLLECTABLE_SOURCES.keys()), default=[])
    per_source_limit = st.slider("소스당 수집 개수", 5, 50, 15, 5)
    collect_button = st.button("실시간 후보 수집", type="primary", use_container_width=True)
    st.divider()
    st.header("API 상태")
    st.caption(f"OpenAI: {'ON' if openai_is_configured() else 'OFF'}")
    st.caption(f"Supabase: {'ON' if db_is_configured() else 'OFF'}")
    llm_model = st.text_input("모델명", value=get_secret("OPENAI_MODEL", DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL)
    temperature = st.slider("창의성", 0.1, 1.2, 0.75, 0.05)
    if st.button("OpenAI 테스트", use_container_width=True):
        with st.spinner("OpenAI API 테스트 중..."):
            raw, err = openai_chat([{"role": "user", "content": "Return exactly OK."}], model=llm_model, temperature=0.1, max_tokens=8)
        st.error(err) if err else st.success(f"응답: {raw}")
    if st.button("Supabase 테스트", use_container_width=True):
        rows, err = load_packages(1)
        st.error(err) if err else st.success("Supabase 연결 성공")

if collect_button:
    collected: list[StoryItem] = []
    logs: list[str] = []
    for source_name in selected_sources:
        items = collect_rss(source_name, OVERSEAS_SOURCES[source_name], per_source_limit)
        collected.extend(items)
        logs.append(f"{source_name} 수집 완료: {len(items)}개")
    for source_name in selected_domestic_sources:
        items, message = collect_public_list(source_name, DOMESTIC_COLLECTABLE_SOURCES[source_name], per_source_limit)
        collected.extend(items)
        logs.append(message)
    st.session_state.stories = collected
    st.session_state.collection_logs = logs

stories: list[StoryItem] = st.session_state.stories
source_count = len(set(item.source for item in stories)) if stories else 0
avg_score = round(sum(calculate_scores(item)["viral_score"] for item in stories) / len(stories), 2) if stories else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("수집 소재", len(stories))
col2.metric("활성 소스", source_count)
col3.metric("평균 Viral", avg_score)
col4.metric("확정 소재", len(st.session_state.approved))
col5.metric("히스토리", len(st.session_state.history_rows))

if st.session_state.collection_logs:
    with st.expander("수집 로그", expanded=False):
        for log in st.session_state.collection_logs:
            st.write(f"- {log}")

tabs = st.tabs(["📡 소스", "🏆 리더보드", "🎬 제작 패키지", "🗂️ 히스토리", "🧪 원칙/DB"])

with tabs[0]:
    st.subheader("소스 목록")
    st.dataframe([{"site": name, **meta} for name, meta in OVERSEAS_SOURCES.items()], use_container_width=True, hide_index=True)
    st.dataframe(DOMESTIC_SOURCES, use_container_width=True, hide_index=True)
    st.dataframe([{"site": name, **meta} for name, meta in DOMESTIC_COLLECTABLE_SOURCES.items()], use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("스코어 리더보드")
    if not stories:
        st.info("왼쪽에서 소스를 고르고 실시간 후보 수집을 눌러주세요.")
    else:
        rows = []
        for item in stories:
            scores = calculate_scores(item)
            minutes_posted = minutes_since(item.posted_at)
            posted_at_str = item.posted_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if item.posted_at else None
            rows.append({"id": f"{item.source}-{item.rank_position}-{abs(hash(item.url))}", "badge": status_badge(scores["production_score"]), "region": item.region, "source": item.source, "angle": story_angle(item.title), "title": item.title, "url": item.url, "rank": item.rank_position, "posted_at": posted_at_str, "collected_at": item.collected_at.strftime("%Y-%m-%d %H:%M:%S UTC"), "fresh_min": minutes_posted, "like_count": item.like_count, "comment_count": item.comment_count, "view_count": item.view_count, "original_excerpt": item.original_excerpt, **scores})
        rows = sorted(rows, key=lambda row: row["production_score"], reverse=True)
        st.session_state.rows = rows
        c1, c2, c3 = st.columns([2, 1, 1])
        q = c1.text_input("제목 검색", "")
        sort_key = c2.selectbox("정렬", ["production_score", "viral_score", "velocity_score", "debate_score", "risk_score", "fresh_min"], index=0)
        max_risk = c3.slider("위험 점수 상한", 0, 100, 80, 5)
        filtered = [row for row in rows if (not q or q.lower() in row["title"].lower()) and row["risk_score"] <= max_risk]
        reverse = sort_key not in ["risk_score", "fresh_min"]
        filtered = sorted(filtered, key=lambda row: row[sort_key] if row[sort_key] is not None else -1, reverse=reverse)
        st.dataframe(filtered, use_container_width=True, hide_index=True, column_order=["badge", "region", "production_score", "viral_score", "velocity_score", "debate_score", "risk_score", "fresh_min", "rank", "source", "angle", "title", "url"])

with tabs[2]:
    st.subheader("소재 선택 → LLM 제작 패키지")
    rows = st.session_state.get("rows", [])
    if not rows:
        st.info("먼저 리더보드에서 소재를 수집/생성해주세요.")
    else:
        idx = st.radio("제작할 소재", options=list(range(len(rows))), format_func=lambda i: f"{i + 1}. {rows[i]['title'][:60]} | {rows[i]['source']} | {rows[i]['region']}")
        selected = rows[idx]
        analysis = infer_analysis(selected)
        metric_cols = st.columns(6)
        metric_cols[0].metric("Production", selected.get("production_score", 0))
        metric_cols[1].metric("Viral", selected.get("viral_score", 0))
        metric_cols[2].metric("Debate", selected.get("debate_score", 0))
        metric_cols[3].metric("댓글", selected.get("comment_count", 0) or "N/A")
        metric_cols[4].metric("좋아요", selected.get("like_count", 0) or "N/A")
        metric_cols[5].metric("조회수", selected.get("view_count", 0) or "N/A")
        with st.expander("원문 개요 / 안전 확인", expanded=True):
            st.write(f"**원문 제목:** {selected['title']}")
            st.write(f"**소스:** {selected['source']} / {selected['region']}")
            st.write(f"**URL:** {selected['url']}")
            st.text_area("원문 요약 또는 공개목록 excerpt", selected.get("original_excerpt", ""), height=120)
            st.json(analysis)
        option_cols = st.columns(5)
        tone = option_cols[0].selectbox("톤", ["Drama", "Suspense", "Comical", "Documentary"], index=0)
        structure = option_cols[1].selectbox("구조", ["Classic", "Twist", "Parallel"], index=0)
        voice = option_cols[2].selectbox("시점", ["Third Person", "First Person", "Second Person"], index=0)
        output_language = option_cols[3].selectbox("출력 언어", ["English", "Korean"], index=0)
        pattern_pct = option_cols[4].slider("패턴 비중", 0, 30, 10, 5)
        key = package_key(selected, tone, structure, voice, output_language, pattern_pct, llm_model)
        col_a, col_b, col_c = st.columns(3)
        if col_a.button("LLM API로 제작 패키지 생성", type="primary", use_container_width=True):
            with st.spinner("LLM 제작 패키지 생성 중..."):
                package, error = generate_llm_package(selected, analysis, tone, structure, voice, output_language, pattern_pct, llm_model, temperature)
            st.session_state.production_packages[key] = package
            st.warning(error) if error else st.success("LLM 제작 패키지 생성 완료")
        package = st.session_state.production_packages.get(key)
        if package and col_b.button("Supabase에 저장", use_container_width=True):
            result, error = save_package(selected, package)
            if error:
                st.error(error)
            else:
                st.success("Supabase 저장 완료")
                if isinstance(result, list):
                    st.session_state.history_rows = result + st.session_state.history_rows
        col_c.download_button("원문 링크 저장", selected["url"], file_name="source_url.txt", use_container_width=True)
        if not package:
            st.info("아직 제작 패키지가 없습니다. 생성 버튼을 누르세요.")
            st.text_area("템플릿 초안", make_template_script(selected, analysis), height=360)
        else:
            if package.get("api_error"):
                st.error(package["api_error"])
            tabs_pkg = st.tabs(["개요/분석", "10분 롱폼", "쇼츠", "Threads", "카드뉴스", "제목/썸네일", "JSON"])
            with tabs_pkg[0]:
                st.text_area("운영자용 한글 요약", package_to_text(package, "overview_ko"), height=120)
                st.text_area("운영자용 한글 번역", package_to_text(package, "translation_ko"), height=160)
                st.text_area("LLM 추론 분석", package_to_text(package, "analysis"), height=260)
            with tabs_pkg[1]:
                edited = st.text_area("10분 롱폼 대본", package_to_text(package, "longform_script"), height=520)
                if st.button("수정한 롱폼 저장", use_container_width=True):
                    package["longform_script"] = edited
                    st.session_state.production_packages[key] = package
                    st.success("수정본 저장 완료")
            exp = expansions_from_package(package)
            with tabs_pkg[2]:
                st.text_area("30초 쇼츠", exp["30초 쇼츠"], height=160)
                st.text_area("60초 쇼츠", exp["60초 쇼츠"], height=220)
                st.text_area("90초 쇼츠", exp["90초 쇼츠"], height=260)
            with tabs_pkg[3]:
                st.text_area("5-post Thread", exp["Threads 5"], height=220)
                st.text_area("10-post Thread", exp["Threads 10"], height=320)
            with tabs_pkg[4]:
                st.text_area("카드뉴스 패키지", exp["카드뉴스"], height=420)
            with tabs_pkg[5]:
                st.text_area("썸네일 문구", exp["썸네일"], height=140)
                st.text_area("제목 후보", exp["제목"], height=240)
                st.text_area("댓글 질문", package_to_text(package, "comment_question"), height=100)
            with tabs_pkg[6]:
                st.download_button("제작 패키지 JSON 다운로드", data=json.dumps(package, ensure_ascii=False, indent=2), file_name="story_production_package.json", mime="application/json", use_container_width=True)
                st.json(package)

with tabs[3]:
    st.subheader("Supabase 히스토리")
    c1, c2 = st.columns([1, 1])
    limit = c1.slider("불러올 개수", 5, 100, 30, 5)
    if c2.button("히스토리 불러오기", type="primary", use_container_width=True):
        rows, error = load_packages(limit)
        if error:
            st.error(error)
        else:
            st.session_state.history_rows = rows
            st.success(f"히스토리 {len(rows)}개 불러옴")
    history = st.session_state.history_rows
    if not history:
        st.info("아직 불러온 히스토리가 없습니다.")
    else:
        st.dataframe(history, use_container_width=True, hide_index=True, column_order=["created_at", "status", "source_name", "production_score", "viral_score", "title", "source_url"])
        selected_history_title = st.selectbox("상세 확인", [row.get("title", "제목 없음") for row in history])
        selected_history = next((row for row in history if row.get("title") == selected_history_title), history[0])
        pkg = selected_history.get("package_json", {})
        st.text_area("저장된 10분 롱폼", package_to_text(pkg, "longform_script"), height=420)
        st.download_button("히스토리 JSON 다운로드", json.dumps(selected_history, ensure_ascii=False, indent=2), file_name="history_package.json", mime="application/json", use_container_width=True)

with tabs[4]:
    st.subheader("원칙 / DB 세팅")
    for principle in REWRITE_PRINCIPLES:
        st.write(f"- {principle}")
    st.divider()
    st.markdown("### Supabase 테이블 SQL")
    st.code("""create table if not exists story_production_packages (
  id uuid primary key default gen_random_uuid(),
  source_url text,
  source_name text,
  title text,
  status text default 'scripted_longform',
  production_score numeric,
  viral_score numeric,
  package_json jsonb,
  created_at timestamptz default now()
);""", language="sql")
    st.markdown("### 앱 설정")
    st.write("OpenAI와 Supabase 값은 Streamlit Secrets 또는 환경변수에서 읽습니다. 키는 코드에 저장하지 않습니다.")

st.caption("Story Pattern Lab v0.4 · OpenAI + Supabase 연결형 Streamlit 제작 대시보드")
