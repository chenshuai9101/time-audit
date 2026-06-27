"""
FDE 交付物生成器

将各阶段的结构化数据渲染为人类可读的 Markdown 文档（.md），
未来可扩展为 .docx / .html / .pptx 格式。
"""
import os
import json
from datetime import datetime
from typing import List, Dict, Optional


def _ensure_output_dir(cfg) -> str:
    """确保输出目录存在"""
    os.makedirs(cfg.output_dir, exist_ok=True)
    return cfg.output_dir


# ═════════════════════════════════════════════════════════════════════
# Phase 1: 现场发现报告
# ═════════════════════════════════════════════════════════════════════
def build_discovery_doc(cfg, pain_points: List[Dict], ctx: Dict) -> str:
    """生成 FDE Phase 1 交付物"""
    output_dir = _ensure_output_dir(cfg)
    path = os.path.join(output_dir, "01-fde-discovery.md")
    client_input = ctx.get("client_input", "")

    pain_rows = "\n".join(
        f"| {p.get('id', '?')} | {p.get('category', '-')} | "
        f"{p.get('description', '-')} | "
        f"{'⭐' * p.get('frequency', 3)} | "
        f"{'🔥' * p.get('impact', 3)} |"
        for p in pain_points
    )

    content = f"""# FDE 现场发现报告

> **项目**: {cfg.project_name or cfg.engagement_id}
> **客户**: {cfg.client_name} ({cfg.client_industry})
> **日期**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> **FDE 引擎**: time-audit + fde-agent-skill v1.0

---

## 1. 客户概览

- **客户名称**: {cfg.client_name or '待确认'}
- **所属行业**: {cfg.client_industry or '待确认'}
- **项目名称**: {cfg.project_name or '待确认'}
- **FDE Engagement ID**: `{cfg.engagement_id}`

---

## 2. 客户输入

{"```" if client_input else ""}
{client_input if client_input else "（无输入，使用默认痛点模板）"}
{"```" if client_input else ""}

---

## 3. 痛点矩阵

| ID | 类别 | 描述 | 频率 | 影响 |
|:--|:----|:----|:---:|:---:|
{pain_rows if pain_rows else '| — | — | 无痛点数据 | — | — |'}

### 评分规则
- **频率**: ⭐1-5（1=极少，5=每天多次）
- **影响**: 🔥1-5（1=轻度不便，5=关键流程阻塞）

---

## 4. FDE 可行性判断

- [ ] 问题可以通过技术手段解决
- [ ] 客户有足够的配合意愿
- [ ] 数据/系统可访问
- [ ] 预计 ROI 为正

---

## 5. 下一步

→ 进入 **Phase 2: 差距评估**，基于以上痛点生成自动化机会清单。
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ═════════════════════════════════════════════════════════════════════
# Phase 2: 差距评估报告
# ═════════════════════════════════════════════════════════════════════
def build_assessment_doc(cfg, opportunities: List[Dict], ctx: Dict) -> str:
    """生成 FDE Phase 2 交付物"""
    output_dir = _ensure_output_dir(cfg)
    path = os.path.join(output_dir, "02-fde-assessment.md")

    if not opportunities:
        opp_rows = "| — | — | — | — | — | — | — |"
    else:
        opp_rows = "\n".join(
            f"| {o.get('id', '?')} "
            f"| {o.get('layer', '?')} "
            f"| {o.get('description', '-')[:50]} "
            f"| {o.get('confidence', '?')} "
            f"| {o.get('difficulty', '?')} "
            f"| {o.get('estimated_weekly_savings_minutes', 0)}分钟 "
            f"| {o.get('source', '?')} |"
            for o in opportunities
        )

    content = f"""# FDE 差距评估报告

> **项目**: {cfg.project_name or cfg.engagement_id}
> **日期**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> **来源**: 现场发现报告 Phase 1 + 时间审计 MCP

---

## 1. 自动化机会清单

| ID | 层级 | 描述 | 置信度 | 难度 | 周节省 | 来源 |
|:--|:---|:----|:-----|:----|:-----|:----|
{opp_rows}

### 层级说明
- **点 (point)**：单次低效小动作，适合 alias/snippet
- **线 (line)**：跨系统固定流程，适合自动化 Skill ← **核心价值**
- **面 (surface)**：角色级工作模式，适合流程再造

---

## 2. ROI 汇总

| 指标 | 值 |
|:---|:---|
| 总机会数 | {len(opportunities)} |
| 高置信度机会 | {sum(1 for o in opportunities if o.get('confidence') == 'high')} |
| 线级机会 | {sum(1 for o in opportunities if o.get('layer') == 'line')} |
| 预计总周节省 | {sum(o.get('estimated_weekly_savings_minutes', 0) for o in opportunities)} 分钟 |

