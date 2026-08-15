from __future__ import annotations

from dataclasses import dataclass

import reasoning_engine


TRADER_PIPELINE_VERSION = "trader-pipeline-v6.0"


@dataclass
class TraderResult:
    brief: dict
    content_package: dict
    error: str | None = None


def build_trader_brief(
    resources: list[dict],
    market_snapshot: dict,
    briefing_type: str,
    tone: str,
    config: dict,
) -> tuple[dict, str | None]:
    """Run the legacy professional trader reasoning path without any story patches."""
    return reasoning_engine.generate_trader_brief(
        resources,
        market_snapshot,
        briefing_type,
        tone,
        config,
    )


def build_trader_content_package(
    brief: dict,
    resources: list[dict],
    custom_card_count: int,
    config: dict,
    output_locale: str,
) -> dict:
    """Build trader cards from the trader brief only.

    Storytelling never calls this function. Keeping this boundary explicit prevents the
    old fixed market-card schema from leaking into the storytelling product.
    """
    package = reasoning_engine.generate_content_package(
        brief,
        resources,
        custom_card_count,
        config,
        output_locale,
    )
    package = dict(package or {})
    quality = package.setdefault("content_quality", {})
    quality["mode"] = "trader"
    quality["pipeline"] = TRADER_PIPELINE_VERSION
    return package


def generate_trader_result(
    resources: list[dict],
    market_snapshot: dict,
    briefing_type: str,
    tone: str,
    config: dict,
    output_locale: str,
    custom_card_count: int,
) -> TraderResult:
    brief, error = build_trader_brief(
        resources,
        market_snapshot,
        briefing_type,
        tone,
        config,
    )
    if error:
        return TraderResult(brief=dict(brief or {}), content_package={}, error=error)
    package = build_trader_content_package(
        dict(brief or {}),
        resources,
        custom_card_count,
        config,
        output_locale,
    )
    return TraderResult(brief=dict(brief or {}), content_package=package, error=None)
