"""
OllamaBackend — 本地 Ollama 后端

封装 modules.ai_helper.AIHelper，通过 Ollama 本地模型提供对话能力。
"""

import logging
from typing import Callable, Optional

from backends.base import BackendType

logger = logging.getLogger("OllamaBackend")


class OllamaBackend:
    """Ollama 后端实现

    通过 AIHelper 调用本地 Ollama 模型。
    支持流式回调、超时控制。
    """

    def __init__(self, config_manager=None):
        self._config_manager = config_manager
        self._helper = None

    @property
    def name(self) -> str:
        return BackendType.OLLAMA.value

    @property
    def is_available(self) -> bool:
        helper = self._get_helper()
        if helper is None:
            return False
        return helper.use_ai_features

    def _get_helper(self):
        """延迟加载 AIHelper，避免循环依赖"""
        if self._helper is None:
            from modules.ai_helper import AIHelper
            self._helper = AIHelper(config_manager=self._config_manager)
        return self._helper

    def chat(self, message: str,
             stream_callback: Callable[[str], None] = None,
             timeout: int = None) -> str:
        """发送聊天消息

        委托给 AIHelper.ai_query()，完成本地 Ollama 模型调用。

        Args:
            message: 用户输入消息
            stream_callback: 流式回调
            timeout: 超时秒数

        Returns:
            AI 回复文本
        """
        helper = self._get_helper()
        if helper is None:
            return "[错误] AIHelper 未初始化"

        actual_timeout = timeout if timeout is not None else 60

        result = helper.ai_query(
            prompt=message,
            stream_callback=stream_callback,
            timeout=actual_timeout,
        )
        if result is None:
            return "[错误] Ollama 模型无响应"
        return result