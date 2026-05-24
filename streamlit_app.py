from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from math import log1p
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Story Pattern Lab", page_icon="SP", layout="wide")
st.markdown(
    """
<style>
.block-container{padding-top:1.35rem;max-width:1320px}
[data-testid="stSidebar"]{background:#eef1f5}
.eyebrow{color:#9f302b;font-size:.78rem;font-weight:800;text-transform:uppercase;letter-spacing:.03em}
.hero-line{color:#596272;max-width:900px;line-height:1.65}
.metric-card,.export-card{padding:1rem;border:1px solid #dce1e7;border-radius:8px;background:#fff;box-shadow:0 10px 26px rgba(24,31,43,.06);min-height:112px}
.metric-card span,.export-card span{display:block;color:#6b7280;font-weight:800;margin-bottom:.35rem;font-size:.88rem}
.metric-card strong,.export-card strong{display:block;font-size:2.02rem;line-height:1;margin-bottom:.5rem;color:#171b23}
.metric-card small,.export-card small{display:block;color:#7a8491;line-height:1.4}
.pill{display:inline-block;padding:.22rem .52rem;border:1px solid #d9dee7;border-radius:999px;margin:.15rem .25rem .35rem 0;color:#485160;font-size:.82rem;background:#fff}
.pill-red{border-color:#e2b7b4;color:#9f302b;background:#fff7f6}
.pill-green{border-color:#b7d8bf;color:#236b38;background:#f5fbf6}
.pill-amber{border-color:#e7d5a8;color:#805b13;background:#fffaf0}
.item-title{font-size:1.08rem;font-weight:850;margin-bottom:.35rem}
.source-meta{color:#68707d;font-size:.86rem;line-height:1.5}
.source-text{white-space:pre-wrap;line-height:1.68;padding:1rem;border:1px solid #dce1e7;border-radius:8px;background:#fff;max-height:360px;overflow:auto}
.small-muted{color:#7a8491;font-size:.86rem;line-height:1.55}
div.stButton>button[kind="primary"],div.stDownloadButton>button[kind="primary"]{background:#c9443e;border-color:#c9443e}
div.stButton>button,div.stDownloadButton>button{border-radius:6px;font-weight:800}
</style>
""",
    unsafe_allow_html=True,
)


USER_AGENT = "StoryPatternLab/0.7 (+https://streamlit.app)"

SOURCE_GROUPS = {
    "news_rss": "뉴스 RSS",
    "crypto_media": "크립토 미디어",
    "community": "커뮤니티 반응",
    "macro_channels": "거시경제 채널",
    "trading_channels": "트레이딩 채널",
    "market_intel": "온체인/마켓 레퍼런스",
}

SOURCE_GROUP_META = {
    "news_rss": {"country_group": "domestic/global", "collection_method": "RSS query", "policy_risk_level": "low"},
    "crypto_media": {"country_group": "overseas", "collection_method": "RSS feed", "policy_risk_level": "low"},
    "community": {"country_group": "overseas", "collection_method": "public API/RSS", "policy_risk_level": "medium"},
    "macro_channels": {"country_group": "overseas", "collection_method": "Podcast/YouTube RSS", "policy_risk_level": "low"},
    "trading_channels": {"country_group": "overseas", "collection_method": "YouTube RSS", "policy_risk_level": "low"},
    "market_intel": {"country_group": "reference", "collection_method": "manual reference", "policy_risk_level": "low"},
}

DEFAULT_GROUPS = {"news_rss", "crypto_media", "community"}

