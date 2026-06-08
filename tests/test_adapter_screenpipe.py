"""
screenpipe 适配器单元测试 —— 用真实临时 sqlite（v0.3 frames 表）。

跑法：
    python3 -m unittest tests.test_adapter_screenpipe
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

from time_audit.sources.screenpipe import ScreenpipeAdapter


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE frames (
            timestamp TEXT, app_name TEXT, window_name TEXT,
            full_text TEXT, accessibility_text TEXT,
            snapshot_path TEXT, browser_url TEXT
        )""")
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO frames VALUES (?,?,?,?,?,?,?)",
        (now, "Safari浏览器", "GitHub - traffic", "仓库浏览量 327", None, "", "https://github.com"))
    conn.commit()
    conn.close()


class TestScreenpipeAdapter(unittest.TestCase):
    def test_available_false_when_db_missing(self):
        cfg = {"screenpipe": {"db_path": "/no/such/db.sqlite", "auto_discover": False}}
        self.assertFalse(ScreenpipeAdapter().available(cfg))

    def test_collect_reads_frames(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "db.sqlite")
        _make_db(db)
        cfg = {"screenpipe": {"db_path": db, "auto_discover": False}}
        adapter = ScreenpipeAdapter()
        self.assertTrue(adapter.available(cfg))
        events = adapter.collect(cfg, days=14)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["app"], "Safari浏览器")
        self.assertTrue(e["source"].startswith("screenpipe"))
        self.assertIn("仓库浏览量", e["content"])

    def test_collect_does_not_fall_back_to_mock(self):
        # DB 存在但为空表 -> 适配器返回空，而不是塞模拟数据（mock 兜底是编排层的事）
        d = tempfile.mkdtemp()
        db = os.path.join(d, "db.sqlite")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE frames (timestamp TEXT, app_name TEXT, "
                     "window_name TEXT, full_text TEXT, accessibility_text TEXT, "
                     "snapshot_path TEXT, browser_url TEXT)")
        conn.commit(); conn.close()
        cfg = {"screenpipe": {"db_path": db, "auto_discover": False}}
        events = ScreenpipeAdapter().collect(cfg, days=14)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
