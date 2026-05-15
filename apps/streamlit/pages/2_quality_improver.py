from __future__ import annotations

import json

import streamlit as st

try:
    from script_improver import build_rewrite_brief, improve_failed_script
except Exception as error:
    build_rewrite_brief = None
    improve_failed_script = None
    IMPORT_ERROR = str(error)
else:
    IMPORT_ERROR = None

try:
    from quality_check import quality_check_live_script
except Exception:
    quality_check_live_script = None


def package_key(row: dict) -> str:
    return row.get("url", row.get("id", row.get("title", "")))


st.set_page_config(page_title="품질개선", page_icon="🛠️", layout="wide")
st.title("품질개선 워크벤치")
st.caption("품질검사에서 탈락한 10분 롱폼을 실패 리포트 기반으로 재작성합니다.")

if IMPORT_ERROR:
    st.error(f"script_improver.py 로드 실패: {IMPORT_ERROR}")
    st.stop()

rows = st.session_state.get("rows", [])
longform_scripts = st.session_state.get("longform_scripts", {})
quality_checks = st.session_state.get("quality_checks", {})
source_texts = st.session_state.get("source_texts", {})
story_analyses = st.session_state.get("story_analyses", {})
live_blueprints = st.session_state.get("live_blueprints", {})

if not longform_scripts:
    st.info("아직 개선할 롱폼 대본이 없습니다. 먼저 라이브 제작실에서 10분 대본을 생성하세요.")
    st.stop()

options = list(longform_scripts.keys())

def label_for_key(key: str) -> str:
    row = next((item for item in rows if package_key(item) == key), None)
    if row:
        return f"{row.get('title', '제목 없음')[:70]} | {row.get('source', '')}"
    return key[:90]

selected_key = st.selectbox("개선할 대본", options=options, format_func=label_for_key)
selected_row = next((item for item in rows if package_key(item) == selected_key), {"title": selected_key, "url": selected_key, "source": "manual"})

script = longform_scripts.get(selected_key, "")
quality = quality_checks.get(selected_key, {})
source_text = source_texts.get(selected_key, "")
analysis = story_analyses.get(selected_key, {})
blueprint = live_blueprints.get(selected_key, {})

cols = st.columns(5)
cols[0].metric("현재 점수", quality.get("overall_score", "N/A") if quality else "N/A")
cols[1].metric("등급", quality.get("grade", "N/A") if quality else "N/A")
cols[2].metric("통과", "YES" if quality.get("passed") else "NO")
cols[3].metric("대본 길이", len(script or ""))
cols[4].metric("본문 길이", len(source_text or ""))

if not quality:
    st.warning("품질검사 결과가 없습니다. 먼저 아래에서 검사하거나 라이브 제작실에서 품질검사를 실행하세요.")
    if st.button("현재 대본 품질검사", disabled=quality_check_live_script is None, use_container_width=True):
        quality = quality_check_live_script(script)
        st.session_state.quality_checks[selected_key] = quality
        st.rerun()
else:
    with st.expander("품질검사 리포트", expanded=True):
        st.json(quality)
    if build_rewrite_brief:
        st.text_area("재작성 브리프", build_rewrite_brief(quality), height=220)

mode = st.selectbox(
    "개선 모드",
    [
        "품질검사 기준 통과용 전면 재작성",
        "후킹/라이브감 집중 개선",
        "상담 디테일 집중 개선",
        "캐릭터성/사주점성술 화자성 집중 개선",
        "로컬라이징/민감표현 집중 개선",
    ],
)

st.markdown("### 현재 대본")
st.text_area("개선 전", script, height=380)

if st.button("품질 실패 항목 기반으로 개선하기", type="primary", disabled=improve_failed_script is None or not bool(script), use_container_width=True):
    with st.spinner("품질검사 리포트를 반영해 대본을 전면 개선 중..."):
        improved, error = improve_failed_script(
            source_text=source_text,
            analysis=analysis,
            blueprint=blueprint,
            current_script=script,
            quality=quality,
            row=selected_row,
            model=st.session_state.get("llm_model", "gpt-4o-mini"),
            temperature=0.78,
            improvement_mode=mode,
        )
    if error:
        st.error(error)
    else:
        st.session_state.longform_scripts[selected_key] = improved
        if quality_check_live_script:
            new_quality = quality_check_live_script(improved)
            st.session_state.quality_checks[selected_key] = new_quality
        st.success("개선 대본 생성 완료. 새 품질검사 결과로 업데이트했습니다.")
        st.rerun()

if selected_key in st.session_state.get("longform_scripts", {}):
    st.markdown("### 개선 후 / 현재 저장된 대본")
    st.text_area("현재 저장본", st.session_state.longform_scripts[selected_key], height=520)
    if selected_key in st.session_state.get("quality_checks", {}):
        st.markdown("### 최신 품질검사")
        st.json(st.session_state.quality_checks[selected_key])

st.download_button(
    "현재 대본 TXT 다운로드",
    st.session_state.longform_scripts.get(selected_key, ""),
    file_name="improved_live_script.txt",
    mime="text/plain",
    use_container_width=True,
)
