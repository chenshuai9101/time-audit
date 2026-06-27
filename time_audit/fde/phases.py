"""
FDE 五阶段核心逻辑

每个阶段函数接收输入、执行分析、返回结构化输出。
设计原则：
  - 纯函数（输入→输出，无副作用）
  - 可独立测试
  - LLM 调用封装为可替换的策略
"""
import os
from datetime import datetime
from typing import List, Dict, Optional


# ═════════════════════════════════════════════════════════════════════
# Phase 1: 现场发现
# ═════════════════════════════════════════════════════════════════════
def run_discovery(client_input: str, cfg) -> List[Dict]:
    """Phase 1 核心：从客户描述中提取痛点矩阵

    Args:
        client_input: 客户输入（背景、目标、痛点描述）
        cfg: FDEConfig 对象

    Returns:
        痛点列表 [{"id": "P1", "category": "效率", "description": "...", "frequency": 5, "impact": 4}]
    """
    pain_points = _extract_pain_points(client_input)
    if not pain_points:
        pain_points = _default_pain_points()
    return pain_points


def _extract_pain_points(text: str) -> List[Dict]:
    """从客户描述中提取结构化痛点。
    实际使用时由 LLM 执行；此处为结构化协议。
    """
    if not text.strip():
        return []
    # LLM 调用位置：将 text 喂给 LLM，返回 JSON 格式的痛点评分列表
    return []


def _default_pain_points() -> List[Dict]:
    """没有输入时生成默认模板（让用户修改而非从零开始）"""
    return [
        {"id": "P1", "category": "效率", "description": "重复性手工操作频繁，多系统间切换耗时",
         "frequency": 4, "impact": 4, "details": ""},
        {"id": "P2", "category": "数据", "description": "数据分散在多个平台/文件，缺乏统一视图",
         "frequency": 5, "impact": 3, "details": ""},
        {"id": "P3", "category": "质量", "description": "人工操作引入的差错难以追踪和归因",
         "frequency": 3, "impact": 5, "details": ""},
    ]


