from __future__ import annotations

import json
import os
import html
from datetime import datetime

import streamlit as st

from excel_exporter import build_excel_bytes
from market_data import (
    MARKET_SCHEMA_VERSION,
    collect_market_snapshot,
    flatten_derivatives_rows,
    flatten_indicator_rows,
    flatten_level_rows,
    flatten_market_rows,
    summarize_market,
)
from reasoning_engine import (
    DEFAULT_BRAND_OUTRO,
    DEFAULT_OUTPUT_LOCALE,
    PROVIDER_LOCAL,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI_COMPATIBLE,
    generate_content_package,
    generate_trader_brief,
)
from resource_collector import PUBLIC_LIST_SOURCES, RSS_SOURCES, collect_resources

try:
    from source_fetcher import fetch_article_body
except Exception:
    fetch_article_body = None


APP_VERSION = "2026-08-15 kiyosaki-editorial-carousel-v12"


MARKET_STRUCTURE_LABELS = {
    "regime": "시장 체제",
    "trader_bias": "내 방향 편향",
    "trader_market_read": "내 시장 해석",
    "trader_expected_path": "내 예상 경로",
    "trader_entry_plan": "내 진입 계획",
    "trader_profit_plan": "내 익절 계획",
    "trader_risk_plan": "내 무효화/리스크",
    "trader_no_trade_zone": "내 매매 금지 구간",
    "trader_alt_strategy": "내 알트 대응",
    "trader_subjective_note": "내 매매 철학",
    "critical_levels": "현재 가격·핵심 레벨",
    "technical_indicators": "보조지표",
    "derivatives": "파생 포지션",
    "btc_axis": "BTC 기준축",
    "alts": "알트 로테이션",
    "japan_risk": "니케이·일본 위험자산",
    "defensive_assets": "골드·달러 방어축",
    "sentiment": "심리 지표",
    "reference_lens": "참고 관점",
}


st.set_page_config(page_title="Crypto Trader Briefing Lab", page_icon="₿", layout="wide")


