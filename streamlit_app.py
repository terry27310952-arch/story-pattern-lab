from __future__ import annotations

import json
from datetime import datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Editorial Life Intelligence Lab", page_icon="EL", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top:2rem; }
    [data-testid="stSidebar"] { background:#eef1f5; }
    .eyebrow { color:#9f302b; font-size:.78rem; font-weight:800; text-transform:uppercase; }
    .metric-card { padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:white; box-shadow:0 10px 28px rgba(24,31,43,.07); }
    .metric-card span { display:block; color:#68707d; font-weight:700; margin-bottom:.35rem; }
    .metric-card strong { font-size:2rem; }
    .pill { display:inline-block; padding:.22rem .5rem; border:1px solid #d9dee7; border-radius:999px; margin:.15rem .25rem .35rem 0; color:#485160; font-size:.82rem; }
    .quote,.output { white-space:pre-wrap; line-height:1.7; padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:white; }
    .quote { border-left:4px solid #c9443e; background:#fff7f6; }
    div.stButton > button[kind="primary"] { background:#c9443e; border-color:#c9443e; }
    div.stButton > button { border-radius:6px; font-weight:800; }
    </style>
    """,
    unsafe_allow_html=True,
)

SOURCE_GROUPS = {
    "reddit": "Reddit 의견글",
    "korea": "국내 커뮤니티 의견글",
    "wallets": "지갑 / 온체인 주장",
    "philosophy": "돈 / 삶 철학글",
}

COMMUNITIES = [
    ("reddit", "Reddit r/wallstreetbets", "FOMO, 손실 인증, 과도한 확신, 군중 심리가 노골적으로 드러남", "https://www.reddit.com/r/wallstreetbets/"),
    ("reddit", "Reddit r/stocks / r/investing", "장기 투자자가 가격보다 배치, 리스크, 현금 비중을 논쟁함", "https://www.reddit.com/r/stocks/"),
    ("reddit", "Reddit r/CryptoCurrency / r/Bitcoin", "레버리지, 신념, 탈출 타이밍이 섞인 코인 서사가 많음", "https://www.reddit.com/r/CryptoCurrency/"),
    ("reddit", "Reddit r/daytrading", "손절 실패, 매매 복기, 멘탈 붕괴가 1인칭으로 기록됨", "https://www.reddit.com/r/daytrading/"),
    ("korea", "네이버 종목토론실", "기대, 분노, 체념, 물타기 심리가 종목별로 압축됨", "https://finance.naver.com/"),
    ("korea", "디시인사이드 주식 / 미국주식 / 비트코인 갤러리", "짧고 거친 문장 안에 확신, 조롱, 후회가 빠르게 발생함", "https://www.dcinside.com/"),
    ("korea", "블라인드 투자 / 재테크", "월급, 커리어, 부동산, 투자 압박이 한 사람의 삶과 연결됨", "https://www.teamblind.com/kr/"),
    ("korea", "뽐뿌 재테크 / 클리앙", "절약, 예적금, ETF, 소비 습관 같은 생활형 금융 의견이 많음", "https://www.ppomppu.co.kr/"),
]

FRAMES = {
    "남길 것": ("이 화자에게 계속 가져가야 할 원칙은 무엇인가?", "남겨야 할 건 가격 예측이 아니라 반복 가능한 판단 기준입니다."),
    "덜어낼 것": ("이 의견에서 계좌와 삶을 흐트러뜨리는 소음은 무엇인가?", "덜어내야 할 건 정보가 아니라 반응 속도에 중독된 습관입니다."),
    "순서를 바꿀 것": ("이 사람은 무엇보다 먼저 무엇을 배치했어야 했나?", "순서를 바꾸면 같은 자산도 다른 역할을 맡게 됩니다."),
    "다시 찍을 것": ("이 실패한 판단은 어떤 장면으로 다시 찍어야 하나?", "다시 찍는다는 건 후회가 아니라 다음 선택의 기준을 고치는 일입니다."),
}

TITLES = {
    "Market Note": "시장은 가격보다 사람들의 포지션을 먼저 보여줍니다",
    "Money Edit": "돈이 남지 않는 이유는 수익률보다 구조에 있습니다",
    "Portfolio Life": "내 삶의 포트폴리오에 지금 무엇이 너무 많을까",
    "Mind Edit": "내가 계속 보는 것이 결국 내 선택이 됩니다",
    "Career Recut": "늦었다고 느끼는 순간이 사실 편집점일 수 있습니다",
}

SEEDS = [
    dict(group="reddit", community="Reddit r/wallstreetbets", speaker="공격적 단기 트레이더", asset="NVDA", frame="순서를 바꿀 것", stance="과열 경계", emotion="FOMO와 의심", conviction=4.3, friction=4.7, url="https://www.reddit.com/r/wallstreetbets/search/?q=NVDA&restrict_sr=1", title="좋은 회사인 건 알지만 지금 들어가는 건 남의 수익률을 사는 느낌이다", opinion="NVDA가 강한 건 인정하지만, 신규 진입은 내가 확신을 산 게 아니라 커뮤니티의 흥분을 따라 산 것에 가깝다고 본다.", quote="I know the company is great, but buying after everyone already got rich feels like paying for someone else's conviction.", evidence="AI 주도주 긍정론과 진입 가격 불안이 동시에 드러남", counter="강한 추세에서는 비싸 보이는 가격이 한동안 계속 비싸지는 경우도 있음"),
    dict(group="reddit", community="Reddit r/stocks", speaker="장기 ETF 투자자", asset="SPY", frame="남길 것", stance="방어적 낙관", emotion="차분한 불안", conviction=4.0, friction=3.5, url="https://www.reddit.com/r/stocks/", title="시장 고점보다 더 무서운 건 내가 왜 들고 있는지 모르는 상태다", opinion="S&P500이 비싸 보여도 투자 기간과 현금 비중이 정리되어 있다면 고점 공포는 줄어든다. 문제는 가격이 아니라 계좌 안 역할이다.", quote="The index being expensive matters less than not knowing what role it plays in your portfolio.", evidence="고점 논쟁을 종목 선택이 아니라 현금, ETF, 리밸런싱 순서로 해석함", counter="장기 원칙이 있어도 단기 급락 행동 규칙이 없으면 흔들릴 수 있음"),
    dict(group="reddit", community="Reddit r/CryptoCurrency", speaker="레버리지 경험자", asset="BTC", frame="덜어낼 것", stance="레버리지 경계", emotion="후회와 경고", conviction=4.6, friction=4.8, url="https://www.reddit.com/r/CryptoCurrency/", title="비트코인을 믿는 것과 레버리지를 버티는 건 완전히 다른 문제다", opinion="BTC 장기 방향을 믿어도 10배 레버리지는 신념이 아니라 청산 게임이다. 믿음보다 먼저 생존 구조를 잡아야 한다.", quote="Believing in Bitcoin and surviving leveraged Bitcoin are not the same thing.", evidence="자산에 대한 믿음과 포지션 설계의 차이를 분리해서 말함", counter="손절 규칙이 있는 트레이더에게 레버리지는 도구일 수 있음"),
    dict(group="reddit", community="Reddit r/daytrading", speaker="매매 복기 작성자", asset="DAYTRADE", frame="다시 찍을 것", stance="규칙 우선", emotion="자책과 재정렬", conviction=4.7, friction=4.4, url="https://www.reddit.com/r/daytrading/", title="오늘 손실은 시장 때문이 아니라 손절을 미룬 내 편집 실패였다", opinion="계획은 있었지만 손실을 인정하는 장면을 잘라내지 못했다. 좋은 진입보다 먼저 필요한 건 나쁜 포지션을 끝내는 버튼이었다.", quote="My loss today wasn't the market. It was me refusing to cut the scene when the trade was already wrong.", evidence="트레이딩 손실을 외부 탓보다 행동 규칙의 실패로 복기함", counter="자책만 반복하면 다음 기준이 아니라 공포만 남을 수 있음"),
    dict(group="korea", community="네이버 종목토론실", speaker="물린 개인투자자", asset="국내주식", frame="덜어낼 것", stance="손실 회피", emotion="불안과 체념", conviction=3.8, friction=4.9, url="https://finance.naver.com/", title="손절은 못 하겠고 물타기는 무섭고 결국 게시판만 계속 본다", opinion="종목을 믿는다고 말하지만 사실은 손실 확정이 싫어서 같은 의견을 찾아다니는 중이다. 정보 수집이 아니라 불안 진정에 가깝다.", quote="오늘도 반등 온다는 글만 찾고 있다. 팔면 손실이고 안 팔면 매일 계좌를 보게 된다.", evidence="종목 의견이 실제 판단보다 감정 안정 장치로 쓰이는 장면", counter="게시판 감정과 기업 가치 판단을 분리하지 않으면 같은 글만 소비하게 됨"),
    dict(group="korea", community="블라인드 투자 / 재테크", speaker="월급쟁이 투자자", asset="계좌", frame="순서를 바꿀 것", stance="구조 재설계", emotion="현실적 피로", conviction=4.5, friction=3.9, url="https://www.teamblind.com/kr/", title="연봉이 올라도 돈이 안 남는 건 계좌가 아니라 생활 장면이 너무 많아서다", opinion="월급이 늘었는데도 남는 돈이 없다면 수익률 문제가 아니다. 고정비, 구독, 인간관계 비용이 먼저 편집되어야 한다.", quote="연봉은 올랐는데 매달 남는 돈은 그대로다. 투자보다 생활 구조가 먼저인 것 같다.", evidence="투자를 삶의 현금흐름과 소비 습관으로 연결함", counter="소비 통제만 강조하면 소득 확장이나 커리어 전략이 빠질 수 있음"),
    dict(group="wallets", community="온체인 관찰 메모", speaker="고래 지갑 추종자", asset="WALLET", frame="남길 것", stance="정보와 기준 분리", emotion="경계와 호기심", conviction=4.1, friction=3.7, url="https://etherscan.io/", title="고래 지갑을 따라가는 건 정보일 수도 있지만 내 기준이 없으면 소음이다", opinion="큰 지갑 이동은 유용하지만 그걸 내 포지션의 이유로 삼는 순간 판단권을 남에게 넘기는 일이 된다.", quote="A whale moved funds. That is a signal, not a reason to abandon my own risk plan.", evidence="온체인 이벤트를 매매 명령이 아니라 관찰 자료로 제한함", counter="주소 하나의 이동만으로 매수, 매도, 담보 이동을 단정하기 어려움"),
    dict(group="philosophy", community="돈과 삶의 철학 메모", speaker="Editorial Life 화자", asset="LIFE", frame="남길 것", stance="삶의 편집", emotion="차분한 관찰", conviction=4.8, friction=2.7, url="", title="돈은 숫자가 아니라 선택이 남은 상태다", opinion="돈이 많다는 건 모든 걸 살 수 있다는 뜻이 아니라 싫은 선택을 거절할 수 있는 장면이 늘어났다는 뜻이다.", quote="돈은 숫자가 아니라 선택이 남은 상태다. 돈이 머물 구조가 없으면 소득도 장면 밖으로 사라진다.", evidence="돈을 수익률이 아니라 선택권과 생활 구조로 해석함", counter="철학적 문장만 남으면 실행 도구가 약해질 수 있어 계좌 구조로 내려와야 함"),
]

for key, default in {"rows": [], "insights": [], "selected": None, "generated": {}, "archive": [], "status": []}.items():
    st.session_state.setdefault(key, default)


def split_terms(text: str) -> list[str]:
    return [x.strip().lower() for x in text.replace(",", " ").replace("\n", " ").split(" ") if x.strip()]


def matches(item: dict, terms: list[str]) -> bool:
    if not terms:
        return True
    hay = " ".join(str(item.get(k, "")) for k in ["asset", "title", "opinion", "quote", "stance", "community", "speaker"]).lower()
    return any(term in hay for term in terms)


def row_from(item: dict, idx: int, category: str, origin: str) -> dict:
    question, line = FRAMES[item["frame"]]
    score = round(min(99, 30 + item["conviction"] * 8.5 + item["friction"] * 9 + max(0, 8 - idx % 6)))
    return {
        **item,
        "id": f"{datetime.now().isoformat(timespec='seconds')}-{origin}-{idx}",
        "origin": origin,
        "category": category,
        "score": score,
        "question": question,
        "editorial_line": line,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }


def infer_reddit(post: dict, sub: str) -> dict:
    title = post.get("title", "Untitled discussion")[:150]
    quote_text = (post.get("selftext") or title).strip()[:420]
    text = f"{title} {quote_text}".lower()
    asset = next((x for x in ["NVDA", "TSLA", "BTC", "ETH", "SOL", "SPY", "QQQ", "AAPL", "AMD"] if x.lower() in text), "MARKET")
    if any(w in text for w in ["loss", "lost", "mistake", "revenge", "blew"]):
        stance, emotion, frame = "손실 복기", "후회와 재정렬", "다시 찍을 것"
    elif any(w in text for w in ["sell", "short", "bubble", "overvalued", "bear"]):
        stance, emotion, frame = "과열 경계", "의심과 경계", "덜어낼 것"
    elif any(w in text for w in ["hold", "long", "buy", "bull", "dca"]):
        stance, emotion, frame = "보유 논리", "확신과 불안", "남길 것"
    else:
        stance, emotion, frame = "시장 관찰", "호기심과 긴장", "순서를 바꿀 것"
    comments = int(post.get("num_comments") or 0)
    ups = int(post.get("ups") or 0)
    return dict(
        group="reddit",
        community=f"Reddit r/{sub}",
        speaker="Reddit 커뮤니티 작성자",
        asset=asset,
        frame=frame,
        stance=stance,
        emotion=emotion,
        conviction=min(5.0, 2.8 + min(ups, 400) / 220),
        friction=min(5.0, 2.8 + min(comments, 300) / 120),
        url=f"https://www.reddit.com{post.get('permalink', f'/r/{sub}/')}",
        title=title,
        opinion="커뮤니티 작성자가 가격 자체보다 자신의 포지션, 확신, 불안, 행동 기준을 드러낸 글입니다.",
        quote=quote_text,
        evidence=f"댓글 {comments}개, 업보트 {ups}개. 토론 반응이 있는 의견글로 분류했습니다.",
        counter="제목만 강한 글일 수 있으므로 원문과 댓글 맥락을 확인한 뒤 콘텐츠화해야 합니다.",
    )


@st.cache_data(ttl=900, show_spinner=False)
def fetch_reddit(sub: str, query: str, limit: int = 3) -> tuple[list[dict], str]:
    path = f"search.json?q={quote(query)}&restrict_sr=1&sort=new&limit={limit}" if query else f"hot.json?limit={limit}"
    req = Request(f"https://www.reddit.com/r/{sub}/{path}", headers={"User-Agent": "EditorialLifeLab/0.1"})
    try:
        with urlopen(req, timeout=7) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], f"r/{sub}: 실시간 접근 실패, seed 의견으로 대체 ({type(exc).__name__})"
    posts = [c.get("data", {}) for c in data.get("data", {}).get("children", [])]
    posts = [p for p in posts if p.get("title") and not p.get("stickied")]
    return [infer_reddit(p, sub) for p in posts[:limit]], f"r/{sub}: {len(posts[:limit])}개 의견글 수집"


def collect(active: list[str], keyword: str, minimum: float, live: bool, wallets: str, category: str) -> None:
    keys = split_terms(keyword)
    rows, status = [], []
    if "reddit" in active and live:
        query = " ".join(keys[:3])
        for sub in ["wallstreetbets", "stocks", "investing", "CryptoCurrency", "Bitcoin", "daytrading"]:
            items, msg = fetch_reddit(sub, query)
            status.append(msg)
            rows += [row_from(x, len(rows) + i, category, "live-reddit") for i, x in enumerate(items) if x["conviction"] >= minimum and matches(x, keys)]
    rows += [row_from(x, len(rows) + i, category, "seed") for i, x in enumerate(SEEDS) if x["group"] in active and x["conviction"] >= minimum and matches(x, keys)]
    if "wallets" in active:
        for address in [x.strip() for x in wallets.replace(",", "\n").splitlines() if x.strip()]:
            item = dict(SEEDS[-2], title=f"{address[:6]}...{address[-4:]} 지갑을 따라보려는 이유", quote=f"사용자가 관측 대상으로 입력한 지갑주소: {address}", url=f"https://etherscan.io/address/{address}" if address.startswith("0x") else "")
            rows.append(row_from(item, len(rows), category, "wallet-input"))
    rows = sorted(rows, key=lambda x: x["score"], reverse=True)
    st.session_state["rows"] = rows
    st.session_state["insights"] = rows
    st.session_state["selected"] = rows[0]["id"] if rows else None
    st.session_state["generated"] = {}
    st.session_state["status"] = status or ["seed 의견글 기준으로 수집했습니다."]


def selected() -> dict | None:
    return next((x for x in st.session_state["insights"] if x["id"] == st.session_state["selected"]), None)


def source_block(row: dict) -> None:
    st.markdown(f"**커뮤니티 / 화자**  \n{row['community']} · {row['speaker']}")
    st.markdown(f"**원문 제목**  \n{row['title']}")
    if row["url"]:
        st.markdown(f"**원문 링크**  \n[{row['url']}]({row['url']})")
    else:
        st.caption("외부 원문 링크가 없는 내부 브랜드/철학 메모입니다.")
    st.markdown("**화자의 원문/발췌**")
    st.markdown(f'<div class="quote">{escape(row["quote"])}</div>', unsafe_allow_html=True)
    st.markdown("**근거로 볼 지점**")
    st.write(row["evidence"])
    st.markdown("**반론 포인트**")
    st.write(row["counter"])


def card(row: dict, action: bool = False) -> None:
    with st.container(border=True):
        st.markdown(f"#### {escape(row['title'])}")
        st.markdown(f'<span class="pill">{escape(row["community"])}</span><span class="pill">{escape(row["stance"])}</span><span class="pill">{escape(row["emotion"])}</span>', unsafe_allow_html=True)
        st.markdown("**화자의 주장**")
        st.write(row["opinion"])
        st.caption(f"{row['speaker']} · {row['asset']} · {row['frame']} · Signal {row['score']}")
        with st.expander("원본과 근거 확인"):
            source_block(row)
        if action and st.button("제작실로", key=f"select-{row['id']}", use_container_width=True):
            st.session_state["selected"] = row["id"]
            st.session_state["generated"] = {}
            st.rerun()


def make_content(row: dict, tone: str) -> dict[str, str]:
    title = TITLES.get(row["category"], TITLES["Market Note"])
    longform = f"""제목: {title}

오프닝
오늘 볼 것은 {row['asset']}의 가격 자체가 아닙니다.
더 중요한 건 한 커뮤니티 화자가 왜 이런 판단을 했는지, 그리고 그 판단이 우리 삶과 계좌에 어떤 편집점을 남기는지입니다.

원본 확인
커뮤니티: {row['community']}
화자: {row['speaker']}
원문 링크: {row['url'] or '내부 메모'}
원문 발췌: {row['quote']}

화자의 주장
{row['opinion']}

Editorial Life 관점
이 의견을 그대로 믿을 필요는 없습니다.
대신 이 사람이 무엇을 남기고, 무엇을 덜어내지 못했고, 어떤 순서를 놓쳤는지를 봐야 합니다.

Life Edit
프레임: {row['frame']}
핵심 질문: {row['question']}
편집 문장: {row['editorial_line']}

반론까지 보기
{row['counter']}

클로징
시장은 숫자로 움직이지만, 사람은 자기 해석으로 움직입니다.
{tone} 말하자면, 투자 콘텐츠의 재료는 차트만이 아니라 사람들이 돈 앞에서 남기는 문장입니다."""
    shorts = f"1. {row['asset']}보다 먼저 볼 것은 화자의 포지션입니다.\n\n2. {row['opinion']}\n\n3. Editorial Life식으로 묻겠습니다. {row['question']}"
    cards = f"카드 1\n{title}\n\n카드 2\n커뮤니티: {row['community']}\n화자의 주장: {row['opinion']}\n\n카드 3\n편집점: {row['frame']}\n{row['editorial_line']}\n\n카드 4\n원문 출처: {row['url'] or '내부 메모'}"
    return {"롱폼": longform, "쇼츠": shorts, "카드뉴스": cards}


st.sidebar.markdown('<p class="eyebrow">Editorial Life</p>', unsafe_allow_html=True)
st.sidebar.title("Opinion Collector")
st.sidebar.write("가격보다 먼저, 사람들이 돈 앞에서 남기는 문장을 수집합니다.")
st.sidebar.divider()
active = [key for key, label in SOURCE_GROUPS.items() if st.sidebar.checkbox(label, value=True)]
keyword = st.sidebar.text_input("관찰 키워드", "", placeholder="NVDA, BTC, 금리, 손절, 계좌")
minimum = st.sidebar.slider("화자 확신도", 1.0, 5.0, 2.5, 0.1)
live = st.sidebar.checkbox("Reddit 실시간 수집 시도", value=True)
wallets = st.sidebar.text_area("지갑주소", placeholder="0x...")
category = st.sidebar.selectbox("카테고리", list(TITLES.keys()))
tone = st.sidebar.selectbox("톤", ["차분하고 날카롭게", "현실 조언 중심", "철학적 관찰자", "숏폼 훅 중심"])
if st.sidebar.button("커뮤니티 의견 수집", type="primary", use_container_width=True):
    collect(active, keyword, minimum, live, wallets, category)
if st.sidebar.button("아카이브 초기화", use_container_width=True):
    st.session_state["archive"] = []

rows = st.session_state["rows"]
avg = round(sum(x["score"] for x in rows) / len(rows)) if rows else 0
live_count = len([x for x in rows if x["origin"] == "live-reddit"])

st.markdown('<p class="eyebrow">Financial Self-Editing Console</p>', unsafe_allow_html=True)
st.title("Editorial Life 제작실")
st.caption("주식, 코인, 데이 트레이딩, 지갑주소, 삶의 철학을 커뮤니티 화자의 의견 단위로 수집해 콘텐츠 재료로 편집합니다.")
for col, (label, value) in zip(st.columns(4), [("의견 소재", len(rows)), ("평균 Signal", avg), ("실시간 Reddit", live_count), ("아카이브", len(st.session_state["archive"]))]):
    col.markdown(f'<div class="metric-card"><span>{label}</span><strong>{value}</strong></div>', unsafe_allow_html=True)
st.divider()

radar, source_viewer, community_map, insights, studio, archive = st.tabs(["Opinion Radar", "Source Viewer", "Community Map", "Insight Board", "Content Studio", "Archive"])

with radar:
    st.subheader("의견 레이더")
    if not rows:
        st.info("왼쪽에서 커뮤니티 소스를 고르고 의견 수집을 시작하세요.")
    else:
        with st.expander("수집 상태"):
            for msg in st.session_state["status"]:
                st.caption(msg)
        left, right = st.columns([1.05, .95])
        with left:
            for row in rows[:6]:
                card(row)
        with right:
            chart = pd.DataFrame({"Conviction": [x["conviction"] for x in rows], "Friction": [x["friction"] for x in rows], "Signal": [x["score"] for x in rows], "Asset": [x["asset"] for x in rows]})
            st.scatter_chart(chart, x="Conviction", y="Friction", size="Signal", color="#c9443e")
            st.dataframe(chart, use_container_width=True, hide_index=True)

with source_viewer:
    st.subheader("수집 원본 검수")
    if not rows:
        st.info("수집을 실행하면 커뮤니티 원문 링크, 화자의 발췌문, 수집 판단이 여기에 표시됩니다.")
    for row in rows:
        with st.expander(f"{row['asset']} · {row['community']} · {row['title']}"):
            st.caption(f"{row['captured_at']} · {row['origin']}")
            source_block(row)
            st.markdown("**화자의 주장**")
            st.write(row["opinion"])

with community_map:
    st.subheader("커뮤니티 소스 맵")
    st.write("이 수집기는 가격 데이터가 아니라 의견이 들어있는 글을 우선합니다. 아래 소스들은 화자의 포지션과 감정이 드러나는 곳입니다.")
    for group, name, why, url in COMMUNITIES:
        with st.container(border=True):
            st.markdown(f"#### {name}")
            st.caption(SOURCE_GROUPS[group])
            st.write(why)
            st.markdown("**수집해야 할 의견**")
            st.write("왜 샀는지, 왜 못 파는지, 어떤 불안이나 확신 때문에 같은 선택을 반복하는지.")
            st.markdown(f"[소스 보기]({url})")

with insights:
    st.subheader("브랜드식 재해석")
    if not st.session_state["insights"]:
        st.info("수집된 의견글을 Editorial Life 관점으로 변환하면 여기에 표시됩니다.")
    for row in st.session_state["insights"]:
        card(row, action=True)

with studio:
    st.subheader("롱폼 / 쇼츠 / 카드뉴스")
    row = selected()
    if not row:
        st.info("먼저 Insight Board에서 제작 소재를 선택하세요.")
    else:
        left, right = st.columns([.85, 1.35])
        with left:
            card(row)
        with right:
            c1, c2, _ = st.columns([1, 1, 2])
            if c1.button("대본 생성", type="primary", use_container_width=True):
                st.session_state["generated"] = make_content(row, tone)
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
                st.info("선택한 의견글로 대본을 생성하세요.")

with archive:
    st.subheader("저장된 제작 패키지")
    if not st.session_state["archive"]:
        st.info("저장된 제작 패키지가 없습니다.")
    for package in st.session_state["archive"]:
        st.caption(package["created_at"])
        card(package["row"])
