"""
时间审计 — 数据读取层
从Screenpipe SQLite数据库提取事件日志，标准化为统一格式。
也支持从测试数据/CSV文件读取。
"""
import sqlite3
import os
import json
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def discover_screenpipe_db() -> Optional[str]:
    """自动发现Screenpipe数据库位置（兼容新旧版本路径）"""
    candidates = [
        # 新版（0.3.x）
        os.path.expanduser("~/.screenpipe/db.sqlite"),
        # 旧版
        os.path.expanduser("~/.screenpipe/db/screenpipe.db"),
        os.path.expanduser("~/Library/Application Support/screenpipe/screenpipe.db"),
        os.path.expanduser("~/Library/Application Support/screenpipe/db/screenpipe.db"),
        "/tmp/screenpipe.db",
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"  📍 发现Screenpipe数据库: {path}")
            return path
    return None


def read_screenpipe_events(db_path: str, days: int = 14, fallback_mock: bool = True) -> list:
    """
    从Screenpipe数据库读取事件日志
    返回标准化事件列表: [{timestamp, app, window, event_type, content, duration}]

    fallback_mock=True 时，库中无事件则回退到模拟数据（保留旧 CLI 行为）；
    适配器层用 fallback_mock=False，让"无数据"如实返回空，mock 兜底交给编排层。
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"数据库不存在: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    # 尝试不同的表结构（Screenpipe不同版本可能有差异）
    events = []

    # 查询0: 新版 0.3.x — frames 表合并了 full_text/accessibility，单表搞定
    try:
        cursor.execute("""
            SELECT timestamp, app_name, window_name,
                   COALESCE(full_text, accessibility_text, '') AS text,
                   COALESCE(snapshot_path, '') AS path,
                   COALESCE(browser_url, '') AS url
            FROM frames
            WHERE timestamp >= ?
              AND (full_text IS NOT NULL OR accessibility_text IS NOT NULL)
            ORDER BY timestamp ASC
            LIMIT 50000
        """, (cutoff,))
        for row in cursor.fetchall():
            content = (row["text"] or "")[:500]
            if row["url"]:
                content = f"[{row['url']}] {content}"
            events.append({
                "timestamp": row["timestamp"],
                "app": row["app_name"] or "unknown",
                "window": row["window_name"] or "",
                "event_type": "screen",
                "content": content,
                "file_path": row["path"] or "",
                "source": "screenpipe.frames.v2"
            })
        if events:
            print(f"  📄 从 frames(v0.3+) 读取了 {len(events)} 条记录")
    except sqlite3.OperationalError:
        pass

    # 查询1: 旧版 frames 表（带 ocr_text 字段）
    if not events:
        try:
            cursor.execute("""
                SELECT timestamp, app_name, window_name, ocr_text, file_path
                FROM frames
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT 50000
            """, (cutoff,))
            for row in cursor.fetchall():
                events.append({
                    "timestamp": row["timestamp"],
                    "app": row["app_name"] or "unknown",
                    "window": row["window_name"] or "",
                    "event_type": "screen",
                    "content": (row["ocr_text"] or "")[:500],
                    "file_path": row["file_path"] or "",
                    "source": "screenpipe.frames.legacy"
                })
            if events:
                print(f"  📄 从 frames(legacy) 读取了 {len(events)} 条记录")
        except sqlite3.OperationalError:
            pass

    # 查询2: audio_transcriptions表（音频转文字）
    if not events:
        try:
            cursor.execute("""
                SELECT timestamp, app_name, transcription, speaker
                FROM audio_transcriptions
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT 10000
            """, (cutoff,))
            for row in cursor.fetchall():
                events.append({
                    "timestamp": row["timestamp"],
                    "app": row["app_name"] or "audio",
                    "window": f"speaker:{row['speaker']}" if row['speaker'] else "",
                    "event_type": "audio",
                    "content": (row["transcription"] or "")[:500],
                    "file_path": "",
                    "source": "screenpipe.audio"
                })
        except sqlite3.OperationalError:
            pass

    # 查询3: events表（通用事件）
    if not events:
        try:
            cursor.execute("""
                SELECT timestamp, event_type, app_name, window_name, content
                FROM events
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT 50000
            """, (cutoff,))
            for row in cursor.fetchall():
                events.append({
                    "timestamp": row["timestamp"],
                    "app": row["app_name"] or row.get("event_type", "unknown"),
                    "window": row["window_name"] or "",
                    "event_type": row["event_type"] or "event",
                    "content": (row["content"] or "")[:500],
                    "file_path": "",
                    "source": "screenpipe.events"
                })
        except sqlite3.OperationalError:
            pass

    conn.close()
    
    if not events:
        print("  ⚠️  Screenpipe数据库中没有找到事件记录")
        return generate_mock_events(days) if fallback_mock else []
    
    # 校准时间戳
    for e in events:
        try:
            dt = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            e["ts"] = dt.timestamp()
        except:
            e["ts"] = 0.0
    
    # 按时间排序
    events.sort(key=lambda x: x["ts"])
    # 添加相邻事件间隔
    for i in range(1, len(events)):
        events[i]["gap_seconds"] = events[i]["ts"] - events[i-1]["ts"]
    if events:
        events[0]["gap_seconds"] = 0
    
    return events


def read_custom_csv(csv_path: str, days: int = 14) -> list:
    """从CSV读取自定义事件数据"""
    events = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append({
                "timestamp": row.get("timestamp", datetime.now().isoformat()),
                "app": row.get("app", "unknown"),
                "window": row.get("window", ""),
                "event_type": row.get("event_type", "custom"),
                "content": row.get("content", ""),
                "file_path": row.get("file_path", ""),
                "source": "csv"
            })
    for e in events:
        try:
            dt = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            e["ts"] = dt.timestamp()
        except:
            e["ts"] = 0.0
    events.sort(key=lambda x: x["ts"])
    for i in range(1, len(events)):
        events[i]["gap_seconds"] = events[i]["ts"] - events[i-1]["ts"]
    if events:
        events[0]["gap_seconds"] = 0
    return events


def generate_mock_events(days: int = 14) -> list:
    """生成模拟数据进行功能测试"""
    print("  🧪 生成模拟事件数据用于测试")
    now = datetime.now()
    events = []
    
    # 模拟14天的规律行为
    for day_offset in range(days):
        day = now - timedelta(days=day_offset)
        base = day.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 场景1: 每日日报生成 (每天09:30-10:00)
        if day.weekday() < 5:  # 工作日
            t = base.replace(hour=9, minute=30)
            app_sequence = [
                (t.isoformat(), "Excel", "日报模板.xlsx - Excel", "screen",
                 "打开Excel日报模板", ""),
                (t.replace(minute=32).isoformat(), "Chrome", "数据库管理页面 - Chrome", "screen",
                 "登录数据库管理后台", "https://db.xxx.com"),
                (t.replace(minute=35).isoformat(), "Chrome", "SQL查询结果", "screen",
                 "SELECT * FROM daily_sales WHERE date=CURRENT_DATE", ""),
                (t.replace(minute=37).isoformat(), "Excel", "日报模板.xlsx - Excel", "screen",
                 "粘贴数据到日报模板", "/Users/user/模板/日报.xlsx"),
                (t.replace(minute=42).isoformat(), "Excel", "日报模板.xlsx - Excel", "screen",
                 "刷新数据透视表", ""),
                (t.replace(minute=48).isoformat(), "Excel", "日报模板.xlsx - Excel", "screen",
                 "保存并导出PDF", "/Users/user/Desktop/日报_20260528.pdf"),
            ]
            for ts, app, win, etype, content, fpath in app_sequence:
                events.append({
                    "timestamp": ts, "app": app, "window": win,
                    "event_type": etype, "content": content,
                    "file_path": fpath, "source": "mock"
                })
        
        # 场景2: 患者信息查询+病历整理 (每天11:00-11:15 + 15:00-15:15)
        for hour in [11, 15]:
            t = base.replace(hour=hour, minute=0)
            seq = [
                (t.isoformat(), "Chrome", "HIS系统 - Chrome", "screen",
                 "登录HIS系统查询患者信息", "https://his.hospital.com"),
                (t.replace(minute=2).isoformat(), "Chrome", "HIS系统 - 患者列表", "screen",
                 "搜索患者ID: P2026XXXX", ""),
                (t.replace(minute=5).isoformat(), "Chrome", "HIS系统 - 患者详情", "screen",
                 "查看患者诊疗记录", ""),
                (t.replace(minute=8).isoformat(), "Word", "病历模板.docx - Word", "screen",
                 "打开病历模板文档", "/Users/user/文档/病历模板.docx"),
                (t.replace(minute=10).isoformat(), "Word", "病历模板.docx - Word", "screen",
                 "填写患者基本信息+诊断摘要", ""),
                (t.replace(minute=14).isoformat(), "Word", "病历模板.docx - Word", "screen",
                 "保存病历文档", "/Users/user/Desktop/病历_P2026XXXX.docx"),
            ]
            for ts, app, win, etype, content, fpath in seq:
                events.append({
                    "timestamp": ts, "app": app, "window": win,
                    "event_type": etype, "content": content,
                    "file_path": fpath, "source": "mock"
                })
        
        # 场景3: VSCode开发工作 (每天14:00-14:30)
        t = base.replace(hour=14, minute=0)
        dev_seq = [
            (t.isoformat(), "VSCode", "项目A - VSCode", "screen",
             "打开VSCode工作区: /Users/user/projects/project-a", "/Users/user/projects/project-a"),
            (t.replace(minute=1).isoformat(), "Terminal", "bash - project-a", "screen",
             "git pull origin main", "/Users/user/projects/project-a"),
            (t.replace(minute=3).isoformat(), "VSCode", "main.py - VSCode", "screen",
             "编辑主业务逻辑文件", "/Users/user/projects/project-a/main.py"),
            (t.replace(minute=5).isoformat(), "Terminal", "bash - project-a", "screen",
             "python3 -m pytest tests/", ""),
            (t.replace(minute=7).isoformat(), "VSCode", "main.py - VSCode", "screen",
             "修改代码修复bug", "/Users/user/projects/project-a/main.py"),
            (t.replace(minute=15).isoformat(), "Terminal", "bash - project-a", "screen",
             "git add . && git commit -m 'fix: bug修复' && git push", ""),
        ]
        for ts, app, win, etype, content, fpath in dev_seq:
            events.append({
                "timestamp": ts, "app": app, "window": win,
                "event_type": etype, "content": content,
                "file_path": fpath, "source": "mock"
            })

        # 场景4: 会议纪要整理 (每周一/三/五 16:00)
        if day.weekday() in [0, 2, 4]:
            t = base.replace(hour=16, minute=0)
            meeting_seq = [
                (t.isoformat(), "WeChat", "项目群聊", "screen",
                 "查看群聊中的会议录音文件", ""),
                (t.replace(minute=2).isoformat(), "Chrome", "飞书文档 - Chrome", "screen",
                 "打开飞书会议记录", "https://feishu.cn/doc/xxxx"),
                (t.replace(minute=5).isoformat(), "Word", "会议纪要模板.docx - Word", "screen",
                 "创建会议纪要文档", "/Users/user/模板/会议纪要模板.docx"),
                (t.replace(minute=10).isoformat(), "Word", "会议纪要模板.docx - Word", "screen",
                 "整理会议要点+待办事项", ""),
                (t.replace(minute=15).isoformat(), "Chrome", "企业微信 - 邮件", "screen",
                 "发送会议纪要邮件", ""),
            ]
            for ts, app, win, etype, content, fpath in meeting_seq:
                events.append({
                    "timestamp": ts, "app": app, "window": win,
                    "event_type": etype, "content": content,
                    "file_path": fpath, "source": "mock"
                })

    # 按时间排序
    for e in events:
        try:
            dt = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            e["ts"] = dt.timestamp()
        except:
            e["ts"] = 0.0
    events.sort(key=lambda x: x["ts"])
    for i in range(1, len(events)):
        events[i]["gap_seconds"] = events[i]["ts"] - events[i-1]["ts"]
    if events:
        events[0]["gap_seconds"] = 0

    print(f"  📊 生成了 {len(events)} 条模拟事件（{days}天，含日报/病历/开发/会议场景）")
    return events


def load_events(config: dict) -> list:
    """统一入口：通过多源适配器注册表采集并合并事件。

    缺省启用全部源（screenpipe / shell / claude / openclaw）；
    可经 config 的 sources.enabled 或 CLI --sources 收窄。
    所有源都无数据时回退到模拟数据（保留 demo 能力）。
    """
    print("\n📂 数据读取层（多源）")
    from time_audit.sources import registry

    days = config.get("analysis", {}).get("lookback_days", 14)
    events = registry.collect_all(config, days)

    if not events:
        print("  ⚠️  所有启用的源均无数据，回退到模拟数据")
        return generate_mock_events(days)
    return events


def format_events_summary(events: list) -> str:
    """生成事件摘要（用于分析层的快速参考）"""
    if not events:
        return "无事件数据"
    
    total = len(events)
    apps = {}
    for e in events:
        app = e.get("app", "unknown")
        apps[app] = apps.get(app, 0) + 1
    
    time_span = "unknown"
    if total > 1:
        t1 = datetime.fromtimestamp(events[0]["ts"])
        t2 = datetime.fromtimestamp(events[-1]["ts"])
        time_span = f"{t1.strftime('%m-%d')} ~ {t2.strftime('%m-%d')}"
    
    lines = [
        f"  总事件数: {total}",
        f"  时间跨度: {time_span}",
        f"  App分布: {', '.join(f'{a}({c})' for a, c in sorted(apps.items(), key=lambda x:-x[1])[:8])}"
    ]
    return "\n".join(lines)
