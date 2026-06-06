#!/usr/bin/env python3
"""
时间审计 v2 — MCP server

把"读报告文件"换成"Agent 直连查询"。让 Claude Desktop / Cursor 等 MCP 客户端里的
Agent 直接问"我该自动化什么"，而不是自己去翻 reports/*.json。

只读、本地、零网络。三个工具：
  - list_reports                     列出已有报告（轻量索引）
  - get_report_summary               单份报告概览（规模/app 分布/三层计数）
  - query_automation_opportunities   ⭐ 核心：按层/置信度/难度取自动化机会

所有取数逻辑在 core/report_query.py（纯函数、可离线测）。本文件只做 FastMCP 胶水。

依赖：mcp（可选安装）。装法：pip install -e ".[mcp]"
运行：time-audit-mcp   或   python -m time_audit.mcp_server
"""
import json
from enum import Enum
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # 给出可执行的下一步，而不是裸 traceback
    raise SystemExit(
        "未安装 MCP 依赖。请运行：pip install -e \".[mcp]\"\n"
        "（核心 CLI 不需要它；仅 MCP server 模式需要。）"
    )

from pydantic import BaseModel, Field, ConfigDict

from time_audit.core import report_query


mcp = FastMCP("time_audit_mcp")


# ── 枚举：约束入参取值 ───────────────────────────────────────────────
class Layer(str, Enum):
    POINT = "point"      # 单点低效动作
    LINE = "line"        # 跨 App 固定流程（最可 skill 化）
    SURFACE = "surface"  # 角色级工作模式
    ALL = "all"


class Level(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


# ── 共享：把逻辑层异常转成给 Agent 的可执行错误文本 ──────────────────
def _err(e: Exception) -> str:
    if isinstance(e, FileNotFoundError):
        return f"Error: {e}"
    if isinstance(e, ValueError):
        return f"Error: 入参不合法：{e}"
    return f"Error: 读取报告失败（{type(e).__name__}）：{e}"


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# ── 入参模型 ─────────────────────────────────────────────────────────
class ListReportsInput(BaseModel):
    """list_reports 入参。"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    limit: int = Field(default=20, description="最多返回几份报告", ge=1, le=100)
    offset: int = Field(default=0, description="跳过前 N 份（分页用）", ge=0)


class ReportSummaryInput(BaseModel):
    """get_report_summary 入参。"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    report_id: Optional[str] = Field(
        default=None,
        description="报告 id，如 '20260603_000631'。留空取最新一份。",
    )


