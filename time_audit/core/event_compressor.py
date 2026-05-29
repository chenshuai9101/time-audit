"""
时间审计 v2 — 事件压缩器

把 Screenpipe 海量事件流压成 LLM 可消化的会话片段：
  1. 按时间空隙切分会话
  2. 同窗口连续 OCR 去重（防止 LLM 被刷屏式重复淹没）
  3. 长会话采样（首/中/尾 + 应用切换帧）
  4. 文本截断 + 元数据保留

输出格式（每个 session）:
{
  "id": "S001",
  "day": "2026-05-28",
  "start": "09:30",
  "end": "09:48",
  "duration_min": 18,
  "apps": ["Excel", "Chrome"],
  "frame_count": 6,                # 压缩后实际帧数
  "raw_count": 42,                 # 原始帧数
  "frames": [
    {"t": "09:30", "app": "Excel", "win": "日报模板.xlsx", "ocr": "...", "file": "..."},
    ...
  ],
  "summary_for_llm": "09:30-09:48 (18min) Excel→Chrome→Excel ..."   # 一句话标题，给 LLM 看
}
"""
from datetime import datetime
from typing import List, Dict


def _similarity(a: str, b: str) -> float:
    """简易字符级 Jaccard 相似度，用于 OCR 去重，无外部依赖"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    sa = set(a[:200])
    sb = set(b[:200])
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _dedupe_consecutive(frames: list, threshold: float) -> list:
    """同 app+window 连续帧，OCR 相似度高于 threshold 则丢弃"""
    if not frames:
        return frames
    kept = [frames[0]]
    for f in frames[1:]:
        prev = kept[-1]
        same_ctx = (f.get("app") == prev.get("app") and
                    f.get("window") == prev.get("window"))
        if same_ctx:
            sim = _similarity(f.get("content", ""), prev.get("content", ""))
            if sim >= threshold:
                continue
        kept.append(f)
    return kept


def _sample_long_session(frames: list, max_frames: int) -> list:
    """会话过长则采样：保留首尾 + app 切换帧 + 中间均匀采样"""
    if len(frames) <= max_frames:
        return frames

    keep_idx = {0, len(frames) - 1}
    # app 切换帧
    for i in range(1, len(frames)):
        if frames[i].get("app") != frames[i - 1].get("app"):
            keep_idx.add(i)
            keep_idx.add(i - 1)
        if len(keep_idx) >= max_frames:
            break

    # 均匀填充剩余配额
    if len(keep_idx) < max_frames:
        remaining = max_frames - len(keep_idx)
        step = max(1, len(frames) // (remaining + 1))
        for i in range(step, len(frames), step):
            keep_idx.add(i)
            if len(keep_idx) >= max_frames:
                break

    return [frames[i] for i in sorted(keep_idx)[:max_frames]]


def _build_summary(session: dict) -> str:
    """生成一行会话摘要，作为 LLM prompt 中的标题"""
    apps_seq = []
    for f in session["frames"]:
        a = f["app"]
        if not apps_seq or apps_seq[-1] != a:
            apps_seq.append(a)
    return (
        f"[{session['day']} {session['start']}-{session['end']} "
        f"{session['duration_min']}min] {'→'.join(apps_seq)}"
    )


def _format_frame(frame: dict, max_chars: int) -> dict:
    """规范化单帧，截断长文本"""
    dt = datetime.fromtimestamp(frame["ts"])
    ocr = (frame.get("content") or "").strip().replace("\n", " ")
    if len(ocr) > max_chars:
        ocr = ocr[:max_chars] + "…"
    return {
        "t": dt.strftime("%H:%M"),
        "app": frame.get("app", "unknown"),
        "win": (frame.get("window") or "")[:80],
        "ocr": ocr,
        "file": frame.get("file_path", ""),
    }


def compress_events(events: list, config: dict) -> List[Dict]:
    """事件流 → 会话列表"""
    if not events:
        return []

    cfg = config.get("analysis", {})
    gap = cfg.get("session_gap_seconds", 300)
    sim_th = cfg.get("dedupe_similarity", 0.85)
    max_frames = cfg.get("max_frames_per_session", 12)
    max_chars = cfg.get("max_ocr_chars", 240)

    print("\n🗜  事件压缩")
    print(f"   原始事件: {len(events)} 条")

    # 切分会话
    raw_sessions = []
    current = [events[0]]
    for e in events[1:]:
        if e.get("gap_seconds", 0) > gap:
            raw_sessions.append(current)
            current = [e]
        else:
            current.append(e)
    if current:
        raw_sessions.append(current)

    print(f"   切分会话: {len(raw_sessions)} 个 (gap > {gap}s 即新会话)")

    # 压缩每个会话
    sessions = []
    for idx, frames in enumerate(raw_sessions):
        raw_count = len(frames)
        deduped = _dedupe_consecutive(frames, sim_th)
        sampled = _sample_long_session(deduped, max_frames)

        if not sampled:
            continue

        start_dt = datetime.fromtimestamp(sampled[0]["ts"])
        end_dt = datetime.fromtimestamp(sampled[-1]["ts"])
        duration_min = max(1, int((end_dt - start_dt).total_seconds() / 60))

        apps = []
        for f in sampled:
            if not apps or apps[-1] != f["app"]:
                apps.append(f["app"])

        session = {
            "id": f"S{idx + 1:03d}",
            "day": start_dt.strftime("%Y-%m-%d"),
            "start": start_dt.strftime("%H:%M"),
            "end": end_dt.strftime("%H:%M"),
            "duration_min": duration_min,
            "apps": apps,
            "frame_count": len(sampled),
            "raw_count": raw_count,
            "frames": [_format_frame(f, max_chars) for f in sampled],
        }
        session["summary_for_llm"] = _build_summary(session)
        sessions.append(session)

    total_raw = sum(s["raw_count"] for s in sessions)
    total_kept = sum(s["frame_count"] for s in sessions)
    if total_raw:
        ratio = round((1 - total_kept / total_raw) * 100, 1)
        print(f"   压缩率: {total_kept}/{total_raw} 帧保留 (压缩 {ratio}%)")

    return sessions


def render_sessions_for_llm(sessions: list) -> str:
    """把 sessions 渲染成 LLM prompt 中的纯文本块"""
    blocks = []
    for s in sessions:
        lines = [s["summary_for_llm"]]
        for f in s["frames"]:
            line = f"  {f['t']} [{f['app']}] {f['win']}"
            if f["ocr"]:
                line += f" :: {f['ocr']}"
            if f["file"]:
                line += f"  <{f['file']}>"
            lines.append(line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
