"""
FDE MCP 工具扩展

定义 FDE 专属的 MCP 工具，供 Agent（Claude Desktop / Cursor / OpenClaw）直连调用。
作为 time-audit MCP Server 的热插拔扩展。

工具清单：

  fde.create_engagement     → 创建 FDE 项目
  fde.list_engagements      → 列出本地 FDE 项目
  fde.get_engagement_status → 查看项目状态
  fde.run_phase             → 执行指定阶段
  fde.run_all               → 一键跑全流程
  fde.get_deliverable       → 获取阶段交付物内容
"""
import os
import json
import glob
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

# 延迟导入（避免运行时依赖 time_audit）
_FDE_ENGINE = None


def _get_engine():
    global _FDE_ENGINE
    if _FDE_ENGINE is None:
        from time_audit.fde.engine import create_engagement, load_engagement
        _FDE_ENGINE = {"create": create_engagement, "load": load_engagement}
    return _FDE_ENGINE


FDE_STATE_DIR = os.path.expanduser("~/Desktop/fde-engagements/")


# ── 入参模型 ─────────────────────────────────────────────────────────
class CreateEngagementInput(BaseModel):
    """create_engagement 入参"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    client_name: str = Field(default="", description="客户名称")
    client_industry: str = Field(default="", description="客户所属行业")
    project_name: str = Field(default="", description="项目名称")
    description: str = Field(default="", description="项目描述/客户输入的背景")


class ListEngagementsInput(BaseModel):
    """list_engagements 入参"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit: int = Field(default=10, description="最多返回几个项目", ge=1, le=50)


class RunPhaseInput(BaseModel):
    """run_phase 入参"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    engagement_id: str = Field(description="FDE 项目 ID (目录名)")
    phase: int = Field(description="阶段号 1-5", ge=1, le=5)
    context: str = Field(default="{}", description="阶段上下文 JSON 字符串")


class RunAllInput(BaseModel):
    """run_all 入参"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    engagement_id: str = Field(description="FDE 项目 ID (目录名)")
    client_input: str = Field(default="", description="客户输入（Phase 1 用）")


class GetStatusInput(BaseModel):
    """get_engagement_status 入参"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    engagement_id: str = Field(description="FDE 项目 ID (目录名)")


class GetDeliverableInput(BaseModel):
    """get_deliverable 入参"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    engagement_id: str = Field(description="FDE 项目 ID")
    phase: int = Field(description="阶段号 1-5", ge=1, le=5)


