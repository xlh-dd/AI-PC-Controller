import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, ttk, filedialog
import threading
import logging
import traceback
import os
import re
from datetime import datetime

logger = logging.getLogger("ChatPanel")

# Catppuccin Mocha 配色(与 main.py 保持一致)
CATPPUCCIN = {
    "base":       "#1e1e2e",
    "mantle":     "#181825",
    "crust":      "#11111b",
    "surface0":   "#313244",
    "surface1":   "#45475a",
    "surface2":   "#585b70",
    "overlay0":   "#6c7086",
    "overlay1":   "#7f849c",
    "text":       "#cdd6f4",
    "subtext0":   "#a6adc8",
    "subtext1":   "#bac2de",
    "blue":       "#89b4fa",
    "blue_dim":   "#2a3a5c",
    "green":      "#a6e3a1",
    "green_dim":  "#2a3a2c",
    "red":        "#f38ba8",
    "yellow":     "#f9e2af",
    "mauve":      "#cba6f7",
    "peach":      "#fab387",
    "teal":       "#94e2d5",
    "sky":        "#89dceb",
    "lavender":   "#b4befe",
}


class ChatPanel:
    """智能对话面板 - 左侧对话列表 + 右侧聊天区(气泡样式)"""

    MODEL_DISPLAY_MAP = {
        "DeepSeek V4 Flash · 快速": "ds-v4-flash",
        "DeepSeek V4 Flash · 深度": "ds-v4-flash-r",
        "DeepSeek V4 Pro · 通用": "ds-v4-pro",
        "DeepSeek V4 Pro · 推理": "ds-v4-pro-r",
    }
    MODEL_ID_TO_DISPLAY = {v: k for k, v in MODEL_DISPLAY_MAP.items()}

    def __init__(self, parent: tk.Widget, controller):
        """构建智能对话标签页

        Args:
            parent: 父容器(tk.Widget)
            controller: AppController / AIPCHelperV8 主控制器实例
        """
        self.parent = parent
        self.controller = controller
        self._streaming_manager = None
        self._bubble_tags_configured = False

        from services.conversation_manager import get_conversation_manager
        self._conv_mgr = get_conversation_manager()

        self._build_chat_tab()

    # ─── 标签页构建 ──────────────────────────────────────────

    def _build_chat_tab(self):
        """构建智能对话标签页 - 左侧对话列表 + 右侧聊天区"""
        base = CATPPUCCIN
        ctrl = self.controller

        self.chat_paned = tk.PanedWindow(
            self.parent, orient=tk.HORIZONTAL, sashwidth=3,
            bg=base["surface1"], sashrelief=tk.FLAT
        )
        self.chat_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # ── 左侧对话列表 ──
        self.conv_panel = tk.Frame(self.chat_paned, bg=base["mantle"])
        self._build_conversation_sidebar()
        self.chat_paned.add(self.conv_panel, minsize=160, stretch="never")

        # ── 右侧聊天区 ──
        self.chat_right = tk.Frame(self.chat_paned, bg=base["base"])
        self.chat_paned.add(self.chat_right, minsize=300, stretch="always")

        # 聊天显示区(气泡式)
        self.chat = scrolledtext.ScrolledText(
            self.chat_right, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 10), bg=base["base"], fg=base["text"],
            relief=tk.FLAT, padx=12, pady=8,
            insertbackground=base["text"],
            selectbackground=base["surface1"],
            selectforeground=base["text"],
            spacing1=2, spacing3=2,
        )
        self.chat.pack(fill=tk.BOTH, expand=True)
        self._configure_chat_tags()

        # ── 多行输入框 ──
        input_outer = tk.Frame(self.chat_right, bg=base["base"])
        input_outer.pack(fill=tk.X, padx=6, pady=(2, 4))

        input_frame = tk.Frame(input_outer, bg=base["surface0"],
                               highlightbackground=base["surface1"],
                               highlightthickness=1)
        input_frame.pack(fill=tk.X)

        self.input_text = tk.Text(
            input_frame, font=("微软雅黑", 10),
            bg=base["surface0"], fg=base["text"],
            insertbackground=base["text"],
            relief=tk.FLAT, height=3, padx=8, pady=6,
            selectbackground=base["surface1"],
            selectforeground=base["text"],
            wrap=tk.WORD,
        )
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self.input_text.bind("<Return>", self._on_input_return)
        self.input_text.bind("<Shift-Return>", self._on_input_shift_return)
        self.input_text.focus()

        btn_col = tk.Frame(input_frame, bg=base["surface0"])
        btn_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)

        self.send_btn = tk.Button(
            btn_col, text="🚀 发送", font=("微软雅黑", 9, "bold"),
            bg=base["blue"], fg=base["base"],
            activebackground=base["sky"], activeforeground=base["base"],
            relief=tk.FLAT, cursor="hand2", padx=10, pady=4,
            command=self.send_msg,
        )
        self.send_btn.pack(pady=(0, 2))

        self.cancel_btn = tk.Button(
            btn_col, text="⏹ 停止", font=("微软雅黑", 9),
            bg=base["red"], fg=base["base"],
            activebackground=base["peach"], activeforeground=base["base"],
            relief=tk.FLAT, cursor="hand2", padx=10, pady=4,
            command=self._cancel_stream,
        )

        # ── 引擎控制区(Chip 风格) ──
        self._build_engine_controls()

        # ── 底部操作条 ──
        self._build_action_bar()

        # 快捷键
        self.controller.root.bind("<Control-n>", lambda e: self._new_conversation_named())
        self.controller.root.bind("<Control-N>", lambda e: self._new_conversation_named())

        self._load_active_conversation()

    def _configure_chat_tags(self):
        """配置聊天区文本标签(气泡样式)"""
        base = CATPPUCCIN
        self.chat.tag_configure("timestamp",
            foreground=base["overlay0"], font=("微软雅黑", 8),
            justify=tk.RIGHT,
        )
        self.chat.tag_configure("user_name",
            foreground=base["blue"], font=("微软雅黑", 9, "bold"),
            justify=tk.RIGHT,
        )
        self.chat.tag_configure("user_text",
            foreground=base["blue"], font=("微软雅黑", 10),
            lmargin1=80, lmargin2=80, rmargin=12,
            justify=tk.RIGHT,
        )
        self.chat.tag_configure("ai_name",
            foreground=base["green"], font=("微软雅黑", 9, "bold"),
        )
        self.chat.tag_configure("ai_text",
            foreground=base["text"], font=("微软雅黑", 10),
            lmargin1=12, lmargin2=20, rmargin=80,
        )
        self.chat.tag_configure("code_block",
            background=base["crust"], foreground=base["green"],
            font=("Cascadia Code", 9) if self._font_exists("Cascadia Code") else ("Consolas", 9),
            lmargin1=20, lmargin2=20, rmargin=20,
            spacing1=6, spacing3=6,
            relief=tk.FLAT, borderwidth=0,
        )
        self.chat.tag_configure("separator",
            foreground=base["surface1"], font=("微软雅黑", 7),
            justify=tk.CENTER,
        )
        self.chat.tag_configure("system_name",
            foreground=base["yellow"], font=("微软雅黑", 9, "bold"),
        )
        self.chat.tag_configure("system_text",
            foreground=base["subtext0"], font=("微软雅黑", 9),
            lmargin1=12, lmargin2=20,
        )
        self._bubble_tags_configured = True

    @staticmethod
    def _font_exists(font_name):
        try:
            import tkinter.font as tkfont
            root = tk._default_root
            if root:
                return font_name in tkfont.families(root)
        except Exception:
            pass
        return False

    def _on_input_return(self, event=None):
        """Enter 发送消息"""
        self.send_msg()
        return "break"

    def _on_input_shift_return(self, event=None):
        """Shift+Enter 换行(默认行为)"""
        return None

    # ─── 引擎控制区(Chip 风格) ─────────────────────────────

    def _build_engine_controls(self):
        """构建引擎控制区 - Chip/Badge 风格"""
        base = CATPPUCCIN
        ctrl = self.controller

        engine_frame = tk.Frame(self.chat_right, bg=base["mantle"],
                                highlightbackground=base["surface0"],
                                highlightthickness=1)
        engine_frame.pack(fill=tk.X, padx=6, pady=(0, 2))

        # 左侧 chip 按钮
        chips_frame = tk.Frame(engine_frame, bg=base["mantle"])
        chips_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=4)

        self.hermes_toggle_var = tk.BooleanVar(value=getattr(ctrl, 'use_hermes', False))
        self.hermes_toggle_btn = tk.Button(
            chips_frame, text="🤖 Hermes", font=("微软雅黑", 8, "bold"),
            bg=base["surface0"], fg=base["overlay0"],
            activebackground=base["surface1"], activeforeground=base["text"],
            relief=tk.FLAT, cursor="hand2", padx=10, pady=2,
            command=self._toggle_hermes_switch,
        )
        self.hermes_toggle_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.model_var = tk.StringVar(value="DeepSeek V4 Flash · 快速")
        self.model_combo = ttk.Combobox(
            chips_frame, textvariable=self.model_var,
            values=[
                "DeepSeek V4 Flash · 快速",
                "DeepSeek V4 Flash · 深度",
                "DeepSeek V4 Pro · 通用",
                "DeepSeek V4 Pro · 推理",
            ],
            state="readonly", width=22, font=("微软雅黑", 8),
        )
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)
        self.model_combo.pack(side=tk.LEFT, padx=4)

        self.auto_switch_var = tk.BooleanVar(value=True)
        self.auto_switch_btn = tk.Button(
            chips_frame, text="🔄 自动", font=("微软雅黑", 8, "bold"),
            bg=base["green_dim"], fg=base["green"],
            activebackground=base["surface1"], activeforeground=base["green"],
            relief=tk.FLAT, cursor="hand2", padx=8, pady=2,
            command=self._toggle_auto_switch,
        )
        self.auto_switch_btn.pack(side=tk.LEFT, padx=4)

        # 右侧设置按钮
        settings_btn = tk.Button(
            engine_frame, text="⚙️", font=("Segoe UI Emoji", 10),
            bg=base["mantle"], fg=base["overlay0"],
            activebackground=base["surface0"], activeforeground=base["text"],
            relief=tk.FLAT, cursor="hand2", padx=6, pady=2,
            command=ctrl.ai_settings,
        )
        settings_btn.pack(side=tk.RIGHT, padx=6, pady=4)

        self._update_hermes_toggle_ui()

    def _build_action_bar(self):
        """底部操作条"""
        base = CATPPUCCIN
        ctrl = self.controller

        action_frame = tk.Frame(self.chat_right, bg=base["base"])
        action_frame.pack(fill=tk.X, padx=6, pady=(0, 3))

        clear_btn = tk.Button(
            action_frame, text="🗑️ 清空", font=("微软雅黑", 8),
            bg=base["surface0"], fg=base["overlay0"],
            activebackground=base["surface1"], activeforeground=base["text"],
            relief=tk.FLAT, cursor="hand2", padx=8, pady=1,
            command=self._clear_chat_display,
        )
        clear_btn.pack(side=tk.LEFT, padx=(0, 4))

        help_btn = tk.Button(
            action_frame, text="❓ 帮助", font=("微软雅黑", 8),
            bg=base["surface0"], fg=base["overlay0"],
            activebackground=base["surface1"], activeforeground=base["text"],
            relief=tk.FLAT, cursor="hand2", padx=8, pady=1,
            command=ctrl.show_help,
        )
        help_btn.pack(side=tk.RIGHT, padx=4)

        self._history_label = tk.Label(
            action_frame, text="💬 新对话", font=("微软雅黑", 8),
            bg=base["base"], fg=base["overlay0"],
        )
        self._history_label.pack(side=tk.RIGHT, padx=8)

    # ─── 对话列表侧边栏 ────────────────────────────────────

    def _build_conversation_sidebar(self):
        """构建对话列表侧边栏"""
        base = CATPPUCCIN
        panel = self.conv_panel

        header = tk.Frame(panel, bg=base["mantle"])
        header.pack(fill=tk.X, pady=4, padx=4)
        tk.Label(header, text="💬 对话", font=("微软雅黑", 10, "bold"),
                 bg=base["mantle"], fg=base["text"], anchor="w").pack(side=tk.LEFT, padx=4)
        tk.Button(header, text="≡", font=("微软雅黑", 9),
                  bg=base["mantle"], fg=base["overlay0"],
                  activebackground=base["surface0"], activeforeground=base["text"],
                  relief=tk.FLAT, cursor="hand2", padx=4,
                  command=self._toggle_conv_sidebar).pack(side=tk.RIGHT, padx=4)

        list_frame = tk.Frame(panel, bg=base["mantle"])
        list_frame.pack(fill=tk.BOTH, expand=True, pady=2, padx=4)

        self.conv_listbox = tk.Listbox(
            list_frame, font=("微软雅黑", 9),
            bg=base["crust"], fg=base["text"],
            selectbackground=base["blue_dim"], selectforeground=base["blue"],
            highlightthickness=0, bd=0,
            relief=tk.FLAT, activestyle="none",
            spacing1=4, spacing3=4,
        )
        self.conv_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.conv_listbox.bind("<<ListboxSelect>>", self._on_conv_selected)
        self.conv_listbox.bind("<Double-Button-1>", lambda e: self._rename_conversation())
        self.conv_listbox.bind("<Button-3>", self._on_conv_right_click)
        # Hover 效果
        self.conv_listbox.bind("<Motion>", self._on_conv_hover)
        self.conv_listbox.bind("<Leave>", self._on_conv_leave)
        self._hover_idx = -1

        v_scroll = tk.Scrollbar(list_frame, command=self.conv_listbox.yview,
                                bg=base["surface0"], troughcolor=base["crust"])
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.conv_listbox.config(yscrollcommand=v_scroll.set)

        btn_frame = tk.Frame(panel, bg=base["mantle"])
        btn_frame.pack(fill=tk.X, pady=4, padx=4)
        tk.Button(btn_frame, text="+ 新建", font=("微软雅黑", 8),
                  bg=base["surface0"], fg=base["text"],
                  activebackground=base["surface1"], activeforeground=base["text"],
                  relief=tk.FLAT, cursor="hand2", padx=8, pady=2,
                  command=self._new_conversation).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="🗑", font=("微软雅黑", 8),
                  bg=base["surface0"], fg=base["overlay0"],
                  activebackground=base["surface1"], activeforeground=base["text"],
                  relief=tk.FLAT, cursor="hand2", padx=6, pady=2,
                  command=self._delete_conversation).pack(side=tk.RIGHT, padx=2)

        tip_label = tk.Label(panel, text="Ctrl+N 命名新建", font=("微软雅黑", 7),
                             bg=base["mantle"], fg=base["overlay0"])
        tip_label.pack(side=tk.BOTTOM, pady=(0, 4))

        self._refresh_conv_listbox()

    def _on_conv_hover(self, event):
        idx = self.conv_listbox.nearest(event.y)
        if idx != self._hover_idx:
            if self._hover_idx >= 0:
                try:
                    self.conv_listbox.itemconfig(self._hover_idx, bg=CATPPUCCIN["crust"])
                except Exception:
                    pass
            if idx >= 0:
                try:
                    self.conv_listbox.itemconfig(idx, bg=CATPPUCCIN["surface0"])
                except Exception:
                    pass
            self._hover_idx = idx

    def _on_conv_leave(self, event):
        if self._hover_idx >= 0:
            try:
                self.conv_listbox.itemconfig(self._hover_idx, bg=CATPPUCCIN["crust"])
            except Exception:
                pass
            self._hover_idx = -1

    # ─── 气泡式消息渲染 ────────────────────────────────────

    def _render_message(self, who, what, timestamp=""):
        """在聊天区渲染气泡消息"""
        base = CATPPUCCIN
        chat = self.chat
        chat.config(state=tk.NORMAL)

        ts = timestamp or datetime.now().strftime("%H:%M")
        is_user = who in ("user", "你", "我")
        is_system = who in ("系统", "AI管家")

        if is_user:
            chat.insert(tk.END, f"     {ts}\n", "timestamp")
            chat.insert(tk.END, f"            👤 你\n", "user_name")
            parts = self._split_code_blocks(what)
            for ptype, ptext in parts:
                if ptype == "code":
                    chat.insert(tk.END, f"  {ptext.strip()}\n", "code_block")
                else:
                    chat.insert(tk.END, f"{ptext}", "user_text")
            chat.insert(tk.END, "\n")
        elif is_system:
            chat.insert(tk.END, f"⚙️ {who}  {ts}\n", "system_name")
            chat.insert(tk.END, f"  {what}\n", "system_text")
        else:
            chat.insert(tk.END, f"{ts}\n", "timestamp")
            chat.insert(tk.END, f"🤖 AI\n", "ai_name")
            parts = self._split_code_blocks(what)
            for ptype, ptext in parts:
                if ptype == "code":
                    chat.insert(tk.END, f"  {ptext.strip()}\n", "code_block")
                else:
                    chat.insert(tk.END, f"{ptext}", "ai_text")
            chat.insert(tk.END, "\n")

        chat.insert(tk.END, "  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n", "separator")
        chat.config(state=tk.DISABLED)
        chat.see(tk.END)

    def _split_code_blocks(self, text):
        """将消息拆分为 (type, content) 列表"""
        pattern = r'(```[\s\S]*?```|`[^`\n]+`)'
        parts = []
        last = 0
        for m in re.finditer(pattern, text):
            if m.start() > last:
                parts.append(("text", text[last:m.start()]))
            code = m.group(0)
            if code.startswith("```"):
                lines = code.split("\n")
                if len(lines) > 2:
                    code_body = "\n".join(lines[1:-1])
                elif len(lines) == 2:
                    code_body = lines[1].rstrip("`")
                else:
                    code_body = code[3:].rstrip("`")
                parts.append(("code", code_body))
            else:
                parts.append(("code", code[1:-1]))
            last = m.end()
        if last < len(text):
            parts.append(("text", text[last:]))
        if not parts:
            parts.append(("text", text))
        return parts

    # ─── 对话列表操作 ──────────────────────────────────────

    def _refresh_conv_listbox(self):
        self.conv_listbox.delete(0, tk.END)
        convs = self._conv_mgr.list_conversations()
        for conv in convs:
            title = conv.title or "新对话"
            count = len([m for m in conv.messages if m.get("role") == "user"])
            display = f"  {title}  [{count}]"
            self.conv_listbox.insert(tk.END, display)
        active = self._conv_mgr.active_id
        if active:
            convs = self._conv_mgr.list_conversations()
            for i, c in enumerate(convs):
                if c.id == active:
                    self.conv_listbox.selection_set(i)
                    self.conv_listbox.see(i)
                    break

    def _on_conv_selected(self, event=None):
        sel = self.conv_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        convs = self._conv_mgr.list_conversations()
        if idx < len(convs):
            conv = convs[idx]
            self._conv_mgr.switch_to(conv.id)
            self._load_active_conversation()
            self._update_conv_label()
            self._refresh_conv_listbox()

    def _new_conversation(self):
        conv = self._conv_mgr.create()
        self._conv_mgr.switch_to(conv.id)
        self._clear_chat_display()
        self._refresh_conv_listbox()
        self._update_conv_label()

    def _new_conversation_named(self):
        title = simpledialog.askstring(
            "新建对话", "请输入对话名称（留空自动命名）:",
            parent=self.controller.root
        )
        if title is None:
            return
        title = title.strip() or "新对话"
        conv = self._conv_mgr.create(title=title)
        self._conv_mgr.switch_to(conv.id)
        self._clear_chat_display()
        self._refresh_conv_listbox()
        self._update_conv_label()
        self.controller.say("系统", f"✅ 新建对话「{title}」")

    def _delete_conversation(self):
        active = self._conv_mgr.active_id
        if not active:
            return
        if len(self._conv_mgr.list_conversations()) <= 1:
            self.controller.say("系统", "⚠️ 至少保留一个对话")
            return
        if not messagebox.askyesno("确认删除", "确定要删除这个对话吗？此操作不可撤销！"):
            return
        self._conv_mgr.delete(active)
        convs = self._conv_mgr.list_conversations()
        if convs:
            self._conv_mgr.switch_to(convs[0].id)
        self._load_active_conversation()
        self._refresh_conv_listbox()
        self._update_conv_label()

    def _rename_conversation(self):
        active = self._conv_mgr.active_id
        conv = self._conv_mgr.get(active)
        if not conv:
            return
        new_title = simpledialog.askstring("重命名", "输入新标题:", initialvalue=conv.title or "")
        if new_title:
            self._conv_mgr.rename(active, new_title)
            self._refresh_conv_listbox()
            self._update_conv_label()

    def _toggle_conv_sidebar(self):
        try:
            x, _ = self.chat_paned.sash_coord(0)
            if x < 10:
                self.chat_paned.sash_place(0, 200, 0)
            else:
                self.chat_paned.sash_place(0, 0, 0)
        except Exception:
            pass

    def _load_active_conversation(self):
        self._clear_chat_display()
        conv = self._conv_mgr.active
        if conv and conv.messages:
            for msg in conv.messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    self._render_message("你", content)
                elif role == "assistant":
                    self._render_message("AI", content)
        self._update_conv_label()

    def _update_conv_label(self):
        conv = self._conv_mgr.active
        if conv:
            base = CATPPUCCIN
            self._history_label.config(text=f"💬 {conv.title[:15]}", fg=base["overlay0"])

    def _clear_chat_display(self):
        self.chat.config(state=tk.NORMAL)
        self.chat.delete(1.0, tk.END)
        self.chat.config(state=tk.DISABLED)

    def _get_active_conversation(self):
        return self._conv_mgr.active

    def say(self, who, what):
        self.controller.say(who, what)

    # ─── 任务分类 ──────────────────────────────────────────

    def _classify_task(self, msg: str):
        msg_lower = msg.lower()
        result = {
            'type': 'chat', 'complexity': 'simple',
            'model': 'ds-v4-flash', 'timeout': 180,
            'reasoning': '默认对话'
        }

        if len(msg) < 10:
            trivial = ['help', '帮助', 'status', '状态', 'clear', 'cls', 'hi', '你好', 'hello', '在吗']
            if any(k in msg_lower for k in trivial):
                result.update(type='system', complexity='trivial', timeout=60, reasoning='问候/系统 → Flash')
                return result
            result['reasoning'] = '短消息 → Flash 默认'
            return result

        code_kw = ['写', '生成代码', '代码', '函数', 'def ', 'class ', '实现', '修复bug',
                   'fix bug', 'debug', '重构', 'review', '审查', '爬虫', 'scraper',
                   '算法', '数据结构', '生成一个', '帮我写', '接口', 'api']
        if any(k in msg_lower for k in code_kw):
            complex_ind = ['重构', '架构', '系统设计', '大规模', '分布式',
                          '多线程', '并发', '全栈', '完整']
            if any(k in msg_lower for k in complex_ind) or len(msg) > 200:
                result.update(type='code', complexity='complex', model='ds-v4-pro',
                              timeout=600, reasoning='复杂代码/架构 → V4 Pro')
            else:
                result.update(type='code', complexity='moderate', model='ds-v4-pro',
                              timeout=300, reasoning='代码生成 → V4 Pro')
            return result

        search_kw = ['搜索', '查询', '查找', '怎么', '如何', '为什么', '什么是',
                    '定义', '区别', '对比', '有哪些', '介绍一下']
        if any(k in msg_lower for k in search_kw):
            result.update(type='search', model='ds-v4-flash', reasoning='搜索查询 → Flash')
            return result

        analysis_kw = ['分析', '诊断', '审核', '评估', '总结', '摘要', '深入分析']
        if any(k in msg_lower for k in analysis_kw):
            result.update(type='analysis', complexity='moderate', model='ds-v4-flash-r',
                          reasoning='分析任务 → Flash 深度思考')
            return result

        creative_kw = ['创意', '设计', '头脑风暴', '想法', '建议', '推荐', '方案']
        if any(k in msg_lower for k in creative_kw):
            result.update(type='creative', model='ds-v4-flash-r', reasoning='创意 → Flash 深度思考')
            return result

        cmd_kw = ['打开', '关闭', '启动', '停止', '重启', '清理', '整理',
                 '下载', '安装', '配置', '检查', '查看']
        if any(k in msg_lower for k in cmd_kw):
            result.update(type='command', timeout=120, reasoning='系统命令 → 快速执行')
            return result

        if len(msg) > 200:
            result.update(complexity='moderate', model='ds-v4-flash-r',
                          timeout=300, reasoning='长文本 → Flash 深度思考')

        return result

    # ─── 发送消息 ──────────────────────────────────────────

    def send_msg(self, event=None):
        """发送消息 - 主入口"""
        try:
            msg = self.input_text.get("1.0", tk.END).strip()
            if not msg:
                return

            self.input_text.delete("1.0", tk.END)
            self._render_message("你", msg)

            conv = self._get_active_conversation()

            if msg.startswith('/'):
                cmd = msg[1:].strip().lower()
                if cmd == 'clear' or cmd == 'cls':
                    self._conv_mgr.clear_conversation(conv.id)
                    self._clear_chat_display()
                    self._render_message("系统", "✅ 对话历史已清空")
                elif cmd in ('hermes', 'h'):
                    self.launch_hermes_task(msg)
                elif cmd == 'history':
                    self._show_conversation_history()
                elif cmd == 'new':
                    self._new_conversation()
                else:
                    self._render_message("系统", f"未知命令: /{cmd}")
                return

            cmd_handler = getattr(self.controller, 'command_handler', None)
            if cmd_handler:
                quick = cmd_handler.quick_parse_command(msg)
                if quick:
                    action, params = quick
                    cmd_handler._execute_quick_action(action, params)
                    return

            conv.add_message("user", msg)
            self._refresh_conv_listbox()

            task_info = self._classify_task(msg)

            if self.controller.use_hermes and task_info.get('complexity') in ('complex', 'heavy'):
                self._chat_with_history(msg, task_info=task_info)
            else:
                self._chat_with_deepseek(msg, conv)
        except Exception as e:
            print(f"send_msg异常:{e}")
            traceback.print_exc()
            self.controller.say("系统", f"❌ 发送消息时发生错误:{str(e)}")

    def _chat_with_deepseek(self, msg: str, conv):
        """使用 DeepSeek API 直连进行对话"""
        from services.deepseek_client import get_deepseek_client

        ctrl = self.controller
        client = get_deepseek_client(config_manager=ctrl.config_manager)
        sm = self._get_streaming_manager()

        if not sm.can_start():
            self._render_message("系统", "⏳ 正在处理中,请稍候...")
            return

        model_id = self._current_model_id()
        client.set_model(model_id)

        context = conv.get_context(max_messages=10)

        result_holder = [None]

        def _task(callback, cancel_event):
            result = client.chat(
                messages=context,
                stream_callback=callback,
                timeout=60,
                system_prompt=(
                    "你是 AI 电脑管家 (AIPCHelperV8) 的智能对话助手。"
                    "运行在用户 Windows 桌面，可以直接控制电脑。\n\n"
                    "你可以用 [CMD:动作名:参数] 标记来触发本地命令，标记会被系统自动执行并从显示中移除。\n\n"
                    "常用命令：\n"
                    "  [CMD:list_files:path=路径] — 列出文件夹内容（会显示在聊天框）\n"
                    "  [CMD:open_explorer] — 打开资源管理器（推荐用于'打开/查看文件夹'）\n"
                    "  [CMD:open_folder] — 打开文件夹窗口\n"
                    "  [CMD:open_app:app_name=应用名] — 打开应用\n"
                    "  [CMD:take_screenshot] — 截图\n"
                    "  [CMD:get_system_info] — 系统信息\n"
                    "  [CMD:get_disk_usage] — 磁盘空间\n"
                    "  [CMD:get_ip_address] — 我的IP\n"
                    "  [CMD:shutdown] — 关机\n  [CMD:show_desktop] — 显示桌面\n\n"
                    "示例：\n"
                    "  用户: '查看桌面的AI项目'\n"
                    "  你: '让我看看这个项目。[CMD:list_files:path=C:\\\\Users\\\\Administrator\\\\Desktop]'\n"
                    "  用户: '打开我的文件夹'\n"
                    "  你: '好的。[CMD:open_folder]'\n"
                    "  用户: '看看桌面上有什么文件'\n"
                    "  你: '好的，让我看看。[CMD:list_files]'\n\n"
                    "注意：[CMD:xxx] 标记不会出现在用户看到的界面里，系统自动移除并执行。\n"
                    "风格：简洁、务实、少废话"
                )
            )
            result_holder[0] = result
            return result

        sm.start(
            _task,
            header_label="🤖 DeepSeek",
            status_prefix="思考中",
            color_stops=(10, 25, 40),
            timeout=60
        )

        def _check_done():
            if sm.is_active:
                ctrl.root.after(300, _check_done)
            elif result_holder[0]:
                reply = result_holder[0]
                cmd_markers = re.findall(r'\[CMD:(\w+)(?::([^\]]*))?\]', reply)
                if cmd_markers:
                    clean_reply = re.sub(r'\s*\[CMD:[^\]]+\]', '', reply).strip()
                    if clean_reply:
                        conv.add_message("assistant", clean_reply)
                        self._refresh_conv_listbox()
                    cmd_handler = getattr(self.controller, 'command_handler', None)
                    for action, params_str in cmd_markers:
                        params = {}
                        if params_str and '=' in params_str:
                            for pair in params_str.split(','):
                                if '=' in pair:
                                    k, v = pair.split('=', 1)
                                    params[k.strip()] = v.strip()
                        if cmd_handler and hasattr(cmd_handler, 'execute_ai_command'):
                            cmd_handler.execute_ai_command({"action": action, **params})
                else:
                    conv.add_message("assistant", reply)
                    self._refresh_conv_listbox()

        ctrl.root.after(500, _check_done)

    def _current_model_id(self) -> str:
        display = self.model_var.get()
        MODEL_TABLE = {
            "DeepSeek V4 Flash · 快速": "ds-v4-flash",
            "DeepSeek V4 Flash · 深度": "ds-v4-flash-r",
            "DeepSeek V4 Pro · 通用": "ds-v4-pro",
            "DeepSeek V4 Pro · 推理": "ds-v4-pro-r",
        }
        return MODEL_TABLE.get(display, "ds-v4-flash")

    def _chat_with_history(self, msg: str, task_info: dict = None):
        """多轮对话:流式输出 + Hermes 实时反馈 + 智能模型路由"""
        from services.agent_service import get_agent_service

        ctrl = self.controller
        agent = get_agent_service(ctrl.config_manager)
        sm = self._get_streaming_manager()

        if not sm.can_start():
            self._render_message("系统", "⏳ Hermes 正在处理上一轮对话,请稍候...")
            return

        if task_info is None:
            task_info = {}
        timeout = task_info.get('timeout', 300)

        if self.auto_switch_var.get():
            try:
                from services.model_switcher import get_model_switcher
                switcher = get_model_switcher()
                recommended = switcher.select_model(msg)
                current = switcher.get_current()
                if recommended.id != (current.id if current else 'ds-v4-flash'):
                    switcher.set_model(recommended.id)
                    ctrl.config_manager.set("hermes_model", recommended.id)
                    logger.info(f"🎯 智能路由: {current.id if current else 'default'} → {recommended.id}")
            except Exception as e:
                logger.warning(f"智能路由失败,使用当前模型: {e}")

        def _task(callback, cancel_event):
            return agent.chat_with_history(
                message=msg,
                stream_callback=callback,
                timeout=timeout
            )

        task_type = task_info.get('type', 'chat')
        type_labels = {
            'code': ('💻', '生成代码中'),
            'analysis': ('🔍', '分析中'),
            'search': ('🔎', '搜索中'),
            'creative': ('💡', '创作中'),
            'command': ('⚡', '执行中'),
            'system': ('🤖', '处理中'),
        }
        header_prefix, status_prefix = type_labels.get(task_type, ('🤖', '处理中'))

        sm.start(
            _task,
            header_label=f"{header_prefix} AI · {task_info.get('reasoning', '任务')[:10]}",
            status_prefix=status_prefix,
            color_stops=(30, 60, 120),
            timeout=timeout
        )

    def _show_conversation_history(self):
        try:
            from services.agent_service import get_agent_service
            ctrl = self.controller
            agent = get_agent_service(ctrl.config_manager)
            history = agent.get_history()
            turns = agent.history_turns

            if not history:
                self._render_message("系统", "📜 对话历史为空")
                return

            summary = f"📜 对话历史 ({turns} 轮)\n" + "─" * 40 + "\n"
            for i, msg in enumerate(history):
                role = "👤" if msg["role"] == "user" else "🤖"
                content = msg["content"][:80] + ("..." if len(msg["content"]) > 80 else "")
                summary += f"{i+1}. {role} {content}\n"
            self._render_message("系统", summary)
        except Exception as e:
            self._render_message("系统", f"❌ 获取历史失败: {e}")

    def _get_streaming_manager(self):
        if self._streaming_manager is None:
            from services.streaming_manager import StreamingManager
            ctrl = self.controller
            self._streaming_manager = StreamingManager(
                root=ctrl.root,
                chat_widget=self.chat,
                status_label=ctrl.status_label,
                on_complete=self._on_stream_complete,
                on_cancel_button=lambda show: (
                    self._show_cancel_button() if show else self._hide_cancel_button()
                )
            )
        return self._streaming_manager

    def _on_stream_complete(self):
        self._update_history_status()

    def _cancel_stream(self):
        if self._streaming_manager:
            self._streaming_manager.cancel()

    def _show_cancel_button(self):
        base = CATPPUCCIN
        self.send_btn.pack_forget()
        self.cancel_btn.pack(pady=(0, 2))

    def _hide_cancel_button(self):
        base = CATPPUCCIN
        self.cancel_btn.pack_forget()
        self.send_btn.pack(pady=(0, 2))

    def _update_history_status(self):
        if not hasattr(self, '_history_label'):
            return
        try:
            from services.agent_service import get_agent_service
            ctrl = self.controller
            agent = get_agent_service(ctrl.config_manager)
            turns = agent.history_turns
            base = CATPPUCCIN
            self._history_label.config(
                text=f"💬 {turns}轮" if turns > 0 else "💬 新对话",
                fg=base["overlay0"]
            )
        except Exception:
            pass

    # ─── 引擎控制 ──────────────────────────────────────────

    def _toggle_hermes_switch(self):
        ctrl = self.controller
        hermes_available = ctrl.hermes_bridge.available or (
            ctrl._agent_service and ctrl._agent_service.get_status().get("hermes")
        )
        if not hermes_available:
            messagebox.showwarning("Hermes 不可用",
                "Hermes 未检测到。\n请确保:\n1. WSL 已安装\n2. Hermes 已安装在 WSL 中")
            return

        ctrl.use_hermes = not ctrl.use_hermes
        self.hermes_toggle_var.set(ctrl.use_hermes)
        ctrl.config_manager.set("use_hermes", ctrl.use_hermes)
        self._update_hermes_toggle_ui()

        if hasattr(ctrl, 'ai_engine_label'):
            ai_engine = "Hermes" if ctrl.use_hermes else "Ollama"
            ctrl.ai_engine_label.config(text=f"AI引擎: {ai_engine}")

        ctrl.say("系统", f"Hermes {'已启用' if ctrl.use_hermes else '已禁用'}")
        logger.info(f"Hermes 切换为: {'启用' if ctrl.use_hermes else '禁用'}")

    def _update_hermes_toggle_ui(self):
        base = CATPPUCCIN
        if self.controller.use_hermes:
            self.hermes_toggle_btn.config(
                text="🟢 Hermes: 开", bg=base["green_dim"], fg=base["green"]
            )
            self.model_combo.config(state="readonly")
            self.auto_switch_btn.config(state=tk.NORMAL, bg=base["green_dim"], fg=base["green"])
        else:
            self.hermes_toggle_btn.config(
                text="⚪ Hermes: 关", bg=base["surface0"], fg=base["overlay0"]
            )
            self.model_combo.config(state="disabled")
            self.auto_switch_btn.config(state=tk.DISABLED, bg=base["surface0"], fg=base["overlay0"])

    def _on_model_selected(self, event=None):
        display_name = self.model_var.get()
        model_id = self.MODEL_DISPLAY_MAP.get(display_name)
        if not model_id:
            model_id = display_name
        ctrl = self.controller
        if ctrl.use_hermes:
            try:
                from services.model_switcher import get_model_switcher
                switcher = get_model_switcher()
                for m in switcher.list_models(enabled_only=False):
                    if m.id == model_id:
                        switcher.set_model(m.id)
                        ctrl.say("系统", f"🔄 已切换到: {m.name}")
                        self._update_model_display()
                        return
                ctrl.say("系统", f"⚠️ 未找到模型: {display_name}")
            except Exception as e:
                ctrl.say("系统", f"❌ 模型切换失败: {e}")

    def _toggle_auto_switch(self):
        try:
            from services.model_switcher import get_model_switcher
            switcher = get_model_switcher()
            is_auto = switcher.toggle_auto_switch()
            self.auto_switch_var.set(is_auto)
            ctrl = self.controller
            base = CATPPUCCIN

            if is_auto:
                self.auto_switch_btn.configure(
                    text="🔄 自动", bg=base["green_dim"], fg=base["green"]
                )
                self.model_combo.config(state="disabled")
                ctrl.say("系统", "🔄 自动模型选择已开启 - 根据任务复杂度自动匹配最优模型")
            else:
                self.auto_switch_btn.configure(
                    text="🔒 手动", bg=base["surface0"], fg=base["yellow"]
                )
                if ctrl.use_hermes:
                    self.model_combo.config(state="readonly")
                ctrl.say("系统", "🔒 手动模型选择 - 请从下拉框选择模型")
        except Exception as e:
            ctrl.say("系统", f"❌ 切换失败: {e}")

    def _update_model_display(self):
        try:
            from services.model_switcher import get_model_switcher
            switcher = get_model_switcher()
            current = switcher.get_current()
            if current:
                self.model_var.set(
                    self.MODEL_ID_TO_DISPLAY.get(current.id, current.name)
                )
                self.auto_switch_var.set(switcher.auto_switch_enabled)
                base = CATPPUCCIN

                if switcher.auto_switch_enabled:
                    self.auto_switch_btn.configure(text="🔄 自动", bg=base["green_dim"], fg=base["green"])
                    self.model_combo.config(state="disabled")
                else:
                    self.auto_switch_btn.configure(text="🔒 手动", bg=base["surface0"], fg=base["yellow"])

                models = [
                    self.MODEL_ID_TO_DISPLAY.get(m.id, m.name)
                    for m in switcher.list_models(enabled_only=False)
                ]
                self.model_combo['values'] = models
        except Exception:
            pass

    def launch_hermes_task(self, task=None):
        ctrl = self.controller
        if task is None:
            task = self.input_text.get("1.0", tk.END).strip()

        if not task:
            self._render_message("系统", "⚠️ 请先在输入框中输入任务内容")
            return

        self.input_text.delete("1.0", tk.END)
        self._render_message("你", task)

        agent_svc = ctrl.agent_service
        agent_hermes_ok = agent_svc and agent_svc.ensure_ready() and agent_svc.get_preferred_backend() == "hermes"
        if not agent_hermes_ok and not ctrl.hermes_bridge.available:
            self._render_message("系统", "❌ Hermes 不可用,请检查 WSL 和 Hermes 安装")
            return

        sm = self._get_streaming_manager()

        if not sm.can_start():
            self._render_message("系统", "⏳ Hermes 正在处理上一轮对话,请稍候...")
            return

        if self.auto_switch_var.get():
            try:
                from services.model_switcher import get_model_switcher
                switcher = get_model_switcher()
                recommended = switcher.select_model(task)
                current = switcher.get_current()
                if recommended.id != (current.id if current else 'ds-v4-flash'):
                    switcher.set_model(recommended.id)
                    ctrl.config_manager.set("hermes_model", recommended.id)
            except Exception as e:
                logger.warning(f"智能路由失败: {e}")

        def _task(callback, cancel_event):
            if agent_svc and agent_svc.ensure_ready() and agent_svc.get_preferred_backend() == "hermes":
                hermes_svc = agent_svc.hermes
                if hermes_svc and hasattr(hermes_svc, 'oneshot_with_escalation'):
                    return hermes_svc.oneshot_with_escalation(
                        task, max_retries=2, stream_callback=callback
                    )
                else:
                    return agent_svc.chat(task)
            else:
                return ctrl.hermes_bridge.send_message(task)

        task_info = self._classify_task(task)
        type_labels = {
            'code': ('💻', '生成代码中'),
            'analysis': ('🔍', '分析中'),
            'search': ('🔎', '搜索中'),
            'creative': ('💡', '创作中'),
            'command': ('⚡', '执行中'),
            'system': ('🤖', '处理中'),
        }
        header_prefix, status_prefix = type_labels.get(task_info.get('type', 'chat'), ('🤖', '处理中'))

        sm.start(
            _task,
            header_label=f"{header_prefix} Hermes",
            status_prefix=status_prefix,
            color_stops=(30, 90, 180)
        )

    def clear_chat(self):
        self.chat.config(state=tk.NORMAL)
        self.chat.delete(1.0, tk.END)
        self.chat.config(state=tk.DISABLED)

    def _on_conv_right_click(self, event):
        idx = self.conv_listbox.nearest(event.y)
        if idx < 0:
            return
        self.conv_listbox.selection_clear(0, tk.END)
        self.conv_listbox.selection_set(idx)
        base = CATPPUCCIN
        menu = tk.Menu(self.conv_panel, tearoff=0,
                        bg=base["surface0"], fg=base["text"],
                        activebackground=base["surface1"], activeforeground=base["text"])
        menu.add_command(label="✏️ 重命名", command=self._rename_conversation)
        menu.add_command(label="🗑️ 删除", command=self._delete_conversation_dialog)
        menu.add_separator()
        menu.add_command(label="📤 导出", command=self._export_conversation)
        menu.post(event.x_root, event.y_root)

    def _delete_conversation_dialog(self):
        sel = self.conv_listbox.curselection()
        if not sel:
            return
        if messagebox.askyesno("删除对话", "确定删除此对话？\n此操作不可恢复。"):
            self._delete_selected_conversation(sel[0])

    def _delete_selected_conversation(self, idx):
        try:
            convs = self._conv_mgr.list_conversations()
            if idx >= len(convs):
                return
            conv = convs[idx]
        except Exception:
            return
        self._conv_mgr.delete(conv.id)
        self._load_active_conversation()
        self._refresh_conv_listbox()
        self.controller.show_toast("对话已删除")

    def _export_conversation(self):
        sel = self.conv_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        try:
            convs = self._conv_mgr.list_conversations()
            if idx >= len(convs):
                return
            conv = convs[idx]
        except Exception:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("Markdown", "*.md")],
            initialfile=(conv.title or "conversation")
        )
        if not path:
            return
        lines = []
        for turn in conv.messages:
            lines.append(f"## {turn['role'].upper()}")
            lines.append(turn["content"])
            lines.append("")
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        self.controller.show_toast(f"已导出到 {os.path.basename(path)}")
