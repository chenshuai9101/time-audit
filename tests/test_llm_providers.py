"""
provider 抽象层单元测试 —— 全离线，不打真实网络。

跑法：
    python -m unittest tests.test_llm_providers
    或  python -m pytest tests/
"""
import io
import json
import unittest
from unittest import mock

from time_audit.core import llm_providers as P
from time_audit.core.llm_providers import (
    get_provider, OllamaProvider, OpenAIProvider, ProviderError,
)
from time_audit.core import llm_analyzer


def _fake_http_response(payload: dict):
    """造一个能当 urlopen 上下文管理器用的假响应"""
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")
    cm.__enter__.return_value.status = 200
    return cm


class TestGetProvider(unittest.TestCase):
    def test_default_is_ollama(self):
        self.assertIsInstance(get_provider({}), OllamaProvider)

    def test_explicit_ollama(self):
        p = get_provider({"provider": "ollama", "model": "qwen2.5:7b"})
        self.assertIsInstance(p, OllamaProvider)
        self.assertFalse(p.is_cloud())

    def test_openai_provider(self):
        p = get_provider({"provider": "openai",
                          "cloud": {"base_url": "https://x/v1", "model": "m"}})
        self.assertIsInstance(p, OpenAIProvider)
        self.assertTrue(p.is_cloud())

    def test_unknown_provider_raises(self):
        with self.assertRaises(ProviderError):
            get_provider({"provider": "banana"})


class TestOpenAIProvider(unittest.TestCase):
    def test_api_key_from_named_env(self):
        with mock.patch.dict("os.environ", {"MY_KEY": "sk-abc"}, clear=False):
            p = OpenAIProvider("https://x/v1", "m", api_key_env="MY_KEY")
            self.assertEqual(p.api_key, "sk-abc")

    def test_preflight_fails_without_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            p = OpenAIProvider("https://x/v1", "m", api_key_env="ABSENT_KEY")
            r = p.preflight()
            self.assertFalse(r["ok"])
            self.assertIn("ABSENT_KEY", r["reason"])

    def test_preflight_fails_without_model(self):
        with mock.patch.dict("os.environ", {"K": "sk"}, clear=False):
            p = OpenAIProvider("https://x/v1", "", api_key_env="K")
            self.assertFalse(p.preflight()["ok"])

    def test_preflight_ok_with_key_and_model(self):
        with mock.patch.dict("os.environ", {"K": "sk"}, clear=False):
            p = OpenAIProvider("https://x/v1", "m", api_key_env="K")
            self.assertTrue(p.preflight()["ok"])

    def test_chat_parses_choices(self):
        payload = {"choices": [{"message": {"content": '{"points": []}'}}]}
        with mock.patch.dict("os.environ", {"K": "sk"}, clear=False), \
             mock.patch("urllib.request.urlopen", return_value=_fake_http_response(payload)):
            p = OpenAIProvider("https://x/v1", "m", api_key_env="K")
            out = p.chat("sys", "user")
            self.assertEqual(out, '{"points": []}')

    def test_chat_without_key_returns_none(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            p = OpenAIProvider("https://x/v1", "m", api_key_env="ABSENT")
            self.assertIsNone(p.chat("sys", "user"))


class TestOllamaProvider(unittest.TestCase):
    def test_describe_and_not_cloud(self):
        p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
        self.assertIn("本地", p.describe())
        self.assertFalse(p.is_cloud())

    def test_chat_parses_response(self):
        payload = {"response": '{"lines": []}'}
        with mock.patch("urllib.request.urlopen", return_value=_fake_http_response(payload)):
            p = OllamaProvider("http://localhost:11434", "m")
            self.assertEqual(p.chat("sys", "user"), '{"lines": []}')


class TestLenientParse(unittest.TestCase):
    """确保抽象层重构没破坏原有 JSON 容错解析"""

    def test_clean_json(self):
        self.assertEqual(
            llm_analyzer._parse_json_lenient('{"points": [1, 2]}', "points"), [1, 2])

    def test_json_with_prose_wrapper(self):
        raw = '这是分析结果：\n{"lines": [{"id": "L-01"}]}\n以上。'
        out = llm_analyzer._parse_json_lenient(raw, "lines")
        self.assertEqual(out, [{"id": "L-01"}])

    def test_empty_returns_empty_list(self):
        self.assertEqual(llm_analyzer._parse_json_lenient("", "points"), [])


class TestPreflightWiring(unittest.TestCase):
    def test_preflight_reports_provider_and_cloud_flag(self):
        with mock.patch.dict("os.environ", {"K": "sk"}, clear=False):
            r = llm_analyzer.preflight({
                "provider": "openai",
                "cloud": {"base_url": "https://x/v1", "model": "m", "api_key_env": "K"},
            })
            self.assertEqual(r["provider"], "openai")
            self.assertTrue(r["is_cloud"])
            self.assertTrue(r["ok"])


if __name__ == "__main__":
    unittest.main()
