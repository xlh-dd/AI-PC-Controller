"""
ChromaDBClient - ChromaDB 向量存储封装
替代 SQLite FTS，提供语义向量检索能力。
"""
import logging
import hashlib
import os
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

logger = logging.getLogger("ChromaDBClient")

CHROMADB_AVAILABLE = False
chromadb = None

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    logger.warning("ChromaDB 未安装。运行: pip install chromadb")


class ChromaDBClient:
    """
    ChromaDB 封装，提供：
    - add_chunk / add_chunks 批量添加
    - search(query, top_k) 语义检索
    - update_chunk / delete_chunk 增删改
    - 混合检索（语义+关键词）
    """

    DEFAULT_COLLECTION = "knowledge_base"

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_function: Optional[Callable] = None,
    ):
        if not CHROMADB_AVAILABLE:
            raise RuntimeError("ChromaDB 未安装，无法初始化向量库。pip install chromadb")

        if persist_dir is None:
            persist_dir = str(Path(__file__).parent.parent / "knowledge_base" / "vector_store")
        os.makedirs(persist_dir, exist_ok=True)

        self.persist_dir = persist_dir
        self.collection_name = collection_name

        # 初始化 ChromaDB
        self.client = chromadb.PersistentClient(path=persist_dir)

        # 嵌入函数（默认用 sentence-transformers）
        if embedding_function is None:
            self.embedding_fn = self._default_embedding
        else:
            self.embedding_fn = embedding_function

        # 获取或创建 collection
        try:
            self.collection = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
            )
            logger.info(f"[ChromaDB] Loaded existing collection: {collection_name} "
                        f"({self.collection.count()} items)")
        except Exception:
            self.collection = self.client.create_collection(
                name=collection_name,
                embedding_function=self.embedding_fn,
                metadata={"description": "AI电脑管家知识库"},
            )
            logger.info(f"[ChromaDB] Created new collection: {collection_name}")

    def _default_embedding(self, texts: List[str]) -> List[List[float]]:
        """默认嵌入函数：尝试 sentence-transformers"""
        try:
            from sentence_transformers import SentenceTransformer
            model_name = "all-MiniLM-L6-v2"
            cache_folder = str(Path(__file__).parent.parent / ".models")
            model = SentenceTransformer(model_name, cache_folder=cache_folder)
            embeddings = model.encode(texts, show_progress_bar=False)
            return embeddings.tolist()
        except ImportError:
            logger.warning("sentence-transformers 未安装，使用占位嵌入（请安装：pip install sentence-transformers）")
            # 返回占位向量（维度必须一致，MiniLM-L6-v2 是 384 维）
            import numpy as np
            dim = 384
            return [[float(i % dim) / dim for i in range(dim)] for _ in texts]

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add_chunk(
        self,
        content: str,
        chunk_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        source: str = "",
    ) -> str:
        """添加单个 chunk"""
        if chunk_id is None:
            chunk_id = hashlib.md5(content.encode()).hexdigest()[:16]
        metadata = metadata or {}
        if source:
            metadata["source"] = source

        self.collection.add(
            documents=[content],
            ids=[chunk_id],
            metadatas=[metadata],
        )
        return chunk_id

    def add_chunks(self, chunks: List[Any]) -> int:
        """
        批量添加 chunk。
        chunks: List[Chunk] from semantic_chunker
        """
        if not chunks:
            return 0
        documents = [c.content for c in chunks]
        ids = [c.chunk_id for c in chunks]
        metadatas = [c.metadata for c in chunks]

        self.collection.add(
            documents=documents,
            ids=ids,
            metadatas=metadatas,
        )
        logger.info(f"[ChromaDB] Added {len(chunks)} chunks")
        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict] = None,
        include_scores: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        语义检索。

        Returns:
            List[{
                "content": str,
                "chunk_id": str,
                "metadata": dict,
                "score": float  # cosine similarity（越大越相关）
            }]
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=filter_metadata,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                item = {
                    "content": results["documents"][0][i],
                    "chunk_id": chunk_id,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                }
                if include_scores and results["distances"]:
                    # ChromaDB distance → 转成相似度（越小越近）
                    dist = results["distances"][0][i]
                    item["score"] = 1.0 / (1.0 + dist)
                items.append(item)
        return items

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        alpha: float = 0.7,  # 0=纯关键词，1=纯语义
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        混合检索：语义 × alpha + 关键词 × (1-alpha)
        关键词用 BM25 打分，语义用向量相似度。
        """
        # 1. 向量检索
        vector_results = self.search(query, top_k=top_k * 2, filter_metadata=filter_metadata)
        if not vector_results:
            return []

        # 2. BM25 关键词打分（简单版）
        bm25_scores = self._bm25_score(query, [r["content"] for r in vector_results])
        max_bm25 = max(bm25_scores) if bm25_scores else 1.0
        max_vec = max(r.get("score", 1.0) for r in vector_results) or 1.0

        # 3. 融合排序
        fused = []
        for i, r in enumerate(vector_results):
            vec_score = r.get("score", 0) / max_vec
            bm_score = bm25_scores[i] / max_bm25 if max_bm25 > 0 else 0
            combined = alpha * vec_score + (1 - alpha) * bm_score
            r["combined_score"] = combined
            fused.append(r)

        fused.sort(key=lambda x: x["combined_score"], reverse=True)
        return fused[:top_k]

    def update_chunk(self, chunk_id: str, content: str, metadata: Optional[Dict] = None):
        """更新 chunk 内容"""
        self.collection.update(
            documents=[content],
            ids=[chunk_id],
            metadatas=[metadata] if metadata else None,
        )

    def delete_chunk(self, chunk_id: str):
        """删除 chunk"""
        self.collection.delete(ids=[chunk_id])

    def delete_by_source(self, source: str):
        """按来源删除所有 chunks"""
        self.collection.delete(where={"source": source})

    def count(self) -> int:
        return self.collection.count()

    def clear(self):
        """清空 collection"""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
        )
        logger.info("[ChromaDB] Collection cleared")

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _bm25_score(self, query: str, documents: List[str]) -> List[float]:
        """简化 BM25（无第三方库依赖）"""
        import math
        k1, b = 1.5, 0.75
        terms = query.lower().split()
        if not terms:
            return [0.0] * len(documents)
        avg_dl = sum(len(d.split()) for d in documents) / max(len(documents), 1)
        scores = []
        for doc in documents:
            dl = len(doc.split())
            score = 0.0
            for term in terms:
                tf = doc.lower().count(term)
                if tf > 0:
                    idf = math.log((len(documents) + 0.5) / (0.5 + 1))
                    score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            scores.append(score)
        return scores


# ── 懒加载单例 ───────────────────────────────────────────────────────────────

_client: Optional[ChromaDBClient] = None


def get_chromadb_client(
    persist_dir: Optional[str] = None,
    collection: str = ChromaDBClient.DEFAULT_COLLECTION,
) -> Optional[ChromaDBClient]:
    global _client
    if _client is None and CHROMADB_AVAILABLE:
        try:
            _client = ChromaDBClient(persist_dir=persist_dir, collection_name=collection)
        except Exception as e:
            logger.error(f"[ChromaDB] Init failed: {e}")
            return None
    return _client
