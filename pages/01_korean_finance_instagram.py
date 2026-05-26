from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="국내 경제 인스타 레퍼런스", page_icon="IG", layout="wide")

DATA_PATH = Path(__file__).resolve().parents[1] / "references" / "korean_finance_instagram.json"

st.title("국내 경제 인스타 레퍼런스")
st.write("자동 수집 대상이 아니라 카드뉴스, 릴스, 썸네일, 후킹 문장 검수용 포맷 레퍼런스입니다.")

with DATA_PATH.open("r", encoding="utf-8") as file:
    sources = json.load(file)

df = pd.DataFrame(sources)

metric_cols = st.columns(3)
metric_cols[0].metric("레퍼런스 계정", len(df))
metric_cols[1].metric("카테고리", df["category"].nunique())
metric_cols[2].metric("운영 방식", "수동 검증")

st.divider()

selected_categories = st.multiselect(
    "카테고리 필터",
    sorted(df["category"].unique()),
    default=sorted(df["category"].unique()),
)
filtered = df[df["category"].isin(selected_categories)].copy()

st.dataframe(
    filtered[["category", "handle", "name", "use", "url"]],
    use_container_width=True,
    hide_index=True,
)

st.divider()

for category, group in filtered.groupby("category", sort=True):
    st.subheader(category)
    cols = st.columns(3)
    for index, (_, source) in enumerate(group.iterrows()):
        with cols[index % 3]:
            with st.container(border=True):
                st.markdown(f"**{source['name']}**")
                st.caption(source["handle"])
                st.write(source["use"])
                st.link_button("계정 열기", source["url"], use_container_width=True)
