from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StoryProviderCloudV106Test(unittest.TestCase):
    def test_story_ui_defaults_to_ollama_cloud_not_deterministic(self) -> None:
        entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('STORY_PROVIDER_CLOUD = "Ollama Cloud · 기본 추론 모델"', entry)
        self.assertIn("STORY_PROVIDER_OPTIONS = [\n    STORY_PROVIDER_CLOUD,", entry)
        self.assertIn('migration_key = "_story_provider_cloud_default_v106"', entry)
        self.assertIn('st.session_state["provider_story"] = STORY_PROVIDER_CLOUD', entry)

    def test_cloud_config_cannot_be_overridden_by_stale_localhost_session(self) -> None:
        entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        cloud_block = entry.split("def _cloud_story_llm", 1)[1].split("def _local_story_llm", 1)[0]
        self.assertIn('OLLAMA_CLOUD_BASE_URL', cloud_block)
        self.assertIn('OLLAMA_CLOUD_MODEL', cloud_block)
        self.assertNotIn('st.session_state.get("ollama_base_url")', cloud_block)
        self.assertNotIn('_secret_or_env("OLLAMA_BASE_URL"', cloud_block)

    def test_deterministic_fallback_is_not_auto_promoted_to_ollama(self) -> None:
        entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        generate_block = entry.split("def _generate_story_llm_first", 1)[1].split(
            "story_content_pipeline_v5.generate_story_package = _generate_story_llm_first", 1
        )[0]
        self.assertIn("if incoming_provider == story_content_pipeline_v5.PROVIDER_OLLAMA:", generate_block)
        self.assertNotIn(
            "incoming_provider in {story_content_pipeline_v5.PROVIDER_LOCAL, story_content_pipeline_v5.PROVIDER_OLLAMA}",
            generate_block,
        )
        self.assertIn('quality["story_llm_default"] = "deterministic_fallback"', generate_block)

    def test_cloud_generic_card_model_uses_authenticated_native_ollama_api(self) -> None:
        entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        block = entry.split("def _call_story_model_with_cloud_auth", 1)[1].split(
            "story_content_pipeline_legacy._call_model = _call_story_model_with_cloud_auth", 1
        )[0]
        self.assertIn('story_llm_runtime.ollama_api_url(base, "chat")', block)
        self.assertIn("story_llm_runtime.ollama_headers", block)
        self.assertNotIn('"format": "json"', block)

    def test_story_provider_widget_exposes_cloud_and_preserves_local_and_fallback(self) -> None:
        entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('STORY_PROVIDER_FALLBACK = "내장 규칙 기반 · deterministic fallback"', entry)
        self.assertIn('STORY_PROVIDER_LOCAL = "Ollama 로컬 추론 모델"', entry)
        self.assertIn('kwargs.get("key") == "provider_story"', entry)
        self.assertIn("return _original_sidebar_selectbox(label, STORY_PROVIDER_OPTIONS", entry)


if __name__ == "__main__":
    unittest.main()
