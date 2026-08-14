from __future__ import annotations

import json
import os
import re
import hashlib
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


st.set_page_config(page_title="Japan Crypto Pattern Lab", page_icon="₿", layout="wide")

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

USER_AGENT = "Mozilla/5.0 StoryPatternLab/0.7; japan-crypto-radar-public-list-only"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
STREAMLIT_PATCH_VERSION = "2026-08-13 japan-crypto-radar-v1"
TOKEN_PARAMETER_POLICY = "max_completion_tokens only"
DEPLOYMENT_ENTRYPOINT = "streamlit_app.py -> apps/streamlit/app.py"

CRYPTO_RSS_SOURCES = {
    "CoinPost JP": {"url": "https://coinpost.jp/?feed=rss2", "category": "일본 암호자산 뉴스", "status": "Active RSS", "region": "일본 미디어"},
    "NADA NEWS / CoinDesk Japan": {"url": "https://www.coindeskjapan.com/feed/", "category": "일본 Web3·디지털자산 뉴스", "status": "Active RSS", "region": "일본 미디어"},
    "CRYPTO TIMES JP": {"url": "https://crypto-times.jp/feed/", "category": "일본 블록체인·Web3 뉴스", "status": "Active RSS", "region": "일본 미디어"},
    "CryptoNews JP": {"url": "https://cryptonews.com/jp/feed/", "category": "일본어 크립토 글로벌 뉴스", "status": "Active RSS", "region": "일본어 미디어"},
    "Coinspeaker JP": {"url": "https://www.coinspeaker.com/jp/feed/", "category": "일본어 크립토·금융 뉴스", "status": "Active RSS", "region": "일본어 미디어"},
    "99Bitcoins JP": {"url": "https://99bitcoins.com/jp/feed/", "category": "일본어 BTC·알트코인 뉴스", "status": "Active RSS", "region": "일본어 미디어"},
    "CryptoDnes JP": {"url": "https://cryptodnes.bg/jp/feed/", "category": "일본어 글로벌 크립토 뉴스", "status": "Active RSS", "region": "일본어 미디어"},
    "CoinDesk Global": {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "category": "글로벌 크립토 뉴스", "status": "Active RSS", "region": "글로벌 미디어"},
}

CRYPTO_PUBLIC_LIST_SOURCES = {
    "5ch 仮想通貨板": {
        "url": "https://fate.5ch.io/cryptocoin/subject.txt",
        "thread_base_url": "https://fate.5ch.io/test/read.cgi/cryptocoin/",
        "category": "일본 커뮤니티 스레드",
        "status": "공개 subject.txt",
        "region": "일본 커뮤니티",
        "parser": "5ch_subject",
        "note": "스레드 제목과 댓글 수만 수집합니다. 본문/댓글 원문 대량 저장은 하지 않습니다.",
    },
    "CoinMarketCap Headlines": {
        "url": "https://coinmarketcap.com/headlines/news/",
        "category": "글로벌 코인 헤드라인",
        "status": "공개 헤드라인",
        "region": "글로벌 미디어",
        "parser": "coinmarketcap_headlines",
        "note": "CoinMarketCap 커뮤니티 기사 링크와 제목 중심 수집",
    },
    "Yahoo Finance JP Crypto": {
        "url": "https://finance.yahoo.co.jp/news/search?q=%E4%BB%AE%E6%83%B3%E9%80%9A%E8%B2%A8",
        "category": "일본 금융 포털 크립토 뉴스",
        "status": "공개 검색목록",
        "region": "일본 미디어",
        "parser": "yahoo_finance_jp_news",
        "note": "Yahoo!ファイナンス 검색 결과에서 암호자산 관련 기사 제목과 링크만 수집",
    },
}

SOURCE_NOTES = [
    {"site": "CoinPost JP", "category": "일본 대표 암호자산 미디어", "status": "기본 수집", "note": "RSS 정상 응답. 일본 시장 반응과 주요 공시·ETF·거래소 이슈 감지용"},
    {"site": "NADA NEWS / CoinDesk Japan", "category": "디지털자산·Web3", "status": "기본 수집", "note": "CoinDesk Japan 계열 RSS가 NADA NEWS로 리다이렉트되어 정상 응답"},
    {"site": "CRYPTO TIMES JP", "category": "일본 Web3·프로젝트 뉴스", "status": "기본 수집", "note": "프로젝트·규제·거래소 이슈 감지용"},
    {"site": "5ch 仮想通貨板", "category": "일본 커뮤니티", "status": "옵션 수집", "note": "제목/댓글 수 기반으로 커뮤니티 화제성만 확인"},
    {"site": "CoinMarketCap Headlines", "category": "글로벌 헤드라인", "status": "옵션 수집", "note": "글로벌 기사 흐름 보정용. 영문 제목이 섞일 수 있음"},
    {"site": "Cointelegraph JP", "category": "일본어 글로벌 뉴스", "status": "보류", "note": "확인 시점 RSS가 410 Gone으로 응답해 기본 수집에서 제외"},
]

