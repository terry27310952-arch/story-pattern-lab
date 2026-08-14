from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from math import log10
from typing import Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import feedparser
from dateutil import parser as date_parser


USER_AGENT = "Mozilla/5.0 StoryPatternLab/1.0; crypto-trader-briefing"


RSS_SOURCES = {
    "NADA NEWS / CoinDesk Japan": {
        "url": "https://www.coindeskjapan.com/feed/",
        "category": "일본 크립토 미디어",
        "region": "Japan",
        "source_type": "rss",
    },
    "CRYPTO TIMES JP": {
        "url": "https://crypto-times.jp/feed/",
        "category": "일본 Web3/블록체인",
        "region": "Japan",
        "source_type": "rss",
    },
    "Cryptonews JP": {
        "url": "https://cryptonews.com/jp/feed/",
        "category": "일본어 글로벌 크립토 뉴스",
        "region": "Japan/Global",
        "source_type": "rss",
    },
    "Coinspeaker JP": {
        "url": "https://www.coinspeaker.com/jp/feed/",
        "category": "일본어 크립토/금융 뉴스",
        "region": "Japan/Global",
        "source_type": "rss",
    },
    "CoinDesk Global": {
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "category": "글로벌 크립토 뉴스",
        "region": "Global",
        "source_type": "rss",
    },
    "Cointelegraph Global": {
        "url": "https://cointelegraph.com/rss",
        "category": "글로벌 크립토 뉴스",
        "region": "Global",
        "source_type": "rss",
    },
}


PUBLIC_LIST_SOURCES = {
    "5ch Crypto Board": {
        "url": "https://fate.5ch.io/cryptocoin/subject.txt",
        "thread_base_url": "https://fate.5ch.io/test/read.cgi/cryptocoin/",
        "category": "일본 커뮤니티",
        "region": "Japan Community",
        "source_type": "community",
        "parser": "5ch_subject",
    },
    "CoinMarketCap Headlines": {
        "url": "https://coinmarketcap.com/headlines/news/",
        "category": "글로벌 코인 헤드라인",
        "region": "Global",
        "source_type": "public_list",
        "parser": "link_list",
    },
    "Yahoo Finance JP Crypto": {
        "url": "https://finance.yahoo.co.jp/news/search?q=%E4%BB%AE%E6%83%B3%E9%80%9A%E8%B2%A8",
        "category": "일본 금융/암호자산 뉴스",
        "region": "Japan",
        "source_type": "public_list",
        "parser": "yahoo_finance",
    },
    "Yahoo Finance JP CoinPost": {
        "url": "https://finance.yahoo.co.jp/news/media/coinpost",
        "category": "CoinPost 기사 목록",
        "region": "Japan",
        "source_type": "public_list",
        "parser": "yahoo_finance",
    },
}


ASSET_KEYWORDS = {
    "BTC": ["bitcoin", "btc", "ビットコイン", "비트코인"],
    "ETH": ["ethereum", "eth", "イーサリアム", "이더리움"],
    "SOL": ["solana", "sol", "ソラナ", "솔라나"],
    "XRP": ["xrp", "ripple", "リップル", "리플"],
    "ALT": ["altcoin", "アルト", "알트", "token", "토큰"],
    "STABLE": ["stablecoin", "ステーブルコイン", "스테이블"],
    "ETF": ["etf", "上場投資信託", "현물 etf"],
    "REG": ["sec", "cftc", "規制", "税制", "규제", "세제"],
    "EXCHANGE": ["binance", "coinbase", "取引所", "거래소", "sbi"],
    "SECURITY": ["hack", "scam", "exploit", "ハッキング", "해킹", "피싱"],
    "MACRO": ["cpi", "fed", "frb", "金利", "금리", "inflation", "国債"],
    "WEB3": ["web3", "defi", "nft", "dao", "rwa", "블록체인"],
}


NOISE_WORDS = [
    "로그인",
    "회원가입",
    "広告",
    "プライバシー",
    "利用規約",
    "次へ",
    "前へ",
    "ランキング",
    "お問い合わせ",
]


