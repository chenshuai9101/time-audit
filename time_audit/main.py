"""
时间审计 v2 — 主编排

流水线：
  Screenpipe SQLite → 事件读取 → 事件压缩 → 本地 LLM 三层分析 → 报告
"""
import os
import sys
import json
import yaml
import argparse
from datetime import datetime

from time_audit import __version__
from time_audit.core import (
    db_reader,
    event_compressor,
    frequency_analyzer,
    llm_analyzer,
    report_builder,
)


DEFAULT_CONFIG = {
    "screenpipe": {"db_path": "", "auto_discover": True},
    "analysis": {
        "lookback_days": 14,
        "session_gap_seconds": 300,
        "dedupe_similarity": 0.85,
        "max_frames_per_session": 12,
        "max_ocr_chars": 240,
        "sessions_per_batch": 25,
    },
    "llm": {
        "enabled": True,
        "provider": "ollama",
        "endpoint": "http://localhost:11434",
        "model": "qwen2.5:14b",
        "timeout_seconds": 600,
        "temperature": 0.2,
        "fallback_to_dryrun": True,
        "analyze_points": True,
        "analyze_lines": True,
        "analyze_surfaces": True,
    },
    "reports": {
        "output_dir": os.path.expanduser("~/Desktop/时间审计/reports"),
        "keep_raw_sessions": True,
    },
    "logging": {"level": "INFO"},
}


def load_config(config_path: str = None) -> dict:
    """加载配置，缺失字段用默认值兜底"""
    cfg = {}
    candidates = [config_path] if config_path else []
    candidates += [
        os.path.join(os.path.dirname(__file__), "..", "config", "time_audit.yaml"),
        os.path.expanduser("~/.time_audit/config.yaml"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            with open(p) as f:
                cfg = yaml.safe_load(f) or {}
            break

    # 深度合并默认值
    out = json.loads(json.dumps(DEFAULT_CONFIG))
    for top in cfg:
        if isinstance(cfg[top], dict) and isinstance(out.get(top), dict):
            out[top].update(cfg[top])
        else:
            out[top] = cfg[top]
    return out


def _print_banner(report_id: str, cfg: dict):
    print("")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   🎯 时间审计 v2 · 本地 LLM 行为分析中间件                 ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║   版本     : {__version__}")
    print(f"║   报告 ID  : {report_id}")
    print(f"║   分析周期 : 过去 {cfg['analysis']['lookback_days']} 天")
    print(f"║   LLM 模型 : {cfg['llm']['model']} @ {cfg['llm']['endpoint']}")
    print("╚══════════════════════════════════════════════════════════╝")


def run_analysis(cfg: dict, force_dryrun: bool = False) -> dict:
    report_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    _print_banner(report_id, cfg)

    # 1. 读取
    events = db_reader.load_events(cfg)
    print(db_reader.format_events_summary(events))
    if not events:
        print("\n❌ 无事件数据，退出")
        return {}

    # 2. 压缩
    sessions = event_compressor.compress_events(events, cfg)
    if not sessions:
        print("\n❌ 压缩后无可用会话，退出")
        return {}

    # 3. 上下文统计
    app_freq = frequency_analyzer.analyze_app_frequency(events)
    hours = frequency_analyzer.active_hours(events)

    # 4. LLM 分析
    llm_cfg = cfg["llm"]
    dry_run = force_dryrun or not llm_cfg.get("enabled", True)
    llm_result = {"points": [], "lines": [], "surfaces": []}

    if not dry_run:
        check = llm_analyzer.preflight(llm_cfg)
        if not check["ok"]:
            print(f"\n⚠️  LLM 健康检查未通过：{check['reason']}")
            if check["models"]:
                print(f"   已安装模型: {', '.join(check['models'])}")
            if llm_cfg.get("fallback_to_dryrun", True):
                print("   ↪ 自动回退到 dry-run（仅压缩，无 AI 洞察）")
                dry_run = True
            else:
                print("   ↪ 中止（设置 llm.fallback_to_dryrun=true 可回退）")
                return {}
        else:
            llm_result = llm_analyzer.analyze(
                sessions, app_freq, llm_cfg,
                sessions_per_batch=cfg["analysis"]["sessions_per_batch"])

    # 5. 报告
    report = report_builder.build_report(
        report_id=report_id,
        llm_result=llm_result,
        sessions=sessions,
        app_freq=app_freq,
        hours=hours,
        events_total=len(events),
        model_name=llm_cfg.get("model", ""),
        dry_run=dry_run,
        keep_raw=cfg["reports"].get("keep_raw_sessions", True),
    )
    paths = report_builder.save_report(report, cfg["reports"]["output_dir"])
    report_builder.present_console_summary(report)

    print(f"\n  📄 JSON: {paths['json']}")
    print(f"  📄 MD  : {paths['md']}")
    print("")
    return report


def show_last_report(cfg: dict):
    out_dir = cfg["reports"]["output_dir"]
    if not os.path.isdir(out_dir):
        print("❌ 暂无报告目录")
        return
    mds = sorted([f for f in os.listdir(out_dir) if f.endswith(".md")])
    if not mds:
        print("❌ 暂无报告，先运行 `python -m time_audit`")
        return
    with open(os.path.join(out_dir, mds[-1]), "r", encoding="utf-8") as f:
        print(f.read())


def check_llm(cfg: dict):
    """诊断子命令：探活 Ollama 并列模型"""
    llm_cfg = cfg["llm"]
    print(f"探测 Ollama: {llm_cfg['endpoint']}")
    check = llm_analyzer.preflight(llm_cfg)
    if check["ok"]:
        print("✅ Ollama 在线")
        print(f"   配置模型: {llm_cfg['model']}")
        print(f"   已安装 : {', '.join(check['models']) or '无'}")
    else:
        print(f"❌ {check['reason']}")
        if check["models"]:
            print(f"   已安装 : {', '.join(check['models'])}")
        print("\n安装提示：")
        print("   brew install ollama && ollama serve")
        print(f"   ollama pull {llm_cfg['model']}")


def main():
    parser = argparse.ArgumentParser(
        prog="time-audit",
        description="时间审计 v2 — 本地 LLM 行为分析中间件",
        epilog="不生成代码，只出报告。Agent 读报告后自行创建 skill。")
    parser.add_argument("--days", type=int, default=0, help="分析天数")
    parser.add_argument("--report", action="store_true", help="显示最近一份报告")
    parser.add_argument("--dryrun", action="store_true", help="跳过 LLM，仅做事件压缩")
    parser.add_argument("--check-llm", action="store_true", help="探活 Ollama 与模型")
    parser.add_argument("--config", default="", help="配置文件路径")
    parser.add_argument("--version", action="version", version=f"时间审计 v{__version__}")
    args = parser.parse_args()

    cfg = load_config(args.config or None)
    if args.days > 0:
        cfg["analysis"]["lookback_days"] = args.days

    if args.check_llm:
        check_llm(cfg)
        return
    if args.report:
        show_last_report(cfg)
        return

    run_analysis(cfg, force_dryrun=args.dryrun)


if __name__ == "__main__":
    main()