REWRITE_PRINCIPLES = [
    "원문 문장 구조를 그대로 복제하지 않는다.",
    "5ch 등 커뮤니티 댓글 원문과 사용자 식별 정보를 대량 저장하지 않는다.",
    "계정명, 지갑 주소, 개인명 등 식별 가능한 정보는 필요한 경우 일반화한다.",
    "매수/매도/가격 전망을 단정하지 않고 출처, 시간, 공식 발표 여부를 분리한다.",
    "대본은 크립토 라이브 해설형 1인칭 진행자 말투를 기준으로 한다.",
    "존댓말 진행, 반말 리액션, 커뮤니티 반응 받아치기, 리스크 체크가 모두 들어가야 한다.",
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


def llm_pipeline_source() -> str:
    if analyze_story is None:
        return "llm_pipeline 로드 실패"
    try:
        return os.path.abspath(str(analyze_story.__globals__.get("__file__", "")))
    except Exception:
        return "경로 확인 실패"


def app_source() -> str:
    return os.path.abspath(__file__)


def clear_llm_outputs() -> None:
    for state_key in [
        "story_analyses",
        "live_blueprints",
        "longform_scripts",
        "quality_checks",
        "derivative_assets",
        "production_packages",
    ]:
        st.session_state[state_key] = {}
    st.session_state.pop("last_addition", None)


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
    candidates.extend(["utf-8", "shift_jis", "cp932", "cp949", "euc-kr"])
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
    text = title
    if any(word in lower for word in ["bitcoin", "btc", "metaplanet"]) or any(word in text for word in ["ビットコイン", "BTC", "メタプラネット"]):
        return "BTC / Bitcoin"
    if any(word in lower for word in ["ethereum", "eth", "solana", "xrp", "ripple", "altcoin", "doge"]) or any(word in text for word in ["イーサリアム", "ソラナ", "リップル", "アルト", "ドージ", "柴犬"]):
        return "Altcoin / L1-L2"
    if any(word in lower for word in ["sec", "cftc", "regulation", "law", "tax", "etf"]) or any(word in text for word in ["規制", "金融庁", "税", "法", "ETF", "承認", "当局"]):
        return "Regulation / ETF"
    if any(word in lower for word in ["exchange", "binance", "coinbase", "bitget", "sbi"]) or any(word in text for word in ["取引所", "バイナンス", "コインベース", "ビットゲット", "SBI"]):
        return "Exchange / Infrastructure"
    if any(word in lower for word in ["hack", "scam", "phishing", "exploit", "attack"]) or any(word in text for word in ["不正", "ハッキング", "詐欺", "攻撃", "流出", "フィッシング"]):
        return "Security / Risk"
    if any(word in lower for word in ["fed", "inflation", "cpi", "rate", "treasury"]) or any(word in text for word in ["米国", "FRB", "CPI", "金利", "インフレ", "国債"]):
        return "Macro / Market"
    if any(word in lower for word in ["defi", "nft", "web3", "dao", "rwa", "stablecoin"]) or any(word in text for word in ["DeFi", "NFT", "Web3", "DAO", "RWA", "ステーブルコイン"]):
        return "Web3 / DeFi"
    return "Crypto General"


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
    risk_score = 45 if "커뮤니티" in item.region else 25
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
        content_values = []
        for content_item in getattr(entry, "content", []) or []:
            value = getattr(content_item, "value", "")
            if value:
                content_values.append(value)
        summary_source = max([getattr(entry, "summary", ""), *content_values], key=lambda value: len(str(value)), default="")
        summary = clean_html(summary_source)
        items.append(StoryItem(source=source_name, region=source_meta["region"], category=source_meta["category"], title=title, url=url, original_excerpt=summary, posted_at=parse_datetime(published), collected_at=collected_at, rank_position=index))
    return items


CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "xrp", "ripple", "solana", "sol", "crypto", "token",
    "stablecoin", "defi", "nft", "web3", "sec", "cftc", "etf", "binance", "coinbase",
    "ビットコイン", "仮想通貨", "暗号資産", "イーサリアム", "リップル", "ソラナ", "トークン",
    "ステーブルコイン", "取引所", "金融庁", "規制", "ETF", "ブロックチェーン",
]


def is_crypto_public_link(parser_type: str, href: str, text: str) -> bool:
    if len(text) < 8:
        return False
    bad_words = ["로그인", "회원가입", "검색", "이전", "다음", "공지", "광고", "이벤트", "고객센터", "ログイン", "会員登録", "広告", "検索", "ヘルプ"]
    if any(word in text for word in bad_words):
        return False
    lower_text = text.lower()
    lower_href = href.lower()
    if parser_type == "coinmarketcap_headlines":
        if "coinmarketcap.com/community/" not in lower_href:
            return False
        return any(keyword.lower() in lower_text for keyword in CRYPTO_KEYWORDS)
    if parser_type == "yahoo_finance_jp_news":
        if "finance.yahoo.co.jp/news/detail/" not in lower_href:
            return False
        return any(keyword.lower() in lower_text for keyword in CRYPTO_KEYWORDS)
    return False


def parse_5ch_subject_title(raw_title: str) -> tuple[str, int]:
    match = re.search(r"\s*\((\d+)\)\s*$", raw_title)
    if not match:
        return raw_title.strip(), 0
    title = raw_title[: match.start()].strip()
    return title, int(match.group(1))


def collect_5ch_subject_list(source_name: str, source_meta: dict[str, str], limit: int) -> tuple[list[StoryItem], str]:
    collected_at = datetime.now(timezone.utc)
    request = Request(source_meta["url"], headers={"User-Agent": USER_AGENT, "Accept-Language": "ja-JP,ja;q=0.9,ko;q=0.7,en;q=0.6"})
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read()
            text = decode_html(raw, response.headers.get("Content-Type", ""))
    except Exception as error:
        return [], f"{source_name} 수집 실패: {error}"
    items: list[StoryItem] = []
    for line in text.splitlines():
        if "<>" not in line or ".dat" not in line:
            continue
        thread_part, raw_title = line.split("<>", 1)
        thread_id = thread_part.replace(".dat", "").strip()
        if not thread_id.isdigit():
            continue
        title, comment_count = parse_5ch_subject_title(clean_html(raw_title))
        try:
            posted_at = datetime.fromtimestamp(int(thread_id), tz=timezone.utc)
        except Exception:
            posted_at = None
        url = f"{source_meta.get('thread_base_url', source_meta['url']).rstrip('/')}/{thread_id}/l50"
        items.append(
            StoryItem(
                source=source_name,
                region=source_meta["region"],
                category=source_meta["category"],
                title=title[:180],
                url=url,
                original_excerpt=f"5ch 仮想通貨板 subject.txt 공개 스레드 목록에서 제목과 댓글 수만 수집했습니다. 댓글 수: {comment_count}",
                posted_at=posted_at,
                collected_at=collected_at,
                rank_position=len(items) + 1,
                comment_count=comment_count,
            )
        )
        if len(items) >= limit:
            break
    return items, f"{source_name} 수집 완료: {len(items)}개"


