from __future__ import annotations

import re
from dataclasses import asdict, dataclass


STORY_ARTICLE_CLEANER_VERSION = "story-article-cleaner-v2.0"

# The cleaner intentionally knows structural page roles, not publishers or article topics.
# New sites should therefore not require code changes just because their brand/name changes.
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
]

_AUTHOR_BIO_HINTS = [
    "プロフィール", "経歴", "ライター", "編集者", "記者として", "参画", "joined", "contributor",
]


@dataclass
class CleaningDiagnostics:
    original_chars: int
    cleaned_chars: int
    removed_segments: int
    cutoff_marker: str
    removal_reasons: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
    for pattern in _STRUCTURAL_DROP_PATTERNS:
        if re.search(pattern, segment, flags=re.I):
            return True, "structural_pattern"
    lower = segment.casefold()
    # Author bios often survive flattened HTML without a heading. Detect the role,
    # not the publisher/person name. Require a career/profile cue plus a year/date.
    if any(hint.casefold() in lower for hint in _AUTHOR_BIO_HINTS) and re.search(r"(?:19|20)\d{2}", segment):
        return True, "author_bio"
    # Navigation/ad widgets are typically link-dense, sentence-poor fragments.
    pipe_count = segment.count("|") + segment.count("›") + segment.count("→")
    if pipe_count >= 3 and len(re.findall(r"[。！？.!?]", segment)) <= 1:
        return True, "navigation_block"
    return False, ""


def clean_article_text(text: str, title: str = "") -> tuple[str, dict]:
    original = _clean_space(text)
    if not original:
        return "", CleaningDiagnostics(0, 0, 0, "", {}).to_dict()

    segments = _split_segments(original)
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
    if any(marker.casefold() in value.casefold() for marker in _CUTOFF_MARKERS):
        return True
    drop, _ = _is_structural_noise(value)
    return drop
