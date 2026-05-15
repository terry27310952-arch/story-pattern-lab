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


def safe_quality(script: str, cached_quality: dict | None = None) -> dict:
    if cached_quality:
        return cached_quality
    if quality_check_live_script and script:
        return quality_check_live_script(script)
    return {}


def run_improvement_once(
    selected_key: str,
    selected_row: dict,
    script: str,
    quality: dict,
    source_text: str,
    analysis: dict,
    blueprint: dict,
    model: str,
    temperature: float,
    mode: str,
) -> tuple[str, dict, str | None]:
    if not improve_failed_script:
        return script, quality, "script_improver.py를 불러오지 못했습니다."
    if not quality and quality_check_live_script:
        quality = quality_check_live_script(script)
    improved, error = improve_failed_script(
        source_text=source_text,
        analysis=analysis,
        blueprint=blueprint,
        current_script=script,
        quality=quality,
        row=selected_row,
        model=model,
        temperature=temperature,
        improvement_mode=mode,
    )
    if error:
        return script, quality, error
    new_quality = quality_check_live_script(improved) if quality_check_live_script else {}
    st.session_state.longform_scripts[selected_key] = improved
    st.session_state.quality_checks[selected_key] = new_quality
    return improved, new_quality, None


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
quality = safe_quality(script, quality_checks.get(selected_key, {}))
source_text = source_texts.get(selected_key, "")
analysis = story_analyses.get(selected_key, {})
blueprint = live_blueprints.get(selected_key, {})

with st.sidebar:
    st.header("개선 설정")
    model = st.text_input("모델", value=st.session_state.get("llm_model", "gpt-4o-mini"))
    temperature = st.slider("재작성 창의성", 0.3, 1.1, float(st.session_state.get("temperature", 0.78)), 0.05)
    max_rounds = st.slider("자동 개선 최대 회차", 1, 3, 2, 1)
    auto_stop = st.checkbox("통과하면 자동 중단", value=True)
    st.session_state.llm_model = model
    st.session_state.temperature = temperature

cols = st.columns(6)
cols[0].metric("현재 점수", quality.get("overall_score", "N/A") if quality else "N/A")
cols[1].metric("등급", quality.get("grade", "N/A") if quality else "N/A")
cols[2].metric("통과", "YES" if quality.get("passed") else "NO")
cols[3].metric("대본 길이", len(script or ""))
cols[4].metric("본문 길이", len(source_text or ""))
cols[5].metric("치명 실패", len(quality.get("critical_failures", [])) if quality else "N/A")

if not quality:
    st.warning("품질검사 결과가 없습니다. 먼저 아래에서 검사하거나 라이브 제작실에서 품질검사를 실행하세요.")
    if st.button("현재 대본 품질검사", disabled=quality_check_live_script is None, use_container_width=True):
        quality = quality_check_live_script(script)
        st.session_state.quality_checks[selected_key] = quality
        st.rerun()
else:
    status = "통과" if quality.get("passed") else "개선 필요"
    if quality.get("passed"):
        st.success(f"현재 대본은 품질검사를 통과했습니다. 등급: {quality.get('grade')}")
    else:
        st.warning(f"현재 대본은 품질검사를 통과하지 못했습니다. 등급: {quality.get('grade')}, 점수: {quality.get('overall_score')}")

    with st.expander("품질검사 리포트", expanded=True):
        score_cols = st.columns(4)
        for idx, (name, value) in enumerate((quality.get("scores") or {}).items()):
            score_cols[idx % 4].metric(name, value)
        if quality.get("critical_failures"):
            st.error("\n".join(f"- {item}" for item in quality.get("critical_failures", [])))
        if quality.get("warnings"):
            st.warning("\n".join(f"- {item}" for item in quality.get("warnings", [])))
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

run_col1, run_col2 = st.columns(2)

if run_col1.button("1회 개선하기", type="primary", disabled=improve_failed_script is None or not bool(script), use_container_width=True):
    with st.spinner("품질검사 리포트를 반영해 1회 개선 중..."):
        improved, new_quality, error = run_improvement_once(
            selected_key=selected_key,
            selected_row=selected_row,
            script=script,
            quality=quality,
            source_text=source_text,
            analysis=analysis,
            blueprint=blueprint,
            model=model,
            temperature=temperature,
            mode=mode,
        )
    if error:
        st.error(error)
    else:
        st.success(f"1회 개선 완료. 새 점수: {new_quality.get('overall_score', 'N/A')} / 통과: {'YES' if new_quality.get('passed') else 'NO'}")
        st.rerun()

if run_col2.button("통과할 때까지 자동 개선", disabled=improve_failed_script is None or not bool(script), use_container_width=True):
    current_script = script
    current_quality = quality
    logs: list[str] = []
    with st.spinner("품질검사 통과를 목표로 자동 개선 중..."):
        for round_idx in range(1, max_rounds + 1):
            current_script, current_quality, error = run_improvement_once(
                selected_key=selected_key,
                selected_row=selected_row,
                script=current_script,
                quality=current_quality,
                source_text=source_text,
                analysis=analysis,
                blueprint=blueprint,
                model=model,
                temperature=temperature,
                mode=mode,
            )
            if error:
                logs.append(f"{round_idx}회차 실패: {error}")
                break
            logs.append(f"{round_idx}회차 완료: 점수 {current_quality.get('overall_score', 'N/A')} / 통과 {'YES' if current_quality.get('passed') else 'NO'}")
            if auto_stop and current_quality.get("passed"):
                break
    st.session_state.improvement_logs = logs
    st.rerun()

if st.session_state.get("improvement_logs"):
    with st.expander("자동 개선 로그", expanded=True):
        for item in st.session_state.improvement_logs:
            st.write(f"- {item}")

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