def collect_public_list(source_name: str, source_meta: dict[str, str], limit: int) -> tuple[list[StoryItem], str]:
    parser_type = source_meta.get("parser", "")
    if parser_type == "5ch_subject":
        return collect_5ch_subject_list(source_name, source_meta, limit)

    collected_at = datetime.now(timezone.utc)
    request = Request(source_meta["url"], headers={"User-Agent": USER_AGENT, "Accept-Language": "ja-JP,ja;q=0.9,ko;q=0.7,en;q=0.6"})
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
        if not is_crypto_public_link(parser_type, href, text):
            continue
        url = urljoin(source_meta["url"], href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(StoryItem(source=source_name, region=source_meta["region"], category=source_meta["category"], title=text[:180], url=url, original_excerpt="공개 목록에서 제목과 링크만 수집했습니다. 본문 확인은 원문 링크에서 진행합니다.", posted_at=None, collected_at=collected_at, rank_position=len(items) + 1))
        if len(items) >= limit:
            break
    return items, f"{source_name} 수집 완료: {len(items)}개"


def infer_analysis(row: dict) -> dict[str, str]:
    return {
        "core_summary": f"이 소재는 '{row['title']}'에서 시작되는 {row['angle']} 유형의 일본/글로벌 크립토 이슈입니다.",
        "core_conflict": "가격 재료, 규제 변화, 거래소·프로젝트 리스크, 커뮤니티 반응 사이의 간극이 핵심입니다.",
        "relationship_map": "발행 매체 / 관련 프로젝트·토큰 / 투자자 커뮤니티 / 규제기관 또는 거래소",
        "red_flag": "커뮤니티발 루머와 공식 발표를 분리하고, 가격 전망을 단정하지 않는 것이 핵심 리스크 관리입니다.",
        "comment_trigger": "시청자는 매수·관망·리스크 회피 관점으로 갈릴 가능성이 높습니다.",
        "pattern_insight": "일본 커뮤니티 반응과 글로벌 헤드라인을 비교해 시장 심리의 방향성을 읽습니다.",
        "risk_note": "투자 조언처럼 단정하지 않고, 출처·시간·확인 필요 포인트를 분리해 재가공해야 합니다.",
    }


def status_badge(score: float) -> str:
    if score >= 75:
        return "🔥 제작 우선"
    if score >= 55:
        return "🟡 후보"
    return "⚪ 관찰"


def make_template_script(row: dict, analysis: dict[str, str]) -> str:
    return f"""00:00
오늘 코인 이슈는요. 제목만 보면 그냥 {row['title']} 이 정도로 보일 수 있어요.
근데 잠깐만. 이건 단순 뉴스가 아니라 일본 커뮤니티 반응과 글로벌 헤드라인이 같이 움직이는 재료일 수 있습니다.
제가 이런 이슈 볼 때 제일 먼저 보는 건 가격 예측이 아니라, 출처와 타이밍이에요.

00:40
먼저 확인할 건 세 가지입니다. 누가 말했는지, 어떤 토큰이나 거래소가 엮였는지, 그리고 시장이 이미 반응했는지예요.
커뮤니티에서는 바로 매수다, 악재다 갈리겠지만 그 전에 공식 발표와 기사 원문을 나눠서 봐야 합니다.

01:40
아니 근데 여러분, 코인판에서 제일 위험한 게 뭐냐면 제목 하나 보고 바로 방향을 정하는 겁니다.
BTC 재료인지, 알트 개별 재료인지, 규제 재료인지에 따라 파급력이 완전히 달라져요.

02:30
지금 댓글에서도 갈릴 수 있어요. 호재다, 이미 반영됐다, 위험하다.
잠깐만요. 이럴수록 가격 예측이 아니라 체크리스트로 봐야 합니다. 출처, 시간, 관련 토큰, 거래소 반응, 커뮤니티 과열도.

06:30
제 관점은 이겁니다. 이 이슈는 바로 매매 판단으로 쓰기보다, 오늘 시장 심리를 읽는 재료로 두는 게 맞습니다.
특히 일본발 커뮤니티 반응은 속도가 빠르지만 루머도 섞이기 때문에 기사 원문과 공식 발표를 반드시 나눠야 합니다.

09:30
여러분이라면 이 이슈, 단기 트레이딩 재료로 보시겠어요? 아니면 리스크 체크용 뉴스로만 보시겠어요?
"""


def fallback_package(row: dict, analysis: dict[str, str]) -> dict:
    script = make_template_script(row, analysis)
    return {
        "source": "template_fallback_live_advice",
        "overview_ko": analysis["core_summary"],
        "analysis": analysis,
        "risk_filter": ["원문 직접 복제 금지", "인물/장소/직장명 일반화", "댓글 원문 대량 저장 금지"],
        "longform_script": script,
        "shorts": {
            "30s": "일본 크립토 커뮤니티에서 지금 갈리는 코인 이슈입니다. 제목보다 먼저 봐야 할 건 출처와 타이밍이에요.",
            "60s": "이 뉴스는 호재냐 악재냐보다 어떤 토큰, 어떤 거래소, 어떤 규제 맥락과 연결되는지가 중요합니다. 바로 매매 판단으로 쓰기 전에 확인 포인트를 나눠야 합니다.",
            "90s": script[:900],
        },
        "threads": {
            "5_post": "1. 오늘 일본/글로벌 크립토 헤드라인에서 체크할 이슈입니다.\n2. 제목보다 중요한 건 출처, 시간, 관련 토큰입니다.\n3. 커뮤니티 반응은 빠르지만 루머가 섞일 수 있습니다.\n4. 공식 발표와 기사 해석을 분리해서 봐야 합니다.\n5. 매매 판단보다 먼저 리스크 체크리스트로 정리하세요.",
            "10_post": "",
        },
        "card_news": {
            "deck_title": "오늘의 일본 크립토 이슈 체크",
            "format": "8장 카드뉴스",
            "8_cards": [
                {
                    "title": "제목보다 먼저 볼 것",
                    "hook": "호재/악재보다 출처와 타이밍",
                    "body": row["title"],
                    "image_prompt": "live advice storytime scene",
                    "design_note": "market radar dashboard, clean dark chart mood",
                    "cta": "이 이슈를 호재로 보시나요, 리스크로 보시나요?",
                }
            ],
        },
        "note_content": {
            "title": "오늘의 일본 크립토 이슈 체크",
            "subtitle": "제목보다 출처, 타이밍, 관련 토큰을 먼저 보는 법",
            "platform": "Notion / 블로그 공용",
            "opening_hook": "코인 뉴스는 제목보다 먼저 출처와 시장 반응의 시간차를 봐야 합니다.",
            "body_markdown": "## 오늘 확인할 포인트\n\n이 이슈는 일본/글로벌 크립토 뉴스 흐름에서 나온 소재입니다. 먼저 관련 토큰, 거래소, 규제기관, 공식 발표 여부를 분리해서 봐야 합니다.\n\n## 바로 매매 판단하지 않기\n\n커뮤니티 반응은 빠르지만 루머와 과장이 섞일 수 있습니다. 뉴스 원문, 공식 발표, 가격 반응, 거래량 변화를 나눠서 체크하는 편이 안전합니다.",
            "key_takeaways": ["출처와 게시 시간을 먼저 확인한다.", "관련 토큰과 거래소를 분리한다.", "커뮤니티 반응은 보조지표로만 사용한다."],
            "cta": "이 이슈를 단기 재료로 보시나요, 리스크 체크용으로 보시나요?",
            "tags": ["크립토뉴스", "일본코인", "비트코인", "카드뉴스", "노트콘텐츠"],
        },
        "titles": ["일본 크립토 커뮤니티가 주목한 오늘의 이슈", "이 코인 뉴스, 호재보다 먼저 볼 체크포인트"],
        "thumbnail_text": ["호재야, 리스크야?", "일본 코인판 반응"],
        "comment_question": "여러분은 이 이슈를 호재로 보시나요, 리스크로 보시나요?",
    }


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
    return {
        "30초 쇼츠": shorts.get("30s", ""),
        "60초 쇼츠": shorts.get("60s", ""),
        "90초 쇼츠": shorts.get("90s", ""),
        "Threads 5": threads.get("5_post", ""),
        "Threads 10": threads.get("10_post", ""),
        "카드뉴스": card_news_to_markdown(package.get("card_news", {})),
        "Note": note_to_markdown(package.get("note_content", {})),
        "썸네일": "\n".join(package.get("thumbnail_text", [])) if isinstance(package.get("thumbnail_text"), list) else str(package.get("thumbnail_text", "")),
        "제목": "\n".join(package.get("titles", [])) if isinstance(package.get("titles"), list) else str(package.get("titles", "")),
    }


def list_to_lines(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value if str(item).strip())
    return str(value or "")


def card_items(card_news: object) -> list[dict]:
    if not isinstance(card_news, dict):
        return []
    for key in ["slides", "cards", "10_cards", "8_cards"]:
        value = card_news.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def card_news_to_markdown(card_news: object) -> str:
    if not isinstance(card_news, dict):
        return str(card_news or "")
    lines = [f"# {card_news.get('deck_title') or '카드뉴스'}"]
    if card_news.get("format"):
        lines.append(f"\n- 포맷: {card_news.get('format')}")
    if card_news.get("design_system"):
        lines.append(f"- 디자인: {card_news.get('design_system')}")
    for index, card in enumerate(card_items(card_news), start=1):
        lines.append(f"\n## {index}장. {card.get('title', '제목 없음')}")
        if card.get("hook"):
            lines.append(f"\n**훅**: {card.get('hook')}")
        if card.get("body"):
            lines.append(f"\n{card.get('body')}")
        if card.get("image_prompt"):
            lines.append(f"\n이미지 프롬프트: {card.get('image_prompt')}")
        if card.get("design_note"):
            lines.append(f"디자인 노트: {card.get('design_note')}")
        if card.get("cta"):
            lines.append(f"CTA: {card.get('cta')}")
    return "\n".join(lines).strip()


def note_to_markdown(note: object) -> str:
    if not isinstance(note, dict):
        return str(note or "")
    title = note.get("title") or "Note 콘텐츠"
    lines = [f"# {title}"]
    if note.get("subtitle"):
        lines.append(f"\n> {note.get('subtitle')}")
    if note.get("opening_hook"):
        lines.append(f"\n{note.get('opening_hook')}")
    if note.get("body_markdown"):
        lines.append(f"\n{note.get('body_markdown')}")
    elif note.get("body"):
        lines.append(f"\n{note.get('body')}")
    takeaways = list_to_lines(note.get("key_takeaways"))
    if takeaways:
        lines.append(f"\n## 핵심 정리\n{takeaways}")
    if note.get("cta"):
        lines.append(f"\n## 질문\n{note.get('cta')}")
    tags = note.get("tags")
    if isinstance(tags, list) and tags:
        lines.append("\n" + " ".join(f"#{tag}" for tag in tags))
    return "\n".join(lines).strip()


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


def fingerprint_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="ignore")).hexdigest()


