"""
ConversationManager — 多对话管理

支持创建多个独立对话，每个对话有自己的上下文和记忆。
持久化存储到 ~/.aipc_conversations.json
"""

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("ConversationManager")

STORAGE_FILE = os.path.expanduser("~/.aipc_conversations.json")
MAX_MESSAGES_PER_CONV = 50  # 每个对话最多保留的消息数


@dataclass
class Conversation:
    """单个对话"""
    id: str
    title: str = "新对话"
    messages: List[dict] = field(default_factory=list)
    model: str = "deepseek-chat"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "time": datetime.now().isoformat()
        })
        # 自动截断旧消息
        if len(self.messages) > MAX_MESSAGES_PER_CONV * 2:
            self.messages = self.messages[-MAX_MESSAGES_PER_CONV * 2:]

        # 自动更新标题（取第一条用户消息的前20字符）
        if self.title == "新对话" and role == "user":
            self.title = content[:20] + ("..." if len(content) > 20 else "")

        self.updated_at = datetime.now().isoformat()

    def get_context(self, max_messages: int = 10) -> list:
        """获取最近的上下文消息"""
        return self.messages[-max_messages * 2:]  # user+assistant pairs

    def clear(self):
        self.messages = []
        self.title = "新对话"
        self.updated_at = datetime.now().isoformat()


class ConversationManager:
    """多对话管理器"""

    def __init__(self, storage_path: str = None):
        self._storage = Path(storage_path or STORAGE_FILE)
        self._conversations: Dict[str, Conversation] = {}
        self._order: List[str] = []  # 对话顺序
        self._active_id: Optional[str] = None
        self._lock = threading.Lock()

        # 加载已有对话
        self._load()

        # 如果没有对话，创建默认对话
        if not self._order:
            conv = Conversation(id=str(uuid.uuid4())[:8], title="新对话")
            self._conversations[conv.id] = conv
            self._order.append(conv.id)
            self._active_id = conv.id

    # ── 基础操作 ──────────────────────────────────────────────────────────

    def list_conversations(self) -> List[Conversation]:
        """按时间倒序列出所有对话"""
        with self._lock:
            result = []
            for cid in reversed(self._order):
                conv = self._conversations.get(cid)
                if conv and conv.messages:
                    result.append(conv)
            # 新对话（无消息的）排在第一个
            for cid in self._order:
                conv = self._conversations.get(cid)
                if conv and not conv.messages and conv not in result:
                    result.insert(0, conv)
            return result

    def create(self, title: str = "新对话") -> Conversation:
        """创建新对话"""
        conv = Conversation(id=str(uuid.uuid4())[:8], title=title)
        with self._lock:
            self._conversations[conv.id] = conv
            self._order.append(conv.id)
        self._save_async()
        return conv

    def switch_to(self, conv_id: str) -> Optional[Conversation]:
        """切换到指定对话"""
        with self._lock:
            conv = self._conversations.get(conv_id)
            if conv:
                self._active_id = conv_id
            return conv

    def delete(self, conv_id: str) -> bool:
        """删除对话"""
        with self._lock:
            if conv_id not in self._conversations:
                return False
            del self._conversations[conv_id]
            self._order.remove(conv_id)
            if self._active_id == conv_id:
                # 切换到下一个
                self._active_id = self._order[-1] if self._order else None
        self._save_async()
        return True

    def rename(self, conv_id: str, new_title: str):
        """重命名对话"""
        with self._lock:
            conv = self._conversations.get(conv_id)
            if conv:
                conv.title = new_title
                conv.updated_at = datetime.now().isoformat()
        self._save_async()

    def clear_conversation(self, conv_id: str):
        """清空对话消息"""
        with self._lock:
            conv = self._conversations.get(conv_id)
            if conv:
                conv.clear()
        self._save_async()

    @property
    def active(self) -> Optional[Conversation]:
        with self._lock:
            if self._active_id:
                return self._conversations.get(self._active_id)
            return None

    @property
    def active_id(self) -> Optional[str]:
        return self._active_id

    def get(self, conv_id: str) -> Optional[Conversation]:
        with self._lock:
            return self._conversations.get(conv_id)

    # ── 持久化 ────────────────────────────────────────────────────────────

    def _to_dict(self) -> dict:
        """序列化"""
        return {
            "conversations": {
                cid: {
                    "id": c.id,
                    "title": c.title,
                    "messages": c.messages,
                    "model": c.model,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                }
                for cid, c in self._conversations.items()
            },
            "order": self._order,
            "active_id": self._active_id,
        }

    def _save_async(self):
        """异步保存（避免阻塞 GUI）"""
        t = threading.Thread(target=self.save, daemon=True)
        t.start()

    def save(self):
        """保存到磁盘"""
        try:
            data = self._to_dict()
            self._storage.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(self._storage) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(self._storage))
        except Exception as e:
            logger.error(f"保存对话失败: {e}")

    def _load(self):
        """从磁盘加载"""
        try:
            if not self._storage.exists():
                return
            with open(self._storage, "r", encoding="utf-8") as f:
                data = json.load(f)

            convs = data.get("conversations", {})
            for cid, cdata in convs.items():
                conv = Conversation(
                    id=cdata["id"],
                    title=cdata.get("title", "新对话"),
                    messages=cdata.get("messages", []),
                    model=cdata.get("model", "deepseek-chat"),
                    created_at=cdata.get("created_at", ""),
                    updated_at=cdata.get("updated_at", ""),
                )
                self._conversations[cid] = conv

            self._order = data.get("order", list(convs.keys()))
            self._active_id = data.get("active_id")
        except Exception as e:
            logger.error(f"加载对话失败: {e}")

    # ── 工具方法 ──────────────────────────────────────────────────────────

    def get_summary(self, conv_id: str) -> str:
        """生成对话摘要"""
        conv = self._conversations.get(conv_id)
        if not conv or not conv.messages:
            return "空对话"

        user_msgs = [m["content"][:30] for m in conv.messages if m["role"] == "user"]
        if user_msgs:
            last = user_msgs[-1]
            return f"{last}{'...' if len(last) >= 30 else ''}"
        return conv.title


# ── 全局单例 ──
_cm: Optional[ConversationManager] = None
_cm_lock = threading.Lock()


def get_conversation_manager() -> ConversationManager:
    global _cm
    if _cm is None:
        with _cm_lock:
            if _cm is None:
                _cm = ConversationManager()
    return _cm