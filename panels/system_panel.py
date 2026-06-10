"""
SystemPanel — 系统控制面板 (PyQt6 + Fluent 版)

功能：
- 电源操作（关机/重启/注销/锁屏/休眠/睡眠）
- 系统仪表盘（CPU/内存/磁盘进度条，5s 自动刷新）
- 音量控制
- 系统信息
"""

import logging
import subprocess
import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QPushButton, QLabel, QSlider, QProgressBar,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, FluentIcon, InfoBarPosition,
)

from modules.fluent_theme import (
    BG_PRIMARY, MANTLE, SURFACE0, TEXT, SUBTEXT0, FG_PRIMARY,
    BLUE, GREEN, RED, YELLOW, PEACH, TEAL, SAPPHIRE,
    RADIUS, RADIUS_LG, PADDING, PADDING_SM, PADDING_LG,
    button_stylesheet, outline_button_stylesheet, card_stylesheet,
)
from modules.ui_manager import DashboardGauge

logger = logging.getLogger("SystemPanel")


# ═══════════════════════════════════════════════════════════════════════
# SystemPanel
# ═══════════════════════════════════════════════════════════════════════

class SystemPanel(QWidget):
    """系统控制面板"""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.root = parent
        self._refresh_timer = None
        self._gauges = {}  # "cpu" / "memory" / "disk"

        self._build_ui()
        self._start_auto_refresh()

    # ═══ UI 构建 ══════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING_LG, PADDING_LG, PADDING_LG, PADDING_LG)
        layout.setSpacing(PADDING_LG)

        # ── 标题 ──
        title = QLabel("系统控制")
        title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        # ── 电源操作卡片 ──
        power_card = QFrame()
        power_card.setStyleSheet(card_stylesheet())
        power_layout = QVBoxLayout(power_card)
        power_layout.setSpacing(PADDING)

        power_title = QLabel("电源操作")
        power_title.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: bold;")
        power_layout.addWidget(power_title)

        btn_grid = QGridLayout()
        btn_grid.setSpacing(PADDING_SM)

        power_actions = [
            ("关机", RED, self._do_shutdown),
            ("重启", PEACH, self._do_restart),
            ("注销", YELLOW, self._do_logout),
            ("锁屏", BLUE, self._do_lock),
            ("休眠", TEAL, self._do_hibernate),
            ("睡眠", SAPPHIRE, self._do_sleep),
        ]

        for i, (name, color, fn) in enumerate(power_actions):
            btn = QPushButton(f"◉\n{name}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color}25;
                    color: {color};
                    border: 2px solid {color}40;
                    border-radius: {RADIUS_LG}px;
                    padding: 12px 8px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {color}40;
                    border-color: {color};
                }}
            """)
            btn.setFixedHeight(70)
            btn.clicked.connect(fn)
            btn_grid.addWidget(btn, i // 3, i % 3)

        power_layout.addLayout(btn_grid)
        layout.addWidget(power_card)

        # ── 系统仪表盘 ──
        dash_card = QFrame()
        dash_card.setStyleSheet(card_stylesheet())
        dash_layout = QVBoxLayout(dash_card)
        dash_layout.setSpacing(PADDING)

        dash_title = QLabel("系统仪表盘")
        dash_title.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: bold;")
        dash_layout.addWidget(dash_title)

        # CPU / 内存 / 磁盘
        self._gauges["cpu"] = DashboardGauge(label="CPU 使用率")
        self._gauges["memory"] = DashboardGauge(label="内存使用率")
        self._gauges["disk"] = DashboardGauge(label="系统盘 (C:\\)")
        dash_layout.addWidget(self._gauges["cpu"])
        dash_layout.addWidget(self._gauges["memory"])
        dash_layout.addWidget(self._gauges["disk"])

        layout.addWidget(dash_card)

        # ── 音量和系统工具 ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(PADDING)

        # 音量
        vol_card = QFrame()
        vol_card.setStyleSheet(card_stylesheet())
        vol_layout = QVBoxLayout(vol_card)
        vol_layout.setSpacing(PADDING)

        vol_title = QLabel("🔊 音量控制")
        vol_title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: bold;")
        vol_layout.addWidget(vol_title)

        vol_slider_row = QHBoxLayout()
        self.vol_label = QLabel("50")
        self.vol_label.setStyleSheet(f"color: {TEXT}; font-size: 28px; font-weight: bold; min-width: 50px;")
        vol_slider_row.addWidget(self.vol_label)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.valueChanged.connect(self._on_vol_changed)
        vol_slider_row.addWidget(self.vol_slider, stretch=1)

        vol_layout.addLayout(vol_slider_row)
        bottom_row.addWidget(vol_card, stretch=1)

        # 系统工具
        tool_card = QFrame()
        tool_card.setStyleSheet(card_stylesheet())
        tool_layout = QVBoxLayout(tool_card)
        tool_layout.setSpacing(PADDING)

        tool_title = QLabel("系统工具")
        tool_title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: bold;")
        tool_layout.addWidget(tool_title)

        tools = [
            ("任务管理器", self._open_taskmgr),
            ("系统信息", self._open_sysinfo),
            ("磁盘清理", self._open_diskcleanup),
        ]
        for name, fn in tools:
            btn = PushButton(name)
            btn.clicked.connect(fn)
            tool_layout.addWidget(btn)

        bottom_row.addWidget(tool_card, stretch=1)
        layout.addLayout(bottom_row)

        # ── 系统信息 ──
        info_card = QFrame()
        info_card.setStyleSheet(card_stylesheet())
        info_layout = QVBoxLayout(info_card)
        info_layout.setSpacing(4)

        self.info_label = QLabel("正在加载系统信息...")
        self.info_label.setStyleSheet(f"color: {SUBTEXT0}; font-size: 12px;")
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)

        layout.addWidget(info_card)

    # ═══ 电源操作 ══════════════════════════════════════════════════════

    def _do_shutdown(self):
        self._confirm_action("确认关机？", "shutdown /s /t 30 /c \"AI管家定时关机\"")

    def _do_restart(self):
        self._confirm_action("确认重启？", "shutdown /r /t 30 /c \"AI管家定时重启\"")

    def _do_logout(self):
        self._confirm_action("确认注销？", "shutdown /l")

    def _do_lock(self):
        self._confirm_action("确认锁屏？", "rundll32.exe user32.dll,LockWorkStation")

    def _do_hibernate(self):
        self._confirm_action("确认休眠？", "shutdown /h")

    def _do_sleep(self):
        self._confirm_action("确认睡眠？", "rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

    def _confirm_action(self, msg, command):
        """简单确认后执行"""
        from qfluentwidgets import MessageBox
        box = MessageBox("确认操作", msg, self.root)
        if box.exec():
            try:
                subprocess.Popen(command, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                from modules.ui_manager import show_info
                show_info(self.root, "执行中", f"命令已提交：{msg}")
            except Exception as e:
                from modules.ui_manager import show_error
                show_error(self.root, "执行失败", str(e))

    # ═══ 音量 ══════════════════════════════════════════════════════════

    def _on_vol_changed(self, value):
        self.vol_label.setText(str(value))

    # ═══ 系统工具 ══════════════════════════════════════════════════════

    def _open_taskmgr(self):
        subprocess.Popen("taskmgr", creationflags=subprocess.CREATE_NO_WINDOW)

    def _open_sysinfo(self):
        subprocess.Popen("msinfo32", creationflags=subprocess.CREATE_NO_WINDOW)

    def _open_diskcleanup(self):
        subprocess.Popen("cleanmgr", creationflags=subprocess.CREATE_NO_WINDOW)

    # ═══ 仪表盘刷新 ════════════════════════════════════════════════════

    def _start_auto_refresh(self):
        """启动自动刷新（每 5 秒）"""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_system_info)
        self._refresh_timer.start(5000)
        self._refresh_system_info()  # 立即刷新一次

    def _refresh_system_info(self):
        """后台刷新系统信息"""
        def _do_refresh():
            try:
                import psutil

                cpu = psutil.cpu_percent(interval=1)
                mem = psutil.virtual_memory().percent
                disk = psutil.disk_usage("C:\\").percent

                boot = psutil.boot_time()
                import time
                uptime_sec = time.time() - boot
                h, m = divmod(int(uptime_sec // 60), 60)

                self._gauges["cpu"].update_value(cpu, f"CPU 使用率")
                self._gauges["memory"].update_value(mem, f"内存使用率")
                self._gauges["disk"].update_value(disk, "系统盘 (C:\\)")
                self.info_label.setText(
                    f"系统运行时间: {h}小时{m}分钟 · Python {__import__('sys').version.split()[0]}"
                )
            except ImportError:
                self.info_label.setText("psutil 未安装，部分信息不可用")
            except Exception as e:
                pass

        threading.Thread(target=_do_refresh, daemon=True).start()