@dataclass
class ResourceItem:
    id: str
    source: str
    source_type: str
    region: str
    category: str
    title: str
    url: str
    excerpt: str
    posted_at: Optional[datetime]
    collected_at: datetime
    rank: int
    comment_count: int = 0
    view_count: int = 0
    tags: tuple[str, ...] = ()
    freshness_min: Optional[int] = None
    trader_score: float = 0.0
    risk_score: float = 0.0

    def to_row(self) -> dict:
        row = asdict(self)
        row["tags"] = ", ".join(self.tags)
        row["posted_at"] = self.posted_at.isoformat() if self.posted_at else ""
        row["collected_at"] = self.collected_at.isoformat()
        row["freshness_min"] = self.freshness_min
        return row


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
        text = clean_html(text, limit=260)
        if href and text:
            self.links.append((href, text))


def clean_html(value: str | None, limit: int = 1400) -> str:
    if not value:
        return ""
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def decode_html(raw: bytes, content_type: str = "") -> str:
    charset_match = re.search(r"charset=([\w-]+)", content_type or "")
    candidates: list[str] = []
    if charset_match:
        candidates.append(charset_match.group(1))
    candidates.extend(["utf-8", "shift_jis", "cp932", "euc-jp", "cp949"])
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
    return max(0, int((datetime.now(timezone.utc) - value).total_seconds() / 60))


def stable_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def classify_tags(text: str) -> tuple[str, ...]:
    lower = text.lower()
    tags: list[str] = []
    for tag, keywords in ASSET_KEYWORDS.items():
        if any(keyword.lower() in lower for keyword in keywords):
            tags.append(tag)
    return tuple(tags or ["CRYPTO"])


def log_score(value: int, scale: float) -> float:
    if value <= 0:
        return 0.0
    return min(100.0, max(0.0, log10(value + 1) * scale))


def score_item(item: ResourceItem) -> ResourceItem:
    fresh = minutes_since(item.posted_at)
    freshness_score = 52.0 if fresh is None else max(0.0, min(100.0, 100.0 - fresh / 20.0))
    rank_score = max(0.0, min(100.0, 100.0 - (item.rank - 1) * 3.5))
    comment_score = log_score(item.comment_count, 24.0)
    source_bonus = 10.0 if item.source_type == "rss" else 6.0
    community_bonus = min(24.0, comment_score * 0.35) if item.source_type == "community" else 0.0
    tag_bonus = 8.0 if any(tag in item.tags for tag in ("BTC", "ETH", "ETF", "REG", "MACRO")) else 3.0
    trader_score = min(100.0, freshness_score * 0.36 + rank_score * 0.34 + comment_score * 0.18 + source_bonus + tag_bonus + community_bonus)
    risk_score = 58.0 if item.source_type == "community" else 28.0 if item.source_type == "public_list" else 18.0
    item.freshness_min = fresh
    item.trader_score = round(trader_score, 2)
    item.risk_score = round(risk_score, 2)
    return item


def make_resource(
    *,
    source: str,
    meta: dict,
    title: str,
    url: str,
    excerpt: str,
    posted_at: Optional[datetime],
    rank: int,
    comment_count: int = 0,
) -> ResourceItem:
    title = clean_html(title, limit=240)
    excerpt = clean_html(excerpt, limit=1400)
    item = ResourceItem(
        id=stable_id(source, url, title),
        source=source,
        source_type=meta.get("source_type", "unknown"),
        region=meta.get("region", ""),
        category=meta.get("category", ""),
        title=title,
        url=url,
        excerpt=excerpt,
        posted_at=posted_at,
        collected_at=datetime.now(timezone.utc),
        rank=rank,
        comment_count=comment_count,
        tags=classify_tags(f"{title} {excerpt}"),
    )
    return score_item(item)


def collect_rss(source_name: str, meta: dict, limit: int) -> tuple[list[ResourceItem], str]:
    feed = feedparser.parse(meta["url"])
    items: list[ResourceItem] = []
    if getattr(feed, "bozo", False) and not getattr(feed, "entries", []):
        return [], f"{source_name}: RSS 응답 파싱 실패"
    for index, entry in enumerate(getattr(feed, "entries", [])[:limit], start=1):
        title = getattr(entry, "title", "")
        url = getattr(entry, "link", "")
        if not title or not url:
            continue
        published = getattr(entry, "published", None) or getattr(entry, "updated", None)
        content_values = []
        for content_item in getattr(entry, "content", []) or []:
            value = getattr(content_item, "value", "")
            if value:
                content_values.append(value)
        summary_source = max([getattr(entry, "summary", ""), *content_values], key=lambda value: len(str(value)), default="")
        items.append(
            make_resource(
                source=source_name,
                meta=meta,
                title=title,
                url=url,
                excerpt=summary_source,
                posted_at=parse_datetime(published),
                rank=index,
            )
        )
    return items, f"{source_name}: {len(items)}건 수집"