def clear_downstream_outputs(selected_key: str) -> None:
    for state_key in ["story_analyses", "live_blueprints", "longform_scripts", "quality_checks", "derivative_assets", "production_packages"]:
        st.session_state.setdefault(state_key, {}).pop(selected_key, None)


def ensure_source_material(row: dict, selected_key: str, current_text: str, allow_short_material: bool) -> tuple[str, list[str], str | None]:
    logs: list[str] = []
    current_text = (current_text or "").strip()
    if len(current_text) >= 500:
        logs.append(f"본문 재료 확인: 기존 입력 {len(current_text)}자 사용")
        return current_text, logs, None

    fallback_text = (row.get("original_excerpt", "") or "").strip()
    if fetch_article_body is not None:
        result = fetch_article_body(row.get("url", ""), row.get("source", ""), fallback_text)
        if result.ok and result.body.strip():
            logs.append(f"본문 확보: {result.length}자 / {result.method}")
            if result.method == "rss_excerpt_fallback" and result.error:
                logs.append(f"원문 직접 요청 차단 감지: RSS 제작 재료로 대체 ({result.error})")
            return result.body.strip(), logs, None
        logs.append(f"본문 자동 수집 실패: {result.error or '원인 미상'}")
    else:
        logs.append("본문 수집 모듈 없음: RSS/제목 대체 재료 사용 시도")

    if len(fallback_text) >= 500:
        logs.append(f"RSS 요약 대체 사용: {len(fallback_text)}자")
        return fallback_text, logs, None
    if allow_short_material and len(fallback_text) >= 120:
        logs.append(f"짧은 RSS 요약으로 자동 제작 진행: {len(fallback_text)}자")
        return fallback_text, logs, None
    if allow_short_material and row.get("title"):
        material = f"제목: {row.get('title', '')}\n소스: {row.get('source', '')}\n요약: {fallback_text or '본문 없음'}".strip()
        if len(material) >= 80:
            logs.append("본문이 부족해 제목/RSS 요약 기반 테스트 재료로 진행")
            return material, logs, None
    return current_text or fallback_text, logs, "제작 재료가 너무 짧습니다. RSS 요약도 부족해서 자동 제작을 안전하게 진행할 수 없습니다."


