"""
DeepSeekClient — 直连 DeepSeek API 客户端

用于 AI 助手聊天对话，绕过 Hermes/WSL，直接调用 DeepSeek API。
支持流式输出、会话管理、模型切换。
"""

import json
import logging
import threading
import time
from typing import Optional, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger("DeepSeekClient")

# DeepSeek V4 模型
DEFAULT_MODEL = "deepseek-chat"  # V4 通用
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# 备用：OpenRouter 端点
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class DeepSeekClient:
    """轻量级 DeepSeek API 客户端"""

    def __init__(self, api_key: str = None, base_url: str = None,
                 model: str = None, config_manager=None):
        self._api_key = api_key
        self._base_url = base_url or DEEPSEEK_URL
        self._model = model or DEFAULT_MODEL
        self._config = config_manager
        self._lock = threading.Lock()
        self._cached_key: Optional[str] = None  # 缓存避免重复读 WSL

    @property
    def api_key(self) -> str:
        if self._cached_key:
            return self._cached_key
        if self._api_key:
            self._cached_key = self._api_key
            return self._api_key
        # 从配置读取
        if self._config:
            key = self._config.get("deepseek_api_key", "")
            if key:
                self._cached_key = key
                return key
        # 从环境变量读取
        import os
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if key:
            self._cached_key = key
            return key
        # WSL fallback — 从 Windows 侧读取 WSL 文件系统（无需启动 WSL）
        try:
            env_path = r"\\wsl$\Ubuntu-22.04\home\xlh\.hermes\.env"
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('DEEPSEEK_API_KEY='):
                        key = line.strip().split('=', 1)[1]
                        if key:
                            self._cached_key = key
                            return key
        except Exception:
            pass
        return ""

    @property
    def model(self) -> str:
        if self._config:
            return self._config.get("deepseek_model", self._model)
        return self._model

    def set_model(self, model_id: str):
        model_map = {
            "ds-v4-flash": "deepseek-chat",
            "ds-v4-flash-r": "deepseek-chat",
            "ds-v4-pro": "deepseek-chat",
            "ds-v4-pro-r": "deepseek-reasoner",
        }
        self._model = model_map.get(model_id, model_id)

    def chat(self, messages: list, stream_callback: Callable[[str], None] = None,
             timeout: int = 60, system_prompt: str = "") -> str:
        """发送聊天请求，支持流式输出
        
        Args:
            messages: [{"role": "user"/"assistant", "content": "..."}, ...]
            stream_callback: 流式回调 (接收每个 token)
            timeout: 超时秒数
            system_prompt: 系统提示
        
        Returns:
            AI 回复文本
        """
        api_key = self.api_key
        if not api_key:
            return "[错误] DeepSeek API Key 未配置"

        # 构建请求体
        msg_list = []
        if system_prompt:
            msg_list.append({"role": "system", "content": system_prompt})
        msg_list.extend(messages)

        payload = {
            "model": self.model,
            "messages": msg_list,
            "stream": stream_callback is not None,
            "temperature": 0.7,
            "max_tokens": 4096,
        }

        return self._do_request(payload, stream_callback, timeout)

    def _do_request(self, payload: dict,
                    stream_callback: Callable[[str], None] = None,
                    timeout: int = 60) -> str:
        """执行 HTTP 请求"""
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            req = Request(self._base_url, data=data, headers=headers,
                         method="POST")

            if stream_callback:
                return self._stream_response(req, timeout, stream_callback)
            else:
                return self._blocking_response(req, timeout)

        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(f"DeepSeek API HTTP {e.code}: {body[:200]}")
            return f"[错误] API 请求失败 ({e.code})"
        except URLError as e:
            logger.error(f"DeepSeek API 网络错误: {e.reason}")
            return f"[错误] 网络连接失败: {e.reason}"
        except Exception as e:
            logger.error(f"DeepSeek API 异常: {e}")
            return f"[错误] {e}"

    def _blocking_response(self, req: Request, timeout: int) -> str:
        """阻塞模式"""
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            choices = result.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return "(空响应)"

    def _stream_response(self, req: Request, timeout: int,
                         callback: Callable[[str], None]) -> str:
        """流式模式 — 逐行解析 SSE"""
        full_text = []

        try:
            with urlopen(req, timeout=timeout) as resp:
                for line_bytes in resp:
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text.append(content)
                            callback(content)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"流式读取异常: {e}")

        return "".join(full_text)


# ── 全局单例 ──
_deepseek_client: Optional[DeepSeekClient] = None
_instance_lock = threading.Lock()


def get_deepseek_client(config_manager=None) -> DeepSeekClient:
    global _deepseek_client
    if _deepseek_client is None:
        with _instance_lock:
            if _deepseek_client is None:
                _deepseek_client = DeepSeekClient(config_manager=config_manager)
    return _deepseek_client