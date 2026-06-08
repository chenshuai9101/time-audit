"""
时间审计 v2 — 报告查询逻辑层

把"从磁盘报告里取出自动化机会"这件事抽成纯函数，**不依赖任何第三方包**：
  - MCP server（mcp_server.py）调它做 Agent 直连查询
  - 将来 B 端 / Fara 导出 / 其它消费方也复用同一套取数逻辑

设计：报告 JSON 的 schema 见 report_builder.build_report()。本模块只读、不改、不算分，
只做"加载 + 合成稳定编号(P-/L-/F-) + 统一字段 + 过滤"。
"""
import os
import glob
import json
import hashlib
from typing import Optional, List, Dict, Any


# 置信度 / 难度分级。入参容忍 med / medium 两种写法，但产出一律归一化为规范拼写。
_RANK = {"low": 1, "med": 2, "medium": 2, "high": 3}

# 规范拼写：'medium' 仅作入参别名，归一化为 'med'。产出方不得直接发出 'medium'。
_LEVEL_CANON = {"low": "low", "med": "med", "medium": "med", "high": "high"}

VALID_LAYERS = ("point", "line", "surface", "all")

# Automation Opportunity Schema 版本（语义化）。规范见 docs/automation-opportunity-schema.md。
# 这是 AOS 版本的【唯一真源】：schema .json / 规范 md / MCP 响应都以它为准。
# 0.x = Draft，结构仍可能破坏性变更；详见规范『版本与稳定性』。
SCHEMA_VERSION = "0.1.0"


def _rank(value: Optional[str]) -> int:
    """把 low/med/high 映射成可比较的数；未知/缺失记 0。"""
    if not value:
        return 0
    return _RANK.get(str(value).strip().lower(), 0)


def _norm_level(value: Any, default: Optional[str] = None) -> Optional[str]:
    """归一化为规范分级 low/med/high（medium→med）。无法识别时返回 default。"""
    key = str(value).strip().lower() if value else ""
    return _LEVEL_CANON.get(key, default)


def _fingerprint(layer: str, *parts: Any) -> str:
    """由机会的内容特征派生跨报告稳定身份（execution_probe 回写的 join key）。

    与位置编号 id（P-/L-/F-，仅报告内稳定）不同，fingerprint 只取语义稳定的特征，
    因此同一个工作流在不同报告里得到同一个指纹，可用于去重与累积。
    """
    basis = "|".join([layer] + [str(p).strip().lower() for p in parts if p])
    return "fp_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _put(d: dict, key: str, value: Any) -> None:
    """仅当值非空时写入；让"缺失"与"空串"对消费方可区分（可选字段不发空串）。"""
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    d[key] = value


def resolve_reports_dir(config_path: Optional[str] = None) -> str:
    """定位报告目录。优先读 config，失败则退回默认 ~/Desktop/时间审计/reports。"""
    try:
        from time_audit.main import load_config
        cfg = load_config(config_path)
        out = cfg["reports"]["output_dir"]
    except Exception:
        out = "~/Desktop/时间审计/reports"
    return os.path.expanduser(out)


def list_report_files(reports_dir: str) -> List[str]:
    """按文件名（含时间戳）升序返回所有报告 JSON 路径。"""
    if not os.path.isdir(reports_dir):
        return []
    return sorted(glob.glob(os.path.join(reports_dir, "report_*.json")))


def load_report(reports_dir: str, report_id: Optional[str] = None) -> Dict[str, Any]:
    """加载一份报告。report_id 为空则取最新一份。

    raises:
        FileNotFoundError: 目录无报告，或指定 id 不存在（消息含可执行的下一步）。
    """
    files = list_report_files(reports_dir)
    if not files:
        raise FileNotFoundError(
            f"报告目录无任何报告：{reports_dir}。"
            "请先运行 `time-audit --days 14` 生成报告。"
        )

    if report_id:
        target = os.path.join(reports_dir, f"report_{report_id}.json")
        if not os.path.exists(target):
            available = [_rid_from_path(p) for p in files]
            raise FileNotFoundError(
                f"未找到报告 id={report_id}。可用 id：{', '.join(available)}"
            )
        path = target
    else:
        path = files[-1]  # 最新

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _rid_from_path(path: str) -> str:
    base = os.path.basename(path)
    return base[len("report_"):-len(".json")]


