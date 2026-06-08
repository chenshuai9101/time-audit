"""
源适配器注册表 —— 编排所有数据源。

职责：
  1. 维护默认适配器列表
  2. 按 config 的 sources.enabled 过滤启用哪些
  3. 调用每个启用且可用的适配器，合并事件、按 ts 排序、重算 gap_seconds
  4. 单个适配器失败被隔离，不影响其他源（隐私 / 健壮性硬约束）
"""
from typing import List, Dict


def default_adapters() -> list:
    """内置适配器实例列表。延迟导入避免循环依赖。"""
    from time_audit.sources.screenpipe import ScreenpipeAdapter
    from time_audit.sources.shell_history import ShellHistoryAdapter
    from time_audit.sources.claude_code import ClaudeCodeAdapter
    from time_audit.sources.openclaw import OpenClawAdapter
    return [
        ScreenpipeAdapter(),
        ShellHistoryAdapter(),
        ClaudeCodeAdapter(),
        OpenClawAdapter(),
    ]


def enabled_adapters(cfg: dict, all_adapters: list = None) -> list:
    """按 cfg['sources']['enabled'] 过滤；未配置则全部启用。"""
    all_adapters = all_adapters if all_adapters is not None else default_adapters()
    enabled = (cfg.get("sources") or {}).get("enabled")
    if not enabled:
        return list(all_adapters)
    enabled = set(enabled)
    return [a for a in all_adapters if a.name in enabled]


def collect_all(cfg: dict, days: int, adapters: list = None) -> List[Dict]:
    """跑所有启用且可用的适配器，合并 / 排序 / 重算 gap。"""
    adapters = adapters if adapters is not None else enabled_adapters(cfg)

    merged = []
    for adapter in adapters:
        try:
            if not adapter.available(cfg):
                continue
            events = adapter.collect(cfg, days) or []
            merged.extend(events)
            print(f"  ✅ 源 [{adapter.name}]: {len(events)} 事件")
        except Exception as e:
            print(f"  ⚠️  源 [{getattr(adapter, 'name', '?')}] 采集失败，已跳过: {e}")

    merged.sort(key=lambda x: x.get("ts", 0))
    for i in range(1, len(merged)):
        merged[i]["gap_seconds"] = merged[i].get("ts", 0) - merged[i - 1].get("ts", 0)
    if merged:
        merged[0]["gap_seconds"] = 0
    return merged
