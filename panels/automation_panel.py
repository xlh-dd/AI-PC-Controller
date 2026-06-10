"""
AutomationPanel — 自动化面板 (PyQt6 + Fluent 版)

功能：
- 宏录制/回放
- 定时任务（命令/应用/脚本/循环）
- AI 智能体
- 编程工作区
"""

import logging
import threading
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QPushButton, QLabel, QLineEdit, QTextEdit, QSpinBox,
    QCheckBox, QComboBox,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit, TextEdit, ComboBox,
    FluentIcon, InfoBarPosition, IndeterminateProgressBar,
)

from modules.fluent_theme import (
    BG_PRIMARY, MANTLE, SURFACE0, SURFACE1, TEXT, SUBTEXT0, FG_PRIMARY,
    BLUE, GREEN, RED, YELLOW, PEACH, MAUVE, LAVENDER,
    RADIUS, RADIUS_LG, PADDING, PADDING_SM, PADDING_LG,
    card_stylesheet, button_stylesheet, outline_button_stylesheet,
)
from modules.ui_manager import show_info, show_error

logger = logging.getLogger("AutomationPanel")


# ═══════════════════════════════════════════════════════════════════════
# AutomationPanel
# ═══════════════════════════════════════════════════════════════════════

class AutomationPanel(QWidget):
    """自动化面板"""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.root = parent

        # 宏录制状态
        self._recording = False
        self._macro_actions = []
        self._macro_name = "未命名宏"

        self._build_ui()

    # ═══ UI 构建 ══════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING_LG, PADDING_LG, PADDING_LG, PADDING_LG)
        layout.setSpacing(PADDING)

        # ── 标题 ──
        title = QLabel("自动化")
        title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        # ── 功能卡片网格（2行 × 2列） ──
        grid = QGridLayout()
        grid.setSpacing(PADDING)

        cards = [
            ("🎬 宏录制", "录制键盘鼠标操作\n一键回放", BLUE, self._build_macro_card),
            ("⏰ 定时任务", "命令/应用/脚本\n循环定时执行", GREEN, self._build_task_card),
            ("🤖 AI 智能体", "自动执行任务\n多步骤推理", MAUVE, self._build_agent_card),
            ("💻 编程工作区", "Python 脚本执行\n代码片段管理", PEACH, self._build_code_card),
        ]

        for i, (name, desc, color, build_fn) in enumerate(cards):
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {SURFACE0};
                    border-top: 3px solid {color};
                    border-radius: {RADIUS_LG}px;
                    padding: {PADDING}px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(6)

            # 图标 + 标题
            header = QHBoxLayout()
            name_label = QLabel(name)
            name_label.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: bold;")
            header.addWidget(name_label)
            header.addStretch()
            card_layout.addLayout(header)

            # 描述
            desc_label = QLabel(desc)
            desc_label.setStyleSheet(f"color: {SUBTEXT0}; font-size: 12px;")
            desc_label.setWordWrap(True)
            card_layout.addWidget(desc_label)

            card_layout.addStretch()

            # 内建内容
            build_fn(card_layout)

            card.mousePressEvent = lambda e, fn=build_fn: None
            grid.addWidget(card, i // 2, i % 2)

        layout.addLayout(grid)

        # ── 帮助提示 ──
        help_card = QFrame()
        help_card.setStyleSheet(f"""
            background: {SURFACE0};
            border: 1px solid {SURFACE1};
            border-radius: {RADIUS}px;
            padding: {PADDING}px;
        """)
        help_layout = QVBoxLayout(help_card)
        help_layout.setSpacing(4)

        help_title = QLabel("💡 提示")
        help_title.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        help_layout.addWidget(help_title)

        tips = [
            "宏录制依赖 modules.macro_recorder，录制时按 F8 开始/停止",
            "定时任务通过 ctrl.task_scheduler 管理，支持命令、应用、脚本、循环四种类型",
            "AI 智能体可自动规划和执行多步骤操作，适合复杂自动化场景",
            "编程工作区可运行 Python 脚本，输出结果显示在控制台中",
        ]
        for tip in tips:
            tip_label = QLabel(f"• {tip}")
            tip_label.setStyleSheet(f"color: {SUBTEXT0}; font-size: 11px;")
            tip_label.setWordWrap(True)
            help_layout.addWidget(tip_label)

        layout.addWidget(help_card)

    # ═══ 宏录制卡片内容 ══════════════════════════════════════════════

    def _build_macro_card(self, parent_layout):
        """向卡片内添加宏录制控件"""

        # 宏名称
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("名称:"))
        self.macro_name_input = LineEdit()
        self.macro_name_input.setText("未命名宏")
        self.macro_name_input.setFixedWidth(150)
        name_row.addWidget(self.macro_name_input)
        name_row.addStretch()
        parent_layout.addLayout(name_row)

        # 控制按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(PADDING_SM)

        self.record_btn = PrimaryPushButton("⏺ 开始录制")
        self.record_btn.clicked.connect(self._toggle_recording)
        btn_row.addWidget(self.record_btn)

        self.play_btn = PushButton("▶ 回放")
        self.play_btn.clicked.connect(self._play_macro)
        self.play_btn.setEnabled(False)
        btn_row.addWidget(self.play_btn)

        parent_layout.addLayout(btn_row)

        # 重复次数
        repeat_row = QHBoxLayout()
        repeat_row.addWidget(QLabel("重复:"))
        self.repeat_spin = QSpinBox()
        self.repeat_spin.setRange(1, 100)
        self.repeat_spin.setValue(1)
        repeat_row.addWidget(self.repeat_spin)
        repeat_row.addWidget(QLabel("次"))
        repeat_row.addStretch()
        parent_layout.addLayout(repeat_row)

        # 进度
        self.macro_progress = IndeterminateProgressBar()
        self.macro_progress.hide()
        parent_layout.addWidget(self.macro_progress)

    def _toggle_recording(self):
        """切换录制状态"""
        if self._recording:
            self._recording = False
            self.record_btn.setText("⏺ 开始录制")
            self.record_btn.setStyleSheet("")
            show_info(self.root, "宏录制", f"已停止录制，共 {len(self._macro_actions)} 个动作")
            self.play_btn.setEnabled(len(self._macro_actions) > 0)
        else:
            self._recording = True
            self._macro_actions = []
            self.record_btn.setText("⏹ 停止录制 (F8)")
            self.record_btn.setStyleSheet(f"background: {RED}; color: #1e1e2e;")
            show_info(self.root, "宏录制", "录制已开始，按 F8 或点击按钮停止")

    def _play_macro(self):
        """回放宏"""
        if not self._macro_actions:
            show_error(self.root, "宏回放", "没有录制的动作")
            return

        repeats = self.repeat_spin.value()
        self.macro_progress.show()

        def _play():
            for _ in range(repeats):
                for action in self._macro_actions:
                    # 实际回放逻辑在 modules/macro_recorder 中
                    pass

            QTimer.singleShot(0, self.macro_progress.hide)
            QTimer.singleShot(0, lambda: show_info(self.root, "宏回放", "回放完成"))

        threading.Thread(target=_play, daemon=True).start()

    # ═══ 定时任务卡片内容 ══════════════════════════════════════════════

    def _build_task_card(self, parent_layout):
        """向卡片内添加定时任务控件"""
        # 任务类型
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("类型:"))
        self.task_type = ComboBox()
        self.task_type.addItems(["命令", "应用程序", "脚本文件", "循环任务"])
        type_row.addWidget(self.task_type, stretch=1)
        parent_layout.addLayout(type_row)

        # 命令/路径
        self.task_command = LineEdit()
        self.task_command.setPlaceholderText("输入命令或选择文件...")
        parent_layout.addWidget(self.task_command)

        # 调度
        sched_row = QHBoxLayout()
        sched_row.addWidget(QLabel("间隔:"))
        self.task_interval = QSpinBox()
        self.task_interval.setRange(1, 1440)
        self.task_interval.setValue(30)
        self.task_interval.setSuffix(" 分钟")
        sched_row.addWidget(self.task_interval)
        sched_row.addStretch()

        add_btn = PrimaryPushButton("添加任务")
        add_btn.clicked.connect(self._add_scheduled_task)
        sched_row.addWidget(add_btn)
        parent_layout.addLayout(sched_row)

    def _add_scheduled_task(self):
        """添加定时任务"""
        ttype = self.task_type.currentText()
        cmd = self.task_command.text().strip()
        interval = self.task_interval.value()

        if not cmd:
            show_error(self.root, "定时任务", "请输入命令或路径")
            return

        try:
            if hasattr(self.controller, 'task_scheduler'):
                self.controller.task_scheduler.add_task(
                    name=f"{ttype}: {cmd[:30]}",
                    command=cmd,
                    interval_minutes=interval,
                    task_type=ttype,
                )
                show_info(self.root, "定时任务", f"已添加: {ttype} ({interval}分钟间隔)")
            else:
                show_info(self.root, "定时任务", "task_scheduler 未初始化")
        except Exception as e:
            show_error(self.root, "定时任务", str(e))

    # ═══ AI 智能体卡片内容 ═══════════════════════════════════════════

    def _build_agent_card(self, parent_layout):
        """向卡片内添加 AI 智能体控件"""
        desc = QLabel("输入自然语言指令，AI 自动分解执行。\n例：\"帮我整理桌面文件并按日期分类\"")
        desc.setStyleSheet(f"color: {SUBTEXT0}; font-size: 11px;")
        desc.setWordWrap(True)
        parent_layout.addWidget(desc)

        self.agent_input = LineEdit()
        self.agent_input.setPlaceholderText("描述你想让 AI 做的事情...")
        parent_layout.addWidget(self.agent_input)

        run_btn = PrimaryPushButton("🤖 执行")
        run_btn.clicked.connect(self._run_agent)
        parent_layout.addWidget(run_btn)

    def _run_agent(self):
        """运行 AI 智能体"""
        task = self.agent_input.text().strip()
        if not task:
            show_error(self.root, "AI 智能体", "请输入任务描述")
            return

        show_info(self.root, "AI 智能体", f"正在执行: {task}")

        def _execute():
            try:
                if hasattr(self.controller, 'ai_helper'):
                    result = self.controller.ai_helper.execute_task(task)
                    QTimer.singleShot(0, lambda: show_info(self.root, "AI 智能体", f"完成: {result}"))
                else:
                    QTimer.singleShot(0, lambda: show_info(self.root, "AI 智能体", "AI 助手未就绪"))
            except Exception as e:
                QTimer.singleShot(0, lambda: show_error(self.root, "AI 智能体", str(e)))

        threading.Thread(target=_execute, daemon=True).start()

    # ═══ 编程工作区卡片内容 ══════════════════════════════════════════════

    def _build_code_card(self, parent_layout):
        """向卡片内添加编程工作区控件"""
        self.code_input = TextEdit()
        self.code_input.setPlaceholderText("# 在此输入 Python 代码\nprint('Hello, AI管家!')")
        self.code_input.setFixedHeight(80)
        self.code_input.setAcceptRichText(False)
        parent_layout.addWidget(self.code_input)

        btn_row = QHBoxLayout()
        run_btn = PrimaryPushButton("▶ 运行")
        run_btn.clicked.connect(self._run_code)
        btn_row.addWidget(run_btn)

        clear_btn = PushButton("清空")
        clear_btn.clicked.connect(self.code_input.clear)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        parent_layout.addLayout(btn_row)

    def _run_code(self):
        """执行 Python 代码"""
        code = self.code_input.toPlainText().strip()
        if not code:
            show_error(self.root, "编程工作区", "请输入 Python 代码")
            return

        show_info(self.root, "编程工作区", "正在执行...")

        def _exec():
            import io, sys
            old_stdout = sys.stdout
            buf = io.StringIO()
            try:
                sys.stdout = buf
                exec(code, {"__builtins__": __builtins__})
                output = buf.getvalue()
                QTimer.singleShot(0, lambda: show_info(self.root, "编程工作区",
                                                        f"✅ 执行成功\n输出: {output}" if output else "✅ 执行成功（无输出）"))
            except Exception as e:
                QTimer.singleShot(0, lambda: show_error(self.root, "编程工作区", str(e)))
            finally:
                sys.stdout = old_stdout

        threading.Thread(target=_exec, daemon=True).start()
