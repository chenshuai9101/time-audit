"""
shell_history 适配器单元测试 —— 全离线，用临时历史文件。

跑法：
    python3 -m unittest tests.test_adapter_shell
"""
import os
import tempfile
import unittest

from time_audit.sources.shell_history import ShellHistoryAdapter, parse_history


class TestParseHistory(unittest.TestCase):
    def test_extended_zsh_format_parses_ts_and_cmd(self):
        text = ": 1700000000:0;git status\n: 1700000005:2;git push\n"
        events = parse_history(text, base_ts=999.0)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["content"], "git status")
        self.assertEqual(events[0]["ts"], 1700000000.0)
        self.assertEqual(events[1]["content"], "git push")
        self.assertEqual(events[0]["app"], "shell")
        self.assertEqual(events[0]["source"], "shell")

    def test_plain_lines_get_monotonic_synthetic_ts(self):
        text = "openclaw tui\ncodex\nopenclaw tui\n"
        events = parse_history(text, base_ts=1000.0)
        self.assertEqual([e["content"] for e in events],
                         ["openclaw tui", "codex", "openclaw tui"])
        ts = [e["ts"] for e in events]
        self.assertTrue(ts[0] < ts[1] < ts[2], "合成时间戳应单调递增")

    def test_backslash_continuation_joined(self):
        text = "cp a.json a.json.bak\\\n  --verbose\nls\n"
        events = parse_history(text, base_ts=0.0)
        self.assertEqual(events[0]["content"], "cp a.json a.json.bak --verbose")
        self.assertEqual(events[1]["content"], "ls")

    def test_comment_lines_skipped(self):
        text = "# 这是注释\ngit status\n"
        events = parse_history(text, base_ts=0.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["content"], "git status")

    def test_blank_lines_skipped(self):
        text = "\n\ngit status\n\n"
        events = parse_history(text, base_ts=0.0)
        self.assertEqual(len(events), 1)


class TestAdapter(unittest.TestCase):
    def test_available_false_when_no_file(self):
        cfg = {"sources": {"shell": {"history_path": "/no/such/history/file"}}}
        self.assertFalse(ShellHistoryAdapter().available(cfg))

    def test_collect_reads_configured_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".history",
                                         delete=False, encoding="utf-8") as f:
            f.write("git status\ngit push\n")
            path = f.name
        try:
            cfg = {"sources": {"shell": {"history_path": path}}}
            adapter = ShellHistoryAdapter()
            self.assertTrue(adapter.available(cfg))
            events = adapter.collect(cfg, days=14)
            self.assertEqual([e["content"] for e in events],
                             ["git status", "git push"])
            self.assertTrue(all(e["source"] == "shell" for e in events))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
