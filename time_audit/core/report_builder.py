"""
时间审计 v2 — 报告构建器

不再计算任何东西，只做两件事：
  1. 把 LLM 输出（点/线/面）+ 元数据 + sessions 拼成结构化 JSON
  2. 渲染人类可读的 Markdown 摘要
"""
import os
import json
from datetime import datetime
from typing import List, Dict


def build_report(report_id: str, llm_result: dict, sessions: list,
                 app_freq: dict, hours: list, events_total: int,
                 model_name: str, dry_run: bool, keep_raw: bool) -> dict:
    """构建完整结构化报告"""
    days = sorted({s["day"] for s in sessions}) if sessions else []

    report = {
        "report_meta": {
            "id": report_id,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine_version": "time-audit v2 (LLM-driven)",
            "llm_model": model_name if not dry_run else "(dry-run, no LLM)",
            "dry_run": dry_run,
        },
        "overall": {
            "raw_event_count": events_total,
            "session_count": len(sessions),
            "day_count": len(days),
            "day_range": f"{days[0]} ~ {days[-1]}" if days else "",
            "active_hours": hours,
        },
        "app_breakdown": app_freq.get("top_apps", []),
        "ai_insights": {
            "points": llm_result.get("points", []),
            "lines": llm_result.get("lines", []),
            "surfaces": llm_result.get("surfaces", []),
        },
    }

    if keep_raw:
        report["raw_sessions"] = sessions

    return report


