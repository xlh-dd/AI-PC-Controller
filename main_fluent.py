"""
AI电脑管家 — PyQt6 + Fluent-Widgets 入口

从 tkinter+ttkbootstrap 全面迁移至 Fluent Design 风格。
保留所有业务逻辑（controllers/services/modules），仅重写 UI 层。

启动: python main_fluent.py
"""

import sys
import os
import logging
import threading
import time
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtWidgets import QApplication, QStackedWidget, QWidget
from PyQt6.QtGui import QIcon
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    setTheme, Theme, InfoBar, InfoBarPosition,
)

# ═══ 路径设置 ═════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.fluent_theme import apply_global_stylesheet

logger = logging.getLogger("AI电脑管家")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


# ═══════════════════════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════════════════════

class MainWindow(FluentWindow):
    """AI电脑管家主窗口 - Fluent Design 风格"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI电脑管家")
        self.resize(1200, 800)
        self.setMinimumSize(960, 640)

        # ── 初始化控制器层（复用现有代码） ──
        self._init_controllers()

        # ── 创建面板 ──
        self._chat_panel = None
        self._system_panel = None
        self._file_panel = None
        self._wechat_panel = None
        self._automation_panel = None

        # ── 导航 ──
        self._setup_navigation()

        # ── 更新原生标题栏 UI ──
        self.stackedWidget.setStyleSheet("QStackedWidget { background: #1e1e2e; }")

        # ── 延迟加载重模块 ──
        QTimer.singleShot(200, self._lazy_init_modules)

        # ── 窗口状态恢复 ──
        self._restore_window_state()

        logger.info("AI电脑管家 (Fluent UI) 启动完成")

    # ═══ 控制器初始化 ══════════════════════════════════════════════════

    def _init_controllers(self):
        """初始化控制器层 — 复用现有代码"""
        from utils.config import ConfigManager
        from controllers.app_controller import AppController
        from controllers.message_router import MessageRouter
        from controllers.command_handler import CommandHandler

        config = ConfigManager()
        self.controller = AppController(config)
        self.controller.root = self  # 兼容现有代码引用

        # 消息路由
        self.controller.message_router = MessageRouter(self.controller)
        self.controller.command_handler = CommandHandler(self.controller)

    # ═══ 导航设置 ══════════════════════════════════════════════════════

    def _setup_navigation(self):
        """配置侧边导航栏"""

        # 延迟创建面板引用（占位）
        # 面板在第一次切换时才真正构建（与原来一样懒加载）
        self.navigationInterface.setExpandWidth(180)

        # 顶部导航项
        chat_interface = QWidget()  # 占位，实际在 _on_nav 中懒加载
        self.addSubInterface(chat_interface, FluentIcon.CHAT, "智能对话")
        self.addSubInterface(QWidget(), FluentIcon.FOLDER, "文件管理")
        self.addSubInterface(QWidget(), FluentIcon.COMMAND, "系统控制")
        self.addSubInterface(QWidget(), FluentIcon.PEOPLE, "微信通讯")
        self.addSubInterface(QWidget(), FluentIcon.ROBOT, "自动化")

        # 底部
        self.addSubInterface(QWidget(), FluentIcon.SETTING, "设置", NavigationItemPosition.BOTTOM)

        # 连接切换信号
        self.stackedWidget.currentChanged.connect(self._on_tab_changed)

        # 默认选中智能对话
        self.stackedWidget.setCurrentIndex(0)

    # ═══ 面板懒加载 ════════════════════════════════════════════════════

    def _on_tab_changed(self, index):
        """选项卡切换时懒加载面板"""
        panels = [
            ("chat", 0, self._ensure_chat_panel),
            ("file", 1, self._ensure_file_panel),
            ("system", 2, self._ensure_system_panel),
            ("wechat", 3, self._ensure_wechat_panel),
            ("automation", 4, self._ensure_automation_panel),
        ]
        for name, idx, fn in panels:
            if index == idx:
                fn()
                break

    def _ensure_chat_panel(self):
        if self._chat_panel:
            return
        from panels.chat_panel import ChatPanel
        self._chat_panel = ChatPanel(self, self.controller)
        old = self.stackedWidget.widget(0)
        self.stackedWidget.insertWidget(0, self._chat_panel)
        self.stackedWidget.setCurrentWidget(self._chat_panel)
        if old:
            old.deleteLater()

    def _ensure_file_panel(self):
        if self._file_panel:
            return
        from panels.file_panel import FilePanel
        self._file_panel = FilePanel(self, self.controller)
        old = self.stackedWidget.widget(1)
        self.stackedWidget.insertWidget(1, self._file_panel)
        self.stackedWidget.setCurrentWidget(self._file_panel)
        if old:
            old.deleteLater()

    def _ensure_system_panel(self):
        if self._system_panel:
            return
        from panels.system_panel import SystemPanel
        self._system_panel = SystemPanel(self, self.controller)
        old = self.stackedWidget.widget(2)
        self.stackedWidget.insertWidget(2, self._system_panel)
        self.stackedWidget.setCurrentWidget(self._system_panel)
        if old:
            old.deleteLater()

    def _ensure_wechat_panel(self):
        if self._wechat_panel:
            return
        from panels.wechat_panel import WeChatPanel
        self._wechat_panel = WeChatPanel(self, self.controller)
        old = self.stackedWidget.widget(3)
        self.stackedWidget.insertWidget(3, self._wechat_panel)
        self.stackedWidget.setCurrentWidget(self._wechat_panel)
        if old:
            old.deleteLater()

    def _ensure_automation_panel(self):
        if self._automation_panel:
            return
        from panels.automation_panel import AutomationPanel
        self._automation_panel = AutomationPanel(self, self.controller)
        old = self.stackedWidget.widget(4)
        self.stackedWidget.insertWidget(4, self._automation_panel)
        self.stackedWidget.setCurrentWidget(self._automation_panel)
        if old:
            old.deleteLater()

    # ═══ 延迟初始化重模块 ══════════════════════════════════════════════

    def _lazy_init_modules(self):
        """延迟加载重量级模块"""
        logger.info("正在加载后端模块...")

        def _load():
            try:
                # 初始化 AI 后端
                self.controller.initialize_backends()
                logger.info("AI 后端初始化完成")
            except Exception as e:
                logger.warning(f"部分后端模块加载失败: {e}")

        threading.Thread(target=_load, daemon=True).start()

    # ═══ 消息输出 ══════════════════════════════════════════════════════

    def say(self, msg, level="info"):
        """全局消息输出 — 兼容原 tkinter 的 say()"""
        levels = {
            "info": (InfoBar.info, "提示", 3000),
            "success": (InfoBar.success, "成功", 3000),
            "warning": (InfoBar.warning, "警告", 4000),
            "error": (InfoBar.error, "错误", 5000),
        }
        fn, title, dur = levels.get(level, (InfoBar.info, "提示", 3000))
        try:
            fn(title=title, content=msg, parent=self,
               position=InfoBarPosition.TOP_RIGHT, duration=dur)
        except Exception:
            pass

    # ═══ 窗口状态 ══════════════════════════════════════════════════════

    def _restore_window_state(self):
        """恢复窗口大小位置"""
        settings = QSettings("AI管家", "MainWindow")
        geo = settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        state = settings.value("windowState")
        if state:
            self.restoreState(state)

    def closeEvent(self, event):
        """保存状态、清理资源"""
        # 保存窗口状态
        settings = QSettings("AI管家", "MainWindow")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())

        # 停止所有后台线程
        if self._wechat_panel and hasattr(self._wechat_panel, '_stop_listener'):
            self._wechat_panel._stop_listener()

        event.accept()


# ═══════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════

def main():
    # 高 DPI 适配
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("AI电脑管家")
    app.setOrganizationName("AI管家")

    # Fluent 暗色主题
    setTheme(Theme.DARK)
    apply_global_stylesheet(app)

    # 启动窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