STATUS_OPTIONS = ["collected", "candidate", "approved", "needs_review", "rejected", "archived"]
STATUS_LABELS = {
    "collected": "수집됨",
    "candidate": "후보",
    "approved": "제작 승인",
    "needs_review": "리스크 검토",
    "rejected": "제외",
    "archived": "보관",
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
    {"group": "news_rss", "name": "Google News KR", "mode": "query", "url_template": "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko", "weight": 1.2},
    {"group": "news_rss", "name": "Google News Global", "mode": "query", "url_template": "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en", "weight": 1.15},
    {"group": "crypto_media", "name": "CoinDesk", "mode": "feed", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "weight": 1.2},
    {"group": "crypto_media", "name": "Cointelegraph", "mode": "feed", "url": "https://cointelegraph.com/rss", "weight": 1.05},
    {"group": "crypto_media", "name": "Decrypt", "mode": "feed", "url": "https://decrypt.co/feed", "weight": 1.05},
    {"group": "crypto_media", "name": "CryptoSlate", "mode": "feed", "url": "https://cryptoslate.com/feed/", "weight": 1.0},
    {"group": "crypto_media", "name": "NewsBTC", "mode": "feed", "url": "https://newsbtc.com/feed/", "weight": 0.95},
    {"group": "crypto_media", "name": "BeInCrypto", "mode": "feed", "url": "https://beincrypto.com/feed/", "weight": 0.95},
    {"group": "macro_channels", "name": "Macro Voices", "mode": "feed", "url": "https://feed.podbean.com/macrovoices/feed.xml", "weight": 1.2, "match": "latest", "source_type": "Podcast RSS"},
    {"group": "macro_channels", "name": "Real Vision", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCGXWKlq1Oxr3ddEtmKhAkPg", "weight": 1.12, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "macro_channels", "name": "Forward Guidance", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCkrwgzhIBKccuDsi_SvZtnQ", "weight": 1.15, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "macro_channels", "name": "Eurodollar University", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCrXNkk4IESnqU-8GMad2vyA", "weight": 1.12, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "macro_channels", "name": "CME Group", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCLC4PuFlyKwK03Sc29YLEGQ", "weight": 1.0, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "trading_channels", "name": "SMB Capital", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCg3B_joekBGJ1s_4fRjsMKA", "weight": 1.15, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "trading_channels", "name": "TraderTV Live", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCn75vF3UxwWeWPAY4-5Z6HQ", "weight": 1.05, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "trading_channels", "name": "TheChartGuys", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCnqZ2hx679DqRi6khRUNw2g", "weight": 1.02, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "trading_channels", "name": "Rayner Teo", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCFSn-h8wTnhpKJMteN76Abg", "weight": 1.08, "match": "latest", "source_type": "YouTube RSS"},
    {"group": "trading_channels", "name": "Tastytrade", "mode": "feed", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC_PAASO4wwhMviJc3rqkPxg", "weight": 1.0, "match": "latest", "source_type": "YouTube RSS"},
]

REDDIT_SOURCES = [
    {"name": "Reddit r/EthereumClassic", "sub": "EthereumClassic", "weight": 1.25},
    {"name": "Reddit r/CryptoCurrency", "sub": "CryptoCurrency", "weight": 1.15},
    {"name": "Reddit r/CryptoMarkets", "sub": "CryptoMarkets", "weight": 1.05},
    {"name": "Reddit r/ethtrader", "sub": "ethtrader", "weight": 1.0},
    {"name": "Reddit r/ethereum", "sub": "ethereum", "weight": 0.95},
    {"name": "Reddit r/wallstreetbets", "sub": "wallstreetbets", "weight": 0.9},
    {"name": "Reddit r/stocks", "sub": "stocks", "weight": 0.9},
]

REFERENCE_SOURCES = [
    {"name": "Arkham", "url": "https://intel.arkm.com/", "use": "지갑 거래, 입출금, 온체인 이동 검증"},
    {"name": "Lookonchain", "url": "https://lookonchain.com/", "use": "고래 지갑과 스마트머니 이동"},
    {"name": "Spot On Chain", "url": "https://spotonchain.ai/", "use": "지갑 평판, CEX 입출금 흐름 확인"},
    {"name": "Whale Alert", "url": "https://whale-alert.io/", "use": "대형 트랜잭션 알림"},
    {"name": "Nansen", "url": "https://www.nansen.ai/", "use": "Smart Money 흐름"},
    {"name": "DefiLlama", "url": "https://defillama.com/", "use": "TVL, 스테이블코인, CEX 투명성"},
    {"name": "Unusual Whales", "url": "https://unusualwhales.com/", "use": "옵션 플로우와 시장 이상거래"},
    {"name": "Quiver Quantitative", "url": "https://www.quiverquant.com/", "use": "공시, 정치인/내부자 거래 데이터"},
    {"name": "SEC EDGAR", "url": "https://www.sec.gov/search-filings", "use": "Form 4, 13F, 8-K, 10-Q 원천 공시"},
]

BULLISH_WORDS = {
    "surge", "rally", "breakout", "approval", "upgrade", "inflow", "accumulate", "bull",
    "rebound", "record", "상승", "급등", "반등", "호재", "승인", "유입", "업그레이드", "매수",
}
BEARISH_WORDS = {
    "dump", "sell", "lawsuit", "hack", "exploit", "liquidation", "outflow", "bear",
    "crash", "plunge", "하락", "급락", "매도", "소송", "해킹", "청산", "유출", "규제",
}
RISK_WORDS = {
    "lawsuit", "hack", "exploit", "scam", "rug", "fraud", "liquidation", "bankruptcy",
    "규제", "소송", "해킹", "사기", "파산", "청산", "개인정보", "폭로",
}


def clean_text(value: str | None, limit: int = 1000) -> str:
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def html_to_text(value: str, limit: int = 9000) -> str:
    value = re.sub(r"(?is)<(script|style|noscript|svg|canvas|form|nav|footer|header).*?</\1>", " ", value)
    value = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", value)
    value = unescape(re.sub(r"(?is)<[^>]+>", " ", value))
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join([line for line in lines if len(line) >= 24])[:limit]


def safe_filename(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", value).strip("_") or "story_radar"


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def topic_terms(keyword: str) -> list[str]:
    base = normalize_term(keyword)
    terms = [normalize_term(piece) for piece in re.split(r"[,/\n]", keyword) if normalize_term(piece)]
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
        if normalized and normalized != "etc" and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def community_query(keyword: str) -> str:
    return next((term for term in topic_terms(keyword) if re.search(r"[A-Za-z]", term) and "$" not in term and len(term) > 2), keyword)


def query_string(keyword: str) -> str:
    terms = topic_terms(keyword)
    return terms[0] if len(terms) == 1 else " OR ".join([f'"{term}"' if " " in term else term for term in terms[:6]])


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


def request_text(url: str, timeout: int = 9, accept: str = "application/rss+xml, application/json, text/xml, */*") -> str:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def decode_bytes(raw: bytes, content_type: str = "") -> str:
    charset_match = re.search(r"charset=([\w.-]+)", content_type or "", re.IGNORECASE)
    candidates = [charset_match.group(1)] if charset_match else []
    candidates.extend(["utf-8", "cp949", "euc-kr", "latin-1"])
    for encoding in candidates:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def google_news_article_id(url: str) -> str:
    parsed = urlparse(url)
    if "news.google." not in parsed.netloc:
        return ""
    match = re.search(r"/(?:rss/)?articles/([^/?#]+)", parsed.path)
    return match.group(1) if match else ""


@st.cache_data(ttl=86400, show_spinner=False)
def resolve_google_news_url(url: str) -> str:
    article_id = google_news_article_id(url)
    if not article_id:
        return url
    article_url = f"https://news.google.com/rss/articles/{article_id}?oc=5"
    try:
        html = request_text(article_url, timeout=12, accept="text/html,*/*")
        signature = re.search(r'data-n-a-sg="([^"]+)"', html)
        timestamp = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not signature or not timestamp:
            return url

        request_payload = [
            "garturlreq",
            [
                [
                    "en-US",
                    "US",
                    ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"],
                    None,
                    None,
                    1,
                    1,
                    "US:en",
                    None,
                    180,
                    None,
                    None,
                    None,
                    None,
                    None,
                    0,
                    None,
                    None,
                    [1608992183, 723341000],
                ],
                "en-US",
                "US",
                1,
                [2, 3, 4, 8],
                1,
                0,
                "655000234",
                0,
                0,
                None,
                0,
            ],
            article_id,
            int(timestamp.group(1)),
            signature.group(1),
        ]
        rpc = [["Fbv4je", json.dumps(request_payload, separators=(",", ":")), None, "generic"]]
        body = urlencode({"f.req": json.dumps([rpc], separators=(",", ":"))}).encode("utf-8")
        req = Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data=body,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Referer": "https://news.google.com/",
            },
            method="POST",
        )
        with urlopen(req, timeout=12) as response:
            text = response.read().decode("utf-8", errors="replace")
        payload_text = text.split("\n\n", 1)[-1].strip()
        decoded_outer = json.loads(payload_text)
        for entry in decoded_outer:
            if isinstance(entry, list) and len(entry) >= 3 and entry[0] == "wrb.fr" and entry[1] == "Fbv4je" and entry[2]:
                decoded_inner = json.loads(entry[2])
                if isinstance(decoded_inner, list) and len(decoded_inner) > 1 and isinstance(decoded_inner[1], str):
                    return decoded_inner[1]
    except Exception:
        return url
    return url


