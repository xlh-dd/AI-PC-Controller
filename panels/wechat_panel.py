"""
WeChatPanel — 微信通讯面板 (PyQt6 + Fluent 版)

功能：
- 微信消息监听（OCR 模式）
- 定时发送消息
- 远程指令执行
- 监听状态指示（脉冲动画）
"""

import logging
import threading
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QPushButton, QLabel, QLineEdit, QTextEdit, QSpinBox,
    QCheckBox, QGroupBox,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, SwitchButton, LineEdit, TextEdit,
    FluentIcon, InfoBarPosition, InfoBar,
)

from modules.fluent_theme import (
    BG_PRIMARY, MANTLE, SURFACE0, SURFACE1, TEXT, SUBTEXT0, FG_PRIMARY,
    BLUE, GREEN, RED, YELLOW, PEACH,
    RADIUS, RADIUS_LG, PADDING, PADDING_SM, PADDING_LG,
    card_stylesheet, button_stylesheet, outline_button_stylesheet,
)
from modules.ui_manager import StatusDot, show_info, show_error, show_warning

logger = logging.getLogger("WeChatPanel")


# ═══════════════════════════════════════════════════════════════════════
# WeChatPanel
# ═══════════════════════════════════════════════════════════════════════

class WeChatPanel(QWidget):
    """微信通讯面板"""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.root = parent

        self._listening = False
        self._listener_thread = None
        self._stop_event = threading.Event()

        self._build_ui()

    # ═══ UI 构建 ══════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING_LG, PADDING_LG, PADDING_LG, PADDING_LG)
        layout.setSpacing(PADDING)

        # ── 标题 ──
        title = QLabel("微信通讯")
        title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        # ── 第一行：监听 + 定时发送 ──
        top_row = QHBoxLayout()
        top_row.setSpacing(PADDING)

        # 监听卡片
        listen_card = QFrame()
        listen_card.setStyleSheet(card_stylesheet())
        listen_layout = QVBoxLayout(listen_card)
        listen_layout.setSpacing(PADDING)

        listen_title = QLabel("📡 消息监听")
        listen_title.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: bold;")
        listen_layout.addWidget(listen_title)

        # 状态指示
        status_row = QHBoxLayout()
        self.listen_status = StatusDot(text="监听已停止", color="#6c7086")
        self.listen_status.set_text("监听已停止")
        status_row.addWidget(self.listen_status)
        status_row.addStretch()
        listen_layout.addLayout(status_row)

        # 控制按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(PADDING_SM)

        self.start_btn = PrimaryPushButton("▶ 启动监听")
        self.start_btn.clicked.connect(self._start_listener)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = PushButton("⏹ 停止监听")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_listener)
        btn_row.addWidget(self.stop_btn)

        open_wechat_btn = PushButton("打开微信")
        open_wechat_btn.clicked.connect(self._open_wechat)
        btn_row.addWidget(open_wechat_btn)

        listen_layout.addLayout(btn_row)
        top_row.addWidget(listen_card)

        # 定时发送卡片
        send_card = QFrame()
        send_card.setStyleSheet(card_stylesheet())
        send_layout = QVBoxLayout(send_card)
        send_layout.setSpacing(PADDING)

        send_title = QLabel("⏰ 定时发送")
        send_title.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: bold;")
        send_layout.addWidget(send_title)

        # 目标
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("联系人:"))
        self.target_input = LineEdit()
        self.target_input.setPlaceholderText("微信昵称或备注...")
        target_row.addWidget(self.target_input, stretch=1)
        send_layout.addLayout(target_row)

        # 消息内容
        self.schedule_msg = TextEdit()
        self.schedule_msg.setPlaceholderText("定时发送的消息内容...")
        self.schedule_msg.setFixedHeight(60)
        self.schedule_msg.setAcceptRichText(False)
        send_layout.addWidget(self.schedule_msg)

        # 时间设置
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("延迟:"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(1, 300)
        self.delay_spin.setValue(10)
        self.delay_spin.setSuffix(" 秒")
        time_row.addWidget(self.delay_spin)
        time_row.addStretch()

        schedule_btn = PrimaryPushButton("设置定时")
        schedule_btn.clicked.connect(self._schedule_message)
        time_row.addWidget(schedule_btn)
        send_layout.addLayout(time_row)

        top_row.addWidget(send_card)
        layout.addLayout(top_row)

        # ── 远程指令卡片 ──
        cmd_card = QFrame()
        cmd_card.setStyleSheet(card_stylesheet())
        cmd_layout = QVBoxLayout(cmd_card)
        cmd_layout.setSpacing(PADDING)

        cmd_title = QLabel("🤖 远程指令执行")
        cmd_title.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: bold;")
        cmd_layout.addWidget(cmd_title)

        cmd_hint = QLabel("通过微信消息发送指令（如 /关机、/截图），AI管家自动执行。")
        cmd_hint.setStyleSheet(f"color: {SUBTEXT0}; font-size: 12px;")
        cmd_layout.addWidget(cmd_hint)

        examples = QHBoxLayout()
        for cmd in ["/关机", "/重启", "/锁屏", "/截图", "/音量 50", "/查询系统"]:
            chip = QLabel(cmd)
            chip.setStyleSheet(f"""
                background: {SURFACE1};
                color: {TEXT};
                border-radius: {RADIUS}px;
                padding: 4px 10px;
                font-size: 12px;
            """)
            examples.addWidget(chip)
        examples.addStretch()
        cmd_layout.addLayout(examples)

        layout.addWidget(cmd_card)

        # ── 日志区域 ──
        log_card = QFrame()
        log_card.setStyleSheet(card_stylesheet())
        log_layout = QVBoxLayout(log_card)
        log_layout.setSpacing(PADDING)

        log_title = QLabel("📋 通讯日志")
        log_title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: bold;")
        log_layout.addWidget(log_title)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("微信通讯日志...")
        self.log_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {MANTLE};
                color: {SUBTEXT0};
                border: 1px solid {SURFACE1};
                border-radius: {RADIUS}px;
                padding: {PADDING}px;
                font-family: Consolas, "Microsoft YaHei UI", monospace;
                font-size: 12px;
            }}
        """)
        log_layout.addWidget(self.log_area)

        layout.addWidget(log_card, stretch=1)

    # ═══ 日志 ══════════════════════════════════════════════════════════

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{ts}] {msg}")

    # ═══ 监听控制 ══════════════════════════════════════════════════════

    def _start_listener(self):
        if self._listening:
            return

        # 尝试打开微信
        self._open_wechat()

        self._listening = True
        self._stop_event.clear()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.listen_status.set_color(GREEN)
        self.listen_status.set_text("监听中...")
        self.listen_status.start_pulse()

        self._log("🟢 微信消息监听已启动")

        # 后台监听线程
        def _listen_loop():
            fail_count = 0
            while not self._stop_event.is_set():
                try:
                    # 尝试通过 wechat_controller 获取消息
                    if hasattr(self.controller, 'wechat_controller'):
                        wc = self.controller.wechat_controller
                        if hasattr(wc, 'get_new_messages'):
                            msgs = wc.get_new_messages()
                            for msg in msgs:
                                self._log(f"💬 {msg.get('sender','?')}: {msg.get('content','')}")

                    time.sleep(2)
                    fail_count = 0
                except Exception as e:
                    fail_count += 1
                    if fail_count >= 5:
                        def _stop():
                            self._stop_listener()
                            show_error(self.root, "监听错误", f"连续失败 {fail_count} 次，已自动停止")
                        QTimer.singleShot(0, _stop)
                        break
                    time.sleep(5)

        self._listener_thread = threading.Thread(target=_listen_loop, daemon=True)
        self._listener_thread.start()

    def _stop_listener(self):
        if not self._listening:
            return

        self._listening = False
        self._stop_event.set()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.listen_status.set_color("#6c7086")
        self.listen_status.set_text("监听已停止")
        self.listen_status.stop_pulse()

        self._log("🔴 微信消息监听已停止")

    def _open_wechat(self):
        """尝试打开微信"""
        import subprocess
        wechat_paths = [
            r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
        ]
        for path in wechat_paths:
            import os
            if os.path.exists(path):
                try:
                    subprocess.Popen(path, creationflags=subprocess.CREATE_NO_WINDOW)
                    self._log("📱 微信已启动")
                    return
                except Exception:
                    pass
        self._log("⚠️ 未找到微信安装路径")

    def _schedule_message(self):
        """定时发送消息"""
        target = self.target_input.text().strip()
        msg = self.schedule_msg.toPlainText().strip()
        delay = self.delay_spin.value()

        if not target or not msg:
            show_warning(self.root, "定时发送", "请填写联系人和消息内容")
            return

        self._log(f"⏰ 已设置定时发送 → {target}（{delay}秒后）")
        self.schedule_msg.clear()

        show_info(self.root, "定时发送", f"将在 {delay} 秒后发送消息给 {target}")
        self._log(f"📤 定时消息内容: {msg}")

        # 定时器
        QTimer.singleShot(delay * 1000, lambda: self._do_send(target, msg))

    def _do_send(self, target, msg):
        """实际发送消息"""
        self._log(f"📤 正在发送消息给 {target}...")
        try:
            if hasattr(self.controller, 'wechat_controller'):
                wc = self.controller.wechat_controller
                if hasattr(wc, 'send_message'):
                    wc.send_message(target, msg)
                    self._log(f"✅ 消息已发送给 {target}")
                    return
        except Exception as e:
            self._log(f"❌ 发送失败: {e}")
        self._log("⚠️ 微信控制器不可用，消息未发送")
