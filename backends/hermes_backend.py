"""
HermesBackend — Hermes 降级链后端

封装 services.agent_service.AgentService，利用其自动降级链
（Hermes → AIAgentCore → Ollama）提供统一对话能力。
"""

import logging
from typing import Callable, Optional

from backends.base import BackendType

logger = logging.getLogger("HermesBackend")


class HermesBackend:
    """Hermes 后端实现

    通过 AgentService 统一入口调用 AI 能力，自动处理后端降级。
    支持多轮对话历史管理。
    """

    def __init__(self, config_manager=None):
        self._config_manager = config_manager
        self._agent_service = None

    @property
    def name(self) -> str:
        return BackendType.HERMES.value

    @property
    def is_available(self) -> bool:
        agent = self._get_agent_service()
        if agent is None:
            return False
        agent.ensure_ready()
        backend = agent.get_preferred_backend()
        return backend != "none"

    def _get_agent_service(self):
        """延迟加载 AgentService，避免循环依赖"""
        if self._agent_service is None:
            from services.agent_service import get_agent_service
            self._agent_service = get_agent_service(
                config_manager=self._config_manager
            )
        return self._agent_service

    def chat(self, message: str,
             stream_callback: Callable[[str], None] = None,
             timeout: int = None) -> str:
        """发送聊天消息（多轮对话）

        委托给 AgentService.chat_with_history()，自动拼接历史上下文。

        Args:
            message: 用户输入消息
            stream_callback: 流式回调
            timeout: 超时秒数

        Returns:
            AI 回复文本
        """
        agent = self._get_agent_service()
        if agent is None:
            return "[错误] AgentService 未初始化"

        return agent.chat_with_history(
            message=message,
            stream_callback=stream_callback,
            timeout=timeout,
        )