def resolve_source_url(url: str) -> str:
    if "news.google." in urlparse(url).netloc:
        return resolve_google_news_url(url)
    return url


def strip_html_to_lines(value: str) -> list[str]:
    value = re.sub(r"(?is)<(script|style|noscript|svg|canvas|iframe|form|nav|footer|header|aside).*?</\1>", " ", value)
    value = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</article>|</section>", "\n", value)
    value = unescape(re.sub(r"(?is)<[^>]+>", " ", value))
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return [line for line in lines if line]


def extract_jsonld_body(html: str) -> str:
    def walk(value: object) -> list[str]:
        results: list[str] = []
        if isinstance(value, dict):
            article_body = value.get("articleBody")
            if isinstance(article_body, str):
                results.append(clean_text(article_body, 12000))
            description = value.get("description")
            if isinstance(description, str) and len(description) > 250:
                results.append(clean_text(description, 3000))
            for nested in value.values():
                results.extend(walk(nested))
        elif isinstance(value, list):
            for item in value:
                results.extend(walk(item))
        return results

    bodies: list[str] = []
    for script in re.findall(r"(?is)<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html):
        try:
            parsed = json.loads(unescape(script).strip())
        except json.JSONDecodeError:
            continue
        bodies.extend(walk(parsed))
    return max(bodies, key=len) if bodies else ""


def is_noise_line(line: str) -> bool:
    lower = line.lower()
    if len(line) < 24:
        return True
    if sum(char.isdigit() for char in line) > max(14, len(line) * 0.45):
        return True
    noise = [
        "subscribe",
        "sign in",
        "log in",
        "cookies",
        "privacy policy",
        "terms of use",
        "all rights reserved",
        "advertisement",
        "share this article",
        "관련기사",
        "구독",
        "로그인",
        "회원가입",
        "개인정보",
        "저작권",
        "광고",
    ]
    return any(pattern in lower for pattern in noise) and len(line) < 120


def extract_readable_body(html: str) -> str:
    jsonld_body = extract_jsonld_body(html)
    if len(jsonld_body) >= 500:
        return jsonld_body[:12000]
    lines = strip_html_to_lines(html)
    candidates: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if is_noise_line(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        candidates.append(line)
    if not candidates:
        return ""

    long_lines = [line for line in candidates if len(line) >= 80]
    if len("\n".join(long_lines)) >= 500:
        return "\n".join(long_lines)[:12000]
    return "\n".join(candidates)[:12000]


def has_meaningful_text(text: str) -> bool:
    cleaned = clean_text(text, 12000)
    if len(cleaned) >= 600:
        return True
    lines = [line for line in text.splitlines() if len(clean_text(line, 1000)) >= 70]
    return len(cleaned) >= 260 and len(lines) >= 3


def source_status_for_short_body(url: str, body: str, fallback: str) -> tuple[str, str]:
    fallback_clean = clean_text(fallback, 5000)
    parsed = urlparse(url)
    if has_meaningful_text(fallback_clean):
        return fallback_clean, "rss_excerpt_fallback"
    if "binance.com" in parsed.netloc.lower():
        return "", "non_article_price_page"
    if body:
        return "", "body_too_short"
    return "", "body_unavailable"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_original_text(url: str, fallback: str = "") -> tuple[str, str]:
    resolved_url = resolve_source_url(url)
    if not resolved_url or not resolved_url.startswith("http"):
        return source_status_for_short_body(resolved_url, "", fallback)
    try:
        req = Request(
            resolved_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        with urlopen(req, timeout=8) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            raw = response.read(850_000)
        if "pdf" in content_type or "image/" in content_type or "video/" in content_type:
            return source_status_for_short_body(resolved_url, "", fallback)
        text = extract_readable_body(decode_bytes(raw, content_type))
        if has_meaningful_text(text):
            return text, "html_body"
        return source_status_for_short_body(resolved_url, text, fallback)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        fallback_text, fallback_status = source_status_for_short_body(resolved_url, "", fallback)
        return fallback_text, f"{fallback_status}_{type(exc).__name__}"


def child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if child.tag.split("}")[-1].lower() in names:
            return clean_text("".join(child.itertext()), 1400)
    for child in node.iter():
        if child is not node and child.tag.split("}")[-1].lower() in names:
            return clean_text("".join(child.itertext()), 1400)
    return ""


def child_link(node: ET.Element) -> str:
    for child in list(node):
        if child.tag.split("}")[-1].lower() == "link" and child.attrib.get("href"):
            return child.attrib["href"]
    return child_text(node, {"link", "guid", "id"})


def matches_topic(title: str, summary: str, terms: list[str]) -> bool:
    text = normalize_term(f"{title} {summary}")
    return not terms or any(term in text for term in terms)


def count_words(text: str, words: set[str]) -> int:
    lower = normalize_term(text)
    return sum(1 for word in words if normalize_term(word) in lower)


def mood_of(text: str) -> tuple[str, int, int]:
    bull = count_words(text, BULLISH_WORDS)
    bear = count_words(text, BEARISH_WORDS)
    if bull > bear:
        return "상승/호재", bull, bear
    if bear > bull:
        return "하락/리스크", bull, bear
    return "중립/관망", bull, bear


def freshness_label(age_hours: float) -> str:
    if age_hours >= 999:
        return "발행 미확인"
    if age_hours < 1:
        return f"{max(1, round(age_hours * 60))}분 전"
    if age_hours < 48:
        return f"{round(age_hours)}시간 전"
    return f"{round(age_hours / 24)}일 전"


def source_group_meta(group: str) -> dict[str, str]:
    return SOURCE_GROUP_META.get(group, {"country_group": "unknown", "collection_method": "unknown", "policy_risk_level": "medium"})


def stable_id(origin: str, url: str, title: str) -> str:
    raw = f"{origin}|{url}|{title}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def compute_scores(
    *,
    text: str,
    age_hours: float,
    relevance_hits: int,
    popularity_raw: int,
    comments: int,
    bull_hits: int,
    bear_hits: int,
    weight: float,
    origin: str,
) -> dict[str, float]:
    unknown_age = age_hours >= 999
    freshness_score = 18.0 if unknown_age else max(0.0, min(100.0, 100.0 - age_hours * 3.8))
    comments_per_hour = 0.0 if unknown_age else comments / max(age_hours, 1.0)
    score_per_hour = 0.0 if unknown_age else popularity_raw / max(age_hours, 1.0)
    reaction_score = min(100.0, log1p(max(popularity_raw, 0) + comments * 2.5) * 15.5)
    debate_score = min(100.0, log1p(max(comments, 0) + 1) * 23.0 + min(24.0, (bull_hits + bear_hits) * 5.0))
    velocity_score = min(100.0, freshness_score * 0.45 + log1p(score_per_hour + comments_per_hour * 4.0) * 22.0)
    relevance_score = min(100.0, relevance_hits * 18.0)
    source_boost = 10.0 if origin in {"reddit", "hn"} else 6.0
    risk_hits = count_words(text, RISK_WORDS)
    risk_score = min(100.0, risk_hits * 14.0 + bear_hits * 8.0 + (8.0 if origin == "reddit" else 0.0))
    viral_score = min(100.0, reaction_score * 0.30 + debate_score * 0.18 + freshness_score * 0.22 + relevance_score * 0.18 + weight * 8.0)
    production_score = min(100.0, viral_score * 0.48 + velocity_score * 0.20 + debate_score * 0.16 + (100.0 - risk_score) * 0.10 + source_boost)
    shorts_potential = min(100.0, velocity_score * 0.42 + debate_score * 0.34 + freshness_score * 0.18 + source_boost)
    length_score = min(100.0, len(clean_text(text, 6000)) / 18.0)
    longform_potential = min(100.0, production_score * 0.42 + debate_score * 0.28 + length_score * 0.22 + relevance_score * 0.08)
    legacy_signal = int(max(1, min(99, round(production_score))))
    return {
        "score": legacy_signal,
        "viral_score": round(viral_score, 1),
        "velocity_score": round(velocity_score, 1),
        "debate_score": round(debate_score, 1),
        "risk_score": round(risk_score, 1),
        "production_score": round(production_score, 1),
        "shorts_potential": round(shorts_potential, 1),
        "longform_potential": round(longform_potential, 1),
        "freshness_score": round(freshness_score, 1),
        "reaction_score": round(reaction_score, 1),
        "comments_per_hour": round(comments_per_hour, 2),
        "score_per_hour": round(score_per_hour, 2),
    }


def is_low_value_news_item(title: str, summary: str, url: str) -> bool:
    parsed = urlparse(url)
    title_clean = clean_text(title, 240)
    summary_clean = clean_text(summary, 600)
    domain = parsed.netloc.lower()
    if "binance.com" in domain and re.search(r"\b(price today|live price|/usdt|/usd|chart)\b", title_clean, re.IGNORECASE):
        return True
    if re.match(r"^[A-Z0-9]{2,12}/[A-Z0-9]{2,12}\s+-\s+Binance$", title_clean):
        return True
    if "news.google." in domain and "Binance" in summary_clean and len(summary_clean) < 140:
        return True
    return False


def make_item(
    source: str,
    group: str,
    source_type: str,
    title: str,
    summary: str,
    url: str,
    keyword: str,
    published: str = "",
    age_hours: float = 9999.0,
    weight: float = 1.0,
    popularity_raw: int = 0,
    comments: int = 0,
    origin: str = "rss",
) -> dict:
    title = clean_text(title, 180) or "Untitled"
    summary = clean_text(summary, 900)
    combined = f"{title} {summary}"
    relevance_hits = sum(1 for term in topic_terms(keyword) if term in normalize_term(combined))
    mood, bull_hits, bear_hits = mood_of(combined)
    signal = (
        f"upvote {popularity_raw} / comment {comments}"
        if origin == "reddit"
        else f"point {popularity_raw} / comment {comments}"
        if origin == "hn"
        else freshness_label(age_hours)
    )
    scores = compute_scores(
        text=combined,
        age_hours=age_hours,
        relevance_hits=relevance_hits,
        popularity_raw=popularity_raw,
        comments=comments,
        bull_hits=bull_hits,
        bear_hits=bear_hits,
        weight=weight,
        origin=origin,
    )
    feed_text = summary if has_meaningful_text(summary) else ""
    content_status = "feed_summary" if feed_text else "metadata_only"
    meta = source_group_meta(group)
    return {
        "id": stable_id(origin, url, title),
        "source": source,
        "group": group,
        "source_group": SOURCE_GROUPS.get(group, group),
        "source_type": source_type,
        "country_group": meta["country_group"],
        "collection_method": meta["collection_method"],
        "policy_risk_level": meta["policy_risk_level"],
        "title": title,
        "summary": summary,
        "original_text": clean_text(feed_text, 5000),
        "content_status": content_status,
        "url": url,
        "published": published,
        "age_hours": age_hours,
        "freshness": freshness_label(age_hours),
        "mood": mood,
        "popularity_raw": popularity_raw,
        "comments": comments,
        "signal": signal,
        "origin": origin,
        "relevance_hits": relevance_hits,
        "bull_hits": bull_hits,
        "bear_hits": bear_hits,
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **scores,
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
    items = []
    for node in nodes[: limit * 4]:
        title = child_text(node, {"title"})
        summary = child_text(node, {"description", "summary", "content", "encoded"})
        if source["mode"] == "feed" and source.get("match", "topic") != "latest" and not matches_topic(title, summary, terms):
            continue
        published, age_hours = parse_date(child_text(node, {"pubdate", "published", "updated", "date"}))
        raw_link = child_link(node)
        source_url = resolve_source_url(raw_link)
        if is_low_value_news_item(title, summary, source_url):
            continue
        item = make_item(
            source["name"],
            source["group"],
            source.get("source_type", "RSS"),
            title,
            summary,
            source_url,
            keyword,
            published,
            age_hours,
            float(source["weight"]),
            origin=source.get("origin", "rss"),
        )
        if raw_link != source_url:
            item["rss_url"] = raw_link
            item["url_resolution"] = "google_news_resolved"
        items.append(
            item
        )
        if len(items) >= limit:
            break
    return items, f"{source['name']}: {len(items)}개"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_reddit_source(source: dict, keyword: str, limit: int) -> tuple[list[dict], str]:
    url = f"https://www.reddit.com/r/{source['sub']}/search.json?{urlencode({'q': community_query(keyword), 'restrict_sr': '1', 'sort': 'hot', 't': 'week', 'limit': limit})}"
    try:
        data = json.loads(request_text(url, timeout=8, accept="application/json,*/*"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return [], f"{source['name']}: 실패 ({type(exc).__name__})"
    items = []
    for post in [child.get("data", {}) for child in data.get("data", {}).get("children", [])]:
        if post.get("stickied") or not post.get("title"):
            continue
        created = datetime.fromtimestamp(float(post.get("created_utc", 0) or 0), tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        items.append(
            make_item(
                source["name"],
                "community",
                "Community API",
                post.get("title", ""),
                post.get("selftext") or post.get("url_overridden_by_dest") or "",
                f"https://www.reddit.com{post.get('permalink', '')}",
                keyword,
                created.strftime("%Y-%m-%d %H:%M UTC"),
                age_hours,
                float(source["weight"]),
                int(post.get("ups") or post.get("score") or 0),
                int(post.get("num_comments") or 0),
                "reddit",
            )
        )
    return items, f"{source['name']}: {len(items)}개"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_hacker_news(keyword: str, limit: int) -> tuple[list[dict], str]:
    url = f"https://hn.algolia.com/api/v1/search?{urlencode({'query': community_query(keyword), 'tags': 'story', 'hitsPerPage': limit})}"
    try:
        data = json.loads(request_text(url, timeout=8, accept="application/json,*/*"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return [], f"Hacker News: 실패 ({type(exc).__name__})"
    items = []
    for hit in data.get("hits", []):
        created, age_hours = parse_date(hit.get("created_at"))
        items.append(
            make_item(
                "Hacker News",
                "community",
                "Community API",
                hit.get("title") or hit.get("story_title") or "",
                hit.get("comment_text") or "",
                hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                keyword,
                created,
                age_hours,
                0.95,
                int(hit.get("points") or 0),
                int(hit.get("num_comments") or 0),
                "hn",
            )
        )
    return items, f"Hacker News: {len(items)}개"


def dedupe_items(items: list[dict]) -> list[dict]:
    seen, deduped = set(), []
    for item in sorted(items, key=lambda value: value["production_score"], reverse=True):
        key = normalize_term(item["url"] or item["title"])
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def run_collection(keyword: str, active_groups: list[str], per_source: int) -> tuple[list[dict], list[str]]:
    all_items, status = [], []
    for source in RSS_SOURCES:
        if source["group"] in active_groups:
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


def item_status(item_id: str) -> str:
    return st.session_state.setdefault("item_statuses", {}).get(item_id, "collected")


def set_item_status(item_id: str, status: str) -> None:
    st.session_state.setdefault("item_statuses", {})[item_id] = status


def update_item(item_id: str, **fields: object) -> None:
    updated = []
    for item in st.session_state.get("items", []):
        if item["id"] == item_id:
            item = {**item, **fields}
        updated.append(item)
    st.session_state["items"] = updated


def status_badge(status: str) -> str:
    css = "pill-green" if status == "approved" else "pill-amber" if status in {"candidate", "needs_review"} else "pill-red" if status == "rejected" else ""
    return f'<span class="pill {css}">{escape(STATUS_LABELS.get(status, status))}</span>'


def export_rows(items: list[dict], keyword: str) -> list[dict]:
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            {
                "rank": index,
                "status": STATUS_LABELS.get(item_status(item["id"]), item_status(item["id"])),
                "query": keyword,
                "captured_at": item.get("captured_at", ""),
                "source_group": item.get("source_group", SOURCE_GROUPS.get(item.get("group", ""), item.get("group", ""))),
                "country_group": item.get("country_group", ""),
                "collection_method": item.get("collection_method", ""),
                "policy_risk_level": item.get("policy_risk_level", ""),
                "source": item.get("source", ""),
                "source_type": item.get("source_type", ""),
                "origin": item.get("origin", ""),
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "original_text": item.get("original_text", ""),
                "content_status": item.get("content_status", "feed_summary"),
                "url": item.get("url", ""),
                "rss_url": item.get("rss_url", ""),
                "url_resolution": item.get("url_resolution", ""),
                "published": item.get("published", ""),
                "freshness": item.get("freshness", ""),
                "age_hours": round(float(item.get("age_hours") or 9999), 2),
                "production_score": item.get("production_score", 0),
                "viral_score": item.get("viral_score", 0),
                "velocity_score": item.get("velocity_score", 0),
                "debate_score": item.get("debate_score", 0),
                "risk_score": item.get("risk_score", 0),
                "shorts_potential": item.get("shorts_potential", 0),
                "longform_potential": item.get("longform_potential", 0),
                "mood": item.get("mood", ""),
                "signal": item.get("signal", ""),
                "popularity_raw": item.get("popularity_raw", 0),
                "comments": item.get("comments", 0),
                "comments_per_hour": item.get("comments_per_hour", 0),
                "score_per_hour": item.get("score_per_hour", 0),
            }
        )
    return rows


def csv_payload(items: list[dict], keyword: str) -> bytes:
    return pd.DataFrame(export_rows(items, keyword)).to_csv(index=False).encode("utf-8-sig")


def table_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        rows.append(
            {
                "상태": STATUS_LABELS.get(item_status(item["id"]), item_status(item["id"])),
                "Production": item["production_score"],
                "Viral": item["viral_score"],
                "Velocity": item["velocity_score"],
                "Debate": item["debate_score"],
                "Risk": item["risk_score"],
                "Fresh": item["freshness"],
                "Source": item["source"],
                "Group": item["source_group"],
                "Mood": item["mood"],
                "Signal": item["signal"],
                "Title": item["title"],
                "URL": item["url"],
            }
        )
    return rows


def score_card(label: str, value: float, help_text: str) -> None:
    st.markdown(
        f'<div class="metric-card"><span>{escape(label)}</span><strong>{escape(str(value))}</strong><small>{escape(help_text)}</small></div>',
        unsafe_allow_html=True,
    )


def item_card(item: dict) -> None:
    status = item_status(item["id"])
    with st.container(border=True):
        st.markdown(f'<div class="item-title">{escape(item["title"])}</div>', unsafe_allow_html=True)
        st.markdown(
            f'{status_badge(status)}<span class="pill pill-red">{escape(str(item["production_score"]))} production</span>'
            f'<span class="pill">{escape(item["source_group"])}</span><span class="pill">{escape(item["source"])}</span>'
            f'<span class="pill">{escape(item["mood"])}</span>',
            unsafe_allow_html=True,
        )
        if item["summary"]:
            st.write(item["summary"])
        st.markdown(
            f'<div class="source-meta">{escape(item["source_type"])} · {escape(item["freshness"])} · '
            f'<a href="{escape(item["url"])}" target="_blank">원문 열기</a></div>',
            unsafe_allow_html=True,
        )


def render_detail(item: dict) -> None:
    st.markdown("### 선택 소재 상세")
    st.markdown(f"#### {item['title']}")
    st.markdown(
        f'{status_badge(item_status(item["id"]))}<span class="pill">{escape(item["source_group"])}</span>'
        f'<span class="pill">{escape(item["source"])}</span><span class="pill">{escape(item["freshness"])}</span>'
        f'<span class="pill">{escape(item["policy_risk_level"])} policy risk</span>',
        unsafe_allow_html=True,
    )
    if item.get("url"):
        st.link_button("원문 열기", item["url"], width="stretch")

    current_status = item_status(item["id"])
    selected_status = st.selectbox(
        "제작 상태",
        STATUS_OPTIONS,
        index=STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0,
        format_func=lambda value: STATUS_LABELS.get(value, value),
        key=f"status_select_{item['id']}_{current_status}",
    )
    if selected_status != current_status:
        set_item_status(item["id"], selected_status)
        st.rerun()

    quick_cols = st.columns(4)
    quick_actions = [("후보 지정", "candidate"), ("제작 승인", "approved"), ("리스크 검토", "needs_review"), ("제외", "rejected")]
    for col, (label, status) in zip(quick_cols, quick_actions):
        if col.button(label, key=f"{status}_{item['id']}", width="stretch"):
            set_item_status(item["id"], status)
            st.rerun()

    metric_cols = st.columns(5)
    for col, (label, key) in zip(
        metric_cols,
        [
            ("Production", "production_score"),
            ("Viral", "viral_score"),
            ("Velocity", "velocity_score"),
            ("Debate", "debate_score"),
            ("Risk", "risk_score"),
        ],
    ):
        col.metric(label, item.get(key, 0))

    st.markdown("#### 점수 해석")
    score_df = pd.DataFrame(
        [
            {"metric": "freshness", "score": item["freshness_score"], "meaning": "게시 시점이 얼마나 최근인지"},
            {"metric": "reaction", "score": item["reaction_score"], "meaning": "업보트/댓글 기반 외부 반응"},
            {"metric": "velocity", "score": item["velocity_score"], "meaning": "시간 대비 반응 속도"},
            {"metric": "debate", "score": item["debate_score"], "meaning": "댓글과 찬반 키워드 기반 논쟁성"},
            {"metric": "risk", "score": item["risk_score"], "meaning": "소송/해킹/사기 등 위험 키워드"},
            {"metric": "shorts", "score": item["shorts_potential"], "meaning": "짧은 영상 후보성"},
            {"metric": "longform", "score": item["longform_potential"], "meaning": "긴 호흡 해설 후보성"},
        ]
    )
    st.dataframe(score_df, width="stretch", hide_index=True)

    st.markdown("#### 원자료")
    st.write(item.get("summary") or "요약이 비어 있습니다.")
    with st.expander("원문/요약 텍스트 미리보기", expanded=False):
        text = item.get("original_text") or item.get("summary") or ""
        status = item.get("content_status", "")
        if item.get("original_text"):
            preview = item["original_text"][:5000]
        elif has_meaningful_text(item.get("summary", "")):
            preview = item.get("summary", "")[:5000]
        else:
            preview = f"본문 미확보 상태입니다. status={status}. 원문 열기로 직접 확인하거나 본문 보강을 다시 시도하세요."
        st.markdown(f'<div class="source-text">{escape(preview)}</div>', unsafe_allow_html=True)
    if st.button("이 소재만 원문 본문 보강", key=f"enrich_{item['id']}", width="stretch"):
        with st.spinner("원문 본문을 가져오는 중입니다."):
            text, status = fetch_original_text(item.get("url", ""), item.get("summary", ""))
            update_item(item["id"], original_text=text, content_status=status)
        st.success("본문 보강을 시도했습니다.")
        st.rerun()


def render_leaderboard(items: list[dict], title: str, sort_key: str, ascending: bool = False) -> None:
    st.markdown(f"#### {title}")
    if not items:
        st.info("수집된 후보가 없습니다.")
        return
    ranked = sorted(items, key=lambda value: value.get(sort_key, 0), reverse=not ascending)[:50]
    df = pd.DataFrame(table_rows(ranked))
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_order=["상태", "Production", "Viral", "Velocity", "Debate", "Risk", "Fresh", "Source", "Title", "URL"],
    )


for key, default in {"items": [], "status": [], "last_query": "", "item_statuses": {}, "last_collected_at": ""}.items():
    st.session_state.setdefault(key, default)


st.sidebar.markdown('<p class="eyebrow">Story Pattern Lab</p>', unsafe_allow_html=True)
st.sidebar.title("Story Radar")
st.sidebar.write("검색 주제에 맞는 원자료를 모으고, 제작 후보를 점수와 상태로 관리합니다.")
st.sidebar.caption("LLM 제작실은 비활성화되어 있습니다. 현재 단계는 수집, 점수화, 후보 선별에 집중합니다.")
st.sidebar.divider()
keyword = st.sidebar.text_input("검색 주제", value=st.session_state.get("last_query") or "이더리움클래식", placeholder="이더리움클래식, BTC, NVDA")
active_groups = [key for key, label in SOURCE_GROUPS.items() if key != "market_intel" and st.sidebar.checkbox(label, value=key in DEFAULT_GROUPS)]
include_refs = st.sidebar.checkbox(SOURCE_GROUPS["market_intel"], value=True)
per_source = st.sidebar.slider("소스별 최대 수집", 3, 12, 6)
if st.sidebar.button("수집하고 점수화", type="primary", width="stretch"):
    with st.spinner("RSS와 커뮤니티 반응을 수집하고 점수화하는 중입니다."):
        collected_items, status = run_collection(keyword, active_groups, per_source)
        st.session_state["items"] = collected_items
        st.session_state["status"] = status
        st.session_state["last_query"] = keyword
        st.session_state["last_collected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        for item in collected_items:
            st.session_state["item_statuses"].setdefault(item["id"], "collected")
if st.sidebar.button("결과 초기화", width="stretch"):
    st.session_state["items"], st.session_state["status"], st.session_state["last_query"] = [], [], ""
    st.session_state["item_statuses"], st.session_state["last_collected_at"] = {}, ""
    st.rerun()

items = st.session_state["items"]
query_label = st.session_state.get("last_query") or keyword
approved_count = len([item for item in items if item_status(item["id"]) == "approved"])
candidate_count = len([item for item in items if item_status(item["id"]) in {"candidate", "approved"}])
recent_count = len([item for item in items if item["age_hours"] <= 24])
body_count = len([item for item in items if item.get("content_status") == "html_body"])
avg_production = round(sum(item["production_score"] for item in items) / len(items), 1) if items else 0

st.markdown('<p class="eyebrow">Discovery to Decision</p>', unsafe_allow_html=True)
st.title("Story Pattern Lab Radar")
st.markdown(
    '<p class="hero-line">뉴스, 크립토 미디어, 커뮤니티 반응, 거시경제/트레이딩 채널을 한 화면에서 수집하고 '
    'Production, Viral, Velocity, Debate, Risk 점수로 오늘 볼 소재를 고릅니다.</p>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<span class="pill pill-red">검색어: {escape(query_label)}</span>'
    f'<span class="pill">확장어: {escape(", ".join(topic_terms(query_label)[:6]))}</span>'
    f'<span class="pill">최근 수집: {escape(st.session_state.get("last_collected_at") or "아직 없음")}</span>',
    unsafe_allow_html=True,
)

metric_cols = st.columns(5)
for col, (label, value, help_text) in zip(
    metric_cols,
    [
        ("수집 후보", len(items), "중복 제거 후 후보 수"),
        ("평균 Production", avg_production, "제작 후보 종합 점수"),
        ("후보/승인", candidate_count, "candidate 또는 approved"),
        ("최근 24시간", recent_count, "발행 시점 기준"),
        ("본문 보강", body_count, "HTML 원문 추출 완료"),
    ],
):
    with col:
        score_card(label, value, help_text)

st.divider()

radar_tab, leaderboard_tab, matrix_tab, export_tab, library_tab = st.tabs(["Story Radar", "Leaderboards", "Source Matrix", "Data Export", "Source Library"])

with radar_tab:
    st.subheader("후보 선별 보드")
    if not items:
        st.info("왼쪽에서 검색 주제를 입력하고 수집을 실행하면 후보 보드가 열립니다.")
    else:
        filter_cols = st.columns([1, 1, 1, 1])
        group_options = sorted({item["source_group"] for item in items})
        status_options = [status for status in STATUS_OPTIONS if any(item_status(item["id"]) == status for item in items)]
        selected_groups = filter_cols[0].multiselect("소스 그룹", group_options, default=group_options)
        selected_status = filter_cols[1].multiselect("상태", status_options, default=status_options, format_func=lambda value: STATUS_LABELS.get(value, value))
        min_score = filter_cols[2].slider("최소 Production", 0, 100, 0)
        sort_key = filter_cols[3].selectbox("정렬", ["production_score", "viral_score", "velocity_score", "debate_score", "risk_score", "freshness_score"], format_func=lambda value: value.replace("_", " ").title())
        filtered = [
            item
            for item in items
            if item["source_group"] in selected_groups
            and item_status(item["id"]) in selected_status
            and item["production_score"] >= min_score
        ]
        filtered = sorted(filtered, key=lambda item: item.get(sort_key, 0), reverse=sort_key != "risk_score")

        left, right = st.columns([1.35, 0.95])
        selected_item = filtered[0] if filtered else None
        with left:
            if not filtered:
                st.warning("필터 조건에 맞는 후보가 없습니다.")
            else:
                table = pd.DataFrame(table_rows(filtered))
                event = st.dataframe(
                    table,
                    width="stretch",
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    column_order=["상태", "Production", "Viral", "Velocity", "Debate", "Risk", "Fresh", "Source", "Group", "Title", "URL"],
                )
                selection = getattr(getattr(event, "selection", None), "rows", [])
                if selection:
                    selected_item = filtered[selection[0]]
        with right:
            if selected_item:
                render_detail(selected_item)

with leaderboard_tab:
    lb_tabs = st.tabs(["Production", "Viral", "Velocity", "Debate", "Shorts", "Longform", "Low Risk", "Recent"])
    with lb_tabs[0]:
        render_leaderboard(items, "Production Score TOP 50", "production_score")
    with lb_tabs[1]:
        render_leaderboard(items, "Viral Score TOP 50", "viral_score")
    with lb_tabs[2]:
        render_leaderboard(items, "Velocity Score TOP 50", "velocity_score")
    with lb_tabs[3]:
        render_leaderboard(items, "Debate Density TOP 50", "debate_score")
    with lb_tabs[4]:
        render_leaderboard(items, "Shorts Potential TOP 50", "shorts_potential")
    with lb_tabs[5]:
        render_leaderboard(items, "Longform Potential TOP 50", "longform_potential")
    with lb_tabs[6]:
        low_risk = sorted(items, key=lambda item: (item["risk_score"], -item["viral_score"]))
        render_leaderboard(low_risk, "Low Risk + High Viral TOP 50", "risk_score", ascending=True)
    with lb_tabs[7]:
        recent = sorted(items, key=lambda item: item["age_hours"])
        render_leaderboard(recent, "최신 수집/발행 TOP 50", "age_hours", ascending=True)

with matrix_tab:
    st.subheader("소스 매트릭스")
    if not items:
        st.info("수집을 실행하면 소스별 커버리지와 점수 분포가 표시됩니다.")
    else:
        df = pd.DataFrame(items)
        st.bar_chart(df.groupby(["source_group", "mood"]).size().reset_index(name="count"), x="source_group", y="count", color="mood")
        source_summary = (
            df.groupby(["source_group", "source", "source_type", "policy_risk_level"])
            .agg(
                count=("title", "count"),
                avg_production=("production_score", "mean"),
                avg_viral=("viral_score", "mean"),
                comments=("comments", "sum"),
                body_ready=("content_status", lambda values: int((values == "html_body").sum())),
            )
            .reset_index()
            .sort_values(["source_group", "count", "avg_production"], ascending=[True, False, False])
        )
        for col in ["avg_production", "avg_viral"]:
            source_summary[col] = source_summary[col].round(1)
        st.dataframe(source_summary, width="stretch", hide_index=True)

with export_tab:
    st.subheader("데이터 내보내기")
    if not items:
        st.info("수집된 후보가 없습니다.")
    else:
        export_cols = st.columns(3)
        with export_cols[0]:
            score_card("CSV 행", len(items), "상태와 점수 포함")
        with export_cols[1]:
            score_card("본문 보강", body_count, "HTML 원문 추출 완료")
        with export_cols[2]:
            score_card("최근 24시간", recent_count, "발행 시점 기준")
        st.download_button(
            "CSV 다운로드",
            data=csv_payload(items, query_label),
            file_name=f"story_radar_{safe_filename(query_label)}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            type="primary",
            width="stretch",
            key="download-story-radar-csv",
        )
        enrich_count = 1 if len(items) == 1 else st.slider("본문을 추가로 가져올 상위 후보 수", 1, len(items), min(len(items), 20))
        if st.button("상위 후보 원문 본문 보강", width="stretch"):
            updated_items = [dict(item) for item in items]
            progress = st.progress(0)
            for index, item in enumerate(updated_items[:enrich_count], start=1):
                item["original_text"], item["content_status"] = fetch_original_text(item.get("url", ""), item.get("summary", ""))
                progress.progress(index / enrich_count)
            st.session_state["items"] = updated_items
            st.success(f"{enrich_count}개 후보의 원문 본문 보강을 시도했습니다.")
            st.rerun()
        with st.expander("수집 로그"):
            for msg in st.session_state["status"]:
                st.caption(msg)
        preview = pd.DataFrame(export_rows(items, query_label))
        st.dataframe(
            preview[
                [
                    "rank",
                    "status",
                    "production_score",
                    "viral_score",
                    "velocity_score",
                    "debate_score",
                    "risk_score",
                    "source_group",
                    "source",
                    "content_status",
                    "published",
                    "title",
                    "url",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

with library_tab:
    st.subheader("소스 라이브러리")
    st.write("자동 수집 가능한 RSS/API 소스와 수동 검증용 레퍼런스를 분리해서 관리합니다.")
    st.markdown("#### 자동 수집 RSS / 채널")
    for group_key in ["news_rss", "crypto_media", "macro_channels", "trading_channels"]:
        group_sources = [source for source in RSS_SOURCES if source["group"] == group_key]
        if group_sources:
            st.markdown(f"##### {SOURCE_GROUPS[group_key]}")
            for source in group_sources:
                with st.container(border=True):
                    feed_url = source.get("url") or source.get("url_template", "").format(query=quote(query_string(query_label)))
                    st.markdown(f"**{source['name']}**")
                    st.caption(f"{source.get('source_type', 'RSS')} · {SOURCE_GROUP_META[group_key]['collection_method']} · policy {SOURCE_GROUP_META[group_key]['policy_risk_level']}")
                    st.markdown(f"[피드 열기]({feed_url})")
    st.markdown("#### 커뮤니티 수집")
    for source in REDDIT_SOURCES:
        with st.container(border=True):
            st.markdown(f"**{source['name']}**")
            st.caption("Reddit hot/week search · public JSON")
    st.markdown("#### 수동 검증 레퍼런스")
    if include_refs:
        for source in REFERENCE_SOURCES:
            with st.container(border=True):
                st.markdown(f"**{source['name']}**")
                st.caption(SOURCE_GROUPS["market_intel"])
                st.write(source["use"])
                st.markdown(f"[사이트 열기]({source['url']})")
    else:
        st.info("왼쪽 사이드바에서 온체인/마켓 레퍼런스를 켜면 표시됩니다.")
