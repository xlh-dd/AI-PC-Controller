"""
VectorMemory - 向量化对话长期记忆
在 conversation_memory.py 基础上增加：
- 语义向量索引（sentence-transformers）
- 自然语言检索 /记得 XX
- 记忆衰减
- 对话摘要定时任务
"""
import logging
import sqlite3
import threading
import time
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger("VectorMemory")

EMBEDDING_AVAILABLE = False
_embed_model = None

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    logger.warning("sentence-transformers 未安装，向量记忆不可用。pip install sentence-transformers")


# ── 向量引擎 ─────────────────────────────────────────────────────────────────

def _get_embed_model():
    global _embed_model
    if _embed_model is None and EMBEDDING_AVAILABLE:
        try:
            cache = str(Path(__file__).parent.parent / ".models")
            _embed_model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=cache)
            logger.info("[VectorMemory] Embedding model loaded")
        except Exception as e:
            logger.error(f"[VectorMemory] Model load failed: {e}")
    return _embed_model


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: int = 0
    content: str = ""
    summary: str = ""
    role: str = "user"     # user / assistant / system
    session_id: str = ""
    timestamp: datetime = None
    embedding: List[float] = None
    decay_weight: float = 1.0   # 衰减权重
    tags: List[str] = None
    source: str = "conversation"  # conversation / manual / extracted

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.tags is None:
            self.tags = []