---

## 3. 时间审计集成

- **时间审计报告**: {ctx.get('time_audit_report_id', '未集成')}
- **MCP 工具**: list_reports / get_report_summary / query_automation_opportunities
- **数据源**: {' / '.join(ctx.get('sources', ['screenpipe', 'shell', 'claude', 'openclaw']))}

> 💡 如果未集成 time-audit，运行 `time-audit --days 14` 获取真实的自动化机会发现。

---

## 4. 下一步

→ 进入 **Phase 3: 架构设计**，为高优先级机会设计技术方案。
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ═════════════════════════════════════════════════════════════════════
# Phase 3: 架构设计报告
# ═════════════════════════════════════════════════════════════════════
def build_architecture_doc(cfg, architecture: Dict, ctx: Dict) -> str:
    """生成 FDE Phase 3 交付物"""
    output_dir = _ensure_output_dir(cfg)
    path = os.path.join(output_dir, "03-fde-architecture.md")

    # 组件表
    comp_rows = "\n".join(
        f"| {c.get('name', '?')} | {c.get('tech', '?')} | {c.get('description', '?')} |"
        for c in architecture.get("components", [])
    )

    # 里程碑
    mile_rows = "\n".join(
        f"| {m.get('phase', '?')} | {m.get('name', '?')} | {m.get('duration', '?')} | {m.get('deliverable', '?')} |"
        for m in architecture.get("milestones", [])
    )

    # 风险
    risk_rows = "\n".join(
        f"| {r.get('risk', '?')} | {r.get('mitigation', '?')} |"
        for r in architecture.get("risks", [])
    )

    content = f"""# FDE 架构设计报告

> **项目**: {cfg.project_name or cfg.engagement_id}
> **日期**: {architecture.get('design_date', datetime.now().strftime('%Y-%m-%d'))}
> **依据**: 差距评估 Phase 2 产出的自动化机会清单

---

## 1. 方案概览

{architecture.get('overview', '—')}

---

## 2. 优先自动化链路

| ID | 描述 | 周节省 | 难度 |
|:--|:----|:-----|:----|
"""
    for pl in architecture.get("priority_lines", []):
        content += f"| {pl['id']} | {pl['description'][:50]} | {pl['weekly_savings']}分钟 | {pl['difficulty']} |\n"

    content += f"""
---

## 3. 组件架构

| 组件 | 技术选型 | 职责 |
|:---|:--------|:----|
{comp_rows}

---

## 4. 架构图

{architecture.get('architecture_mermaid', '*未生成*')}

---

## 5. 技术栈

"""
    for category, techs in architecture.get("tech_stack", {}).items():
        content += f"- **{category}**: {', '.join(techs)}\n"

    content += f"""
---

## 6. 里程碑规划

| 阶段 | 名称 | 周期 | 交付物 |
|:---|:----|:---:|:-----|
{mile_rows}

---

## 7. 风险评估

| 风险 | 缓解方案 |
|:---|:--------|
{risk_rows}

---

## 8. 下一步

→ 进入 **Phase 4: 原型构建**，实现优先级最高的自动化链路。
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ═════════════════════════════════════════════════════════════════════
# Phase 4: 原型构建报告
# ═════════════════════════════════════════════════════════════════════
def build_prototype_doc(cfg, prototype: Dict, ctx: Dict) -> str:
    """生成 FDE Phase 4 交付物"""
    output_dir = _ensure_output_dir(cfg)
    path = os.path.join(output_dir, "04-fde-prototype.md")

    file_rows = "\n".join(
        f"| {f.get('path', '?')} | {f.get('purpose', '?')} |"
        for f in prototype.get("files", [])
    )

    test_rows = "\n".join(
        f"| {t.get('id', '?')} | {t.get('description', '?')} | {t.get('expected', '?')} |"
        for t in prototype.get("test_cases", [])
    )

    content = f"""# FDE 原型构建报告

> **项目**: {cfg.project_name or cfg.engagement_id}
> **日期**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> **依据**: 架构设计 Phase 3

---

## 1. 原型目录

**位置**: `{prototype.get('prototype_dir', '?')}`

| 文件 | 用途 |
|:---|:----|
{file_rows}

---

## 2. 核心工作流

| 步骤 | 操作 | 使用工具 |
|:---:|:----|:--------|
"""
    for wf in prototype.get("core_workflow", []):
        content += f"| {wf.get('step', '?')} | {wf.get('action', '?')} | {wf.get('tool', '?')} |\n"

    content += f"""