def save_report(report: dict, output_dir: str) -> dict:
    """落盘 JSON + MD，返回路径字典"""
    os.makedirs(output_dir, exist_ok=True)
    rid = report["report_meta"]["id"]

    json_path = os.path.join(output_dir, f"report_{rid}.json")
    md_path = os.path.join(output_dir, f"report_{rid}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_render_markdown(report))

    return {"json": json_path, "md": md_path}


def _render_markdown(report: dict) -> str:
    meta = report["report_meta"]
    overall = report["overall"]
    insights = report["ai_insights"]

    lines = [
        f"# 时间审计分析报告 · {meta['id']}",
        "",
        f"- 生成时间：{meta['generated_at']}",
        f"- 引擎版本：{meta['engine_version']}",
        f"- LLM 模型：{meta['llm_model']}",
        f"- 时间跨度：{overall['day_range']} ({overall['day_count']} 天)",
        f"- 数据规模：{overall['raw_event_count']} 原始事件 → {overall['session_count']} 会话",
        f"- 活跃时段：{', '.join(f'{h}:00' for h in overall['active_hours']) or '—'}",
        "",
        "## 应用耗时分布（Top）",
        "",
    ]
    for a in (report.get("app_breakdown") or [])[:8]:
        lines.append(
            f"- {a['app']}: {a['duration_minutes']} 分钟 "
            f"({a['duration_pct']}%) · 事件 {a['events']}"
        )
    lines.append("")

    if meta.get("dry_run"):
        lines.extend([
            "## ⚠️ Dry-run 模式",
            "",
            "本次未调用 LLM。要获得点/线/面分析，请：",
            "  1. `brew install ollama && ollama serve`",
            "  2. `ollama pull qwen2.5:14b`（或修改 config 中的 model）",
            "  3. 重新运行 `python -m time_audit`",
            "",
        ])

    # 点
    lines.append("## 🎯 点 — 单点低效动作")
    lines.append("")
    points = insights.get("points") or []
    if not points:
        lines.append("（未发现明显的单点低效）")
    for i, p in enumerate(points, 1):
        lines.extend(_render_point(i, p))
    lines.append("")

    # 线
    lines.append("## 🔁 线 — 跨App固定流程")
    lines.append("")
    plines = insights.get("lines") or []
    if not plines:
        lines.append("（未发现明显的跨App重复流程）")
    for i, l in enumerate(plines, 1):
        lines.extend(_render_line(i, l))
    lines.append("")

    # 面
    lines.append("## 🪞 面 — 角色级工作模式")
    lines.append("")
    surfaces = insights.get("surfaces") or []
    if not surfaces:
        lines.append("（未给出工作方式洞察）")
    for i, s in enumerate(surfaces, 1):
        lines.extend(_render_surface(i, s))
    lines.append("")

    lines.extend([
        "---",
        "",
        "> 时间审计 v2 — 本地 LLM 行为分析中间件",
        "> 报告供 Agent（牧云野/OpenClaw/Claude）决策使用，本身不包含可执行代码",
    ])
    return "\n".join(lines)


def _render_point(idx: int, p: dict) -> list:
    return [
        f"### P-{idx:02d} {p.get('title', '(无标题)')} · 置信度 {p.get('confidence', '?')}",
        "",
        f"- 描述：{p.get('description', '')}",
        f"- 频次：{p.get('frequency_hint', '')}",
        f"- 建议：{p.get('skill_suggestion', '')}",
        f"- 证据：{', '.join(p.get('evidence_sessions', []))}",
        "",
    ]


def _render_line(idx: int, l: dict) -> list:
    steps = l.get("steps") or []
    step_block = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
    return [
        f"### L-{idx:02d} {l.get('workflow_name', '(无名)')} · "
        f"难度 {l.get('automation_difficulty', '?')} · "
        f"置信度 {l.get('confidence', '?')}",
        "",
        f"- 触发：{l.get('trigger', '')}",
        f"- 涉及应用：{', '.join(l.get('apps_involved', []))}",
        f"- 重复次数：{l.get('occurrence_count', '?')}",
        f"- 单次耗时：约 {l.get('avg_duration_min', '?')} 分钟",
        f"- 预计周节省：{l.get('estimated_weekly_savings_min', '?')} 分钟",
        f"- 建议：{l.get('skill_suggestion', '')}",
        f"- 证据：{', '.join(l.get('evidence_sessions', []))}",
        f"- 步骤：",
        step_block if steps else "  （无）",
        "",
    ]


def _render_surface(idx: int, s: dict) -> list:
    return [
        f"### F-{idx:02d} {s.get('insight_title', '(无标题)')} · 置信度 {s.get('confidence', '?')}",
        "",
        f"- 现象：{s.get('observation', '')}",
        f"- 含义：{s.get('implication', '')}",
        f"- 建议：{s.get('recommendation', '')}",
        f"- 证据：{', '.join(s.get('evidence_sessions', []))}",
        "",
    ]


def present_console_summary(report: dict) -> None:
    """控制台终端摘要（给运行时间审计的人看）"""
    insights = report["ai_insights"]
    p_n = len(insights.get("points") or [])
    l_n = len(insights.get("lines") or [])
    f_n = len(insights.get("surfaces") or [])

    print("\n" + "═" * 60)
    print("  📋 时间审计 → Agent 行为洞察摘要")
    print("═" * 60)
    print(f"  点（单点低效）   : {p_n}")
    print(f"  线（固定流程）   : {l_n}")
    print(f"  面（工作方式）   : {f_n}")

    for i, p in enumerate((insights.get("points") or [])[:3], 1):
        print(f"\n  🎯 P-{i:02d} {p.get('title', '')}")
        print(f"     {p.get('description', '')[:60]}")
        print(f"     建议: {p.get('skill_suggestion', '')[:60]}")

    for i, l in enumerate((insights.get("lines") or [])[:3], 1):
        print(f"\n  🔁 L-{i:02d} {l.get('workflow_name', '')}")
        print(f"     {l.get('occurrence_count', '?')} 次, "
              f"周省 {l.get('estimated_weekly_savings_min', '?')} 分钟")
        print(f"     建议: {l.get('skill_suggestion', '')[:60]}")

    for i, s in enumerate((insights.get("surfaces") or [])[:3], 1):
        print(f"\n  🪞 F-{i:02d} {s.get('insight_title', '')}")
        print(f"     {s.get('observation', '')[:60]}")
        print(f"     建议: {s.get('recommendation', '')[:60]}")

    print("\n" + "═" * 60)
