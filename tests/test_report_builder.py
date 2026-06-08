"""
report_builder 证据校验 + modality 合并单元测试 —— 全离线。

跑法：
    python3 -m unittest tests.test_report_builder
"""
import unittest

from time_audit.core import report_builder as RB


class TestValidateEvidence(unittest.TestCase):
    def test_drops_insight_with_all_fake_sessions(self):
        items = [{"title": "幻觉", "evidence_sessions": ["S014", "S099"]}]
        out = RB.validate_evidence(items, valid_ids={"S001", "S002"})
        self.assertEqual(out, [])

    def test_prunes_fake_keeps_real(self):
        items = [{"title": "半真", "evidence_sessions": ["S001", "S099"]}]
        out = RB.validate_evidence(items, valid_ids={"S001"})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["evidence_sessions"], ["S001"])

    def test_command_layer_without_sessions_untouched(self):
        items = [{"title": "命令层", "modality": "command",
                  "evidence_samples": ["x"]}]
        out = RB.validate_evidence(items, valid_ids=set())
        self.assertEqual(len(out), 1)


class TestBuildReportMergesCommandLayer(unittest.TestCase):
    def _sessions(self):
        return [{"id": "S001", "day": "2026-06-08", "apps": ["shell"]}]

    def test_command_results_merged_with_modality(self):
        llm_result = {
            "points": [{"title": "ocr点", "evidence_sessions": ["S001"]}],
            "lines": [], "surfaces": [],
        }
        command_result = {
            "points": [{"normalized": "openclaw doctor --fix", "count": 19,
                        "evidence_samples": ["openclaw doctor --fix"],
                        "modality": "command"}],
            "lines": [{"sequence": ["openclaw gateway start", "openclaw tui"],
                       "count": 58, "length": 2, "modality": "command"}],
        }
        report = RB.build_report(
            report_id="t", llm_result=llm_result, sessions=self._sessions(),
            app_freq={"top_apps": []}, hours=[], events_total=100,
            model_name="m", dry_run=False, keep_raw=False,
            command_result=command_result)
        pts = report["ai_insights"]["points"]
        lns = report["ai_insights"]["lines"]
        # OCR 点 + 命令点
        self.assertEqual(len(pts), 2)
        modalities = {p.get("modality") for p in pts}
        self.assertEqual(modalities, {"ocr", "command"})
        # 命令线进入
        self.assertEqual(len(lns), 1)
        self.assertEqual(lns[0]["modality"], "command")

    def test_hallucinated_ocr_evidence_dropped(self):
        llm_result = {
            "points": [{"title": "幻觉点", "evidence_sessions": ["S999"]}],
            "lines": [], "surfaces": [],
        }
        report = RB.build_report(
            report_id="t", llm_result=llm_result, sessions=self._sessions(),
            app_freq={"top_apps": []}, hours=[], events_total=100,
            model_name="m", dry_run=False, keep_raw=False)
        self.assertEqual(report["ai_insights"]["points"], [])


if __name__ == "__main__":
    unittest.main()
