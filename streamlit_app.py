from __future__ import annotations

import runpy
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent / "apps" / "streamlit"
APP_FILE = APP_DIR / "app.py"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

runpy.run_path(str(APP_FILE), run_name="__main__")

# Main-app quick access panel. The full workflow also exists as a separate
# Streamlit page at apps/streamlit/pages/2_quality_improver.py, but this panel
# makes the feature visible directly after the production flow.
try:
    from quality_check import quality_check_live_script
    from script_improver import generate_directed_addition, improve_failed_script, merge_addition
except Exception:
    quality_check_live_script = None
    generate_directed_addition = None
    improve_failed_script = None
    merge_addition = None


def _package_key(row: dict) -> str:
    return row.get("url", row.get("id", row.get("title", "")))


longform_scripts = st.session_state.get("longform_scripts", {})
if longform_scripts:
    st.divider()
    st.markdown("## 🛠️ 품질개선 퀵패널")
    st.caption("품질검사를 통과하지 못했을 때, 여기서 바로 PD 디렉션을 넣어 전면 개선하거나 필요한 구간만 추가 생성할 수 있습니다.")

    keys = list(longform_scripts.keys())
    rows = st.session_state.get("rows", [])

    def _label(key: str) -> str:
        row = next((item for item in rows if _package_key(item) == key), None)
        if row:
            return f"{row.get('title', '제목 없음')[:70]} | {row.get('source', '')}"
        return key[:90]

    selected_key = st.selectbox("퀵패널 대상 대본", keys, format_func=_label, key="quick_improve_selected_key")
    selected_row = next((item for item in rows if _package_key(item) == selected_key), {"title": selected_key, "url": selected_key, "source": "manual"})
    script = st.session_state.longform_scripts.get(selected_key, "")
    quality = st.session_state.get("quality_checks", {}).get(selected_key, {})

    if not quality and quality_check_live_script and script:
        quality = quality_check_live_script(script)
        st.session_state.setdefault("quality_checks", {})[selected_key] = quality

    q_cols = st.columns(5)
    q_cols[0].metric("현재 점수", quality.get("overall_score", "N/A") if quality else "N/A")
    q_cols[1].metric("등급", quality.get("grade", "N/A") if quality else "N/A")
    q_cols[2].metric("통과", "YES" if quality.get("passed") else "NO")
    q_cols[3].metric("대본 길이", len(script or ""))
    q_cols[4].metric("치명 실패", len(quality.get("critical_failures", [])) if quality else "N/A")

    if quality and not quality.get("passed"):
        st.warning("품질검사를 통과하지 못했습니다. 아래 디렉션으로 개선하거나 추가 블록을 생성하세요.")
    elif quality and quality.get("passed"):
        st.success("현재 대본은 품질검사를 통과했습니다. 그래도 추가 보강은 가능합니다.")

    with st.expander("품질검사 상세", expanded=False):
        st.json(quality or {})

    user_direction = st.text_area(
        "PD 디렉션",
        value=st.session_state.get("quick_user_direction", ""),
        height=130,
        placeholder="예: 오프닝을 더 세게. 갈등을 3초 안에 박고, 상담 파트는 실제로 보낼 문장과 상대 반응별 대응까지 넣어줘.",
        key="quick_user_direction",
    )

    mode = st.selectbox(
        "개선 모드",
        [
            "사용자 디렉션 최우선 전면 재작성",
            "품질검사 기준 통과용 전면 재작성",
            "후킹/라이브감 집중 개선",
            "상담 디테일 집중 개선",
            "캐릭터성/사주점성술 화자성 집중 개선",
            "로컬라이징/민감표현 집중 개선",
        ],
        key="quick_improve_mode",
    )

    c1, c2 = st.columns(2)
    if c1.button("디렉션 반영해서 전면 개선", disabled=not bool(script) or improve_failed_script is None, use_container_width=True):
        with st.spinner("PD 디렉션과 품질검사 리포트를 반영해 대본 전면 개선 중..."):
            improved, error = improve_failed_script(
                source_text=st.session_state.get("source_texts", {}).get(selected_key, ""),
                analysis=st.session_state.get("story_analyses", {}).get(selected_key, {}),
                blueprint=st.session_state.get("live_blueprints", {}).get(selected_key, {}),
                current_script=script,
                quality=quality or {},
                row=selected_row,
                model=st.session_state.get("llm_model", "gpt-4o-mini"),
                temperature=float(st.session_state.get("temperature", 0.78)),
                improvement_mode=mode,
                user_direction=user_direction,
            )
        if error:
            st.error(error)
        else:
            st.session_state.longform_scripts[selected_key] = improved
            if quality_check_live_script:
                st.session_state.setdefault("quality_checks", {})[selected_key] = quality_check_live_script(improved)
            st.success("전면 개선 완료. 품질검사 결과를 업데이트했습니다.")
            st.rerun()

    target_section = c2.selectbox(
        "추가 생성 구간",
        ["부족한 구간 자동 판단", "00:00 오프닝 보강", "02:50 채팅 반응 보강", "05:50 사주/점성술 해석 보강", "06:50 상담 디테일 보강", "09:00 최종 판단 보강"],
        key="quick_target_section",
    )
    target_length = st.selectbox("추가 분량", ["800~1,200자", "1,500~2,500자", "2,500~3,500자"], index=1, key="quick_target_length")

    if st.button("내 디렉션으로 추가 생성해서 대본 뒤에 붙이기", disabled=not bool(script) or not bool(user_direction.strip()) or generate_directed_addition is None, use_container_width=True):
        with st.spinner("PD 디렉션 기반 추가 블록 생성 중..."):
            addition, error = generate_directed_addition(
                source_text=st.session_state.get("source_texts", {}).get(selected_key, ""),
                analysis=st.session_state.get("story_analyses", {}).get(selected_key, {}),
                blueprint=st.session_state.get("live_blueprints", {}).get(selected_key, {}),
                current_script=script,
                quality=quality or {},
                row=selected_row,
                model=st.session_state.get("llm_model", "gpt-4o-mini"),
                temperature=float(st.session_state.get("temperature", 0.78)),
                user_direction=user_direction,
                target_section=target_section,
                target_length=target_length,
            )
        if error:
            st.error(error)
        else:
            merged = merge_addition(script, addition, "append") if merge_addition else script.strip() + "\n\n" + addition.strip()
            st.session_state.longform_scripts[selected_key] = merged
            st.session_state.last_addition = addition
            if quality_check_live_script:
                st.session_state.setdefault("quality_checks", {})[selected_key] = quality_check_live_script(merged)
            st.success("추가 블록을 대본 뒤에 붙이고 품질검사를 다시 실행했습니다.")
            st.rerun()

    if st.session_state.get("last_addition"):
        with st.expander("마지막 추가 생성 블록", expanded=False):
            st.text_area("추가 생성 블록", st.session_state.last_addition, height=260)
