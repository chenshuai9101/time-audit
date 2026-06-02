"""
Automation Opportunity Schema (AOS) 一致性测试 —— 零依赖，不引 jsonschema。

校验：
  1. JSON Schema 文件本身是合法 JSON 且结构完整
  2. report_query.extract_opportunities 的产出符合 AOS 必填字段约定
  3. SCHEMA_VERSION 与规范文件版本一致

跑法：
    python3 -m unittest tests.test_schema_conformance
"""
import os
import re
import json
import unittest

from time_audit.core import report_query as RQ

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
SCHEMA_JSON = os.path.join(DOCS, "automation-opportunity-schema.v1.json")
SCHEMA_MD = os.path.join(DOCS, "automation-opportunity-schema.md")

# AOS v1 必填字段（与 docs/automation-opportunity-schema.md 对应）
COMMON_REQUIRED = {"id", "layer", "confidence", "evidence_sessions"}
LAYER_REQUIRED = {
    "point": {"title", "description"},
    "line": {"workflow_name"},
    "surface": {"insight_title", "observation"},
}
CONFIDENCE_ENUM = {"low", "med", "medium", "high"}
ID_PATTERN = re.compile(r"^[PLF]-\d+$")


def _sample_report():
    return {
        "report_meta": {"id": "20260101_120000"},
        "ai_insights": {
            "points": [{"title": "t", "description": "d", "confidence": "high",
                        "evidence_sessions": ["S001"]}],
            "lines": [{"workflow_name": "w", "automation_difficulty": "low",
                       "confidence": "med", "evidence_sessions": ["S002"],
                       "steps": ["a"]}],
            "surfaces": [{"insight_title": "i", "observation": "o",
                          "confidence": "high", "evidence_sessions": ["S003"]}],
        },
    }


def _assert_conformant(testcase, opp):
    """逐条机会做 AOS 必填/枚举/编号校验。"""
    missing = COMMON_REQUIRED - set(opp)
    testcase.assertFalse(missing, f"{opp.get('id')} 缺公共必填: {missing}")
    testcase.assertTrue(ID_PATTERN.match(opp["id"]), f"id 格式不对: {opp['id']}")
    testcase.assertIn(opp["confidence"], CONFIDENCE_ENUM, f"置信度越界: {opp['confidence']}")
    testcase.assertIsInstance(opp["evidence_sessions"], list)
    layer = opp["layer"]
    testcase.assertIn(layer, LAYER_REQUIRED, f"未知 layer: {layer}")
    lmissing = LAYER_REQUIRED[layer] - set(opp)
    testcase.assertFalse(lmissing, f"{opp['id']} ({layer}) 缺层级必填: {lmissing}")


class TestSchemaFiles(unittest.TestCase):
    def test_json_schema_is_valid_json(self):
        with open(SCHEMA_JSON, encoding="utf-8") as f:
            schema = json.load(f)
        self.assertEqual(schema["title"], "Automation Opportunity Schema (AOS)")
        self.assertIn("opportunity", schema["$defs"])
        self.assertIn("$id", schema)

    def test_version_consistency(self):
        # 代码常量符合 semver
        self.assertRegex(RQ.SCHEMA_VERSION, r"^\d+\.\d+\.\d+$")
        # 与规范 md 中声明的版本一致
        with open(SCHEMA_MD, encoding="utf-8") as f:
            md = f.read()
        self.assertIn(f"**版本：{RQ.SCHEMA_VERSION}**", md)


class TestProducerConformance(unittest.TestCase):
    """时间审计作为 reference producer，产出必须符合 AOS。"""

    def test_all_layers_conformant(self):
        opps = RQ.extract_opportunities(_sample_report(), layer="all")
        self.assertEqual(len(opps), 3)
        for opp in opps:
            _assert_conformant(self, opp)

    def test_layers_present(self):
        opps = RQ.extract_opportunities(_sample_report(), layer="all")
        self.assertEqual({o["layer"] for o in opps}, {"point", "line", "surface"})


if __name__ == "__main__":
    unittest.main()
