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

USER_AGENT = "Mozilla/5.0 StoryPatternLab/0.5; article-body-preview"


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
        if tag in {"p", "div", "article", "section", "li", "br", "h1", "h2", "h3"}:
            self.flush()

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if self.skip_stack and self.skip_stack[-1] == tag:
            self.skip_stack.pop()
            return
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "article", "section", "li", "br", "h1", "h2", "h3"}:
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
    "로그인", "회원가입", "고객센터", "이벤트", "광고", "공지", "검색", "댓글", "추천", "스크랩", "공유",
    "이전글", "다음글", "목록", "본문 바로가기", "메뉴", "copyright", "all rights reserved", "개인정보",
    "정치", "경제", "사회", "연예", "스포츠", "랭킹", "베스트", "쪽지", "신고", "삭제",
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
    candidates.extend(["utf-8", "cp949", "euc-kr"])
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
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
        return decode_html(raw, content_type), None
    except HTTPError as error:
        return None, f"HTTP {error.code}: {error.reason}"
    except URLError as error:
        return None, f"URL 오류: {error}"
    except Exception as error:
        return None, f"본문 요청 실패: {error}"


def is_noise_line(line: str) -> bool:
    lower = line.lower()
    if len(line) < 12:
        return True
    if sum(char.isdigit() for char in line) > max(12, len(line) * 0.45):
        return True
    if any(pattern.lower() in lower for pattern in NOISE_PATTERNS) and len(line) < 80:
        return True
    return False


def score_line(line: str) -> int:
    score = len(line)
    if any(mark in line for mark in ["요", "다", "죠", "ㅠ", "ㅜ", "?", "!", "."]):
        score += 20
    if any(word in line for word in ["엄마", "친구", "남친", "여친", "남편", "아내", "결혼", "회사", "상사", "사연", "제가", "저는"]):
        score += 30
    return score


def extract_readable_text(html: str) -> tuple[str, str, str]:
    cleaned_html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    parser = ReadableTextParser()
    parser.feed(cleaned_html)
    parser.close()
    title = clean_text(" ".join(parser.title_parts))[:200]

    candidates: list[str] = []
    seen: set[str] = set()
    for line in parser.blocks:
        line = clean_text(line)
        if not line or line in seen or is_noise_line(line):
            continue
        seen.add(line)
        candidates.append(line)

    # Prefer longer, more story-like lines while preserving rough order.
    story_lines = [line for line in candidates if score_line(line) >= 60]
    if len("\n".join(story_lines)) < 500:
        story_lines = candidates

    body = "\n".join(story_lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return title, body[:12000], "generic_html_text"


def reddit_json_url(url: str) -> str:
    clean = url.split("?")[0].rstrip("/")
    return clean + ".json"


def fetch_reddit_body(url: str) -> FetchResult:
    json_url = reddit_json_url(url)
    text, error = fetch_url(json_url, accept="application/json")
    if error or not text:
        return FetchResult(False, url, "reddit", "", "", 0, "reddit_json", error or "본문 없음")
    try:
        payload = json.loads(text)
        post = payload[0]["data"]["children"][0]["data"]
        title = clean_text(post.get("title", ""))
        body = clean_text(post.get("selftext", ""))
        if not body:
            body = clean_text(post.get("title", ""))
        return FetchResult(True, url, "reddit", title, body[:12000], len(body), "reddit_json")
    except Exception as error:
        return FetchResult(False, url, "reddit", "", "", 0, "reddit_json", f"Reddit JSON 파싱 실패: {error}")


def fetch_article_body(url: str, source_name: str = "") -> FetchResult:
    domain = urlparse(url).netloc.lower()
    if "reddit.com" in domain:
        result = fetch_reddit_body(url)
        if result.ok and result.length >= 80:
            return result

    html, error = fetch_url(url)
    if error or not html:
        return FetchResult(False, url, source_name, "", "", 0, "html", error or "본문 없음")

    title, body, method = extract_readable_text(html)
    if len(body) < 150:
        return FetchResult(False, url, source_name, title, body, len(body), method, "본문 후보가 너무 짧습니다.")
    return FetchResult(True, url, source_name, title, body, len(body), method)