# ── 工具定义 ─────────────────────────────────────────────────────────
def init_mcp_tools(mcp):
    """注册所有 FDE 工具到 MCP server 实例。

    用法：
        from time_audit.fde.mcp_tools import init_mcp_tools
        init_mcp_tools(mcp)   # 在你的 MCP server 创建后调用
    """

    @mcp.tool(
        name="fde_create_engagement",
        annotations={
            "title": "创建 FDE 项目",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
        },
    )
    def create_engagement(params: CreateEngagementInput) -> str:
        """创建新的 FDE（Forward Deployed Engineering）项目。

        FDE 项目将客户的企业 AI 落地需求拆解为 5 阶段：
          1. 现场发现 → 2. 差距评估 → 3. 架构设计 → 4. 原型构建 → 5. 交付交接

        Args:
            params (CreateEngagementInput):
                - client_name (str): 客户名称
                - client_industry (str): 客户行业（如"医疗/制造/金融"）
                - project_name (str): 项目名称
                - description (str): 客户输入的背景/需求/痛点

        Returns:
            str: 创建成功的项目概要（JSON 格式）
        """
        try:
            eng = _get_engine()["create"](
                client_name=params.client_name,
                client_industry=params.client_industry,
                project_name=params.project_name,
            )
            # 如有上下文，保存到临时文件供 Phase 1 使用
            if params.description:
                ctx_path = os.path.join(eng.config.output_dir, ".client_input.txt")
                os.makedirs(eng.config.output_dir, exist_ok=True)
                with open(ctx_path, "w", encoding="utf-8") as f:
                    f.write(params.description)

            return json.dumps({
                "engagement_id": eng.config.engagement_id,
                "output_dir": eng.config.output_dir,
                "status": "created",
                "phases": [f"Phase {p.phase}: {p.name}" for p in eng.state.phases],
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Error: 创建失败 — {e}"

    @mcp.tool(
        name="fde_list_engagements",
        annotations={
            "title": "列出 FDE 项目",
            "readOnlyHint": True,
            "destructiveHint": False,
        },
    )
    def list_engagements(params: ListEngagementsInput) -> str:
        """列出本机已有的 FDE 项目。

        Returns:
            str: 项目列表（按最后修改时间倒序）
        """
        engagements = []
        pattern = os.path.join(FDE_STATE_DIR, "*/fde_state.json")
        for state_path in sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True):
            try:
                with open(state_path, encoding="utf-8") as f:
                    data = json.load(f)
                cfg = data.get("config", {})
                phases = data.get("phases", [])
                completed = sum(1 for p in phases if p.get("status") == "completed")
                engagements.append({
                    "id": cfg.get("engagement_id", os.path.basename(os.path.dirname(state_path))),
                    "client": f"{cfg.get('client_name', '?')} ({cfg.get('client_industry', '?')})",
                    "project": cfg.get("project_name", "未命名"),
                    "phases": f"{completed}/5",
                    "updated": data.get("updated_at", ""),
                })
            except Exception:
                continue

        return json.dumps({
            "count": len(engagements[:params.limit]),
            "engagements": engagements[:params.limit],
        }, ensure_ascii=False, indent=2)

    @mcp.tool(
        name="fde_get_engagement_status",
        annotations={
            "title": "查看 FDE 项目状态",
            "readOnlyHint": True,
        },
    )
    def get_engagement_status(params: GetStatusInput) -> str:
        """查看指定 FDE 项目的当前状态。

        Args:
            params (GetStatusInput):
                - engagement_id (str): FDE 项目 ID

        Returns:
            str: 项目当前状态概览
        """
        try:
            state_path = os.path.join(FDE_STATE_DIR, params.engagement_id, "fde_state.json")
            if not os.path.exists(state_path):
                return f"Error: 项目 '{params.engagement_id}' 不存在"
            from time_audit.fde.engine import load_engagement
            eng = load_engagement(state_path)
            return eng.get_status_text()
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool(
        name="fde_run_phase",
        annotations={
            "title": "执行 FDE 阶段",
            "readOnlyHint": False,
            "destructiveHint": False,
        },
    )
    def run_phase(params: RunPhaseInput) -> str:
        """执行 FDE 项目的指定阶段。

        Args:
            params (RunPhaseInput):
                - engagement_id (str): FDE 项目 ID
                - phase (int): 阶段号 1(现场发现) / 2(差距评估) / 3(架构设计) / 4(原型构建) / 5(交付交接)
                - context (str, optional): 阶段上下文的 JSON 字符串

        Returns:
            str: 执行结果
        """
        try:
            state_path = os.path.join(FDE_STATE_DIR, params.engagement_id, "fde_state.json")
            if not os.path.exists(state_path):
                return f"Error: 项目 '{params.engagement_id}' 不存在"
            from time_audit.fde.engine import load_engagement
            eng = load_engagement(state_path)

            ctx = json.loads(params.context) if params.context.strip() else {}
            result = eng.run_phase(params.phase, ctx)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            return f"Error: Phase {params.phase} 执行失败 — {e}"

    @mcp.tool(
        name="fde_run_all",
        annotations={
            "title": "一键执行全流程",
            "readOnlyHint": False,
            "destructiveHint": False,
        },
    )
    def run_all(params: RunAllInput) -> str:
        """一键执行 FDE 全流程（Phase 1-5 顺序执行）。

        适合已有完整客户输入的场景。先创建项目再执行。

        Args:
            params (RunAllInput):
                - engagement_id (str): FDE 项目 ID
                - client_input (str, optional): 客户输入描述

        Returns:
            str: 全流程执行结果摘要
        """
        try:
            state_path = os.path.join(FDE_STATE_DIR, params.engagement_id, "fde_state.json")
            if not os.path.exists(state_path):
                return f"Error: 项目 '{params.engagement_id}' 不存在"
            from time_audit.fde.engine import load_engagement
            eng = load_engagement(state_path)

            context = {
                "phase_1": {"client_input": params.client_input},
            }
            results = eng.run_all(context)
            return json.dumps({
                "status": "completed",
                "output_dir": eng.config.output_dir,
                "phases": {
                    k: {
                        "status": "completed" if v.get("deliverable_path") else "failed",
                        "deliverable": v.get("deliverable_path", ""),
                    }
                    for k, v in results.items()
                },
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Error: 全流程执行失败 — {e}"

    @mcp.tool(
        name="fde_get_deliverable",
        annotations={
            "title": "获取 FDE 阶段交付物",
            "readOnlyHint": True,
        },
    )
    def get_deliverable(params: GetDeliverableInput) -> str:
        """读取 FDE 项目某阶段的交付物内容。

        Args:
            params (GetDeliverableInput):
                - engagement_id (str): FDE 项目 ID
                - phase (int): 阶段号 1-5

        Returns:
            str: 交付物 Markdown 内容
        """
        try:
            phase_docs = {1: "01", 2: "02", 3: "03", 4: "04", 5: "05"}
            prefix = phase_docs.get(params.phase, "01")
            pattern = os.path.join(FDE_STATE_DIR, params.engagement_id, f"{prefix}*.md")
            files = glob.glob(pattern)
            if not files:
                return f"Error: 项目 '{params.engagement_id}' Phase {params.phase} 交付物不存在"

            with open(files[0], encoding="utf-8") as f:
                content = f.read()
            return content[:5000] + ("\n\n...（内容较长，已截断）" if len(content) > 5000 else "")
        except Exception as e:
            return f"Error: {e}"

    return mcp
