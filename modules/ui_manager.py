"""
UIManager — PyQt6 版 UI 工具集

提供：ThreadWorker、StreamingManager、消息卡片、仪表盘等通用组件。
替代原 tkinter 版 ui_manager.py，保留窗口状态保存/恢复功能。
"""

import logging
from datetime import datetime
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                              QProgressBar, QPushButton, QSizePolicy, QApplication)
from qfluentwidgets import InfoBar, InfoBarPosition, IndeterminateProgressBar

from modules.fluent_theme import (
    BG_CARD, BG_HOVER, TEXT, SUBTEXT0, FG_PRIMARY,
    ACCENT, SUCCESS, WARNING, DANGER, INFO, RADIUS, RADIUS_LG, PADDING,
    card_stylesheet, button_stylesheet,
)

logger = logging.getLogger("UIManager")

# ═══════════════════════════════════════════════════════════════════════
# 线程安全工具
# ═══════════════════════════════════════════════════════════════════════

class ThreadWorker(QThread):
    """通用后台工作线程 - 替代 tkinter 的 threading.Thread + root.after"""
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))
            logger.error(f"ThreadWorker 异常: {e}")


# ═══════════════════════════════════════════════════════════════════════
# 流式输出管理器 (Qt 版)
# ═══════════════════════════════════════════════════════════════════════

class FluentStreamingManager:
    """流式输出管理器 — 简易封装

    不依赖 tkinter root。用于后台任务管理。
    """

    def __init__(self):
        self._active = False
        self._cancel = False
        self._start_time = 0
        self._full_text = []
        self._header_sent = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def elapsed(self) -> float:
        if not self._start_time:
            return 0
        import time
        return time.time() - self._start_time

    def cancel(self):
        self._cancel = True

    def start(self, task_fn, *, label="AI", status_prefix="思考中", timeout=300):
        """启动流式会话

        Args:
            task_fn: (token_callback, cancel_event) -> result_str
        """
        if self._active:
            return

        self._cancel = False
        self._active = True
        import time
        self._start_time = time.time()
        self._full_text = []
        self._header_sent = False

        import threading

        def _on_token(token):
            if self._cancel:
                return
            self.token_signal.emit(token)

        def _run():
            try:
                result = task_fn(_on_token, self)
                if self._cancel:
                    self.done_signal.emit({"status": "cancelled"})
                    return
                self.done_signal.emit({
                    "status": "ok",
                    "result": result,
                    "elapsed": self.elapsed,
                })
            except Exception as e:
                self.done_signal.emit({"status": "error", "message": str(e)})

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()


# ═══════════════════════════════════════════════════════════════════════
# 卡片组件
# ═══════════════════════════════════════════════════════════════════════

def create_card(parent, title="", border_highlight=None) -> QFrame:
    """创建一张 Catppuccin 风格卡片

    Returns:
        QFrame 卡片容器（含 QVBoxLayout）
    """
    card = QFrame(parent)
    card.setObjectName("card")
    bg = BG_CARD
    border_qss = ""
    if border_highlight:
        border_qss = f"border: 1px solid {border_highlight};"
    card.setStyleSheet(f"""
        #card {{
            background: {bg};
            border-radius: {RADIUS_LG}px;
            {border_qss}
            padding: {PADDING}px;
        }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
    layout.setSpacing(8)

    if title:
        label = QLabel(title)
        label.setObjectName("card-title")
        label.setStyleSheet(f"""
            #card-title {{
                color: {TEXT};
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        layout.addWidget(label)

    return card, layout


def create_section_title(text: str, parent=None) -> QLabel:
    """创建区域标题标签"""
    label = QLabel(text, parent)
    label.setStyleSheet(f"color: {SUBTEXT0}; font-size: 12px; font-weight: bold;")
    return label


# ═══════════════════════════════════════════════════════════════════════
# 仪表盘进度条
# ═══════════════════════════════════════════════════════════════════════

class DashboardGauge(QFrame):
    """仪表盘进度条 — 颜色随使用率变化"""

    def __init__(self, parent=None, label=""):
        super().__init__(parent)
        self.setObjectName("dashboard-gauge")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 顶部标签行
        hdr = QHBoxLayout()
        self._title = QLabel(label)
        self._title.setStyleSheet(f"color: {SUBTEXT0}; font-size: 12px;")
        hdr.addWidget(self._title)
        hdr.addStretch()
        self._percent = QLabel("0%")
        self._percent.setStyleSheet(f"color: {TEXT}; font-size: 12px; font-weight: bold;")
        hdr.addWidget(self._percent)
        layout.addLayout(hdr)

        # 进度条
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        layout.addWidget(self._bar)

    def update_value(self, value: float, label: str = None):
        """更新进度条值 (0-100)"""
        self._bar.setValue(int(value))
        self._percent.setText(f"{value:.0f}%")
        if label:
            self._title.setText(label)
        # 颜色随使用率变化
        if value < 50:
            color = SUCCESS
        elif value < 75:
            color = WARNING
        elif value < 90:
            color = "#fab387"
        else:
            color = DANGER
        self._bar.setStyleSheet(f"""
            QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}
        """)


# ═══════════════════════════════════════════════════════════════════════
# 状态点指示器
# ═══════════════════════════════════════════════════════════════════════

class StatusDot(QWidget):
    """状态指示点 + 文字"""

    def __init__(self, parent=None, text="", color=SUCCESS):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet(f"""
            background: {color};
            border-radius: 5px;
        """)
        layout.addWidget(self._dot)

        self._label = QLabel(text)
        self._label.setStyleSheet(f"color: {SUBTEXT0}; font-size: 12px;")
        layout.addWidget(self._label)
        layout.addStretch()

    def set_color(self, color):
        self._dot.setStyleSheet(f"background: {color}; border-radius: 5px;")

    def set_text(self, text):
        self._label.setText(text)

    def start_pulse(self, duration_ms=1200):
        """启动脉冲动画"""
        self._pulse_on = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle_pulse)
        self._timer.start(duration_ms // 2)

    def _toggle_pulse(self):
        self._dot.setVisible(not self._dot.isVisible())

    def stop_pulse(self):
        if hasattr(self, '_timer') and self._timer:
            self._timer.stop()
        self._dot.setVisible(True)


# ═══════════════════════════════════════════════════════════════════════
# 消息提示
# ═══════════════════════════════════════════════════════════════════════

def show_info(parent, title="", content="", duration=3000):
    """显示 InfoBar 信息提示"""
    InfoBar.info(
        title=title, content=content, parent=parent,
        position=InfoBarPosition.TOP_RIGHT, duration=duration,
    )


def show_success(parent, title="", content="", duration=3000):
    InfoBar.success(
        title=title, content=content, parent=parent,
        position=InfoBarPosition.TOP_RIGHT, duration=duration,
    )


def show_warning(parent, title="", content="", duration=4000):
    InfoBar.warning(
        title=title, content=content, parent=parent,
        position=InfoBarPosition.TOP_RIGHT, duration=duration,
    )


def show_error(parent, title="", content="", duration=5000):
    InfoBar.error(
        title=title, content=content, parent=parent,
        position=InfoBarPosition.TOP_RIGHT, duration=duration,
    )
