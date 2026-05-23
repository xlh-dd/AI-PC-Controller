import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog, ttk
import threading
import logging

logger = logging.getLogger("AutomationPanel")

try:
    from modules.macro_recorder import PYAUTOGUI_AVAILABLE, get_recorder, get_player
    MACRO_AVAILABLE = PYAUTOGUI_AVAILABLE
except ImportError:
    MACRO_AVAILABLE = False
    get_recorder = None
    get_player = None
    PYAUTOGUI_AVAILABLE = False


class AutomationPanel:
    """自动化面板 - 宏录制、自动化任务、AI智能体、编程工作区"""

    def __init__(self, parent: tk.Widget, controller):
        """构建自动化标签页

        Args:
            parent: 父容器(tk.Widget)
            controller: AppController / AIPCHelperV8 主控制器实例
        """
        self.parent = parent
        self.controller = controller
        self._built = False

        self._show_loading()

    def _show_loading(self):
        """显示加载中提示"""
        self._loading_label = ttk.Label(
            self.parent, text="加载中...",
            font=("微软雅黑", 14), foreground="gray"
        )
        self._loading_label.pack(expand=True)

        self.controller.root.after(50, self._build)

    def _build(self):
        """实际构建自动化UI"""
        self._loading_label.pack_forget()
        self._built = True

        ctrl = self.controller

        tools_frame = ttk.LabelFrame(self.parent, text="自动化工具", padding=10)
        tools_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(tools_frame, text="🎬 宏录制", command=self.show_macro_panel, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools_frame, text="🔄 自动化任务", command=self.show_automation_panel, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools_frame, text="🤖 AI智能体", command=ctrl.show_ai_agent_panel, bootstyle="success", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools_frame, text="💻 编程工作区", command=ctrl.show_code_workspace, bootstyle="info", width=15).pack(side=tk.LEFT, padx=3)

        app_frame = ttk.LabelFrame(self.parent, text="应用管理", padding=10)
        app_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(app_frame, text="➕ 添加应用", command=ctrl.add_custom_app, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(app_frame, text="📋 应用列表", command=ctrl.list_custom_apps, width=15).pack(side=tk.LEFT, padx=5)

        help_frame = ttk.LabelFrame(self.parent, text="使用说明", padding=10)
        help_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        help_text = scrolledtext.ScrolledText(
            help_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg="#1e1e2e", fg="#cdd6f4",
            height=8
        )
        help_text.pack(fill=tk.BOTH, expand=True)

        help_content = """🎬 宏录制: 录制鼠标键盘操作,可重复播放
🔄 自动化任务: 创建定时或条件触发的自动化任务
🤖 AI智能体: 自动搜索整理信息并保存文档
💻 编程工作区: 项目监控 + 代码质量 + 批量生成

💡 提示: 所有自动化操作都可以通过智能对话标签页用自然语言触发
"""
        help_text.config(state=tk.NORMAL)
        help_text.insert(tk.END, help_content)
        help_text.config(state=tk.DISABLED)

    def show_automation_panel(self):
        """显示自动化任务面板"""
        ctrl = self.controller
        win, content_frame = ctrl.create_scrollable_window("🔄 自动化任务", 650, 600)

        ttk.Label(content_frame, text="🔄 自动化任务", font=("微软雅黑", 14, "bold")).pack(pady=10)
        ttk.Label(content_frame, text="添加定时执行的自动化任务,关闭窗口后任务继续运行", foreground="gray").pack(pady=(0, 10))

        notebook = ttk.Notebook(content_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        frame_command = ttk.Frame(notebook)
        frame_app = ttk.Frame(notebook)
        frame_script = ttk.Frame(notebook)
        frame_loop = ttk.Frame(notebook)
        notebook.add(frame_command, text="定时命令")
        notebook.add(frame_app, text="启动应用")
        notebook.add(frame_script, text="执行脚本")
        notebook.add(frame_loop, text="循环任务")

        self._build_command_tab(frame_command)
        self._build_app_tab(frame_app)
        self._build_script_tab(frame_script)
        self._build_loop_task_tab(frame_loop)

        ttk.Button(content_frame, text="关闭", command=win.destroy).pack(pady=10)

    def _build_command_tab(self, parent):
        """定时命令标签"""
        ctrl = self.controller
        ttk.Label(parent, text="任务名称:").pack(pady=5)
        cmd_name_entry = ttk.Entry(parent, width=40)
        cmd_name_entry.pack(pady=5)

        ttk.Label(parent, text="命令内容:").pack(pady=5)
        cmd_text = scrolledtext.ScrolledText(parent, width=50, height=5)
        cmd_text.pack(pady=5)

        ttk.Label(parent, text="执行时间:").pack(pady=5)
        time_frame = ttk.Frame(parent)
        time_frame.pack(pady=5)

        hour_var = tk.StringVar(value="09")
        minute_var = tk.StringVar(value="00")
        ttk.Combobox(time_frame, textvariable=hour_var, values=[f"{i:02d}" for i in range(24)], width=4, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        ttk.Combobox(time_frame, textvariable=minute_var, values=[f"{i:02d}" for i in range(0, 60, 5)], width=4, state="readonly").pack(side=tk.LEFT, padx=2)

        def add_command_task():
            name = cmd_name_entry.get().strip()
            command = cmd_text.get("1.0", tk.END).strip()
            send_time = f"{hour_var.get()}:{minute_var.get()}"
            if name and command:
                ctrl.task_scheduler.add_command_task(name, command, send_time)
                ctrl.say("系统", f"✅ 已添加命令任务:{name},执行时间 {send_time}")
            else:
                messagebox.showwarning("警告", "请填写完整信息")

        ttk.Button(parent, text="添加任务", command=add_command_task).pack(pady=10)

    def _build_app_tab(self, parent):
        """启动应用标签"""
        ctrl = self.controller
        ttk.Label(parent, text="任务名称:").pack(pady=5)
        app_name_entry = ttk.Entry(parent, width=40)
        app_name_entry.pack(pady=5)

        ttk.Label(parent, text="应用路径:").pack(pady=5)
        app_path_entry = ttk.Entry(parent, width=40)
        app_path_entry.pack(pady=5)

        ttk.Button(parent, text="浏览", command=lambda: app_path_entry.insert(0, filedialog.askopenfilename(title="选择应用"))).pack(pady=5)

        ttk.Label(parent, text="执行时间:").pack(pady=5)
        time_frame = ttk.Frame(parent)
        time_frame.pack(pady=5)

        hour_var = tk.StringVar(value="09")
        minute_var = tk.StringVar(value="00")
        ttk.Combobox(time_frame, textvariable=hour_var, values=[f"{i:02d}" for i in range(24)], width=4, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        ttk.Combobox(time_frame, textvariable=minute_var, values=[f"{i:02d}" for i in range(0, 60, 5)], width=4, state="readonly").pack(side=tk.LEFT, padx=2)

        def add_app_task():
            name = app_name_entry.get().strip()
            app_path = app_path_entry.get().strip()
            send_time = f"{hour_var.get()}:{minute_var.get()}"
            if name and app_path:
                ctrl.task_scheduler.add_app_task(name, app_path, send_time)
                ctrl.say("系统", f"✅ 已添加应用任务:{name},执行时间 {send_time}")
            else:
                messagebox.showwarning("警告", "请填写完整信息")

        ttk.Button(parent, text="添加任务", command=add_app_task).pack(pady=10)

    def _build_script_tab(self, parent):
        """执行脚本标签"""
        ctrl = self.controller
        ttk.Label(parent, text="任务名称:").pack(pady=5)
        script_name_entry = ttk.Entry(parent, width=40)
        script_name_entry.pack(pady=5)

        ttk.Label(parent, text="脚本路径:").pack(pady=5)
        script_path_entry = ttk.Entry(parent, width=40)
        script_path_entry.pack(pady=5)

        ttk.Button(parent, text="浏览", command=lambda: script_path_entry.insert(0, filedialog.askopenfilename(
            title="选择脚本", filetypes=[("脚本文件", "*.py *.bat *.ps1"), ("所有文件", "*.*")]
        ))).pack(pady=5)

        ttk.Label(parent, text="执行时间:").pack(pady=5)
        time_frame = ttk.Frame(parent)
        time_frame.pack(pady=5)

        hour_var = tk.StringVar(value="09")
        minute_var = tk.StringVar(value="00")
        ttk.Combobox(time_frame, textvariable=hour_var, values=[f"{i:02d}" for i in range(24)], width=4, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Label(time_frame, text=":").pack(side=tk.LEFT)
        ttk.Combobox(time_frame, textvariable=minute_var, values=[f"{i:02d}" for i in range(0, 60, 5)], width=4, state="readonly").pack(side=tk.LEFT, padx=2)

        def add_script_task():
            name = script_name_entry.get().strip()
            script_path = script_path_entry.get().strip()
            send_time = f"{hour_var.get()}:{minute_var.get()}"
            if name and script_path:
                ctrl.task_scheduler.add_script_task(name, script_path, send_time)
                ctrl.say("系统", f"✅ 已添加脚本任务:{name},执行时间 {send_time}")
            else:
                messagebox.showwarning("警告", "请填写完整信息")

        ttk.Button(parent, text="添加任务", command=add_script_task).pack(pady=10)

    def _build_loop_task_tab(self, parent):
        """循环任务标签"""
        ctrl = self.controller
        ttk.Label(parent, text="任务名称:").pack(pady=5)
        loop_name_entry = ttk.Entry(parent, width=40)
        loop_name_entry.pack(pady=5)

        ttk.Label(parent, text="循环间隔(分钟):").pack(pady=5)
        interval_var = tk.StringVar(value="60")
        ttk.Combobox(parent, textvariable=interval_var, values=["1", "5", "10", "15", "30", "60", "120", "360"], width=10, state="readonly").pack(pady=5)

        ttk.Label(parent, text="任务类型:").pack(pady=5)
        task_type_var = tk.StringVar(value="command")
        type_frame = ttk.Frame(parent)
        type_frame.pack(pady=5)
        ttk.Radiobutton(type_frame, text="执行命令", variable=task_type_var, value="command").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(type_frame, text="启动应用", variable=task_type_var, value="app").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(type_frame, text="发送微信", variable=task_type_var, value="wechat").pack(side=tk.LEFT, padx=5)

        ttk.Label(parent, text="命令/应用路径/联系人:").pack(pady=5)
        task_value_entry = ttk.Entry(parent, width=40)
        task_value_entry.pack(pady=5)

        ttk.Label(parent, text="消息内容(仅微信):").pack(pady=5)
        msg_entry = ttk.Entry(parent, width=40)
        msg_entry.pack(pady=5)

        def add_loop_task():
            name = loop_name_entry.get().strip()
            interval = int(interval_var.get())
            task_type = task_type_var.get()
            task_value = task_value_entry.get().strip()

            if not name or not task_value:
                messagebox.showwarning("警告", "请填写完整信息")
                return

            if task_type == "command":
                ctrl.task_scheduler.add_loop_task(name, "command", interval, params={"command": task_value})
                ctrl.say("系统", f"✅ 已添加循环命令任务:{name},间隔 {interval} 分钟")
            elif task_type == "app":
                ctrl.task_scheduler.add_loop_task(name, "app", interval, params={"app_path": task_value})
                ctrl.say("系统", f"✅ 已添加循环应用任务:{name},间隔 {interval} 分钟")
            elif task_type == "wechat":
                message = msg_entry.get().strip()
                if not message:
                    messagebox.showwarning("警告", "请填写微信消息内容")
                    return
                ctrl.task_scheduler.add_loop_task(name, "wechat", interval, params={"target": task_value, "message": message})
                ctrl.say("系统", f"✅ 已添加循环微信任务:{name},间隔 {interval} 分钟")

        ttk.Button(parent, text="添加任务", command=add_loop_task).pack(pady=10)

        ttk.Label(parent, text="已添加的循环任务:", font=("微软雅黑", 10)).pack(pady=10)
        self.loop_task_listbox = tk.Listbox(parent, height=6)
        self.loop_task_listbox.pack(pady=5, fill=tk.X, padx=10)
        self._refresh_loop_tasks()

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="刷新", command=self._refresh_loop_tasks).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="停止选中", command=self._stop_selected_loop_task).pack(side=tk.LEFT, padx=5)

    def _refresh_loop_tasks(self):
        """刷新循环任务列表"""
        ctrl = self.controller
        if hasattr(self, 'loop_task_listbox'):
            self.loop_task_listbox.delete(0, tk.END)
            tasks = ctrl.task_scheduler.get_loop_tasks()
            for task in tasks:
                status = "运行中" if task.get("running") else "已停止"
                self.loop_task_listbox.insert(
                    tk.END,
                    f"{task.get('name', '未命名')} - {task.get('interval_minutes', 60)}分钟 - {status}"
                )

    def _stop_selected_loop_task(self):
        """停止选中的循环任务"""
        ctrl = self.controller
        selection = self.loop_task_listbox.curselection()
        if selection:
            tasks = ctrl.task_scheduler.get_loop_tasks()
            if selection[0] < len(tasks):
                name = tasks[selection[0]].get("name")
                ctrl.task_scheduler.stop_loop_task(name)
                ctrl.say("系统", f"⏹ 已停止循环任务:{name}")
                self._refresh_loop_tasks()

    def show_macro_panel(self):
        """显示宏录制面板"""
        ctrl = self.controller
        win, content_frame = ctrl.create_scrollable_window("🎬 宏录制", 550, 550)

        self.macro_recorder = get_recorder()
        self.macro_player = get_player()
        self.is_recording = False

        ttk.Label(content_frame, text="🎬 宏录制/回放", font=("微软雅黑", 14, "bold")).pack(pady=10)
        ttk.Label(content_frame, text="录制鼠标和键盘操作,自动执行重复任务", foreground="gray").pack(pady=(0, 10))

        ttk.Label(content_frame, text="录制说明:点击「开始录制」后进行操作,完成后点击「停止并保存」",
                  font=("微软雅黑", 9), foreground="orange").pack(pady=5)

        speed_frame = ttk.Frame(content_frame)
        speed_frame.pack(pady=5)
        ttk.Label(speed_frame, text="播放速度:").pack(side=tk.LEFT)
        self.macro_speed_var = tk.DoubleVar(value=1.0)
        speed_combo = ttk.Combobox(speed_frame, textvariable=self.macro_speed_var,
                                   values=["0.5", "1.0", "1.5", "2.0"], width=5, state="readonly")
        speed_combo.pack(side=tk.LEFT, padx=5)

        self.macro_repeat_var = tk.IntVar(value=1)
        ttk.Label(speed_frame, text="  重复次数:").pack(side=tk.LEFT)
        repeat_combo = ttk.Combobox(speed_frame, textvariable=self.macro_repeat_var,
                                    values=["1", "2", "3", "5"], width=3, state="readonly")
        repeat_combo.pack(side=tk.LEFT, padx=5)

        record_frame = ttk.Frame(content_frame)
        record_frame.pack(pady=15)

        self.record_btn = ttk.Button(record_frame, text="⏺ 开始录制", command=self.toggle_recording)
        self.record_btn.pack(side=tk.LEFT, padx=10)

        ttk.Button(record_frame, text="⏹ 停止并保存", command=self.stop_and_save_macro).pack(side=tk.LEFT, padx=10)

        ttk.Label(content_frame, text="已录制的宏:", font=("微软雅黑", 11)).pack(pady=10)

        self.macro_listbox = tk.Listbox(content_frame, height=10)
        self.macro_listbox.pack(pady=5, fill=tk.X, padx=10)
        self.refresh_macro_list()

        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="▶ 播放", command=self.play_selected_macro).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔄 刷新", command=self.refresh_macro_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🗑️ 删除", command=self.delete_selected_macro).pack(side=tk.LEFT, padx=5)

        ttk.Label(content_frame, text="使用提示:", font=("微软雅黑", 10)).pack(pady=(15, 5))
        tips = """• 录制过程中计算机会记录您的所有操作
• 播放时可选择速度和重复次数
• 建议为每个宏起一个易懂的名字
• 关闭窗口不影响正在录制的宏"""
        ttk.Label(content_frame, text=tips, foreground="gray", font=("微软雅黑", 9)).pack(pady=5)

        ttk.Button(content_frame, text="关闭", command=win.destroy).pack(pady=10)

    def toggle_recording(self):
        """切换录制状态"""
        ctrl = self.controller
        if not self.is_recording:
            name = "未命名宏"
            self.macro_recorder.start_recording(name)
            self.is_recording = True
            self.record_btn.config(text="⏸ 录制中...")
            ctrl.say("系统", "🔴 开始录制宏,请在电脑上进行操作...")
        else:
            ctrl.say("系统", "录制进行中,请点击\"停止并保存\"")

    def stop_and_save_macro(self):
        """停止并保存宏"""
        ctrl = self.controller
        if self.is_recording:
            macro_data = self.macro_recorder.stop_recording()
            if macro_data:
                name = macro_data.get("name", "未命名宏")
                macro_name = simpledialog.askstring("保存宏", "请输入宏名称:", initialvalue=name)
                if macro_name:
                    macro_data["name"] = macro_name
                    self.macro_recorder.save_macro(macro_data)
                    ctrl.say("系统", f"✅ 宏已保存:{macro_name}")
                    self.refresh_macro_list()
            self.is_recording = False
            self.record_btn.config(text="⏺ 开始录制")
        else:
            messagebox.showinfo("提示", "请先开始录制")

    def refresh_macro_list(self):
        """刷新宏列表"""
        self.macro_listbox.delete(0, tk.END)
        macros = self.macro_recorder.list_macros()
        for m in macros:
            self.macro_listbox.insert(tk.END, f"{m['name']} ({m['actions']}个动作)")

    def play_selected_macro(self):
        """播放选中的宏"""
        ctrl = self.controller
        selection = self.macro_listbox.curselection()
        if selection:
            macros = self.macro_recorder.list_macros()
            if selection[0] < len(macros):
                macro_name = macros[selection[0]]["file"]
                speed = self.macro_speed_var.get() if hasattr(self, 'macro_speed_var') else 1.0
                repeat = self.macro_repeat_var.get() if hasattr(self, 'macro_repeat_var') else 1
                ctrl.say("系统", f"▶ 正在播放宏:{macros[selection[0]]['name']} (速度:{speed}x, 重复:{repeat}次)")
                threading.Thread(
                    target=lambda: self.macro_player.play(macro_name, speed=speed, repeat=repeat),
                    daemon=True
                ).start()

    def delete_selected_macro(self):
        """删除选中的宏"""
        selection = self.macro_listbox.curselection()
        if selection:
            macros = self.macro_recorder.list_macros()
            if selection[0] < len(macros):
                macro_name = macros[selection[0]]["file"]
                if messagebox.askyesno("确认", f"确定删除宏 \"{macros[selection[0]]['name']}\" 吗?"):
                    self.macro_recorder.delete_macro(macro_name)
                    self.refresh_macro_list()
                    self.controller.say("系统", f"✅ 宏已删除")