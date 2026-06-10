"""
ChatPanel — 智能对话面板 (PyQt5 + Fluent 版)

功能：
- 左侧对话列表 + 右侧聊天区域
- 气泡式消息（用户蓝右 / AI 灰左）
- 代码块高亮
- 流式输出（逐 token 显示）
- DeepSeek / Hermes 双引擎切换
- 模型智能路由
"""

import logging
import threading
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFrame,
    QListWidget, QListWidgetItem, QTextEdit, QPushButton,
    QLabel, QSizePolicy, QScrollArea,
)
from PyQt5.QtGui import QFont, QTextCursor, QColor
from qfluentwidgets import (
    PushButton, PrimaryPushButton, PillPushButton, LineEdit,
    TextEdit, ComboBox, InfoBar, InfoBarPosition,
)

from modules.fluent_theme import (
    BG_PRIMARY, MANTLE, SURFACE0, SURFACE1, TEXT, SUBTEXT0,
    BLUE, GREEN, RED, YELLOW, PEACH, LAVENDER,
    RADIUS, RADIUS_LG, PADDING, PADDING_SM,
)

logger = logging.getLogger("ChatPanel")

# ═══════════════════════════════════════════════════════════════════════
# 消息气泡组件
# ═══════════════════════════════════════════════════════════════════════

class MessageBubble(QFrame):
    """聊天消息气泡 — 用户蓝色靠右 / AI 灰色靠左"""

    BUBBLE_USER = "#89b4fa"
    BUBBLE_AI = "#45475a"

    def __init__(self, text, sender="user", timestamp=None, parent=None):
        super().__init__(parent)
        self.setObjectName("msg-bubble")
        self.sender = sender
        is_user = sender == "user"
        bubble_color = self.BUBBLE_USER if is_user else self.BUBBLE_AI
        text_color = "#1e1e2e" if is_user else "#cdd6f4"
        align = Qt.AlignRight if is_user else Qt.AlignLeft

        # 外层布局
        outer = QVBoxLayout(self)
        outer.setContentsMargins(PADDING, 4, PADDING, 4)

        # 气泡容器
        bubble = QFrame()
        bubble.setObjectName("bubble")
        bubble.setStyleSheet(f"""
            #bubble {{
                background: {bubble_color};
                border-radius: {RADIUS_LG}px;
                padding: {PADDING_SM + 2}px {PADDING}px;
            }}
        """)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        bubble.setMaximumWidth(600)

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(PADDING, PADDING_SM, PADDING, PADDING_SM)
        bubble_layout.setSpacing(2)

        # 时间标签
        if timestamp:
            ts_label = QLabel(timestamp.strftime("%H:%M") if timestamp else "")
            ts_label.setStyleSheet(f"color: {text_color}99; font-size: 10px;")
            ts_label.setAlignment(Qt.AlignRight if is_user else Qt.AlignLeft)
            bubble_layout.addWidget(ts_label)

        # 消息文本
        self.content = QTextEdit()
        self.content.setReadOnly(True)
        self.content.setFrameShape(QTextEdit.Shape.NoFrame)
        self.content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {text_color};
                border: none;
                padding: 2px;
                font-size: 13px;
            }}
        """)

        # 设置 Markdown 渲染的 HTML
        rendered = _render_markdown(text)
        self.content.setHtml(rendered)

        # 自适应高度
        self.content.document().setDocumentMargin(4)
        self.content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        doc_h = int(self.content.document().size().height()) + 8
        self.content.setFixedHeight(min(doc_h, 500))

        bubble_layout.addWidget(self.content)

        # 对齐
        row = QHBoxLayout()
        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()
        outer.addLayout(row)

    def append_text(self, text):
        """追加文本（流式输出用）"""
        cursor = self.content.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.content.setTextCursor(cursor)
        # 更新高度
        doc_h = int(self.content.document().size().height()) + 8
        self.content.setFixedHeight(min(doc_h, 500))


# ═══════════════════════════════════════════════════════════════════════
# 对话列表项
# ═══════════════════════════════════════════════════════════════════════

class ConversationItem(QFrame):
    """对话列表条目"""

    clicked = pyqtSignal(str)  # conversation_id

    def __init__(self, conv_id, title, preview="", parent=None):
        super().__init__(parent)
        self.setObjectName("conv-item")
        self.conv_id = conv_id
        self.setStyleSheet(f"""
            #conv-item {{
                background: transparent;
                border-radius: {RADIUS}px;
                padding: {PADDING_SM}px {PADDING}px;
            }}
            #conv-item:hover {{
                background: {SURFACE1};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING_SM, PADDING_SM, PADDING_SM, PADDING_SM)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.title_label)

        if preview:
            p = QLabel(preview[:50])
            p.setStyleSheet(f"color: {SUBTEXT0}; font-size: 11px;")
            p.setWordWrap(True)
            layout.addWidget(p)

    def mousePressEvent(self, event):
        self.clicked.emit(self.conv_id)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════
