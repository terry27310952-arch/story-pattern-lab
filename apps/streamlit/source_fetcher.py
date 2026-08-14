from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 StoryPatternLab/1.0"
MAX_BODY_CHARS = 26000


@dataclass
class FetchResult:
    ok: bool
    url: str
    source: str
    title: str
    body: str
    length: int
    method: str
    error: Optional[str] = None


class ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_stack: list[str] = []
        self.blocks: list[str] = []
        self.current: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe", "form", "select", "button"}:
            self.skip_stack.append(tag)
            return
        if tag == "title":
            self.in_title = True
        if tag in {"p", "div", "article", "main", "section", "li", "br", "h1", "h2", "h3", "blockquote"}:
            self.flush()

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if self.skip_stack and self.skip_stack[-1] == tag:
            self.skip_stack.pop()
            return
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "article", "main", "section", "li", "br", "h1", "h2", "h3", "blockquote"}:
            self.flush()

    def handle_data(self, data: str):
        if self.skip_stack:
            return
        text = clean_text(data)
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        self.current.append(text)

    def flush(self) -> None:
        if not self.current:
            return
        line = clean_text(" ".join(self.current))
        self.current = []
        if line:
            self.blocks.append(line)

    def close(self):
        super().close()
        self.flush()


NOISE_PATTERNS = [
    "ログイン",
    "会員登録",
    "広告",
    "お問い合わせ",
    "利用規約",
    "プライバシー",
    "関連記事",
    "おすすめ",
    "ランキング",
    "シェア",
    "コメント",
    "前の記事",
    "次の記事",
    "copyright",
    "all rights reserved",
    "newsletter",
    "subscribe",
]


ARTICLE_TERMS = [
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "xrp",
    "solana",
    "altcoin",
    "crypto",
    "token",
    "etf",
    "sec",
    "stablecoin",
    "blockchain",
    "ビットコイン",
    "イーサリアム",
    "暗号資産",
    "仮想通貨",
    "アルトコイン",
    "ステーブルコイン",
    "ブロックチェーン",
    "規制",
    "取引所",
    "市場",
    "投資家",
    "ビットコインETF",
]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def decode_html(raw: bytes, content_type: str = "") -> str:
    charset_match = re.search(r"charset=([\w-]+)", content_type or "")
    candidates: list[str] = []
    if charset_match:
        candidates.append(charset_match.group(1))
    candidates.extend(["utf-8", "shift_jis", "cp932", "euc-jp", "cp949", "euc-kr"])
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def fetch_url(url: str, accept: str = "text/html") -> tuple[Optional[str], Optional[str]]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "ja-JP,ja;q=0.9,ko-KR;q=0.8,ko;q=0.7,en;q=0.6",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with urlopen(request, timeout=18) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
        return decode_html(raw, content_type), None
    except HTTPError as error:
        return None, f"HTTP {error.code}: {error.reason}"
    except URLError as error:
        return None, f"URL error: {error}"
    except Exception as error:
        return None, f"article request failed: {error}"


def is_noise_line(line: str) -> bool:
    lower = line.lower()
    if len(line) < 12:
        return True
    if sum(char.isdigit() for char in line) > max(20, len(line) * 0.5):
        return True
    if any(pattern.lower() in lower for pattern in NOISE_PATTERNS) and len(line) < 120:
        return True
    return False


def score_line(line: str) -> int:
    score = len(line)
    if any(mark in line for mark in ["。", "、", "です", "ます", "だ", "である", "?", "!", "."]):
        score += 20
    if any(word.lower() in line.lower() for word in ARTICLE_TERMS):
        score += 35
    if len(line) > 120:
        score += 15
    return score


def extract_json_ld_article(html: str) -> tuple[str, str]:
    titles: list[str] = []
    bodies: list[str] = []
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE):
        raw = unescape(match.group(1)).strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph")
            if isinstance(graph, list):
                candidates.extend([item for item in graph if isinstance(item, dict)])
            article_type = str(candidate.get("@type", "")).lower()
            if "article" not in article_type and "newsarticle" not in article_type:
                continue
            if candidate.get("headline"):
                titles.append(clean_text(str(candidate["headline"])))
            if candidate.get("articleBody"):
                bodies.append(clean_text(str(candidate["articleBody"])))
            elif candidate.get("description"):
                bodies.append(clean_text(str(candidate["description"])))
    return (titles[0] if titles else "", "\n\n".join(bodies)[:MAX_BODY_CHARS])


