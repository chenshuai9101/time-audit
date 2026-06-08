"""
openclaw 适配器（best-effort）—— 从 ~/.openclaw 挖"已固化的自动化意图"。

OpenClaw 目录结构杂乱、版本多变。本适配器只抓最干净、最高价值的信号：
  - cron/jobs.json：用户亲手定义的定时任务（name + description + schedule）。
    这本身就是最强的"该做成 skill"信号——用户已经把某个重复任务固化成了 cron。

格式不认 / 文件缺失 / 解析失败一律优雅返回空，绝不抛错（best-effort 约束）。
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict

from time_audit.sources.base import SourceAdapter

_DEFAULT_BASE = os.path.expanduser("~/.openclaw")


def parse_cron_jobs(text: str) -> List[Dict]:
    """解析 cron/jobs.json → 自动化意图事件列表。"""
    try:
        data = json.loads(text)
    except Exception:
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return []

    events = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = (job.get("name") or "").strip()
        desc = (job.get("description") or "").strip()
        if not name and not desc:
            continue
        expr = ((job.get("schedule") or {}).get("expr") or "").strip()
        content = name
        if desc:
            content = f"{name}：{desc}" if name else desc
        if expr:
            content = f"[cron {expr}] {content}"
        ts = 0.0
        created = job.get("createdAtMs")
        if isinstance(created, (int, float)):
            ts = created / 1000.0
        events.append({
            "timestamp": "",
            "app": "openclaw",
            "window": "cron",
            "event_type": "agent-intent",
            "content": content,
            "file_path": "",
            "source": "openclaw",
            "ts": ts,
        })
    return events


class OpenClawAdapter(SourceAdapter):
    name = "openclaw"

    def _resolve_base(self, cfg: dict) -> str:
        override = ((cfg.get("sources") or {}).get("openclaw") or {}).get("base_dir")
        return os.path.expanduser(override) if override else _DEFAULT_BASE

    def available(self, cfg: dict) -> bool:
        return os.path.isdir(self._resolve_base(cfg))

    def collect(self, cfg: dict, days: int) -> List[Dict]:
        base = self._resolve_base(cfg)
        jobs_path = os.path.join(base, "cron", "jobs.json")
        if not os.path.exists(jobs_path):
            return []
        try:
            with open(jobs_path, "r", encoding="utf-8", errors="replace") as f:
                events = parse_cron_jobs(f.read())
        except Exception:
            return []
        # cron 任务定义的"年龄"不代表近期活动；只在有真实创建时间时按 days 截断
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        events = [e for e in events if e["ts"] == 0.0 or e["ts"] >= cutoff]
        return events
