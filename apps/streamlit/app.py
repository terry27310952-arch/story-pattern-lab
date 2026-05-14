from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from html import unescape
from math import log10
from re import sub
from typing import Optional

import feedparser
import streamlit as st
from dateutil import parser as date_parser

st.set_page_config(page_title="Story Pattern Lab", page_icon="🔮", layout="wide")

OVERSEAS_SOURCES = {
    "Reddit AITA": {
        "url": "https://www.reddit.com/r/AmItheAsshole/.rss",
        "category": "AITA / Moral Debate",
        "status": "Active RSS",
        "region": "해외",
    },
    "Reddit Relationship Advice": {
        "url": "https://www.reddit.com/r/relationship_advice/.rss",
        "category": "Relationship Drama",
        "status": "Active RSS",
        "region": "해외",
    },
    "Reddit TrueOffMyChest": {
        "url": "https://www.reddit.com/r/TrueOffMyChest/.rss",
        "category": "Confession / Personal Story",
        "status": "Active RSS",
        "region": "해외",
    },
    "Reddit BestOfRedditorUpdates": {
        "url": "https://www.reddit.com/r/BestofRedditorUpdates/.rss",
        "category": "Update Story / Longform",
        "status": "Active RSS",
        "region": "해외",
    },
}

DOMESTIC_SOURCES = [
    {"site": "디시인사이드", "category": "익명 커뮤니티", "status": "검토 필요", "note": "약관/자동수집 제한 검토 후 결정"},
    {"site": "네이트판", "category": "연애/결혼/가족 사연", "status": "후보", "note": "공개 인기글 중심 가능성 검토"},
    {"site": "더쿠", "category": "이슈/썰", "status": "후보", "note": "원문 저장 금지 원칙 필요"},
    {"site": "인스티즈", "category": "커뮤니티 썰", "status": "후보", "note": "로그인/약관 검토 필요"},
    {"site": "쭉빵닷컴", "category": "여성 커뮤니티", "status": "보류", "note": "접근/약관/개인정보 위험도 확인 필요"},
    {"site": "보배드림", "category": "사건/가족/직장", "status": "후보", "note": "공개 게시판 지표 중심 검토"},
    {"site": "블라인드", "category": "직장 썰", "status": "보류", "note": "로그인 기반, 자동 수집 부적합 가능성 높음"},
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


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(value)
    text = sub(r"<[^>]+>", " ", text)
    text = sub(r"\s+", " ", text).strip()
    return text[:1200]


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
    if "wedding" in lower or "fiancé" in lower or "fiance" in lower or "husband" in lower or "wife" in lower:
        return "Wedding / Relationship Drama"
    if "mother" in lower or "father" in lower or "parent" in lower or "family" in lower:
        return "Family Conflict"
    if "work" in lower or "boss" in lower or "coworker" in lower or "job" in lower:
        return "Workplace Betrayal"
    if "friend" in lower or "roommate" in lower:
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

with st.sidebar:
    st.header("수집 설정")
    selected_sources = st.multiselect("해외 소스", options=list(OVERSEAS_SOURCES.keys()), default=["Reddit AITA", "Reddit Relationship Advice"])
    per_source_limit = st.slider("소스당 수집 개수", 5, 50, 15, 5)
    collect_button = st.button("실시간 후보 수집", type="primary")
    st.divider()
    st.caption("현재는 RSS를 버튼 클릭 시점에 읽는 on-demand 수집입니다. Reddit API/스냅샷 저장 후 near real-time으로 확장합니다.")

if collect_button:
    collected: list[StoryItem] = []
    for source_name in selected_sources:
        collected.extend(collect_rss(source_name, OVERSEAS_SOURCES[source_name], per_source_limit))
    st.session_state.stories = collected

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

tabs = st.tabs(["📡 사이트별 소스", "🏆 스코어 리더보드", "🔎 소재 상세", "✅ 제작 확정", "🧪 재가공 원칙"])

with tabs[0]:
    st.subheader("해외 소스 리스트")
    overseas_rows = []
    for name, meta in OVERSEAS_SOURCES.items():
        overseas_rows.append({"site": name, "region": meta["region"], "category": meta["category"], "status": meta["status"], "url": meta["url"]})
    st.dataframe(overseas_rows, use_container_width=True, hide_index=True)

    st.subheader("국내 소스 후보")
    st.dataframe(DOMESTIC_SOURCES, use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("스코어 리더보드")
    if not stories:
        st.info("왼쪽에서 소스를 고르고 '실시간 후보 수집'을 눌러주세요.")
    else:
        rows = []
        for idx, item in enumerate(stories, start=1):
            scores = calculate_scores(item)
            row_id = f"{item.source}-{item.rank_position}-{abs(hash(item.url))}"
            rows.append(
                {
                    "id": row_id,
                    "badge": status_badge(scores["production_score"]),
                    "viral_score": scores["viral_score"],
                    "velocity_score": scores["velocity_score"],
                    "debate_score": scores["debate_score"],
                    "production_score": scores["production_score"],
                    "risk_score": scores["risk_score"],
                    "fresh_min": minutes_since(item.posted_at),
                    "rank": item.rank_position,
                    "source": item.source,
                    "angle": story_angle(item.title),
                    "title": item.title,
                    "url": item.url,
                    "collected_at": item.collected_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "original_excerpt": item.original_excerpt,
                }
            )
        rows = sorted(rows, key=lambda row: row["production_score"], reverse=True)
        st.session_state.rows = rows

        sort_key = st.selectbox("정렬 기준", ["production_score", "viral_score", "velocity_score", "debate_score", "risk_score", "fresh_min"], index=0)
        reverse = sort_key != "risk_score" and sort_key != "fresh_min"
        rows_sorted = sorted(rows, key=lambda row: row[sort_key] if row[sort_key] is not None else 999999, reverse=reverse)
        st.dataframe(
            rows_sorted,
            use_container_width=True,
            hide_index=True,
            column_order=["badge", "production_score", "viral_score", "velocity_score", "debate_score", "risk_score", "fresh_min", "rank", "source", "angle", "title", "url"],
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
            st.write(f"**소스:** {selected['source']}")
            st.write(f"**분류:** {selected['angle']}")
            st.write(f"**수집 시각:** {selected['collected_at']}")
            st.write(f"**원문 링크:** {selected['url']}")
            st.text_area("원문 요약 / RSS excerpt", selected["original_excerpt"] or "RSS에서 제공한 요약이 없습니다.", height=160)
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
    st.write("3. 스냅샷 저장으로 실시간 변화량 계산")
    st.write("4. LLM 연결로 원문 요약, 한글 번역, 10분 대본 생성")
    st.write("5. 쇼츠, 쓰레드, 카드뉴스 확장 자동화")

st.caption("현재 버전은 Phase 1 Streamlit 대시보드 고도화입니다. 실시간 API/DB/LLM은 다음 단계에서 연결합니다.")
