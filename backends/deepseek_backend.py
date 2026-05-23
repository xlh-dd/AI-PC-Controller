"""
DeepSeekBackend — 直连 DeepSeek API 后端

封装 services.deepseek_client.DeepSeekClient，遵循 AIBackend Protocol，
将单条消息自动转换为 messages 列表格式后调用底层客户端。
"""

import logging
from typing import Callable, Optional

from backends.base import BackendType

logger = logging.getLogger("DeepSeekBackend")


class DeepSeekBackend:
    """DeepSeek 后端实现

    直接调用 DeepSeek API，不经过 Hermes/WSL。
    支持流式输出、超时控制。
    """

    def __init__(self, config_manager=None):
        self._config_manager = config_manager
        self._client = None

    @property
    def name(self) -> str:
        return BackendType.DEEPSEEK.value

    @property
    def is_available(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        return bool(client.api_key)

    def _get_client(self):
        """延迟加载 DeepSeekClient，避免循环依赖"""
        if self._client is None:
            from services.deepseek_client import DeepSeekClient
            self._client = DeepSeekClient(config_manager=self._config_manager)
        return self._client

    def chat(self, message: str,
             stream_callback: Callable[[str], None] = None,
             timeout: int = None) -> str:
        """发送聊天消息

        将单条消息转换为 messages 列表格式，委托给 DeepSeekClient.chat()。

        Args:
            message: 用户输入消息
            stream_callback: 流式回调
            timeout: 超时秒数

        Returns:
            AI 回复文本
        """
        client = self._get_client()
        if client is None:
            return "[错误] DeepSeek 客户端未初始化"

        messages = [{"role": "user", "content": message}]
        actual_timeout = timeout if timeout is not None else 60

        return client.chat(
            messages=messages,
            stream_callback=stream_callback,
            timeout=actual_timeout,
        )