# ═════════════════════════════════════════════════════════════════════
# Phase 2: 差距评估
# ═════════════════════════════════════════════════════════════════════
def run_assessment(
    pain_points: List[Dict],
    cfg,
    time_audit_opportunities: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Phase 2 核心：痛点到自动化机会的映射

    融合两个来源：
      1. 客户痛点（上阶段产出）
      2. time-audit 发现的自动化机会（如已集成）

    Returns:
        自动化机会清单（AOS schema 兼容）
        每条含: layer(P/L/F), id, 描述, 置信度, 难度, 预计周节省(分钟), 建议动作
    """
    opportunities = []

    # 来源A：时间审计数据（最可信）
    if time_audit_opportunities:
        for opp in time_audit_opportunities:
            opportunities.append(_normalize_opportunity(opp, source="time-audit"))

    # 来源B：客户痛点（需 LLM 分析）
    for pp in pain_points:
        opps = _pain_to_opportunities(pp)
        opportunities.extend(opps)

    # 去重 + 排序（置信度降序 → ROI 降序）
    opportunities = _dedupe_and_rank(opportunities)
    return opportunities


def _normalize_opportunity(raw: Dict, source: str = "time-audit") -> Dict:
    """统一时间审计产出的机会格式"""
    return {
        "id": raw.get("id", "?"),
        "layer": raw.get("layer", "line"),
        "description": raw.get("description", raw.get("title", "")),
        "confidence": raw.get("confidence", "med"),
        "difficulty": raw.get("automation_difficulty", raw.get("difficulty", "med")),
        "estimated_weekly_savings_minutes": raw.get("estimated_weekly_savings_minutes",
                                                     raw.get("estimated_savings_minutes", 0)),
        "steps": raw.get("steps", []),
        "evidence": raw.get("evidence_sessions", []),
        "source": source,
        "suggestion": raw.get("suggestion", ""),
    }


def _pain_to_opportunities(pain_point: Dict) -> List[Dict]:
    """将单个痛点映射为 0-N 个自动化机会。
    实际由 LLM 推理。
    """
    return []


def _dedupe_and_rank(opportunities: List[Dict]) -> List[Dict]:
    """去重（按描述相似度）并按置信度×ROI 排序"""
    seen = set()
    uniq = []
    for opp in opportunities:
        key = opp["description"][:60]
        if key in seen:
            continue
        seen.add(key)

        # 置信度分值的映射
        conf_score = {"high": 3, "med": 2, "low": 1}.get(opp.get("confidence", "med"), 2)
        savings = opp.get("estimated_weekly_savings_minutes", 0) or 0
        opp["_score"] = conf_score * (1 + savings / 60)
        uniq.append(opp)

    uniq.sort(key=lambda x: x["_score"], reverse=True)
    for opp in uniq:
        opp.pop("_score", None)
    return uniq


# ═════════════════════════════════════════════════════════════════════
# Phase 3: 架构设计
# ═════════════════════════════════════════════════════════════════════
def run_architecture(opportunities: List[Dict], cfg) -> Dict:
    """Phase 3 核心：机会清单 → 技术方案设计

    Returns:
        architecture dict:
          { overview, components: [{name, tech, description}],
            architecture_mermaid, milestones, risks, tech_stack }
    """
    # 从机会清单中提取关键链路
    top_lines = [o for o in opportunities if o.get("layer") == "line"][:3]

    architecture = {
        "design_date": datetime.now().strftime("%Y-%m-%d"),
        "overview": "基于差距评估识别的自动化机会，设计面向 FDE 的技术架构",
        "priority_lines": [
            {
                "id": o["id"],
                "description": o["description"],
                "weekly_savings": o.get("estimated_weekly_savings_minutes", 0),
                "difficulty": o.get("difficulty", "med"),
            }
            for o in top_lines
        ],
        "components": [
            {"name": "AI Agent 层", "tech": "OpenClaw / LangChain",
             "description": "Agent 技能编排与执行，负责跨系统自动化流程的调用链"},
            {"name": "数据接入层", "tech": "时间审计 MCP + 源适配器",
             "description": "从客户现有系统（HIS/CRM/ERP）采集行为数据与工作流上下文"},
            {"name": "LLM 推理层", "tech": f"{cfg.llm_provider} ({cfg.llm_model})",
             "description": "本地或云端大模型驱动语义分析、方案生成与代码构建"},
            {"name": "交付输出层", "tech": "Markdown / DOCX / Mermaid",
             "description": "结构化文档与架构图输出，支持交付证据包一键生成"},
        ],
        "architecture_mermaid": _generate_architecture_mermaid(top_lines),
        "tech_stack": {
            "前端/工具": ["Python 3.8+", "Ollama", "MCP SDK"],
            "LLM": [f"{cfg.llm_provider}/{cfg.llm_model}"],
            "数据": ["SQLite (time-audit 自有)", "客户系统 API"],
            "交付": ["Markdown", "python-pptx (可选)", "Mermaid"],
        },
        "milestones": _default_milestones(),
        "risks": [
            {"risk": "客户数据隐私限制", "mitigation": "本地模型优先，数据不离机（时间审计原生支持）"},
            {"risk": "现有系统 API 不开放", "mitigation": "屏幕录制 OCR 回退方案（Screenpipe 适配器）"},
            {"risk": "自动化 ROI 不达预期", "mitigation": "先运行 time-audit 探测实际频率再立项"},
        ],
    }
    return architecture


def _generate_architecture_mermaid(top_lines: List[Dict]) -> str:
    """生成 FDE 项目架构的 Mermaid 图"""
    lines = [
        "```mermaid",
        "graph TD",
        "    subgraph \"🏢 客户现场\"",
        "        A[现有系统] --> B[时间审计<br>行为采集]",
        "        C[人工流程] --> B",
        "    end",
        "    subgraph \"⚙️ FDE 引擎层\"",
        "        B --> D[发现层<br>点/线/面分析]",
        "        D --> E[差距评估]",
        "        E --> F[方案架构]",
        "        F --> G[原型构建]",
        "    end",
        "    subgraph \"📦 交付输出\"",
        "        G --> H[自动化 Skill]",
        "        G --> I[交付证据包]",
        "        G --> J[运维文档]",
        "    end",
        "    H --> A",
    ]
    # 为每条 top line 加一条边
    for i, o in enumerate(top_lines):
        safe_id = o["id"].replace("-", "_")
        desc = o["description"][:20]
        lines.append(f'        E -->|"{i+1}. {desc}"| L{safe_id}[{o["id"]}]')
        lines.append(f'        L{safe_id} --> F')

    lines.append("```")
    return "\n".join(lines)


def _default_milestones() -> List[Dict]:
    return [
        {"phase": "Phase 1", "name": "现场发现", "duration": "1 周",
         "deliverable": "现场发现报告 + 痛点矩阵"},
        {"phase": "Phase 2", "name": "差距评估", "duration": "1 周",
         "deliverable": "自动化机会清单 + ROI"},
        {"phase": "Phase 3", "name": "架构设计", "duration": "1 周",
         "deliverable": "技术方案 + 架构图"},
        {"phase": "Phase 4", "name": "原型构建", "duration": "2 周",
         "deliverable": "可运行原型 + 测试"},
        {"phase": "Phase 5", "name": "交付交接", "duration": "1 周",
         "deliverable": "交付证据包 + 交接文档"},
    ]


# ═════════════════════════════════════════════════════════════════════
# Phase 4: 原型构建
# ═════════════════════════════════════════════════════════════════════
def run_prototype(architecture: Dict, cfg) -> Dict:
    """Phase 4 核心：架构 → 最小原型

    Returns:
        prototype dict:
          { prototype_dir, files: [{path, purpose}],
            core_workflow, test_cases, setup_guide }
    """
    # + 使用场景：根据架构设计生成原型文件
    proto_dir = os.path.expanduser(
        f"~/Desktop/fde-prototype-{cfg.engagement_id}/"
    )

    prototype = {
        "prototype_dir": proto_dir,
        "generated_at": datetime.now().isoformat(),
        "core_workflow": _generate_core_workflow(architecture),
        "files": _generate_prototype_files(architecture, proto_dir),
        "test_cases": _generate_test_cases(architecture),
        "setup_guide": _generate_setup_guide(architecture, cfg),
    }
    return prototype


def _generate_core_workflow(arch: Dict) -> List[Dict]:
    return [
        {"step": 1, "action": "采集客户数据", "tool": "时间审计 MCP / 源适配器"},
        {"step": 2, "action": "运行点/线/面分析", "tool": "time-audit LLM Analyzer"},
        {"step": 3, "action": "构建自动化 Skill", "tool": "FDE Phase 4 原型引擎"},
        {"step": 4, "action": "验证交付物", "tool": "FDE 自检清单"},
    ]


def _generate_prototype_files(arch: Dict, proto_dir: str) -> List[Dict]:
    return [
        {"path": f"{proto_dir}/fde_agent.py", "purpose": "FDE Agent 主入口"},
        {"path": f"{proto_dir}/discovery.py", "purpose": "现场发现模块"},
        {"path": f"{proto_dir}/assessment.py", "purpose": "差距评估模块"},
        {"path": f"{proto_dir}/deliver.py", "purpose": "交付生成模块"},
        {"path": f"{proto_dir}/requirements.txt", "purpose": "依赖清单"},
        {"path": f"{proto_dir}/README.md", "purpose": "使用说明"},
    ]


def _generate_test_cases(arch: Dict) -> List[Dict]:
    return [
        {"id": "T1", "description": "客户需求输入 → 正确提取痛点", "expected": "≥3 个痛点"},
        {"id": "T2", "description": "痛点 → 自动化机会映射", "expected": "每条痛点映射到机会"},
        {"id": "T3", "description": "交付文档生成", "expected": "文档完整可读"},
    ]


def _generate_setup_guide(arch: Dict, cfg) -> str:
    return f"""## 环境准备

1. 安装依赖: `pip install time-audit`
2. 启动 Ollama: `ollama serve &`
3. 拉取模型: `ollama pull {cfg.llm_model}`
4. 运行 FDE: `time-audit fde run --client "客户名称"`
"""


# ═════════════════════════════════════════════════════════════════════
# Phase 5: 交付交接
# ═════════════════════════════════════════════════════════════════════
def run_handoff(state, cfg) -> Dict:
    """Phase 5 核心：汇总全阶段产出 → 交付证据包

    Returns:
        handoff package: { summary, deliverables, metrics,
                           handoff_docs: [{title, content}], next_steps }
    """
    package = {
        "engagement_id": cfg.engagement_id,
        "client": f"{cfg.client_name} ({cfg.client_industry})",
        "project": cfg.project_name,
        "delivery_date": datetime.now().strftime("%Y-%m-%d"),
        "summary": _build_handoff_summary(state),
        "metrics": _build_metrics(state),
        "handoff_docs": [
            {"title": "系统架构", "content": "参见 FDE 架构设计文档"},
            {"title": "部署步骤", "content": "1. 安装依赖 → 2. 配置环境 → 3. 启动服务"},
            {"title": "运维指南", "content": "日常检查项：日志、LLM 连接、存储"},
            {"title": "常见问题", "content": "Q: LLM 响应慢 → A: 检查本地模型或切换到云端"},
            {"title": "关键决策记录", "content": "ADR-001: 选用本地模型保护客户数据隐私"},
        ],
        "next_steps": [
            "✅ 第一阶段 FDE 交付完成",
            "→ 建议 2 周后回访，评估自动化实际采纳率",
            "→ 可扩展到阶段二：覆盖更多自动化流程",
        ],
    }
    return package


def _build_handoff_summary(state) -> str:
    phases = state.phases
    completed = sum(1 for p in phases if p.status == "completed")
    return f"FDE 项目于 {state.created_at} 启动，{completed}/5 阶段完成。交付包内含各阶段完整结构化文档。"


def _build_metrics(state) -> Dict:
    completed_phases = [p for p in state.phases if p.status == "completed"]
    return {
        "total_phases": 5,
        "completed_phases": len(completed_phases),
        "total_duration_days": "—",
        "deliverable_count": len([p for p in completed_phases if p.deliverable_path]),
    }
