from __future__ import annotations

import hashlib
import json
from datetime import datetime


CARD_MARKDOWN_LABELS = {
    "5장 Markdown 다운로드",
    "6장 Markdown 다운로드",
    "7장 Markdown 다운로드",
    "자율제안 Markdown 다운로드",
}
RUNTIME_VERSION = "card-download-v4.3"


def _package_signature(package: dict) -> str:
    payload = json.dumps(package or {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _excel_payload(st):
    import excel_exporter

    package = st.session_state.get("content_package") or {}
    brief = st.session_state.get("brief") or {}
    if not package or not brief:
        return None

    signature = _package_signature(package)
    cache_signature = st.session_state.get("_excel_with_previews_signature")
    cache_payload = st.session_state.get("_excel_with_previews_payload")
    if cache_signature == signature and cache_payload:
        return cache_payload

    resources = st.session_state.get("enriched_resources") or st.session_state.get("resources") or []
    market_snapshot = st.session_state.get("market_snapshot") or {}
    payload = excel_exporter.build_excel_bytes(brief, package, resources, market_snapshot)
    st.session_state._excel_with_previews_signature = signature
    st.session_state._excel_with_previews_payload = payload
    return payload


def apply_card_download_patch() -> None:
    """Place an Excel-with-previews button directly under every card-set Markdown button.

    app.py originally renders its global Excel button after render_cards(), which can be
    below the visible fold. This wrapper makes the export affordance explicit inside
    each 5/6/7/custom card tab while reusing the same verified Excel exporter.
    """
    import streamlit as st

    current = getattr(st, "_kiyosaki_card_download_runtime_version", None)
    if current == RUNTIME_VERSION:
        return

    original = getattr(st, "_kiyosaki_original_download_button", None)
    if original is None:
        original = st.download_button
        st._kiyosaki_original_download_button = original

    def download_button(label, data=None, *args, **kwargs):
        result = original(label, data, *args, **kwargs)
        if str(label) in CARD_MARKDOWN_LABELS:
            try:
                payload = _excel_payload(st)
                if payload:
                    original(
                        "Excel 패키지 + 카드 미리보기 이미지 다운로드",
                        payload,
                        file_name=f"crypto_briefing_package_with_previews_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key=f"excel-with-previews-{str(label)}",
                    )
                    st.caption("Excel 첫 시트 Card_Previews에 현재 카드 렌더러의 미리보기 PNG가 직접 삽입됩니다.")
            except Exception as exc:
                st.error(f"Excel 패키지 생성 실패: {exc}")
        return result

    st.download_button = download_button
    st._kiyosaki_card_download_runtime_version = RUNTIME_VERSION
