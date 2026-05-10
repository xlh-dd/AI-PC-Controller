"""
AppContext - 应用全局上下文
统一管理所有模块实例，提供依赖注入。
模块通过 get_app_context().get("module_name") 获取依赖，
而非直接 import，保持解耦。
"""
import logging
import threading
import time
from typing import Any, Dict, Optional, Callable
from pathlib import Path

from .event_bus import EventBus, event_bus

logger = logging.getLogger("AppContext")


class ModuleHandle:
    """模块句柄，管理单个模块的生命周期"""

    def __init__(self, name: str, factory: Callable, **init_kwargs):
        self.name = name
        self.factory = factory
        self.init_kwargs = init_kwargs
        self._instance: Optional[Any] = None
        self._lock = threading.Lock()
        self._init_time: float = 0

    def get(self) -> Any:
        """懒加载获取实例"""
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    logger.info(f"[AppContext] Instantiating module: {self.name}")
                    t0 = time.time()
                    self._instance = self.factory(**self.init_kwargs)
                    self._init_time = time.time() - t0
                    logger.info(f"[AppContext] Module {self.name} ready in {self._init_time:.2f}s")
        return self._instance

    def is_ready(self) -> bool:
        return self._instance is not None

    def reload(self):
        """重新加载模块"""
        with self._lock:
            self._instance = None
            logger.info(f"[AppContext] Module {self.name} marked for reload")


class AppContext:
    """
    全局应用上下文。

    使用方式：
        ctx = get_app_context()
        ctx.register("ai_helper", factory=create_ai_helper)
        ai = ctx.get("ai_helper")   # 首次调用时真正实例化
    """

    def __init__(self):
        self._modules: Dict[str, ModuleHandle] = {}
        self._lock = threading.RLock()
        self._event_bus: EventBus = event_bus
        self._started = False
        self._start_time: float = 0

    # ── 注册 ────────────────────────────────────────────────────────────────

    def register(self, name: str, factory: Callable, **init_kwargs):
        """注册一个模块（懒加载工厂）"""
        with self._lock:
            self._modules[name] = ModuleHandle(name, factory, **init_kwargs)
            logger.debug(f"[AppContext] Registered module: {name}")

    def register_instance(self, name: str, instance: Any):
        """注册一个已实例化的对象（不懒加载）"""
        with self._lock:
            handle = ModuleHandle(name, lambda: instance)
            handle._instance = instance
            self._modules[name] = handle
            logger.debug(f"[AppContext] Registered instance: {name}")

    def unregister(self, name: str):
        """注销模块"""
        with self._lock:
            if name in self._modules:
                del self._modules[name]
                logger.debug(f"[AppContext] Unregistered: {name}")

    # ── 获取 ────────────────────────────────────────────────────────────────

    def get(self, name: str, default=None) -> Any:
        """获取模块实例（懒加载）"""
        with self._lock:
            handle = self._modules.get(name)
        if handle is None:
            if default is not None:
                return default
            raise KeyError(f"[AppContext] Module '{name}' not registered. "
                            f"Available: {list(self._modules.keys())}")
        return handle.get()

    def has(self, name: str) -> bool:
        """检查模块是否已注册"""
        with self._lock:
            return name in self._modules

    def is_ready(self, name: str) -> bool:
        """检查模块是否已实例化"""
        with self._lock:
            handle = self._modules.get(name)
        if handle is None:
            return False
        return handle.is_ready()

    def get_or_none(self, name: str) -> Optional[Any]:
        """安全获取，不抛异常"""
        try:
            return self.get(name)
        except KeyError:
            return None

    # ── 生命周期 ────────────────────────────────────────────────────────────

    def start(self):
        """启动上下文，触发所有已注册模块的预热"""
        if self._started:
            logger.warning("[AppContext] Already started")
            return
        self._started = True
        self._start_time = time.time()
        logger.info(f"[AppContext] Starting with {len(self._modules)} modules...")

        # 预热所有模块（触发懒加载）
        for name in list(self._modules.keys()):
            try:
                self.get(name)
            except Exception as e:
                logger.error(f"[AppContext] Failed to start module {name}: {e}", exc_info=True)

        elapsed = time.time() - self._start_time
        logger.info(f"[AppContext] Started in {elapsed:.2f}s")

    def reload(self, name: str):
        """热重载指定模块"""
        with self._lock:
            handle = self._modules.get(name)
        if handle:
            handle.reload()
            logger.info(f"[AppContext] Module {name} reloaded")

    def shutdown(self):
        """关闭上下文，清理所有模块"""
        logger.info("[AppContext] Shutting down...")
        for name in list(self._modules.keys()):
            inst = self.get_or_none(name)
            if inst and hasattr(inst, "shutdown"):
                try:
                    inst.shutdown()
                except Exception as e:
                    logger.error(f"[AppContext] Error shutting down {name}: {e}")

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def list_modules(self) -> Dict[str, bool]:
        """返回 {模块名: 是否已就绪}"""
        with self._lock:
            return {name: h.is_ready() for name, h in self._modules.items()}


# 全局单例
_app_context: Optional[AppContext] = None
_context_lock = threading.Lock()


def get_app_context() -> AppContext:
    global _app_context
    if _app_context is None:
        with _context_lock:
            if _app_context is None:
                _app_context = AppContext()
    return _app_context


def reset_app_context():
    """仅用于测试，重置全局上下文"""
    global _app_context
    with _context_lock:
        if _app_context:
            _app_context.shutdown()
        _app_context = None
