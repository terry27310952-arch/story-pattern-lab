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
    .block-container { padding-top:1.55rem; max-width:1280px; }
    [data-testid="stSidebar"] { background:#eef1f5; }
    .eyebrow { color:#9f302b; font-size:.78rem; font-weight:800; text-transform:uppercase; letter-spacing:.03em; }
    .hero-line { color:#596272; max-width:800px; line-height:1.65; }
    .metric-card,.export-card { padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:#fff; box-shadow:0 10px 26px rgba(24,31,43,.06); min-height:112px; }
    .metric-card span,.export-card span { display:block; color:#6b7280; font-weight:800; margin-bottom:.35rem; font-size:.88rem; }
    .metric-card strong,.export-card strong { display:block; font-size:2.02rem; line-height:1; margin-bottom:.5rem; }
    .metric-card small,.export-card small { display:block; color:#7a8491; line-height:1.4; }
    .pill { display:inline-block; padding:.22rem .52rem; border:1px solid #d9dee7; border-radius:999px; margin:.15rem .25rem .35rem 0; color:#485160; font-size:.82rem; background:#fff; }
    .pill-red { border-color:#e2b7b4; color:#9f302b; background:#fff7f6; }
    .item-title { font-size:1.04rem; font-weight:850; margin-bottom:.35rem; }
    .source-meta { color:#68707d; font-size:.86rem; line-height:1.5; }
    .source-text { white-space:pre-wrap; line-height:1.68; padding:1rem; border:1px solid #dce1e7; border-radius:8px; background:#fff; max-height:360px; overflow:auto; }
    .small-muted { color:#7a8491; font-size:.86rem; line-height:1.55; }
    div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"] { background:#c9443e; border-color:#c9443e; }
    div.stButton > button, div.stDownloadButton > button { border-radius:6px; font-weight:800; }
    </style>
    """,
    unsafe_allow_html=True,
)


USER_AGENT = "EditorialLifeLab/0.5 (+https://streamlit.app)"

SOURCE_GROUPS = {
    "news_rss": "뉴스 RSS 일괄 취합",
    "crypto_media": "크립토 전문 미디어",
    "community": "커뮤니티 인기글",
    "market_intel": "큰손/온체인 레퍼런스",
}

TOPIC_ALIASES = {
    "이더리움클래식": ["이더리움클래식", "이더리움 클래식", "Ethereum Classic", "$ETC", "ETC coin", "ETC/USDT", "ethereumclassic"],
    "이더리움 클래식": ["이더리움클래식", "이더리움 클래식", "Ethereum Classic", "$ETC", "ETC coin", "ETC/USDT", "ethereumclassic"],
    "etc": ["Ethereum Classic", "$ETC", "ETC coin", "ETC/USDT", "이더리움클래식", "ethereumclassic"],
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
    {
        "group": "news_rss",
        "name": "Google News KR",
        "mode": "query",
        "url_template": "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko",
        "weight": 1.2,
    },
    {
        "group": "news_rss",
        "name": "Google News Global",
        "mode": "query",
        "url_template": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
        "weight": 1.15,
    },
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


def clean_text(value: str | None, limit: int = 1000) -> str:
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def html_to_text(value: str, limit: int = 9000) -> str:
    value = re.sub(r"(?is)<(script|style|noscript|svg|canvas|form|nav|footer|header).*?</\1>", " ", value)
    value = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    value = unescape(value)
    lines = []
    for line in value.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) >= 24:
            lines.append(line)
    return "\n".join(lines)[:limit]


def safe_filename(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", value).strip("_")
    return safe or "market_sources"


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def topic_terms(keyword: str) -> list[str]:
    base = normalize_term(keyword)
    terms: list[str] = []
    for piece in re.split(r"[,/\n]", keyword):
        piece = normalize_term(piece)
        if piece:
            terms.append(piece)
    for key, aliases in sorted(TOPIC_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        key_norm = normalize_term(key)
        alias_norms = [normalize_term(alias) for alias in aliases]
        if base == key_norm or key_norm in base or base in alias_norms or any(alias in base for alias in alias_norms):
            terms.extend(aliases)
            break
    terms.append(keyword)
    deduped = []
    for term in terms:
        normalized = normalize_term(term)
        if normalized == "etc":
            continue
        if normalized and normalized not in deduped:
            deduped.append(normalized)
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
    quoted = [f'"{term}"' if " " in term else term for term in terms[:6]]
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


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_original_text(url: str, fallback: str = "") -> tuple[str, str]:
    fallback_text = clean_text(fallback, 5000)
    if not url or not url.startswith("http"):
        return fallback_text, "fallback_no_url"
    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
            },
        )
        with urlopen(request, timeout=8) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(850_000)
        if "pdf" in content_type or "image/" in content_type or "video/" in content_type:
            return fallback_text, "fallback_binary"
        original_text = html_to_text(raw.decode(charset, errors="replace"))
        if len(original_text) < 240:
            return fallback_text, "fallback_short"
        return original_text, "html_body"
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return fallback_text, f"fallback_{type(exc).__name__}"


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


def item_score(source_weight: float, relevance: int, age_hours: float, popularity: float, bull: int, bear: int) -> int:
    recency = max(0, 24 - min(age_hours, 24)) * 1.15
    tension = min(14, (bull + bear) * 3.5)
    score = 28 + source_weight * 12 + relevance * 8 + recency + popularity + tension
    return int(max(1, min(99, round(score))))


def make_item(
    *,
    source: str,
    group: str,
    source_type: str,
    title: str,
    summary: str,
    url: str,
    published: str = "",
    age_hours: float = 9999.0,
    source_weight: float = 1.0,
    popularity_raw: int = 0,
    comments: int = 0,
    origin: str = "rss",
    keyword: str,
) -> dict:
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
    return {
        "id": f"{origin}-{abs(hash(url + title))}",
        "source": source,
        "group": group,
        "source_type": source_type,
        "title": clean_text(title, 180) or "Untitled",
        "summary": clean_text(summary, 900),
        "original_text": clean_text(summary, 5000),
        "content_status": "feed_summary",
        "url": url,
        "published": published,
        "age_hours": age_hours,
        "score": score,
        "mood": mood,
        "popularity_raw": popularity_raw,
        "comments": comments,
        "signal": signal,
        "origin": origin,
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_rss_source(source: dict, keyword: str, limit: int) -> tuple[list[dict], str]:
    terms = topic_terms(keyword)
    url = source["url_template"].format(query=quote(query_string(keyword))) if source["mode"] == "query" else source["url"]
    try:
        root = ET.fromstring(request_text(url))
    except (HTTPError, URLError, TimeoutError, ET.ParseError, ValueError) as exc:
        return [], f"{source['name']}: 실패 ({type(exc).__name__})"

    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    items: list[dict] = []
    for node in nodes[: limit * 4]:
        title = child_text(node, {"title"})
        summary = child_text(node, {"description", "summary", "content", "encoded"})
        if source["mode"] == "feed" and not matches_topic(title, summary, terms):
            continue
        published, age_hours = parse_date(child_text(node, {"pubdate", "published", "updated", "date"}))
        items.append(
            make_item(
                source=source["name"],
                group=source["group"],
                source_type="RSS",
                title=title,
                summary=summary,
                url=child_link(node),
                published=published,
                age_hours=age_hours,
                source_weight=float(source["weight"]),
                origin="rss",
                keyword=keyword,
            )
        )
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
        summary = post.get("selftext") or post.get("url_overridden_by_dest") or ""
        items.append(
            make_item(
                source=source["name"],
                group="community",
                source_type="Community",
                title=post.get("title", ""),
                summary=summary,
                url=f"https://www.reddit.com{post.get('permalink', '')}",
                published=created.strftime("%Y-%m-%d %H:%M UTC"),
                age_hours=age_hours,
                source_weight=float(source["weight"]),
                popularity_raw=int(post.get("ups") or post.get("score") or 0),
                comments=int(post.get("num_comments") or 0),
                origin="reddit",
                keyword=keyword,
            )
        )
    return items, f"{source['name']}: {len(items)}개"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_hacker_news(keyword: str, limit: int) -> tuple[list[dict], str]:
    params = urlencode({"query": community_query(keyword), "tags": "story", "hitsPerPage": limit})
    url = f"https://hn.algolia.com/api/v1/search?{params}"
    try:
        data = json.loads(request_text(url, timeout=8))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return [], f"Hacker News: 실패 ({type(exc).__name__})"
    items = []
    for hit in data.get("hits", []):
        created, age_hours = parse_date(hit.get("created_at"))
        items.append(
            make_item(
                source="Hacker News",
                group="community",
                source_type="Community",
                title=hit.get("title") or hit.get("story_title") or "",
                summary=hit.get("comment_text") or "",
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                published=created,
                age_hours=age_hours,
                source_weight=0.95,
                popularity_raw=int(hit.get("points") or 0),
                comments=int(hit.get("num_comments") or 0),
                origin="hn",
                keyword=keyword,
            )
        )
    return items, f"Hacker News: {len(items)}개"


def dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped = []
    for item in sorted(items, key=lambda value: value["score"], reverse=True):
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


def export_rows(items: list[dict], keyword: str) -> list[dict]:
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            {
                "rank": index,
                "query": keyword,
                "captured_at": item.get("captured_at", ""),
                "source_group": SOURCE_GROUPS.get(item.get("group", ""), item.get("group", "")),
                "source": item.get("source", ""),
                "source_type": item.get("source_type", ""),
                "origin": item.get("origin", ""),
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "original_text": item.get("original_text") or item.get("summary", ""),
                "content_status": item.get("content_status", "feed_summary"),
                "url": item.get("url", ""),
                "published": item.get("published", ""),
                "age_hours": round(float(item.get("age_hours") or 9999), 2),
                "score": item.get("score", 0),
                "mood": item.get("mood", ""),
                "signal": item.get("signal", ""),
                "popularity_raw": item.get("popularity_raw", 0),
                "comments": item.get("comments", 0),
            }
        )
    return rows


def csv_payload(items: list[dict], keyword: str) -> bytes:
    return pd.DataFrame(export_rows(items, keyword)).to_csv(index=False).encode("utf-8-sig")


def source_badge(item: dict) -> str:
    return (
        f'<span class="pill pill-red">{escape(str(item["score"]))} signal</span>'
        f'<span class="pill">{escape(item["source"])}</span>'
        f'<span class="pill">{escape(item["mood"])}</span>'
        f'<span class="pill">{escape(item["signal"])}</span>'
        f'<span class="pill">{escape(item.get("content_status", "feed_summary"))}</span>'
    )


def item_card(item: dict) -> None:
    with st.container(border=True):
        st.markdown(f'<div class="item-title">{escape(item["title"])}</div>', unsafe_allow_html=True)
        st.markdown(source_badge(item), unsafe_allow_html=True)
        if item["summary"]:
            st.write(item["summary"])
        st.markdown(
            f'<div class="source-meta">{escape(item["source_type"])} · {escape(item["published"] or "발행일 미확인")} · '
            f'<a href="{escape(item["url"])}" target="_blank">원문 열기</a></div>',
            unsafe_allow_html=True,
        )
        with st.expander("CSV에 들어갈 원문 텍스트 미리보기"):
            text = item.get("original_text") or item.get("summary") or ""
            st.markdown(f'<div class="source-text">{escape(text[:5000] or "원문 텍스트가 비어 있습니다.")}</div>', unsafe_allow_html=True)


for key, default in {"items": [], "status": [], "last_query": ""}.items():
    st.session_state.setdefault(key, default)


st.sidebar.markdown('<p class="eyebrow">Editorial Life</p>', unsafe_allow_html=True)
st.sidebar.title("Source Collector")
st.sidebar.write("브리프 생성보다 원문 확보가 먼저입니다. 수집한 자료를 LLM 입력용 CSV로 정리합니다.")
st.sidebar.divider()

keyword = st.sidebar.text_input("검색 주제", value=st.session_state.get("last_query") or "이더리움클래식", placeholder="이더리움클래식, BTC, NVDA")
active_groups = [
    key for key, label in SOURCE_GROUPS.items() if key != "market_intel" and st.sidebar.checkbox(label, value=True)
]
include_refs = st.sidebar.checkbox(SOURCE_GROUPS["market_intel"], value=True)
per_source = st.sidebar.slider("소스별 최대 수집", 3, 12, 6)

if st.sidebar.button("수집 + CSV 데이터 생성", type="primary", use_container_width=True):
    with st.spinner("RSS와 커뮤니티 반응을 취합하는 중입니다."):
        items, status = run_collection(keyword, active_groups, per_source)
        st.session_state["items"] = items
        st.session_state["status"] = status
        st.session_state["last_query"] = keyword

if st.sidebar.button("결과 초기화", use_container_width=True):
    st.session_state["items"] = []
    st.session_state["status"] = []
    st.session_state["last_query"] = ""

items = st.session_state["items"]
query_label = st.session_state.get("last_query") or keyword
community_count = len([item for item in items if item["group"] == "community"])
recent_count = len([item for item in items if item["age_hours"] <= 24])
body_count = len([item for item in items if item.get("content_status") == "html_body"])
avg_score = round(sum(item["score"] for item in items) / len(items)) if items else 0

st.markdown('<p class="eyebrow">Financial Self-Editing Console</p>', unsafe_allow_html=True)
st.title("Editorial Life 원자료 수집실")
st.markdown(
    '<p class="hero-line">주식, 코인, 지갑주소, 데이 트레이딩, 커뮤니티 반응을 하나의 원자료 테이블로 모읍니다. '
    "검색어를 넣으면 RSS와 커뮤니티 인기글을 취합하고, 원문 텍스트/링크/반응 수치를 CSV로 내려받을 수 있습니다.</p>",
    unsafe_allow_html=True,
)

alias_preview = ", ".join(topic_terms(query_label)[:6])
st.markdown(f'<span class="pill pill-red">검색어: {escape(query_label)}</span><span class="pill">확장어: {escape(alias_preview)}</span>', unsafe_allow_html=True)

metric_cols = st.columns(4)
metrics = [
    ("수집 자료", len(items), "뉴스/RSS/커뮤니티 합산"),
    ("평균 Signal", avg_score, "관련도, 최신성, 반응 점수"),
    ("커뮤니티 반응", community_count, "Reddit/HN 기반 인기 자료"),
    ("본문 보강", body_count, "HTML 원문 추출 완료 자료"),
]
for col, (label, value, help_text) in zip(metric_cols, metrics):
    col.markdown(f'<div class="metric-card"><span>{label}</span><strong>{value}</strong><small>{help_text}</small></div>', unsafe_allow_html=True)

st.divider()

export_tab, feed_tab, matrix_tab, library_tab = st.tabs(["Data Export", "Live Feed", "Source Matrix", "Source Library"])

with export_tab:
    st.subheader("CSV 원자료 내보내기")
    if not items:
        st.info("왼쪽에서 검색 주제를 입력하고 수집을 실행하면 CSV 다운로드가 열립니다.")
    else:
        export_cols = st.columns(3)
        export_cols[0].markdown(f'<div class="export-card"><span>CSV 행</span><strong>{len(items)}</strong><small>수집된 자료 전체</small></div>', unsafe_allow_html=True)
        export_cols[1].markdown(f'<div class="export-card"><span>본문 보강</span><strong>{body_count}</strong><small>HTML 원문 추출 완료</small></div>', unsafe_allow_html=True)
        export_cols[2].markdown(f'<div class="export-card"><span>최근 24시간</span><strong>{recent_count}</strong><small>발행 시점 기준</small></div>', unsafe_allow_html=True)

        file_name = f"editorial_life_{safe_filename(query_label)}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        st.download_button(
            "CSV 다운로드",
            data=csv_payload(items, query_label),
            file_name=file_name,
            mime="text/csv",
            type="primary",
            use_container_width=True,
            key="download-source-csv",
        )
        st.caption("CSV는 Excel에서 바로 열기 쉽도록 UTF-8 BOM으로 저장합니다. 본문 보강 전에는 RSS 요약/selftext가 original_text 컬럼에 들어갑니다.")

        st.markdown("#### 원문 본문 보강")
        if len(items) == 1:
            enrich_count = 1
            st.caption("본문 보강 대상: 상위 1개 자료")
        else:
            enrich_count = st.slider("본문을 추가로 긁어올 상위 자료 수", 1, len(items), min(len(items), 20))
        if st.button("상위 자료 원문 본문 보강", use_container_width=True):
            updated_items = [dict(item) for item in items]
            progress = st.progress(0)
            for index, item in enumerate(updated_items[:enrich_count], start=1):
                original_text, content_status = fetch_original_text(item.get("url", ""), item.get("summary", ""))
                item["original_text"] = original_text
                item["content_status"] = content_status
                progress.progress(index / enrich_count)
            st.session_state["items"] = updated_items
            st.success(f"{enrich_count}개 자료의 원문 본문 보강을 시도했습니다.")
            st.rerun()

        with st.expander("수집 로그"):
            for msg in st.session_state["status"]:
                st.caption(msg)

        st.markdown("#### CSV 미리보기")
        preview = pd.DataFrame(export_rows(items, query_label))
        preview_cols = ["rank", "score", "source", "content_status", "published", "title", "url"]
        st.dataframe(preview[preview_cols], use_container_width=True, hide_index=True)

with feed_tab:
    st.subheader("수집 자료 피드")
    if not items:
        st.info("수집된 자료가 없습니다.")
    else:
        mood_options = sorted({item["mood"] for item in items})
        group_options = sorted({SOURCE_GROUPS.get(item["group"], item["group"]) for item in items})
        mood_filter = st.multiselect("시장 톤 필터", mood_options, default=mood_options)
        group_filter = st.multiselect("소스 그룹 필터", group_options, default=group_options)
        filtered = [
            item
            for item in items
            if item["mood"] in mood_filter and SOURCE_GROUPS.get(item["group"], item["group"]) in group_filter
        ]
        left, right = st.columns([1.05, 0.95])
        with left:
            for item in filtered[:14]:
                item_card(item)
        with right:
            table = pd.DataFrame(
                [
                    {
                        "score": item["score"],
                        "source": item["source"],
                        "mood": item["mood"],
                        "signal": item["signal"],
                        "content_status": item.get("content_status", "feed_summary"),
                        "title": item["title"],
                    }
                    for item in filtered
                ]
            )
            st.dataframe(table, use_container_width=True, hide_index=True)

with matrix_tab:
    st.subheader("소스 매트릭스")
    if not items:
        st.info("수집을 실행하면 소스별 커버리지와 원문 보강 상태가 표시됩니다.")
    else:
        df = pd.DataFrame(items)
        df["source_group"] = df["group"].map(SOURCE_GROUPS).fillna(df["group"])
        group_summary = df.groupby(["source_group", "mood"]).size().reset_index(name="count")
        st.bar_chart(group_summary, x="source_group", y="count", color="mood")
        source_summary = (
            df.groupby("source")
            .agg(
                count=("title", "count"),
                avg_score=("score", "mean"),
                comments=("comments", "sum"),
                body_ready=("content_status", lambda values: int((values == "html_body").sum())),
            )
            .reset_index()
            .sort_values(["count", "avg_score"], ascending=False)
        )
        source_summary["avg_score"] = source_summary["avg_score"].round(1)
        st.dataframe(source_summary, use_container_width=True, hide_index=True)

with library_tab:
    st.subheader("소스 라이브러리")
    st.write("RSS와 커뮤니티는 자동 수집 대상이고, 큰손/온체인 레퍼런스는 원천 검증 링크로 사용합니다.")
    st.markdown("#### 자동 수집 RSS")
    for source in RSS_SOURCES:
        with st.container(border=True):
            feed_url = source.get("url") or source.get("url_template", "").format(query=quote(query_string(query_label)))
            st.markdown(f"**{source['name']}**")
            st.caption(SOURCE_GROUPS[source["group"]])
            st.markdown(f"[피드 열기]({feed_url})")
    st.markdown("#### 커뮤니티 수집")
    for source in REDDIT_SOURCES:
        with st.container(border=True):
            st.markdown(f"**{source['name']}**")
            st.caption("Reddit hot/week search")
    st.markdown("#### 원천 검증 레퍼런스")
    if include_refs:
        for source in REFERENCE_SOURCES:
            with st.container(border=True):
                st.markdown(f"**{source['name']}**")
                st.caption(SOURCE_GROUPS[source["group"]])
                st.write(source["use"])
                st.markdown(f"[사이트 열기]({source['url']})")
    else:
        st.info("왼쪽 사이드바에서 큰손/온체인 레퍼런스를 켜면 표시됩니다.")
