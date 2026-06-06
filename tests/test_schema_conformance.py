"""
Automation Opportunity Schema (AOS) 一致性测试。

校验三件事：
  1. JSON Schema 文件本身是合法 JSON 且结构完整
  2. SCHEMA_VERSION 与规范 md 声明的版本一致（版本唯一真源 = 代码常量）
  3. report_query.extract_opportunities 的真实产出，能通过【那份 JSON Schema 本身】的校验
     —— 关键：用 jsonschema 跑真 schema，而不是在 Python 里另写一套规则。
        覆盖了归一化（medium→med）与缺失置信度（→low）等边界，确保产出方永远发合规 AOS。

jsonschema 是可选开发依赖；缺失时第 3 类测试自动跳过，保持 report_query 的零硬依赖。

跑法：
    python3 -m unittest tests.test_schema_conformance
"""
import os
import re
import json
import unittest

from time_audit.core import report_query as RQ

try:
    import jsonschema
    from jsonschema import Draft202012Validator
    _HAS_JSONSCHEMA = True
except Exception:  # pragma: no cover - 取决于环境
    _HAS_JSONSCHEMA = False

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
SCHEMA_JSON = os.path.join(DOCS, "automation-opportunity-schema.json")
SCHEMA_MD = os.path.join(DOCS, "automation-opportunity-schema.md")

# AOS 规范分级：产出方只发规范拼写（medium 仅入参别名，不得发出）。
LEVEL_ENUM = {"low", "med", "high"}
ID_PATTERN = re.compile(r"^[PLF]-\d+$")
FP_PATTERN = re.compile(r"^fp_[0-9a-f]{12}$")


def _load_schema():
    with open(SCHEMA_JSON, encoding="utf-8") as f:
        return json.load(f)


def _sample_report():
    """刻意制造边界：line 用 'medium' 别名、surface 缺 confidence，验证产出仍合规。"""
    return {
        "report_meta": {"id": "20260101_120000"},
        "ai_insights": {
            "points": [{"title": "t", "description": "d", "confidence": "high",
                        "evidence_sessions": ["S001"]}],
            "lines": [{"workflow_name": "w", "automation_difficulty": "medium",
                       "confidence": "medium", "evidence_sessions": ["S002"],
                       "apps_involved": ["Chrome", "Word"], "steps": ["a"],
                       "estimated_weekly_savings_min": 70}],
            "surfaces": [{"insight_title": "i", "observation": "o",
                          "evidence_sessions": ["S003"]}],  # 故意缺 confidence
        },
    }


def _envelope(opps):
    return {
        "schema_version": RQ.SCHEMA_VERSION,
        "report_id": "20260101_120000",
        "count": len(opps),
        "opportunities": opps,
    }


class TestSchemaFiles(unittest.TestCase):
    def test_json_schema_is_valid_json(self):
        schema = _load_schema()
        self.assertEqual(schema["title"], "Automation Opportunity Schema (AOS)")
        self.assertIn("opportunity", schema["$defs"])
        self.assertIn("$id", schema)

    def test_id_is_host_independent(self):
        # $id 不应再绑定任何具体仓库/host，便于抽成独立 repo 后仍稳定。
        schema = _load_schema()
        self.assertFalse(schema["$id"].startswith("http"),
                         "$id 应为 host 无关的 URN，不要硬编码 github 路径")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 未安装")
    def test_schema_itself_is_valid_metaschema(self):
        Draft202012Validator.check_schema(_load_schema())

    def test_version_consistency(self):
        self.assertRegex(RQ.SCHEMA_VERSION, r"^\d+\.\d+\.\d+$")
        with open(SCHEMA_MD, encoding="utf-8") as f:
            md = f.read()
        self.assertIn(f"**版本：{RQ.SCHEMA_VERSION}**", md)


class TestProducerConformance(unittest.TestCase):
    """时间审计作为 reference producer，真实产出必须符合 AOS。"""

    def test_layers_present_and_fingerprinted(self):
        opps = RQ.extract_opportunities(_sample_report(), layer="all")
        self.assertEqual({o["layer"] for o in opps}, {"point", "line", "surface"})
        for o in opps:
            self.assertTrue(ID_PATTERN.match(o["id"]), f"id 格式: {o['id']}")
            self.assertTrue(FP_PATTERN.match(o["fingerprint"]),
                            f"fingerprint 格式: {o.get('fingerprint')}")
            self.assertIn(o["confidence"], LEVEL_ENUM,
                          f"产出置信度必须是规范拼写: {o['confidence']}")

    def test_normalization_medium_to_med(self):
        opps = RQ.extract_opportunities(_sample_report(), layer="line")
        line = opps[0]
        self.assertEqual(line["confidence"], "med", "medium 必须归一化为 med")
        self.assertEqual(line["automation_difficulty"], "med")

    def test_missing_confidence_defaults_valid(self):
        opps = RQ.extract_opportunities(_sample_report(), layer="surface")
        self.assertIn(opps[0]["confidence"], LEVEL_ENUM,
                      "缺失置信度也必须落到合法枚举（不得是空串）")

    def test_fingerprint_stable_across_reports(self):
        # 同一个工作流在两份报告里（位置不同），fingerprint 应一致。
        a = RQ.extract_opportunities(_sample_report(), layer="line")[0]
        rep2 = _sample_report()
        rep2["ai_insights"]["lines"].insert(0, {
            "workflow_name": "另一个", "confidence": "low", "evidence_sessions": ["S9"]})
        b = next(o for o in RQ.extract_opportunities(rep2, layer="line")
                 if o["workflow_name"] == "w")
        self.assertNotEqual(a["id"], b["id"], "位置编号应随顺序变化")
        self.assertEqual(a["fingerprint"], b["fingerprint"], "指纹应跨报告稳定")

    @unittest.skipUnless(_HAS_JSONSCHEMA, "jsonschema 未安装")
    def test_real_output_validates_against_schema(self):
        """核心：真实产出（含归一化/缺失边界）整体通过 JSON Schema 校验。"""
        schema = _load_schema()
        opps = RQ.extract_opportunities(_sample_report(), layer="all")
        envelope = _envelope(opps)
        errors = sorted(Draft202012Validator(schema).iter_errors(envelope),
                        key=lambda e: e.path)
        self.assertFalse(
            errors,
            "产出不符合 AOS schema:\n" + "\n".join(
                f"  - {list(e.path)}: {e.message}" for e in errors))


if __name__ == "__main__":
    unittest.main()