def parse_5ch_subject_title(raw_title: str) -> tuple[str, int]:
    match = re.search(r"\s*\((\d+)\)\s*$", raw_title)
    if not match:
        return raw_title.strip(), 0
    return raw_title[: match.start()].strip(), int(match.group(1))


def collect_5ch_subject(source_name: str, meta: dict, limit: int) -> tuple[list[ResourceItem], str]:
    request = Request(meta["url"], headers={"User-Agent": USER_AGENT, "Accept-Language": "ja-JP,ja;q=0.9,ko;q=0.7,en;q=0.6"})
    try:
        with urlopen(request, timeout=12) as response:
            text = decode_html(response.read(), response.headers.get("Content-Type", ""))
    except Exception as error:
        return [], f"{source_name}: 수집 실패 - {error}"

    items: list[ResourceItem] = []
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
        url = f"{meta.get('thread_base_url', meta['url']).rstrip('/')}/{thread_id}/l50"
        excerpt = f"5ch 공개 subject 목록에서 감지된 스레드입니다. 댓글 수: {comment_count}. 원문 댓글 전문은 저장하지 않고 제목과 반응량만 사용합니다."
        items.append(
            make_resource(
                source=source_name,
                meta=meta,
                title=title,
                url=url,
                excerpt=excerpt,
                posted_at=posted_at,
                rank=len(items) + 1,
                comment_count=comment_count,
            )
        )
        if len(items) >= limit:
            break
    return items, f"{source_name}: {len(items)}건 수집"


def link_is_relevant(parser_type: str, href: str, text: str) -> bool:
    if len(text) < 8:
        return False
    if any(word.lower() in text.lower() for word in NOISE_WORDS):
        return False
    lower_href = href.lower()
    lower_text = text.lower()
    if parser_type == "yahoo_finance":
        if "finance.yahoo.co.jp/news" not in lower_href:
            return False
    if parser_type == "link_list":
        if "coinmarketcap.com" not in lower_href:
            return False
    return any(keyword.lower() in lower_text for keywords in ASSET_KEYWORDS.values() for keyword in keywords)


def collect_public_links(source_name: str, meta: dict, limit: int) -> tuple[list[ResourceItem], str]:
    request = Request(
        meta["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ja-JP,ja;q=0.9,ko;q=0.7,en;q=0.6",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urlopen(request, timeout=14) as response:
            html = decode_html(response.read(), response.headers.get("Content-Type", ""))
    except Exception as error:
        return [], f"{source_name}: 수집 실패 - {error}"

    parser = LinkTextParser()
    parser.feed(html)
    seen: set[str] = set()
    items: list[ResourceItem] = []
    for href, text in parser.links:
        url = urljoin(meta["url"], href)
        if url in seen or not link_is_relevant(meta.get("parser", ""), url, text):
            continue
        seen.add(url)
        items.append(
            make_resource(
                source=source_name,
                meta=meta,
                title=text,
                url=url,
                excerpt="공개 목록에서 제목과 링크를 수집했습니다. 본문 취합 옵션을 켜면 가능한 범위에서 원문 텍스트를 보강합니다.",
                posted_at=None,
                rank=len(items) + 1,
            )
        )
        if len(items) >= limit:
            break
    return items, f"{source_name}: {len(items)}건 수집"


def collect_source(source_name: str, meta: dict, limit: int) -> tuple[list[ResourceItem], str]:
    parser = meta.get("parser", "")
    if parser == "5ch_subject":
        return collect_5ch_subject(source_name, meta, limit)
    if parser:
        return collect_public_links(source_name, meta, limit)
    return collect_rss(source_name, meta, limit)


def collect_resources(rss_names: list[str], public_names: list[str], limit: int) -> tuple[list[dict], list[str]]:
    collected: list[ResourceItem] = []
    logs: list[str] = []
    for source_name in rss_names:
        items, log = collect_source(source_name, RSS_SOURCES[source_name], limit)
        collected.extend(items)
        logs.append(log)
    for source_name in public_names:
        items, log = collect_source(source_name, PUBLIC_LIST_SOURCES[source_name], limit)
        collected.extend(items)
        logs.append(log)

    unique: dict[str, ResourceItem] = {}
    for item in collected:
        unique[item.id] = item
    rows = [item.to_row() for item in unique.values()]
    rows.sort(key=lambda row: row.get("trader_score", 0), reverse=True)
    return rows, logs
