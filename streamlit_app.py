from __future__ import annotations

from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Editorial Life Intelligence Lab", page_icon="EL", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top: 2.2rem; }
    [data-testid="stSidebar"] { background: #eef1f5; }
    .eyebrow { color:#9f302b; font-size:.78rem; font-weight:800; text-transform:uppercase; }
    .metric-card { padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:white; box-shadow:0 10px 28px rgba(24,31,43,.07); }
    .metric-card span { display:block; color:#68707d; font-weight:700; margin-bottom:.4rem; }
    .metric-card strong { font-size:2rem; }
    .output { white-space:pre-wrap; line-height:1.72; padding:1.1rem; border:1px solid #dce1e7; border-radius:8px; background:white; }
    div.stButton > button[kind="primary"] { background:#c9443e; border-color:#c9443e; }
    div.stButton > button { border-radius:6px; font-weight:800; }
    </style>
    """,
    unsafe_allow_html=True,
)

SOURCES = [
    ("stocks", "주식 / ETF", "SPY", "S&P500이 다시 고점권에서 숨을 고르는 중", "가격보다 중요한 건 포트폴리오 안에서 주식 비중이 맡은 역할이다.", 0.8, 42, "https://finance.yahoo.com/quote/SPY"),
    ("stocks", "주식 / ETF", "NVDA", "AI 주도주의 기대가 다시 가격에 반영됨", "좋은 기업과 좋은 진입 가격은 같은 말이 아니다.", 1.7, 73, "https://finance.yahoo.com/quote/NVDA"),
    ("crypto", "암호화폐", "BTC", "비트코인 박스권에서 레버리지 포지션이 누적됨", "방향을 맞히기보다 내가 버틸 수 있는 변동 폭을 먼저 정해야 한다.", 1.1, 68, "https://www.coingecko.com/en/coins/bitcoin"),
    ("crypto", "암호화폐", "SOL", "솔라나 생태계 거래량이 단기 관심을 재점화", "빠른 자산은 빠른 판단보다 작은 비중을 요구한다.", 2.2, 84, "https://www.coingecko.com/en/coins/solana"),
    ("macro", "거시경제", "10Y", "장기금리가 위험자산의 할인율을 재조정", "금리가 바뀌면 가격만이 아니라 사람들의 선택 순서도 바뀐다.", -0.2, 39, "https://fred.stlouisfed.org/series/DGS10"),
    ("wallets", "지갑 / 온체인", "FLOW", "스테이블코인 유입이 위험 선호 회복을 암시", "자금 흐름은 뉴스보다 먼저 포지션의 방향을 보여줄 때가 있다.", 0.9, 52, "https://etherscan.io/"),
    ("philosophy", "철학 / 문장", "EDIT", "돈은 숫자가 아니라 선택이 남은 상태", "돈이 머물 구조가 없으면 높은 소득도 금방 장면 밖으로 사라진다.", 0, 28, ""),
]

FRAMES = [
    ("남길 것", "지금 이 흐름에서 계속 가져가야 할 원칙은 무엇인가?", "남겨야 할 건 가격 예측이 아니라 반복 가능한 판단 기준입니다."),
    ("덜어낼 것", "내 계좌와 삶을 흐트러뜨리는 소음은 무엇인가?", "덜어내야 할 건 정보가 아니라 반응 속도에 중독된 습관입니다."),
    ("순서를 바꿀 것", "수익보다 먼저 배치해야 할 것은 무엇인가?", "순서를 바꾸면 같은 자산도 다른 역할을 맡게 됩니다."),
    ("다시 찍을 것", "실패한 판단을 어떤 장면으로 재구성할 것인가?", "다시 찍는다는 건 후회가 아니라 다음 선택의 기준을 고치는 일입니다."),
]

TITLES = {
    "Market Note": "지금 시장에서 진짜 봐야 할 건 가격이 아닙니다",
    "Money Edit": "돈이 남지 않는 이유는 수익률보다 구조에 있습니다",
    "Portfolio Life": "내 삶의 포트폴리오에 지금 무엇이 너무 많을까",
    "Mind Edit": "내가 계속 보는 것이 결국 내 선택이 됩니다",
    "Career Recut": "늦었다고 느끼는 순간이 사실 편집점일 수 있습니다",
}

for key, default in {"rows": [], "insights": [], "selected": None, "generated": {}, "archive": []}.items():
    st.session_state.setdefault(key, default)


def token_set(text: str) -> set[str]:
    return {item.strip().upper() for item in text.split(",") if item.strip()}


def make_row(raw: tuple, index: int, category: str) -> dict:
    key, source, symbol, title, summary, move, volatility, url = raw
    frame, question, line = FRAMES[index % len(FRAMES)]
    score = round(min(99, 35 + abs(float(move)) * 8 + float(volatility) * 0.42 + 12 - index % 4 + 14))
    return {
        "id": f"{datetime.now().isoformat(timespec='seconds')}-{index}",
        "key": key,
        "source": source,
        "symbol": symbol,
        "title": title,
        "summary": summary,
        "move": move,
        "volatility": volatility,
        "source_url": url,
        "original_title": title,
        "original_excerpt": f"[{source}] {title}. {summary}",
        "collector_note": "MVP 샘플 원본입니다. 실제 수집기에서는 원문 URL, 발췌문, 수집 시각, 파서 상태를 함께 저장합니다.",
        "category": category,
        "framework": frame,
        "question": question,
        "editorial_line": line,
        "score": score,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }


def collect(active: list[str], tickers: str, cryptos: str, wallets: str, category: str) -> None:
    ticker_tokens = token_set(tickers)
    crypto_tokens = token_set(cryptos)
    picked = []
    for raw in SOURCES:
        key, _, symbol, *_ = raw
        if key not in active:
            continue
        if key == "stocks" and ticker_tokens and symbol not in ticker_tokens:
            continue
        if key == "crypto" and crypto_tokens and symbol not in crypto_tokens:
            continue
        picked.append(raw)
    for address in [x.strip() for x in wallets.replace(",", "\n").splitlines() if x.strip()]:
        picked.append(("wallets", "지갑 / 온체인", "WALLET", f"{address[:6]}...{address[-4:]} 지갑 관측 메모", f"사용자가 관측 대상으로 입력한 지갑주소: {address}", 0.6, 55, f"https://etherscan.io/address/{address}" if address.startswith("0x") else ""))
    rows = [make_row(raw, i, category) for i, raw in enumerate(picked)]
    st.session_state["rows"] = rows
    st.session_state["insights"] = sorted(rows, key=lambda row: row["score"], reverse=True)
    st.session_state["selected"] = st.session_state["insights"][0]["id"] if rows else None
    st.session_state["generated"] = {}


def selected() -> dict | None:
    return next((row for row in st.session_state["insights"] if row["id"] == st.session_state["selected"]), None)


def source_block(row: dict) -> None:
    st.markdown(f"**원문 제목**  \n{row['original_title']}")
    if row["source_url"]:
        st.markdown(f"**원문 링크**  \n[{row['source_url']}]({row['source_url']})")
    else:
        st.caption("외부 원문 링크가 없는 내부 브랜드/철학 메모입니다.")
    st.markdown("**원문 발췌**")
    st.write(row["original_excerpt"])
    st.markdown("**수집 메모**")
    st.write(row["collector_note"])


def card(row: dict, action: bool = False) -> None:
    with st.container(border=True):
        st.markdown(f"#### {escape(row['title'])}")
        st.write(row["summary"])
        st.caption(f"{row['source']} · {row['framework']} · Signal {row['score']}")
        with st.expander("원본 확인"):
            source_block(row)
        if action and st.button("제작실로", key=f"select-{row['id']}", use_container_width=True):
            st.session_state["selected"] = row["id"]
            st.session_state["generated"] = {}
            st.rerun()


def build_content(row: dict, tone: str) -> dict[str, str]:
    title = TITLES.get(row["category"], TITLES["Market Note"])
    longform = f"""제목: {title}

오프닝
지금 시장에서 중요한 건 {row['symbol']}의 다음 가격을 맞히는 일이 아닙니다.
더 중요한 질문은 이겁니다. 내 삶과 계좌는 이 변동성을 감당할 구조를 갖고 있는가.

원본 확인
원문 링크: {row['source_url'] or '내부 메모'}
원문 발췌: {row['original_excerpt']}

관점
{row['summary']}
이 장면을 Editorial Life에서는 "{row['framework']}"의 문제로 봅니다.
{row['editorial_line']}

Life Edit
{row['question']}

클로징
투자는 예측보다 배치에 가깝습니다. 그리고 삶도 마찬가지입니다.
{tone} 말하자면, 돈을 공부한다는 건 내 선택의 편집권을 되찾는 일입니다."""
    shorts = f"1. {row['symbol']}이 오를지보다 먼저 볼 것은 구조입니다.\n\n2. {row['editorial_line']}\n\n3. 돈은 숫자가 아니라 선택이 남은 상태입니다."
    cards = f"카드 1\n{title}\n\n카드 2\n원문 출처: {row['source_url'] or '내부 메모'}\n\n카드 3\n{row['framework']}: {row['question']}\n\n카드 4\n삶은 더하는 일이 아니라, 편집하는 일입니다."
    return {"롱폼": longform, "쇼츠": shorts, "카드뉴스": cards}


st.sidebar.markdown('<p class="eyebrow">Editorial Life</p>', unsafe_allow_html=True)
st.sidebar.title("Intelligence Lab")
st.sidebar.write("삶은 더하는 일이 아니라, 편집하는 일입니다.")
st.sidebar.divider()
source_labels = {"stocks": "주식 / ETF", "crypto": "암호화폐", "macro": "거시경제", "wallets": "지갑 / 온체인", "philosophy": "철학 / 문장"}
active = [key for key, label in source_labels.items() if st.sidebar.checkbox(label, value=True)]
tickers = st.sidebar.text_input("티커", "SPY, QQQ, TSLA, NVDA")
cryptos = st.sidebar.text_input("코인", "BTC, ETH, SOL")
wallets = st.sidebar.text_area("지갑주소", placeholder="0x...")
category = st.sidebar.selectbox("카테고리", list(TITLES.keys()))
tone = st.sidebar.selectbox("톤", ["차분하고 날카롭게", "현실 조언 중심", "철학적 관찰자", "숏폼 훅 중심"])
if st.sidebar.button("실시간 인사이트 수집", type="primary", use_container_width=True):
    collect(active, tickers, cryptos, wallets, category)
if st.sidebar.button("아카이브 초기화", use_container_width=True):
    st.session_state["archive"] = []

st.markdown('<p class="eyebrow">Financial Self-Editing Console</p>', unsafe_allow_html=True)
st.title("Editorial Life 제작실")
st.caption("시장 데이터와 삶의 관점을 수집해 Editorial Life 브랜드 문법으로 재편집합니다.")

rows = st.session_state["rows"]
avg = round(sum(row["score"] for row in rows) / len(rows)) if rows else 0
for col, (label, value) in zip(st.columns(4), [("수집 소재", len(rows)), ("평균 Signal", avg), ("콘텐츠 후보", len(st.session_state["insights"])), ("아카이브", len(st.session_state["archive"]))]):
    col.markdown(f'<div class="metric-card"><span>{label}</span><strong>{value}</strong></div>', unsafe_allow_html=True)
st.divider()

market, source_viewer, insights, studio, archive = st.tabs(["Market Radar", "Source Viewer", "Insight Board", "Content Studio", "Archive"])

with market:
    st.subheader("시장 흐름")
    if not rows:
        st.info("왼쪽에서 소스를 고르고 수집을 시작하세요.")
    else:
        left, right = st.columns([1, 1])
        with left:
            for row in rows:
                card(row)
        with right:
            st.scatter_chart(pd.DataFrame({"Signal": [row["score"] for row in rows], "Volatility": [row["volatility"] for row in rows]}), x="Signal", y="Volatility", color="#c9443e", size=120)

with source_viewer:
    st.subheader("수집 원본 검수")
    if not rows:
        st.info("수집을 실행하면 원문 링크와 발췌문이 여기에 표시됩니다.")
    for row in rows:
        with st.expander(f"{row['symbol']} · {row['original_title']}"):
            st.caption(f"{row['source']} · {row['captured_at']}")
            source_block(row)

with insights:
    st.subheader("브랜드식 재해석")
    if not st.session_state["insights"]:
        st.info("수집된 소재를 Editorial Life 관점으로 변환하면 여기에 표시됩니다.")
    for row in st.session_state["insights"]:
        card(row, action=True)

with studio:
    st.subheader("롱폼 / 쇼츠 / 카드뉴스")
    row = selected()
    if not row:
        st.info("먼저 Insight Board에서 제작 소재를 선택하세요.")
    else:
        left, right = st.columns([0.85, 1.35])
        with left:
            card(row)
        with right:
            c1, c2, _ = st.columns([1, 1, 2])
            if c1.button("대본 생성", type="primary", use_container_width=True):
                st.session_state["generated"] = build_content(row, tone)
            if c2.button("저장", use_container_width=True):
                if st.session_state["generated"]:
                    st.session_state["archive"].insert(0, {"created_at": datetime.now().isoformat(timespec="seconds"), "row": row})
                    st.success("아카이브에 저장했습니다.")
                else:
                    st.warning("먼저 대본을 생성하세요.")
            if st.session_state["generated"]:
                output_type = st.radio("결과 유형", ["롱폼", "쇼츠", "카드뉴스"], horizontal=True)
                st.markdown(f'<div class="output">{escape(st.session_state["generated"][output_type])}</div>', unsafe_allow_html=True)
            else:
                st.info("선택한 소재로 대본을 생성하세요.")

with archive:
    st.subheader("저장된 제작 패키지")
    if not st.session_state["archive"]:
        st.info("저장된 제작 패키지가 없습니다.")
    for package in st.session_state["archive"]:
        st.caption(package["created_at"])
        card(package["row"])
