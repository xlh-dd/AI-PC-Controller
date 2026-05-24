import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, ttk, filedialog
import threading
import logging
import traceback
import os
from datetime import datetime

logger = logging.getLogger("ChatPanel")


class ChatPanel:
    """智能对话面板 - 左侧对话列表 + 右侧聊天区"""

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

        from services.conversation_manager import get_conversation_manager
        self._conv_mgr = get_conversation_manager()

        self._build_chat_tab()

    def _build_chat_tab(self):
        """构建智能对话标签页 - 左侧对话列表 + 右侧聊天区"""
        ctrl = self.controller

        self.chat_paned = tk.PanedWindow(
            self.parent, orient=tk.HORIZONTAL, sashwidth=3,
            bg="#45475a", sashrelief=tk.RAISED
        )
        self.chat_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.conv_panel = ttk.Frame(self.chat_paned)
        self._build_conversation_sidebar()
        self.chat_paned.add(self.conv_panel, minsize=120, stretch="never")

        self.chat_right = ttk.Frame(self.chat_paned)
        self.chat_paned.add(self.chat_right, minsize=250, stretch="always")

        self.chat = scrolledtext.ScrolledText(
            self.chat_right, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 10), bg="#1e1e2e", fg="#cdd6f4",
            relief=tk.FLAT, padx=8, pady=5
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.Frame(self.chat_right)
        input_frame.pack(fill=tk.X, padx=3, pady=3)

        self.input_text = ttk.Entry(input_frame, font=("微软雅黑", 10), foreground="#cdd6f4")
        self.input_text.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 8), ipady=5)
        self.input_text.bind("<Return>", self.send_msg)
        self.input_text.focus()

        send_btn = ttk.Button(input_frame, text="🚀 发送", command=self.send_msg)
        send_btn.pack(side=tk.RIGHT, ipady=3)

        # 绑定快捷键
        self.controller.root.bind("<Control-n>", lambda e: self._new_conversation_named())
        self.controller.root.bind("<Control-N>", lambda e: self._new_conversation_named())

        engine_frame = ttk.LabelFrame(self.chat_right, text="引擎控制", padding=5)
        engine_frame.pack(fill=tk.X, padx=3, pady=(0, 2))

        self.hermes_toggle_var = tk.BooleanVar(value=getattr(ctrl, 'use_hermes', False))
        self.hermes_toggle_btn = ttk.Button(
            engine_frame, text="🤖 Hermes",
            command=self._toggle_hermes_switch,
            bootstyle="secondary", width=10
        )
        self.hermes_toggle_btn.pack(side=tk.LEFT, padx=2)

        self.model_var = tk.StringVar(value="DeepSeek V4 Flash · 快速")
        self.model_combo = ttk.Combobox(
            engine_frame, textvariable=self.model_var,
            values=[
                "DeepSeek V4 Flash · 快速",
                "DeepSeek V4 Flash · 深度",
                "DeepSeek V4 Pro · 通用",
                "DeepSeek V4 Pro · 推理",
            ],
            state="readonly", width=24, font=("微软雅黑", 9)
        )
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)
        self.model_combo.pack(side=tk.LEFT, padx=2)
        # 模型选择提示
        model_hint = ttk.Label(
            engine_frame, text="选择AI模型",
            font=("微软雅黑", 7), foreground="#6c7086"
        )
        model_hint.pack(side=tk.LEFT, padx=(2, 0))

        self.auto_switch_var = tk.BooleanVar(value=True)
        self.auto_switch_btn = ttk.Button(
            engine_frame, text="🔄 自动",
            command=self._toggle_auto_switch,
            bootstyle="success", width=8
        )
        self.auto_switch_btn.pack(side=tk.LEFT, padx=2)

        ttk.Label(engine_frame, text=" ").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(engine_frame, text="⚙️ 设置", command=ctrl.ai_settings, width=8).pack(side=tk.RIGHT, padx=2)

        self._update_hermes_toggle_ui()

        action_frame = ttk.Frame(self.chat_right)
        action_frame.pack(fill=tk.X, padx=3, pady=(0, 3))

        ttk.Button(action_frame, text="🗑️ 清空聊天", command=self._clear_chat_display, width=10).pack(side=tk.LEFT, padx=2)
        self._history_label = ttk.Label(action_frame, text="💬 新对话", font=("微软雅黑", 8))
        self._history_label.pack(side=tk.RIGHT, padx=5)
        ttk.Button(action_frame, text="❓ 帮助", command=ctrl.show_help, width=8).pack(side=tk.RIGHT, padx=2)

        self._load_active_conversation()

    def _build_conversation_sidebar(self):
        """构建对话列表侧边栏"""
        panel = self.conv_panel

        header = ttk.Frame(panel)
        header.pack(fill=tk.X, pady=3)
        ttk.Label(header, text="💬 对话", font=("微软雅黑", 10, "bold"), width=18, anchor="w").pack(side=tk.LEFT, padx=3)
        ttk.Button(header, text="≡", width=2, command=self._toggle_conv_sidebar).pack(side=tk.RIGHT, padx=3)

        list_frame = ttk.Frame(panel)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=3)

        self.conv_listbox = tk.Listbox(
            list_frame, font=("微软雅黑", 9),
            bg="#313244", fg="#cdd6f4",
            selectbackground="#45475a",
            highlightthickness=0, bd=0,
            relief=tk.FLAT, activestyle="none"
        )
        self.conv_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.conv_listbox.bind("<<ListboxSelect>>", self._on_conv_selected)
        self.conv_listbox.bind("<Double-Button-1>", lambda e: self._rename_conversation())
        self.conv_listbox.bind("<Button-3>", self._on_conv_right_click)

        v_scroll = ttk.Scrollbar(list_frame, command=self.conv_listbox.yview)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.conv_listbox.config(yscrollcommand=v_scroll.set)

        btn_frame = ttk.Frame(panel)
        btn_frame.pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="+ 新建", command=self._new_conversation, width=9).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑", command=self._delete_conversation, width=3).pack(side=tk.RIGHT, padx=2)

        # 提示标签
        tip_label = ttk.Label(panel, text="Ctrl+N 命名新建", font=("微软雅黑", 7), foreground="#666666")
        tip_label.pack(side=tk.BOTTOM, pady=(0, 4))

        self._refresh_conv_listbox()

    def _refresh_conv_listbox(self):
        """刷新对话列表"""
        self.conv_listbox.delete(0, tk.END)
        convs = self._conv_mgr.list_conversations()
        for conv in convs:
            title = conv.title or "新对话"
            count = len([m for m in conv.messages if m.get("role") == "user"])
            display = f"{title} [{count}]"
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
        """切换对话"""
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
        """新建对话"""
        conv = self._conv_mgr.create()
        self._conv_mgr.switch_to(conv.id)
        self._clear_chat_display()
        self._refresh_conv_listbox()
        self._update_conv_label()

    def _new_conversation_named(self):
        """新建对话 — 带命名对话框"""
        title = simpledialog.askstring(
            "新建对话", "请输入对话名称（留空自动命名）:",
            parent=self.controller.root
        )
        if title is None:  # 用户点了取消
            return
        title = title.strip() or "新对话"
        conv = self._conv_mgr.create(title=title)
        self._conv_mgr.switch_to(conv.id)
        self._clear_chat_display()
        self._refresh_conv_listbox()
        self._update_conv_label()
        self.controller.say("系统", f"✅ 新建对话「{title}」")

    def _delete_conversation(self):
        """删除当前对话"""
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
        """重命名对话"""
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
        """折叠/展开对话侧边栏"""
        try:
            x, _ = self.chat_paned.sash_coord(0)
            if x < 10:
                self.chat_paned.sash_place(0, 200, 0)
            else:
                self.chat_paned.sash_place(0, 0, 0)
        except Exception:
            pass

    def _load_active_conversation(self):
        """加载当前对话的历史到聊天区"""
        self._clear_chat_display()
        conv = self._conv_mgr.active
        if conv and conv.messages:
            for msg in conv.messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    self.controller.say("你", content)
                elif role == "assistant":
                    self.controller.say("AI", content)
        self._update_conv_label()

    def _update_conv_label(self):
        """更新对话标签"""
        conv = self._conv_mgr.active
        if conv:
            self._history_label.config(text=f"💬 {conv.title[:15]}")

    def _clear_chat_display(self):
        """清空聊天显示(保留对话管理器中的数据)"""
        self.chat.config(state=tk.NORMAL)
        self.chat.delete(1.0, tk.END)
        self.chat.config(state=tk.DISABLED)

    def _get_active_conversation(self):
        """获取当前对话"""
        return self._conv_mgr.active

    def say(self, who, what):
        """面板内消息显示 - 委托给 controller.say"""
        self.controller.say(who, what)

    def _classify_task(self, msg: str):
        """分析任务复杂度,推荐最优模型/超时/路由

        Returns:
            dict: {type, complexity, model, timeout, reasoning}
        """
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

    def send_msg(self, event=None):
        """发送消息 - 主入口(日常对话直达 DeepSeek,复杂任务走 Hermes)"""
        try:
            msg = self.input_text.get().strip()
            if not msg:
                return

            self.input_text.delete(0, tk.END)
            self.controller.say("你", msg)

            conv = self._get_active_conversation()

            if msg.startswith('/'):
                cmd = msg[1:].strip().lower()
                if cmd == 'clear' or cmd == 'cls':
                    self._conv_mgr.clear_conversation(conv.id)
                    self._clear_chat_display()
                    self.controller.say("系统", "✅ 对话历史已清空")
                elif cmd in ('hermes', 'h'):
                    self.launch_hermes_task(msg)
                elif cmd == 'history':
                    self._show_conversation_history()
                elif cmd == 'new':
                    self._new_conversation()
                else:
                    self.controller.say("系统", f"未知命令: /{cmd}")
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
        """使用 DeepSeek API 直连进行对话 - 轻量快速,不走 Hermes/WSL"""
        from services.deepseek_client import get_deepseek_client

        ctrl = self.controller
        client = get_deepseek_client(config_manager=ctrl.config_manager)
        sm = self._get_streaming_manager()

        if not sm.can_start():
            ctrl.say("系统", "⏳ 正在处理中,请稍候...")
            return

        model_id = self._current_model_id()
        client.set_model(model_id)

        context = conv.get_context(max_messages=10)

        result_holder = [None]

        def _task(callback, cancel_event):
            result = client.chat(
                messages=context,
                stream_callback=callback,
                timeout=60
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
                conv.add_message("assistant", result_holder[0])
                self._refresh_conv_listbox()

        ctrl.root.after(500, _check_done)

    def _current_model_id(self) -> str:
        """从 UI 下拉框获取当前模型 ID"""
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
            ctrl.say("系统", "⏳ Hermes 正在处理上一轮对话,请稍候...")
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
        """显示对话历史摘要"""
        try:
            from services.agent_service import get_agent_service
            ctrl = self.controller
            agent = get_agent_service(ctrl.config_manager)
            history = agent.get_history()
            turns = agent.history_turns

            if not history:
                ctrl.say("系统", "📜 对话历史为空")
                return

            summary = f"📜 对话历史 ({turns} 轮)\n" + "─" * 40 + "\n"
            for i, msg in enumerate(history):
                role = "👤" if msg["role"] == "user" else "🤖"
                content = msg["content"][:80] + ("..." if len(msg["content"]) > 80 else "")
                summary += f"{i+1}. {role} {content}\n"
            ctrl.say("系统", summary)
        except Exception as e:
            ctrl.say("系统", f"❌ 获取历史失败: {e}")

    def _get_streaming_manager(self):
        """懒加载 StreamingManager 单例"""
        if self._streaming_manager is None:
            from services.streaming_manager import StreamingManager
            ctrl = self.controller
            self._streaming_manager = StreamingManager(
                root=ctrl.root,
                chat_widget=self.chat,
                status_label=ctrl.status_label,
                on_complete=self._on_stream_complete,
                on_cancel_button=lambda show: (
                    ctrl._show_cancel_button() if show else ctrl._hide_cancel_button()
                )
            )
        return self._streaming_manager

    def _on_stream_complete(self):
        """流式完成回调 - 更新对话历史状态"""
        self._update_history_status()

    def _update_history_status(self):
        """更新对话历史状态显示"""
        if not hasattr(self, '_history_label'):
            return
        try:
            from services.agent_service import get_agent_service
            ctrl = self.controller
            agent = get_agent_service(ctrl.config_manager)
            turns = agent.history_turns
            self._history_label.config(text=f"💬 {turns}轮" if turns > 0 else "💬 新对话")
        except Exception:
            pass

    def _toggle_hermes_switch(self):
        """Hermes 开关按钮点击处理"""
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
        """更新 Hermes 开关按钮的显示状态"""
        if self.controller.use_hermes:
            self.hermes_toggle_btn.configure(text="🟢 Hermes: 开", bootstyle="success")
            self.model_combo.config(state="readonly")
            self.auto_switch_btn.configure(state="normal", bootstyle="success")
        else:
            self.hermes_toggle_btn.configure(text="⚪ Hermes: 关", bootstyle="secondary")
            self.model_combo.config(state="disabled")
            self.auto_switch_btn.configure(state="disabled", bootstyle="secondary")

    def _on_model_selected(self, event=None):
        """模型下拉框切换事件"""
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
        """切换自动模型选择"""
        try:
            from services.model_switcher import get_model_switcher
            switcher = get_model_switcher()
            is_auto = switcher.toggle_auto_switch()
            self.auto_switch_var.set(is_auto)
            ctrl = self.controller

            if is_auto:
                self.auto_switch_btn.configure(
                    text="🔄 自动", bootstyle="success"
                )
                self.model_combo.config(state="disabled")
                ctrl.say("系统", "🔄 自动模型选择已开启 - 根据任务复杂度自动匹配最优模型")
            else:
                self.auto_switch_btn.configure(
                    text="🔒 手动", bootstyle="warning"
                )
                if ctrl.use_hermes:
                    self.model_combo.config(state="readonly")
                ctrl.say("系统", "🔒 手动模型选择 - 请从下拉框选择模型")
        except Exception as e:
            ctrl.say("系统", f"❌ 切换失败: {e}")

    def _update_model_display(self):
        """更新模型相关UI显示"""
        try:
            from services.model_switcher import get_model_switcher
            switcher = get_model_switcher()
            current = switcher.get_current()
            if current:
                self.model_var.set(
                    self.MODEL_ID_TO_DISPLAY.get(current.id, current.name)
                )
                self.auto_switch_var.set(switcher.auto_switch_enabled)

                if switcher.auto_switch_enabled:
                    self.auto_switch_btn.configure(text="🔄 自动", bootstyle="success")
                    self.model_combo.config(state="disabled")
                else:
                    self.auto_switch_btn.configure(text="🔒 手动", bootstyle="warning")

                models = [
                    self.MODEL_ID_TO_DISPLAY.get(m.id, m.name)
                    for m in switcher.list_models(enabled_only=False)
                ]
                self.model_combo['values'] = models
        except Exception:
            pass

    def launch_hermes_task(self, task=None):
        """向 Hermes 发送任务 - 使用 StreamingManager"""
        ctrl = self.controller
        if task is None:
            task = self.input_text.get().strip()

        if not task:
            ctrl.say("系统", "⚠️ 请先在输入框中输入任务内容")
            return

        self.input_text.delete(0, tk.END)
        ctrl.say("你", task)

        agent_svc = ctrl.agent_service
        agent_hermes_ok = agent_svc and agent_svc.ensure_ready() and agent_svc.get_preferred_backend() == "hermes"
        if not agent_hermes_ok and not ctrl.hermes_bridge.available:
            ctrl.say("系统", "❌ Hermes 不可用,请检查 WSL 和 Hermes 安装")
            return

        sm = self._get_streaming_manager()

        if not sm.can_start():
            ctrl.say("系统", "⏳ Hermes 正在处理上一轮对话,请稍候...")
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
        """清空聊天显示"""
        self.chat.config(state=tk.NORMAL)
        self.chat.delete(1.0, tk.END)
        self.chat.config(state=tk.DISABLED)

    def _on_conv_right_click(self, event):
        """对话列表右键菜单"""
        idx = self.conv_listbox.nearest(event.y)
        if idx < 0:
            return
        self.conv_listbox.selection_clear(0, tk.END)
        self.conv_listbox.selection_set(idx)
        menu = tk.Menu(self.conv_panel, tearoff=0,
                        bg="#313244", fg="#cdd6f4",
                        activebackground="#45475a", activeforeground="#f5e0dc")
        menu.add_command(label="✏️ 重命名", command=self._rename_conversation)
        menu.add_command(label="🗑️ 删除", command=self._delete_conversation_dialog)
        menu.add_separator()
        menu.add_command(label="📤 导出", command=self._export_conversation)
        menu.post(event.x_root, event.y_root)

    def _delete_conversation_dialog(self):
        """删除对话确认对话框"""
        sel = self.conv_listbox.curselection()
        if not sel:
            return
        if messagebox.askyesno("删除对话", "确定删除此对话？\n此操作不可恢复。"):
            self._delete_selected_conversation(sel[0])

    def _delete_selected_conversation(self, idx):
        """删除列表索引处的对话"""
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
        """导出对话为文本文件"""
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
            lines.append(f"## {turn["role"].upper()}")
            lines.append(turn["content"])
            lines.append("")
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        self.controller.show_toast(f"已导出到 {os.path.basename(path)}")