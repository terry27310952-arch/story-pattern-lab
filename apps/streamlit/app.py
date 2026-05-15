from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from math import log10
from re import search, sub
from typing import Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import feedparser
import streamlit as st
from dateutil import parser as date_parser

st.set_page_config(page_title="Story Pattern Lab", page_icon="🔮", layout="wide")

USER_AGENT = "Mozilla/5.0 StoryPatternLab/0.1; public-list-metadata-only"

OVERSEAS_SOURCES = {
    "Reddit AITA": {"url": "https://www.reddit.com/r/AmItheAsshole/.rss", "category": "AITA / Moral Debate", "status": "Active RSS", "region": "해외"},
    "Reddit Relationship Advice": {"url": "https://www.reddit.com/r/relationship_advice/.rss", "category": "Relationship Drama", "status": "Active RSS", "region": "해외"},
    "Reddit TrueOffMyChest": {"url": "https://www.reddit.com/r/TrueOffMyChest/.rss", "category": "Confession / Personal Story", "status": "Active RSS", "region": "해외"},
    "Reddit BestOfRedditorUpdates": {"url": "https://www.reddit.com/r/BestofRedditorUpdates/.rss", "category": "Update Story / Longform", "status": "Active RSS", "region": "해외"},
}

DOMESTIC_COLLECTABLE_SOURCES = {
    "네이트판 랭킹": {
        "url": "https://pann.nate.com/talk/ranking",
        "category": "연애/결혼/가족 사연",
        "status": "실험 수집",
        "region": "국내",
        "parser": "nate_pann",
        "note": "공개 랭킹 목록에서 제목/URL 중심 수집",
    },
    "보배드림 베스트": {
        "url": "https://www.bobaedream.co.kr/list?code=best",
        "category": "사건/가족/직장/이슈",
        "status": "실험 수집",
        "region": "국내",
        "parser": "bobaedream",
        "note": "공개 베스트 목록에서 제목/URL 중심 수집",
    },
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

STATUS_OPTIONS = ["Collected", "Scored", "Analyzed", "Candidate", "Approved", "Scripted", "Expanded", "Rejected", "Archived"]

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


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(value)
    text = sub(r"<[^>]+>", " ", text)
    text = sub(r"\s+", " ", text).strip()
    return text[:1200]


def decode_html(raw: bytes, content_type: str = "") -> str:
    charset_match = search(r"charset=([\w-]+)", content_type or "")
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
    return {
        "viral_score": round(viral_score, 2),
        "velocity_score": round(velocity_score, 2),
        "debate_score": round(debate_score, 2),
        "production_score": round(production_score, 2),
        "risk_score": round(risk_score, 2),
        "freshness_score": round(freshness_score, 2),
        "rank_score": round(rank_score, 2),
    }


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
        items.append(
            StoryItem(
                source=source_name,
                region=source_meta["region"],
                category=source_meta["category"],
                title=title,
                url=url,
                original_excerpt=summary,
                posted_at=parse_datetime(published),
                collected_at=collected_at,
                rank_position=index,
            )
        )
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
        items.append(
            StoryItem(
                source=source_name,
                region=source_meta["region"],
                category=source_meta["category"],
                title=text[:180],
                url=url,
                original_excerpt="공개 목록에서 제목과 링크만 수집했습니다. 원문 확인은 원문 링크에서 진행합니다.",
                posted_at=None,
                collected_at=collected_at,
                rank_position=len(items) + 1,
            )
        )
        if len(items) >= limit:
            break

    return items, f"{source_name} 수집 완료: {len(items)}개"


def pseudo_translate(text: str) -> str:
    if not text:
        return "번역할 원문 요약이 없습니다. Reddit API/LLM 연결 후 원문 번역을 고도화합니다."
    return "[한글 번역 예정] " + text[:600]


def infer_analysis(row: dict) -> dict[str, str]:
    return {
        "core_summary": f"이 소재는 '{row['title']}'에서 시작되는 {row['angle']} 유형의 사연입니다.",
        "core_conflict": "주인공이 불편함을 감지했지만 주변 인물의 반응 때문에 스스로를 의심하게 되는 구조입니다.",
        "relationship_map": "주인공 / 갈등 유발 인물 / 주변 압박 인물의 삼각 구도로 재구성할 수 있습니다.",
        "red_flag": "문제의 사건 자체보다, 사건 이후 상대가 책임을 회피하거나 감정을 축소하는 태도가 핵심 레드플래그입니다.",
        "comment_trigger": "시청자는 '예민한 반응인가, 조기 경고를 본 것인가'로 갈릴 가능성이 높습니다.",
        "pattern_insight": "Most people saw drama. She saw the pattern. 이 방향으로 관계 패턴을 해석합니다.",
        "risk_note": "원문 표현을 그대로 쓰지 않고, 인물·장소·관계 디테일을 일반화해서 재창작해야 합니다.",
    }


def make_10min_script(row: dict, analysis: dict[str, str]) -> str:
    return f"""0:00 Hook
She thought this was just one strange moment. But the pattern was already there.

0:30 Setup
The story begins with this title: {row['title']}
At first, it looks like another online drama post. But the reason this works as a longform story is not the event itself. It is the emotional pattern behind it.

1:30 First Red Flag
The first red flag is not always loud. Sometimes it is the moment someone makes the main character feel dramatic for noticing something uncomfortable.

3:00 Escalation
As the situation grows, the audience starts looking for one thing: did the main character miss the warning signs, or were they trained to ignore them?

5:00 Main Turn
This is where the story should reveal the real conflict. {analysis['core_conflict']}

6:30 Pattern Reading
Most people will focus on the drama. But the stronger angle is this: {analysis['pattern_insight']}

8:00 Reframed Ending
The ending should not simply say who was right or wrong. It should show what this moment reveals about the relationship dynamic.

9:30 Comment Question
Was this an overreaction, or did they see the pattern before everyone else?
"""


def make_expansions(row: dict) -> dict[str, str]:
    return {
        "60초 쇼츠": f"She thought it was one small problem.\nBut it started with this: {row['title']}\nMost people saw drama. She saw the pattern.\nWas it an overreaction, or an early warning?",
        "30초 쇼츠": f"Everyone focused on the drama.\nBut the real story was the pattern behind it.\n{row['title']}\nWould you walk away?",
        "Threads": f"Most people saw this as simple drama.\n\n{row['title']}\n\nBut the real question is not what happened. It is why the same boundary kept getting crossed.",
        "카드뉴스 8장": "1. 충격 제목\n2. 상황 세팅\n3. 첫 번째 이상 신호\n4. 갈등 확대\n5. 반전 포인트\n6. 관계 패턴 분석\n7. 제작용 결론\n8. 댓글 유도 질문",
        "썸네일 문구": "SHE WAS RIGHT / NOT JUST DRAMA / THE PATTERN / RED FLAG?",
        "제목 10개": "1. Everyone Saw Drama. She Saw the Pattern.\n2. They Called Her Dramatic Until the Truth Came Out\n3. This Was Not the Real Problem\n4. She Noticed the Red Flag Early\n5. The Pattern Was There the Whole Time",
    }


def status_badge(score: float) -> str:
    if score >= 75:
        return "🔥 제작 우선"
    if score >= 55:
        return "🟡 후보"
    return "⚪ 관찰"


st.markdown(
    """
    <style>
    .main { background: #080713; }
    .block-container { padding-top: 2rem; }
    div[data-testid="stMetric"] { background: #121026; border: 1px solid rgba(255,255,255,0.08); padding: 16px; border-radius: 18px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Story Pattern Lab")
st.caption("실시간 점수 · 사이트별 소스 · 리더보드 · 제작 소재 확정 · 롱폼/쇼츠/쓰레드/카드뉴스 확장 환경")

if "stories" not in st.session_state:
    st.session_state.stories = []
if "approved" not in st.session_state:
    st.session_state.approved = []
if "statuses" not in st.session_state:
    st.session_state.statuses = {}
if "collection_logs" not in st.session_state:
    st.session_state.collection_logs = []

with st.sidebar:
    st.header("수집 설정")
    selected_sources = st.multiselect("해외 RSS 소스", options=list(OVERSEAS_SOURCES.keys()), default=["Reddit AITA", "Reddit Relationship Advice"])
    selected_domestic_sources = st.multiselect("국내 공개목록 실험 소스", options=list(DOMESTIC_COLLECTABLE_SOURCES.keys()), default=[])
    per_source_limit = st.slider("소스당 수집 개수", 5, 50, 15, 5)
    collect_button = st.button("실시간 후보 수집", type="primary")
    st.divider()
    st.caption("국내 소스는 원문/댓글 저장 없이 공개 목록의 제목·URL 중심으로만 실험 수집합니다.")

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
avg_score = 0
if stories:
    avg_score = round(sum(calculate_scores(item)["viral_score"] for item in stories) / len(stories), 2)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("수집 소재", len(stories))
col2.metric("활성 소스", source_count)
col3.metric("평균 Viral", avg_score)
col4.metric("확정 소재", len(st.session_state.approved))
col5.metric("브랜드", "Mira Files")

if st.session_state.collection_logs:
    with st.expander("수집 로그", expanded=False):
        for log in st.session_state.collection_logs:
            st.write(f"- {log}")

tabs = st.tabs(["📡 사이트별 소스", "🏆 스코어 리더보드", "🔎 소재 상세", "✅ 제작 확정", "🧪 재가공 원칙"])

with tabs[0]:
    st.subheader("해외 소스 리스트")
    overseas_rows = []
    for name, meta in OVERSEAS_SOURCES.items():
        overseas_rows.append({"site": name, "region": meta["region"], "category": meta["category"], "status": meta["status"], "url": meta["url"]})
    st.dataframe(overseas_rows, use_container_width=True, hide_index=True)

    st.subheader("국내 소스 후보")
    st.dataframe(DOMESTIC_SOURCES, use_container_width=True, hide_index=True)

    st.subheader("국내 실험 수집 가능 소스")
    st.dataframe(
        [{"site": name, **meta} for name, meta in DOMESTIC_COLLECTABLE_SOURCES.items()],
        use_container_width=True,
        hide_index=True,
        column_order=["site", "region", "category", "status", "note", "url"],
    )

with tabs[1]:
    st.subheader("스코어 리더보드")
    if not stories:
        st.info("왼쪽에서 소스를 고르고 '실시간 후보 수집'을 눌러주세요.")
    else:
        rows = []
        for item in stories:
            scores = calculate_scores(item)
            row_id = f"{item.source}-{item.rank_position}-{abs(hash(item.url))}"
            # compute posted time string and per-hour metrics
            posted_at_str = None
            comments_per_hour = None
            score_per_hour = None
            minutes_posted = minutes_since(item.posted_at)
            if item.posted_at:
                posted_at_str = item.posted_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                if minutes_posted and minutes_posted > 0:
                    hours_elapsed = minutes_posted / 60.0
                    comments_per_hour = round(item.comment_count / hours_elapsed, 2) if item.comment_count else 0
                    score_per_hour = round(item.like_count / hours_elapsed, 2) if item.like_count else 0
            # build row dictionary with extended metrics
            rows.append(
                {
                    "id": row_id,
                    "badge": status_badge(scores["production_score"]),
                    "region": item.region,
                    "viral_score": scores["viral_score"],
                    "velocity_score": scores["velocity_score"],
                    "debate_score": scores["debate_score"],
                    "production_score": scores["production_score"],
                    "risk_score": scores["risk_score"],
                    "fresh_min": minutes_posted,
                    "rank": item.rank_position,
                    "source": item.source,
                    "angle": story_angle(item.title),
                    "title": item.title,
                    "url": item.url,
                    "collected_at": item.collected_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "posted_at": posted_at_str,
                    "like_count": item.like_count,
                    "comment_count": item.comment_count,
                    "view_count": item.view_count,
                    "comments_per_hour": comments_per_hour,
                    "score_per_hour": score_per_hour,
                    "original_excerpt": item.original_excerpt,
                }
            )
        # store for later use
        rows = sorted(rows, key=lambda row: row["production_score"] if row["production_score"] is not None else 0, reverse=True)
        st.session_state.rows = rows

        # allow sorting by additional columns
        sort_options = [
            "production_score",
            "viral_score",
            "velocity_score",
            "debate_score",
            "risk_score",
            "fresh_min",
            "like_count",
            "comment_count",
            "view_count",
            "comments_per_hour",
            "score_per_hour",
        ]
        sort_key = st.selectbox("정렬 기준", sort_options, index=0)
        reverse = sort_key not in ["risk_score", "fresh_min"]
        rows_sorted = sorted(
            rows,
            key=lambda row: row[sort_key] if row[sort_key] is not None else -1,
            reverse=reverse,
        )
        st.dataframe(
            rows_sorted,
            use_container_width=True,
            hide_index=True,
            column_order=[
                "badge",
                "region",
                "production_score",
                "viral_score",
                "velocity_score",
                "debate_score",
                "risk_score",
                "fresh_min",
                "like_count",
                "comment_count",
                "view_count",
                "comments_per_hour",
                "score_per_hour",
                "rank",
                "source",
                "angle",
                "title",
                "url",
            ],
        )

with tabs[2]:
    st.subheader("행 클릭 대체: 소재 선택 상세 패널")
    rows = st.session_state.get("rows", [])
    if not rows:
        st.info("먼저 리더보드에서 소재를 수집/생성해주세요.")
    else:
        selected_title = st.selectbox("상세 확인할 게시물", [row["title"] for row in rows])
        selected = next(row for row in rows if row["title"] == selected_title)
        analysis = infer_analysis(selected)

        left, right = st.columns([1, 1])
        with left:
            st.markdown("### 게시물 개요")
            st.write(f"**원문 제목:** {selected['title']}")
            st.write(f"**지역/소스:** {selected['region']} · {selected['source']}")
            st.write(f"**분류:** {selected['angle']}")
            st.write(f"**수집 시각:** {selected['collected_at']}")
            st.write(f"**원문 링크:** {selected['url']}")
            st.text_area("원문 요약 / 공개목록 excerpt", selected["original_excerpt"] or "RSS/공개목록에서 제공한 요약이 없습니다.", height=160)
            st.text_area("한글 번역", pseudo_translate(selected["original_excerpt"] or selected["title"]), height=160)

        with right:
            st.markdown("### LLM 추론 분석 초안")
            for key, value in analysis.items():
                st.write(f"**{key}:** {value}")

        status = st.selectbox("제작 상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(st.session_state.statuses.get(selected["id"], "Candidate")))
        st.session_state.statuses[selected["id"]] = status

        approve_col, script_col = st.columns(2)
        with approve_col:
            if st.button("이 소재 제작 확정", type="primary"):
                if selected not in st.session_state.approved:
                    st.session_state.approved.append(selected)
                st.session_state.statuses[selected["id"]] = "Approved"
                st.success("제작 소재로 확정했습니다.")
        with script_col:
            st.download_button("원문 링크 저장", selected["url"], file_name="source_url.txt")

        st.markdown("### 10분 롱폼 대본 초안")
        st.text_area("10분 대본", make_10min_script(selected, analysis), height=420)

        st.markdown("### 확장 제작물")
        expansion_tabs = st.tabs(["60초 쇼츠", "30초 쇼츠", "Threads", "카드뉴스", "썸네일/제목"])
        expansions = make_expansions(selected)
        with expansion_tabs[0]:
            st.text_area("60초 쇼츠", expansions["60초 쇼츠"], height=180)
        with expansion_tabs[1]:
            st.text_area("30초 쇼츠", expansions["30초 쇼츠"], height=150)
        with expansion_tabs[2]:
            st.text_area("Threads", expansions["Threads"], height=180)
        with expansion_tabs[3]:
            st.text_area("카드뉴스 8장", expansions["카드뉴스 8장"], height=220)
        with expansion_tabs[4]:
            st.text_area("썸네일 문구", expansions["썸네일 문구"], height=100)
            st.text_area("제목 10개", expansions["제목 10개"], height=180)

with tabs[3]:
    st.subheader("제작 소재 확정 보드")
    if not st.session_state.approved:
        st.info("아직 확정된 소재가 없습니다. 상세 패널에서 '이 소재 제작 확정'을 눌러주세요.")
    else:
        st.dataframe(st.session_state.approved, use_container_width=True, hide_index=True, column_order=["production_score", "viral_score", "source", "angle", "title", "url"])

with tabs[4]:
    st.subheader("원문 LLM 추론분석 및 재가공 원칙")
    for principle in REWRITE_PRINCIPLES:
        st.write(f"- {principle}")
    st.divider()
    st.markdown("### 개발 우선순위")
    st.write("1. 현재 Streamlit UI에서 소스/리더보드/상세/확정/확장 구조를 먼저 고정")
    st.write("2. Reddit API로 score, num_comments, created_utc 수집")
    st.write("3. 국내 공개목록 수집기는 제목/URL 중심으로 제한")
    st.write("4. 스냅샷 저장으로 실시간 변화량 계산")
    st.write("5. LLM 연결로 원문 요약, 한글 번역, 10분 대본 생성")
    st.write("6. 쇼츠, 쓰레드, 카드뉴스 확장 자동화")

st.caption("현재 버전은 Phase 1 Streamlit 대시보드 고도화입니다. 국내 소스는 네이트판/보배드림 공개목록 실험 수집부터 시작합니다.")
