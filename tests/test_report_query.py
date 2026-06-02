"""
report_query 逻辑层单元测试 —— 全离线，不需要 mcp 包，用临时目录造报告。

跑法：
    python3 -m unittest tests.test_report_query
"""
import os
import json
import tempfile
import unittest

from time_audit.core import report_query as RQ


def _sample_report(report_id: str = "20260101_120000", dry_run: bool = False) -> dict:
    """构造一份覆盖各置信度/难度的报告 fixture。"""
    return {
        "report_meta": {
            "id": report_id,
            "generated_at": "2026-01-01 12:00:00",
            "engine_version": "time-audit v2 (LLM-driven)",
            "llm_model": "qwen2.5:7b",
            "dry_run": dry_run,
        },
        "overall": {
            "raw_event_count": 100, "session_count": 10, "day_count": 3,
            "day_range": "2026-01-01 ~ 2026-01-03", "active_hours": [9, 14],
        },
        "app_breakdown": [
            {"app": "Chrome", "duration_minutes": 100, "duration_pct": 50, "events": 20},
        ],
        "ai_insights": {
            "points": [
                {"title": "P高", "description": "d", "frequency_hint": "每天",
                 "skill_suggestion": "s", "confidence": "high",
                 "evidence_sessions": ["S001"]},
                {"title": "P低", "description": "d", "frequency_hint": "偶尔",
                 "skill_suggestion": "s", "confidence": "low",
                 "evidence_sessions": ["S002"]},
            ],
            "lines": [
                {"workflow_name": "易流程", "automation_difficulty": "low",
                 "confidence": "high", "trigger": "每天11点",
                 "apps_involved": ["Chrome", "Word"], "occurrence_count": 3,
                 "avg_duration_min": 14, "estimated_weekly_savings_min": 70,
                 "skill_suggestion": "s", "evidence_sessions": ["S001", "S007"],
                 "steps": ["a", "b"]},
                {"workflow_name": "难流程", "automation_difficulty": "high",
                 "confidence": "med", "trigger": "不定", "apps_involved": ["微信"],
                 "occurrence_count": 2, "avg_duration_min": 5,
                 "estimated_weekly_savings_min": 10, "skill_suggestion": "s",
                 "evidence_sessions": ["S003"], "steps": []},
            ],
            "surfaces": [
                {"insight_title": "F面", "observation": "o", "implication": "i",
                 "recommendation": "r", "confidence": "med",
                 "evidence_sessions": ["S001"]},
            ],
        },
    }


class _TmpReportsDir:
    """上下文管理器：建临时报告目录并写入若干报告。"""
    def __init__(self, reports):
        self.reports = reports
        self._td = None

    def __enter__(self):
        self._td = tempfile.TemporaryDirectory()
        d = self._td.name
        for rep in self.reports:
            rid = rep["report_meta"]["id"]
            with open(os.path.join(d, f"report_{rid}.json"), "w", encoding="utf-8") as f:
                json.dump(rep, f, ensure_ascii=False)
        return d

    def __exit__(self, *a):
        self._td.cleanup()


class TestLoadReport(unittest.TestCase):
    def test_latest_when_no_id(self):
        early = _sample_report("20260101_090000")
        late = _sample_report("20260102_090000")
        with _TmpReportsDir([early, late]) as d:
            rep = RQ.load_report(d)
            self.assertEqual(rep["report_meta"]["id"], "20260102_090000")

    def test_specific_id(self):
        with _TmpReportsDir([_sample_report("20260101_090000"),
                             _sample_report("20260102_090000")]) as d:
            rep = RQ.load_report(d, "20260101_090000")
            self.assertEqual(rep["report_meta"]["id"], "20260101_090000")

    def test_empty_dir_raises_with_hint(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError) as ctx:
                RQ.load_report(d)
            self.assertIn("time-audit", str(ctx.exception))

    def test_missing_id_lists_available(self):
        with _TmpReportsDir([_sample_report("20260101_090000")]) as d:
            with self.assertRaises(FileNotFoundError) as ctx:
                RQ.load_report(d, "nope")
            self.assertIn("20260101_090000", str(ctx.exception))


class TestListReportsIndex(unittest.TestCase):
    def test_newest_first_and_counts(self):
        with _TmpReportsDir([_sample_report("20260101_090000"),
                             _sample_report("20260102_090000")]) as d:
            idx = RQ.list_reports_index(d)
            self.assertEqual(idx["total"], 2)
            self.assertEqual(idx["reports"][0]["report_id"], "20260102_090000")
            self.assertEqual(idx["reports"][0]["counts"],
                             {"points": 2, "lines": 2, "surfaces": 1})

    def test_pagination(self):
        reps = [_sample_report(f"2026010{i}_090000") for i in range(1, 4)]
        with _TmpReportsDir(reps) as d:
            idx = RQ.list_reports_index(d, limit=1, offset=0)
            self.assertEqual(idx["count"], 1)
            self.assertTrue(idx["has_more"])


class TestExtractOpportunities(unittest.TestCase):
    def setUp(self):
        self.rep = _sample_report()

    def test_all_layers_with_stable_ids(self):
        opps = RQ.extract_opportunities(self.rep, layer="all")
        ids = [o["id"] for o in opps]
        self.assertEqual(ids, ["P-01", "P-02", "L-01", "L-02", "F-01"])

    def test_layer_filter(self):
        opps = RQ.extract_opportunities(self.rep, layer="line")
        self.assertTrue(all(o["layer"] == "line" for o in opps))
        self.assertEqual(len(opps), 2)

    def test_min_confidence_drops_low(self):
        opps = RQ.extract_opportunities(self.rep, layer="point", min_confidence="high")
        self.assertEqual([o["id"] for o in opps], ["P-01"])

    def test_max_difficulty_only_affects_lines(self):
        opps = RQ.extract_opportunities(self.rep, layer="all", max_difficulty="low")
        line_ids = [o["id"] for o in opps if o["layer"] == "line"]
        # 难流程(high)被过滤，易流程(low)保留
        self.assertEqual(line_ids, ["L-01"])
        # point/surface 不受难度过滤影响
        self.assertIn("P-01", [o["id"] for o in opps])
        self.assertIn("F-01", [o["id"] for o in opps])

    def test_combined_filters(self):
        opps = RQ.extract_opportunities(
            self.rep, layer="line", min_confidence="high", max_difficulty="low")
        self.assertEqual([o["id"] for o in opps], ["L-01"])

    def test_evidence_preserved(self):
        opps = RQ.extract_opportunities(self.rep, layer="line")
        self.assertEqual(opps[0]["evidence_sessions"], ["S001", "S007"])

    def test_invalid_layer_raises(self):
        with self.assertRaises(ValueError):
            RQ.extract_opportunities(self.rep, layer="banana")


class TestSummarize(unittest.TestCase):
    def test_summary_shape(self):
        s = RQ.summarize_report(_sample_report())
        self.assertEqual(s["insight_counts"], {"points": 2, "lines": 2, "surfaces": 1})
        self.assertEqual(s["overall"]["session_count"], 10)
        self.assertIn("app_breakdown", s)


if __name__ == "__main__":
    unittest.main()
