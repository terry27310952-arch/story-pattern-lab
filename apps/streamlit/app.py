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
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import feedparser
import streamlit as st
from dateutil import parser as date_parser

try:
    from source_fetcher import fetch_article_body
except Exception:
    fetch_article_body = None

try:
    from llm_pipeline import (
        analyze_story,
        build_live_blueprint,
        write_live_longform,
        generate_derivatives,
        build_package,
    )
except Exception as import_error:
    analyze_story = build_live_blueprint = write_live_longform = generate_derivatives = build_package = None
    LLM_PIPELINE_IMPORT_ERROR = str(import_error)
else:
    LLM_PIPELINE_IMPORT_ERROR = None

try:
    from quality_check import quality_check_live_script
except Exception:
    quality_check_live_script = None

try:
    from script_improver import build_rewrite_brief, improve_failed_script
except Exception as import_error:
    build_rewrite_brief = None
    improve_failed_script = None
    SCRIPT_IMPROVER_IMPORT_ERROR = str(import_error)
else:
    SCRIPT_IMPROVER_IMPORT_ERROR = None

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
        font-size: 24px !important;
        font-weight: 800 !important;
    }
    .block-container { padding-top: 1.4rem; }
    .pipeline-card {
        border: 1px solid #E2E8F0;
        background: #F8FAFC;
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

USER_AGENT = "Mozilla/5.0 StoryPatternLab/0.5; public-list-metadata-only"
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

REWRITE_PRINCIPLES = [
    "원문 문장 구조를 그대로 복제하지 않는다.",
    "댓글 원문과 사용자 식별 정보를 대량 저장하지 않는다.",
    "이름, 회사, 지역, 학교, 계정명 등 식별 가능한 정보는 일반화한다.",
    "사주/점성술/작두/기운 표현은 허용하되, 단정적 점술 판단은 피한다.",
    "대본은 라이브 상담형 1인칭 여성 유튜버 말투를 기준으로 한다.",
    "존댓말 진행, 반말 리액션, 채팅 받아치기, 현실 조언이 모두 들어가야 한다.",
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


def infer_analysis(row: dict) -> dict[str, str]:
    return {"core_summary": f"이 소재는 '{row['title']}'에서 시작되는 {row['angle']} 유형의 사연입니다.", "core_conflict": "사연자가 느낀 찝찝함과 주변 반응 사이의 간극이 핵심 갈등입니다.", "relationship_map": "사연자 / 갈등 유발 인물 / 채팅이 갈릴 지점", "red_flag": "사건보다 이후 태도와 말투가 핵심 레드플래그입니다.", "comment_trigger": "시청자는 예민함인지 감지력인지로 갈릴 가능성이 높습니다.", "pattern_insight": "관계의 기운과 타이밍이 어긋나는 순간을 읽는 방향으로 해석합니다.", "risk_note": "원문 표현을 그대로 쓰지 않고, 인물·장소·관계 디테일을 일반화해서 재창작해야 합니다."}


def status_badge(score: float) -> str:
    if score >= 75:
        return "🔥 제작 우선"
    if score >= 55:
        return "🟡 후보"
    return "⚪ 관찰"


def make_template_script(row: dict, analysis: dict[str, str]) -> str:
    return f"""00:00
오늘 사연은요. 제목만 보면 그냥 {row['title']} 이 정도로 보일 수 있어요.
근데 잠깐만. 이거는 그냥 웃고 넘길 문제가 아닐 수도 있어요.
제가 이런 사연 볼 때 제일 먼저 보는 게 뭐냐면요. 말보다 타이밍이에요.

00:40
사연자님이 보내주신 내용을 보면, 처음에는 본인도 자기가 예민한 줄 알았대요.
근데 이상하게 마음이 계속 걸린 거죠.

01:40
아니 근데 여러분들, 마음이 계속 걸린다는 건 그냥 지나가는 감정이 아닐 때가 있어요.
사주로 치면 이건 궁합이 나쁘다 이런 단정이 아니라, 기운이 딱 삐끗한 순간이 있는 거예요.

02:30
지금 채팅에서도 갈리죠. 손절이다, 아니다, 그냥 장난이다.
아니 얘들아 잠깐만. 사람 관계를 그렇게 바로 시장가 매도하듯이 던지면 안 됩니다.

06:30
사연자님, 제가 보기엔 바로 끊을 문제는 아니에요. 근데 그냥 넘길 문제도 아닙니다.
한 번은 확인하세요. 대답보다 태도를 보세요.

09:30
여러분이라면 이 관계, 한 번 더 물어볼 것 같아요? 아니면 마음속으로 선을 그을 것 같아요?
"""


def fallback_package(row: dict, analysis: dict[str, str]) -> dict:
    script = make_template_script(row, analysis)
    return {"source": "template_fallback_live_advice", "overview_ko": analysis["core_summary"], "analysis": analysis, "risk_filter": ["원문 직접 복제 금지", "인물/장소/직장명 일반화", "댓글 원문 대량 저장 금지"], "longform_script": script, "shorts": {"30s": "좋은 소식에 이상한 반응을 본 적 있나요? 아니 근데 이건 웃음보다 그 다음 공기가 문제예요.", "60s": "사연자님이 예민한 게 아니라, 관계의 기운이 삐끗한 순간을 감지한 걸 수도 있어요. 바로 손절 말고 한 번은 확인하세요.", "90s": script[:900]}, "threads": {"5_post": "1. 사연자님은 이상한 반응 하나 때문에 마음이 걸렸습니다.\n2. 문제는 사건보다 그 뒤의 태도입니다.\n3. 바로 손절은 빠릅니다.\n4. 하지만 그냥 넘기는 것도 아닙니다.\n5. 한 번은 확인하고, 대답보다 태도를 보세요."}, "card_news": {"8_cards": [{"title": "이상한 반응", "body": row["title"], "image_prompt": "live advice storytime scene", "design_note": "clean and emotional"}]}, "titles": ["사연자님, 이건 예민한 게 아닐 수도 있어요", "좋은 소식에 웃은 친구, 문제는 그 다음 공기였어요"], "thumbnail_text": ["이건 좀 이상한데?", "예민한 게 아니야"], "comment_question": "여러분이라면 한 번 더 물어보실 건가요?"}


def package_to_text(package: dict, key: str, default: str = "") -> str:
    value = package.get(key, default)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def package_key(row: dict) -> str:
    return row.get("url", row.get("id", row.get("title", "")))


def expansions_from_package(package: dict) -> dict[str, str]:
    shorts = package.get("shorts", {}) if isinstance(package.get("shorts"), dict) else {}
    threads = package.get("threads", {}) if isinstance(package.get("threads"), dict) else {}
    return {"30초 쇼츠": shorts.get("30s", ""), "60초 쇼츠": shorts.get("60s", ""), "90초 쇼츠": shorts.get("90s", ""), "Threads 5": threads.get("5_post", ""), "Threads 10": threads.get("10_post", ""), "카드뉴스": json.dumps(package.get("card_news", {}), ensure_ascii=False, indent=2), "썸네일": "\n".join(package.get("thumbnail_text", [])) if isinstance(package.get("thumbnail_text"), list) else str(package.get("thumbnail_text", "")), "제목": "\n".join(package.get("titles", [])) if isinstance(package.get("titles"), list) else str(package.get("titles", ""))}


def render_quality(quality: dict) -> None:
    if not quality:
        st.info("아직 품질검사가 없습니다.")
        return
    st.metric("종합 점수", quality.get("overall_score", 0))
    score_cols = st.columns(4)
    scores = quality.get("scores", {})
    for idx, (name, value) in enumerate(scores.items()):
        score_cols[idx % 4].metric(name, value)
    critical_failures = quality.get("critical_failures", [])
    warnings = quality.get("warnings", [])
    if critical_failures:
        st.error("\n".join([f"- {item}" for item in critical_failures]))
    if warnings:
        st.warning("\n".join([f"- {item}" for item in warnings]))
    if quality.get("rewrite_guidance"):
        with st.expander("재작성 가이드", expanded=False):
            for item in quality.get("rewrite_guidance", []):
                st.write(f"- {item}")
    if quality.get("passed"):
        st.success("품질 기준을 통과했습니다.")
    else:
        st.info("품질 기준 미달입니다. 품질개선 워크벤치나 퀵패널에서 재작성하세요.")


def run_quality_improvement(
    selected_key: str,
    selected_row: dict,
    source_text: str,
    analysis: dict,
    blueprint: dict,
    script: str,
    quality: dict,
    model: str,
    temperature: float,
    mode: str,
    user_direction: str,
) -> tuple[str, dict, str | None]:
    if improve_failed_script is None:
        return script, quality, "script_improver.py를 불러오지 못했습니다."
    if not script:
        return script, quality, "개선할 대본이 없습니다."
    if not quality and quality_check_live_script:
        quality = quality_check_live_script(script)
    improved, error = improve_failed_script(
        source_text=source_text,
        analysis=analysis,
        blueprint=blueprint,
        current_script=script,
        quality=quality or {},
        row=selected_row,
        model=model,
        temperature=temperature,
        improvement_mode=mode,
        user_direction=user_direction,
    )
    if error:
        return script, quality, error
    new_quality = quality_check_live_script(improved) if quality_check_live_script else {}
    st.session_state.longform_scripts[selected_key] = improved
    st.session_state.quality_checks[selected_key] = new_quality
    return improved, new_quality, None


st.title("Story Pattern Lab")
st.caption("자동 본문 수집 · 라이브 사연 상담형 반존대 대본 · 사주/점성술 화자성 · Supabase 히스토리")

initial_state = {
    "stories": [],
    "approved": [],
    "collection_logs": [],
    "rows": [],
    "history_rows": [],
    "source_texts": {},
    "story_analyses": {},
    "live_blueprints": {},
    "longform_scripts": {},
    "quality_checks": {},
    "derivative_assets": {},
    "production_packages": {},
}
for key, value in initial_state.items():
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
    temperature = st.slider("창의성", 0.1, 1.2, 0.78, 0.05)
    auto_improve_after_generation = st.checkbox("생성 직후 품질 미달이면 자동 개선", value=True)
    auto_improve_rounds = st.slider("자동 개선 최대 회차", 1, 3, 2, 1, disabled=not auto_improve_after_generation)
    if LLM_PIPELINE_IMPORT_ERROR:
        st.error(f"LLM 파이프라인 로드 실패: {LLM_PIPELINE_IMPORT_ERROR}")
    if SCRIPT_IMPROVER_IMPORT_ERROR:
        st.error(f"품질개선 모듈 로드 실패: {SCRIPT_IMPROVER_IMPORT_ERROR}")
    if st.button("Supabase 테스트", use_container_width=True):
        _, err = load_packages(1)
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
col4.metric("본문 확보", len(st.session_state.source_texts))
col5.metric("히스토리", len(st.session_state.history_rows))

if st.session_state.collection_logs:
    with st.expander("수집 로그", expanded=False):
        for log in st.session_state.collection_logs:
            st.write(f"- {log}")

tabs = st.tabs(["📡 소스", "🏆 리더보드", "🎙️ 라이브 제작실", "🗂️ 히스토리", "🧪 원칙/DB"])

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
            rows.append({"id": f"{item.source}-{item.rank_position}-{abs(hash(item.url))}", "badge": status_badge(scores["production_score"]), "region": item.region, "source": item.source, "angle": story_angle(item.title), "title": item.title, "url": item.url, "rank": item.rank_position, "posted_at": posted_at_str, "fresh_min": minutes_posted, "like_count": item.like_count, "comment_count": item.comment_count, "view_count": item.view_count, "original_excerpt": item.original_excerpt, **scores})
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
    st.subheader("라이브 사연 상담 제작실")
    rows = st.session_state.get("rows", [])
    if not rows:
        st.info("먼저 리더보드에서 소재를 수집/생성해주세요.")
    else:
        idx = st.radio("제작할 소재", options=list(range(len(rows))), format_func=lambda i: f"{i + 1}. {rows[i]['title'][:60]} | {rows[i]['source']} | {rows[i]['region']}")
        selected = rows[idx]
        key = package_key(selected)
        source_text = st.session_state.source_texts.get(key, selected.get("original_excerpt", ""))
        analysis = st.session_state.story_analyses.get(key, infer_analysis(selected))
        blueprint = st.session_state.live_blueprints.get(key, {})
        longform = st.session_state.longform_scripts.get(key, "")
        quality = st.session_state.quality_checks.get(key, {})
        derivatives = st.session_state.derivative_assets.get(key, {})
        package = st.session_state.production_packages.get(key)

        metric_cols = st.columns(6)
        metric_cols[0].metric("Production", selected.get("production_score", 0))
        metric_cols[1].metric("Viral", selected.get("viral_score", 0))
        metric_cols[2].metric("Debate", selected.get("debate_score", 0))
        metric_cols[3].metric("본문 길이", len(source_text or ""))
        metric_cols[4].metric("댓글", selected.get("comment_count", 0) or "N/A")
        metric_cols[5].metric("조회수", selected.get("view_count", 0) or "N/A")

        st.markdown("### ① 소재 카드")
        st.write(f"**제목:** {selected['title']}")
        st.write(f"**소스:** {selected['source']} / {selected['region']}")
        st.write(f"**URL:** {selected['url']}")

        st.markdown("### ② 본문 자동 가져오기")
        fetch_col1, fetch_col2 = st.columns([1, 2])
        if fetch_col1.button("본문 자동 가져오기", type="primary", use_container_width=True):
            if fetch_article_body is None:
                st.error("source_fetcher.py를 불러오지 못했습니다.")
            else:
                with st.spinner("본문을 자동으로 가져오는 중..."):
                    result = fetch_article_body(selected["url"], selected.get("source", ""))
                if result.ok:
                    st.session_state.source_texts[key] = result.body
                    source_text = result.body
                    st.success(f"본문 확보 완료: {result.length}자 / {result.method}")
                else:
                    st.session_state.source_texts[key] = result.body or selected.get("original_excerpt", "")
                    source_text = st.session_state.source_texts[key]
                    st.warning(result.error or "본문 추출 실패")
        allow_title_mode = fetch_col2.checkbox("본문 부족해도 제목 기반 테스트 허용", value=False)
        source_text = st.text_area("제작 재료 본문 / 요약", value=source_text, height=220)
        st.session_state.source_texts[key] = source_text

        ready_for_llm = len(source_text or "") >= 500 or allow_title_mode
        if not ready_for_llm:
            st.warning("본문이 500자 미만입니다. 자동 본문 가져오기를 먼저 실행하거나 테스트 모드를 켜세요.")

        st.markdown("### ③ 사연 해부")
        if st.button("1차 LLM: 사연 해부하기", disabled=not ready_for_llm or analyze_story is None, use_container_width=True):
            with st.spinner("사연의 핵심 갈등, 채팅 포인트, 사주/점성술 렌즈를 해부 중..."):
                result, error = analyze_story(source_text, selected, llm_model, temperature)
            if error:
                st.error(error)
            else:
                st.session_state.story_analyses[key] = result
                analysis = result
                st.success("사연 해부 완료")
        st.json(analysis)

        st.markdown("### ④ 라이브 상담 구조 설계")
        if st.button("2차 LLM: 라이브 구조 설계하기", disabled=not bool(analysis) or build_live_blueprint is None, use_container_width=True):
            with st.spinner("반말/존댓말 혼합 라이브 상담 구조를 설계 중..."):
                result, error = build_live_blueprint(analysis, selected, llm_model, temperature)
            if error:
                st.error(error)
            else:
                st.session_state.live_blueprints[key] = result
                blueprint = result
                st.success("라이브 구조 설계 완료")
        if blueprint:
            st.json(blueprint)

        st.markdown("### ⑤ 10분 롱폼 대본")
        if st.button("3차 LLM: 10분 대본 쓰기", disabled=not bool(blueprint) or write_live_longform is None, type="primary", use_container_width=True):
            with st.spinner("라이브 사연 상담형 반존대 대본을 작성 중..."):
                script, error = write_live_longform(source_text, analysis, blueprint, selected, llm_model, temperature)
            if error:
                st.error(error)
            else:
                st.session_state.longform_scripts[key] = script
                longform = script
                if quality_check_live_script:
                    st.session_state.quality_checks[key] = quality_check_live_script(script)
                    quality = st.session_state.quality_checks[key]
                if quality and not quality.get("passed") and auto_improve_after_generation and improve_failed_script:
                    current_script = script
                    current_quality = quality
                    improve_logs: list[str] = []
                    with st.spinner("품질 미달 감지: 자동 개선 루프 실행 중..."):
                        for round_idx in range(1, auto_improve_rounds + 1):
                            current_script, current_quality, improve_error = run_quality_improvement(
                                selected_key=key,
                                selected_row=selected,
                                source_text=source_text,
                                analysis=analysis,
                                blueprint=blueprint,
                                script=current_script,
                                quality=current_quality,
                                model=llm_model,
                                temperature=temperature,
                                mode="품질검사 기준 통과용 전면 재작성",
                                user_direction="품질검사 실패 항목을 우선 해결하고, 분량/타임코드/후킹/상담성/캐릭터성/민감주제 처리를 모두 보강하세요.",
                            )
                            if improve_error:
                                improve_logs.append(f"{round_idx}회차 실패: {improve_error}")
                                break
                            improve_logs.append(f"{round_idx}회차 개선: 점수 {current_quality.get('overall_score', 'N/A')} / 통과 {'YES' if current_quality.get('passed') else 'NO'}")
                            if current_quality.get("passed"):
                                break
                    longform = current_script
                    quality = current_quality
                    st.session_state.last_auto_improve_logs = improve_logs
                    if quality.get("passed"):
                        st.success("10분 대본 생성 후 자동 품질개선까지 통과했습니다.")
                    else:
                        st.warning("자동 품질개선을 실행했지만 아직 기준 미달입니다. 아래 품질개선 패널에서 PD 디렉션을 추가해 다시 개선하세요.")
                st.success("10분 대본 생성 완료")
        edited_longform = st.text_area("10분 롱폼 대본", value=longform, height=520)
        if edited_longform != longform:
            st.session_state.longform_scripts[key] = edited_longform
            longform = edited_longform
            st.session_state.quality_checks.pop(key, None)
            quality = {}
            st.info("대본이 수정되어 기존 품질검사 결과를 초기화했습니다. 다시 품질검사를 실행하세요.")

        st.markdown("### ⑥ 품질검사")
        if st.button("대본 품질검사", disabled=not bool(longform) or quality_check_live_script is None, use_container_width=True):
            st.session_state.quality_checks[key] = quality_check_live_script(longform)
            quality = st.session_state.quality_checks[key]
        render_quality(quality)
        quality_passed = bool(quality.get("passed")) if quality else False
        force_failed_output = False
        quality_missing = bool(longform) and not bool(quality)
        if quality_missing:
            st.info("파생 콘텐츠나 저장 전에 품질검사를 먼저 실행하세요.")
        if longform and quality and not quality_passed:
            st.error("현재 대본은 발행 기준 미달입니다. 기본적으로 파생 콘텐츠 생성과 저장을 막습니다.")
            st.markdown("#### 품질개선 바로 실행")
            st.caption("다른 페이지로 이동하지 않고, 현재 제작실에서 실패 리포트 기반 재작성을 바로 실행합니다.")
            direction_key = f"quality_improve_direction_{key}"
            user_direction = st.text_area(
                "PD 디렉션",
                value=st.session_state.get(direction_key, ""),
                height=120,
                placeholder="예: 오프닝을 더 세게. 첫 3초 안에 갈등을 박고, 상담 파트는 상대가 회피/역공/사과할 때 실제로 보낼 문장까지 넣어줘.",
                key=direction_key,
            )
            improve_mode = st.selectbox(
                "개선 모드",
                [
                    "품질검사 기준 통과용 전면 재작성",
                    "사용자 디렉션 최우선 전면 재작성",
                    "후킹/라이브감 집중 개선",
                    "상담 디테일 집중 개선",
                    "캐릭터성/사주점성술 화자성 집중 개선",
                    "로컬라이징/민감표현 집중 개선",
                ],
                key=f"quality_improve_mode_{key}",
            )
            if build_rewrite_brief:
                with st.expander("자동 재작성 브리프", expanded=False):
                    st.text_area("브리프", build_rewrite_brief(quality), height=180, disabled=True)
            improve_cols = st.columns(2)
            if improve_cols[0].button("품질 미달 대본 1회 개선", disabled=improve_failed_script is None, type="primary", use_container_width=True, key=f"improve_once_{key}"):
                with st.spinner("품질검사 실패 항목을 반영해 대본을 1회 재작성 중..."):
                    longform, quality, improve_error = run_quality_improvement(
                        selected_key=key,
                        selected_row=selected,
                        source_text=source_text,
                        analysis=analysis,
                        blueprint=blueprint,
                        script=longform,
                        quality=quality,
                        model=llm_model,
                        temperature=temperature,
                        mode=improve_mode,
                        user_direction=user_direction,
                    )
                if improve_error:
                    st.error(improve_error)
                else:
                    st.success(f"1회 개선 완료. 새 점수: {quality.get('overall_score', 'N/A')} / 통과: {'YES' if quality.get('passed') else 'NO'}")
                    st.rerun()
            if improve_cols[1].button("통과할 때까지 자동 개선", disabled=improve_failed_script is None, use_container_width=True, key=f"improve_until_pass_{key}"):
                current_script = longform
                current_quality = quality
                logs: list[str] = []
                with st.spinner("품질검사 통과를 목표로 최대 3회 자동 개선 중..."):
                    for round_idx in range(1, 4):
                        current_script, current_quality, improve_error = run_quality_improvement(
                            selected_key=key,
                            selected_row=selected,
                            source_text=source_text,
                            analysis=analysis,
                            blueprint=blueprint,
                            script=current_script,
                            quality=current_quality,
                            model=llm_model,
                            temperature=temperature,
                            mode=improve_mode,
                            user_direction=user_direction,
                        )
                        if improve_error:
                            logs.append(f"{round_idx}회차 실패: {improve_error}")
                            break
                        logs.append(f"{round_idx}회차 개선: 점수 {current_quality.get('overall_score', 'N/A')} / 통과 {'YES' if current_quality.get('passed') else 'NO'}")
                        if current_quality.get("passed"):
                            break
                st.session_state.last_auto_improve_logs = logs
                if logs:
                    st.info("\n".join(f"- {item}" for item in logs))
                st.rerun()
            force_failed_output = st.checkbox(
                "테스트 목적으로만 품질 미달 대본 진행 허용",
                value=False,
                key=f"force_failed_output_{key}",
            )

        if st.session_state.get("last_auto_improve_logs"):
            with st.expander("최근 자동 개선 로그", expanded=False):
                for item in st.session_state.last_auto_improve_logs:
                    st.write(f"- {item}")

        st.markdown("### ⑦ 파생 콘텐츠")
        output_locked = bool(longform) and (quality_missing or (bool(quality) and not quality_passed and not force_failed_output))
        if st.button("4차 LLM: 쇼츠/Threads/카드뉴스 만들기", disabled=not bool(longform) or generate_derivatives is None or output_locked, use_container_width=True):
            with st.spinner("롱폼 대본 기반으로 파생 콘텐츠 생성 중..."):
                result, error = generate_derivatives(longform, analysis, selected, llm_model, temperature)
            if error:
                st.error(error)
            else:
                st.session_state.derivative_assets[key] = result
                derivatives = result
                st.success("파생 콘텐츠 생성 완료")
        if derivatives:
            exp = expansions_from_package(derivatives)
            der_tabs = st.tabs(["쇼츠", "Threads", "카드뉴스", "제목/썸네일", "JSON"])
            with der_tabs[0]:
                st.text_area("30초 쇼츠", exp["30초 쇼츠"], height=140)
                st.text_area("60초 쇼츠", exp["60초 쇼츠"], height=180)
                st.text_area("90초 쇼츠", exp["90초 쇼츠"], height=220)
            with der_tabs[1]:
                st.text_area("5-post Thread", exp["Threads 5"], height=220)
                st.text_area("10-post Thread", exp["Threads 10"], height=320)
            with der_tabs[2]:
                cards = derivatives.get("card_news", {}).get("8_cards", []) if isinstance(derivatives.get("card_news"), dict) else []
                if cards:
                    for i, card in enumerate(cards, start=1):
                        with st.expander(f"{i}장 · {card.get('title', '제목 없음')}", expanded=i == 1):
                            st.write(card.get("body", ""))
                            st.caption(card.get("design_note", ""))
                            st.text_area(f"{i}장 이미지 프롬프트", card.get("image_prompt", ""), height=90)
                else:
                    st.text_area("카드뉴스 JSON", exp["카드뉴스"], height=360)
            with der_tabs[3]:
                st.text_area("썸네일 문구", exp["썸네일"], height=120)
                st.text_area("제목 후보", exp["제목"], height=200)
                st.text_area("댓글 질문", derivatives.get("comment_question", ""), height=100)
            with der_tabs[4]:
                st.json(derivatives)

        st.markdown("### ⑧ 저장")
        if output_locked:
            st.warning("품질 미달 대본은 패키지 조립/Supabase 저장 전에 개선이 필요합니다.")
        if st.button("제작 패키지 조립", disabled=not bool(longform) or output_locked, use_container_width=True):
            if build_package:
                package = build_package(selected, source_text, analysis, blueprint, longform, quality, derivatives)
            else:
                package = fallback_package(selected, analysis)
                package["longform_script"] = longform
            st.session_state.production_packages[key] = package
            st.success("제작 패키지 조립 완료")
        package = st.session_state.production_packages.get(key)
        if package:
            save_col, down_col = st.columns(2)
            if save_col.button("Supabase에 저장", disabled=output_locked, use_container_width=True):
                result, error = save_package(selected, package)
                if error:
                    st.error(error)
                else:
                    st.success("Supabase 저장 완료")
                    if isinstance(result, list):
                        st.session_state.history_rows = result + st.session_state.history_rows
            down_col.download_button("패키지 JSON 다운로드", json.dumps(package, ensure_ascii=False, indent=2), file_name="live_advice_package.json", mime="application/json", use_container_width=True)
            with st.expander("최종 패키지 JSON"):
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
    st.markdown("### v0.5 제작 플로우")
    st.write("본문 자동 가져오기 → 사연 해부 → 라이브 구조 설계 → 10분 대본 → 품질검사 → 파생 콘텐츠 → 저장")

st.caption("Story Pattern Lab v0.5 · 라이브 사연 상담형 반존대 대본 제작기")
