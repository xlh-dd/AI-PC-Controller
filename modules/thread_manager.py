import threading
import logging
from contextlib import contextmanager

logger = logging.getLogger("ThreadManager")

class ThreadManager:
    """线程管理器 - 统一管理所有工作线程（单例模式）"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """单例模式：确保全局只有一个 ThreadManager 实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化线程管理器（仅执行一次）"""
        if ThreadManager._initialized:
            return
        
        self._threads = {}
        self._locks = {}
        self._stop_events = {}
        self._callbacks = {}
        ThreadManager._initialized = True
        logger.info("ThreadManager 单例初始化完成")

    def create_lock(self, name):
        if name not in self._locks:
            self._locks[name] = threading.Lock()
        return self._locks[name]

    def get_lock(self, name):
        return self._locks.get(name)

    def create_stop_event(self, name):
        if name not in self._stop_events:
            self._stop_events[name] = threading.Event()
        return self._stop_events[name]

    def get_stop_event(self, name):
        return self._stop_events.get(name)

    def is_stopped(self, name):
        event = self._stop_events.get(name)
        return event and event.is_set()

    def set_stopped(self, name):
        if name in self._stop_events:
            self._stop_events[name].set()

    def start_thread(self, name, target, args=(), daemon=True):
        self.stop_thread(name)

        stop_event = threading.Event()
        self._stop_events[name] = stop_event

        def wrapped_target(*args):
            try:
                target(*args)
            except Exception as e:
                logger.error(f"Thread {name} error: {e}")
            finally:
                stop_event.set()
                logger.info(f"Thread {name} stopped")

        thread = threading.Thread(target=wrapped_target, args=args, daemon=daemon)
        self._threads[name] = thread
        thread.start()
        logger.info(f"Thread {name} started")
        return thread

    def stop_thread(self, name, timeout=3):
        if name in self._stop_events:
            self._stop_events[name].set()

        if name in self._threads:
            thread = self._threads[name]
            if thread.is_alive():
                thread.join(timeout=timeout)
            if not thread.is_alive():
                del self._threads[name]
                if name in self._stop_events:
                    del self._stop_events[name]
                logger.info(f"Thread {name} cleaned up")
                return True
        return False

    def stop_all(self, timeout=3):
        for name in list(self._threads.keys()):
            self.stop_thread(name, timeout)

    def is_running(self, name):
        thread = self._threads.get(name)
        return thread and thread.is_alive()

    @contextmanager
    def lock(self, name):
        lock = self.create_lock(name)
        with lock:
            yield lock

    def safe_execute(self, name, func, *args, **kwargs):
        with self.lock(name):
            return func(*args, **kwargs)

thread_manager = ThreadManager()
