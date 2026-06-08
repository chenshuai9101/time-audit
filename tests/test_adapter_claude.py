"""
claude_code 适配器单元测试 —— 全离线，构造 jsonl 文本。

跑法：
    python3 -m unittest tests.test_adapter_claude
"""
import os
import json
import tempfile
import unittest

from time_audit.sources.claude_code import (
    ClaudeCodeAdapter, extract_user_text, parse_transcript, is_injected_prompt,
)


class TestExtractUserText(unittest.TestCase):
    def test_string_content(self):
        self.assertEqual(extract_user_text("查一下 GitHub 仓库浏览量"),
                         "查一下 GitHub 仓库浏览量")

    def test_text_blocks_concatenated(self):
        content = [{"type": "text", "text": "帮我"},
                   {"type": "text", "text": "查浏览量"}]
        self.assertEqual(extract_user_text(content), "帮我 查浏览量")

    def test_tool_result_only_returns_none(self):
        content = [{"type": "tool_result", "content": "exit 0"}]
        self.assertIsNone(extract_user_text(content))

    def test_blank_returns_none(self):
        self.assertIsNone(extract_user_text("   "))


class TestParseTranscript(unittest.TestCase):
    def _lines(self, *objs):
        return "\n".join(json.dumps(o, ensure_ascii=False) for o in objs)

    def test_extracts_user_text_messages_only(self):
        text = self._lines(
            {"type": "user", "timestamp": "2026-06-08T15:50:47.000Z",
             "cwd": "/proj", "message": {"role": "user", "content": "查浏览量"}},
            {"type": "assistant", "timestamp": "2026-06-08T15:50:48.000Z",
             "message": {"role": "assistant", "content": "好的"}},
            {"type": "queue-operation", "timestamp": "2026-06-08T15:50:49.000Z"},
            {"type": "user", "timestamp": "2026-06-08T15:50:50.000Z",
             "message": {"role": "user",
                         "content": [{"type": "tool_result", "content": "ok"}]}},
        )
        events = parse_transcript(text)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["content"], "查浏览量")
        self.assertEqual(e["app"], "claude-code")
        self.assertEqual(e["source"], "claude-code")
        self.assertEqual(e["window"], "/proj")
        self.assertGreater(e["ts"], 0)

    def test_cutoff_filters_old(self):
        text = self._lines(
            {"type": "user", "timestamp": "2020-01-01T00:00:00.000Z",
             "message": {"role": "user", "content": "old"}},
            {"type": "user", "timestamp": "2026-06-08T00:00:00.000Z",
             "message": {"role": "user", "content": "new"}},
        )
        from datetime import datetime
        cutoff = datetime(2025, 1, 1).timestamp()
        events = parse_transcript(text, cutoff_ts=cutoff)
        self.assertEqual([e["content"] for e in events], ["new"])


class TestAdapter(unittest.TestCase):
    def test_available_false_when_dir_missing(self):
        cfg = {"sources": {"claude": {"projects_dir": "/no/such/dir"}}}
        self.assertFalse(ClaudeCodeAdapter().available(cfg))

    def test_collect_reads_jsonl_files(self):
        d = tempfile.mkdtemp()
        sub = os.path.join(d, "proj-a")
        os.makedirs(sub)
        with open(os.path.join(sub, "s.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "user", "timestamp": "2026-06-08T12:00:00.000Z",
                "message": {"role": "user", "content": "做个 skill"}},
                ensure_ascii=False) + "\n")
        cfg = {"sources": {"claude": {"projects_dir": d}}}
        adapter = ClaudeCodeAdapter()
        self.assertTrue(adapter.available(cfg))
        events = adapter.collect(cfg, days=3650)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["content"], "做个 skill")


class TestInjectedPromptFilter(unittest.TestCase):
    def test_detects_memory_agent_injection(self):
        self.assertTrue(is_injected_prompt(
            "Hello memory agent, you are continuing to observe the primary Claude session."))

    def test_detects_mode_switch_and_tag_requirement(self):
        self.assertTrue(is_injected_prompt("--- MODE SWITCH: PROGRESS SUMMARY ---"))
        self.assertTrue(is_injected_prompt("⚠️ CRITICAL TAG REQUIREMENT — RE..."))

    def test_detects_observed_context_and_system_reminder(self):
        self.assertTrue(is_injected_prompt("<observed_from_primary_session> x"))
        self.assertTrue(is_injected_prompt("<system-reminder>do this</system-reminder>"))

    def test_genuine_prompt_not_flagged(self):
        self.assertFalse(is_injected_prompt("查一下 GitHub 仓库浏览量"))
        self.assertFalse(is_injected_prompt("帮我把这个流程做成 skill"))

    def test_parse_transcript_skips_injected(self):
        text = self._inj_lines()
        events = parse_transcript(text)
        self.assertEqual([e["content"] for e in events], ["真实的提问"])

    def _inj_lines(self):
        return "\n".join(json.dumps(o, ensure_ascii=False) for o in [
            {"type": "user", "timestamp": "2026-06-08T12:00:00.000Z",
             "message": {"role": "user",
                         "content": "Hello memory agent, you are continuing to observe"}},
            {"type": "user", "timestamp": "2026-06-08T12:01:00.000Z",
             "message": {"role": "user", "content": "真实的提问"}},
        ])


class TestObserverDirSkipped(unittest.TestCase):
    def test_collect_skips_observer_sessions(self):
        d = tempfile.mkdtemp()
        observer = os.path.join(d, "-Users-x--claude-mem-observer-sessions")
        normal = os.path.join(d, "proj-real")
        os.makedirs(observer); os.makedirs(normal)
        msg = lambda c: json.dumps({
            "type": "user", "timestamp": "2026-06-08T12:00:00.000Z",
            "message": {"role": "user", "content": c}}, ensure_ascii=False) + "\n"
        with open(os.path.join(observer, "o.jsonl"), "w", encoding="utf-8") as f:
            f.write(msg("观察者噪声"))
        with open(os.path.join(normal, "r.jsonl"), "w", encoding="utf-8") as f:
            f.write(msg("真实意图"))
        cfg = {"sources": {"claude": {"projects_dir": d}}}
        events = ClaudeCodeAdapter().collect(cfg, days=36500)
        self.assertEqual([e["content"] for e in events], ["真实意图"])


if __name__ == "__main__":
    unittest.main()
