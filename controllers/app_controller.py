"""
AppController — 应用主控制器

统一管理 AI 后端、配置和核心业务逻辑的协调。
不依赖 tkinter，可在 GUI 和非 GUI 上下文中使用。
"""

import logging
import threading
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.config import ConfigManager
    from backends.base import AIBackend

logger = logging.getLogger("AppController")


class AppController:
    """应用主控制器

    持有配置管理器和当前活跃的 AI 后端引用，
    负责后端初始化、切换和配置访问。
    """

    def __init__(self, config_manager: "ConfigManager"):
        self._config_manager = config_manager
        self._backend: Optional["AIBackend"] = None
        self._backends: dict = {}
        self._lock = threading.RLock()
        self._initialized = False

    def get_config(self) -> "ConfigManager":
        """获取配置管理器"""
        return self._config_manager

    def get_backend(self) -> Optional["AIBackend"]:
        """获取当前活跃的 AI 后端"""
        return self._backend

    def set_backend(self, backend: "AIBackend"):
        """切换 AI 后端

        Args:
            backend: 新的 AI 后端实例
        """
        with self._lock:
            self._backend = backend
            logger.info(f"AI 后端已切换: {type(backend).__name__}")

    def initialize_backends(self):
        """初始化所有 AI 后端

        按配置中的 current_api_provider 选择首选后端：
        - hermes → HermesBackend
        - deepseek → DeepSeekBackend
        - ollama → OllamaBackend
        未知或不可用时回退到 HermesBackend。
        """
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return
            self._initialized = True

        from backends.deepseek_backend import DeepSeekBackend
        from backends.hermes_backend import HermesBackend
        from backends.ollama_backend import OllamaBackend

        logger.info("正在初始化 AI 后端...")

        self._backends["deepseek"] = DeepSeekBackend(config_manager=self._config_manager)
        self._backends["hermes"] = HermesBackend(config_manager=self._config_manager)
        self._backends["ollama"] = OllamaBackend(config_manager=self._config_manager)

        provider = self._config_manager.get_current_provider()
        preferred = self._backends.get(provider)

        if preferred is None:
            logger.warning(f"未知的服务商 '{provider}'，回退到 HermesBackend")
            preferred = self._backends.get("hermes")

        self._backend = preferred
        logger.info(f"AI 后端初始化完成，当前: {type(self._backend).__name__}")

    def get_backend_by_name(self, name: str) -> Optional["AIBackend"]:
        """按名称获取已注册的后端

        Args:
            name: 后端名称 (deepseek / hermes / ollama)

        Returns:
            AIBackend 实例，未找到返回 None
        """
        return self._backends.get(name)