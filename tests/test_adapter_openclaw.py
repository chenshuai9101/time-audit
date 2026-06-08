"""
openclaw 适配器单元测试 —— 全离线，构造 ~/.openclaw 结构。

跑法：
    python3 -m unittest tests.test_adapter_openclaw
"""
import os
import json
import tempfile
import unittest

from time_audit.sources.openclaw import OpenClawAdapter, parse_cron_jobs


class TestParseCronJobs(unittest.TestCase):
    def test_extracts_job_name_and_description(self):
        text = json.dumps({
            "version": 1,
            "jobs": [{
                "id": "x", "name": "每日Obsidian同步",
                "description": "每天8点同步任务到Obsidian",
                "enabled": True, "createdAtMs": 1778200408394,
                "schedule": {"kind": "cron", "expr": "0 8 * * *"},
            }],
        }, ensure_ascii=False)
        events = parse_cron_jobs(text)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertIn("每日Obsidian同步", e["content"])
        self.assertIn("每天8点同步任务到Obsidian", e["content"])
        self.assertEqual(e["app"], "openclaw")
        self.assertEqual(e["source"], "openclaw")
        self.assertAlmostEqual(e["ts"], 1778200408.394, places=2)

    def test_malformed_json_returns_empty(self):
        self.assertEqual(parse_cron_jobs("{ not json"), [])

    def test_missing_jobs_key_returns_empty(self):
        self.assertEqual(parse_cron_jobs(json.dumps({"version": 1})), [])


class TestAdapter(unittest.TestCase):
    def test_available_false_when_base_missing(self):
        cfg = {"sources": {"openclaw": {"base_dir": "/no/such/openclaw"}}}
        self.assertFalse(OpenClawAdapter().available(cfg))

    def test_collect_reads_cron_jobs(self):
        base = tempfile.mkdtemp()
        os.makedirs(os.path.join(base, "cron"))
        with open(os.path.join(base, "cron", "jobs.json"), "w", encoding="utf-8") as f:
            json.dump({"jobs": [{
                "name": "周报推送", "description": "每周五推送周报",
                "createdAtMs": 1778200408394,
                "schedule": {"expr": "0 17 * * 5"}}]}, f, ensure_ascii=False)
        cfg = {"sources": {"openclaw": {"base_dir": base}}}
        adapter = OpenClawAdapter()
        self.assertTrue(adapter.available(cfg))
        events = adapter.collect(cfg, days=36500)
        self.assertEqual(len(events), 1)
        self.assertIn("周报推送", events[0]["content"])

    def test_collect_graceful_when_no_cron(self):
        base = tempfile.mkdtemp()  # 存在但没有 cron/jobs.json
        cfg = {"sources": {"openclaw": {"base_dir": base}}}
        # 不抛错，返回空
        self.assertEqual(OpenClawAdapter().collect(cfg, days=14), [])


if __name__ == "__main__":
    unittest.main()
