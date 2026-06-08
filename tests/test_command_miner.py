"""
command_miner 确定性命令挖掘单元测试 —— 全离线，纯函数。

跑法：
    python3 -m unittest tests.test_command_miner
"""
import unittest

from time_audit.core import command_miner as CM


def _ev(content, app="shell", ts=0.0, window=""):
    """构造一个归一化事件。"""
    return {"app": app, "content": content, "ts": ts, "window": window,
            "source": app}


class TestNormalizeCommand(unittest.TestCase):
    def test_strips_quoted_string(self):
        self.assertEqual(
            CM.normalize_command('git commit -m "fix a nasty bug"'),
            'git commit -m _',
        )

    def test_strips_path_args(self):
        self.assertEqual(
            CM.normalize_command('gh api repos/me/proj/traffic/views'),
            'gh api repos/_/_/_/_',
        )

    def test_keeps_command_skeleton(self):
        self.assertEqual(CM.normalize_command('git pull origin main'),
                         'git pull origin main')

    def test_blank_returns_empty(self):
        self.assertEqual(CM.normalize_command('   '), '')


class TestPointCandidates(unittest.TestCase):
    def test_repeated_command_becomes_point(self):
        events = [_ev("openclaw tui", ts=i) for i in range(6)]
        points = CM.mine_points(events, min_count=5)
        self.assertEqual(len(points), 1)
        p = points[0]
        self.assertEqual(p["normalized"], "openclaw tui")
        self.assertEqual(p["count"], 6)
        self.assertEqual(p["modality"], "command")
        # 证据是真实样例原文，最多 3 条
        self.assertTrue(p["evidence_samples"])
        self.assertLessEqual(len(p["evidence_samples"]), 3)

    def test_below_threshold_excluded(self):
        events = [_ev("rare cmd", ts=i) for i in range(3)]
        self.assertEqual(CM.mine_points(events, min_count=5), [])

    def test_variable_args_collapse_to_same_point(self):
        events = [
            _ev('gh api repos/a/b/traffic/views', ts=0),
            _ev('gh api repos/c/d/traffic/views', ts=1),
            _ev('gh api repos/e/f/traffic/views', ts=2),
            _ev('gh api repos/g/h/traffic/views', ts=3),
            _ev('gh api repos/i/j/traffic/views', ts=4),
        ]
        points = CM.mine_points(events, min_count=5)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["count"], 5)


class TestSequenceCandidates(unittest.TestCase):
    def test_repeated_sequence_becomes_line(self):
        # 三次重复的 git pull -> pytest -> git push 序列
        seq = ["git pull origin main", "pytest tests/", "git push"]
        events = []
        t = 0
        for _ in range(3):
            for cmd in seq:
                events.append(_ev(cmd, ts=t)); t += 1
            events.append(_ev("unrelated noise", ts=t)); t += 1
        lines = CM.mine_sequences(events, min_count=3, min_len=2, max_len=5)
        self.assertTrue(lines, "应至少挖出一条重复序列")
        top = lines[0]
        self.assertGreaterEqual(top["count"], 3)
        self.assertGreaterEqual(len(top["sequence"]), 2)
        self.assertEqual(top["modality"], "command")

    def test_no_repetition_no_line(self):
        events = [_ev(f"cmd{i}", ts=i) for i in range(8)]
        self.assertEqual(
            CM.mine_sequences(events, min_count=3, min_len=2, max_len=5), [])

    def test_consecutive_duplicates_collapsed(self):
        # 同一命令连按 N 次不是工作流，不应产生 (tui,tui) 退化序列
        events = [_ev("openclaw tui", ts=i) for i in range(10)]
        lines = CM.mine_sequences(events, min_count=3, min_len=2, max_len=5)
        self.assertEqual(lines, [], "连续重复同一命令不应成为线候选")

    def test_real_workflow_survives_collapsing(self):
        # a a b  a a b  a a b -> 折叠成 a b a b a b -> 序列 (a,b) 重复
        seq = []
        t = 0
        for _ in range(3):
            for cmd in ["git add", "git add", "git push"]:
                seq.append(_ev(cmd, ts=t)); t += 1
        lines = CM.mine_sequences(seq, min_count=3, min_len=2, max_len=5)
        self.assertTrue(lines)
        self.assertEqual(lines[0]["sequence"], ["git add", "git push"])


class TestMineSkillCandidates(unittest.TestCase):
    def test_returns_points_and_lines_only_for_command_events(self):
        events = [
            _ev("openclaw tui", ts=0),
            _ev("openclaw tui", ts=1),
            _ev("openclaw tui", ts=2),
            _ev("openclaw tui", ts=3),
            _ev("openclaw tui", ts=4),
            # OCR 事件不应进入命令挖掘
            {"app": "Safari浏览器", "content": "some page", "ts": 5, "source": "screenpipe"},
        ]
        out = CM.mine_skill_candidates(events)
        self.assertIn("points", out)
        self.assertIn("lines", out)
        # openclaw tui 重复 5 次 -> 一个点；OCR 事件被忽略
        self.assertEqual(len(out["points"]), 1)


class TestReportConverters(unittest.TestCase):
    def test_points_converted_to_renderable(self):
        cand = [{"normalized": "openclaw doctor --fix", "count": 19,
                 "evidence_samples": ["openclaw doctor --fix"], "modality": "command"}]
        out = CM.as_report_points(cand)
        self.assertEqual(len(out), 1)
        p = out[0]
        self.assertEqual(p["modality"], "command")
        self.assertEqual(p["confidence"], "high")           # 确定性 = 高置信
        self.assertIn("openclaw doctor --fix", p["title"])
        self.assertEqual(p["evidence_samples"], ["openclaw doctor --fix"])
        self.assertNotIn("evidence_sessions", p)            # 命令层无虚构 session

    def test_lines_converted_to_renderable(self):
        cand = [{"sequence": ["openclaw gateway start", "openclaw tui"],
                 "count": 58, "length": 2, "modality": "command"}]
        out = CM.as_report_lines(cand)
        self.assertEqual(len(out), 1)
        l = out[0]
        self.assertEqual(l["modality"], "command")
        self.assertEqual(l["occurrence_count"], 58)
        self.assertEqual(l["steps"], ["openclaw gateway start", "openclaw tui"])
        self.assertEqual(l["confidence"], "high")


if __name__ == "__main__":
    unittest.main()