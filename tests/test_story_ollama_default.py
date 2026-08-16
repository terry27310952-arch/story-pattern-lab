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
    def test_story_llm_defaults_to_ollama_cloud(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = story_llm_runtime.default_story_llm_config()
        self.assertEqual(config["provider"], "ollama")
        self.assertEqual(config["base_url"], "https://ollama.com/api")
        self.assertEqual(config["model"], "gpt-oss:20b")
        self.assertTrue(config["ollama_cloud"])

    def test_cloud_health_check_requires_api_key_before_network(self) -> None:
        with patch.object(story_llm_runtime, "urlopen") as mocked:
            status = story_llm_runtime.check_ollama("https://ollama.com/api", "gpt-oss:20b", api_key="")
        self.assertFalse(status["reachable"])
        self.assertTrue(status["auth_required"])
        mocked.assert_not_called()

    def test_cloud_health_check_uses_authenticated_tags_endpoint(self) -> None:
        payload = {"models": [{"name": "gpt-oss:20b"}, {"name": "gpt-oss:120b"}]}
        with patch.object(story_llm_runtime, "urlopen", return_value=_FakeResponse(payload)) as mocked:
            status = story_llm_runtime.check_ollama(
                "https://ollama.com/api", "gpt-oss:20b", api_key="secret-test-key"
            )
        self.assertTrue(status["reachable"])
        self.assertTrue(status["model_available"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://ollama.com/api/tags")
        self.assertEqual(request.headers.get("Authorization"), "Bearer secret-test-key")

    def test_local_ollama_remains_supported_when_explicitly_configured(self) -> None:
        config = story_llm_runtime.ollama_config(
            base_url="http://localhost:11434", model="qwen3:4b", api_key=""
        )
        self.assertFalse(config["ollama_cloud"])
        self.assertEqual(config["model"], "qwen3:4b")
        self.assertEqual(story_llm_runtime.ollama_api_url(config["base_url"], "chat"), "http://localhost:11434/api/chat")

    def test_hook_engine_supports_direct_ollama_cloud_without_structured_format(self) -> None:
        model_output = {
            "candidates": [
                {"headline": "採掘会社が、AIを動かし始めた。", "subline": "収益の前提そのものが変わる。", "angle": "転換"}
            ]
        }
        fake = {"message": {"content": json.dumps(model_output, ensure_ascii=False)}}
        config = story_llm_runtime.ollama_config(
            base_url="https://ollama.com/api", model="gpt-oss:20b", api_key="secret-test-key", temperature=0.4
        )
        with patch.object(story_hook_engine, "_post_json", return_value=fake) as mocked:
            parsed, warning = story_hook_engine._call_hook_model(config, {"EVIDENCE": ["事業をAI向けへ転換した。"]})
        self.assertIsNone(warning)
        self.assertEqual(parsed, model_output)
        url, payload, headers = mocked.call_args.args[:3]
        self.assertEqual(url, "https://ollama.com/api/chat")
        self.assertEqual(payload["model"], "gpt-oss:20b")
        self.assertFalse(payload["stream"])
        self.assertNotIn("format", payload)
        self.assertEqual(headers.get("Authorization"), "Bearer secret-test-key")

    def test_openai_compatible_cloud_transport_shape_matches_legacy_card_model(self) -> None:
        model_output = {
            "cards": [
                {"role": "change", "headline": "前提が変わった。", "body": "事業の軸が別の収益源へ移り始めた。"}
            ]
        }
        fake = {"choices": [{"message": {"content": json.dumps(model_output, ensure_ascii=False)}}]}
        config = {
            "provider": "openai_compatible",
            "base_url": "https://ollama.com/v1",
            "api_key": "secret-test-key",
            "model": "gpt-oss:20b",
            "temperature": 0.35,
        }
        hero = {"entities": ["NeoGrid"], "headline_ja": "NeoGridの転換"}
        pack = {"facts": [{"fact_type": "change", "text": "NeoGridは事業を転換した。", "source_id": "a"}]}
        with patch.object(story_content_pipeline_v3, "_post_json", return_value=fake) as mocked:
            parsed, warning = story_content_pipeline_v3._call_model(config, hero, ["change"], pack)
        self.assertIsNone(warning)
        self.assertEqual(parsed, model_output)
        url, payload, headers = mocked.call_args.args[:3]
        self.assertEqual(url, "https://ollama.com/v1/chat/completions")
        self.assertEqual(payload["model"], "gpt-oss:20b")
        self.assertEqual(headers.get("Authorization"), "Bearer secret-test-key")

    def test_runtime_entrypoint_declares_cloud_default_and_api_key_gate(self) -> None:
        source = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        self.assertIn('RUNTIME_TOKEN = "dual-pipeline-v10.5"', source)
        self.assertIn('st.session_state["provider_story"] = "Ollama 로컬 추론 모델"', source)
        self.assertIn("Ollama Cloud API Key", source)
        self.assertIn("story_llm_runtime.check_ollama", source)
        self.assertIn('"base_url": "https://ollama.com/v1"', source)
        self.assertNotIn("Cloud에서 접근 가능한 OLLAMA_BASE_URL이 필요합니다", source)


if __name__ == "__main__":
    unittest.main()