def run_autopilot_pipeline(
    selected_key: str,
    selected_row: dict,
    current_source_text: str,
    model: str,
    temperature: float,
    improve_rounds: int,
    allow_short_material: bool,
    build_derivative_assets: bool,
    package_when_done: bool,
    save_when_done: bool,
) -> tuple[list[str], str | None]:
    logs: list[str] = []
    required_modules = {
        "analyze_story": analyze_story,
        "build_live_blueprint": build_live_blueprint,
        "write_live_longform": write_live_longform,
        "quality_check_live_script": quality_check_live_script,
    }
    missing = [name for name, value in required_modules.items() if value is None]
    if missing:
        return logs, f"필수 모듈 로드 실패: {', '.join(missing)}"
    if not openai_is_configured():
        return logs, "OPENAI_API_KEY가 설정되어 있지 않아 무인 제작을 실행할 수 없습니다."

    source_text, material_logs, material_error = ensure_source_material(selected_row, selected_key, current_source_text, allow_short_material)
    logs.extend(material_logs)
    if material_error:
        return logs, material_error

    previous_fingerprint = st.session_state.setdefault("source_fingerprints", {}).get(selected_key)
    next_fingerprint = fingerprint_text(source_text)
    if previous_fingerprint and previous_fingerprint != next_fingerprint:
        logs.append("제작 재료 변경 감지: 이전 분석/대본/패키지 캐시 초기화")
        clear_downstream_outputs(selected_key)
    else:
        clear_downstream_outputs(selected_key)
        logs.append("무인 제작 기준: 기존 LLM 결과를 재사용하지 않고 새로 생성")
    st.session_state.source_texts[selected_key] = source_text
    st.session_state.source_fingerprints[selected_key] = next_fingerprint

    analysis, error = analyze_story(source_text, selected_row, model, temperature)
    if error:
        return logs, f"1차 이슈 분석 실패: {error}"
    st.session_state.story_analyses[selected_key] = analysis
    logs.append("1차 이슈 분석 완료")

    blueprint, error = build_live_blueprint(analysis, selected_row, model, temperature)
    if error:
        return logs, f"2차 라이브 구조 설계 실패: {error}"
    st.session_state.live_blueprints[selected_key] = blueprint
    logs.append("2차 라이브 구조 설계 완료")

    script, error = write_live_longform(source_text, analysis, blueprint, selected_row, model, temperature)
    if error:
        return logs, f"3차 10분 대본 생성 실패: {error}"
    st.session_state.longform_scripts[selected_key] = script
    logs.append(f"3차 10분 대본 생성 완료: {len(script)}자")

    quality = quality_check_live_script(script)
    st.session_state.quality_checks[selected_key] = quality
    logs.append(f"품질검사: {quality.get('overall_score', 'N/A')}점 / 통과 {'YES' if quality.get('passed') else 'NO'}")

    current_script = script
    current_quality = quality
    for round_idx in range(1, max(1, improve_rounds) + 1):
        if current_quality.get("passed"):
            break
        current_script, current_quality, improve_error = run_quality_improvement(
            selected_key=selected_key,
            selected_row=selected_row,
            source_text=source_text,
            analysis=analysis,
            blueprint=blueprint,
            script=current_script,
            quality=current_quality,
            model=model,
            temperature=temperature,
            mode="품질검사 기준 통과용 전면 재작성",
            user_direction="무인 자동 제작 모드입니다. 품질검사 critical_failures를 반드시 해결하고, 후킹/몰입/상담성/캐릭터성/민감주제 처리/분량을 통과 기준까지 끌어올리세요.",
        )
        if improve_error:
            return logs, f"자동 품질개선 {round_idx}회차 실패: {improve_error}"
        logs.append(f"자동 품질개선 {round_idx}회차: {current_quality.get('overall_score', 'N/A')}점 / 통과 {'YES' if current_quality.get('passed') else 'NO'}")

    if not current_quality.get("passed"):
        return logs, "자동 제작은 완료했지만 품질 기준 통과에 실패했습니다. 파생 콘텐츠/저장은 차단했습니다."

    derivatives = {}
    if build_derivative_assets:
        if generate_derivatives is None:
            logs.append("파생 콘텐츠 생성 모듈 없음: 건너뜀")
        else:
            derivatives, error = generate_derivatives(current_script, analysis, selected_row, model, temperature)
            if error:
                return logs, f"4차 파생 콘텐츠 생성 실패: {error}"
            st.session_state.derivative_assets[selected_key] = derivatives
            logs.append("4차 쇼츠/Threads/카드뉴스/Note 생성 완료")

    if package_when_done:
        if build_package is None:
            return logs, "제작 패키지 조립 모듈을 불러오지 못했습니다."
        package = build_package(selected_row, source_text, analysis, blueprint, current_script, current_quality, derivatives)
        st.session_state.production_packages[selected_key] = package
        logs.append("제작 패키지 조립 완료")
        if save_when_done:
            saved, save_error = save_package(selected_row, package)
            if save_error:
                return logs, f"Supabase 자동 저장 실패: {save_error}"
            logs.append(f"Supabase 자동 저장 완료: {saved}")

    return logs, None


