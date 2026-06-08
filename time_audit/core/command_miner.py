"""
时间审计 — 确定性命令挖掘器

不依赖 LLM。从命令 / 意图类事件（shell / claude-code / openclaw）中，用纯统计
找出"该做成 skill"的信号：

  - 点候选：单条命令（归一化后）重复 ≥ 阈值 → 建议 alias / snippet
  - 线候选：连续命令序列（n-gram）重复 ≥ 阈值 → 建议脚本 / skill

证据全部真实：点带真实出现次数 + 样例原文；线带真实序列 + 出现次数。
完全确定性、零幻觉——这是它相对 OCR + LLM 路线的关键优势。
"""
import re
from collections import Counter
from typing import List, Dict

# 哪些事件算"命令 / 意图"层（按 app 或 source 命中）
COMMAND_SOURCES = {"shell", "claude-code", "openclaw"}

_QUOTED = re.compile(r"""("[^"]*"|'[^']*')""")


def normalize_command(cmd: str) -> str:
    """把一条命令归一化成"骨架"，抹掉可变部分（引号内容、路径片段）。

    例：
      git commit -m "fix a nasty bug"      -> git commit -m _
      gh api repos/me/proj/traffic/views   -> gh api repos/_/_/_/_
      git pull origin main                 -> git pull origin main
    """
    if not cmd or not cmd.strip():
        return ""
    # 1) 引号内容整体折叠为 _
    s = _QUOTED.sub("_", cmd.strip())
    # 2) 逐 token 处理；含 / 的 token 保留首段、其余折叠
    tokens = s.split()
    out = []
    for tok in tokens:
        if "/" in tok:
            head, *rest = tok.split("/")
            out.append("/".join([head] + ["_"] * len(rest)))
        else:
            out.append(tok)
    return " ".join(out)


def _command_events(events: list) -> list:
    """只保留命令 / 意图类事件，按 ts 排序。"""
    kept = [
        e for e in events
        if (e.get("source") in COMMAND_SOURCES or e.get("app") in COMMAND_SOURCES)
    ]
    return sorted(kept, key=lambda x: x.get("ts", 0))


def mine_points(events: list, min_count: int = 5) -> List[Dict]:
    """重复单命令 → 点候选。"""
    counter = Counter()
    samples: Dict[str, list] = {}
    for e in events:
        norm = normalize_command(e.get("content", ""))
        if not norm:
            continue
        counter[norm] += 1
        raw = (e.get("content") or "").strip()
        bucket = samples.setdefault(norm, [])
        if raw and raw not in bucket and len(bucket) < 3:
            bucket.append(raw)

    points = []
    for norm, count in counter.items():
        if count >= min_count:
            points.append({
                "normalized": norm,
                "count": count,
                "evidence_samples": samples.get(norm, []),
                "modality": "command",
            })
    points.sort(key=lambda p: -p["count"])
    return points


def mine_sequences(events: list, min_count: int = 3,
                   min_len: int = 2, max_len: int = 5) -> List[Dict]:
    """重复命令序列（n-gram）→ 线候选。

    Shell 历史无时间戳，序列按"出现顺序"判定连续，不依赖时间间隔。
    """
    cmds = [normalize_command(e.get("content", "")) for e in events]
    cmds = [c for c in cmds if c]

    # 折叠连续重复：同一命令连按 N 次不是工作流，只是重复操作（已由点候选覆盖）。
    # 工作流是"不同步骤的序列"，折叠后才能挖出真正的跨步骤流程。
    collapsed = []
    for c in cmds:
        if not collapsed or collapsed[-1] != c:
            collapsed.append(c)
    cmds = collapsed

    results = []
    for n in range(min_len, max_len + 1):
        if len(cmds) < n:
            break
        counter = Counter()
        for i in range(len(cmds) - n + 1):
            counter[tuple(cmds[i:i + n])] += 1
        for gram, count in counter.items():
            if count >= min_count:
                results.append({
                    "sequence": list(gram),
                    "count": count,
                    "length": n,
                    "modality": "command",
                })

    # 更长、更高频的序列更值钱：长度优先、其次频次
    results.sort(key=lambda r: (-r["length"], -r["count"]))

    # 去掉被更长序列包含且同频的子序列（避免冗余）
    deduped = []
    for r in results:
        sub = tuple(r["sequence"])
        contained = any(
            r["count"] == kept["count"]
            and _is_subsequence(sub, tuple(kept["sequence"]))
            for kept in deduped
        )
        if not contained:
            deduped.append(r)

    deduped.sort(key=lambda r: (-r["count"], -r["length"]))
    return deduped


def _is_subsequence(short: tuple, long: tuple) -> bool:
    """short 是否是 long 的连续子串。"""
    if len(short) >= len(long):
        return False
    for i in range(len(long) - len(short) + 1):
        if long[i:i + len(short)] == short:
            return True
    return False


def mine_skill_candidates(events: list, cfg: dict = None) -> Dict:
    """主入口：从命令 / 意图事件挖点 + 线候选。"""
    cfg = cfg or {}
    cmd_events = _command_events(events)
    return {
        "points": mine_points(
            cmd_events, min_count=cfg.get("min_command_count", 5)),
        "lines": mine_sequences(
            cmd_events,
            min_count=cfg.get("min_sequence_count", 3),
            min_len=cfg.get("min_sequence_len", 2),
            max_len=cfg.get("max_sequence_len", 5)),
    }


def as_report_points(candidates: list) -> list:
    """命令点候选 → 报告可渲染点（证据是真实样例，不含虚构 session）。"""
    out = []
    for c in candidates:
        out.append({
            "title": c["normalized"][:60],
            "description": f"重复 {c['count']} 次的命令 / 意图",
            "frequency_hint": f"共 {c['count']} 次",
            "skill_suggestion": "做成 alias / snippet，一键触发",
            "confidence": "high",              # 确定性统计 = 高置信
            "evidence_samples": c.get("evidence_samples", []),
            "modality": "command",
        })
    return out


def as_report_lines(candidates: list) -> list:
    """命令序列候选 → 报告可渲染线。"""
    out = []
    for c in candidates:
        seq = c["sequence"]
        out.append({
            "workflow_name": " → ".join(seq)[:60],
            "trigger": "",
            "apps_involved": ["shell / agent"],
            "occurrence_count": c["count"],
            "avg_duration_min": "",
            "estimated_weekly_savings_min": "",
            "steps": list(seq),
            "skill_suggestion": "把这串命令做成脚本 / skill",
            "automation_difficulty": "low",
            "confidence": "high",
            "modality": "command",
        })
    return out
