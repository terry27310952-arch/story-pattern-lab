from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from math import log1p
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Editorial Life Intelligence Lab", page_icon="EL", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top:1.6rem; max-width:1280px; }
    [data-testid="stSidebar"] { background:#eef1f5; }
    .eyebrow { color:#9f302b; font-size:.78rem; font-weight:800; text-transform:uppercase; letter-spacing:.03em; }
    .hero-line { color:#596272; max-width:760px; line-height:1.65; }
    .metric-card { padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:white; box-shadow:0 10px 26px rgba(24,31,43,.06); min-height:118px; }
    .metric-card span { display:block; color:#6b7280; font-weight:800; margin-bottom:.35rem; font-size:.9rem; }
    .metric-card strong { font-size:2.05rem; line-height:1; }
    .metric-card small { display:block; color:#7a8491; margin-top:.55rem; line-height:1.4; }
    .brief-card { padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:#ffffff; min-height:142px; }
    .brief-card h4 { margin:0 0 .55rem 0; font-size:1.02rem; }
    .pill { display:inline-block; padding:.22rem .52rem; border:1px solid #d9dee7; border-radius:999px; margin:.15rem .25rem .35rem 0; color:#485160; font-size:.82rem; background:#fff; }
    .pill-red { border-color:#e2b7b4; color:#9f302b; background:#fff7f6; }
    .item-title { font-size:1.04rem; font-weight:850; margin-bottom:.35rem; }
    .source-meta { color:#68707d; font-size:.86rem; line-height:1.5; }
    .quote,.output { white-space:pre-wrap; line-height:1.72; padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:white; }
    .quote { border-left:4px solid #c9443e; background:#fff7f6; }
    .small-muted { color:#7a8491; font-size:.86rem; line-height:1.55; }
    div.stButton > button[kind="primary"] { background:#c9443e; border-color:#c9443e; }
    div.stButton > button { border-radius:6px; font-weight:800; }
    </style>
    """,
    unsafe_allow_html=True,
)


USER_AGENT = "EditorialLifeLab/0.4 (+https://streamlit.app)"

SOURCE_GROUPS = {
    "news_rss": "뉴스 RSS 일괄 취합",
    "crypto_media": "크립토 전문 미디어",
    "community": "커뮤니티 인기글",
    "market_intel": "큰손/온체인 레퍼런스",
}

TOPIC_ALIASES = {
    "이더리움클래식": ["이더리움클래식", "이더리움 클래식", "Ethereum Classic", "ETC", "$ETC", "ethereumclassic"],
    "이더리움 클래식": ["이더리움클래식", "이더리움 클래식", "Ethereum Classic", "ETC", "$ETC", "ethereumclassic"],
    "etc": ["Ethereum Classic", "ETC", "$ETC", "이더리움클래식", "ethereumclassic"],
    "비트코인": ["비트코인", "Bitcoin", "BTC", "$BTC"],
    "btc": ["Bitcoin", "BTC", "$BTC", "비트코인"],
    "이더리움": ["이더리움", "Ethereum", "ETH", "$ETH"],
    "eth": ["Ethereum", "ETH", "$ETH", "이더리움"],
    "솔라나": ["솔라나", "Solana", "SOL", "$SOL"],
    "sol": ["Solana", "SOL", "$SOL", "솔라나"],
    "엔비디아": ["엔비디아", "NVIDIA", "NVDA", "$NVDA"],
    "nvda": ["NVIDIA", "NVDA", "$NVDA", "엔비디아"],
}

RSS_SOURCES = [
    {"group": "news_rss", "name": "Google News KR", "mode": "query", "url_template": "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko", "weight": 1.2},
    {"group": "news_rss", "name": "Google News Global", "mode": "query", "url_template": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en", "weight": 1.15},
    {"group": "crypto_media", "name": "CoinDesk", "mode": "feed", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "weight": 1.2},
    {"group": "crypto_media", "name": "Cointelegraph", "mode": "feed", "url": "https://cointelegraph.com/rss", "weight": 1.05},
    {"group": "crypto_media", "name": "Decrypt", "mode": "feed", "url": "https://decrypt.co/feed", "weight": 1.05},
    {"group": "crypto_media", "name": "CryptoSlate", "mode": "feed", "url": "https://cryptoslate.com/feed/", "weight": 1.0},
    {"group": "crypto_media", "name": "NewsBTC", "mode": "feed", "url": "https://newsbtc.com/feed/", "weight": 0.95},
    {"group": "crypto_media", "name": "BeInCrypto", "mode": "feed", "url": "https://beincrypto.com/feed/", "weight": 0.95},
]

REDDIT_SOURCES = [
    {"group": "community", "name": "Reddit r/EthereumClassic", "sub": "EthereumClassic", "weight": 1.25},
    {"group": "community", "name": "Reddit r/CryptoCurrency", "sub": "CryptoCurrency", "weight": 1.15},
    {"group": "community", "name": "Reddit r/CryptoMarkets", "sub": "CryptoMarkets", "weight": 1.05},
    {"group": "community", "name": "Reddit r/ethtrader", "sub": "ethtrader", "weight": 1.0},
    {"group": "community", "name": "Reddit r/ethereum", "sub": "ethereum", "weight": 0.95},
    {"group": "community", "name": "Reddit r/wallstreetbets", "sub": "wallstreetbets", "weight": 0.9},
    {"group": "community", "name": "Reddit r/stocks", "sub": "stocks", "weight": 0.9},
]

REFERENCE_SOURCES = [
    {"group": "market_intel", "name": "Arkham", "url": "https://intel.arkm.com/", "use": "엔티티 지갑, 거래소 입금, 큰손 이동 검증"},
    {"group": "market_intel", "name": "Lookonchain", "url": "https://lookonchain.com/", "use": "고래 지갑과 스마트머니 이동을 빠르게 문장화하는 레이어"},
    {"group": "market_intel", "name": "Spot On Chain", "url": "https://spotonchain.ai/", "use": "지갑 평균단가, CEX 입출금, 잔여 포지션 확인"},
    {"group": "market_intel", "name": "Whale Alert", "url": "https://whale-alert.io/", "use": "대형 트랜잭션 알림과 체인 간 이동 확인"},
    {"group": "market_intel", "name": "Nansen", "url": "https://www.nansen.ai/", "use": "Smart Money 라벨, 펀드/트레이더 지갑 흐름"},
    {"group": "market_intel", "name": "DefiLlama", "url": "https://defillama.com/", "use": "TVL, 스테이블코인, ETF/DAT, CEX 투명성 데이터"},
    {"group": "market_intel", "name": "Unusual Whales", "url": "https://unusualwhales.com/", "use": "미국 주식 옵션 플로우, 다크풀, 의회 거래"},
    {"group": "market_intel", "name": "Quiver Quantitative", "url": "https://www.quiverquant.com/", "use": "대체 데이터, 의회 거래, 내부자 거래, WSB 추적"},
    {"group": "market_intel", "name": "SEC EDGAR", "url": "https://www.sec.gov/search-filings", "use": "Form 4, 13F, 8-K, 10-Q 등 원천 공시 확인"},
]

BULLISH_WORDS = {"surge", "rally", "breakout", "approval", "upgrade", "inflow", "accumulate", "bull", "rebound", "record", "상승", "급등", "반등", "호재", "승인", "유입", "업그레이드", "매수"}
BEARISH_WORDS = {"dump", "sell", "lawsuit", "hack", "exploit", "liquidation", "outflow", "bear", "crash", "plunge", "하락", "급락", "매도", "소송", "해킹", "청산", "유출", "규제"}
NOISE_WORDS = {"the", "and", "for", "with", "from", "that", "this", "into", "crypto", "bitcoin", "ethereum", "classic", "news", "says", "after", "over", "more", "about", "시장", "관련", "뉴스", "코인", "가상자산", "암호화폐", "이더리움", "이더리움클래식"}

for key, default in {"items": [], "brief": {}, "selected_url": "", "archive": [], "status": [], "last_query": "", "generated": {}}.items():
    st.session_state.setdefault(key, default)


def clean_text(value: str | None, limit: int = 1000) -> str:
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def topic_terms(keyword: str) -> list[str]:
    base = normalize_term(keyword)
    terms: list[str] = []
    for piece in re.split(r"[,/\n]", keyword):
        piece = normalize_term(piece)
        if piece:
            terms.append(piece)
    for key, aliases in sorted(TOPIC_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        key_norm = normalize_term(key)
        alias_norms = [normalize_term(x) for x in aliases]
        if base == key_norm or key_norm in base or base in alias_norms:
            terms.extend(aliases)
            break
    terms.append(keyword)
    deduped = []
    for term in terms:
        n = normalize_term(term)
        if n and n not in deduped:
            deduped.append(n)
    return deduped


def community_query(keyword: str) -> str:
    for term in topic_terms(keyword):
        if re.search(r"[A-Za-z]", term) and "$" not in term and len(term) > 2:
            return term
    return keyword


def query_string(keyword: str) -> str:
    terms = topic_terms(keyword)
    if len(terms) == 1:
        return terms[0]
    quoted = [f'"{term}"' if " " in term else term for term in terms[:5]]
    return " OR ".join(quoted)


def parse_date(value: str | None) -> tuple[str, float]:
    if not value:
        return "", 9999.0
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return clean_text(value, 80), 9999.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), max(age, 0.0)


def request_text(url: str, timeout: int = 9) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/json, text/xml, */*"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        tag = child.tag.split("}")[-1].lower()
        if tag in names:
            return clean_text("".join(child.itertext()), 1400)
    return ""


def child_link(node: ET.Element) -> str:
    link = child_text(node, {"link", "guid", "id"})
    if link:
        return link
    for child in list(node):
        tag = child.tag.split("}")[-1].lower()
        if tag == "link" and child.attrib.get("href"):
            return child.attrib["href"]
    return ""


def matches_topic(title: str, summary: str, terms: list[str]) -> bool:
    text = normalize_term(f"{title} {summary}")
    return not terms or any(term in text for term in terms)


def mood_of(text: str) -> tuple[str, int, int]:
    lower = normalize_term(text)
    bull = sum(1 for word in BULLISH_WORDS if word in lower)
    bear = sum(1 for word in BEARISH_WORDS if word in lower)
    if bull > bear:
        return "상방/호재", bull, bear
    if bear > bull:
        return "하방/리스크", bull, bear
    return "중립/관망", bull, bear


def theme_terms(items: list[dict], keyword: str, count: int = 8) -> list[tuple[str, int]]:
    aliases = set(topic_terms(keyword))
    bucket: dict[str, int] = {}
    for item in items:
        text = normalize_term(f"{item['title']} {item['summary']}")
        for token in re.findall(r"[A-Za-z][A-Za-z0-9$-]{2,}|[가-힣]{2,}", text):
            token = token.lower().strip("$")
            if token in NOISE_WORDS or token in aliases or len(token) < 2:
                continue
            bucket[token] = bucket.get(token, 0) + 1
    return sorted(bucket.items(), key=lambda x: x[1], reverse=True)[:count]


def item_score(source_weight: float, relevance: int, age_hours: float, popularity: float, bull: int, bear: int) -> int:
    recency = max(0, 24 - min(age_hours, 24)) * 1.15
    tension = min(14, (bull + bear) * 3.5)
    score = 28 + source_weight * 12 + relevance * 8 + recency + popularity + tension
    return int(max(1, min(99, round(score))))


def make_item(*, source: str, group: str, source_type: str, title: str, summary: str, url: str, published: str = "", age_hours: float = 9999.0, source_weight: float = 1.0, popularity_raw: int = 0, comments: int = 0, origin: str = "rss", keyword: str) -> dict:
    terms = topic_terms(keyword)
    text = f"{title} {summary}"
    relevance = sum(1 for term in terms if term in normalize_term(text))
    mood, bull, bear = mood_of(text)
    popularity = min(24, log1p(max(popularity_raw, 0) + comments * 2) * 5)
    score = item_score(source_weight, relevance, age_hours, popularity, bull, bear)
    if origin == "reddit":
        signal = f"upvote {popularity_raw} / comment {comments}"
    elif origin == "hn":
        signal = f"point {popularity_raw} / comment {comments}"
    elif age_hours < 999:
        signal = f"{age_hours:.0f}시간 전"
    else:
        signal = "발행일 미확인"
    return {"id": f"{origin}-{abs(hash(url + title))}", "source": source, "group": group, "source_type": source_type, "title": clean_text(title, 180) or "Untitled", "summary": clean_text(summary, 900), "url": url, "published": published, "age_hours": age_hours, "score": score, "mood": mood, "popularity_raw": popularity_raw, "comments": comments, "signal": signal, "origin": origin, "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M")}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_rss_source(source: dict, keyword: str, limit: int) -> tuple[list[dict], str]:
    terms = topic_terms(keyword)
    url = source["url_template"].format(query=quote(query_string(keyword))) if source["mode"] == "query" else source["url"]
    try:
        xml_text = request_text(url)
        root = ET.fromstring(xml_text)
    except (HTTPError, URLError, TimeoutError, ET.ParseError, ValueError) as exc:
        return [], f"{source['name']}: 실패 ({type(exc).__name__})"
    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    items: list[dict] = []
    for node in nodes[: limit * 4]:
        title = child_text(node, {"title"})
        summary = child_text(node, {"description", "summary", "content", "encoded"})
        if source["mode"] == "feed" and not matches_topic(title, summary, terms):
            continue
        published, age_hours = parse_date(child_text(node, {"pubdate", "published", "updated", "dc:date"}))
        items.append(make_item(source=source["name"], group=source["group"], source_type="RSS", title=title, summary=summary, url=child_link(node), published=published, age_hours=age_hours, source_weight=float(source["weight"]), origin="rss", keyword=keyword))
        if len(items) >= limit:
            break
    return items, f"{source['name']}: {len(items)}개"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_reddit_source(source: dict, keyword: str, limit: int) -> tuple[list[dict], str]:
    params = urlencode({"q": community_query(keyword), "restrict_sr": "1", "sort": "hot", "t": "week", "limit": limit})
    url = f"https://www.reddit.com/r/{source['sub']}/search.json?{params}"
    try:
        data = json.loads(request_text(url, timeout=8))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return [], f"{source['name']}: 실패 ({type(exc).__name__})"
    posts = [child.get("data", {}) for child in data.get("data", {}).get("children", [])]
    items = []
    for post in posts:
        if post.get("stickied") or not post.get("title"):
            continue
        created = datetime.fromtimestamp(float(post.get("created_utc", 0) or 0), tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        items.append(make_item(source=source["name"], group="community", source_type="Community", title=post.get("title", ""), summary=post.get("selftext") or post.get("url_overridden_by_dest") or "", url=f"https://www.reddit.com{post.get('permalink', '')}", published=created.strftime("%Y-%m-%d %H:%M UTC"), age_hours=age_hours, source_weight=float(source["weight"]), popularity_raw=int(post.get("ups") or post.get("score") or 0), comments=int(post.get("num_comments") or 0), origin="reddit", keyword=keyword))
    return items, f"{source['name']}: {len(items)}개"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_hacker_news(keyword: str, limit: int) -> tuple[list[dict], str]:
    url = f"https://hn.algolia.com/api/v1/search?{urlencode({'query': community_query(keyword), 'tags': 'story', 'hitsPerPage': limit})}"
    try:
        data = json.loads(request_text(url, timeout=8))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return [], f"Hacker News: 실패 ({type(exc).__name__})"
    items = []
    for hit in data.get("hits", []):
        created, age_hours = parse_date(hit.get("created_at"))
        items.append(make_item(source="Hacker News", group="community", source_type="Community", title=hit.get("title") or hit.get("story_title") or "", summary=hit.get("comment_text") or "", url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}", published=created, age_hours=age_hours, source_weight=0.95, popularity_raw=int(hit.get("points") or 0), comments=int(hit.get("num_comments") or 0), origin="hn", keyword=keyword))
    return items, f"Hacker News: {len(items)}개"


def dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped = []
    for item in sorted(items, key=lambda x: x["score"], reverse=True):
        key = normalize_term(item["url"] or item["title"])
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def run_collection(keyword: str, active_groups: list[str], per_source: int) -> tuple[list[dict], list[str]]:
    all_items: list[dict] = []
    status: list[str] = []
    for source in RSS_SOURCES:
        if source["group"] not in active_groups:
            continue
        items, msg = fetch_rss_source(source, keyword, per_source)
        all_items.extend(items)
        status.append(msg)
    if "community" in active_groups:
        for source in REDDIT_SOURCES:
            items, msg = fetch_reddit_source(source, keyword, max(3, per_source))
            all_items.extend(items)
            status.append(msg)
        hn_items, hn_msg = fetch_hacker_news(keyword, per_source)
        all_items.extend(hn_items)
        status.append(hn_msg)
    return dedupe_items(all_items), status


def build_brief(items: list[dict], keyword: str) -> dict:
    if not items:
        return {"tone": "자료 부족", "one_line": f"{keyword} 관련 자료가 충분히 수집되지 않았습니다.", "facts": [], "risks": ["검색어를 영문/티커와 함께 입력하거나 소스 그룹을 넓혀 다시 수집하세요."], "editorial": "지금은 판단보다 수집 범위를 먼저 편집해야 하는 구간입니다.", "themes": [], "top": []}
    mood_counts = pd.Series([x["mood"] for x in items]).value_counts().to_dict()
    top = sorted(items, key=lambda x: x["score"], reverse=True)[:6]
    recent_count = len([x for x in items if x["age_hours"] <= 24])
    community_count = len([x for x in items if x["group"] == "community"])
    bull = mood_counts.get("상방/호재", 0)
    bear = mood_counts.get("하방/리스크", 0)
    tone = "상방 재료 우세" if bull > bear * 1.35 else "리스크 재료 우세" if bear > bull * 1.35 else "혼조/관망"
    themes = theme_terms(items, keyword)
    facts = [f"총 {len(items)}개 자료 중 최근 24시간 자료는 {recent_count}개입니다.", f"커뮤니티 반응 기반 자료는 {community_count}개이며, 뉴스/RSS와 함께 교차검토가 필요합니다.", f"가장 강한 자료는 {top[0]['source']}의 '{top[0]['title']}'입니다."]
    if themes:
        facts.append("반복 키워드: " + ", ".join([name for name, _ in themes[:5]]))
    risk_words = []
    joined = normalize_term(" ".join([f"{x['title']} {x['summary']}" for x in items]))
    for label, words in {"레버리지/청산": ["liquidation", "leverage", "청산", "레버리지"], "규제/소송": ["lawsuit", "sec", "regulation", "소송", "규제"], "해킹/보안": ["hack", "exploit", "해킹", "익스플로잇"], "거래소/입출금": ["exchange", "deposit", "withdrawal", "거래소", "입금", "출금"]}.items():
        if any(word in joined for word in words):
            risk_words.append(label)
    risks = risk_words or ["강한 방향성보다 자료 간 온도 차이를 먼저 확인해야 합니다."]
    editorial = "남길 것: 원천 링크, 발행 시간, 커뮤니티 반응 수치. 덜어낼 것: 단일 속보만 보고 방향을 확정하는 습관. 순서를 바꿀 것: 가격 판단보다 자료의 출처와 지연 시간을 먼저 확인."
    return {"tone": tone, "one_line": f"{keyword} 장세는 '{tone}'입니다. 지금은 가격 예측보다 어떤 자료가 반복되고 어떤 자료가 과열인지 분리해야 합니다.", "facts": facts, "risks": risks, "editorial": editorial, "themes": themes, "top": top, "mood_counts": mood_counts}


def source_badge(item: dict) -> str:
    return f'<span class="pill pill-red">{escape(item["score"].__str__())} signal</span><span class="pill">{escape(item["source"])}</span><span class="pill">{escape(item["mood"])}</span><span class="pill">{escape(item["signal"])}</span>'


def item_card(item: dict, selectable: bool = False, key_prefix: str = "item") -> None:
    with st.container(border=True):
        st.markdown(f'<div class="item-title">{escape(item["title"])}</div>', unsafe_allow_html=True)
        st.markdown(source_badge(item), unsafe_allow_html=True)
        if item["summary"]:
            st.write(item["summary"])
        st.markdown(f'<div class="source-meta">{escape(item["source_type"])} · {escape(item["published"] or "발행일 미확인")} · <a href="{escape(item["url"])}" target="_blank">원문 열기</a></div>', unsafe_allow_html=True)
        with st.expander("수집 근거와 검수 포인트"):
            st.write(f"출처: {item['source']}")
            st.write(f"인기/반응 신호: {item['signal']}")
            st.write(f"자동 분류: {item['mood']}")
            st.write("검수 질문: 이 자료는 가격 방향을 말하는가, 아니면 사람들의 포지션 변화를 말하는가?")
        if selectable and st.button("제작실로 보내기", key=f"select-{key_prefix}-{item['id']}", use_container_width=True):
            st.session_state["selected_url"] = item["url"]
            st.session_state["generated"] = {}
            st.rerun()


def selected_item() -> dict | None:
    return next((item for item in st.session_state["items"] if item["url"] == st.session_state["selected_url"]), None)


def make_content(item: dict, brief: dict, tone: str) -> dict[str, str]:
    top_titles = "\n".join([f"- {x['title']} ({x['source']})" for x in brief.get("top", [])[:4]])
    longform = f"""제목: {item['title']}

오프닝
오늘의 주제는 {st.session_state.get('last_query', '')}입니다.
단순히 오른다, 내린다를 말하기 전에 지금 어떤 자료들이 반복되고 있는지 먼저 보겠습니다.

현재 장세 브리프
{brief.get('one_line', '')}

핵심 자료
{top_titles}

오늘의 원문
출처: {item['source']}
링크: {item['url']}
요약: {item['summary']}

Editorial Life 관점
{brief.get('editorial', '')}

정리
시장은 가격으로 움직이지만, 콘텐츠는 사람들이 어떤 자료를 붙잡고 있는지에서 시작됩니다.
{tone} 톤으로 말하자면, 지금 해야 할 일은 더 많은 확신을 더하는 것이 아니라 쓸 자료와 버릴 소음을 나누는 일입니다."""
    shorts = f"""1. {st.session_state.get('last_query', '')} 검색 결과에서 지금 반복되는 장면은 이것입니다.
2. {brief.get('one_line', '')}
3. 원문은 {item['source']}의 자료입니다.
4. 결론: 가격보다 먼저 자료의 출처와 지연 시간을 편집해야 합니다."""
    cards = f"""카드 1
{brief.get('tone', '장세 브리프')}

카드 2
핵심 자료: {item['title']}

카드 3
출처: {item['source']}
반응 신호: {item['signal']}

카드 4
남길 것: 원천 링크와 발행 시간
덜어낼 것: 단일 속보만 보고 방향을 확정하는 습관"""
    return {"롱폼": longform, "쇼츠": shorts, "카드뉴스": cards}


st.sidebar.markdown('<p class="eyebrow">Editorial Life</p>', unsafe_allow_html=True)
st.sidebar.title("Resource Collector")
st.sidebar.write("검색어 하나로 RSS, 뉴스, 커뮤니티 반응을 모으고 장세 브리프까지 만듭니다.")
st.sidebar.divider()
keyword = st.sidebar.text_input("검색 주제", value=st.session_state.get("last_query") or "이더리움클래식", placeholder="이더리움클래식, BTC, NVDA")
active_groups = [key for key, label in SOURCE_GROUPS.items() if key != "market_intel" and st.sidebar.checkbox(label, value=True)]
include_refs = st.sidebar.checkbox(SOURCE_GROUPS["market_intel"], value=True)
per_source = st.sidebar.slider("소스별 최대 수집", 3, 12, 6)
tone = st.sidebar.selectbox("제작 톤", ["차분하고 날카롭게", "시장 브리프 중심", "철학적 관찰자", "숏폼 훅 중심"])
if st.sidebar.button("수집 + 장세 브리프 생성", type="primary", use_container_width=True):
    with st.spinner("RSS와 커뮤니티 반응을 취합하는 중입니다."):
        items, status = run_collection(keyword, active_groups, per_source)
        st.session_state["items"] = items
        st.session_state["brief"] = build_brief(items, keyword)
        st.session_state["status"] = status
        st.session_state["selected_url"] = items[0]["url"] if items else ""
        st.session_state["generated"] = {}
        st.session_state["last_query"] = keyword
if st.sidebar.button("결과 초기화", use_container_width=True):
    st.session_state["items"] = []
    st.session_state["brief"] = {}
    st.session_state["selected_url"] = ""
    st.session_state["generated"] = {}

items = st.session_state["items"]
brief = st.session_state["brief"]
query_label = st.session_state.get("last_query") or keyword
community_count = len([x for x in items if x["group"] == "community"])
recent_count = len([x for x in items if x["age_hours"] <= 24])
avg_score = round(sum(x["score"] for x in items) / len(items)) if items else 0
st.markdown('<p class="eyebrow">Financial Self-Editing Console</p>', unsafe_allow_html=True)
st.title("Editorial Life 인사이트 수집실")
st.markdown('<p class="hero-line">주식, 코인, 지갑주소, 데이 트레이딩, 커뮤니티 반응을 하나의 자료 보드로 모읍니다. 검색어를 넣으면 관련 RSS와 커뮤니티 인기글을 취합하고, 현재 장세를 콘텐츠 관점으로 요약합니다.</p>', unsafe_allow_html=True)
alias_preview = ", ".join(topic_terms(query_label)[:6])
st.markdown(f'<span class="pill pill-red">검색어: {escape(query_label)}</span><span class="pill">확장어: {escape(alias_preview)}</span>', unsafe_allow_html=True)
metric_cols = st.columns(4)
for col, (label, value, help_text) in zip(metric_cols, [("수집 자료", len(items), "뉴스/RSS/커뮤니티 합산"), ("평균 Signal", avg_score, "관련도, 최신성, 반응 점수"), ("커뮤니티 반응", community_count, "Reddit/HN 기반 인기 자료"), ("최근 24시간", recent_count, "현재 장세에 가까운 자료")]):
    col.markdown(f'<div class="metric-card"><span>{label}</span><strong>{value}</strong><small>{help_text}</small></div>', unsafe_allow_html=True)
st.divider()
brief_tab, feed_tab, matrix_tab, studio_tab, library_tab = st.tabs(["Market Brief", "Live Feed", "Source Matrix", "Content Studio", "Source Library"])

with brief_tab:
    st.subheader("자동 장세 브리프")
    if not brief:
        st.info("왼쪽에서 검색 주제를 입력하고 수집을 실행하면 장세 브리프가 자동 생성됩니다.")
    else:
        st.markdown(f'<div class="quote">{escape(brief["one_line"])}</div>', unsafe_allow_html=True)
        cols = st.columns(3)
        for col, (title, body) in zip(cols, [("시장 톤", brief.get("tone", "-")), ("핵심 리스크", ", ".join(brief.get("risks", []))), ("반복 테마", ", ".join([x[0] for x in brief.get("themes", [])[:5]]) or "테마 부족")]):
            col.markdown(f'<div class="brief-card"><h4>{escape(title)}</h4><p>{escape(body)}</p></div>', unsafe_allow_html=True)
        st.markdown("#### 핵심 관찰")
        for fact in brief.get("facts", []):
            st.write(f"- {fact}")
        st.markdown("#### Editorial Life 편집점")
        st.write(brief.get("editorial", ""))
        st.markdown("#### 오늘의 핵심 자료")
        for item in brief.get("top", [])[:5]:
            item_card(item, selectable=True, key_prefix="brief")

with feed_tab:
    st.subheader("수집 자료 피드")
    if not items:
        st.info("수집된 자료가 없습니다.")
    else:
        with st.expander("수집 상태"):
            for msg in st.session_state["status"]:
                st.caption(msg)
        mood_filter = st.multiselect("시장 톤 필터", sorted({x["mood"] for x in items}), default=sorted({x["mood"] for x in items}))
        group_filter = st.multiselect("소스 그룹 필터", sorted({SOURCE_GROUPS.get(x["group"], x["group"]) for x in items}), default=sorted({SOURCE_GROUPS.get(x["group"], x["group"]) for x in items}))
        filtered = [item for item in items if item["mood"] in mood_filter and SOURCE_GROUPS.get(item["group"], item["group"]) in group_filter]
        left, right = st.columns([1.05, 0.95])
        with left:
            for item in filtered[:12]:
                item_card(item, selectable=True, key_prefix="feed")
        with right:
            table = pd.DataFrame([{"score": x["score"], "source": x["source"], "mood": x["mood"], "signal": x["signal"], "title": x["title"]} for x in filtered])
            st.dataframe(table, use_container_width=True, hide_index=True)

with matrix_tab:
    st.subheader("소스 매트릭스")
    if not items:
        st.info("수집을 실행하면 소스별 커버리지와 시장 톤 분포가 표시됩니다.")
    else:
        df = pd.DataFrame(items)
        group_summary = df.groupby(["group", "mood"]).size().reset_index(name="count").replace({"group": {key: value for key, value in SOURCE_GROUPS.items()}})
        st.bar_chart(group_summary, x="group", y="count", color="mood")
        source_summary = df.groupby("source").agg(count=("title", "count"), avg_score=("score", "mean"), community=("comments", "sum")).reset_index().sort_values(["count", "avg_score"], ascending=False)
        source_summary["avg_score"] = source_summary["avg_score"].round(1)
        st.dataframe(source_summary, use_container_width=True, hide_index=True)

with studio_tab:
    st.subheader("콘텐츠 제작실")
    item = selected_item()
    if not item:
        st.info("Market Brief나 Live Feed에서 제작실로 보낼 자료를 선택하세요.")
    else:
        left, right = st.columns([0.85, 1.15])
        with left:
            item_card(item)
        with right:
            if st.button("브리프 기반 대본 생성", type="primary", use_container_width=True):
                st.session_state["generated"] = make_content(item, brief or build_brief(items, query_label), tone)
            if st.session_state["generated"]:
                output_type = st.radio("결과 유형", ["롱폼", "쇼츠", "카드뉴스"], horizontal=True)
                st.markdown(f'<div class="output">{escape(st.session_state["generated"][output_type])}</div>', unsafe_allow_html=True)
                if st.button("아카이브 저장", use_container_width=True):
                    st.session_state["archive"].insert(0, {"created_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "query": query_label, "item": item, "brief": brief})
                    st.success("아카이브에 저장했습니다.")
            else:
                st.info("선택 자료와 장세 브리프를 묶어 대본을 생성할 수 있습니다.")

with library_tab:
    st.subheader("소스 라이브러리")
    st.write("RSS는 자동 수집 대상이고, 큰손/온체인 레퍼런스는 원천 검증용 링크로 사용합니다.")
    st.markdown("#### 자동 수집 RSS")
    for source in RSS_SOURCES:
        with st.container(border=True):
            st.markdown(f"**{source['name']}**")
            st.caption(SOURCE_GROUPS[source["group"]])
            st.markdown(f"[피드 열기]({source.get('url') or source.get('url_template', '').format(query=quote(query_string(query_label)))})")
    if include_refs:
        st.markdown("#### 원천 검증 레퍼런스")
        for source in REFERENCE_SOURCES:
            with st.container(border=True):
                st.markdown(f"**{source['name']}**")
                st.caption(SOURCE_GROUPS[source["group"]])
                st.write(source["use"])
                st.markdown(f"[사이트 열기]({source['url']})")
    st.markdown("#### 아카이브")
    if not st.session_state["archive"]:
        st.info("저장된 제작 패키지가 없습니다.")
    for package in st.session_state["archive"]:
        st.caption(f"{package['created_at']} · {package['query']}")
        st.write(package["item"]["title"])
