from __future__ import annotations

import re
from dataclasses import dataclass, asdict


STORY_ARTICLE_CLEANER_VERSION = "story-article-cleaner-v1.0"

_CUTOFF_MARKERS = [
    "関連記事",
    "関連ニュース",
    "あわせて読みたい",
    "合わせて読みたい",
    "おすすめ記事",
    "おすすめのニュース",
    "最新記事",
    "もっと見る",
    "著者情報",
    "この記事を書いた人",
    "About the author",
    "Related Articles",
    "Related News",
    "More Stories",
]

_DROP_PATTERNS = [
    r"\bDisclaimer\b",
    r"投資助言ではありません",
    r"投資判断の前に",
    r"専門家への相談",
    r"Reproduction in whole or in part",
    r"All rights reserved",
    r"The post .* appeared first on",
    r"^\s*By\s+.+\bEditor\b",
    r"\bUpdated\b.+\bmin read\b",
    r"Coinspeaker参画",
    r"メルマガやSNSで最新情報を発信",
    r"Crypto\.comの評判",
    r"\b1\s*BTC\s*=",
    r"^\s*(?:next|previous)\s*$",
]


@dataclass
class CleaningDiagnostics:
    original_chars: int
    cleaned_chars: int
    removed_segments: int
    cutoff_marker: str
    dropped_examples: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split_segments(text: str) -> list[str]:
    # Preserve Japanese sentence boundaries even when the fetcher flattened HTML blocks.
    raw = re.split(r"(?<=[。！？!?\.])\s+|\n+", str(text or ""))
    segments: list[str] = []
    for item in raw:
        cleaned = _clean_space(item)
        if cleaned and cleaned not in segments:
            segments.append(cleaned)
    return segments


def _drop_segment(segment: str) -> bool:
    if len(segment) < 4:
        return True
    for pattern in _DROP_PATTERNS:
        if re.search(pattern, segment, flags=re.I):
            return True
    return False


def clean_article_text(text: str, title: str = "") -> tuple[str, CleaningDiagnostics]:
    original = _clean_space(text)
    if not original:
        return "", CleaningDiagnostics(0, 0, 0, "", []).to_dict()

    segments = _split_segments(original)
    kept: list[str] = []
    removed: list[str] = []
    cutoff_marker = ""

    for segment in segments:
        marker = next((m for m in _CUTOFF_MARKERS if m.casefold() in segment.casefold()), "")
        if marker:
            cutoff_marker = marker
            removed.append(segment)
            break
        if _drop_segment(segment):
            removed.append(segment)
            continue
        kept.append(segment)

    # RSS syndication tails sometimes survive as a short suffix without sentence spacing.
    cleaned = " ".join(kept)
    cleaned = re.sub(r"\s+(?:next|previous)\s+The post .*? appeared first on .*?$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+The post .*? appeared first on .*?$", "", cleaned, flags=re.I)
    cleaned = _clean_space(cleaned)

    diagnostics = CleaningDiagnostics(
        original_chars=len(original),
        cleaned_chars=len(cleaned),
        removed_segments=len(removed),
        cutoff_marker=cutoff_marker,
        dropped_examples=[item[:180] for item in removed[:5]],
    ).to_dict()
    return cleaned, diagnostics


def clean_story_resource(row: dict) -> dict:
    next_row = dict(row or {})
    raw = str(next_row.get("material") or next_row.get("excerpt") or "")
    cleaned, diagnostics = clean_article_text(raw, str(next_row.get("title") or ""))
    if cleaned:
        next_row["material"] = cleaned
        # Keep excerpt useful but prevent a polluted full-body from winning later.
        if len(str(next_row.get("excerpt") or "")) > len(cleaned) * 1.4:
            next_row["excerpt"] = cleaned[:1800]
    next_row["story_cleaning"] = diagnostics
    next_row["story_cleaner_version"] = STORY_ARTICLE_CLEANER_VERSION
    return next_row


def has_boilerplate(text: str) -> bool:
    value = str(text or "")
    return any(re.search(pattern, value, flags=re.I) for pattern in _DROP_PATTERNS) or any(
        marker.casefold() in value.casefold() for marker in _CUTOFF_MARKERS
    )
