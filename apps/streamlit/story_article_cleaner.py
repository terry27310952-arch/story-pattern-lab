from __future__ import annotations

import re
from dataclasses import asdict, dataclass


STORY_ARTICLE_CLEANER_VERSION = "story-article-cleaner-v2.1"

_CUTOFF_MARKERS = [
    "関連記事", "関連ニュース", "あわせて読みたい", "合わせて読みたい", "おすすめ記事",
    "おすすめのニュース", "最新記事", "もっと見る", "著者情報", "この記事を書いた人",
    "About the author", "Related Articles", "Related News", "Recommended", "More Stories",
    "Read more", "You may also like",
]

_STRUCTURAL_DROP_PATTERNS = [
    r"^\s*(?:By|Author|Written by|Reporter|Editor|執筆|著者|編集|記者)\b",
    r"\bUpdated\b.{0,100}\b(?:min|minute)s?\s+read\b",
    r"\b(?:Disclaimer|Legal Notice|Terms of Use|Privacy Policy)\b",
    r"(?:免責|投資助言ではありません|投資判断|専門家への相談|利用規約|プライバシー)",
    r"(?:無断転載|転載禁止|著作権|copyright|all rights reserved)",
    r"Reproduction in whole or in part",
    r"The post .* appeared first on",
    r"^\s*(?:next|previous|前の記事|次の記事)\s*$",
    r"^(?:Share|Follow|Subscribe|Newsletter|シェア|フォロー|会員登録|ログイン)\b",
    r"\b1\s*(?:BTC|ETH|SOL|XRP|USDT|USD|JPY)\s*=",
]

_AUTHOR_BIO_HINTS = [
    "プロフィール", "経歴", "ライター", "編集者", "記者として", "参画", "joined", "contributor",
]

_SOCIAL_URL_RE = re.compile(
    r"https?://(?:t\.co|twitter\.com|x\.com|pic\.twitter\.com)/\S+",
    re.I,
)
_SOCIAL_ATTRIBUTION_RE = re.compile(
    r"(?:[—\-–]\s*)?[A-ZÀ-ÖØ-öø-ÿ一-龥ぁ-んァ-ヶ][^。！？!?\n]{0,100}"
    r"\(@[A-Za-z0-9_]{1,30}\)\s+"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},\s+(?:19|20)\d{2}",
    re.I,
)
_HANDLE_DATE_RE = re.compile(
    r"@[A-Za-z0-9_]{1,30}.{0,80}(?:19|20)\d{2}",
    re.I,
)


@dataclass
class CleaningDiagnostics:
    original_chars: int
    cleaned_chars: int
    removed_segments: int
    cutoff_marker: str
    removal_reasons: dict[str, int]
    social_embed_removed: int = 0
    incomplete_tail_dropped: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _strip_social_embeds(text: str) -> tuple[str, int]:
    value = str(text or "")
    before = value
    value, n1 = _SOCIAL_URL_RE.subn(" ", value)
    value, n2 = _SOCIAL_ATTRIBUTION_RE.subn(" ", value)
    value, n3 = re.subn(
        r"\s*[—\-–]?\s*[^。！？!?\n]{0,80}"
        r"@[A-Za-z0-9_]{1,30}\s+"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2},\s+(?:19|20)\d{2}\s*",
        " ",
        value,
        flags=re.I,
    )
    return _clean_space(value), n1 + n2 + n3 + (1 if before and not value else 0)


def _split_segments(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？!?\.])\s+|\n+", str(text or ""))
    segments: list[str] = []
    for item in raw:
        cleaned = _clean_space(item)
        if cleaned and cleaned not in segments:
            segments.append(cleaned)
    return segments


def _is_structural_noise(segment: str) -> tuple[bool, str]:
    if len(segment) < 4:
        return True, "too_short"
    if _SOCIAL_URL_RE.search(segment) or _HANDLE_DATE_RE.search(segment):
        return True, "social_embed"
    for pattern in _STRUCTURAL_DROP_PATTERNS:
        if re.search(pattern, segment, flags=re.I):
            return True, "structural_pattern"
    lower = segment.casefold()
    if any(hint.casefold() in lower for hint in _AUTHOR_BIO_HINTS) and re.search(r"(?:19|20)\d{2}", segment):
        return True, "author_bio"
    pipe_count = segment.count("|") + segment.count("›") + segment.count("→")
    if pipe_count >= 3 and len(re.findall(r"[。！？.!?]", segment)) <= 1:
        return True, "navigation_block"
    return False, ""


def _looks_incomplete_tail(segment: str) -> bool:
    value = str(segment or "").strip()
    if len(value) < 40:
        return False
    if re.search(r"[。！？.!?」』”’)]$", value):
        return False
    words = re.findall(r"[A-Za-z]+|[ぁ-んァ-ヶ一-龥]+", value)
    return len(words) >= 8 or len(value) >= 120


def clean_article_text(text: str, title: str = "") -> tuple[str, dict]:
    original = _clean_space(text)
    if not original:
        return "", CleaningDiagnostics(0, 0, 0, "", {}).to_dict()

    social_cleaned, social_removed = _strip_social_embeds(original)
    segments = _split_segments(social_cleaned)
    kept: list[str] = []
    removed_count = 0
    cutoff_marker = ""
    reasons: dict[str, int] = {}

    for segment in segments:
        marker = next((m for m in _CUTOFF_MARKERS if m.casefold() in segment.casefold()), "")
        if marker:
            cutoff_marker = marker
            removed_count += 1
            reasons["cutoff"] = reasons.get("cutoff", 0) + 1
            break
        drop, reason = _is_structural_noise(segment)
        if drop:
            removed_count += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        kept.append(segment)

    tail_dropped = False
    if kept and _looks_incomplete_tail(kept[-1]):
        kept.pop()
        removed_count += 1
        reasons["incomplete_tail"] = reasons.get("incomplete_tail", 0) + 1
        tail_dropped = True

    cleaned = " ".join(kept)
    cleaned = re.sub(r"\s+(?:next|previous)\s+The post .*? appeared first on .*?$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+The post .*? appeared first on .*?$", "", cleaned, flags=re.I)
    cleaned = _clean_space(cleaned)

    diagnostics = CleaningDiagnostics(
        original_chars=len(original),
        cleaned_chars=len(cleaned),
        removed_segments=removed_count,
        cutoff_marker=cutoff_marker,
        removal_reasons=reasons,
        social_embed_removed=social_removed,
        incomplete_tail_dropped=tail_dropped,
    ).to_dict()
    return cleaned, diagnostics


def clean_story_resource(row: dict) -> dict:
    next_row = dict(row or {})
    raw = str(next_row.get("material") or next_row.get("excerpt") or "")
    cleaned, diagnostics = clean_article_text(raw, str(next_row.get("title") or ""))
    if cleaned:
        next_row["material"] = cleaned
        if len(str(next_row.get("excerpt") or "")) > len(cleaned) * 1.4:
            next_row["excerpt"] = cleaned[:1800]
    next_row["story_cleaning"] = diagnostics
    next_row["story_cleaner_version"] = STORY_ARTICLE_CLEANER_VERSION
    return next_row


def has_boilerplate(text: str) -> bool:
    value = str(text or "")
    if _SOCIAL_URL_RE.search(value) or _HANDLE_DATE_RE.search(value):
        return True
    if any(marker.casefold() in value.casefold() for marker in _CUTOFF_MARKERS):
        return True
    drop, _ = _is_structural_noise(value)
    return drop


def sentence_complete(text: str) -> bool:
    value = str(text or "").strip()
    return bool(value and re.search(r"[。！？.!?」』”’)]$", value))
