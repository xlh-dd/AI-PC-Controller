"""
通用辅助函数模块
用于减少重复代码，提高代码复用性
"""
import time
import logging
import functools
import threading
from typing import Any, Callable, Optional, Type, TypeVar, Union, Dict, List

logger = logging.getLogger("Helpers")

T = TypeVar('T')

_DEPENDENCY_REGISTRY: Dict[str, bool] = {}
_DEPENDENCY_MODULES: Dict[str, Any] = {}

def check_dependency(module_name: str, package_name: Optional[str] = None, raise_error: bool = False) -> bool:
    """检查依赖是否可用
    
    Args:
        module_name: 模块名
        package_name: PyPI包名（如果与模块名不同）
        raise_error: 是否在缺失时抛出ImportError
        
    Returns:
        是否可用
    """
    try:
        __import__(module_name)
        return True
    except ImportError:
        if raise_error:
            raise ImportError(f"需要 {package_name or module_name} 库，请运行: pip install {package_name or module_name}")
        return False

def register_dependency(module_name: str, package_name: Optional[str] = None) -> bool:
    """注册并检查依赖，将其状态缓存到注册表中
    
    Args:
        module_name: 模块名
        package_name: PyPI包名（如果与模块名不同）
        
    Returns:
        是否可用
    """
    key = module_name
    if key in _DEPENDENCY_REGISTRY:
        return _DEPENDENCY_REGISTRY[key]
    
    try:
        module = __import__(module_name)
        _DEPENDENCY_REGISTRY[key] = True
        _DEPENDENCY_MODULES[key] = module
        return True
    except ImportError:
        _DEPENDENCY_REGISTRY[key] = False
        _DEPENDENCY_MODULES[key] = None
        # 改为 debug 级别，避免启动刷屏
        if package_name:
            logger.debug(f"{package_name}模块未安装，相关功能将不可用")
        else:
            logger.debug(f"{module_name}模块未安装，相关功能将不可用")
        return False

def is_dependency_available(module_name: str) -> bool:
    """检查依赖是否可用（从注册表）
    
    Args:
        module_name: 模块名
        
    Returns:
        是否可用
    """
    return _DEPENDENCY_REGISTRY.get(module_name, False)

def get_dependency_module(module_name: str) -> Any:
    """获取已注册的依赖模块
    
    Args:
        module_name: 模块名
        
    Returns:
        模块对象，如果不可用返回None
    """
    return _DEPENDENCY_MODULES.get(module_name)

def get_install_command(module_name: str) -> str:
    """获取模块的安装命令
    
    Args:
        module_name: 模块名
        
    Returns:
        pip安装命令
    """
    return f"pip install {module_name}"

def check_dependencies(*dependencies: str) -> Dict[str, bool]:
    """批量检查多个依赖的可用性
    
    Args:
        *dependencies: 模块名列表
        
    Returns:
        模块名到可用性的字典
    """
    results = {}
    for dep in dependencies:
        results[dep] = is_dependency_available(dep) or check_dependency(dep)
    return results

