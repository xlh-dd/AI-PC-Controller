import logging
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
import re

logger = logging.getLogger("ConversationMemory")

class ConversationMemory:
    """AI助手对话永久记忆模块

    功能：
    1. 持久化存储对话历史到SQLite数据库
    2. 支持按会话、时间范围、角色检索对话
    3. 自动清理旧对话记录
    4. 支持对话摘要生成（可选）
    5. 与现有AI助手和AI智能体集成
    """

    def __init__(self, config_manager=None, db_path=None):
        """初始化对话记忆模块

        Args:
            config_manager: 配置管理器实例
            db_path: SQLite数据库路径，默认使用data/conversations.db
        """
        self.config_manager = config_manager
        self.db_path = db_path

        if not self.db_path:
            # 默认数据库路径
            base_dir = Path(__file__).parent.parent
            data_dir = base_dir / "data"
            data_dir.mkdir(exist_ok=True)
            self.db_path = str(data_dir / "conversations.db")

        # 初始化数据库连接池（线程安全）
        self._local = threading.local()
        self._init_db()

        # 缓存最近对话（提高性能）
        self.recent_conversations_cache = {}
        self.cache_size = 100
        self.cache_lock = threading.Lock()

        # 当前会话ID（可选，用于分组对话）
        self.current_session_id = self._generate_session_id()

        logger.info(f"对话记忆模块初始化完成，数据库路径：{self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（线程安全）"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    def _close_connection(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')

    def _init_db(self):
        """初始化数据库表"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 会话表（可选，用于分组对话）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME,
                summary TEXT,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')

            # 对话消息表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                embedding_vector BLOB,
                is_archived BOOLEAN DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
            ''')

            # 创建索引以提高查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations (session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations (timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_role ON conversations (role)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_archived ON conversations (is_archived)')

            # 函数调用表（记录AI调用的函数）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS function_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                function_name TEXT NOT NULL,
                arguments TEXT,
                result TEXT,
                called_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN DEFAULT 1,
                error_message TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id)
            )
            ''')

            # 对话摘要表（用于长对话压缩）
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                original_message_ids TEXT,
                summary_text TEXT NOT NULL,
                summary_type TEXT DEFAULT 'periodic',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
            ''')

            conn.commit()
            logger.debug("数据库表初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

    def _generate_session_id(self) -> str:
        """生成唯一会话ID"""
        return str(uuid.uuid4())

    def start_new_session(self, metadata: Dict[str, Any] = None) -> str:
        """开始新会话

        Args:
            metadata: 会话元数据，如应用版本、用户信息等

        Returns:
            新会话ID
        """
        try:
            session_id = self._generate_session_id()
            conn = self._get_connection()
            cursor = conn.cursor()

            metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

            cursor.execute(
                "INSERT INTO sessions (id, metadata) VALUES (?, ?)",
                (session_id, metadata_json)
            )
            conn.commit()

            self.current_session_id = session_id
            logger.info(f"新会话开始：{session_id}")
            return session_id
        except Exception as e:
            logger.error(f"开始新会话失败: {e}")
            raise

    def end_session(self, session_id: str = None, summary: str = None):
        """结束会话

        Args:
            session_id: 会话ID，None表示当前会话
            summary: 会话摘要
        """
        try:
            if not session_id:
                session_id = self.current_session_id

            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE sessions SET end_time = CURRENT_TIMESTAMP, summary = ? WHERE id = ?",
                (summary, session_id)
            )
            conn.commit()

            logger.info(f"会话结束：{session_id}")
        except Exception as e:
            logger.error(f"结束会话失败: {e}")

    def add_message(self, role: str, content: str, session_id: str = None,
                    metadata: Dict[str, Any] = None) -> int:
        """添加对话消息

        Args:
            role: 角色（user, assistant, system, function）
            content: 消息内容
            session_id: 会话ID，None表示当前会话
            metadata: 元数据，如函数调用信息、情感分析等

        Returns:
            消息ID
        """
        if not session_id:
            session_id = self.current_session_id

        # 如果没有会话记录，自动创建
        if session_id:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO sessions (id) VALUES (?)", (session_id,))
                conn.commit()

        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO conversations
               (session_id, role, content, metadata)
               VALUES (?, ?, ?, ?)""",
            (session_id, role, content, metadata_json)
        )
        message_id = cursor.lastrowid
        conn.commit()

        # 更新缓存
        with self.cache_lock:
            if session_id not in self.recent_conversations_cache:
                self.recent_conversations_cache[session_id] = []

            self.recent_conversations_cache[session_id].append({
                'id': message_id,
                'role': role,
                'content': content,
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata
            })

            # 限制缓存大小
            if len(self.recent_conversations_cache[session_id]) > self.cache_size:
                self.recent_conversations_cache[session_id].pop(0)

        logger.debug(f"添加消息：{role} - {content[:50]}...")
        return message_id

    def add_function_call(self, conversation_id: int, function_name: str,
                          arguments: Dict[str, Any], result: Any = None,
                          success: bool = True, error_message: str = None):
        """记录函数调用

        Args:
            conversation_id: 关联的对话消息ID
            function_name: 函数名
            arguments: 参数（字典）
            result: 返回值
            success: 是否成功
            error_message: 错误信息（如果失败）
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        args_json = json.dumps(arguments, ensure_ascii=False) if arguments else None
        result_json = json.dumps(result, ensure_ascii=False) if result else None

        cursor.execute(
            """INSERT INTO function_calls
               (conversation_id, function_name, arguments, result, success, error_message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (conversation_id, function_name, args_json, result_json, success, error_message)
        )
        conn.commit()

        logger.debug(f"记录函数调用：{function_name}")

    def get_conversation_history(self, session_id: str = None, limit: int = 100,
                                 offset: int = 0, include_archived: bool = False,
                                 role_filter: str = None) -> List[Dict[str, Any]]:
        """获取对话历史

        Args:
            session_id: 会话ID，None表示当前会话
            limit: 返回数量限制
            offset: 偏移量
            include_archived: 是否包含已归档的消息
            role_filter: 角色过滤（user, assistant, system, function）

        Returns:
            对话历史列表
        """
        if not session_id:
            session_id = self.current_session_id

        # 检查缓存
        with self.cache_lock:
            if (session_id in self.recent_conversations_cache and
                len(self.recent_conversations_cache[session_id]) >= limit and
                offset == 0 and not role_filter):
                # 从缓存返回
                return self.recent_conversations_cache[session_id][-limit:]

        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM conversations WHERE session_id = ?"
        params = [session_id]

        if not include_archived:
            query += " AND is_archived = 0"

        if role_filter:
            query += " AND role = ?"
            params.append(role_filter)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # 转换为字典列表
        conversations = []
        for row in rows:
            conv = dict(row)
            if conv.get('metadata'):
                try:
                    conv['metadata'] = json.loads(conv['metadata'])
                except:
                    conv['metadata'] = {}
            conversations.append(conv)

        return conversations

    def get_recent_conversations(self, limit: int = 20, include_sessions: bool = False) -> List[Dict[str, Any]]:
        """获取最近对话（跨会话）

        Args:
            limit: 数量限制
            include_sessions: 是否包含会话信息

        Returns:
            最近对话列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
        SELECT c.*, s.start_time as session_start, s.summary as session_summary
        FROM conversations c
        LEFT JOIN sessions s ON c.session_id = s.id
        WHERE c.is_archived = 0
        ORDER BY c.timestamp DESC
        LIMIT ?
        """

        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

        conversations = []
        for row in rows:
            conv = dict(row)
            if conv.get('metadata'):
                try:
                    conv['metadata'] = json.loads(conv['metadata'])
                except:
                    conv['metadata'] = {}
            conversations.append(conv)

        return conversations

    def search_conversations(self, keyword: str, session_id: str = None,
                             limit: int = 50) -> List[Dict[str, Any]]:
        """搜索对话内容

        Args:
            keyword: 搜索关键词
            session_id: 限制会话ID
            limit: 结果限制

        Returns:
            匹配的对话列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if session_id:
            query = """
            SELECT * FROM conversations
            WHERE (content LIKE ? OR metadata LIKE ?)
              AND session_id = ?
              AND is_archived = 0
            ORDER BY timestamp DESC
            LIMIT ?
            """
            params = [f'%{keyword}%', f'%{keyword}%', session_id, limit]
        else:
            query = """
            SELECT * FROM conversations
            WHERE (content LIKE ? OR metadata LIKE ?)
              AND is_archived = 0
            ORDER BY timestamp DESC
            LIMIT ?
            """
            params = [f'%{keyword}%', f'%{keyword}%', limit]

        cursor.execute(query, params)
        rows = cursor.fetchall()

        conversations = []
        for row in rows:
            conv = dict(row)
            if conv.get('metadata'):
                try:
                    conv['metadata'] = json.loads(conv['metadata'])
                except:
                    conv['metadata'] = {}
            conversations.append(conv)

        return conversations

    def archive_conversation(self, message_id: int):
        """归档对话消息（软删除）

        Args:
            message_id: 消息ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE conversations SET is_archived = 1 WHERE id = ?",
            (message_id,)
        )
        conn.commit()

        logger.debug(f"归档消息：{message_id}")

    def delete_conversation(self, message_id: int):
        """永久删除对话消息

        Args:
            message_id: 消息ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM conversations WHERE id = ?", (message_id,))
        cursor.execute("DELETE FROM function_calls WHERE conversation_id = ?", (message_id,))
        conn.commit()

        logger.debug(f"删除消息：{message_id}")

    def cleanup_old_conversations(self, days_to_keep: int = 30):
        """清理旧对话记录

        Args:
            days_to_keep: 保留天数，默认30天
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')

        # 归档旧消息（而不是删除）
        cursor.execute(
            "UPDATE conversations SET is_archived = 1 WHERE timestamp < ? AND is_archived = 0",
            (cutoff_str,)
        )

        deleted_count = cursor.rowcount
        conn.commit()

        logger.info(f"清理了{deleted_count}条{days_to_keep}天前的对话记录")
        return deleted_count

    def get_statistics(self) -> Dict[str, Any]:
        """获取对话统计信息

        Returns:
            统计信息字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        stats = {}

        # 总消息数
        cursor.execute("SELECT COUNT(*) as total FROM conversations WHERE is_archived = 0")
        stats['total_messages'] = cursor.fetchone()[0]

        # 按角色统计
        cursor.execute("""
        SELECT role, COUNT(*) as count
        FROM conversations
        WHERE is_archived = 0
        GROUP BY role
        """)
        stats['by_role'] = dict(cursor.fetchall())

        # 会话统计
        cursor.execute("SELECT COUNT(*) as total FROM sessions")
        stats['total_sessions'] = cursor.fetchone()[0]

        # 最近活跃会话
        cursor.execute("""
        SELECT COUNT(DISTINCT session_id) as active_sessions
        FROM conversations
        WHERE timestamp > datetime('now', '-1 day')
        """)
        stats['active_sessions_24h'] = cursor.fetchone()[0]

        # 最早和最晚消息时间
        cursor.execute("""
        SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest
        FROM conversations
        WHERE is_archived = 0
        """)
        row = cursor.fetchone()
        stats['earliest_message'] = row[0]
        stats['latest_message'] = row[1]

        return stats

    def export_conversations(self, session_id: str = None, format: str = 'json') -> str:
        """导出对话记录

        Args:
            session_id: 会话ID，None表示所有会话
            format: 导出格式（json, txt, csv）

        Returns:
            导出内容字符串
        """
        if session_id:
            conversations = self.get_conversation_history(session_id, limit=10000, include_archived=True)
        else:
            conversations = self.get_recent_conversations(limit=10000)

        if format == 'json':
            return json.dumps(conversations, ensure_ascii=False, indent=2)
        elif format == 'txt':
            lines = []
            for conv in conversations:
                timestamp = conv.get('timestamp', '')
                role = conv.get('role', 'unknown')
                content = conv.get('content', '')
                lines.append(f"[{timestamp}] {role}: {content}")
            return '\n'.join(lines)
        elif format == 'csv':
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['timestamp', 'role', 'content', 'session_id'])
            for conv in conversations:
                writer.writerow([
                    conv.get('timestamp', ''),
                    conv.get('role', ''),
                    conv.get('content', ''),
                    conv.get('session_id', '')
                ])
            return output.getvalue()
        else:
            raise ValueError(f"不支持的导出格式: {format}")

    def integrate_with_ai_helper(self, ai_helper):
        """与现有AI助手集成

        此方法将对话记忆功能添加到AI助手实例中，
        使AI能够记住和引用之前的对话。

        Args:
            ai_helper: AIHelper实例
        """
        # 检查是否已经存储了原始方法引用
        if not hasattr(ai_helper, '_original_ai_query'):
            # 首次集成，存储原始方法引用
            ai_helper._original_ai_query = ai_helper.ai_query
        else:
            # 已经集成过，使用存储的原始方法引用
            # 确保当前方法可能是已经被增强的版本，我们不希望链式包装
            pass

        # 使用存储的原始方法引用
        original_ai_query = ai_helper._original_ai_query

        def enhanced_ai_query(prompt, system_prompt=None, stream_callback=None,
                              use_memory=True, max_history_tokens=2000, **kwargs):
            """增强的AI查询，包含对话记忆"""
            if not use_memory:
                return original_ai_query(prompt, system_prompt, stream_callback, **kwargs)

            # 获取相关历史对话
            relevant_history = self.get_recent_conversations(limit=10)

            # 构建包含历史的prompt
            if relevant_history:
                history_text = "\n".join([
                    f"{msg['role']}: {msg['content']}"
                    for msg in relevant_history[-5:]  # 最近5条
                ])
                enhanced_prompt = f"""先前对话：
{history_text}

