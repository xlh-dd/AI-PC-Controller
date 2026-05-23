"""
统一 AI 后端抽象接口

定义 AIBackend Protocol 及 BackendType 枚举，所有 AI 后端实现必须遵循此协议。
"""

import logging
from enum import Enum
from typing import Protocol, runtime_checkable

logger = logging.getLogger("AIBackend")


class BackendType(Enum):
    """AI 后端类型枚举"""
    DEEPSEEK = "deepseek"
    HERMES = "hermes"
    OLLAMA = "ollama"


@runtime_checkable
class AIBackend(Protocol):
    """AI 后端统一协议

    所有 AI 后端实现需提供以下接口：
    - name: 后端名称
    - is_available: 后端是否可用
    - chat: 发送消息并获取回复
    """

    @property
    def name(self) -> str:
        """后端名称"""
        ...

    @property
    def is_available(self) -> bool:
        """后端是否当前可用"""
        ...

    def chat(self, message: str,
             stream_callback: "Callable[[str], None] | None" = None,
             timeout: int = None) -> str:
        """发送聊天消息并获取 AI 回复

        Args:
            message: 用户输入消息
            stream_callback: 流式回调，每收到一个 token 调用一次
            timeout: 超时秒数，None 表示使用默认值

        Returns:
            AI 回复文本
        """
        ...