def list_reports_index(reports_dir: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """报告清单（不含洞察正文，轻量）。最新的排在前面。"""
    files = list(reversed(list_report_files(reports_dir)))  # 最新优先
    total = len(files)
    window = files[offset:offset + limit]

    items = []
    for p in window:
        try:
            with open(p, "r", encoding="utf-8") as f:
                rep = json.load(f)
        except Exception:
            continue
        meta = rep.get("report_meta", {})
        overall = rep.get("overall", {})
        ins = rep.get("ai_insights", {})
        items.append({
            "report_id": meta.get("id", _rid_from_path(p)),
            "generated_at": meta.get("generated_at", ""),
            "llm_model": meta.get("llm_model", ""),
            "dry_run": meta.get("dry_run", False),
            "day_range": overall.get("day_range", ""),
            "day_count": overall.get("day_count", 0),
            "session_count": overall.get("session_count", 0),
            "counts": {
                "points": len(ins.get("points") or []),
                "lines": len(ins.get("lines") or []),
                "surfaces": len(ins.get("surfaces") or []),
            },
        })

    return {
        "total": total,
        "count": len(items),
        "offset": offset,
        "has_more": total > offset + len(items),
        "reports": items,
    }


def summarize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """单份报告概览：元数据 + 规模 + app 分布 + 三层计数（不含洞察正文）。"""
    meta = report.get("report_meta", {})
    overall = report.get("overall", {})
    ins = report.get("ai_insights", {})
    return {
        "report_id": meta.get("id", ""),
        "generated_at": meta.get("generated_at", ""),
        "llm_model": meta.get("llm_model", ""),
        "dry_run": meta.get("dry_run", False),
        "overall": {
            "raw_event_count": overall.get("raw_event_count", 0),
            "session_count": overall.get("session_count", 0),
            "day_count": overall.get("day_count", 0),
            "day_range": overall.get("day_range", ""),
            "active_hours": overall.get("active_hours", []),
        },
        "app_breakdown": (report.get("app_breakdown") or [])[:8],
        "insight_counts": {
            "points": len(ins.get("points") or []),
            "lines": len(ins.get("lines") or []),
            "surfaces": len(ins.get("surfaces") or []),
        },
    }


def _normalize_point(idx: int, p: dict) -> dict:
    # 公共必填 + 点层必填始终在场；可选字段空则省略（不发空串）。
    title = p.get("title", "")
    out = {
        "id": f"P-{idx:02d}",
        "fingerprint": _fingerprint("point", title),
        "layer": "point",
        "title": title,
        "description": p.get("description", ""),
        "confidence": _norm_level(p.get("confidence"), default="low"),
        "evidence_sessions": p.get("evidence_sessions") or [],
    }
    _put(out, "frequency_hint", p.get("frequency_hint"))
    _put(out, "skill_suggestion", p.get("skill_suggestion"))
    _put(out, "modality", p.get("modality"))
    if p.get("evidence_samples"):
        out["evidence_samples"] = p["evidence_samples"]
    return out


def _normalize_line(idx: int, l: dict) -> dict:
    apps = l.get("apps_involved") or []
    workflow_name = l.get("workflow_name", "")
    out = {
        "id": f"L-{idx:02d}",
        "fingerprint": _fingerprint("line", workflow_name, *sorted(apps)),
        "layer": "line",
        "workflow_name": workflow_name,
        "confidence": _norm_level(l.get("confidence"), default="low"),
        "evidence_sessions": l.get("evidence_sessions") or [],
    }
    _put(out, "trigger", l.get("trigger"))
    if apps:
        out["apps_involved"] = apps
    if l.get("steps"):
        out["steps"] = l["steps"]
    # 数值字段：保留 None（schema 允许 null，区别于"缺失"）。
    for k in ("occurrence_count", "avg_duration_min", "estimated_weekly_savings_min"):
        if k in l:
            out[k] = l[k]
    # 难度为可选：能归一化才发，否则省略（绝不发空串/非法枚举）。
    diff = _norm_level(l.get("automation_difficulty"))
    if diff is not None:
        out["automation_difficulty"] = diff
    _put(out, "skill_suggestion", l.get("skill_suggestion"))
    _put(out, "modality", l.get("modality"))
    return out


def _normalize_surface(idx: int, s: dict) -> dict:
    insight_title = s.get("insight_title", "")
    out = {
        "id": f"F-{idx:02d}",
        "fingerprint": _fingerprint("surface", insight_title),
        "layer": "surface",
        "insight_title": insight_title,
        "observation": s.get("observation", ""),
        "confidence": _norm_level(s.get("confidence"), default="low"),
        "evidence_sessions": s.get("evidence_sessions") or [],
    }
    _put(out, "implication", s.get("implication"))
    _put(out, "recommendation", s.get("recommendation"))
    return out


def extract_opportunities(report: Dict[str, Any], layer: str = "all",
                          min_confidence: Optional[str] = None,
                          max_difficulty: Optional[str] = None) -> List[Dict[str, Any]]:
    """从报告里取出自动化机会，按层/置信度/难度过滤。

    Args:
        layer: point | line | surface | all
        min_confidence: low|med|high，保留 >= 该置信度的项（缺置信度的项会被排除）
        max_difficulty: low|med|high，**仅作用于 line**（point/surface 无难度，不受影响）

    Returns:
        统一结构的机会列表，每项带稳定编号 id（P-/L-/F-）与 evidence_sessions。
    """
    layer = (layer or "all").lower()
    if layer not in VALID_LAYERS:
        raise ValueError(f"未知 layer: {layer!r}（支持 {', '.join(VALID_LAYERS)}）")

    ins = report.get("ai_insights", {})
    out: List[Dict[str, Any]] = []

    if layer in ("point", "all"):
        for i, p in enumerate(ins.get("points") or [], 1):
            out.append(_normalize_point(i, p))
    if layer in ("line", "all"):
        for i, l in enumerate(ins.get("lines") or [], 1):
            out.append(_normalize_line(i, l))
    if layer in ("surface", "all"):
        for i, s in enumerate(ins.get("surfaces") or [], 1):
            out.append(_normalize_surface(i, s))

    # 置信度过滤
    if min_confidence:
        floor = _rank(min_confidence)
        out = [o for o in out if _rank(o.get("confidence")) >= floor]

    # 难度过滤（仅 line）
    if max_difficulty:
        ceil = _rank(max_difficulty)
        out = [
            o for o in out
            if o["layer"] != "line" or _rank(o.get("automation_difficulty")) <= ceil
        ]

    return out


def build_envelope(report: Dict[str, Any], opportunities: List[Dict[str, Any]],
                   filters: Optional[Dict[str, Any]] = None,
                   report_id: str = "") -> Dict[str, Any]:
    """把一批机会包成 AOS 信封（顶层结构）。MCP 与 pipe 导出共用此函数，避免漂移。"""
    meta = report.get("report_meta", {})
    env: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_id": meta.get("id", "") or report_id,
        "produced_at": meta.get("generated_at", ""),
        "producer": f"time-audit/{meta.get('engine_version', '')}".rstrip("/"),
    }
    if filters is not None:
        env["filters"] = filters
    env["count"] = len(opportunities)
    env["opportunities"] = opportunities
    return env
