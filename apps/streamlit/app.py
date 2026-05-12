from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log10
from typing import Optional

import feedparser
import streamlit as st
from dateutil import parser as date_parser

st.set_page_config(page_title="Story Pattern Lab", page_icon="🔮", layout="wide")

DEFAULT_SOURCES = {
    "Reddit AITA": "https://www.reddit.com/r/AmItheAsshole/.rss",
    "Reddit Relationship Advice": "https://www.reddit.com/r/relationship_advice/.rss",
    "Reddit TrueOffMyChest": "https://www.reddit.com/r/TrueOffMyChest/.rss",
    "Reddit BestOfRedditorUpdates": "https://www.reddit.com/r/BestofRedditorUpdates/.rss",
}


@dataclass
class StoryItem:
    source: str
    title: str
    url: str
    posted_at: Optional[datetime]
    rank_position: int
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0


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


def log_score(value: int, scale: float) -> float:
    if value <= 0:
        return 0
    return max(0, min(100, log10(value + 1) * scale))


def calculate_basic_scores(item: StoryItem) -> dict[str, float]:
    rank_score = max(0, min(100, 100 - (item.rank_position - 1) * 3))
    like_score = log_score(item.like_count, 18)
    comment_score = log_score(item.comment_count, 22)
    view_score = log_score(item.view_count, 12)
    reaction_score = like_score * 0.35 + comment_score * 0.45 + view_score * 0.20
    debate_score = min(100, comment_score * 0.25)
    viral_score = min(100, reaction_score * 0.30 + debate_score * 0.20 + rank_score * 0.50)
    return {"viral_score": round(viral_score, 2), "debate_score": round(debate_score, 2), "rank_score": round(rank_score, 2)}


def collect_rss(source_name: str, rss_url: str, limit: int) -> list[StoryItem]:
    feed = feedparser.parse(rss_url)
    items: list[StoryItem] = []
    for index, entry in enumerate(feed.entries[:limit], start=1):
        title = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()
        if not title or not url:
            continue
        published = getattr(entry, "published", None) or getattr(entry, "updated", None)
        items.append(StoryItem(source=source_name, title=title, url=url, posted_at=parse_datetime(published), rank_position=index))
    return items


def story_angle(title: str) -> str:
    lower = title.lower()
    if "wedding" in lower or "fiancé" in lower or "fiance" in lower or "husband" in lower or "wife" in lower:
        return "Wedding / Relationship Drama"
    if "mother" in lower or "father" in lower or "parent" in lower or "family" in lower:
        return "Family Conflict"
    if "work" in lower or "boss" in lower or "coworker" in lower or "job" in lower:
        return "Workplace Betrayal"
    if "friend" in lower or "roommate" in lower:
        return "Friend / Roommate Drama"
    return "General Storytime"


def make_script_stub(title: str) -> str:
    return f"""She thought this was just one strange moment.

But the story was not really about that.

It started with this: {title}

Most people would focus on the drama.
But the real hook is the pattern behind it.

Every time someone crossed a line, the main character was made to feel dramatic for reacting.

And that is why people comment.
Because everyone knows what it feels like to notice something early and still question yourself.

So tell me.
Was this an overreaction, or did they see the pattern before everyone else?"""


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
st.caption("초보 테스트용 Streamlit 버전. RSS 소재 수집 → 점수 정렬 → 대본 초안 생성까지 한 화면에서 확인합니다.")

with st.sidebar:
    st.header("수집 설정")
    selected_sources = st.multiselect("수집할 소스", options=list(DEFAULT_SOURCES.keys()), default=["Reddit AITA", "Reddit Relationship Advice"])
    custom_rss = st.text_input("추가 RSS URL", placeholder="https://example.com/feed.xml")
    per_source_limit = st.slider("소스당 수집 개수", 5, 50, 15, 5)
    collect_button = st.button("소재 수집하기", type="primary")

if "stories" not in st.session_state:
    st.session_state.stories = []

if collect_button:
    collected: list[StoryItem] = []
    for source_name in selected_sources:
        collected.extend(collect_rss(source_name, DEFAULT_SOURCES[source_name], per_source_limit))
    if custom_rss:
        collected.extend(collect_rss("Custom RSS", custom_rss, per_source_limit))
    st.session_state.stories = collected

stories: list[StoryItem] = st.session_state.stories

col1, col2, col3, col4 = st.columns(4)
col1.metric("수집 소재", len(stories))
col2.metric("소스", len(set(item.source for item in stories)))
col3.metric("분석 대기", len(stories))
col4.metric("브랜드", "Mira Files")

if not stories:
    st.info("왼쪽에서 소스를 고르고 '소재 수집하기'를 눌러보세요. 일단 Reddit RSS로 흐름부터 봅니다.")
    st.stop()

rows = []
for item in stories:
    scores = calculate_basic_scores(item)
    rows.append({
        "viral_score": scores["viral_score"],
        "debate_score": scores["debate_score"],
        "rank": item.rank_position,
        "source": item.source,
        "angle": story_angle(item.title),
        "title": item.title,
        "url": item.url,
    })
rows = sorted(rows, key=lambda row: row["viral_score"], reverse=True)

st.subheader("Story Radar")
st.dataframe(rows, use_container_width=True, hide_index=True, column_order=["viral_score", "debate_score", "rank", "source", "angle", "title", "url"])

st.subheader("소재 상세 / 대본 초안")
selected_title = st.selectbox("소재 선택", [row["title"] for row in rows])
selected = next(row for row in rows if row["title"] == selected_title)

left, right = st.columns([1, 1])
with left:
    st.markdown("### 소재 카드")
    st.write(f"**Source:** {selected['source']}")
    st.write(f"**Angle:** {selected['angle']}")
    st.write(f"**Viral Score:** {selected['viral_score']}")
    st.write(f"**Debate Score:** {selected['debate_score']}")
    st.write(f"**URL:** {selected['url']}")

with right:
    st.markdown("### Shorts Script Draft")
    st.text_area("대본 초안", make_script_stub(selected_title), height=360)

st.caption("현재 Streamlit 버전은 초보 테스트용입니다. 이후 Reddit API, LLM 대본 생성, DB 저장을 순서대로 붙입니다.")