class QueryOpportunitiesInput(BaseModel):
    """query_automation_opportunities 入参。"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    report_id: Optional[str] = Field(
        default=None, description="报告 id，留空取最新一份。")
    layer: Layer = Field(
        default=Layer.ALL,
        description="层级：point(单点) | line(跨App流程，最可自动化) | surface(角色级) | all")
    min_confidence: Optional[Level] = Field(
        default=None,
        description="只保留置信度 >= 此值的机会：low|med|high。缺置信度的项会被过滤掉。")
    max_difficulty: Optional[Level] = Field(
        default=None,
        description="只保留自动化难度 <= 此值的机会：low|med|high。仅作用于 line。")


# ── 工具 ─────────────────────────────────────────────────────────────
@mcp.tool(
    name="list_reports",
    annotations={
        "title": "列出时间审计报告",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def list_reports(params: ListReportsInput) -> str:
    """列出本机已生成的时间审计报告（轻量索引，不含洞察正文）。

    用于：Agent 先看有哪些报告、各自的时间范围与洞察数量，再决定深入查哪一份。
    最新的报告排在最前。

    Args:
        params (ListReportsInput):
            - limit (int): 最多返回几份，1-100，默认 20
            - offset (int): 分页偏移，默认 0

    Returns:
        str: JSON 字符串：
        {
          "total": int, "count": int, "offset": int, "has_more": bool,
          "reports": [
            {"report_id": str, "generated_at": str, "llm_model": str,
             "dry_run": bool, "day_range": str, "day_count": int,
             "session_count": int,
             "counts": {"points": int, "lines": int, "surfaces": int}}
          ]
        }
        出错时返回 "Error: <可执行的下一步>"。
    """
    try:
        reports_dir = report_query.resolve_reports_dir()
        return _dumps(report_query.list_reports_index(
            reports_dir, limit=params.limit, offset=params.offset))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="get_report_summary",
    annotations={
        "title": "时间审计报告概览",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def get_report_summary(params: ReportSummaryInput) -> str:
    """取单份报告的概览：数据规模、app 耗时分布、点/线/面计数（不含洞察正文）。

    用于：Agent 想先了解"这份报告覆盖了什么、用户时间花在哪、有多少机会"，
    再用 query_automation_opportunities 拉具体洞察。

    Args:
        params (ReportSummaryInput):
            - report_id (Optional[str]): 报告 id，留空取最新一份

    Returns:
        str: JSON 字符串：
        {
          "report_id": str, "generated_at": str, "llm_model": str, "dry_run": bool,
          "overall": {"raw_event_count": int, "session_count": int,
                      "day_count": int, "day_range": str, "active_hours": [int]},
          "app_breakdown": [{"app": str, "duration_minutes": num,
                             "duration_pct": num, "events": int}],
          "insight_counts": {"points": int, "lines": int, "surfaces": int}
        }
        找不到报告时返回 "Error: ...（含可用 id 或生成命令）"。
    """
    try:
        reports_dir = report_query.resolve_reports_dir()
        report = report_query.load_report(reports_dir, params.report_id)
        return _dumps(report_query.summarize_report(report))
    except Exception as e:
        return _err(e)


@mcp.tool(
    name="query_automation_opportunities",
    annotations={
        "title": "查询自动化机会",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def query_automation_opportunities(params: QueryOpportunitiesInput) -> str:
    """⭐ 核心工具：从报告里取出"该自动化什么"，按层级/置信度/难度过滤。

    这是时间审计作为"发现层"对 Agent 的主接口。每条机会带稳定编号(P-/L-/F-)
    和 evidence_sessions（可回溯证据），Agent 可据此决定创建哪个 skill / 自动化。

    典型用法：
      - "有哪些高置信度、易自动化的流程？" → layer=line, min_confidence=high, max_difficulty=low
      - "用户角色层面有什么洞察？"          → layer=surface
      - "全部机会"                          → layer=all

    Args:
        params (QueryOpportunitiesInput):
            - report_id (Optional[str]): 报告 id，留空取最新一份
            - layer (Layer): point | line | surface | all（默认 all）
            - min_confidence (Optional[Level]): low|med|high，保留 >= 此置信度
            - max_difficulty (Optional[Level]): low|med|high，仅过滤 line

    Returns:
        str: JSON 字符串：
        {
          "schema_version": str,   # Automation Opportunity Schema 版本，如 "0.1.0"
          "report_id": str,
          "produced_at": str,      # 产出时间（报告生成时间）
          "producer": str,         # 产出方标识，如 "time-audit/time-audit v2 (LLM-driven)"
          "filters": {"layer": str, "min_confidence": str|null, "max_difficulty": str|null},
          "count": int,
          "opportunities": [
            # 每条机会均带 fingerprint（跨报告稳定身份）+ id（报告内位置编号）
            # point: {id:"P-01", fingerprint:"fp_...", layer:"point", title, description,
            #         frequency_hint?, skill_suggestion?, confidence, evidence_sessions}
            # line:  {id:"L-01", fingerprint:"fp_...", layer:"line", workflow_name, trigger?,
            #         apps_involved?, occurrence_count?, avg_duration_min?,
            #         estimated_weekly_savings_min?, automation_difficulty?, skill_suggestion?,
            #         steps?, confidence, evidence_sessions}
            # surface:{id:"F-01", fingerprint:"fp_...", layer:"surface", insight_title,
            #         observation, implication?, recommendation?, confidence, evidence_sessions}
          ]
        }
        找不到报告时返回 "Error: ...（含可用 id 或生成命令）"。

    不要用于：触发新分析（本工具只读已有报告；跑新审计请用 CLI `time-audit --days N`）。
    """
    try:
        reports_dir = report_query.resolve_reports_dir()
        report = report_query.load_report(reports_dir, params.report_id)
        opps = report_query.extract_opportunities(
            report,
            layer=params.layer.value,
            min_confidence=params.min_confidence.value if params.min_confidence else None,
            max_difficulty=params.max_difficulty.value if params.max_difficulty else None,
        )
        return _dumps(report_query.build_envelope(
            report,
            opps,
            filters={
                "layer": params.layer.value,
                "min_confidence": params.min_confidence.value if params.min_confidence else None,
                "max_difficulty": params.max_difficulty.value if params.max_difficulty else None,
            },
            report_id=params.report_id or "",
        ))
    except Exception as e:
        return _err(e)


def main():
    """入口：stdio 传输（本地 MCP 客户端标准接法）。"""
    mcp.run()


if __name__ == "__main__":
    main()
