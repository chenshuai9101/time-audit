"""
时间审计 v2 — LLM Provider 抽象层

职责：把"调一次模型"这件事抽象成统一接口，屏蔽本地 / 云端差异。

两个实现：
  - OllamaProvider  本地，默认，隐私优先（数据不离机）
  - OpenAIProvider  云端，OpenAI 兼容 /chat/completions
                    覆盖 DeepSeek / 通义 Qwen API / OpenAI / Moonshot / OpenRouter 等

设计约束（开源卖点，务必保持）：
  - 仅依赖 stdlib：HTTP 走 urllib，JSON 走 json，不引入任何 SDK
  - 云端 api_key 只从环境变量读，绝不落进 config 文件
  - 云端默认关闭；启用即"数据离机"，由上层负责告警
"""
import os
import json
import urllib.request
import urllib.error
from typing import Optional


class ProviderError(Exception):
    """provider 配置/初始化错误（与运行时网络错误区分）"""


class BaseProvider:
    """统一接口。子类实现 chat / ping / installed_models。"""

    name = "base"

    def describe(self) -> str:
        """一行人类可读描述，给 banner / --check-llm 用"""
        raise NotImplementedError

    def is_cloud(self) -> bool:
        """是否会把数据发出本机。云端 True，决定上层是否打隐私警告。"""
        return False

    def chat(self, system: str, user: str, temperature: float = 0.2,
             timeout: int = 600) -> Optional[str]:
        """单次调用，返回模型原始文本；失败返回 None"""
        raise NotImplementedError

    def ping(self, timeout: int = 5) -> bool:
        """探活"""
        raise NotImplementedError

    def installed_models(self, timeout: int = 5) -> list:
        """可列出的模型（本地有意义；云端通常返回空，不强求）"""
        return []

    def preflight(self) -> dict:
        """健康检查，返回 {ok, reason, models}"""
        raise NotImplementedError


class OllamaProvider(BaseProvider):
    """本地 Ollama，/api/generate + /api/tags"""

    name = "ollama"

    def __init__(self, endpoint: str, model: str):
        self.endpoint = (endpoint or "http://localhost:11434").rstrip("/")
        self.model = model

    def describe(self) -> str:
        return f"{self.model} @ {self.endpoint} (本地)"

    def is_cloud(self) -> bool:
        return False

    def ping(self, timeout: int = 5) -> bool:
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=timeout) as r:
                return r.status == 200
        except Exception:
            return False

    def installed_models(self, timeout: int = 5) -> list:
        try:
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=timeout) as r:
                data = json.loads(r.read())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def chat(self, system: str, user: str, temperature: float = 0.2,
             timeout: int = 600) -> Optional[str]:
        body = {
            "model": self.model,
            "system": system,
            "prompt": user,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }
        req = urllib.request.Request(
            f"{self.endpoint}/api/generate",
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

    def preflight(self) -> dict:
        if not self.ping():
            return {"ok": False,
                    "reason": f"Ollama 未运行（{self.endpoint} 不可达）",
                    "models": []}
        models = self.installed_models()
        if self.model and self.model not in models:
            return {"ok": False,
                    "reason": f"模型 {self.model} 未安装。已安装: {models or '无'}",
                    "models": models}
        return {"ok": True, "reason": "", "models": models}


class OpenAIProvider(BaseProvider):
    """云端，OpenAI 兼容 /chat/completions。api_key 从环境变量读取。"""

    name = "openai"

    def __init__(self, base_url: str, model: str, api_key_env: str = "TIME_AUDIT_API_KEY",
                 json_mode: bool = True):
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = model
        self.api_key_env = api_key_env or "TIME_AUDIT_API_KEY"
        self.api_key = os.environ.get(self.api_key_env, "").strip()
        self.json_mode = json_mode

    def describe(self) -> str:
        return f"{self.model} @ {self.base_url} (云端)"

    def is_cloud(self) -> bool:
        return True

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def ping(self, timeout: int = 5) -> bool:
        """有 key 即视为可用；真正的可达性在首次 chat 暴露。
        不主动打 /models —— 部分兼容端点不实现它，反而误报不可用。"""
        return bool(self.api_key)

    def chat(self, system: str, user: str, temperature: float = 0.2,
             timeout: int = 600) -> Optional[str]:
        if not self.api_key:
            print(f"   ❌ 未设置云端 API key（环境变量 {self.api_key_env}）")
            return None
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "stream": False,
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.loads(r.read())
                choices = payload.get("choices") or []
                if not choices:
                    print(f"   ❌ 云端返回无 choices: {str(payload)[:200]}")
                    return None
                return choices[0].get("message", {}).get("content", "")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "ignore")[:200]
            except Exception:
                pass
            print(f"   ❌ 云端 HTTP {e.code}: {e.reason} {detail}")
            return None
        except Exception as e:
            print(f"   ❌ 云端调用失败: {e}")
            return None

    def preflight(self) -> dict:
        if not self.model:
            return {"ok": False, "reason": "云端未配置 model（llm.cloud.model）", "models": []}
        if not self.api_key:
            return {"ok": False,
                    "reason": f"未设置云端 API key：请 export {self.api_key_env}=...",
                    "models": []}
        return {"ok": True, "reason": "", "models": []}


def get_provider(llm_cfg: dict) -> BaseProvider:
    """工厂：按 llm.provider 分发。默认 ollama（本地、隐私优先）。

    config 形态：
      llm:
        provider: ollama        # ollama | openai
        endpoint: http://localhost:11434
        model: qwen2.5:7b
        cloud:                  # provider=openai 时生效
          base_url: https://api.deepseek.com/v1
          model: deepseek-chat
          api_key_env: TIME_AUDIT_API_KEY
          json_mode: true
    """
    provider = (llm_cfg.get("provider") or "ollama").lower()

    if provider in ("ollama", "local"):
        return OllamaProvider(
            endpoint=llm_cfg.get("endpoint", "http://localhost:11434"),
            model=llm_cfg.get("model", ""),
        )

    if provider in ("openai", "cloud", "openai-compatible"):
        cloud = llm_cfg.get("cloud") or {}
        return OpenAIProvider(
            base_url=cloud.get("base_url", "https://api.openai.com/v1"),
            model=cloud.get("model", ""),
            api_key_env=cloud.get("api_key_env", "TIME_AUDIT_API_KEY"),
            json_mode=cloud.get("json_mode", True),
        )

    raise ProviderError(
        f"未知 provider: {provider!r}（支持 ollama | openai）"
    )