---

## 3. 测试用例

| ID | 描述 | 预期结果 |
|:--|:----|:--------|
{test_rows}

---

## 4. 环境准备

{prototype.get('setup_guide', '*未生成*')}

---

## 5. 下一步

→ 进入 **Phase 5: 交付交接**，打包交付证据包并完成知识转移。
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ═════════════════════════════════════════════════════════════════════
# Phase 5: 交付交接包
# ═════════════════════════════════════════════════════════════════════
def build_handoff_package(cfg, state, package: Dict) -> str:
    """生成 FDE Phase 5 交付物——最终交付证据包"""
    output_dir = _ensure_output_dir(cfg)
    path = os.path.join(output_dir, "05-fde-handoff.md")

    doc_rows = "\n".join(
        f"| {d.get('title', '?')} | {d.get('content', '?')} |"
        for d in package.get("handoff_docs", [])
    )

    metrics = package.get("metrics", {})

    content = f"""# FDE 交付证据包

> **项目**: {package.get('project', cfg.project_name or cfg.engagement_id)}
> **客户**: {package.get('client', cfg.client_name)}
> **交付日期**: {package.get('delivery_date', datetime.now().strftime('%Y-%m-%d'))}
> **FDE Engagement ID**: `{package.get('engagement_id', cfg.engagement_id)}`

---

## 1. 执行摘要

{package.get('summary', '—')}

---

## 2. 项目度量

| 指标 | 值 |
|:---|:---|
| 计划阶段数 | {metrics.get('total_phases', 5)} |
| 完成阶段数 | {metrics.get('completed_phases', '—')} |
| 交付物数量 | {metrics.get('deliverable_count', '—')} |

---

## 3. 交付物清单

| 文件 | 说明 |
|:---|:----|
"""
    # 列出所有已完成阶段的交付物
    for p in state.phases:
        if p.deliverable_path and os.path.exists(p.deliverable_path):
            content += f"| `{p.deliverable_path}` | Phase {p.phase}: {p.name} |\n"

    content += f"""
---

## 4. 交接文档清单

| 文档 | 内容摘要 |
|:---|:--------|
{doc_rows if doc_rows else '| — | — |'}

---

## 5. 后续建议

"""
    for step in package.get("next_steps", []):
        content += f"{step}\n"

    content += f"""

---

## 6. 阶段详情

"""
    for p in state.phases:
        icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}
        content += f"- {icon.get(p.status, '❓')} **Phase {p.phase}: {p.name}** — *{p.status}*\n"
        if p.started_at:
            content += f"  - 开始: {p.started_at}\n"
        if p.completed_at:
            content += f"  - 完成: {p.completed_at}\n"

    content += """

---

> 📋 本交付证据包由 **fde-agent-skill v1.0** 自动生成
> 🎯 如需后续支持，请运行 `time-audit fde resume`
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    # 同时生成一份索引文件
    _build_index(cfg, state)
    return path


def _build_index(cfg, state):
    """生成 FDE 项目索引文件"""
    output_dir = _ensure_output_dir(cfg)
    path = os.path.join(output_dir, "README.md")

    lines = [
        f"# FDE 交付项目: {cfg.project_name or cfg.engagement_id}",
        "",
        f"**客户**: {cfg.client_name} ({cfg.client_industry})",
        f"**Engagement ID**: `{cfg.engagement_id}`",
        f"**创建时间**: {state.created_at}",
        f"**最后更新**: {state.updated_at}",
        "",
        "## 交付物索引",
        "",
    ]

    phase_docs = {
        1: ("01-fde-discovery.md", "现场发现报告"),
        2: ("02-fde-assessment.md", "差距评估报告"),
        3: ("03-fde-architecture.md", "架构设计报告"),
        4: ("04-fde-prototype.md", "原型构建报告"),
        5: ("05-fde-handoff.md", "交付交接包"),
    }

    for i, (phase_num, (filename, desc)) in enumerate(phase_docs.items(), 1):
        p = state.phases[phase_num - 1]
        icon = {"completed": "✅", "pending": "⏳", "running": "🔄", "failed": "❌"}
        full_path = os.path.join(output_dir, filename)
        if os.path.exists(full_path):
            lines.append(f"- {icon.get(p.status, '❓')} `{filename}` — {desc}")
        else:
            lines.append(f"- {icon.get(p.status, '⏳')} `{filename}` — {desc} *（未生成）*")

    lines.extend([
        "",
        "---",
        f"由 fde-agent-skill v1.0 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
