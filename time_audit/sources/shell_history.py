"""
shell_history 适配器 —— 从 zsh / bash 历史挖命令事件。

处理三种现实情况：
  - zsh 扩展格式  `: <ts>:<dur>;<cmd>`  → 取真实时间戳
  - 纯命令行（无时间戳，本机 zsh 即如此）→ 按出现顺序合成单调递增 ts
  - `\` 续行 → 合并成单条命令；`#` 注释 / 空行 → 跳过

命令层的重复最直接说明"该做成脚本 / skill"，所以这是最高价值的源之一。
"""
import os
import re
from typing import List, Dict

from time_audit.sources.base import SourceAdapter

_EXT = re.compile(r"^: (\d+):\d+;(.*)$")

_DEFAULT_PATHS = [
    os.path.expanduser("~/.zsh_history"),
    os.path.expanduser("~/.bash_history"),
]


def _logical_lines(text: str) -> List[str]:
    """合并 `\\` 续行为逻辑行（续行段去掉首部缩进）。"""
    out = []
    buf = ""
    for raw in text.split("\n"):
        seg = raw.lstrip() if buf else raw
        if seg.endswith("\\"):
            buf += seg[:-1].rstrip() + " "
        else:
            buf += seg
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def parse_history(text: str, base_ts: float) -> List[Dict]:
    """把历史文件文本解析成归一化事件列表。

    纯命令行（无真实时间戳）从 base_ts 起按序号 +1 秒合成单调递增 ts。
    """
    events = []
    synth = 0
    for raw in _logical_lines(text):
        line = raw.strip()
        m = _EXT.match(raw) or _EXT.match(line)
        if m:
            ts = float(m.group(1))
            cmd = m.group(2).strip()
        else:
            if not line or line.startswith("#"):
                continue
            cmd = line
            ts = base_ts + synth
            synth += 1
        if not cmd:
            continue
        events.append({
            "timestamp": "",
            "app": "shell",
            "window": "",
            "event_type": "command",
            "content": cmd,
            "file_path": "",
            "source": "shell",
            "ts": ts,
        })
    return events


class ShellHistoryAdapter(SourceAdapter):
    name = "shell"

    def _resolve_path(self, cfg: dict) -> str:
        override = ((cfg.get("sources") or {}).get("shell") or {}).get("history_path")
        if override:
            return os.path.expanduser(override)
        for p in _DEFAULT_PATHS:
            if os.path.exists(p):
                return p
        return _DEFAULT_PATHS[0]

    def available(self, cfg: dict) -> bool:
        return os.path.exists(self._resolve_path(cfg))

    def collect(self, cfg: dict, days: int) -> List[Dict]:
        from datetime import datetime, timedelta
        path = self._resolve_path(cfg)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        # 合成时间戳从 (now - days) 起按序号递增，使整段落在分析窗口内
        base_ts = (datetime.now() - timedelta(days=days)).timestamp()
        events = parse_history(text, base_ts=base_ts)

        # 仅当历史是扩展格式（带真实时间戳）才按 days 截断；
        # 合成时间戳无法判断命令真实年龄，全部保留。
        has_real_ts = any(_EXT.match(ln) for ln in text.split("\n"))
        if has_real_ts:
            cutoff = (datetime.now() - timedelta(days=days)).timestamp()
            events = [e for e in events if e["ts"] >= cutoff]
        return events