def retry(max_attempts: int = 3, delay: float = 1.0, 
          exceptions: Type[Exception] = Exception, 
          logger: Optional[logging.Logger] = None) -> Callable:
    """重试装饰器
    
    Args:
        max_attempts: 最大尝试次数
        delay: 重试延迟（秒）
        exceptions: 捕获的异常类型
        logger: 日志记录器
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if logger:
                        logger.warning(f"{func.__name__} 第{attempt}次尝试失败: {e}")
                    if attempt < max_attempts:
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

def safe_get(dictionary: dict, key: Any, default: Any = None, 
             log_error: bool = False, error_message: str = "") -> Any:
    """安全获取字典值，避免KeyError
    
    Args:
        dictionary: 字典
        key: 键
        default: 默认值
        log_error: 是否记录错误
        error_message: 自定义错误消息
        
    Returns:
        值或默认值
    """
    try:
        return dictionary[key]
    except KeyError:
        if log_error:
            msg = error_message or f"字典中缺少键: {key}"
            logger.warning(msg)
        return default

def format_file_size(size_bytes: int) -> str:
    """格式化文件大小（字节转换为易读格式）"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def timeit(func: Callable) -> Callable:
    """计时装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.info(f"{func.__name__} 执行时间: {end - start:.3f}秒")
        return result
    return wrapper

def validate_range(value: Union[int, float], min_val: Union[int, float], 
                   max_val: Union[int, float], default: Union[int, float]) -> Union[int, float]:
    """验证值是否在范围内，否则返回默认值"""
    if min_val <= value <= max_val:
        return value
    logger.warning(f"值 {value} 不在范围 [{min_val}, {max_val}] 内，使用默认值 {default}")
    return default

class Singleton(type):
    """单例元类"""
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class LRUCache:
    """简单LRU缓存"""
    
    def __init__(self, maxsize: int = 128):
        self.cache = {}
        self.access_order = []
        self.maxsize = maxsize
    
    def get(self, key: Any, default: Any = None) -> Any:
        if key in self.cache:
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return default
    
    def set(self, key: Any, value: Any):
        if key in self.cache:
            self.access_order.remove(key)
        elif len(self.cache) >= self.maxsize:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
        
        self.cache[key] = value
        self.access_order.append(key)
    
    def clear(self):
        self.cache.clear()
        self.access_order.clear()
    
    def __contains__(self, key: Any) -> bool:
        return key in self.cache
    
    def __len__(self) -> int:
        return len(self.cache)

class AIServiceWrapper:
    """AI服务包装器 - 提供统一的AI查询接口和缓存"""
    
    def __init__(self, ai_helper=None, ollama_url="http://localhost:11434/api/generate", 
                 model="qwen2.5:1.5b", cache_size: int = 64, max_retries: int = 3):
        self.ai_helper = ai_helper
        self.ollama_url = ollama_url
        self.model = model
        self.max_retries = max_retries
        self.cache = LRUCache(maxsize=cache_size)
        self._requests_available = check_dependency("requests")
    
    def query(self, prompt: str, use_cache: bool = True) -> str:
        """查询AI服务
        
        Args:
            prompt: 提示词
            use_cache: 是否使用缓存
            
        Returns:
            AI响应文本
        """
        if use_cache:
            cached = self.cache.get(prompt)
            if cached:
                logger.debug(f"使用缓存结果: {prompt[:50]}...")
                return cached
        
        result = self._query_with_retry(prompt)
        
        if use_cache and result:
            self.cache.set(prompt, result)
        
        return result
    
    def _query_with_retry(self, prompt: str) -> str:
        """带重试的查询"""
        for attempt in range(self.max_retries):
            try:
                if self.ai_helper:
                    result = self.ai_helper.ai_query(prompt)
                    if result:
                        return result
                elif self._requests_available:
                    return self._query_ollama(prompt)
                else:
                    logger.error("无可用的AI服务")
                    return ""
            except Exception as e:
                logger.warning(f"AI查询第{attempt+1}次失败: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        
        return ""
    
    def _query_ollama(self, prompt: str) -> str:
        """查询Ollama API"""
        import requests
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        
        try:
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                logger.warning(f"Ollama调用失败，状态码: {response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.error(f"无法连接到Ollama服务: {self.ollama_url}")
        except Exception as e:
            logger.error(f"Ollama调用异常: {e}")
        
        return ""
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
    
    def get_cache_size(self) -> int:
        """获取缓存大小"""
        return len(self.cache)

def create_thread_safe_logger(name: str) -> logging.Logger:
    """创建线程安全的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        配置好的Logger对象
    """
    log = logging.getLogger(name)
    
    if not log.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    
    return log

def safe_execute(func: Callable, *args, 
                default_return: Any = None,
                log_errors: bool = True,
                error_message: str = "",
                **kwargs) -> Any:
    """安全执行函数，返回默认值而非抛出异常
    
    Args:
        func: 要执行的函数
        *args: 位置参数
        default_return: 失败时返回的默认值
        log_errors: 是否记录错误
        error_message: 自定义错误消息
        **kwargs: 关键字参数
        
    Returns:
        函数执行结果或默认值
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            msg = error_message or f"执行 {func.__name__} 时出错: {e}"
            logger.error(msg)
        return default_return

def log_exception(exc: Exception, context: str = "", 
                 level: str = "error", 
                 include_traceback: bool = False) -> str:
    """记录异常的详细信息
    
    Args:
        exc: 异常对象
        context: 上下文信息
        level: 日志级别 (debug/info/warning/error/critical)
        include_traceback: 是否包含堆栈跟踪
        
    Returns:
        格式化的错误消息
    """
    import traceback
    
    exc_type = type(exc).__name__
    exc_msg = str(exc)
    
    if context:
        msg = f"[{context}] {exc_type}: {exc_msg}"
    else:
        msg = f"{exc_type}: {exc_msg}"
    
    if include_traceback:
        tb = traceback.format_exc()
        msg += f"\n堆栈跟踪:\n{tb}"
    
    log_func = getattr(logger, level.lower(), logger.error)
    log_func(msg)
    
    return msg

