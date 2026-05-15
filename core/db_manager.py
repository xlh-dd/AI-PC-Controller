"""
统一的 SQLite 数据库连接管理器
解决多线程并发访问时的 "database is locked" 问题
"""
import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("DBManager")


class DatabaseManager:
    """线程安全的 SQLite 连接池管理器（基于 thread-local 单例）"""

    _local = threading.local()

    def __init__(self, db_dir: Optional[str] = None):
        if db_dir is None:
            db_dir = Path(__file__).parent.parent / "knowledge_base" / "data"
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def get_connection(self, db_name: str) -> sqlite3.Connection:
        """获取指定数据库的线程本地连接（lazy init）

        每个线程、每个 db_name 维护独立的连接。
        连接在首次访问时创建，不会跨线程共享。
        """
        key = db_name  # 一个 db_name 对应一个 thread-local 连接

        # thread-local storage: 每个线程独立的连接字典
        if not hasattr(self._local, '_conns'):
            self._local._conns = {}

        if key not in self._local._conns:
            db_path = self.db_dir / db_name
            conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # 启用 WAL 模式，提升并发读性能
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")  # 30s busy timeout
            self._local._conns[key] = conn
            logger.debug(f"创建 DB 连接: {db_name} (thread={threading.current_thread().name})")

        return self._local._conns[key]

    def execute(self, db_name: str, sql: str, params=()) -> sqlite3.Cursor:
        """在指定数据库上执行 SQL（自动提交）"""
        conn = self.get_connection(db_name)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        return cursor

    def fetchone(self, db_name: str, sql: str, params=()) -> Optional[sqlite3.Row]:
        """查询单行"""
        conn = self.get_connection(db_name)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()

    def fetchall(self, db_name: str, sql: str, params=()) -> list:
        """查询所有行"""
        conn = self.get_connection(db_name)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()

    def close(self, db_name: str):
        """关闭指定数据库的连接"""
        if hasattr(self._local, '_conns') and db_name in self._local._conns:
            try:
                self._local._conns[db_name].close()
                del self._local._conns[db_name]
                logger.debug(f"关闭 DB 连接: {db_name}")
            except Exception as e:
                logger.warning(f"关闭 DB 连接失败: {e}")

    def close_all(self):
        """关闭当前线程的所有连接"""
        if hasattr(self._local, '_conns'):
            for key, conn in list(self._local._conns.items()):
                try:
                    conn.close()
                except Exception:
                    pass
            self._local._conns.clear()


# 全局单例
_db_manager: Optional[DatabaseManager] = None
_db_lock = threading.Lock()


def get_db_manager() -> DatabaseManager:
    """获取全局 DatabaseManager 单例"""
    global _db_manager
    if _db_manager is None:
        with _db_lock:
            if _db_manager is None:
                _db_manager = DatabaseManager()
    return _db_manager


# 便捷方法
def get_conn(db_name: str) -> sqlite3.Connection:
    return get_db_manager().get_connection(db_name)


def execute_sql(db_name: str, sql: str, params=()):
    return get_db_manager().execute(db_name, sql, params)


def fetchone_sql(db_name: str, sql: str, params=()) -> Optional[sqlite3.Row]:
    return get_db_manager().fetchone(db_name, sql, params)


def fetchall_sql(db_name: str, sql: str, params=()) -> list:
    return get_db_manager().fetchall(db_name, sql, params)
