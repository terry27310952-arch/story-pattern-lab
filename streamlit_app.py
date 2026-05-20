from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Editorial Life Intelligence Lab",
    page_icon="EL",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2.2rem; }
    [data-testid="stSidebar"] { background: #eef1f5; }
    h1, h2, h3 { letter-spacing: 0 !important; }
    .eyebrow { color: #9f302b; font-size: .78rem; font-weight: 800; text-transform: uppercase; }
    .brand-line { color: #68707d; line-height: 1.55; }
    .metric-card { padding: 1rem 1.1rem; border: 1px solid #dce1e7; border-radius: 8px; background: white; box-shadow: 0 10px 28px rgba(24,31,43,.07); }
    .metric-card span { display: block; color: #68707d; font-size: .86rem; font-weight: 700; margin-bottom: .45rem; }
    .metric-card strong { font-size: 2rem; line-height: 1; }
    .output { white-space: pre-wrap; line-height: 1.72; padding: 1.1rem; background: white; border: 1px solid #dce1e7; border-radius: 8px; }
    div.stButton > button[kind="primary"] { background: #c9443e; border-color: #c9443e; }
    div.stButton > button { border-radius: 6px; font-weight: 800; }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA: list[dict[str, Any]] = [
    {"key": "stocks", "source": "주식 / ETF", "symbol": "SPY", "title": "S&P500이 다시 고점권에서 숨을 고르는 중", "summary": "가격보다 중요한 건 포트폴리오 안에서 주식 비중이 맡은 역할이다.", "move": 0.8, "volatility": 42},
    {"key": "stocks", "source": "주식 / ETF", "symbol": "QQQ", "title": "기술주 쏠림이 수익률과 불안을 동시에 키움", "summary": "성장 자산을 남길지, 비중을 덜어낼지 판단해야 하는 구간이다.", "move": -0.4, "volatility": 61},
    {"key": "stocks", "source": "주식 / ETF", "symbol": "NVDA", "title": "AI 주도주의 기대가 다시 가격에 반영됨", "summary": "좋은 기업과 좋은 진입 가격은 같은 말이 아니다.", "move": 1.7, "volatility": 73},
    {"key": "crypto", "source": "암호화폐", "symbol": "BTC", "title": "비트코인 박스권에서 레버리지 포지션이 누적됨", "summary": "방향을 맞히기보다 내가 버틸 수 있는 변동 폭을 먼저 정해야 한다.", "move": 1.1, "volatility": 68},
    {"key": "crypto", "source": "암호화폐", "symbol": "ETH", "title": "이더리움 스테이킹과 ETF 기대가 서사를 유지함", "summary": "서사가 강할수록 내 원칙은 더 단순해야 한다.", "move": 0.5, "volatility": 57},
    {"key": "crypto", "source": "암호화폐", "symbol": "SOL", "title": "솔라나 생태계 거래량이 단기 관심을 재점화", "summary": "빠른 자산은 빠른 판단보다 작은 비중을 요구한다.", "move": 2.2, "volatility": 84},
    {"key": "macro", "source": "거시경제", "symbol": "USD/KRW", "title": "환율이 투자자의 체감 리스크를 다시 흔듦", "summary": "환율은 숫자가 아니라 내 자산 배치의 스트레스 테스트다.", "move": 0.3, "volatility": 44},
    {"key": "macro", "source": "거시경제", "symbol": "10Y", "title": "장기금리가 위험자산의 할인율을 재조정", "summary": "금리가 바뀌면 가격만이 아니라 사람들의 선택 순서도 바뀐다.", "move": -0.2, "volatility": 39},
    {"key": "wallets", "source": "지갑 / 온체인", "symbol": "FLOW", "title": "스테이블코인 유입이 위험 선호 회복을 암시", "summary": "자금 흐름은 뉴스보다 먼저 포지션의 방향을 보여줄 때가 있다.", "move": 0.9, "volatility": 52},
    {"key": "philosophy", "source": "철학 / 문장", "symbol": "EDIT", "title": "돈은 숫자가 아니라 선택이 남은 상태", "summary": "돈이 머물 구조가 없으면 높은 소득도 금방 장면 밖으로 사라진다.", "move": 0, "volatility": 28},
]

FRAMES = [
    ("남길 것", "지금 이 흐름에서 계속 가져가야 할 원칙은 무엇인가?", "남겨야 할 건 가격 예측이 아니라 반복 가능한 판단 기준입니다."),
    ("덜어낼 것", "내 계좌와 삶을 흐트러뜨리는 소음은 무엇인가?", "덜어내야 할 건 정보가 아니라 반응 속도에 중독된 습관입니다."),
    ("순서를 바꿀 것", "수익보다 먼저 배치해야 할 것은 무엇인가?", "순서를 바꾸면 같은 자산도 다른 역할을 맡게 됩니다."),
    ("다시 찍을 것", "실패한 판단을 어떤 장면으로 재구성할 것인가?", "다시 찍는다는 건 후회가 아니라 다음 선택의 기준을 고치는 일입니다."),
]

TITLE_BY_CATEGORY = {
    "Market Note": "지금 시장에서 진짜 봐야 할 건 가격이 아닙니다",
    "Money Edit": "돈이 남지 않는 이유는 수익률보다 구조에 있습니다",
    "Portfolio Life": "내 삶의 포트폴리오에 지금 무엇이 너무 많을까",
    "Mind Edit": "내가 계속 보는 것이 결국 내 선택이 됩니다",
    "Career Recut": "늦었다고 느끼는 순간이 사실 편집점일 수 있습니다",
}

for key, value in {"items": [], "insights": [], "selected_id": None, "generated": {}, "archive": []}.items():
    st.session_state.setdefault(key, value)


def token_set(text: str) -> set[str]:
    return {item.strip().upper() for item in text.split(",") if item.strip()}


def score(row: dict[str, Any], index: int) -> int:
    raw = 35 + abs(float(row["move"])) * 8 + float(row["volatility"]) * 0.42 + 12 - index % 4
    raw += 14 if len(row["summary"]) > 42 else 9
    return round(max(0, min(99, raw)))


def collect(active: list[str], tickers: str, cryptos: str, wallets: str, category: str) -> None:
    ticker_tokens = token_set(tickers)
    crypto_tokens = token_set(cryptos)
    rows: list[dict[str, Any]] = []
    for row in DATA:
        if row["key"] not in active:
            continue
        if row["key"] == "stocks" and ticker_tokens and row["symbol"] not in ticker_tokens:
            continue
        if row["key"] == "crypto" and crypto_tokens and row["symbol"] not in crypto_tokens:
            continue
        rows.append(dict(row))

    for index, address in enumerate(item.strip() for item in wallets.replace(",", "\n").splitlines() if item.strip()):
        rows.append({"key": "wallets", "source": "지갑 / 온체인", "symbol": f"W{index + 1}", "title": f"{address[:6]}...{address[-4:]} 지갑 관측 메모", "summary": "주소의 움직임은 신호일 수 있지만, 해석되지 않은 신호는 소음에 가깝다.", "move": 0.6 if index % 2 == 0 else -0.5, "volatility": 50 + index * 6})

    captured_at = datetime.now().isoformat(timespec="seconds")
    items, insights = [], []
    for index, row in enumerate(rows):
        frame, question, line = FRAMES[index % len(FRAMES)]
        row.update({"id": f"item-{captured_at}-{index}", "score": score(row, index), "captured_at": captured_at})
        items.append(row)
        insights.append({**row, "category": category, "framework": frame, "question": question, "editorial_line": line})
    st.session_state.items = items
    st.session_state.insights = sorted(insights, key=lambda item: item["score"], reverse=True)
    st.session_state.selected_id = st.session_state.insights[0]["id"] if insights else None
    st.session_state.generated = {}


def selected() -> dict[str, Any] | None:
    return next((row for row in st.session_state.insights if row["id"] == st.session_state.selected_id), None)


def title_for(insight: dict[str, Any]) -> str:
    return TITLE_BY_CATEGORY.get(insight["category"], TITLE_BY_CATEGORY["Market Note"])


def card(title: str, body: str, tags: list[Any]) -> None:
    with st.container(border=True):
        st.markdown(f"#### {escape(str(title))}")
        st.write(body)
        st.caption(" · ".join(str(tag) for tag in tags))


def build_content(insight: dict[str, Any], tone: str) -> dict[str, str]:
    longform = f'''제목: {title_for(insight)}

오프닝
지금 시장에서 중요한 건 {insight["symbol"]}의 다음 가격을 맞히는 일이 아닙니다.
더 중요한 질문은 이겁니다. 내 삶과 계좌는 이 변동성을 감당할 구조를 갖고 있는가.

관점
{insight["summary"]}
이 장면을 Editorial Life에서는 "{insight["framework"]}"의 문제로 봅니다.
{insight["editorial_line"]}

Life Edit
오늘의 질문은 이것입니다.
{insight["question"]}

내 계좌에서 남길 것은 원칙입니다.
덜어낼 것은 반응입니다.
순서를 바꿀 것은 수익률과 리스크입니다.
다시 찍어야 할 것은 지난번과 똑같이 흔들렸던 내 판단입니다.

클로징
투자는 예측보다 배치에 가깝습니다. 그리고 삶도 마찬가지입니다.
{tone} 말하자면, 돈을 공부한다는 건 더 많이 갖기 위한 일이 아니라 내 선택의 편집권을 되찾는 일입니다.'''
    shorts = f'''1. {insight["symbol"]}이 오를지보다 먼저 봐야 할 게 있습니다. 내가 이 변동성을 감당할 구조가 있는가.

2. 시장은 매일 새로운 뉴스를 줍니다. 하지만 내 계좌를 바꾸는 건 뉴스가 아니라 배치입니다.

3. {insight["framework"]}. 오늘 시장을 보는 Editorial Life의 기준은 이 한 문장입니다. {insight["editorial_line"]}

4. 돈은 숫자가 아니라 선택이 남은 상태입니다. 그래서 투자는 더하는 일이 아니라 편집하는 일입니다.'''
    cards = f'''카드 1
{title_for(insight)}

카드 2
가격보다 먼저 볼 것: 내 자산이 어떤 역할로 배치되어 있는가.

카드 3
{insight["framework"]}: {insight["question"]}

카드 4
덜어낼 것: 소음성 정보, 감정 매매, 과도한 확신.

카드 5
남길 것: 현금흐름, 리스크 기준, 반복 가능한 판단.

카드 6
Editorial Life: 삶은 더하는 일이 아니라, 편집하는 일입니다.'''
    return {"롱폼": longform, "쇼츠": shorts, "카드뉴스": cards}


st.sidebar.markdown('<p class="eyebrow">Editorial Life</p>', unsafe_allow_html=True)
st.sidebar.title("Intelligence Lab")
st.sidebar.markdown('<p class="brand-line">삶은 더하는 일이 아니라, 편집하는 일입니다.</p>', unsafe_allow_html=True)
st.sidebar.divider()

source_map = {"stocks": "주식 / ETF", "crypto": "암호화폐", "macro": "거시경제", "wallets": "지갑 / 온체인", "philosophy": "철학 / 문장"}
st.sidebar.subheader("수집 소스")
active_keys = [key for key, label in source_map.items() if st.sidebar.checkbox(label, value=True, key=f"src_{key}")]
st.sidebar.subheader("관측 대상")
ticker_text = st.sidebar.text_input("티커", value="SPY, QQQ, TSLA, NVDA")
crypto_text = st.sidebar.text_input("코인", value="BTC, ETH, SOL")
wallet_text = st.sidebar.text_area("지갑주소", placeholder="0x...", height=90)
st.sidebar.subheader("콘텐츠 설정")
category = st.sidebar.selectbox("카테고리", list(TITLE_BY_CATEGORY.keys()))
tone = st.sidebar.selectbox("톤", ["차분하고 날카롭게", "현실 조언 중심", "철학적 관찰자", "숏폼 훅 중심"])
if st.sidebar.button("실시간 인사이트 수집", type="primary", use_container_width=True):
    collect(active_keys, ticker_text, crypto_text, wallet_text, category)
if st.sidebar.button("아카이브 초기화", use_container_width=True):
    st.session_state.archive = []
st.sidebar.caption(f"prototype v0.1 · {datetime.now():%H:%M}")

st.markdown('<p class="eyebrow">Financial Self-Editing Console</p>', unsafe_allow_html=True)
st.title("Editorial Life 제작실")
st.caption("시장 데이터와 삶의 관점을 수집해 Editorial Life 브랜드 문법으로 재편집합니다.")

avg_signal = round(sum(row["score"] for row in st.session_state.items) / len(st.session_state.items)) if st.session_state.items else 0
for col, (label, value) in zip(st.columns(4), [("수집 소재", len(st.session_state.items)), ("평균 Signal", avg_signal), ("콘텐츠 후보", len(st.session_state.insights)), ("아카이브", len(st.session_state.archive))]):
    col.markdown(f'<div class="metric-card"><span>{label}</span><strong>{value}</strong></div>', unsafe_allow_html=True)
st.divider()

market, wallet, insights, studio, archive, framework = st.tabs(["Market Radar", "Wallet Watch", "Insight Board", "Content Studio", "Archive", "Life Edit"])

with market:
    st.markdown('<p class="eyebrow">Market Radar</p>', unsafe_allow_html=True)
    st.subheader("시장 흐름")
    if not st.session_state.items:
        st.info("왼쪽에서 소스를 고르고 수집을 시작하세요.")
    else:
        left, right = st.columns([1, 1])
        with left:
            for row in st.session_state.items:
                card(f'{row["symbol"]} · {row["title"]}', row["summary"], [row["source"], f'{row["move"]:+.1f}%', f'Vol {row["volatility"]}', f'Signal {row["score"]}'])
        with right:
            st.scatter_chart(pd.DataFrame({"Signal": [row["score"] for row in st.session_state.items], "Volatility": [row["volatility"] for row in st.session_state.items]}), x="Signal", y="Volatility", color="#c9443e", size=120)

with wallet:
    st.markdown('<p class="eyebrow">Wallet / Flow Watch</p>', unsafe_allow_html=True)
    st.subheader("온체인 관측")
    wallet_items = [row for row in st.session_state.items if row["key"] == "wallets"]
    if not wallet_items:
        st.info("지갑주소를 입력하면 관측 카드가 생성됩니다.")
    for row in wallet_items:
        card(row["title"], row["summary"], [row["source"], f'Signal {row["score"]}'])

with insights:
    st.markdown('<p class="eyebrow">Editorial Insight Board</p>', unsafe_allow_html=True)
    st.subheader("브랜드식 재해석")
    if not st.session_state.insights:
        st.info("수집된 소재를 Editorial Life 관점으로 변환하면 여기에 표시됩니다.")
    for row in st.session_state.insights:
        body, action = st.columns([5, 1])
        with body:
            card(row["title"], row["summary"], [row["category"], row["framework"], row["source"], f'Signal {row["score"]}'])
        with action:
            if st.button("제작실로", key=f'select_{row["id"]}', use_container_width=True):
                st.session_state.selected_id = row["id"]
                st.session_state.generated = {}
                st.rerun()

with studio:
    st.markdown('<p class="eyebrow">Content Studio</p>', unsafe_allow_html=True)
    st.subheader("롱폼 / 쇼츠 / 카드뉴스")
    insight = selected()
    if not insight:
        st.info("먼저 Insight Board에서 제작 소재를 선택하세요.")
    else:
        left, right = st.columns([.85, 1.35])
        with left:
            card(insight["title"], insight["summary"], [insight["symbol"], insight["framework"], f'Signal {insight["score"]}'])
            st.markdown("**핵심 질문**")
            st.write(insight["question"])
            st.markdown("**Editorial Line**")
            st.write(insight["editorial_line"])
        with right:
            c1, c2, _ = st.columns([1, 1, 2])
            if c1.button("대본 생성", type="primary", use_container_width=True):
                st.session_state.generated = build_content(insight, tone)
            if c2.button("저장", use_container_width=True):
                if st.session_state.generated:
                    st.session_state.archive.insert(0, {"created_at": datetime.now().isoformat(timespec="seconds"), "insight": insight})
                    st.success("아카이브에 저장했습니다.")
                else:
                    st.warning("먼저 대본을 생성하세요.")
            if st.session_state.generated:
                output_type = st.radio("결과 유형", ["롱폼", "쇼츠", "카드뉴스"], horizontal=True)
                st.markdown(f'<div class="output">{escape(st.session_state.generated[output_type])}</div>', unsafe_allow_html=True)
            else:
                st.info("선택한 소재로 대본을 생성하세요.")

with archive:
    st.markdown('<p class="eyebrow">Life Edit Archive</p>', unsafe_allow_html=True)
    st.subheader("저장된 제작 패키지")
    if not st.session_state.archive:
        st.info("저장된 제작 패키지가 없습니다.")
    for pack in st.session_state.archive:
        row = pack["insight"]
        card(title_for(row), row["summary"], [row["category"], row["framework"], pack["created_at"]])

with framework:
    st.markdown('<p class="eyebrow">Life Edit Framework</p>', unsafe_allow_html=True)
    st.subheader("Editorial Life 기준")
    for col, (title, body) in zip(st.columns(4), [("남길 것", "계속 가져가야 할 자산, 원칙, 현금흐름, 기록 습관, 신뢰의 경험."), ("덜어낼 것", "감정 매매, 과도한 레버리지, 소음성 정보, 근거 없는 자기확신."), ("순서를 바꿀 것", "수익률 전 리스크, 투자 전 비상금, 종목 전 계좌 구조."), ("다시 찍을 것", "실패한 투자 판단, 무너진 루틴, 방향을 잃은 커리어와 정보 소비.")]):
        with col:
            card(title, body, ["Life Edit"])
