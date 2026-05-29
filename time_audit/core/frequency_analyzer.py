"""
时间审计 v2 — 轻量频率统计

唯一作用：给 LLM 准备上下文 hint（app 耗时占比、活跃时段）。
不再做 skill 推断 / 规则判断 / 模板匹配 —— 那是 LLM 的活。
"""
from collections import Counter, defaultdict
from datetime import datetime


def analyze_app_frequency(events: list) -> dict:
    """统计 app 事件数与近似耗时（gap 累加）"""
    if not events:
        return {}

    app_counter = Counter()
    app_duration = defaultdict(float)

    for e in events:
        app = e.get("app", "unknown")
        app_counter[app] += 1
        gap = e.get("gap_seconds", 30)
        if 0 < gap < 3600:
            app_duration[app] += gap

    total_events = sum(app_counter.values())
    total_duration = sum(app_duration.values()) or 1

    top_apps = []
    for app, count in app_counter.most_common(15):
        dur = app_duration.get(app, 0)
        top_apps.append({
            "app": app,
            "events": count,
            "event_pct": round(count / total_events * 100, 1),
            "duration_minutes": round(dur / 60, 1),
            "duration_pct": round(dur / total_duration * 100, 1),
        })

    return {
        "total_events": total_events,
        "total_duration_hours": round(total_duration / 3600, 1),
        "unique_apps": len(app_counter),
        "top_apps": top_apps,
    }


def active_hours(events: list) -> list:
    """活跃时段（每小时事件数 > 阈值的小时）"""
    hourly = defaultdict(int)
    for e in events:
        try:
            hourly[datetime.fromtimestamp(e["ts"]).hour] += 1
        except Exception:
            continue
    if not hourly:
        return []
    threshold = max(hourly.values()) * 0.3
    return sorted([h for h, c in hourly.items() if c >= threshold])
