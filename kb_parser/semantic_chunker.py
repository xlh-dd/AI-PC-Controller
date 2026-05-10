"""
SemanticChunker - 语义分块器
替代固定字数截断，按段落/语义边界切分知识库内容。
"""
import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("SemanticChunker")


@dataclass
class Chunk:
    """单个文本块"""
    content: str
    chunk_id: str
    metadata: Dict[str, Any]  # {"source": "file", "page": 1, "headings": ["标题1"]}
    token_count: int
    char_count: int


class SemanticChunker:
    """
    语义分块：把长文档切成多个有意义的块。

    策略：
    1. 先按自然段落分割（双换行）
    2. 合并小于 min_chunk_size 的段落
    3. 拆分大于 max_chunk_size 的块（按句子）
    4. 保留标题层级信息
    """

    # 中文 token 估算：1 token ≈ 1.5~2 字符，取保守值 2
    AVG_CHARS_PER_TOKEN = 2.0

    def __init__(
        self,
        min_chunk_size: int = 100,     # 字符，最小块
        max_chunk_size: int = 800,    # 字符，最大块
        overlap_chars: int = 50,       # 块间重叠字符
        merge_short_paragraphs: bool = True,
    ):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_chars = overlap_chars
        self.merge_short = merge_short_paragraphs

    def chunk_text(self, text: str, metadata: Optional[Dict] = None) -> List[Chunk]:
        """对纯文本分块"""
        if not text or not text.strip():
            return []

        metadata = metadata or {}
        chunks = []
        chunk_id_prefix = metadata.get("source", "chunk")

        # 1. 提取标题
        headings = self._extract_headings(text)
        current_heading = headings[0] if headings else ""

        # 2. 按段落分割
        paragraphs = self._split_paragraphs(text)
        current_buffer = ""
        buffer_headings = [current_heading]

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 检测段落内是否有标题
            para_headings = self._extract_headings(para)
            if para_headings:
                current_heading = para_headings[-1]
                buffer_headings.append(current_heading)

            # 合并到 buffer
            candidate = (current_buffer + "\n" + para).strip()

            if len(candidate) < self.max_chunk_size:
                current_buffer = candidate
            else:
                # buffer 够大，吐出去
                if len(current_buffer) >= self.min_chunk_size:
                    chunks.append(self._make_chunk(
                        current_buffer, chunk_id_prefix, metadata, buffer_headings
                    ))
                else:
                    # buffer 太小，强制塞下一个或拆分
                    current_buffer = candidate
                    if len(current_buffer) > self.max_chunk_size:
                        sub_chunks = self._split_large_chunk(current_buffer, chunk_id_prefix, metadata)
                        chunks.extend(sub_chunks)
                        current_buffer = ""

        # 处理剩余 buffer
        if current_buffer.strip():
            if len(current_buffer) >= self.min_chunk_size:
                chunks.append(self._make_chunk(current_buffer, chunk_id_prefix, metadata, buffer_headings))
            elif chunks:
                # 合并到最后一个块
                last = chunks[-1]
                merged = last.content + "\n" + current_buffer
                new_chunk = Chunk(
                    content=merged,
                    chunk_id=last.chunk_id,
                    metadata={**last.metadata, "merged_tail": True},
                    token_count=int(len(merged) / self.AVG_CHARS_PER_TOKEN),
                    char_count=len(merged),
                )
                chunks[-1] = new_chunk

        logger.debug(f"[Chunker] Text → {len(chunks)} chunks")
        return chunks

    def chunk_file(self, file_path: str) -> List[Chunk]:
        """对文件分块，自动识别格式"""
        suffix = file_path.lower().split(".")[-1]
        if suffix in ("pdf",):
            return self.chunk_pdf(file_path)
        elif suffix in ("txt", "md", "csv", "json"):
            return self.chunk_text_file(file_path)
        else:
            return self.chunk_text_file(file_path)

    def chunk_text_file(self, file_path: str) -> List[Chunk]:
        """读取文本文件并分块"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            return self.chunk_text(text, {"source": file_path, "type": "file"})
        except Exception as e:
            logger.error(f"[Chunker] Failed to read {file_path}: {e}")
            return []

    def chunk_pdf(self, file_path: str) -> List[Chunk]:
        """PDF 分页分块"""
        chunks = []
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber 未安装，无法解析 PDF")
            return chunks

        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    if not text.strip():
                        continue
                    page_chunks = self.chunk_text(
                        text,
                        {"source": file_path, "page": page_num, "type": "pdf"}
                    )
                    chunks.extend(page_chunks)
        except Exception as e:
            logger.error(f"[Chunker] Failed to parse PDF {file_path}: {e}")
        return chunks

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _split_paragraphs(self, text: str) -> List[str]:
        """按双换行分割段落"""
        # 先统一换行符
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        paras = re.split(r"\n{2,}", text)
        return [p for p in paras if p.strip()]

    def _extract_headings(self, text: str) -> List[str]:
        """提取标题"""
        # Markdown # 标题
        md_heads = re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)
        if md_heads:
            return md_heads
        # 常见标题格式：1. 或 第一章
        numbered = re.findall(r"^(第[一二三四五六七八九十百千零\d]+[章节篇部]?\s*[：:].+)$", text, re.MULTILINE)
        if numbered:
            return numbered
        return []

    def _split_large_chunk(self, text: str, prefix: str, metadata: Dict) -> List[Chunk]:
        """把超大块按句子拆分"""
        # 按句子分割（中文句号/英文句点/感叹号/问号）
        sentences = re.split(r"(?<=[。！？.!?])\s*", text)
        chunks = []
        buffer = ""
        buffer_headings = [metadata.get("headings", [""])[0]] if metadata.get("headings") else [""]

        for sent in sentences:
            if len(buffer) + len(sent) < self.max_chunk_size:
                buffer = (buffer + "\n" + sent).strip()
            else:
                if buffer:
                    chunks.append(self._make_chunk(buffer, prefix, metadata, buffer_headings))
                buffer = sent

        if buffer:
            chunks.append(self._make_chunk(buffer, prefix, metadata, buffer_headings))

        return chunks

    def _make_chunk(self, content: str, prefix: str, metadata: Dict, headings: List[str]) -> Chunk:
        import hashlib
        chunk_id = hashlib.md5(content.encode()).hexdigest()[:12]
        return Chunk(
            content=content,
            chunk_id=f"{prefix}_{chunk_id}",
            metadata={**metadata, "headings": headings[-2:] if headings else []},
            token_count=int(len(content) / self.AVG_CHARS_PER_TOKEN),
            char_count=len(content),
        )
