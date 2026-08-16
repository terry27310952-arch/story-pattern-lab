from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "streamlit"))

import story_content_pipeline_v3  # noqa: E402
import story_hook_engine  # noqa: E402
import story_llm_runtime  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class StoryOllamaDefaultTest(unittest.TestCase):
    def test_story_llm_defaults_to_local_ollama_qwen(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = story_llm_runtime.default_story_llm_config()
        self.assertEqual(config["provider"], "ollama")
        self.assertEqual(config["base_url"], "http://localhost:11434")
        self.assertEqual(config["model"], "qwen3:4b")

    def test_ollama_health_check_confirms_installed_default_model(self) -> None:
        payload = {"models": [{"name": "qwen3:4b"}, {"name": "nomic-embed-text:latest"}]}
        with patch.object(story_llm_runtime, "urlopen", return_value=_FakeResponse(payload)) as mocked:
            status = story_llm_runtime.check_ollama("http://localhost:11434", "qwen3:4b")
        self.assertTrue(status["reachable"])
        self.assertTrue(status["model_available"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/tags")

    def test_hook_engine_uses_ollama_chat_endpoint(self) -> None:
        model_output = {
            "candidates": [
                {"headline": "採掘会社が、AIを動かし始めた。", "subline": "収益の前提そのものが変わる。", "angle": "転換"}
            ]
        }
        fake = {"message": {"content": json.dumps(model_output, ensure_ascii=False)}}
        config = story_llm_runtime.default_story_llm_config(temperature=0.4)
        with patch.object(story_hook_engine, "_post_json", return_value=fake) as mocked:
            parsed, warning = story_hook_engine._call_hook_model(config, {"EVIDENCE": ["事業をAI向けへ転換した。"]})
        self.assertIsNone(warning)
        self.assertEqual(parsed, model_output)
        url, payload, headers = mocked.call_args.args[:3]
        self.assertEqual(url, "http://localhost:11434/api/chat")
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertFalse(payload["stream"])
        self.assertEqual(headers, {})

    def test_generic_card_model_uses_same_ollama_transport(self) -> None:
        model_output = {
            "cards": [
                {"role": "change", "headline": "前提が変わった。", "body": "事業の軸が別の収益源へ移り始めた。"}
            ]
        }
        fake = {"message": {"content": json.dumps(model_output, ensure_ascii=False)}}
        config = story_llm_runtime.default_story_llm_config(temperature=0.35)
        hero = {"entities": ["NeoGrid"], "headline_ja": "NeoGridの転換"}
        pack = {"facts": [{"fact_type": "change", "text": "NeoGridは事業を転換した。", "source_id": "a"}]}
        with patch.object(story_content_pipeline_v3, "_post_json", return_value=fake) as mocked:
            parsed, warning = story_content_pipeline_v3._call_model(config, hero, ["change"], pack)
        self.assertIsNone(warning)
        self.assertEqual(parsed, model_output)
        url, payload, headers = mocked.call_args.args[:3]
        self.assertEqual(url, "http://localhost:11434/api/chat")
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertFalse(payload["stream"])
        self.assertEqual(headers, {})

    def test_runtime_entrypoint_declares_ollama_as_story_default(self) -> None:
        source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('st.session_state["provider_story"] = "Ollama 로컬 추론 모델"', source)
        self.assertIn("story_llm_runtime.check_ollama", source)
        self.assertIn("Ollama에 연결할 수 없습니다", source)
        self.assertNotIn("Story LLM이 아직 설정되지 않았습니다", source)


if __name__ == "__main__":
    unittest.main()