def extract_readable_text(html: str) -> tuple[str, str, str]:
    json_title, json_body = extract_json_ld_article(html)
    if len(json_body) >= 600:
        return json_title[:200], json_body, "json_ld_article"

    cleaned_html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    parser = ReadableTextParser()
    parser.feed(cleaned_html)
    parser.close()
    title = clean_text(json_title or " ".join(parser.title_parts))[:200]

    candidates: list[str] = []
    seen: set[str] = set()
    for line in parser.blocks:
        line = clean_text(line)
        if not line or line in seen or is_noise_line(line):
            continue
        seen.add(line)
        candidates.append(line)

    article_lines = [line for line in candidates if score_line(line) >= 70]
    if len("\n".join(article_lines)) < 900:
        article_lines = candidates

    body = "\n".join(article_lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return title, body[:MAX_BODY_CHARS], "generic_html_text"


def reddit_json_candidates(url: str) -> list[str]:
    clean = url.split("?")[0].rstrip("/")
    candidates = [clean + ".json?raw_json=1"]
    parsed = urlparse(clean)
    parts = [part for part in parsed.path.split("/") if part]
    if "comments" in parts:
        index = parts.index("comments")
        if len(parts) > index + 1:
            post_id = parts[index + 1]
            candidates.append(f"https://www.reddit.com/comments/{post_id}.json?raw_json=1")
            if index >= 2 and parts[index - 2] == "r":
                subreddit = parts[index - 1]
                candidates.append(f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?raw_json=1")
    seen: set[str] = set()
    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)
    return unique_candidates


def fetch_reddit_body(url: str) -> FetchResult:
    errors: list[str] = []
    for json_url in reddit_json_candidates(url):
        text, error = fetch_url(json_url, accept="application/json,text/plain,*/*")
        if error or not text:
            errors.append(f"{json_url}: {error or 'empty body'}")
            continue
        try:
            payload = json.loads(text)
            post = payload[0]["data"]["children"][0]["data"]
            title = clean_text(post.get("title", ""))
            body = clean_text(post.get("selftext", "") or post.get("selftext_html", "") or title)
            if len(body) >= 80:
                return FetchResult(True, url, "reddit", title, body[:MAX_BODY_CHARS], len(body), "reddit_json")
            errors.append(f"{json_url}: Reddit body too short.")
        except Exception as error:
            errors.append(f"{json_url}: Reddit JSON parse failed: {error}")
    return FetchResult(False, url, "reddit", "", "", 0, "reddit_json", " / ".join(errors[-2:]) or "Reddit body unavailable")


def fallback_result(url: str, source_name: str, fallback_text: str, reason: str) -> Optional[FetchResult]:
    fallback = clean_text(fallback_text)
    if len(fallback) < 120:
        return None
    return FetchResult(True, url, source_name, "", fallback[:MAX_BODY_CHARS], len(fallback), "rss_excerpt_fallback", reason)


def fetch_article_body(url: str, source_name: str = "", fallback_text: str = "") -> FetchResult:
    domain = urlparse(url).netloc.lower()
    if "reddit.com" in domain:
        result = fetch_reddit_body(url)
        if result.ok and result.length >= 80:
            return result
        fallback = fallback_result(url, source_name or "reddit", fallback_text, result.error or "Reddit request blocked")
        if fallback:
            return fallback

    html, error = fetch_url(url)
    if error or not html:
        fallback = fallback_result(url, source_name, fallback_text, error or "empty body")
        if fallback:
            return fallback
        return FetchResult(False, url, source_name, "", "", 0, "html", error or "empty body")

    title, body, method = extract_readable_text(html)
    if len(body) < 150:
        fallback = fallback_result(url, source_name, fallback_text, "article text too short; using feed excerpt")
        if fallback:
            return fallback
        return FetchResult(False, url, source_name, title, body, len(body), method, "article text too short")
    return FetchResult(True, url, source_name, title, body, len(body), method)
