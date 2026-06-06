"""
AOS 导出器 —— 把最近一份（或指定）报告导出为独立的 AOS 信封 JSON 文件。

为什么需要它：
  CLI（time-audit）跑完只产出 report_<id>.json（含 ai_insights）；AOS 信封此前只在
  MCP 在线响应里存在。pipe / 离线分发需要一个**落地成文件**的 AOS，供其它 Agent 直接读。

它复用 report_query 的同一套取数 + 信封逻辑（build_envelope），因此与 MCP 输出零漂移。

跑法：
    python -m time_audit.aos_export                 # 最新报告 → reports/aos_<id>.json
    python -m time_audit.aos_export --report-id ID  # 指定报告
    python -m time_audit.aos_export --out PATH      # 自定义输出路径
    python -m time_audit.aos_export --stdout        # 打到标准输出（不写文件）
"""
import os
import json
import argparse
from typing import Optional

from time_audit.core import report_query


def export_aos(report_id: Optional[str] = None, out_path: Optional[str] = None,
               config_path: Optional[str] = None) -> dict:
    """加载报告 → 取全部机会 → 包成 AOS 信封 → 写文件。返回 {envelope, path}。"""
    reports_dir = report_query.resolve_reports_dir(config_path)
    report = report_query.load_report(reports_dir, report_id)
    opps = report_query.extract_opportunities(report, layer="all")
    envelope = report_query.build_envelope(report, opps, report_id=report_id or "")

    if out_path is None:
        rid = envelope.get("report_id", "") or "latest"
        out_path = os.path.join(reports_dir, f"aos_{rid}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)
    return {"envelope": envelope, "path": out_path}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="time_audit.aos_export",
        description="把报告导出为独立 AOS 信封 JSON（供 Agent 消费）。")
    parser.add_argument("--report-id", default=None, help="报告 id，留空取最新")
    parser.add_argument("--out", default=None, help="输出文件路径，默认 reports/aos_<id>.json")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--stdout", action="store_true", help="打到标准输出，不写文件")
    args = parser.parse_args(argv)

    reports_dir = report_query.resolve_reports_dir(args.config)
    report = report_query.load_report(reports_dir, args.report_id)
    opps = report_query.extract_opportunities(report, layer="all")
    envelope = report_query.build_envelope(report, opps, report_id=args.report_id or "")

    if args.stdout:
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
        return 0

    out_path = args.out or os.path.join(
        reports_dir, f"aos_{envelope.get('report_id', '') or 'latest'}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)
    print(f"AOS 已写出: {out_path}  (count={envelope['count']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
