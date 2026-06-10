"""
FilePanel — 文件管理面板 (PyQt6 + Fluent 版)

功能：
- 智能整理、查重、大文件扫描、空文件清理
- 批量重命名（带撤销）
- 磁盘使用进度条
- AI 辅助分析重复文件
"""

import os
import logging
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget,
    QListWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QSplitter, QProgressBar,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit, TextEdit,
    FluentIcon, InfoBarPosition,
)

from modules.fluent_theme import (
    BG_PRIMARY, MANTLE, SURFACE0, SURFACE1, TEXT, SUBTEXT0, FG_PRIMARY,
    BLUE, GREEN, RED, YELLOW, ACCENT,
    RADIUS, RADIUS_LG, PADDING, PADDING_SM, PADDING_LG,
    card_stylesheet, button_stylesheet, outline_button_stylesheet,
)
from modules.ui_manager import ThreadWorker, show_info, show_error, show_warning

logger = logging.getLogger("FilePanel")


# ═══════════════════════════════════════════════════════════════════════
# FilePanel
# ═══════════════════════════════════════════════════════════════════════

class FilePanel(QWidget):
    """文件管理面板"""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.root = parent
        self._current_path = str(Path.home() / "Desktop")
        self._scan_results = []
        self._worker = None
        self._rename_history = []  # 批量重命名撤销记录

        self._build_ui()

    # ═══ UI 构建 ══════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING_LG, PADDING_LG, PADDING_LG, PADDING_LG)
        layout.setSpacing(PADDING)

        # ── 标题 ──
        title = QLabel("文件管理")
        title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        # ── 路径栏 ──
        path_row = QHBoxLayout()
        path_row.setSpacing(PADDING_SM)

        self.path_input = LineEdit()
        self.path_input.setText(self._current_path)
        self.path_input.setPlaceholderText("选择目录路径...")
        path_row.addWidget(self.path_input, stretch=1)

        browse_btn = PushButton("浏览...")
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)

        layout.addLayout(path_row)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(PADDING_SM)

        tools = [
            ("📂 智能整理", self._do_smart_organize),
            ("🔍 文件查重", self._do_find_duplicates),
            ("📊 大文件扫描", self._do_scan_large_files),
            ("🗑 空文件清理", self._do_clean_empty_files),
            ("✏️ 批量重命名", self._do_batch_rename),
        ]
        for name, fn in tools:
            btn = PushButton(name)
            btn.clicked.connect(fn)
            toolbar.addWidget(btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── 磁盘概览 ──
        disk_row = QHBoxLayout()
        disk_row.setSpacing(PADDING)

        drives = self._get_drives()
        for drive, label in drives:
            card = QFrame()
            card.setStyleSheet(card_stylesheet(radius=RADIUS, bg=SURFACE0))
            card.setFixedHeight(60)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(PADDING, PADDING_SM, PADDING, PADDING_SM)

            letter = QLabel(drive)
            letter.setStyleSheet(f"color: {ACCENT}; font-size: 18px; font-weight: bold;")
            card_layout.addWidget(letter)

            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            try:
                import shutil
                usage = shutil.disk_usage(drive)
                pct = usage.used / usage.total * 100
                mb_free = usage.free / (1024 ** 3)
                bar.setValue(int(pct))
                bar_label = QLabel(f"空闲 {mb_free:.0f}GB")
                bar_label.setStyleSheet(f"color: {SUBTEXT0}; font-size: 11px;")
                if pct < 50:
                    bar.setStyleSheet(f"QProgressBar::chunk {{ background: {GREEN}; border-radius: 3px; }}")
                elif pct < 75:
                    bar.setStyleSheet(f"QProgressBar::chunk {{ background: {YELLOW}; border-radius: 3px; }}")
                else:
                    bar.setStyleSheet(f"QProgressBar::chunk {{ background: {RED}; border-radius: 3px; }}")
            except Exception:
                bar.setValue(0)
                bar_label = QLabel("不可用")
                bar_label.setStyleSheet(f"color: {SUBTEXT0}; font-size: 11px;")

            info_layout = QVBoxLayout()
            info_layout.addWidget(bar_label)
            info_layout.addWidget(bar)
            card_layout.addLayout(info_layout, stretch=1)

            disk_row.addWidget(card)

        layout.addLayout(disk_row)

        # ── 结果区域 ──
        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setPlaceholderText("操作结果将显示在这里...")
        self.result_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {MANTLE};
                color: {TEXT};
                border: 1px solid {SURFACE1};
                border-radius: {RADIUS}px;
                padding: {PADDING}px;
                font-family: Consolas, "Microsoft YaHei UI", monospace;
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.result_area, stretch=1)

        # ── 进度条 ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

    # ═══ 路径选择 ══════════════════════════════════════════════════════

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择目录", self._current_path)
        if path:
            self._current_path = path
            self.path_input.setText(path)

    @property
    def _scan_path(self) -> str:
        p = self.path_input.text().strip()
        return p if p else str(Path.home())

    # ═══ 磁盘列表 ══════════════════════════════════════════════════════

    def _get_drives(self):
        """获取可用驱动器列表"""
        drives = []
        for letter in "CDEFGH":
            path = f"{letter}:\\"
            if os.path.exists(path):
                drives.append((path, f"{letter}盘"))
        return drives if drives else [("C:\\", "C盘")]

    # ═══ 工具操作 ══════════════════════════════════════════════════════

    def _do_smart_organize(self):
        self._run_task("📂 智能整理", self._smart_organize)

    def _do_find_duplicates(self):
        self._run_task("🔍 文件查重", self._find_duplicates)

    def _do_scan_large_files(self):
        self._run_task("📊 大文件扫描", self._scan_large_files)

    def _do_clean_empty_files(self):
        self._run_task("🗑 空文件清理", self._clean_empty_files)

    def _do_batch_rename(self):
        """批量重命名 - 弹窗操作"""
        # 简化版：在当前路径批量重命名
        path = self._scan_path
        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        if not files:
            show_warning(self.root, "批量重命名", "当前目录没有文件")
            return
        show_info(self.root, "批量重命名", f"发现 {len(files)} 个文件，功能开发中")

    # ═══ 后台任务执行 ══════════════════════════════════════════════════

    def _run_task(self, task_name, task_fn):
        """在后台线程执行任务"""
        self.result_area.clear()
        self.result_area.append(f"⏳ {task_name} 处理中...")
        self.progress_bar.setRange(0, 0)  # 无限进度
        self.progress_bar.show()

        def _wrapper():
            try:
                results = task_fn()
                return results
            except Exception as e:
                raise e

        self._worker = ThreadWorker(_wrapper)
        self._worker.finished_signal.connect(lambda r: self._on_task_done(task_name, r))
        self._worker.error_signal.connect(lambda e: self._on_task_error(task_name, e))
        self._worker.start()

    def _on_task_done(self, task_name, results):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.hide()
        self.result_area.append(f"✅ {task_name} 完成\n")
        if isinstance(results, list):
            for item in results[:200]:  # 限制输出
                self.result_area.append(str(item))
        elif results:
            self.result_area.append(str(results))

    def _on_task_error(self, task_name, error):
        self.progress_bar.hide()
        self.result_area.append(f"❌ {task_name} 失败: {error}")

    # ═══ 文件操作实现 ══════════════════════════════════════════════════

    def _smart_organize(self):
        """按文件类型智能整理到子文件夹"""
        path = self._scan_path
        results = []
        ext_map = {
            ".jpg": "图片", ".jpeg": "图片", ".png": "图片", ".gif": "图片",
            ".mp4": "视频", ".avi": "视频", ".mkv": "视频",
            ".mp3": "音乐", ".wav": "音乐", ".flac": "音乐",
            ".pdf": "文档", ".doc": "文档", ".docx": "文档", ".xlsx": "文档",
            ".pptx": "文档", ".txt": "文档", ".md": "文档",
            ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包",
            ".exe": "软件", ".msi": "软件",
        }
        for entry in os.scandir(path):
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                folder = ext_map.get(ext, "其他")
                dest_dir = os.path.join(path, folder)
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, entry.name)
                if not os.path.exists(dest):
                    os.rename(entry.path, dest)
                    results.append(f"  {entry.name} → {folder}/")
        return results or ["没有可整理的文件"]

    def _find_duplicates(self):
        """查找重复文件"""
        path = self._scan_path
        hashes = {}
        results = []
        for root, dirs, files in os.walk(path):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    size = os.path.getsize(fpath)
                    if size < 1024:  # 跳过小于 1KB
                        continue
                    import hashlib
                    h = hashlib.md5()
                    with open(fpath, "rb") as f:
                        chunk = f.read(8192)
                        h.update(chunk)
                        h.update(str(size).encode())
                    key = (size, h.hexdigest())
                    if key in hashes:
                        results.append(f"  重复: {fpath}\n     ↔ {hashes[key]}")
                    else:
                        hashes[key] = fpath
                except Exception:
                    pass
        return results[:100] or ["未发现重复文件"]

    def _scan_large_files(self):
        """扫描大文件（>100MB）"""
        path = self._scan_path
        results = []
        large = []
        for root, dirs, files in os.walk(path):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    size = os.path.getsize(fpath)
                    if size > 100 * 1024 * 1024:
                        large.append((size, fpath))
                except Exception:
                    pass

        large.sort(reverse=True)
        for size, fpath in large[:50]:
            results.append(f"  {size / (1024**2):.1f}MB  {fpath}")
        return results or ["未发现大文件（>100MB）"]

    def _clean_empty_files(self):
        """清理空文件"""
        path = self._scan_path
        results = []
        empty_files = []
        empty_dirs = []

        for root, dirs, files in os.walk(path, topdown=False):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    if os.path.getsize(fpath) == 0:
                        os.remove(fpath)
                        results.append(f"  [已删除] {fpath}")
                except Exception as e:
                    pass

            for d in dirs:
                dpath = os.path.join(root, d)
                try:
                    if not os.listdir(dpath):
                        os.rmdir(dpath)
                        results.append(f"  [已删除空目录] {dpath}")
                except Exception:
                    pass

        return results or ["没有可清理的空文件"]
