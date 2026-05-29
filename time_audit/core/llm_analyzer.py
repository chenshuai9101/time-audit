"""
时间审计 v2 — LLM 分析层

职责：
  1. 探活本地 Ollama
  2. 把 sessions 分批喂给本地模型，分别跑 点 / 线 / 面 三套 prompt
  3. 解析 JSON 输出（容错），合并多批结果

只依赖 stdlib。HTTP 走 urllib，JSON 走 json。
"""
import json
import urllib.request
import urllib.error
from typing import Optional

from time_audit.core import prompts, event_compressor


def ping_ollama(endpoint: str, timeout: int = 5) -> bool:
    """探测 Ollama 是否在跑"""
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def list_models(endpoint: str, timeout: int = 5) -> list:
    """列出本地已安装的模型"""
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def call_ollama(endpoint: str, model: str, system: str, user: str,
                temperature: float = 0.2, timeout: int = 600) -> Optional[str]:
    """单次调用 Ollama，返回 raw response 字符串"""
    body = {
        "model": model,
        "system": system,
        "prompt": user,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
    }
    req = urllib.request.Request(
        f"{endpoint}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read())
            return payload.get("response", "")
    except urllib.error.HTTPError as e:
        print(f"   ❌ Ollama HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"   ❌ Ollama 调用失败: {e}")
        return None


def _parse_json_lenient(raw: str, expected_key: str) -> list:
    """容错 JSON 解析：剥掉可能的前后缀，尝试找到 {...}"""
    if not raw:
        return []
    raw = raw.strip()

    candidates = [raw]
    # 截取首个 { 到末尾 } 的范围
    if "{" in raw and "}" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        candidates.append(raw[start:end])

    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and expected_key in obj:
                val = obj[expected_key]
                return val if isinstance(val, list) else []
        except Exception:
            continue
    return []


def _batch(sessions: list, size: int) -> list:
    """切分批次"""
    return [sessions[i:i + size] for i in range(0, len(sessions), size)]


def _build_context_hint(sessions: list, app_freq: dict) -> str:
    """给 LLM 的额外上下文（数据规模、app 概览）"""
    if not sessions:
        return ""
    days = len({s["day"] for s in sessions})
    apps = ", ".join(
        f"{a['app']}({a['duration_pct']}%)"
        for a in (app_freq.get("top_apps") or [])[:6]
    )
    return (
        f"数据规模：{len(sessions)} 个会话，跨 {days} 天。\n"
        f"主要应用耗时占比：{apps or '未统计'}。"
    )


def _run_single_layer(layer_name: str, system: str, user_template: str,
                      sessions: list, app_freq: dict, cfg: dict,
                      result_key: str) -> list:
    """对一层（点/线/面）做批量调用并合并结果"""
    endpoint = cfg["endpoint"]
    model = cfg["model"]
    temperature = cfg.get("temperature", 0.2)
    timeout = cfg.get("timeout_seconds", 600)
    batch_size = cfg.get("sessions_per_batch", 25)

    print(f"\n🤖 LLM 分析 — {layer_name}")
    batches = _batch(sessions, batch_size)
    print(f"   {len(sessions)} 会话 → {len(batches)} 批，模型 {model}")

    merged = []
    for i, batch in enumerate(batches, 1):
        sessions_text = event_compressor.render_sessions_for_llm(batch)
        context = _build_context_hint(batch, app_freq)
        user_prompt = prompts.render(user_template, sessions_text, context)

        print(f"   批 {i}/{len(batches)}: 调用中...", end="", flush=True)
        raw = call_ollama(endpoint, model, system, user_prompt,
                          temperature=temperature, timeout=timeout)
        if raw is None:
            print(" 失败")
            continue
        items = _parse_json_lenient(raw, result_key)
        print(f" 返回 {len(items)} 条")
        merged.extend(items)

    return merged


def analyze(sessions: list, app_freq: dict, llm_cfg: dict,
            sessions_per_batch: int = 25) -> dict:
    """主入口：跑点/线/面三层，返回合并 dict"""
    if not sessions:
        return {"points": [], "lines": [], "surfaces": []}

    cfg = dict(llm_cfg)
    cfg["sessions_per_batch"] = sessions_per_batch

    out = {"points": [], "lines": [], "surfaces": []}

    if cfg.get("analyze_points", True):
        out["points"] = _run_single_layer(
            "点（单点低效动作）",
            prompts.POINT_SYSTEM, prompts.POINT_USER,
            sessions, app_freq, cfg, "points")

    if cfg.get("analyze_lines", True):
        out["lines"] = _run_single_layer(
            "线（跨App固定流程）",
            prompts.LINE_SYSTEM, prompts.LINE_USER,
            sessions, app_freq, cfg, "lines")

    if cfg.get("analyze_surfaces", True):
        # 面：用更大的批（甚至全量）效果更好
        out["surfaces"] = _run_single_layer(
            "面（角色级工作模式）",
            prompts.SURFACE_SYSTEM, prompts.SURFACE_USER,
            sessions, app_freq, cfg, "surfaces")

    return out


def preflight(llm_cfg: dict) -> dict:
    """LLM 健康检查，返回 {ok, reason, models}"""
    endpoint = llm_cfg.get("endpoint", "http://localhost:11434")
    model = llm_cfg.get("model", "")

    if not ping_ollama(endpoint):
        return {
            "ok": False,
            "reason": f"Ollama 未运行（{endpoint} 不可达）",
            "models": [],
        }
    models = list_models(endpoint)
    if model and model not in models:
        return {
            "ok": False,
            "reason": f"模型 {model} 未安装。已安装: {models or '无'}",
            "models": models,
        }
    return {"ok": True, "reason": "", "models": models}
