import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.helpers import (
    check_dependency, register_dependency, is_dependency_available,
    LRUCache, AIServiceWrapper, safe_execute, log_exception,
    ErrorContext, SuppressErrors, ThreadManager, run_in_main_thread,
    retry, validate_range, format_file_size, safe_get
)


class TestDependencyManagement:
    """测试依赖管理功能"""

    def test_check_dependency_available(self):
        """测试检查可用依赖"""
        result = check_dependency("os")
        assert result is True

    def test_check_dependency_unavailable(self):
        """测试检查不可用依赖"""
        result = check_dependency("nonexistent_module_12345")
        assert result is False

    def test_register_dependency(self):
        """测试注册依赖"""
        result = register_dependency("json")
        assert result is True
        assert is_dependency_available("json") is True


class TestLRUCache:
    """测试LRU缓存"""

    def test_cache_set_get(self):
        """测试缓存存取"""
        cache = LRUCache(maxsize=3)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_cache_miss(self):
        """测试缓存未命中"""
        cache = LRUCache(maxsize=3)
        assert cache.get("nonexistent") is None

    def test_cache_eviction(self):
        """测试缓存淘汰"""
        cache = LRUCache(maxsize=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_cache_clear(self):
        """测试清空缓存"""
        cache = LRUCache(maxsize=3)
        cache.set("key1", "value1")
        cache.clear()
        assert len(cache) == 0


class TestSafeExecute:
    """测试安全执行函数"""

    def test_safe_execute_success(self):
        """测试成功执行"""
        def add(a, b):
            return a + b

        result = safe_execute(add, 1, 2, default_return=0)
        assert result == 3

    def test_safe_execute_exception(self):
        """测试异常处理"""
        def raise_error():
            raise ValueError("test error")

        result = safe_execute(raise_error, default_return="error", log_errors=False)
        assert result == "error"

    def test_safe_execute_with_args(self):
        """测试带参数函数"""
        def divide(a, b):
            return a / b

        result = safe_execute(divide, 10, 2, default_return=0)
        assert result == 5

        result = safe_execute(divide, 10, 0, default_return=-1)
        assert result == -1


class TestErrorContext:
    """测试错误上下文管理器"""

    def test_error_context_no_exception(self):
        """测试无异常情况"""
        with ErrorContext("test") as ctx:
            result = 1 + 1

        assert ctx.get_error() is None
        assert result == 2

    def test_error_context_with_exception(self):
        """测试有异常情况"""
        with ErrorContext("test", default_return=-1) as ctx:
            raise ValueError("test error")

        assert ctx.get_error() is not None
        assert isinstance(ctx.get_error(), ValueError)


class TestSuppressErrors:
    """测试错误抑制"""

    def test_suppress_specific_error(self):
        """测试抑制特定错误"""
        with SuppressErrors(ValueError, log_errors=True) as ctx:
            raise ValueError("suppressed")

        assert ctx.get_error() is not None

    def test_suppress_different_error(self):
        """测试不抑制其他错误"""
        with SuppressErrors(ValueError) as ctx:
            raise TypeError("not suppressed")

        assert ctx.get_error() is None


class TestRetryDecorator:
    """测试重试装饰器"""

    def test_retry_success(self):
        """测试重试成功"""
        attempt_count = 0

        @retry(max_attempts=3, delay=0.1)
        def succeed_on_second():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("not yet")
            return "success"

        result = succeed_on_second()
        assert result == "success"
        assert attempt_count == 2

    def test_retry_all_fail(self):
        """测试重试全部失败"""
        attempt_count = 0

        @retry(max_attempts=3, delay=0.1, exceptions=(ValueError,))
        def always_fail():
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            always_fail()

        assert attempt_count == 3


class TestValidateRange:
    """测试范围验证"""

    def test_validate_in_range(self):
        """测试在范围内"""
        result = validate_range(5, 1, 10, 0)
        assert result == 5

    def test_validate_below_range(self):
        """测试低于范围"""
        result = validate_range(0, 1, 10, 5)
        assert result == 5

    def test_validate_above_range(self):
        """测试超出范围"""
        result = validate_range(15, 1, 10, 5)
        assert result == 5


class TestFormatFileSize:
    """测试文件大小格式化"""

    def test_format_bytes(self):
        """测试字节"""
        assert format_file_size(512) == "512.00 B"

    def test_format_kilobytes(self):
        """测试KB"""
        assert "KB" in format_file_size(1024)

    def test_format_megabytes(self):
        """测试MB"""
        assert "MB" in format_file_size(1024 * 1024)


class TestSafeGet:
    """测试安全获取字典值"""

    def test_safe_get_existing(self):
        """测试获取存在的键"""
        d = {"key": "value"}
        result = safe_get(d, "key")
        assert result == "value"

    def test_safe_get_missing(self):
        """测试获取不存在的键"""
        d = {}
        result = safe_get(d, "key", "default")
        assert result == "default"

    def test_safe_get_with_log(self):
        """测试带日志"""
        d = {}
        result = safe_get(d, "key", "default", log_error=True, error_message="Key missing")
        assert result == "default"


class TestThreadManager:
    """测试线程管理器"""

    def test_thread_manager_init(self):
        """测试初始化"""
        tm = ThreadManager()
        assert len(tm.get_running_threads()) == 0

    def test_thread_manager_start_stop(self):
        """测试启动和停止线程"""
        tm = ThreadManager()

        result = tm.start_thread("test", lambda: time.sleep(0.1))
        assert result is True
        assert tm.is_running("test") is True

        result = tm.stop_thread("test")
        assert result is True
        assert tm.is_running("test") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