st.title("Japan Crypto Pattern Lab")
st.caption("일본 크립토 미디어 · 5ch 仮想通貨板 · CoinMarketCap 헤드라인 · 카드뉴스/Note 재가공")

initial_state = {
    "stories": [],
    "approved": [],
    "collection_logs": [],
    "rows": [],
    "history_rows": [],
    "source_texts": {},
    "source_fingerprints": {},
    "story_analyses": {},
    "live_blueprints": {},
    "longform_scripts": {},
    "quality_checks": {},
    "derivative_assets": {},
    "production_packages": {},
    "autopilot_logs": {},
}
for key, value in initial_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

with st.sidebar:
    st.header("수집 설정")
    selected_sources = st.multiselect(
        "크립토 RSS 미디어",
        options=list(CRYPTO_RSS_SOURCES.keys()),
        default=["CoinPost JP", "NADA NEWS / CoinDesk Japan", "CRYPTO TIMES JP"],
    )
    selected_public_sources = st.multiselect(
        "공개목록 / 커뮤니티",
        options=list(CRYPTO_PUBLIC_LIST_SOURCES.keys()),
        default=["5ch 仮想通貨板", "CoinMarketCap Headlines"],
    )
    per_source_limit = st.slider("소스당 수집 개수", 5, 50, 15, 5)
    collect_button = st.button("크립토 후보 수집", type="primary", width="stretch")
    st.divider()
    st.header("API 상태")
    st.caption(f"OpenAI: {'ON' if openai_is_configured() else 'OFF'}")
    st.caption(f"Supabase: {'ON' if db_is_configured() else 'OFF'}")
    st.caption(f"패치 버전: {STREAMLIT_PATCH_VERSION}")
    st.caption(f"토큰 파라미터: {TOKEN_PARAMETER_POLICY}")
    with st.expander("업데이트 진단", expanded=True):
        st.write("새 코드의 OpenAI 오류에는 `요청 token 파라미터:`가 함께 표시됩니다.")
        st.caption(f"배포 엔트리포인트: {DEPLOYMENT_ENTRYPOINT}")
        st.caption("실행 중인 앱 파일")
        st.code(app_source(), language="text")
        st.caption("실행 중인 LLM 파이프라인")
        st.code(llm_pipeline_source(), language="text")
        if st.button("LLM 결과/이전 오류 초기화", width="stretch"):
            clear_llm_outputs()
            st.success("이전 LLM 결과와 오류 표시를 비웠습니다.")
            st.rerun()
    llm_model = st.text_input("모델명", value=get_secret("OPENAI_MODEL", DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL)
    st.caption("품질 우선 권장: gpt-5.5 / 균형: gpt-5.4 / 비용 절감: gpt-5.4-mini")
    if llm_model.strip().lower() == "gpt-4o-mini":
        st.warning("gpt-4o-mini는 빠르지만 크립토 이슈 분석과 콘텐츠 구조 설계 품질이 낮게 나올 수 있습니다.")
    temperature = st.slider("창의성", 0.1, 1.2, 0.78, 0.05)
    auto_improve_after_generation = st.checkbox("생성 직후 품질 미달이면 자동 개선", value=True)
    auto_improve_rounds = st.slider("자동 개선 최대 회차", 1, 3, 2, 1, disabled=not auto_improve_after_generation)
    if LLM_PIPELINE_IMPORT_ERROR:
        st.error(f"LLM 파이프라인 로드 실패: {LLM_PIPELINE_IMPORT_ERROR}")
    if SCRIPT_IMPROVER_IMPORT_ERROR:
        st.error(f"품질개선 모듈 로드 실패: {SCRIPT_IMPROVER_IMPORT_ERROR}")
    if st.button("Supabase 테스트", width="stretch"):
        _, err = load_packages(1)
        st.error(err) if err else st.success("Supabase 연결 성공")

if collect_button:
    collected: list[StoryItem] = []
    logs: list[str] = []
    for source_name in selected_sources:
        items = collect_rss(source_name, CRYPTO_RSS_SOURCES[source_name], per_source_limit)
        collected.extend(items)
        logs.append(f"{source_name} 수집 완료: {len(items)}개")
    for source_name in selected_public_sources:
        items, message = collect_public_list(source_name, CRYPTO_PUBLIC_LIST_SOURCES[source_name], per_source_limit)
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

tabs = st.tabs(["📡 소스", "🏆 레이더", "🧩 콘텐츠 제작실", "🗂️ 히스토리", "🧪 원칙/DB"])

with tabs[0]:
    st.subheader("소스 목록")
    st.markdown("#### RSS 미디어")
    st.dataframe([{"site": name, **meta} for name, meta in CRYPTO_RSS_SOURCES.items()], width="stretch", hide_index=True)
    st.markdown("#### 공개목록 / 커뮤니티")
    st.dataframe([{"site": name, **meta} for name, meta in CRYPTO_PUBLIC_LIST_SOURCES.items()], width="stretch", hide_index=True)
    st.markdown("#### 운영 메모")
    st.dataframe(SOURCE_NOTES, width="stretch", hide_index=True)

with tabs[1]:
    st.subheader("크립토 이슈 레이더")
    if not stories:
        st.info("왼쪽에서 소스를 고르고 크립토 후보 수집을 눌러주세요.")
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
        st.dataframe(filtered, width="stretch", hide_index=True, column_order=["badge", "region", "production_score", "viral_score", "velocity_score", "debate_score", "risk_score", "fresh_min", "rank", "source", "angle", "title", "url"])

with tabs[2]:
    st.subheader("크립토 콘텐츠 제작실")
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

        st.markdown("### 🚀 무인 자동 제작")
        st.caption("본문 확보 → 이슈 분석 → 콘텐츠 구조 → 롱폼 대본 → 품질검사/자동개선 → 카드뉴스/Note 패키지까지 한 번에 실행합니다.")
        auto_col1, auto_col2, auto_col3 = st.columns(3)
        allow_short_material_auto = auto_col1.checkbox("본문 짧아도 RSS/제목 기반 진행", value=True, key=f"allow_short_material_auto_{key}")
        auto_derivatives = auto_col2.checkbox("통과 시 파생 콘텐츠까지 생성", value=True, key=f"auto_derivatives_{key}")
        auto_package = auto_col3.checkbox("통과 시 패키지까지 조립", value=True, key=f"auto_package_{key}")
        auto_save = st.checkbox("통과 시 Supabase 자동 저장", value=False, disabled=not db_is_configured(), key=f"auto_save_{key}")
        autopilot_disabled = (
            not openai_is_configured()
            or analyze_story is None
            or build_live_blueprint is None
            or write_live_longform is None
            or quality_check_live_script is None
        )
        if st.button("무인 자동 제작 실행", type="primary", disabled=autopilot_disabled, width="stretch", key=f"autopilot_run_{key}"):
            with st.spinner("무인 자동 제작 실행 중... 본문 확보부터 품질 통과까지 순차 처리합니다."):
                logs, autopilot_error = run_autopilot_pipeline(
                    selected_key=key,
                    selected_row=selected,
                    current_source_text=source_text,
                    model=llm_model,
                    temperature=temperature,
                    improve_rounds=max(3, int(auto_improve_rounds)),
                    allow_short_material=allow_short_material_auto,
                    build_derivative_assets=auto_derivatives,
                    package_when_done=auto_package,
                    save_when_done=auto_save,
                )
            st.session_state.autopilot_logs[key] = logs
            source_text = st.session_state.source_texts.get(key, source_text)
            analysis = st.session_state.story_analyses.get(key, {})
            blueprint = st.session_state.live_blueprints.get(key, {})
            longform = st.session_state.longform_scripts.get(key, "")
            quality = st.session_state.quality_checks.get(key, {})
            derivatives = st.session_state.derivative_assets.get(key, {})
            package = st.session_state.production_packages.get(key)
            if autopilot_error:
                st.error(autopilot_error)
            else:
                st.success("무인 자동 제작 완료: 품질 통과 기준까지 확인했습니다.")
        if autopilot_disabled:
            st.warning("무인 자동 제작을 실행하려면 OpenAI 키와 LLM/품질검사 모듈이 모두 필요합니다.")
        if st.session_state.autopilot_logs.get(key):
            with st.expander("무인 자동 제작 로그", expanded=True):
                for item in st.session_state.autopilot_logs[key]:
                    st.write(f"- {item}")

        st.markdown("### ② 본문 자동 가져오기")
        fetch_col1, fetch_col2 = st.columns([1, 2])
        if fetch_col1.button("본문 자동 가져오기", type="primary", width="stretch"):
            if fetch_article_body is None:
                st.error("source_fetcher.py를 불러오지 못했습니다.")
            else:
                with st.spinner("본문을 자동으로 가져오는 중..."):
                    result = fetch_article_body(selected["url"], selected.get("source", ""), selected.get("original_excerpt", ""))
                if result.ok:
                    st.session_state.source_texts[key] = result.body
                    source_text = result.body
                    st.success(f"본문 확보 완료: {result.length}자 / {result.method}")
                    if result.method == "rss_excerpt_fallback" and result.error:
                        st.info(f"원문 페이지가 직접 요청을 막아서 RSS에 포함된 제작 재료를 사용했습니다. 원인: {result.error}")
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

        st.markdown("### ③ 이슈 분석")
        if st.button("1차 LLM: 크립토 이슈 분석하기", disabled=not ready_for_llm or analyze_story is None, width="stretch"):
            with st.spinner("이슈의 핵심 재료, 시장 반응, 커뮤니티 포인트를 분석 중..."):
                result, error = analyze_story(source_text, selected, llm_model, temperature)
            if error:
                st.session_state.story_analyses.pop(key, None)
                st.session_state.live_blueprints.pop(key, None)
                st.session_state.longform_scripts.pop(key, None)
                analysis = {}
                blueprint = {}
                longform = ""
                st.error(error)
                st.warning("새 이슈 분석 생성에 실패해서 이전 분석/구조/대본 표시를 비웠습니다.")
            else:
                st.session_state.story_analyses[key] = result
                analysis = result
                st.success("이슈 분석 완료")
        st.json(analysis)

        st.markdown("### ④ 콘텐츠 구조 설계")
        if st.button("2차 LLM: 콘텐츠 구조 설계하기", disabled=not bool(analysis) or build_live_blueprint is None, width="stretch"):
            with st.spinner("크립토 이슈 해설 구조를 설계 중..."):
                result, error = build_live_blueprint(analysis, selected, llm_model, temperature)
            if error:
                st.session_state.live_blueprints.pop(key, None)
                st.session_state.longform_scripts.pop(key, None)
                blueprint = {}
                longform = ""
                st.error(error)
                st.warning("새 콘텐츠 구조 생성에 실패해서 이전 구조/대본 표시를 비웠습니다.")
            else:
                st.session_state.live_blueprints[key] = result
                blueprint = result
                st.success("콘텐츠 구조 설계 완료")
        if blueprint:
            st.json(blueprint)

        st.markdown("### ⑤ 10분 롱폼 대본")
        if st.button("3차 LLM: 10분 대본 쓰기", disabled=not bool(blueprint) or write_live_longform is None, type="primary", width="stretch"):
            with st.spinner("크립토 이슈 해설형 롱폼 대본을 작성 중..."):
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
        if st.button("대본 품질검사", disabled=not bool(longform) or quality_check_live_script is None, width="stretch"):
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
                    st.text_area("브리프", build_rewrite_brief(quality, analysis=analysis, row=selected), height=260, disabled=True)
            improve_cols = st.columns(2)
            if improve_cols[0].button("품질 미달 대본 1회 개선", disabled=improve_failed_script is None, type="primary", width="stretch", key=f"improve_once_{key}"):
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
            if improve_cols[1].button("통과할 때까지 자동 개선", disabled=improve_failed_script is None, width="stretch", key=f"improve_until_pass_{key}"):
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
        if st.button("4차 LLM: 쇼츠/Threads/카드뉴스/Note 만들기", disabled=not bool(longform) or generate_derivatives is None or output_locked, width="stretch"):
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
            download_key_suffix = hashlib.md5(str(key).encode("utf-8")).hexdigest()[:10]
            der_tabs = st.tabs(["쇼츠", "Threads", "카드뉴스", "Note", "제목/썸네일", "JSON"])
            with der_tabs[0]:
                st.text_area("30초 쇼츠", exp["30초 쇼츠"], height=140)
                st.text_area("60초 쇼츠", exp["60초 쇼츠"], height=180)
                st.text_area("90초 쇼츠", exp["90초 쇼츠"], height=220)
            with der_tabs[1]:
                st.text_area("5-post Thread", exp["Threads 5"], height=220)
                st.text_area("10-post Thread", exp["Threads 10"], height=320)
            with der_tabs[2]:
                card_news = derivatives.get("card_news", {})
                cards = card_items(card_news)
                if cards:
                    for i, card in enumerate(cards, start=1):
                        with st.expander(f"{i}장 · {card.get('title', '제목 없음')}", expanded=i == 1):
                            if card.get("hook"):
                                st.markdown(f"**훅**: {card.get('hook')}")
                            st.write(card.get("body", ""))
                            st.caption(card.get("design_note", ""))
                            st.text_area(f"{i}장 이미지 프롬프트", card.get("image_prompt", ""), height=90)
                else:
                    st.text_area("카드뉴스 JSON", exp["카드뉴스"], height=360)
                st.download_button(
                    "카드뉴스 Markdown 다운로드",
                    exp["카드뉴스"],
                    file_name="card_news.md",
                    mime="text/markdown",
                    width="stretch",
                    key=f"download_card_news_{download_key_suffix}",
                )
            with der_tabs[3]:
                note = derivatives.get("note_content", {})
                st.text_area("Note Markdown", exp["Note"], height=480)
                if isinstance(note, dict) and isinstance(note.get("platform_adaptations"), dict):
                    with st.expander("플랫폼별 변형", expanded=False):
                        for platform, content in note.get("platform_adaptations", {}).items():
                            st.text_area(str(platform), str(content), height=160)
                st.download_button(
                    "Note Markdown 다운로드",
                    exp["Note"],
                    file_name="note_content.md",
                    mime="text/markdown",
                    width="stretch",
                    key=f"download_note_{download_key_suffix}",
                )
            with der_tabs[4]:
                st.text_area("썸네일 문구", exp["썸네일"], height=120)
                st.text_area("제목 후보", exp["제목"], height=200)
                st.text_area("댓글 질문", derivatives.get("comment_question", ""), height=100)
            with der_tabs[5]:
                st.json(derivatives)

        st.markdown("### ⑧ 저장")
        if output_locked:
            st.warning("품질 미달 대본은 패키지 조립/Supabase 저장 전에 개선이 필요합니다.")
        if st.button("제작 패키지 조립", disabled=not bool(longform) or output_locked, width="stretch"):
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
            if save_col.button("Supabase에 저장", disabled=output_locked, width="stretch"):
                result, error = save_package(selected, package)
                if error:
                    st.error(error)
                else:
                    st.success("Supabase 저장 완료")
                    if isinstance(result, list):
                        st.session_state.history_rows = result + st.session_state.history_rows
            down_col.download_button("패키지 JSON 다운로드", json.dumps(package, ensure_ascii=False, indent=2), file_name="live_advice_package.json", mime="application/json", width="stretch")
            with st.expander("최종 패키지 JSON"):
                st.json(package)

with tabs[3]:
    st.subheader("Supabase 히스토리")
    c1, c2 = st.columns([1, 1])
    limit = c1.slider("불러올 개수", 5, 100, 30, 5)
    if c2.button("히스토리 불러오기", type="primary", width="stretch"):
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
        st.dataframe(history, width="stretch", hide_index=True, column_order=["created_at", "status", "source_name", "production_score", "viral_score", "title", "source_url"])
        selected_history_title = st.selectbox("상세 확인", [row.get("title", "제목 없음") for row in history])
        selected_history = next((row for row in history if row.get("title") == selected_history_title), history[0])
        pkg = selected_history.get("package_json", {})
        history_tabs = st.tabs(["롱폼", "카드뉴스", "Note", "JSON"])
        with history_tabs[0]:
            st.text_area("저장된 10분 롱폼", package_to_text(pkg, "longform_script"), height=420)
        with history_tabs[1]:
            st.text_area("저장된 카드뉴스", card_news_to_markdown(pkg.get("card_news", {})), height=420)
        with history_tabs[2]:
            st.text_area("저장된 Note", note_to_markdown(pkg.get("note_content", {})), height=420)
        with history_tabs[3]:
            st.json(pkg)
        st.download_button("히스토리 JSON 다운로드", json.dumps(selected_history, ensure_ascii=False, indent=2), file_name="history_package.json", mime="application/json", width="stretch")

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
    st.markdown("### v0.7 제작 플로우")
    st.write("일본/글로벌 크립토 후보 수집 → 이슈 분석 → 콘텐츠 구조 설계 → 롱폼 대본 → 품질검사 → 카드뉴스/Note → 저장")

st.caption("Japan Crypto Pattern Lab v0.7 · 일본 크립토 이슈 레이더 · card news / Note pipeline")

