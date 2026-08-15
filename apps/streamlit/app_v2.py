from __future__ import annotations

import json
import os
import time
from datetime import datetime

import streamlit as st

import card_renderer
from content_modes import (
    MODE_LABELS,
    MODE_STORY,
    MODE_TRADER,
    default_sources,
    mode_policy,
    selection_score,
)
from market_data import collect_market_snapshot, flatten_market_rows, summarize_market
from mode_exporter import build_story_excel, build_trader_excel
from mode_resource_pipeline import available_public_registry, collect_for_mode
from resource_collector import RSS_SOURCES
from source_fetcher import fetch_article_body
from story_content_pipeline import (
    PROVIDER_LOCAL,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI_COMPATIBLE,
    generate_story_package,
)
from trader_pipeline import generate_trader_result


APP_VERSION = "2026-08-16 dual-pipeline-v10.2"
DISPLAY_BRAND_LABEL = "キヨサキ"
DEFAULT_CTA = "フォローして、勢力が入ったポイントを無料でチェック。"


st.set_page_config(page_title="Kiyosaki Editorial Lab", page_icon="₿", layout="wide")
st.markdown(
    """
<style>
.block-container { padding-top: 1.1rem; max-width: 1480px; }
.mode-banner { border:1px solid #31363a; border-radius:10px; padding:14px 16px; background:#101214; margin-bottom:14px; }
.mode-banner strong { color:#f69f19; }
.small-muted { color:#7f8992; font-size:0.88rem; }
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
        "market_snapshot": {},
        "resources_trader": [],
        "resources_story": [],
        "logs_trader": [],
        "logs_story": [],
        "selected_ids_trader": [],
        "selected_ids_story": [],
        "enriched_trader": [],
        "enriched_story": [],
        "trader_brief": {},
        "trader_package": {},
        "story_package": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def state_key(prefix: str, mode: str) -> str:
    return f"{prefix}_{mode}"


def records(data: object) -> list[dict]:
    if hasattr(data, "to_dict"):
        return data.to_dict("records")
    return list(data or [])


def shorten(value: object, length: int = 150) -> str:
    text = " ".join(str(value or "").split())
    return text[: length - 1] + "…" if len(text) > length else text


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


def enrich_material(rows: list[dict], enabled: bool) -> tuple[list[dict], list[str]]:
    enriched: list[dict] = []
    logs: list[str] = []
    for row in rows:
        next_row = dict(row)
        next_row["material"] = row.get("material") or row.get("excerpt") or ""
        if enabled and row.get("source_type") != "community" and row.get("url"):
            result = fetch_article_body(row.get("url", ""), row.get("source", ""), row.get("excerpt", ""))
            if getattr(result, "ok", False) and getattr(result, "body", ""):
                next_row["material"] = result.body
                next_row["fetch_method"] = result.method
                logs.append(f"{row.get('source')}: 본문 {result.length:,}자 취합")
            else:
                next_row["fetch_method"] = "excerpt_fallback"
                logs.append(f"{row.get('source')}: 요약문 fallback")
        else:
            next_row["fetch_method"] = "community_subject_only" if row.get("source_type") == "community" else "excerpt_only"
        enriched.append(next_row)
    return enriched, logs


def selected_resources(mode: str) -> list[dict]:
    rows = st.session_state.get(state_key("resources", mode), [])
    selected_ids = set(st.session_state.get(state_key("selected_ids", mode), []))
    return [row for row in rows if row.get("id") in selected_ids]


def cards_to_markdown(cards: list[dict]) -> str:
    lines: list[str] = []
    for card in cards:
        lines.append(f"## {card.get('slide')}. {card.get('headline', '')}")
        if card.get("eyebrow"):
            lines.append(str(card.get("eyebrow")))
        if card.get("subheadline"):
            lines.append(str(card.get("subheadline")))
        if card.get("key_message") and card.get("key_message") != card.get("subheadline"):
            lines.append(str(card.get("key_message")))
        source = card.get("source") or {}
        source_text = " · ".join(value for value in [source.get("publisher", ""), source.get("short_title", "")] if value)
        if source_text:
            lines.append(f"Source: {source_text}")
        lines.append("")
    return "\n".join(lines).strip()


def render_card_package(package: dict) -> None:
    sets = package.get("cards") or {}
    if not sets:
        st.info("생성된 카드가 없습니다.")
        return
    labels = list(sets.keys())
    tabs = st.tabs(labels)
    for label, tab in zip(labels, tabs):
        with tab:
            cards = [card for card in sets.get(label, []) if (card.get("qa") or {}).get("renderable", True)]
            for card in cards:
                st.markdown(f"#### {card.get('slide')}. {card.get('headline', '')}")
                col_image, col_copy = st.columns([1, 1.1])
                with col_image:
                    try:
                        st.image(card_renderer.render_card_png(card, width=540, height=675), width=430)
                    except Exception as error:
                        st.error(f"preview render failed: {error}")
                with col_copy:
                    if card.get("eyebrow"):
                        st.caption(card.get("eyebrow"))
                    if card.get("subheadline"):
                        st.write(card.get("subheadline"))
                    metrics = card.get("metrics") or []
                    if metrics:
                        for metric in metrics[:5]:
                            st.write(f"- {metric.get('label')}: {metric.get('value')}")
                    source = card.get("source") or {}
                    if source.get("publisher") or source.get("short_title"):
                        st.caption(" · ".join(v for v in [source.get("publisher"), source.get("short_title")] if v))
                    with st.expander("구조 / 근거", expanded=False):
                        st.json(
                            {
                                "card_type": card.get("card_type"),
                                "story_role": card.get("story_role"),
                                "story_tag": card.get("story_archetype"),
                                "evidence_refs": card.get("evidence_refs"),
                                "layout": (card.get("visual_direction") or {}).get("layout_variant"),
                                "scene_type": (card.get("visual_direction") or {}).get("scene_type"),
                                "character_required": (card.get("visual_direction") or {}).get("character_required"),
                            }
                        )
            st.download_button(
                f"{label} Markdown 다운로드",
                cards_to_markdown(cards),
                file_name=f"kiyosaki_{label}_cards.md",
                mime="text/markdown",
                use_container_width=True,
                key=f"md_download_{label}_{package.get('mode', 'trader')}",
            )


def render_trader_brief(brief: dict) -> None:
    if not brief:
        return
    st.markdown(f"### {brief.get('title', 'Trader Briefing')}")
    if brief.get("one_line"):
        st.info(brief.get("one_line"))
    stance = brief.get("trader_stance") or {}
    if stance:
        c1, c2, c3 = st.columns(3)
        c1.metric("방향 편향", stance.get("directional_bias", "N/A"))
        c2.metric("선호 포지션", stance.get("preferred_posture", "N/A"))
        c3.metric("확신도", stance.get("conviction_score", "N/A"))
        st.write(stance.get("market_read", ""))
    if brief.get("key_points"):
        with st.expander("핵심 포인트", expanded=True):
            for point in brief.get("key_points", []):
                st.write(f"- {point}")


def render_story_summary(package: dict) -> None:
    context = package.get("story_context") or {}
    hero = context.get("hero_story") or {}
    plan = context.get("story_plan") or {}
    graph = context.get("fact_graph") or {}
    quality = package.get("content_quality") or {}
    if not hero:
        return
    c1, c2, c3 = st.columns([2, 1, 1])
    c1.markdown(f"### {plan.get('headline_ja') or hero.get('headline_ja', '')}")
    c2.metric("Story Tag", plan.get("archetype_tag", "story_event"))
    c3.metric("Fact Nodes", len(graph.get("facts") or []))
    if plan.get("thesis"):
        st.write(plan.get("thesis"))
    st.caption(f"Story Score · {hero.get('story_score', 0)} · Graph · {quality.get('graph_engine', 'N/A')}")
    candidates = context.get("candidates") or []
    if candidates:
        with st.expander("스토리 후보 랭킹", expanded=False):
            st.dataframe(
                [
                    {
                        "story_score": item.get("story_score"),
                        "hero_score": item.get("hero_story_score"),
                        "topic": item.get("topic"),
                        "headline": item.get("headline_seed"),
                        "sources": ", ".join(item.get("source_names") or []),
                    }
                    for item in candidates[:10]
                ],
                hide_index=True,
                use_container_width=True,
            )


def render_market_snapshot(snapshot: dict) -> None:
    if not snapshot:
        st.caption("시장 데이터 없음")
        return
    summary = summarize_market(snapshot)
    cols = st.columns(4)
    cols[0].metric("BTC", summary.get("btc_price", "N/A"))
    cols[1].metric("Support", summary.get("btc_nearest_support", "N/A"))
    cols[2].metric("Resistance", summary.get("btc_nearest_resistance", "N/A"))
    cols[3].metric("RSI", summary.get("btc_rsi14", "N/A"))


init_state()

st.title("Kiyosaki Editorial Lab")
st.caption("트레이더 브리핑과 스토리텔링 콘텐츠를 서로 다른 입력·추론·카드 파이프라인으로 생성합니다.")

mode_labels = [MODE_LABELS[MODE_TRADER], MODE_LABELS[MODE_STORY]]
label_to_mode = {value: key for key, value in MODE_LABELS.items()}
mode_label = st.sidebar.radio("작업 모드", mode_labels, index=0, key="work_mode_label")
mode = label_to_mode[mode_label]
policy = mode_policy(mode)

st.sidebar.markdown(
    f"<div class='mode-banner'><strong>{MODE_LABELS[mode]}</strong><br><span class='small-muted'>{policy.description}</span></div>",
    unsafe_allow_html=True,
)

public_registry = available_public_registry(mode)
default_rss, default_public = default_sources(mode, RSS_SOURCES, public_registry)

st.sidebar.header("1. 리소스 수집")
selected_rss = st.sidebar.multiselect(
    "RSS / 미디어",
    options=list(RSS_SOURCES.keys()),
    default=default_rss,
    key=f"rss_sources_{mode}",
)
selected_public = st.sidebar.multiselect(
    "공개 목록 / 공식 소스",
    options=list(public_registry.keys()),
    default=default_public,
    key=f"public_sources_{mode}",
)
per_source_limit = st.sidebar.slider(
    "소스별 수집 수",
    5,
    60,
    min(60, policy.source_limit),
    5,
    key=f"source_limit_{mode}",
)
refresh_market_with_collection = st.sidebar.checkbox(
    "시장 데이터 함께 갱신",
    value=mode == MODE_TRADER,
    key=f"refresh_market_{mode}",
)
collect_button = st.sidebar.button(
    f"{MODE_LABELS[mode]}용 리소스 수집",
    type="primary",
    use_container_width=True,
    key=f"collect_{mode}",
)

st.sidebar.divider()
st.sidebar.header("2. 추론 엔진")
external_ready = bool(env_value("FREE_AI_API_BASE") and env_value("FREE_AI_MODEL"))
provider_options = [
    "내장 규칙 기반 · deterministic fallback",
    "Ollama 로컬 추론 모델",
    "OpenAI-compatible API · 외부 추론 모델",
]
provider_label = st.sidebar.selectbox(
    "AI 엔진",
    provider_options,
    index=2 if external_ready else 0,
    key=f"provider_{mode}",
)
temperature = st.sidebar.slider("추론 온도", 0.1, 0.9, 0.35, 0.05, key=f"temperature_{mode}")
if provider_label.startswith("Ollama"):
    st.sidebar.text_input("Ollama URL", value=env_value("OLLAMA_BASE_URL", "http://localhost:11434"), key="ollama_base_url")
    st.sidebar.text_input("Ollama 모델", value=env_value("OLLAMA_MODEL", "qwen3:4b"), key="ollama_model")
elif provider_label.startswith("OpenAI-compatible"):
    st.sidebar.text_input("API Base URL", value=env_value("FREE_AI_API_BASE", ""), key="free_ai_base_url")
    st.sidebar.text_input("모델", value=env_value("FREE_AI_MODEL", ""), key="free_ai_model")
    st.sidebar.text_input("API Key", value=env_value("FREE_AI_API_KEY", ""), type="password", key="free_ai_api_key")

auto_fetch_body = st.sidebar.checkbox("선택 리소스 원문 전체 취합", value=True, key=f"fetch_body_{mode}")
brand_account = st.sidebar.text_input("브랜드 계정 ID", value=env_value("BRAND_ACCOUNT", ""), key=f"brand_account_{mode}")
brand_cta = st.sidebar.text_area("브랜드 CTA", value=DEFAULT_CTA, height=70, key=f"brand_cta_{mode}")

if mode == MODE_TRADER:
    briefing_type_label = st.sidebar.radio("브리핑 타입", ["주간 방향", "일간 시간대"], horizontal=True, key="trader_brief_type")
    tone = st.sidebar.selectbox("문장 톤", ["트레이더 브리핑", "카드뉴스용 압축", "Note용 분석"], key="trader_tone")
    output_locale = st.sidebar.selectbox("카드 locale", ["ja-JP", "ko-KR"], index=0, key="trader_locale")
    custom_card_count = st.sidebar.slider("자율제안 분석 카드 수", 5, 7, 6, 1, key="trader_custom_count")
else:
    story_card_count = st.sidebar.slider("스토리 총 카드 수", 5, 8, 7, 1, key="story_card_count")
    st.sidebar.caption("마지막 1장은 고정 브랜드 아웃트로입니다. 나머지 전개는 Fact Graph와 Story Plan이 근거에 맞춰 동적으로 결정합니다.")

st.sidebar.divider()
st.sidebar.caption(f"App · {APP_VERSION}")
st.sidebar.caption(f"Mode · {mode}")
st.sidebar.caption("Brand · キヨサキ")

if collect_button:
    with st.spinner(f"{MODE_LABELS[mode]}에 맞는 리소스를 수집하는 중입니다."):
        rows, logs = collect_for_mode(mode, selected_rss, selected_public, per_source_limit)
    st.session_state[state_key("resources", mode)] = rows
    st.session_state[state_key("logs", mode)] = logs
    st.session_state[state_key("selected_ids", mode)] = [
        row.get("id") for row in rows[: policy.default_select_count] if row.get("id")
    ]
    st.session_state[state_key("enriched", mode)] = []
    if mode == MODE_TRADER:
        st.session_state.trader_brief = {}
        st.session_state.trader_package = {}
    else:
        st.session_state.story_package = {}
    if refresh_market_with_collection:
        with st.spinner("시장 데이터를 갱신하는 중입니다."):
            st.session_state.market_snapshot = collect_market_snapshot()

resources = st.session_state.get(state_key("resources", mode), [])
selected = selected_resources(mode)

m1, m2, m3, m4 = st.columns(4)
m1.metric("수집 리소스", len(resources))
m2.metric("선택 리소스", len(selected))
m3.metric("주 점수", policy.primary_score)
m4.metric("시장 데이터", len(flatten_market_rows(st.session_state.market_snapshot)) if st.session_state.market_snapshot else 0)

logs = st.session_state.get(state_key("logs", mode), [])
if logs:
    with st.expander("수집 로그", expanded=False):
        for log in logs:
            st.write(f"- {log}")

main_tabs = st.tabs(["리소스 선택", "생성", "결과", "구조"])

with main_tabs[0]:
    if not resources:
        st.info("왼쪽에서 현재 모드용 리소스를 먼저 수집하세요.")
    else:
        f1, f2, f3 = st.columns([2, 1, 1])
        query = f1.text_input("검색", "", key=f"query_{mode}")
        min_score = f2.slider("최소 점수", 0, 100, 0, 5, key=f"min_score_{mode}")
        archetype_filter: list[str] = []
        if mode == MODE_STORY:
            f3.caption("Story score 기준 · 구조는 생성 시 결정")
        else:
            f3.caption("Trader score 기준")

        filtered: list[dict] = []
        for row in resources:
            haystack = f"{row.get('title', '')} {row.get('source', '')} {row.get('tags', '')}".lower()
            if query and query.lower() not in haystack:
                continue
            if selection_score(mode, row) < min_score:
                continue
            filtered.append(row)

        selected_ids = set(st.session_state.get(state_key("selected_ids", mode), []))
        if mode == MODE_STORY:
            display_rows = [
                {
                    "선택": row.get("id") in selected_ids,
                    "id": row.get("id"),
                    "story": row.get("story_score"),
                    "trader": row.get("trader_score"),
                    "hook": row.get("story_hook_score"),
                    "change": row.get("change_score"),
                    "scale": row.get("scale_score"),
                    "evidence": row.get("evidence_story_score"),
                    "visual": row.get("visuality_score"),
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "url": row.get("url"),
                }
                for row in filtered
            ]
            disabled = ["id", "story", "trader", "hook", "change", "scale", "evidence", "visual", "source", "title", "url"]
        else:
            display_rows = [
                {
                    "선택": row.get("id") in selected_ids,
                    "id": row.get("id"),
                    "score": row.get("trader_score"),
                    "risk": row.get("risk_score"),
                    "source": row.get("source"),
                    "tags": row.get("tags"),
                    "title": row.get("title"),
                    "url": row.get("url"),
                }
                for row in filtered
            ]
            disabled = ["id", "score", "risk", "source", "tags", "title", "url"]

        edited = st.data_editor(
            display_rows,
            hide_index=True,
            use_container_width=True,
            disabled=disabled,
            column_config={
                "선택": st.column_config.CheckboxColumn("선택"),
                "url": st.column_config.LinkColumn("URL"),
            },
            key=f"resource_selector_{mode}",
        )
        edited_rows = records(edited)
        visible_ids = {row.get("id") for row in filtered if row.get("id")}
        selected_visible = {row.get("id") for row in edited_rows if row.get("선택") and row.get("id")}
        preserved_hidden = selected_ids - visible_ids
        st.session_state[state_key("selected_ids", mode)] = list(preserved_hidden | selected_visible)
        selected = selected_resources(mode)

        b1, b2, b3 = st.columns([1, 1, 2])
        if b1.button(f"상위 {policy.default_select_count}개 선택", use_container_width=True, key=f"top_select_{mode}"):
            st.session_state[state_key("selected_ids", mode)] = [row.get("id") for row in filtered[: policy.default_select_count] if row.get("id")]
            st.rerun()
        if b2.button("선택 초기화", use_container_width=True, key=f"clear_select_{mode}"):
            st.session_state[state_key("selected_ids", mode)] = []
            st.rerun()
        b3.caption(f"현재 선택: {len(selected)}건")

        if mode == MODE_STORY and filtered:
            with st.expander("왜 이 소재가 스토리 후보인가", expanded=False):
                st.dataframe(
                    [
                        {
                            "story_score": row.get("story_score"),
                            "hook": row.get("story_hook_score"),
                            "conflict": row.get("conflict_score"),
                            "change": row.get("change_score"),
                            "scale": row.get("scale_score"),
                            "evidence": row.get("evidence_story_score"),
                            "market_implication": row.get("market_implication_score"),
                            "visuality": row.get("visuality_score"),
                            "title": row.get("title"),
                        }
                        for row in filtered[:15]
                    ],
                    hide_index=True,
                    use_container_width=True,
                )

with main_tabs[1]:
    selected = selected_resources(mode)
    if not selected:
        st.info("사용할 리소스를 먼저 선택하세요.")
    elif mode == MODE_TRADER:
        st.subheader("트레이더 브리핑 생성")
        st.caption("이 경로만 시장 snapshot, 가격 레벨, 파생, 시나리오, 매매 조건을 생성합니다.")
        if st.button("트레이더 브리핑 + 카드 생성", type="primary", use_container_width=True, key="run_trader"):
            if not st.session_state.market_snapshot:
                with st.spinner("트레이더용 시장 데이터를 수집하는 중입니다."):
                    st.session_state.market_snapshot = collect_market_snapshot()
            with st.spinner("선택 기사 원문을 취합하는 중입니다."):
                enriched, enrich_logs = enrich_material(selected, auto_fetch_body)
                st.session_state.enriched_trader = enriched
            config = provider_config(provider_label, temperature)
            config["brand_outro"] = {
                "brand_name": DISPLAY_BRAND_LABEL,
                "cta": brand_cta.strip() or DEFAULT_CTA,
                "account": brand_account.strip(),
            }
            briefing_type = "weekly" if briefing_type_label == "주간 방향" else "daily"
            with st.spinner("트레이더 전용 추론 파이프라인 실행 중입니다."):
                result = generate_trader_result(
                    enriched,
                    st.session_state.market_snapshot,
                    briefing_type,
                    tone,
                    config,
                    output_locale,
                    custom_card_count,
                )
            if result.error:
                st.error(result.error)
            else:
                st.session_state.trader_brief = result.brief
                st.session_state.trader_package = result.content_package
                st.success("트레이더 브리핑 생성 완료")
            if enrich_logs:
                with st.expander("원문 취합 로그", expanded=False):
                    for log in enrich_logs:
                        st.write(f"- {log}")
        render_market_snapshot(st.session_state.market_snapshot)
    else:
        st.subheader("스토리텔링 콘텐츠 생성")
        st.caption("이 경로는 트레이더 브리핑을 만들지 않습니다. 선택된 원문을 Fact Graph로 구조화한 뒤 Story Plan을 동적으로 만듭니다.")
        if st.button("Hero Story + 카드뉴스 생성", type="primary", use_container_width=True, key="run_story"):
            with st.spinner("스토리 후보 원문을 취합하는 중입니다."):
                enriched, enrich_logs = enrich_material(selected, auto_fetch_body)
                st.session_state.enriched_story = enriched
            config = provider_config(provider_label, temperature)
            with st.spinner("스토리 점수 → 사건 클러스터 → Hero Story → Fact Graph → Story Plan → 카드 전개를 생성하는 중입니다."):
                result = generate_story_package(
                    enriched,
                    total_card_count=story_card_count,
                    config=config,
                    output_locale="ja-JP",
                    brand={"cta": brand_cta.strip() or DEFAULT_CTA, "account": brand_account.strip()},
                    generation_seed=str(time.time_ns()),
                )
            if result.error:
                st.error(result.error)
            else:
                st.session_state.story_package = result.package
                st.success("스토리텔링 카드뉴스 생성 완료")
                if result.model_warning:
                    st.warning(result.model_warning)
            if enrich_logs:
                with st.expander("원문 취합 로그", expanded=False):
                    for log in enrich_logs:
                        st.write(f"- {log}")

with main_tabs[2]:
    if mode == MODE_TRADER:
        brief = st.session_state.trader_brief
        package = st.session_state.trader_package
        if not package:
            st.info("트레이더 결과가 아직 없습니다.")
        else:
            st.subheader("트레이더 결과")
            render_trader_brief(brief)
            try:
                excel_bytes = build_trader_excel(
                    brief,
                    package,
                    st.session_state.enriched_trader or selected_resources(MODE_TRADER),
                    st.session_state.market_snapshot,
                )
                st.download_button(
                    "Excel + 카드 미리보기 이미지 다운로드",
                    excel_bytes,
                    file_name=f"kiyosaki_trader_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="download_trader_excel",
                )
            except Exception as error:
                st.error(f"Excel 생성 실패: {error}")
            st.download_button(
                "트레이더 JSON 다운로드",
                json.dumps({"brief": brief, "package": package}, ensure_ascii=False, indent=2, default=str),
                file_name="kiyosaki_trader.json",
                mime="application/json",
                use_container_width=True,
            )
            render_card_package(package)
    else:
        package = st.session_state.story_package
        if not package:
            st.info("스토리 결과가 아직 없습니다.")
        else:
            st.subheader("스토리텔링 결과")
            render_story_summary(package)
            try:
                excel_bytes = build_story_excel(package, st.session_state.enriched_story or selected_resources(MODE_STORY))
                st.download_button(
                    "Excel + 카드 미리보기 이미지 다운로드",
                    excel_bytes,
                    file_name=f"kiyosaki_story_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="download_story_excel",
                )
            except Exception as error:
                st.error(f"Excel 생성 실패: {error}")
            c1, c2 = st.columns(2)
            c1.download_button(
                "Story JSON 다운로드",
                json.dumps(package, ensure_ascii=False, indent=2, default=str),
                file_name="kiyosaki_story.json",
                mime="application/json",
                use_container_width=True,
            )
            c2.download_button(
                "Story Note 다운로드",
                package.get("note_markdown", ""),
                file_name="kiyosaki_story_note.md",
                mime="text/markdown",
                use_container_width=True,
            )
            render_card_package(package)

with main_tabs[3]:
    st.subheader("현재 실행 구조")
    st.code(
        """MODE SELECT
├─ TRADER
│  ├─ trader source preset
│  ├─ trader_score ranking
│  ├─ market snapshot required
│  ├─ generate_trader_brief()
│  ├─ build_trader_content_package()
│  └─ trader Excel + previews
│
└─ STORY
   ├─ story source preset + official policy sources
   ├─ generic story_score ranking
   ├─ full article enrichment + structural cleaner
   ├─ same-event clustering
   ├─ Hero Story selection
   ├─ Fact Graph (entity / relation / value / timeline)
   ├─ dynamic Story Plan / Card Plan
   ├─ archetype tag is assigned after planning
   ├─ evidence-bound copy + semantic visual scenes
   └─ story Excel + Story_Graph + Story_Plan + previews

IMPORTANT: STORY DOES NOT CALL generate_trader_brief() OR generate_content_package().
IMPORTANT: STORY PLAN IS NOT SELECTED BY A HARD-CODED ARTICLE OR ARCHETYPE TEMPLATE.
""",
        language="text",
    )
    st.write("트레이더와 스토리 상태도 각각 `trader_*`, `story_*`로 분리되어 서로 덮어쓰지 않습니다.")