class VectorMemory:
    """
    向量化长期记忆模块。

    新增能力：
    - semantic_search(query) 自然语言检索
    - decay_old_memories() 记忆衰减
    - summarize_long_conversations() 对话摘要
    """

    EMBEDDING_DIM = 384   # MiniLM-L6-v2 的维度

    def __init__(self, db_path: Optional[str] = None, decay_days: int = 30,
                 decay_factor: float = 0.9):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "memories.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.decay_days = decay_days
        self.decay_factor = decay_factor
        self._lock = threading.RLock()
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                summary TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                session_id TEXT DEFAULT '',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                decay_weight REAL DEFAULT 1.0,
                tags TEXT DEFAULT '[]',
                source TEXT DEFAULT 'conversation'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                id INTEGER PRIMARY KEY,
                embedding BLOB NOT NULL,
                FOREIGN KEY (id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        # 全文索引（备用检索）
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id)
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)
        """)
        conn.commit()

    # ── 写入 ─────────────────────────────────────────────────────────────

    def add(self, content: str, role: str = "user", session_id: str = "",
            summary: str = "", tags: Optional[List[str]] = None,
            source: str = "conversation") -> int:
        """添加记忆条目，异步生成向量"""
        if not content or not content.strip():
            return 0
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO memories (content, role, session_id, summary, tags, source, decay_weight)
            VALUES (?, ?, ?, ?, ?, ?, 1.0)
        """, (content, role, session_id, summary, json.dumps(tags or [], ensure_ascii=False), source))
        entry_id = c.lastrowid
        conn.commit()

        # 异步生成向量（不在锁内）
        threading.Thread(target=self._embed_async, args=(entry_id, content), daemon=True).start()
        return entry_id

    def _embed_async(self, entry_id: int, content: str):
        """异步生成并存储向量"""
        model = _get_embed_model()
        if model is None:
            return
        try:
            vec = model.encode([content], show_progress_bar=False)[0].tolist()
            blob = json.dumps(vec)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO memory_embeddings (id, embedding) VALUES (?, ?)",
                     (entry_id, blob))
            conn.commit()
            conn.close()
            logger.debug(f"[VectorMemory] Embedded entry {entry_id}")
        except Exception as e:
            logger.warning(f"[VectorMemory] Embed failed: {e}")

    # ── 检索 ─────────────────────────────────────────────────────────────

    def semantic_search(self, query: str, top_k: int = 5,
                        session_id: Optional[str] = None,
                        since_days: int = 0) -> List[Dict[str, Any]]:
        """
        自然语言检索记忆。

        Returns:
            List[{content, summary, role, timestamp, score, tags}]
        """
        model = _get_embed_model()
        if model is None:
            # 降级到关键词搜索
            return self._keyword_search(query, top_k, session_id)

        try:
            query_vec = model.encode([query], show_progress_bar=False)[0].tolist()
        except Exception as e:
            logger.warning(f"[VectorMemory] Query embed failed: {e}")
            return self._keyword_search(query, top_k, session_id)

        conn = self._get_conn()
        c = conn.cursor()

        # 取所有记忆的向量，计算余弦相似度
        c.execute("""
            SELECT m.id, m.content, m.summary, m.role, m.timestamp, m.decay_weight,
                   m.tags, e.embedding
            FROM memories m
            LEFT JOIN memory_embeddings e ON m.id = e.id
        """)

        results = []
        cutoff = datetime.now() - timedelta(days=since_days) if since_days > 0 else None

        for row in c.fetchall():
            if cutoff and row["timestamp"] < cutoff:
                continue
            if session_id and row["session_id"] != session_id:
                continue
            embedding_str = row["embedding"]
            if not embedding_str:
                continue
            try:
                stored_vec = json.loads(embedding_str)
                score = self._cosine_sim(query_vec, stored_vec) * row["decay_weight"]
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "role": row["role"],
                    "timestamp": row["timestamp"],
                    "score": round(score, 4),
                    "tags": json.loads(row["tags"] or "[]"),
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _keyword_search(self, query: str, top_k: int, session_id: Optional[str]) -> List[Dict]:
        """关键词降级搜索"""
        conn = self._get_conn()
        c = conn.cursor()
        terms = query.lower().split()
        placeholders = " AND ".join(["content LIKE ?"] * len(terms))
        params = [f"%{t}%" for t in terms]
        if session_id:
            sql = f"SELECT * FROM memories WHERE {placeholders} AND session_id=? ORDER BY timestamp DESC LIMIT ?"
            params.extend([session_id, top_k])
        else:
            sql = f"SELECT * FROM memories WHERE {placeholders} ORDER BY timestamp DESC LIMIT ?"
            params.append(top_k)
        c.execute(sql, params)
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "summary": row["summary"],
                "role": row["role"],
                "timestamp": row["timestamp"],
                "score": 0.5,
                "tags": json.loads(row["tags"] or "[]"),
            }
            for row in c.fetchall()
        ]

    # ── 记忆衰减 ─────────────────────────────────────────────────────────

    def decay_old_memories(self, dry_run: bool = False) -> Dict[str, int]:
        """
        对旧记忆执行衰减：超过 decay_days 的条目，权重乘以 decay_factor。
        低于阈值（0.1）的记忆将被删除。
        """
        conn = self._get_conn()
        c = conn.cursor()
        cutoff = datetime.now() - timedelta(days=self.decay_days)
        deleted = 0
        decayed = 0

        c.execute("""
            SELECT id, decay_weight FROM memories
            WHERE timestamp < ? AND decay_weight > 0.1
        """, (cutoff,))

        for row in c.fetchall():
            new_weight = row["decay_weight"] * self.decay_factor
            if new_weight < 0.1:
                if not dry_run:
                    c.execute("DELETE FROM memories WHERE id=?", (row["id"],))
                    c.execute("DELETE FROM memory_embeddings WHERE id=?", (row["id"],))
                deleted += 1
            else:
                if not dry_run:
                    c.execute("UPDATE memories SET decay_weight=? WHERE id=?",
                             (new_weight, row["id"]))
                decayed += 1

        if not dry_run:
            conn.commit()

        return {"decayed": decayed, "deleted": deleted}

    # ── 对话摘要 ─────────────────────────────────────────────────────────

    def summarize_long_conversations(self, ai_helper=None, session_id: Optional[str] = None,
                                     min_turns: int = 8) -> int:
        """
        对长对话生成摘要，节省 token。
        返回摘要数量。
        """
        conn = self._get_conn()
        c = conn.cursor()

        # 找出长会话
        if session_id:
            where = "session_id = ?"
            params = [session_id]
        else:
            where = "1=1"
            params = []

        c.execute(f"""
            SELECT session_id, COUNT(*) as cnt
            FROM memories
            WHERE {where}
            GROUP BY session_id
            HAVING cnt >= ?
            ORDER BY MAX(timestamp) DESC
        """, params + [min_turns])

        summarized = 0
        for row in c.fetchall():
            sid = row["session_id"]
            c2 = conn.cursor()
            c2.execute("""
                SELECT content, role FROM memories
                WHERE session_id=? AND summary=''
                ORDER BY timestamp ASC
            """, (sid,))
            messages = c2.fetchall()
            if len(messages) < min_turns:
                continue

            # 拼接对话历史
            dialogue = "\n".join(
                f"[{m['role']}]: {m['content'][:200]}" for m in messages
            )
            prompt = f"请用一段话总结以下对话的核心内容和结论（不超过100字）：\n{dialogue[:2000]}"

            summary_text = ""
            if ai_helper:
                try:
                    summary_text = ai_helper.ai_query(prompt, use_memory=False) or ""
                    summary_text = summary_text.strip()
                except Exception as e:
                    logger.warning(f"[VectorMemory] Summarize failed: {e}")

            # 把所有消息的 summary 更新
            ids = [m[0] for m in messages]
            for mid in ids:
                c2.execute("UPDATE memories SET summary=? WHERE id=? AND summary=''",
                          (summary_text, mid))
            summarized += 1
            time.sleep(0.5)  # 避免过快

        conn.commit()
        logger.info(f"[VectorMemory] Summarized {summarized} conversations")
        return summarized

    # ── 统计 ─────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total, COUNT(e.id) as embedded FROM memories m LEFT JOIN memory_embeddings e ON m.id=e.id")
        row = c.fetchone()
        c.execute("SELECT COUNT(DISTINCT session_id) as sessions FROM memories")
        row2 = c.fetchone()
        return {
            "total": row["total"],
            "embedded": row["embedded"],
            "sessions": row2["sessions"],
            "embedding_available": EMBEDDING_AVAILABLE,
        }

    def search_by_tags(self, tags: List[str], top_k: int = 10) -> List[Dict]:
        conn = self._get_conn()
        c = conn.cursor()
        placeholders = " OR ".join(["tags LIKE ?"] * len(tags))
        params = [f'%"{t}"%' for t in tags]
        c.execute(f"""
            SELECT * FROM memories
            WHERE {placeholders}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params + [top_k])
        return [dict(row) for row in c.fetchall()]