当前问题：
{prompt}

请基于上述对话历史回答当前问题。"""
            else:
                enhanced_prompt = prompt

            # 调用原始AI查询
            response = original_ai_query(enhanced_prompt, system_prompt, stream_callback, **kwargs)

            # 保存当前对话到记忆
            if response:
                self.add_message("user", prompt)
                self.add_message("assistant", response)

            return response

        # 存储增强方法引用（可选，用于未来可能的移除操作）
        ai_helper._enhanced_ai_query_with_memory = enhanced_ai_query

        # 替换AI助手的ai_query方法
        ai_helper.ai_query = enhanced_ai_query

        # 添加记忆相关方法到AI助手
        ai_helper.get_conversation_history = lambda limit=20: self.get_recent_conversations(limit)
        ai_helper.search_conversations = lambda keyword: self.search_conversations(keyword)
        ai_helper.clear_conversation_history = lambda: self.cleanup_old_conversations(days_to_keep=0)

        logger.info("对话记忆已集成到AI助手")

    def close(self):
        """关闭数据库连接"""
        self._close_connection()
        logger.info("对话记忆模块已关闭")


# 单例实例（可选）
_default_instance = None

def get_conversation_memory(config_manager=None, db_path=None) -> ConversationMemory:
    """获取对话记忆单例实例"""
    global _default_instance
    if _default_instance is None:
        _default_instance = ConversationMemory(config_manager, db_path)
    return _default_instance