st.markdown(
    """
    <style>
    .block-container { padding-top: 1.2rem; max-width: 1480px; }
    div[data-testid="stMetric"] {
        background: #F7FAFC;
        border: 1px solid #D9E2EC;
        border-radius: 8px;
        padding: 12px;
    }
    div[data-testid="stMetric"] label { color: #334E68; font-weight: 700; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #102A43; }
    .brief-box {
        border: 1px solid #D9E2EC;
        border-radius: 8px;
        padding: 14px 16px;
        background: #FFFFFF;
        margin-bottom: 12px;
    }
    .muted { color: #52606D; font-size: 0.92rem; }
    .observer-preview {
        position: relative;
        width: min(100%, 430px);
        aspect-ratio: 4 / 5;
        overflow: hidden;
        border-radius: 8px;
        border: 1px solid #2b241f;
        background:
            radial-gradient(circle at 78% 34%, rgba(241, 112, 36, 0.18), transparent 26%),
            linear-gradient(155deg, #050505 0%, #10100f 58%, #080706 100%);
        color: #f4efe6;
        padding: 28px;
        margin: 0 0 16px 0;
        box-shadow: 0 18px 42px rgba(0,0,0,0.28);
    }
    .observer-preview::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(0deg, rgba(0,0,0,0.42), transparent 48%);
        pointer-events: none;
    }
    .observer-copy { position: relative; z-index: 3; max-width: 78%; }
    .observer-eyebrow {
        color: #f17a2d;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 12px;
    }
    .observer-headline {
        font-size: 1.65rem;
        line-height: 1.12;
        font-weight: 800;
        color: #fff8ed;
        margin-bottom: 12px;
    }
    .observer-sub {
        color: #d8d0c3;
        font-size: 0.92rem;
        line-height: 1.45;
        margin-bottom: 12px;
    }
    .observer-message {
        color: #f1e7d9;
        font-size: 0.95rem;
        line-height: 1.48;
    }
    .observer-metrics {
        position: absolute;
        left: 28px;
        right: 28px;
        bottom: 58px;
        z-index: 3;
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
    }
    .observer-metric {
        border: 1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.045);
        padding: 9px 10px;
        border-radius: 6px;
    }
    .observer-metric span {
        display: block;
        color: #a9a096;
        font-size: 0.66rem;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .observer-metric strong { color: #fff8ed; font-size: 0.98rem; }
    .observer-metric.support strong { color: #7fcf9b; }
    .observer-metric.risk strong,
    .observer-metric.resistance strong { color: #e66d5f; }
    .observer-source {
        position: absolute;
        left: 28px;
        right: 28px;
        bottom: 22px;
        z-index: 3;
        color: #82796f;
        font-size: 0.68rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .observer-figure {
        position: absolute;
        z-index: 2;
        right: 22px;
        bottom: 26px;
        width: 36%;
        height: 48%;
        filter: drop-shadow(-10px 0 18px rgba(241,112,36,0.22));
        opacity: 0.92;
    }
    .observer-figure::before {
        content: "";
        position: absolute;
        left: 36%;
        top: 0;
        width: 28%;
        height: 24%;
        border-radius: 50% 50% 46% 46%;
        background: #010101;
        box-shadow: -4px 0 0 rgba(241,112,36,0.44), 0 0 22px rgba(241,112,36,0.16);
    }
    .observer-figure::after {
        content: "";
        position: absolute;
        left: 18%;
        bottom: 0;
        width: 64%;
        height: 78%;
        border-radius: 44% 44% 8% 8%;
        background: linear-gradient(90deg, #020202, #14110f 50%, #030303);
        border-left: 1px solid rgba(241,112,36,0.32);
    }
    .observer-preview.chart_primary .observer-figure,
    .observer-preview.scenario_primary .observer-figure { width: 18%; height: 28%; opacity: 0.64; }
    .observer-preview.data_primary .observer-figure,
    .observer-preview.news_primary .observer-figure { width: 25%; height: 36%; opacity: 0.76; }
    .observer-preview.hero_character .observer-copy { max-width: 64%; }
    .observer-preview.brand_outro {
        background:
            radial-gradient(circle at 50% 38%, rgba(241, 112, 36, 0.22), transparent 28%),
            linear-gradient(180deg, #020202 0%, #0a0908 58%, #000000 100%);
    }
    .observer-preview.brand_outro .observer-copy {
        max-width: 100%;
        text-align: center;
        margin: 0 auto;
    }
    .observer-preview.brand_outro .observer-headline {
        font-size: 2rem;
        line-height: 1.04;
        margin-top: 8px;
        white-space: pre-line;
    }
    .observer-preview.brand_outro .observer-sub { color: #f17a2d; }
    .observer-preview.brand_outro .observer-message {
        position: absolute;
        left: 24px;
        right: 24px;
        top: 322px;
        white-space: pre-line;
        font-size: 1rem;
    }
    .observer-preview.brand_outro .observer-metrics { display: none; }
    .observer-preview.brand_outro .observer-figure {
        left: 25%;
        right: auto;
        bottom: 120px;
        width: 50%;
        height: 44%;
        opacity: 0.98;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def env_value(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get(name, default)


def init_state() -> None:
    defaults = {
        "resources": [],
        "collection_logs": [],
        "selected_ids": [],
        "market_snapshot": {},
        "brief": {},
        "content_package": {},
        "enriched_resources": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def records(data: object) -> list[dict]:
    if hasattr(data, "to_dict"):
        return data.to_dict("records")
    return list(data or [])


def selected_resources() -> list[dict]:
    selected = set(st.session_state.get("selected_ids", []))
    return [row for row in st.session_state.get("resources", []) if row.get("id") in selected]


def has_value(value: object) -> bool:
    return value is not None and value != ""


def market_snapshot_has_depth(snapshot: dict) -> bool:
    if not snapshot:
        return False
    if snapshot.get("schema_version") != MARKET_SCHEMA_VERSION:
        return False
    summary = summarize_market(snapshot)
    required = [
        "btc_price",
        "btc_nearest_support",
        "btc_nearest_resistance",
        "btc_ma20",
        "btc_ma50",
        "btc_rsi14",
        "btc_macd_bias",
        "btc_atr14",
        "btc_atr14_pct",
        "btc_mark_price",
        "btc_funding_rate",
    ]
    oi_available = any(
        has_value(summary.get(key))
        for key in ["btc_open_interest_contracts", "btc_open_interest_value_usd", "btc_open_interest_base"]
    )
    return all(has_value(summary.get(key)) for key in required) and oi_available


def refresh_market_if_incomplete(reason: str) -> bool:
    if market_snapshot_has_depth(st.session_state.get("market_snapshot", {})):
        return True
    with st.spinner(f"{reason} 가격 레벨과 보조지표를 다시 계산하는 중입니다."):
        st.session_state.market_snapshot = collect_market_snapshot()
    ok = market_snapshot_has_depth(st.session_state.get("market_snapshot", {}))
    if not ok:
        st.warning("시장 데이터가 일부만 수집되었습니다. 브리핑은 생성할 수 있지만 가격 레벨/보조지표 일부가 제한될 수 있습니다.")
        errors = st.session_state.market_snapshot.get("errors", [])
        if errors:
            with st.expander("시장 데이터 수집 오류", expanded=False):
                for error in errors:
                    st.write(f"- {error}")
    return ok


def shorten(value: object, length: int = 120) -> str:
    text = " ".join(str(value or "").split())
    return text[: length - 1] + "…" if len(text) > length else text


def market_label(key: str) -> str:
    return MARKET_STRUCTURE_LABELS.get(key, key)


def fmt_price(value: object) -> str:
    if value is None or value == "":
        return "데이터 없음"
    try:
        number = float(value)
    except Exception:
        return str(value)
    if abs(number) >= 1000:
        return f"${number:,.0f}"
    if abs(number) >= 1:
        return f"${number:,.4f}".rstrip("0").rstrip(".")
    return f"${number:,.6f}".rstrip("0").rstrip(".")


def fmt_pct(value: object) -> str:
    if value is None or value == "":
        return "데이터 없음"
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return str(value)


def markdown_brief(brief: dict) -> str:
    if not brief:
        return ""
    lines = [f"# {brief.get('title', 'Crypto Trader Briefing')}", "", brief.get("one_line", ""), ""]
    if brief.get("trader_stance"):
        stance = brief["trader_stance"]
        lines.append("## 내 매매 관점")
        for key, label in [
            ("persona", "관점"),
            ("directional_bias", "방향 편향"),
            ("preferred_posture", "선호 포지션"),
            ("conviction_score", "확신도"),
            ("market_read", "시장 해석"),
            ("expected_path", "예상 경로"),
            ("entry_plan", "진입 계획"),
            ("profit_plan", "익절 계획"),
            ("risk_plan", "무효화/리스크"),
            ("no_trade_zone", "매매 금지 구간"),
            ("alt_strategy", "알트 대응"),
            ("subjective_note", "매매 철학"),
        ]:
            if stance.get(key) != "":
                lines.append(f"- {label}: {stance.get(key)}")
        lines.append("")
    if brief.get("material_coverage"):
        coverage = brief["material_coverage"]
        lines.append("## 원문 취합 범위")
        lines.append(
            f"- 선택 {coverage.get('selected_sources')}건 / 본문 확보 {coverage.get('full_text_sources')}건 / "
            f"총 {coverage.get('total_material_chars', 0):,}자"
        )
        lines.append("")
    lines.append("## 핵심 포인트")
    for point in brief.get("key_points", []):
        lines.append(f"- {point}")
    lines.append("")
    if brief.get("market_structure"):
        lines.append("## 시장 구조")
        for key, value in brief.get("market_structure", {}).items():
            lines.append(f"- {market_label(key)}: {value}")
        lines.append("")
    if brief.get("source_findings"):
        lines.append("## 원문별 해석")
        for item in brief.get("source_findings", []):
            lines.append(f"### {item.get('source')} - {item.get('title')}")
            lines.append(f"- 역할: {item.get('role')}")
            for evidence in item.get("evidence", []):
                lines.append(f"- 근거: {evidence}")
            lines.append(f"- 트레이더 해석: {item.get('trader_read')}")
            lines.append("")
    if brief.get("scenarios"):
        lines.append("## 시나리오")
        for scenario in brief.get("scenarios", []):
            lines.append(f"### {scenario.get('case')}")
            lines.append(f"- 조건: {scenario.get('trigger')}")
            lines.append(f"- 예상 경로: {scenario.get('expected_path')}")
            if scenario.get("trader_view"):
                lines.append(f"- 내 해석: {scenario.get('trader_view')}")
            if scenario.get("positioning"):
                lines.append(f"- 포지션: {scenario.get('positioning')}")
            lines.append(f"- 체크: {scenario.get('watch')}")
        lines.append("")
    if brief.get("invalidation_points"):
        lines.append("## 무효화 조건")
        for point in brief.get("invalidation_points", []):
            lines.append(f"- {point}")
        lines.append("")
    if brief.get("action_plan"):
        lines.append("## 실행 체크리스트")
        for item in brief.get("action_plan", []):
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## 트레이더 문장")
    for sentence in brief.get("trader_sentences", []):
        lines.append(f"- {sentence}")
    lines.append("")
    if brief.get("weekly_brief"):
        lines.append("## 주간 브리핑")
        for section in brief.get("weekly_brief", []):
            lines.append(f"### {section.get('heading', '')}")
            lines.append(section.get("body", ""))
            lines.append("")
    if brief.get("daily_brief"):
        lines.append("## 일간 시간대 브리핑")
        for block in brief.get("daily_brief", []):
            lines.append(f"### {block.get('time_zone', '')}")
            if block.get("decision"):
                lines.append(f"- 내 결정: {block.get('decision')}")
            lines.append(block.get("trader_read", ""))
            if block.get("expected_move"):
                lines.append(f"- 예상 움직임: {block.get('expected_move')}")
            if block.get("action_plan"):
                lines.append(f"- 행동 계획: {block.get('action_plan')}")
            if block.get("no_trade"):
                lines.append(f"- 하지 않을 매매: {block.get('no_trade')}")
            for item in block.get("watch", []):
                lines.append(f"- 관련 원문: {item}")
            lines.append("")
    lines.append("## 리스크")
    for note in brief.get("risk_notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines)


def cards_to_markdown(cards: list[dict]) -> str:
    lines: list[str] = []
    for card in cards:
        lines.append(f"## {card.get('slide')}. {card.get('headline', '')}")
        if card.get("eyebrow"):
            lines.append(f"*{card.get('eyebrow')}*")
        lines.append("")
        if card.get("subheadline"):
            lines.append(card.get("subheadline", ""))
            lines.append("")
        if card.get("key_message"):
            lines.append(card.get("key_message", ""))
            lines.append("")
        metrics = card.get("metrics") or []
        if metrics:
            for metric in metrics[:4]:
                lines.append(f"- {metric.get('label')}: {metric.get('value')}")
            lines.append("")
        insight = card.get("insight") or {}
        if insight.get("visible") and insight.get("text"):
            label = insight.get("label")
            lines.append(f"### {label}" if label else "### 핵심")
            lines.append(insight.get("text", ""))
            lines.append("")
        action = card.get("action") or {}
        if action.get("visible") and action.get("text"):
            prefix = f"{action.get('label')}: " if action.get("label") else ""
            lines.append(f"> {prefix}{action.get('text')}")
            lines.append("")
        risk = card.get("risk") or {}
        if risk.get("visible") and risk.get("text"):
            lines.append(f"> {risk.get('text')}")
            lines.append("")
        source = card.get("source") or {}
        source_text = " · ".join([value for value in [source.get("publisher", ""), source.get("short_title", "")] if value])
        if source_text:
            lines.append(f"`{source_text}`")
        lines.append("")
    return "\n".join(lines).strip()


def visual_spec_rows(content_package: dict) -> list[dict]:
    rows: list[dict] = []
    for set_label, card_set in (content_package.get("cards") or {}).items():
        for card in card_set:
            direction = card.get("visual_direction") or {}
            prompts = direction.get("image_prompts") or {}
            source = card.get("source") or {}
            rows.append(
                {
                    "set": set_label,
                    "slide": card.get("slide"),
                    "card_type": card.get("card_type"),
                    "headline": card.get("headline"),
                    "layout": direction.get("layout_variant"),
                    "shot": direction.get("character_shot"),
                    "visibility": direction.get("character_visibility"),
                    "pose": direction.get("character_pose"),
                    "position": direction.get("character_position"),
                    "camera": direction.get("camera_angle"),
                    "lighting": direction.get("lighting_intensity"),
                    "focus": direction.get("visual_focus"),
                    "prompt_4_5": prompts.get("4:5", ""),
                    "prompt_9_16": prompts.get("9:16", ""),
                    "negative_prompt": direction.get("negative_prompt", ""),
                    "source": " · ".join([value for value in [source.get("publisher", ""), source.get("short_title", "")] if value]),
                }
            )
    return rows


def metric_variant(label: str) -> str:
    lowered = str(label or "").lower()
    if "지지" in lowered or "support" in lowered:
        return "support"
    if "저항" in lowered or "risk" in lowered or "resistance" in lowered:
        return "resistance"
    return ""


def observer_card_preview_html(card: dict) -> str:
    direction = card.get("visual_direction") or {}
    layout = html.escape(str(direction.get("layout_variant") or "character_side"))
    visibility = direction.get("character_visibility") or 0.3
    try:
        figure_width = max(14, min(54, float(visibility) * 100))
    except Exception:
        figure_width = 32
    source = card.get("source") or {}
    source_text = " · ".join([value for value in [source.get("publisher", ""), source.get("short_title", "")] if value])
    footer_text = card.get("footer") or f"The Observer · {source_text}"
    metric_html = []
    for metric in (card.get("metrics") or [])[:4]:
        variant = metric_variant(metric.get("label", ""))
        metric_html.append(
            "<div class='observer-metric {variant}'><span>{label}</span><strong>{value}</strong></div>".format(
                variant=html.escape(variant),
                label=html.escape(str(metric.get("label", ""))),
                value=html.escape(str(metric.get("value", ""))),
            )
        )
    return """
    <div class="observer-preview {layout}">
      <div class="observer-copy">
        <div class="observer-eyebrow">{eyebrow}</div>
        <div class="observer-headline">{headline}</div>
        <div class="observer-sub">{subheadline}</div>
        <div class="observer-message">{message}</div>
      </div>
      <div class="observer-figure" style="width:{figure_width:.1f}%"></div>
      <div class="observer-metrics">{metrics}</div>
      <div class="observer-source">{footer}</div>
    </div>
    """.format(
        layout=layout,
        eyebrow=html.escape(str(card.get("eyebrow", ""))),
        headline=html.escape(str(card.get("headline", ""))),
        subheadline=html.escape(str(card.get("subheadline", ""))),
        message=html.escape(str(card.get("key_message", ""))),
        figure_width=figure_width,
        metrics="".join(metric_html),
        footer=html.escape(footer_text),
    )


def enrich_material(rows: list[dict], enabled: bool) -> tuple[list[dict], list[str]]:
    enriched: list[dict] = []
    logs: list[str] = []
    for index, row in enumerate(rows, start=1):
        next_row = dict(row)
        next_row["material"] = row.get("excerpt", "")
        if enabled and fetch_article_body is not None and row.get("source_type") != "community":
            result = fetch_article_body(row.get("url", ""), row.get("source", ""), row.get("excerpt", ""))
            if getattr(result, "ok", False) and getattr(result, "body", ""):
                next_row["material"] = result.body
                next_row["fetch_method"] = result.method
                logs.append(f"{row.get('source')}: 본문 {result.length}자 취합")
            else:
                next_row["fetch_method"] = "excerpt_fallback"
                logs.append(f"{row.get('source')}: 요약문 사용")
        else:
            next_row["fetch_method"] = "community_subject_only" if row.get("source_type") == "community" else "excerpt_only"
        enriched.append(next_row)
    return enriched, logs


def provider_config(provider_label: str, temperature: float) -> dict:
    if provider_label.startswith("Ollama"):
        return {
            "provider": PROVIDER_OLLAMA,
            "base_url": st.session_state.get("ollama_base_url", "http://localhost:11434"),
            "model": st.session_state.get("ollama_model", "qwen3:4b"),
            "temperature": temperature,
        }
    if provider_label.startswith("OpenAI-compatible"):
        return {
            "provider": PROVIDER_OPENAI_COMPATIBLE,
            "base_url": st.session_state.get("free_ai_base_url", env_value("FREE_AI_API_BASE", "")),
            "api_key": st.session_state.get("free_ai_api_key", env_value("FREE_AI_API_KEY", "")),
            "model": st.session_state.get("free_ai_model", env_value("FREE_AI_MODEL", "")),
            "temperature": temperature,
        }
    return {"provider": PROVIDER_LOCAL, "temperature": temperature}


def render_market(snapshot: dict) -> None:
    rows = flatten_market_rows(snapshot)
    if not rows:
        st.info("시장 데이터가 아직 없습니다.")
        return
    summary = summarize_market(snapshot)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BTC 현재가", fmt_price(summary.get("btc_price")), fmt_pct(summary.get("btc_24h")))
    c2.metric("가까운 지지", fmt_price(summary.get("btc_nearest_support")), fmt_pct(summary.get("btc_support_distance_pct")))
    c3.metric("가까운 저항", fmt_price(summary.get("btc_nearest_resistance")), fmt_pct(summary.get("btc_resistance_distance_pct")))
    c4.metric("RSI / MACD", f"{summary.get('btc_rsi14', 'N/A')} / {summary.get('btc_macd_bias', 'N/A')}", f"ATR {fmt_pct(summary.get('btc_atr14_pct'))}")

    market_tabs = st.tabs(["가격", "핵심 레벨", "보조지표", "파생/심리"])
    with market_tabs[0]:
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
            column_order=[
                "name",
                "asset_class",
                "price",
                "unit",
                "change_24h",
                "change_7d",
                "change_30d",
                "technical_bias",
                "nearest_support",
                "nearest_resistance",
                "rsi14",
                "macd_bias",
                "source",
            ],
        )
    with market_tabs[1]:
        level_rows = flatten_level_rows(snapshot)
        if level_rows:
            st.dataframe(
                level_rows,
                hide_index=True,
                use_container_width=True,
                column_order=["asset", "direction", "level", "distance_pct", "reason", "importance", "source"],
            )
        else:
            st.info("가격 레벨 데이터가 없습니다.")
    with market_tabs[2]:
        indicator_rows = flatten_indicator_rows(snapshot)
        if indicator_rows:
            st.dataframe(indicator_rows, hide_index=True, use_container_width=True)
        else:
            st.info("보조지표 데이터가 없습니다.")
    with market_tabs[3]:
        derivative_rows = flatten_derivatives_rows(snapshot)
        if derivative_rows:
            st.dataframe(derivative_rows, hide_index=True, use_container_width=True)
        fear = snapshot.get("fear_greed", {})
        if fear:
            st.write(f"Fear & Greed: **{fear.get('value')} / {fear.get('classification')}**")
        st.caption("가격/캔들: Binance spot, 파생: Binance Futures, 시총/JYP: CoinGecko, 매크로: Yahoo Finance, 심리: Alternative.me")
    if not market_snapshot_has_depth(snapshot):
        st.warning("현재 시장 snapshot에 가격 레벨/보조지표가 부족합니다. 브리핑 생성 시 자동으로 다시 갱신됩니다.")
    if snapshot.get("errors"):
        with st.expander("시장 데이터 오류", expanded=False):
            for error in snapshot["errors"]:
                st.write(f"- {error}")


def render_brief(brief: dict) -> None:
    if not brief:
        st.info("아직 생성된 브리핑이 없습니다.")
        return
    if brief.get("_provider_warning"):
        st.warning(brief["_provider_warning"])
    if brief.get("material_coverage"):
        coverage = brief["material_coverage"]
        c1, c2, c3 = st.columns(3)
        c1.metric("선택 원문", coverage.get("selected_sources", 0))
        c2.metric("본문 확보", coverage.get("full_text_sources", 0))
        c3.metric("분석 글자수", f"{coverage.get('total_material_chars', 0):,}")
    st.markdown(f"### {brief.get('title', 'Briefing')}")
    st.markdown(f"<div class='brief-box'><strong>{brief.get('one_line', '')}</strong></div>", unsafe_allow_html=True)
    stance = brief.get("trader_stance") or {}
    if stance:
        st.markdown("#### 내 매매 관점")
        s1, s2, s3 = st.columns(3)
        s1.metric("방향 편향", stance.get("directional_bias", "N/A"))
        s2.metric("선호 포지션", stance.get("preferred_posture", "N/A"))
        s3.metric("확신도", f"{stance.get('conviction_score', 'N/A')}점")
        st.markdown(
            f"<div class='brief-box'><strong>{stance.get('persona', '')}</strong><br>{stance.get('market_read', '')}<br><br>"
            f"<strong>예상 경로:</strong> {stance.get('expected_path', '')}<br>"
            f"<strong>진입:</strong> {stance.get('entry_plan', '')}<br>"
            f"<strong>리스크:</strong> {stance.get('risk_plan', '')}<br>"
            f"<strong>하지 않을 행동:</strong> {stance.get('no_trade_zone', '')}</div>",
            unsafe_allow_html=True,
        )
    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.markdown("#### 핵심 포인트")
        for point in brief.get("key_points", []):
            st.write(f"- {point}")
    with col_b:
        st.markdown("#### 트레이더 문장")
        for sentence in brief.get("trader_sentences", []):
            st.write(f"- {sentence}")

    brief_tabs = st.tabs(["시장 구조", "원문별 해석", "시나리오", "주간", "일간", "소스", "JSON"])
    with brief_tabs[0]:
        market = brief.get("market_structure", {})
        if market:
            for key, value in market.items():
                st.markdown(f"#### {market_label(key)}")
                st.write(value)
        else:
            st.info("시장 구조 분석이 없습니다.")
    with brief_tabs[1]:
        findings = brief.get("source_findings", [])
        if not findings:
            st.info("원문별 해석이 없습니다.")
        for item in findings:
            with st.expander(f"{item.get('source')} · {item.get('title')}", expanded=False):
                st.write(f"**역할:** {item.get('role')}")
                st.write(f"**원문 글자수:** {item.get('material_chars', 0):,}")
                st.write("**근거:**")
                for evidence in item.get("evidence", []):
                    st.write(f"- {evidence}")
                st.write(f"**트레이더 해석:** {item.get('trader_read')}")
                if item.get("url"):
                    st.link_button("원문 열기", item.get("url"))
    with brief_tabs[2]:
        scenarios = brief.get("scenarios", [])
        for scenario in scenarios:
            st.markdown(f"#### {scenario.get('case')}")
            st.write(f"**조건:** {scenario.get('trigger')}")
            st.write(f"**예상 경로:** {scenario.get('expected_path')}")
            if scenario.get("trader_view"):
                st.write(f"**내 해석:** {scenario.get('trader_view')}")
            if scenario.get("positioning"):
                st.write(f"**포지션:** {scenario.get('positioning')}")
            st.caption(f"체크: {scenario.get('watch')}")
        if brief.get("invalidation_points"):
            st.markdown("#### 무효화 조건")
            for point in brief.get("invalidation_points", []):
                st.write(f"- {point}")
        if brief.get("action_plan"):
            st.markdown("#### 실행 체크리스트")
            for item in brief.get("action_plan", []):
                st.write(f"- {item}")
    with brief_tabs[3]:
        for section in brief.get("weekly_brief", []):
            st.markdown(f"#### {section.get('heading', '')}")
            st.write(section.get("body", ""))
    with brief_tabs[4]:
        for block in brief.get("daily_brief", []):
            st.markdown(f"#### {block.get('time_zone', '')}")
            if block.get("decision"):
                st.write(f"**내 결정:** {block.get('decision')}")
            st.write(block.get("trader_read", ""))
            if block.get("expected_move"):
                st.write(f"**예상 움직임:** {block.get('expected_move')}")
            if block.get("action_plan"):
                st.write(f"**행동 계획:** {block.get('action_plan')}")
            if block.get("no_trade"):
                st.write(f"**하지 않을 매매:** {block.get('no_trade')}")
            if block.get("watch"):
                st.markdown("**관련 원문 체크:**")
                for item in block.get("watch", []):
                    st.write(f"- {item}")
    with brief_tabs[5]:
        st.dataframe(brief.get("source_digest", []), hide_index=True, use_container_width=True)
    with brief_tabs[6]:
        st.json(brief)


def render_cards(content_package: dict) -> None:
    if not content_package:
        st.info("브리핑을 먼저 카드뉴스/Note로 분리해 주세요.")
        return
    cards = content_package.get("cards") or {}
    tabs = st.tabs(["5장", "6장", "7장", "자율제안", "브랜드 연출", "Note", "JSON"])
    for label, tab in zip(["5장", "6장", "7장", "자율제안"], tabs[:4]):
        with tab:
            card_set = cards.get(label, [])
            for card in card_set:
                with st.expander(f"{card.get('slide')}. {card.get('headline')}", expanded=card.get("slide") == 1):
                    st.markdown(observer_card_preview_html(card), unsafe_allow_html=True)
                    if card.get("eyebrow"):
                        st.caption(card.get("eyebrow"))
                    if card.get("subheadline"):
                        st.markdown(f"#### {card.get('subheadline')}")
                    if card.get("key_message"):
                        st.write(card.get("key_message", ""))
                    metrics = card.get("metrics") or []
                    if metrics:
                        metric_columns = st.columns(min(len(metrics), 4))
                        for metric, column in zip(metrics[:4], metric_columns):
                            column.metric(metric.get("label", ""), metric.get("value", ""))
                    insight = card.get("insight") or {}
                    if insight.get("visible") and insight.get("text"):
                        if insight.get("label"):
                            st.markdown(f"**{insight.get('label')}**")
                        st.write(insight.get("text", ""))
                    action = card.get("action") or {}
                    if action.get("visible") and action.get("text"):
                        action_text = f"{action.get('label')}: {action.get('text')}" if action.get("label") else action.get("text")
                        st.info(action_text)
                    risk = card.get("risk") or {}
                    if risk.get("visible") and risk.get("text"):
                        st.warning(risk.get("text", ""))
                    source = card.get("source") or {}
                    source_text = " · ".join([value for value in [source.get("publisher", ""), source.get("short_title", "")] if value])
                    if source_text:
                        st.caption(source_text)
            st.download_button(
                f"{label} Markdown 다운로드",
                cards_to_markdown(card_set),
                file_name=f"card_news_{label}.md",
                mime="text/markdown",
                use_container_width=True,
            )
    with tabs[4]:
        rows = visual_spec_rows(content_package)
        if rows:
            st.dataframe(
                rows,
                hide_index=True,
                use_container_width=True,
                column_order=[
                    "set",
                    "slide",
                    "card_type",
                    "headline",
                    "layout",
                    "shot",
                    "visibility",
                    "pose",
                    "position",
                    "camera",
                    "lighting",
                    "focus",
                    "prompt_4_5",
                    "prompt_9_16",
                    "negative_prompt",
                    "source",
                ],
            )
            st.download_button(
                "브랜드 연출 JSON 다운로드",
                json.dumps(rows, ensure_ascii=False, indent=2),
                file_name="observer_visual_prompts.json",
                mime="application/json",
                use_container_width=True,
            )
        else:
            st.info("브랜드 연출 데이터가 없습니다.")
    with tabs[5]:
        st.text_area("Note Markdown", content_package.get("note_markdown", ""), height=520)
        st.download_button(
            "Note Markdown 다운로드",
            content_package.get("note_markdown", ""),
            file_name="note_briefing.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with tabs[6]:
        st.json(content_package)


init_state()


with st.sidebar:
    st.header("수집")
    selected_rss = st.multiselect(
        "일본/글로벌 크립토 RSS",
        options=list(RSS_SOURCES.keys()),
        default=[
            "NADA NEWS / CoinDesk Japan",
            "Cryptonews JP",
            "Coinspeaker JP",
            "CoinDesk Global",
            "Cointelegraph Global",
            "Decrypt",
            "NewsBTC",
            "U.Today",
        ],
    )
    selected_public = st.multiselect(
        "커뮤니티/공개 목록",
        options=list(PUBLIC_LIST_SOURCES.keys()),
        default=[
            "5ch Crypto Board",
            "CoinMarketCap Headlines",
            "Yahoo Finance JP Crypto",
            "Yahoo Finance JP Bitcoin",
            "Yahoo Finance JP CoinPost",
            "Yahoo Finance JP CoinDesk Japan",
        ],
    )
    per_source_limit = st.slider("소스별 수집 수", 5, 80, 20, 1)
    refresh_market_with_collection = st.checkbox("시장 데이터 함께 갱신", value=True)
    collect_button = st.button("리소스 수집", type="primary", use_container_width=True)

    st.divider()
    st.header("추론")
    provider_label = st.selectbox(
        "AI 엔진",
        [
            "무료 로컬 전문 분석 엔진",
            "Ollama 무료 로컬 모델",
            "OpenAI-compatible 무료 API",
        ],
    )
    temperature = st.slider("추론 온도", 0.1, 0.9, 0.35, 0.05)
    if provider_label.startswith("Ollama"):
        st.text_input("Ollama URL", value=env_value("OLLAMA_BASE_URL", "http://localhost:11434"), key="ollama_base_url")
        st.text_input("Ollama 모델", value=env_value("OLLAMA_MODEL", "qwen3:4b"), key="ollama_model")
    elif provider_label.startswith("OpenAI-compatible"):
        st.text_input("API Base URL", value=env_value("FREE_AI_API_BASE", ""), key="free_ai_base_url")
        st.text_input("모델", value=env_value("FREE_AI_MODEL", ""), key="free_ai_model")
        st.text_input("API Key", value=env_value("FREE_AI_API_KEY", ""), type="password", key="free_ai_api_key")

    st.divider()
    st.header("브리핑")
    briefing_type_label = st.radio("브리핑 타입", ["주간 방향", "일간 시간대"], horizontal=True)
    tone = st.selectbox("문장 톤", ["트레이더 브리핑", "카드뉴스용 압축", "Note용 분석"], index=0)
    auto_fetch_body = st.checkbox("선택 리소스 원문 전체 자동 취합", value=True)
    st.caption("커뮤니티 자료는 제목/반응량만 사용하고, 기사/미디어 자료는 선택된 항목 전부의 본문 취합을 시도합니다. 선택 수를 늘릴수록 전문성은 올라가지만 생성 시간도 늘어납니다.")
    output_locale = st.selectbox("카드 출력 locale", ["ja-JP", "ko-KR"], index=0 if DEFAULT_OUTPUT_LOCALE == "ja-JP" else 1)
    custom_card_count = st.slider("자율제안 분석 카드 수", 5, 7, 6, 1)
    with st.expander("브랜드 엔딩", expanded=False):
        st.caption("마지막 카드는 항상 고정 브랜드 발행 카드로 붙습니다.")
        brand_account = st.text_input("FOLLOW 계정 ID", value=env_value("BRAND_ACCOUNT", ""))
        brand_cta = st.text_area("고정 CTA", value=DEFAULT_BRAND_OUTRO["cta"], height=72)

    st.divider()
    st.caption(f"버전: {APP_VERSION}")


if collect_button:
    with st.spinner("선택 소스에서 리소스를 수집하는 중입니다."):
        resources, logs = collect_resources(selected_rss, selected_public, per_source_limit)
    st.session_state.resources = resources
    st.session_state.collection_logs = logs
    st.session_state.selected_ids = [row["id"] for row in resources[: min(20, len(resources))]]
    st.session_state.brief = {}
    st.session_state.content_package = {}
    if refresh_market_with_collection:
        with st.spinner("시장 데이터를 갱신하는 중입니다."):
            st.session_state.market_snapshot = collect_market_snapshot()


st.title("Crypto Trader Briefing Lab")
st.caption("Expanded Japan/global crypto source reader with live BTC levels, technical indicators, derivatives, Nikkei/Gold/DXY context, card news, Note, and Excel packaging.")

resources = st.session_state.resources
market_snapshot = st.session_state.market_snapshot
selected = selected_resources()

m1, m2, m3, m4 = st.columns(4)
m1.metric("수집 리소스", len(resources))
m2.metric("선택 리소스", len(selected))
m3.metric("시장 데이터", len(flatten_market_rows(market_snapshot)) if market_snapshot else 0)
m4.metric("카드뉴스 세트", len((st.session_state.content_package.get("cards") or {})))

if st.session_state.collection_logs:
    with st.expander("수집 로그", expanded=False):
        for log in st.session_state.collection_logs:
            st.write(f"- {log}")


tabs = st.tabs(["수집/시장", "리소스 선택", "AI 브리핑", "카드뉴스/Note", "구조"])


with tabs[0]:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("시장 데이터")
        if st.button("시장 데이터 갱신", use_container_width=True):
            with st.spinner("BTC, 알트, 니케이, 골드, 달러, 심리 데이터를 가져오는 중입니다."):
                st.session_state.market_snapshot = collect_market_snapshot()
                market_snapshot = st.session_state.market_snapshot
        render_market(market_snapshot)
    with right:
        st.subheader("소스 매트릭스")
        source_tabs = st.tabs(["RSS", "공개 목록"])
        with source_tabs[0]:
            st.dataframe([{"name": name, **meta} for name, meta in RSS_SOURCES.items()], hide_index=True, use_container_width=True)
        with source_tabs[1]:
            st.dataframe([{"name": name, **meta} for name, meta in PUBLIC_LIST_SOURCES.items()], hide_index=True, use_container_width=True)


with tabs[1]:
    st.subheader("리소스 다중 선택")
    if not resources:
        st.info("왼쪽에서 리소스를 먼저 수집하세요.")
    else:
        f1, f2, f3 = st.columns([2, 1, 1])
        query = f1.text_input("검색", "")
        tag_filter = f2.multiselect("태그", sorted({tag.strip() for row in resources for tag in str(row.get("tags", "")).split(",") if tag.strip()}))
        min_score = f3.slider("최소 점수", 0, 100, 0, 5)

        filtered = []
        for row in resources:
            haystack = f"{row.get('title', '')} {row.get('source', '')} {row.get('tags', '')}".lower()
            row_tags = {tag.strip() for tag in str(row.get("tags", "")).split(",") if tag.strip()}
            if query and query.lower() not in haystack:
                continue
            if tag_filter and not row_tags.intersection(tag_filter):
                continue
            if float(row.get("trader_score", 0) or 0) < min_score:
                continue
            filtered.append(row)

        visible_ids = {row["id"] for row in filtered}
        display_rows = [
            {
                "선택": row["id"] in set(st.session_state.selected_ids),
                "id": row["id"],
                "score": row.get("trader_score"),
                "risk": row.get("risk_score"),
                "source": row.get("source"),
                "tags": row.get("tags"),
                "title": row.get("title"),
                "url": row.get("url"),
                "excerpt": shorten(row.get("excerpt"), 160),
            }
            for row in filtered
        ]
        edited = st.data_editor(
            display_rows,
            hide_index=True,
            use_container_width=True,
            column_config={
                "선택": st.column_config.CheckboxColumn("선택"),
                "url": st.column_config.LinkColumn("URL"),
                "excerpt": st.column_config.TextColumn("요약", width="large"),
            },
            disabled=["id", "score", "risk", "source", "tags", "title", "url", "excerpt"],
            key="resource_selector",
        )
        edited_rows = records(edited)
        selected_visible = {row["id"] for row in edited_rows if row.get("선택")}
        preserved_hidden = set(st.session_state.selected_ids) - visible_ids
        st.session_state.selected_ids = list(preserved_hidden | selected_visible)
        selected = selected_resources()

        b1, b2, b3 = st.columns([1, 1, 2])
        if b1.button("상위 20개 선택", use_container_width=True):
            st.session_state.selected_ids = [row["id"] for row in filtered[:20]]
            st.rerun()
        if b2.button("선택 초기화", use_container_width=True):
            st.session_state.selected_ids = []
            st.rerun()
        b3.caption(f"현재 선택: {len(selected)}건")

        if selected:
            st.markdown("#### 선택된 리소스")
            st.dataframe(
                [
                    {
                        "source": row.get("source"),
                        "tags": row.get("tags"),
                        "score": row.get("trader_score"),
                        "title": row.get("title"),
                        "url": row.get("url"),
                    }
                    for row in selected
                ],
                hide_index=True,
                use_container_width=True,
            )


with tabs[2]:
    st.subheader("AI 트레이더 브리핑")
    if not selected:
        st.info("브리핑에 사용할 리소스를 먼저 선택하세요.")
    else:
        briefing_type = "weekly" if briefing_type_label == "주간 방향" else "daily"
        run_brief = st.button("선택 리소스로 브리핑 생성", type="primary", use_container_width=True)
        if run_brief:
            refresh_market_if_incomplete("브리핑 생성 전")
            with st.spinner("선택 리소스의 원문 전체를 취합하는 중입니다. 선택 수가 많으면 시간이 걸릴 수 있습니다."):
                enriched, enrich_logs = enrich_material(selected, auto_fetch_body)
                st.session_state.enriched_resources = enriched
            if enrich_logs:
                with st.expander("본문 취합 로그", expanded=False):
                    for log in enrich_logs:
                        st.write(f"- {log}")
            config = provider_config(provider_label, temperature)
            with st.spinner("추론 엔진이 원문별 근거, BTC 기준축, 시나리오, 무효화 조건을 생성하는 중입니다."):
                brief, error = generate_trader_brief(enriched, st.session_state.market_snapshot, briefing_type, tone, config)
            if error:
                st.error(error)
            else:
                st.session_state.brief = brief
                st.session_state.content_package = {}
                st.success("브리핑 생성 완료")

        render_brief(st.session_state.brief)
        if st.session_state.brief:
            md = markdown_brief(st.session_state.brief)
            d1, d2 = st.columns(2)
            d1.download_button("브리핑 Markdown 다운로드", md, file_name="crypto_trader_briefing.md", mime="text/markdown", use_container_width=True)
            d2.download_button(
                "브리핑 JSON 다운로드",
                json.dumps(st.session_state.brief, ensure_ascii=False, indent=2),
                file_name="crypto_trader_briefing.json",
                mime="application/json",
                use_container_width=True,
            )


with tabs[3]:
    st.subheader("카드뉴스 및 Note 분리")
    brief = st.session_state.brief
    if not brief:
        st.info("AI 브리핑을 먼저 생성하세요.")
    else:
        make_content = st.button("카드뉴스/Note 생성", type="primary", use_container_width=True)
        if make_content:
            resources_for_content = st.session_state.enriched_resources or selected
            config = provider_config(provider_label, temperature)
            config["brand_outro"] = {
                "brand_name": DEFAULT_BRAND_OUTRO["brand_name"],
                "cta": brand_cta.strip() or DEFAULT_BRAND_OUTRO["cta"],
                "account": brand_account.strip(),
            }
            st.session_state.content_package = generate_content_package(brief, resources_for_content, custom_card_count, config, output_locale)
            st.success("카드뉴스/Note 생성 완료")
        render_cards(st.session_state.content_package)
        if st.session_state.content_package:
            excel_bytes = build_excel_bytes(
                brief,
                st.session_state.content_package,
                st.session_state.enriched_resources or selected,
                st.session_state.market_snapshot,
            )
            st.download_button(
                "Excel 패키지 다운로드",
                excel_bytes,
                file_name=f"crypto_briefing_package_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )


with tabs[4]:
    st.subheader("운영 구조")
    st.markdown(
        """
```text
Sources
  -> RSS / public list / community subject
  -> normalized ResourceItem
  -> multi-select resource bundle
  -> fetch every selected article body
  -> per-source evidence and trader interpretation
  -> market snapshot: BTC, alts, Nikkei, gold, Nasdaq, DXY, rates, sentiment
  -> derived levels: support/resistance, MA, RSI, MACD, Bollinger, ATR, funding, OI
  -> Bitcoin-first professional reasoning lens
  -> weekly/daily research briefing
  -> price-level scenarios, invalidation, action checklist
  -> card news 5/6/7/custom + Note
  -> Markdown, JSON, Excel package
```
        """
    )
    st.markdown("#### 환경 변수")
    st.code(
        """OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
FREE_AI_API_BASE=https://example.com/v1
FREE_AI_MODEL=free-reasoning-model
FREE_AI_API_KEY=...
""",
        language="bash",
    )
    st.markdown("#### 원칙")
    for item in [
        "선택된 기사/미디어 자료는 원문 전체 취합을 먼저 시도",
        "BTC를 기준축으로 놓고 알트는 후행 로테이션으로 판별",
        "시나리오마다 트리거와 무효화 조건을 포함",
        "매수/매도 단정 대신 조건부 시나리오로 작성",
        "커뮤니티 글은 과열/공포 감지용으로만 사용",
        "공식 발표와 거래소 공지 확인 전 루머로 분리",
        "카드뉴스는 출처 힌트와 리스크 문구를 포함",
    ]:
        st.write(f"- {item}")