def fallback(default_value: Any = None, 
            exceptions: tuple = (Exception,),
            log_errors: bool = True,
            error_message: str = "") -> Callable:
    """函数执行失败时的回退装饰器
    
    Args:
        default_value: 失败时返回的默认值
        exceptions: 捕获的异常类型元组
        log_errors: 是否记录错误
        error_message: 自定义错误消息
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                if log_errors:
                    msg = error_message or f"{func.__name__} 执行失败: {e}"
                    logger.warning(msg)
                return default_value
        return wrapper
    return decorator

class ErrorContext:
    """错误上下文管理器 - 提供更精细的异常处理"""
    
    def __init__(self, context: str = "", 
                 default_return: Any = None,
                 reraise: bool = False,
                 log_level: str = "error"):
        self.context = context
        self.default_return = default_return
        self.reraise = reraise
        self.log_level = log_level
        self.error = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error = exc_val
            msg = f"[{self.context}] {exc_type.__name__}: {exc_val}"
            log_func = getattr(logger, self.log_level.lower(), logger.error)
            log_func(msg)
            
            if self.reraise:
                return False
            return True
        
        return False
    
    def get_error(self) -> Optional[Exception]:
        """获取捕获的异常"""
        return self.error

class SuppressErrors:
    """抑制特定错误的上下文管理器"""
    
    def __init__(self, *error_types, log_errors: bool = False):
        self.error_types = error_types
        self.log_errors = log_errors
        self.error = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and issubclass(exc_type, self.error_types):
            self.error = exc_val
            if self.log_errors:
                logger.debug(f"已抑制错误: {exc_type.__name__}: {exc_val}")
            return True
        return False
    
    def get_error(self) -> Optional[Exception]:
        """获取被抑制的错误"""
        return self.error

class ThreadManager:
    """线程管理器 - 统一管理后台线程，避免线程泄漏"""
    
    def __init__(self):
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
    
    def start_thread(self, name: str, target: Callable, *args, 
                    daemon: bool = True, **kwargs) -> bool:
        """启动一个命名线程
        
        Args:
            name: 线程名称
            target: 目标函数
            *args: 位置参数
            daemon: 是否为守护线程
            **kwargs: 关键字参数
            
        Returns:
            是否成功启动
        """
        with self._lock:
            if name in self._threads and self._threads[name].is_alive():
                logger.warning(f"线程 {name} 已在运行中")
                return False
            
            stop_event = threading.Event()
            self._stop_events[name] = stop_event
            self._threads[name] = threading.Thread(
                target=target,
                args=args,
                kwargs={**kwargs, "_stop_event": stop_event},
                daemon=daemon,
                name=name
            )
            self._threads[name].start()
            logger.info(f"线程 {name} 已启动")
            return True
    
    def stop_thread(self, name: str, timeout: float = 3.0) -> bool:
        """停止一个命名线程
        
        Args:
            name: 线程名称
            timeout: 等待超时时间
            
        Returns:
            是否成功停止
        """
        with self._lock:
            if name not in self._threads:
                return True
            
            stop_event = self._stop_events.get(name)
            if stop_event:
                stop_event.set()
            
            thread = self._threads[name]
            thread.join(timeout=timeout)
            
            if thread.is_alive():
                logger.warning(f"线程 {name} 无法正常停止")
                return False
            
            del self._threads[name]
            if name in self._stop_events:
                del self._stop_events[name]
            
            logger.info(f"线程 {name} 已停止")
            return True
    
    def stop_all(self, timeout: float = 3.0):
        """停止所有线程"""
        with self._lock:
            thread_names = list(self._threads.keys())
        
        for name in thread_names:
            self.stop_thread(name, timeout)
    
    def is_running(self, name: str) -> bool:
        """检查线程是否正在运行"""
        with self._lock:
            if name not in self._threads:
                return False
            return self._threads[name].is_alive()
    
    def get_running_threads(self) -> List[str]:
        """获取所有正在运行的线程名称"""
        with self._lock:
            return [name for name, thread in self._threads.items() if thread.is_alive()]
    
    def get_thread(self, name: str) -> Optional[threading.Thread]:
        """获取指定线程"""
        with self._lock:
            return self._threads.get(name)

def run_in_main_thread(root, func: Callable, *args, **kwargs):
    """在线程中安全地运行UI更新函数
    
    Args:
        root: Tkinter根窗口
        func: 要执行的函数
        *args: 位置参数
        **kwargs: 关键字参数
    """
    if threading.current_thread() is threading.main_thread():
        func(*args, **kwargs)
    else:
        root.after(0, lambda: func(*args, **kwargs))