# 简单 Markdown 渲染
# ═══════════════════════════════════════════════════════════════════════

def _render_markdown(text: str) -> str:
    """将 Markdown 文本转为 HTML（轻量级）"""
    import re

    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 代码块 ```...```
    def code_block_repl(m):
        code = m.group(1)
        return f'<pre style="background:#313244;color:#cdd6f4;padding:8px;border-radius:6px;font-family:Consolas,monospace;font-size:12px;overflow-x:auto;">{code}</pre>'
    html = re.sub(r'```(.*?)```', code_block_repl, html, flags=re.DOTALL)

    # 行内代码 `...`
    html = re.sub(r'`([^`]+)`', r'<code style="background:#313244;color:#f9e2af;padding:1px 4px;border-radius:3px;font-family:Consolas,monospace;">\1</code>', html)

    # 粗体 **...**
    html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)

    # 斜体 *...*
    html = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', html)

    # 换行
    html = html.replace("\n", "<br>")

    return html


# ═══════════════════════════════════════════════════════════════════════
# ChatPanel 主类
# ═══════════════════════════════════════════════════════════════════════

class ChatPanel(QWidget):
    """智能对话面板"""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.root = parent

        self._conversations = {}  # id -> {title, messages, ...}
        self._current_conv_id = None
        self._current_model = "ds-v4-flash"
        self._streaming = False
        self._stream_bubble = None

        self._build_ui()
        self._new_conversation()

    # ═══ UI 构建 ══════════════════════════════════════════════════════

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 分割器 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {SURFACE1}; width: 1px; }}")

        # 左侧：对话列表
        left = self._build_sidebar()
        splitter.addWidget(left)

        # 右侧：聊天区
        right = self._build_chat_area()
        splitter.addWidget(right)

        splitter.setSizes([220, 780])
        layout.addWidget(splitter)

    def _build_sidebar(self) -> QWidget:
        """构建对话列表侧栏"""
        sidebar = QWidget()
        sidebar.setObjectName("chat-sidebar")
        sidebar.setStyleSheet(f"""
            #chat-sidebar {{
                background: {MANTLE};
                border-radius: 0;
            }}
        """)
        sidebar.setMinimumWidth(180)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(PADDING_SM, PADDING_SM, PADDING_SM, PADDING_SM)
        layout.setSpacing(PADDING_SM)

        # 新建对话按钮
        new_btn = PrimaryPushButton("+ 新对话")
        new_btn.clicked.connect(self._new_conversation)
        layout.addWidget(new_btn)

        # 对话列表
        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                padding: 4px;
            }}
        """)
        layout.addWidget(self.conv_list)

        return sidebar

    def _build_chat_area(self) -> QWidget:
        """构建聊天区域"""
        chat_area = QWidget()
        layout = QVBoxLayout(chat_area)
        layout.setContentsMargins(PADDING_SM, PADDING_SM, PADDING_SM, PADDING_SM)
        layout.setSpacing(PADDING_SM)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(PADDING_SM)

        # 模型选择器
        self.model_combo = ComboBox()
        self.model_combo.addItems([
            "🔵 DeepSeek V4 Flash · 快速",
            "🟣 DeepSeek V4 Flash · 深度",
            "🟢 DeepSeek V4 Pro · 通用",
            "🔴 DeepSeek V4 Pro · 推理",
            "🟡 Hermes (WSL)",
        ])
        self.model_combo.setCurrentIndex(0)
        self.model_combo.setMinimumWidth(220)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        toolbar.addWidget(self.model_combo)

        toolbar.addStretch()

        # 清空对话
        clear_btn = PushButton("清空对话")
        clear_btn.clicked.connect(self._clear_chat)
        toolbar.addWidget(clear_btn)

        layout.addLayout(toolbar)

        # ── 聊天消息区域（滚动） ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {BG_PRIMARY};
                border: none;
            }}
        """)

        self.msg_container = QWidget()
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(PADDING, PADDING, PADDING, 0)
        self.msg_layout.setSpacing(4)
        self.msg_layout.addStretch()

        scroll.setWidget(self.msg_container)
        layout.addWidget(scroll, stretch=1)

        # ── 输入区域 ──
        input_row = QHBoxLayout()
        input_row.setSpacing(PADDING_SM)

        self.input_box = TextEdit()
        self.input_box.setPlaceholderText("输入消息... (Shift+Enter 换行, Enter 发送)")
        self.input_box.setFixedHeight(72)
        self.input_box.setAcceptRichText(False)
        self.input_box.installEventFilter(self)
        input_row.addWidget(self.input_box, stretch=1)

        self.send_btn = PrimaryPushButton("↵ 发送")
        self.send_btn.setFixedHeight(72)
        self.send_btn.setFixedWidth(80)
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        layout.addLayout(input_row)

        return chat_area

    # ═══ 事件处理 ══════════════════════════════════════════════════════

    def eventFilter(self, obj, event):
        """拦截输入框按键"""
        from PyQt5.QtCore import QEvent
        if obj == self.input_box and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # Shift+Enter → 换行
                    return False
                else:
                    # Enter → 发送
                    self._send_message()
                    return True
        return super().eventFilter(obj, event)

    # ═══ 对话管理 ══════════════════════════════════════════════════════

    def _new_conversation(self):
        """新建对话"""
        import uuid
        conv_id = str(uuid.uuid4())[:8]
        self._conversations[conv_id] = {
            "id": conv_id,
            "title": "新对话",
            "messages": [],
            "created": datetime.now(),
        }
        self._current_conv_id = conv_id

        # 添加到列表
        item = QListWidgetItem()
        widget = ConversationItem(conv_id, "新对话", preview="")
        widget.clicked.connect(self._switch_conversation)
        item.setSizeHint(widget.sizeHint())
        self.conv_list.insertItem(0, item)
        self.conv_list.setItemWidget(item, widget)
        self.conv_list.setCurrentRow(0)

        # 清空聊天区
        self._clear_chat_display()

    def _switch_conversation(self, conv_id):
        """切换对话"""
        if conv_id == self._current_conv_id:
            return
        self._current_conv_id = conv_id

        # 重建聊天显示
        self._clear_chat_display()
        conv = self._conversations.get(conv_id)
        if conv:
            for msg in conv.get("messages", []):
                bubble = MessageBubble(
                    msg["content"],
                    sender=msg["role"],
                    timestamp=msg.get("time"),
                    parent=self.msg_container,
                )
                self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)

    def _clear_chat_display(self):
        """清空聊天消息显示"""
        # 移除所有气泡（保留 stretch）
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_chat(self):
        """清空当前对话"""
        conv = self._conversations.get(self._current_conv_id)
        if conv:
            conv["messages"] = []
        self._clear_chat_display()

    # ═══ 模型切换 ══════════════════════════════════════════════════════

    def _on_model_changed(self, index):
        """模型选择变更"""
        model_map = {
            0: "ds-v4-flash",
            1: "ds-v4-flash-r",
            2: "ds-v4-pro",
            3: "ds-v4-pro-r",
            4: "hermes",
        }
        self._current_model = model_map.get(index, "ds-v4-flash")

    # ═══ 发送消息 ══════════════════════════════════════════════════════

    def _send_message(self):
        """发送消息"""
        text = self.input_box.toPlainText().strip()
        if not text or self._streaming:
            return
        self.input_box.clear()

        now = datetime.now()

        # 更新对话标题
        conv = self._conversations.get(self._current_conv_id)
        if conv:
            conv["title"] = text[:20] + ("..." if len(text) > 20 else "")
            conv["messages"].append({
                "role": "user", "content": text, "time": now,
            })

        # 显示用户气泡
        user_bubble = MessageBubble(text, sender="user", timestamp=now, parent=self.msg_container)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, user_bubble)
        self._scroll_to_bottom()

        # 创建 AI 气泡（占位）
        ai_bubble = MessageBubble("思考中...", sender="ai", timestamp=datetime.now(), parent=self.msg_container)
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, ai_bubble)

        # 调用 AI
        if self._current_model == "hermes":
            self._call_hermes(text, ai_bubble, conv)
        else:
            self._call_deepseek(text, ai_bubble, conv)

    def _call_deepseek(self, prompt, bubble, conv):
        """调用 DeepSeek API"""
        self._streaming = True
        self.send_btn.setEnabled(False)

        from services.deepseek_client import get_deepseek_client
        client = get_deepseek_client()

        messages = [{"role": m["role"], "content": m["content"]}
                     for m in (conv.get("messages", [])[:-1] or [])]  # 去掉刚加的 user
        if not messages:
            messages = [{"role": "user", "content": prompt}]
        else:
            messages.append({"role": "user", "content": prompt})

        full_text = []

        def _on_token(token):
            full_text.append(token)
            # 线程安全更新 UI
            def _update():
                bubble.append_text(token)
                self._scroll_to_bottom()
            # 使用 invokeMethod 或直接通过信号
            QTimer.singleShot(0, _update)

        def _task(callback, cancel):
            return client.chat(messages, stream_callback=callback)

        def _run():
            try:
                result = client.chat(messages, stream_callback=_on_token)
                text = "".join(full_text) if full_text else result

                def _done():
                    self._streaming = False
                    self.send_btn.setEnabled(True)
                    if conv:
                        conv["messages"].append({
                            "role": "assistant", "content": text, "time": datetime.now(),
                        })
                    self._scroll_to_bottom()
                QTimer.singleShot(0, _done)

            except Exception as e:
                def _err():
                    self._streaming = False
                    self.send_btn.setEnabled(True)
                    bubble.append_text(f"\n\n❌ 错误: {e}")
                QTimer.singleShot(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    def _call_hermes(self, prompt, bubble, conv):
        """调用 Hermes (WSL)"""
        self._streaming = True
        self.send_btn.setEnabled(False)

        full_text = []

        def _on_token(token):
            full_text.append(token)
            def _update():
                bubble.append_text(token)
                self._scroll_to_bottom()
            QTimer.singleShot(0, _update)

        def _run():
            try:
                from services.agent_service import AgentService
                svc = AgentService(hermes_service=None, config_manager=self.controller.get_config())
                result = svc.chat(prompt, stream_callback=_on_token)
                text = result or "".join(full_text)

                def _done():
                    self._streaming = False
                    self.send_btn.setEnabled(True)
                    if conv:
                        conv["messages"].append({
                            "role": "assistant", "content": text, "time": datetime.now(),
                        })
                QTimer.singleShot(0, _done)

            except Exception as e:
                def _err():
                    self._streaming = False
                    self.send_btn.setEnabled(True)
                    bubble.append_text(f"\n\n❌ Hermes 错误: {e}")
                QTimer.singleShot(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    def _scroll_to_bottom(self):
        """滚动到底部"""
        # 找到 QScrollArea 并滚动
        scroll = self.findChild(QScrollArea)
        if scroll:
            vbar = scroll.verticalScrollBar()
            vbar.setValue(vbar.maximum())
