from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="핵심 레퍼런스", page_icon="TR", layout="wide")

DATA_PATH = Path(__file__).resolve().parents[1] / "references" / "core_references.json"

st.title("핵심 레퍼런스")
st.write("트렌드 감지와 소재 발굴에서 우선 확인해야 할 기준점입니다.")

if not DATA_PATH.exists():
    st.error("핵심 레퍼런스 데이터 파일을 찾을 수 없습니다.")
    st.stop()

with DATA_PATH.open("r", encoding="utf-8") as file:
    sources = json.load(file)

df = pd.DataFrame(sources)

metric_cols = st.columns(3)
metric_cols[0].metric("핵심 레퍼런스", len(df))
metric_cols[1].metric("최상위 티어", int((df["tier"] == "core").sum()))
metric_cols[2].metric("운영 상태", ", ".join(sorted(df["status"].unique())))

st.divider()

st.dataframe(
    df[["tier_label", "category", "source_type", "name", "url", "role", "status"]],
    use_container_width=True,
    hide_index=True,
)

st.divider()

for _, source in df.iterrows():
    with st.container(border=True):
        header_cols = st.columns([2, 1])
        with header_cols[0]:
            st.subheader(source["name"])
            st.caption(f"{source['tier_label']} · {source['category']} · {source['source_type']}")
            st.write(source["role"])
        with header_cols[1]:
            st.link_button("사이트 열기", source["url"], use_container_width=True)

        st.markdown("**수집 기준**")
        st.write(source["collection_policy"])

        st.markdown("**확인할 신호**")
        for signal in source["signals"]:
            st.write(f"- {signal}")

        if source["status"] == "접근 확인 필요":
            st.warning(source["notes"])
