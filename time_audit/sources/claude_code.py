"""
claude_code 适配器 —— 从 Claude Code 转录挖"反复让 agent 做的事"。

转录在 ~/.claude/projects/**/*.jsonl，是异构的（user / assistant / queue-operation /
attachment ...）。我们只取真正的用户意图消息：
  - type == "user" 且 message.role == "user"
  - content 是文本（str）或含 text block 的列表
  - 纯 tool_result 列表 = 工具回灌，不是用户意图，跳过

这是"意图层"：repeated 委托正是最该固化成 skill 的信号。
"""
import os
import glob
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from time_audit.sources.base import SourceAdapter

_DEFAULT_DIR = os.path.expanduser("~/.claude/projects")

# 机器注入的提示（claude-mem 观察者、模式切换、系统提醒等），不是用户真实意图
_INJECTION_MARKERS = (
    "hello memory agent",
    "continuing to observe the primary",
    "mode switch:",
    "critical tag requirement",
    "<observed_from_primary_session>",
    "<system-reminder>",
)

# 路径中含这些片段的项目目录是 claude-mem 观察者会话，整目录跳过
_SKIP_PATH_MARKERS = ("observer", "claude-mem")


def is_injected_prompt(text: str) -> bool:
    """判断是否为机器注入提示（应从用户意图中剔除）。"""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in _INJECTION_MARKERS)


def extract_user_text(content) -> Optional[str]:
    """从 message.content 抽出用户文本；非文本（tool_result 等）返回 None。"""
    if isinstance(content, str):
        text = content.strip()
        return text or None
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = " ".join(p.strip() for p in parts if p.strip())
        return text or None
    return None


def _parse_ts(iso: str) -> float:
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def parse_transcript(text: str, cutoff_ts: float = None) -> List[Dict]:
    """解析一个 jsonl 转录文本 → 用户意图事件列表。"""
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "user":
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        user_text = extract_user_text(msg.get("content"))
        if not user_text or is_injected_prompt(user_text):
            continue
        ts = _parse_ts(obj.get("timestamp", ""))
        if cutoff_ts is not None and ts and ts < cutoff_ts:
            continue
        events.append({
            "timestamp": obj.get("timestamp", ""),
            "app": "claude-code",
            "window": obj.get("cwd") or obj.get("gitBranch") or "",
            "event_type": "agent-intent",
            "content": user_text,
            "file_path": "",
            "source": "claude-code",
            "ts": ts,
        })
    return events


class ClaudeCodeAdapter(SourceAdapter):
    name = "claude"

    def _resolve_dir(self, cfg: dict) -> str:
        override = ((cfg.get("sources") or {}).get("claude") or {}).get("projects_dir")
        return os.path.expanduser(override) if override else _DEFAULT_DIR

    def available(self, cfg: dict) -> bool:
        return os.path.isdir(self._resolve_dir(cfg))

    def collect(self, cfg: dict, days: int) -> List[Dict]:
        root = self._resolve_dir(cfg)
        if not os.path.isdir(root):
            return []
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        events = []
        for fp in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
            # 跳过 claude-mem 观察者会话目录（注入提示噪声源）
            low = fp.lower()
            if any(m in low for m in _SKIP_PATH_MARKERS):
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    events.extend(parse_transcript(f.read(), cutoff_ts=cutoff))
            except Exception:
                continue
        return events
