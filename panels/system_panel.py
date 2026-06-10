import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog, ttk
import os
import subprocess
import threading
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("SystemPanel")

# Catppuccin Mocha 配色
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
    "red_dim":    "#3a2a2a",
    "yellow":     "#f9e2af",
    "mauve":      "#cba6f7",
    "peach":      "#fab387",
    "teal":       "#94e2d5",
    "sky":        "#89dceb",
}


class SystemPanel:
    """系统控制面板 - 电源控制(卡片按钮)、仪表盘、系统工具(图标网格)"""

    def __init__(self, parent: tk.Widget, controller):
        self.parent = parent
        self.controller = controller
        self._built = False
        self._monitor_bars = {}  # 进度条引用
        self._monitor_job = None

        self._show_loading()

    def _show_loading(self):
        self._loading_label = tk.Label(
            self.parent, text="加载中...", font=("微软雅黑", 14),
            fg=CATPPUCCIN["overlay0"], bg=CATPPUCCIN["base"]
        )
        self._loading_label.pack(expand=True)
        self.controller.root.after(50, self._build)

    def _build(self):
        self._loading_label.pack_forget()
        self._built = True
        base = CATPPUCCIN

        # 可滚动容器
        canvas = tk.Canvas(self.parent, bg=base["base"], highlightthickness=0)
        scrollbar = tk.Scrollbar(self.parent, orient="vertical", command=canvas.yview,
                                 bg=base["surface0"], troughcolor=base["crust"])
        self._scroll_frame = tk.Frame(canvas, bg=base["base"])

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        parent = self._scroll_frame

        # ── 电源控制(卡片按钮) ──
        self._build_power_section(parent)

        # ── 系统工具(图标网格) ──
        self._build_tools_grid(parent)

        # ── 音量控制 ──
        self._build_volume_section(parent)

        # ── 仪表盘 ──
        self._build_dashboard(parent)

        # 初始刷新
        self._refresh_dashboard()

    # ─── 电源控制(卡片式) ──────────────────────────────

    def _build_power_section(self, parent):
        base = CATPPUCCIN
        section = tk.Frame(parent, bg=base["base"])
        section.pack(fill=tk.X, padx=12, pady=(10, 4))

        tk.Label(section, text="⚡ 电源控制", font=("微软雅黑", 11, "bold"),
                 bg=base["base"], fg=base["text"], anchor="w").pack(fill=tk.X, pady=(0, 6))

        cards_frame = tk.Frame(section, bg=base["base"])
        cards_frame.pack(fill=tk.X)

        power_actions = [
            ("🔴", "关机", base["red_dim"], base["red"], lambda: self.system_operation("关机")),
            ("🔄", "重启", base["blue_dim"], base["blue"], lambda: self.system_operation("重启")),
            ("💤", "睡眠", base["green_dim"], base["green"], lambda: self.system_operation("睡眠")),
            ("🔒", "锁定", base["surface0"], base["mauve"], lambda: self.system_operation("锁定")),
            ("❌", "取消关机", base["surface0"], base["yellow"], lambda: self.system_operation("取消关机")),
        ]

        for icon, text, card_bg, icon_fg, cmd in power_actions:
            card = tk.Frame(cards_frame, bg=card_bg, cursor="hand2",
                            highlightbackground=base["surface1"],
                            highlightthickness=1, padx=10, pady=8)

            icon_lbl = tk.Label(card, text=icon, font=("Segoe UI Emoji", 18),
                                bg=card_bg, fg=icon_fg)
            icon_lbl.pack(pady=(0, 2))

            text_lbl = tk.Label(card, text=text, font=("微软雅黑", 9),
                                bg=card_bg, fg=base["subtext0"])
            text_lbl.pack()

            # Hover
            def make_hover(c, i, t, bg, hbg=base["surface1"]):
                def on_enter(e):
                    c.config(bg=hbg); i.config(bg=hbg); t.config(bg=hbg)
                def on_leave(e):
                    c.config(bg=bg); i.config(bg=bg); t.config(bg=bg)
                return on_enter, on_leave

            on_enter, on_leave = make_hover(card, icon_lbl, text_lbl, card_bg)
            for w in (card, icon_lbl, text_lbl):
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.bind("<Button-1>", lambda e, c=cmd: c())

            card.pack(side=tk.LEFT, padx=4, pady=2)

    # ─── 系统工具(图标网格) ──────────────────────────────

    def _build_tools_grid(self, parent):
        base = CATPPUCCIN
        section = tk.Frame(parent, bg=base["base"])
        section.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(section, text="🛠️ 系统工具", font=("微软雅黑", 11, "bold"),
                 bg=base["base"], fg=base["text"], anchor="w").pack(fill=tk.X, pady=(0, 6))

        grid_frame = tk.Frame(section, bg=base["base"])
        grid_frame.pack(fill=tk.X)

        tools = [
            ("🖥️", "任务管理器", base["blue_dim"], base["blue"],
             lambda: self._safe_execute_command("open_task_manager", "taskmgr")),
            ("⚙️", "系统设置", base["surface0"], base["mauve"],
             lambda: self._safe_execute_command("open_settings", "start ms-settings:")),
            ("📟", "CMD", base["surface0"], base["teal"],
             lambda: self._safe_execute_command("open_cmd", "start cmd")),
            ("💻", "PowerShell", base["blue_dim"], base["sky"],
             lambda: self._safe_execute_command("open_powershell", "start powershell")),
        ]

        for i, (icon, text, card_bg, icon_fg, cmd) in enumerate(tools):
            card = tk.Frame(grid_frame, bg=card_bg, cursor="hand2",
                            highlightbackground=base["surface1"],
                            highlightthickness=1, padx=12, pady=8)

            icon_lbl = tk.Label(card, text=icon, font=("Segoe UI Emoji", 16),
                                bg=card_bg, fg=icon_fg)
            icon_lbl.pack(pady=(0, 2))

            text_lbl = tk.Label(card, text=text, font=("微软雅黑", 8),
                                bg=card_bg, fg=base["subtext0"])
            text_lbl.pack()

            def make_hover(c, i, t, bg, hbg=base["surface1"]):
                def on_enter(e):
                    c.config(bg=hbg); i.config(bg=hbg); t.config(bg=hbg)
                def on_leave(e):
                    c.config(bg=bg); i.config(bg=bg); t.config(bg=bg)
                return on_enter, on_leave

            on_enter, on_leave = make_hover(card, icon_lbl, text_lbl, card_bg)
            for w in (card, icon_lbl, text_lbl):
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.bind("<Button-1>", lambda e, c=cmd: c())

            row, col = divmod(i, 4)
            card.grid(row=row, column=col, padx=4, pady=3, sticky="nsew")

        for c in range(4):
            grid_frame.columnconfigure(c, weight=1)

    # ─── 音量控制 ──────────────────────────────────────

    def _build_volume_section(self, parent):
        base = CATPPUCCIN
        section = tk.Frame(parent, bg=base["base"])
        section.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(section, text="🔊 音量控制", font=("微软雅黑", 11, "bold"),
                 bg=base["base"], fg=base["text"], anchor="w").pack(fill=tk.X, pady=(0, 6))

        vol_frame = tk.Frame(section, bg=base["base"])
        vol_frame.pack(fill=tk.X)

        vol_actions = [
            ("🔊", "增大", base["blue_dim"], base["blue"],
             lambda: self.execute_ai_command({"action": "volume_up"})),
            ("🔉", "减小", base["surface0"], base["teal"],
             lambda: self.execute_ai_command({"action": "volume_down"})),
            ("🔇", "静音", base["red_dim"], base["red"],
             lambda: self.execute_ai_command({"action": "toggle_mute"})),
        ]

        for icon, text, card_bg, icon_fg, cmd in vol_actions:
            card = tk.Frame(vol_frame, bg=card_bg, cursor="hand2",
                            highlightbackground=base["surface1"],
                            highlightthickness=1, padx=14, pady=6)

            icon_lbl = tk.Label(card, text=icon, font=("Segoe UI Emoji", 14),
                                bg=card_bg, fg=icon_fg)
            icon_lbl.pack(side=tk.LEFT, padx=(0, 4))

            text_lbl = tk.Label(card, text=text, font=("微软雅黑", 9),
                                bg=card_bg, fg=base["subtext0"])
            text_lbl.pack(side=tk.LEFT)

            def make_hover(c, i, t, bg, hbg=base["surface1"]):
                def on_enter(e):
                    c.config(bg=hbg); i.config(bg=hbg); t.config(bg=hbg)
                def on_leave(e):
                    c.config(bg=bg); i.config(bg=bg); t.config(bg=bg)
                return on_enter, on_leave

            on_enter, on_leave = make_hover(card, icon_lbl, text_lbl, card_bg)
            for w in (card, icon_lbl, text_lbl):
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.bind("<Button-1>", lambda e, c=cmd: c())

            card.pack(side=tk.LEFT, padx=4, pady=2)

    # ─── 仪表盘 ────────────────────────────────────────

    def _build_dashboard(self, parent):
        base = CATPPUCCIN
        section = tk.Frame(parent, bg=base["base"])
        section.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))

        header_frame = tk.Frame(section, bg=base["base"])
        header_frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(header_frame, text="📊 系统仪表盘", font=("微软雅黑", 11, "bold"),
                 bg=base["base"], fg=base["text"], anchor="w").pack(side=tk.LEFT)

        refresh_btn = tk.Button(
            header_frame, text="🔄 刷新", font=("微软雅黑", 8),
            bg=base["surface0"], fg=base["overlay0"],
            activebackground=base["surface1"], activeforeground=base["text"],
            relief=tk.FLAT, cursor="hand2", padx=8, pady=1,
            command=self._refresh_dashboard,
        )
        refresh_btn.pack(side=tk.RIGHT)

        dashboard = tk.Frame(section, bg=base["base"])
        dashboard.pack(fill=tk.BOTH, expand=True)

        # CPU 进度条
        self._monitor_bars["cpu"] = self._create_dashboard_bar(
            dashboard, "🧠 CPU", base["blue"]
        )
        # 内存进度条
        self._monitor_bars["memory"] = self._create_dashboard_bar(
            dashboard, "💾 内存", base["green"]
        )
        # 磁盘进度条
        self._monitor_bars["disk"] = self._create_dashboard_bar(
            dashboard, "💿 磁盘", base["mauve"]
        )

        # 系统信息文本
        info_frame = tk.Frame(dashboard, bg=base["crust"],
                              highlightbackground=base["surface0"],
                              highlightthickness=1)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.system_info_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg=base["crust"], fg=base["subtext0"],
            height=4, relief=tk.FLAT, padx=8, pady=6,
            insertbackground=base["text"],
        )
        self.system_info_text.pack(fill=tk.BOTH, expand=True)

    def _create_dashboard_bar(self, parent, label_text, bar_color):
        base = CATPPUCCIN
        frame = tk.Frame(parent, bg=base["base"])
        frame.pack(fill=tk.X, pady=3)

        # 标签行
        label_row = tk.Frame(frame, bg=base["base"])
        label_row.pack(fill=tk.X)

        tk.Label(label_row, text=label_text, font=("微软雅黑", 9, "bold"),
                 bg=base["base"], fg=base["text"]).pack(side=tk.LEFT)

        pct_label = tk.Label(label_row, text="0%", font=("微软雅黑", 9, "bold"),
                             bg=base["base"], fg=bar_color)
        pct_label.pack(side=tk.RIGHT)

        # 进度条 Canvas
        canvas = tk.Canvas(frame, height=14, bg=base["surface0"],
                           highlightthickness=0, bd=0)
        canvas.pack(fill=tk.X, pady=(2, 0))

        bar_id = canvas.create_rectangle(0, 0, 0, 14, fill=bar_color, outline="")

        result = {
            "canvas": canvas,
            "bar_id": bar_id,
            "pct_label": pct_label,
            "color": bar_color,
        }

        def on_resize(event):
            pct = result.get("_pct", 0)
            bar_w = int(pct * event.width)
            canvas.coords(bar_id, 0, 0, bar_w, 14)

        canvas.bind("<Configure>", on_resize)
        return result

    def _update_bar(self, bar_name, value, max_value=100):
        bar = self._monitor_bars.get(bar_name)
        if not bar:
            return
        pct = min(value / max_value, 1.0) if max_value > 0 else 0
        bar["_pct"] = pct

        canvas = bar["canvas"]
        bar_id = bar["bar_id"]
        pct_label = bar["pct_label"]

        # 颜色根据使用率变化
        base = CATPPUCCIN
        if pct < 0.7:
            color = bar["color"]
        elif pct < 0.9:
            color = base["yellow"]
        else:
            color = base["red"]

        try:
            w = canvas.winfo_width()
            bar_w = int(pct * w)
            canvas.coords(bar_id, 0, 0, bar_w, 14)
            canvas.itemconfig(bar_id, fill=color)
            pct_label.config(text=f"{value:.0f}%", fg=color)
        except Exception:
            pass

    def _refresh_dashboard(self):
        """刷新仪表盘数据"""
        try:
            import platform
            import psutil

            cpu_pct = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            self._update_bar("cpu", cpu_pct)
            self._update_bar("memory", mem.percent)
            self._update_bar("disk", disk.percent)

            info = f"🖥️ {platform.system()} {platform.release()}  |  "
            info += f"💻 {platform.processor()[:40]}\n"
            info += f"🧠 CPU {cpu_pct}%  |  💾 内存 {mem.percent}% ({mem.used//1024**3}/{mem.total//1024**3} GB)  |  "
            info += f"💿 磁盘 {disk.percent}% ({disk.used//1024**3}/{disk.total//1024**3} GB)\n"

            try:
                battery = psutil.sensors_battery()
                if battery:
                    info += f"🔋 电池 {battery.percent}%{' (充电中)' if battery.power_plugged else ''}"
            except Exception:
                pass

            self.system_info_text.config(state=tk.NORMAL)
            self.system_info_text.delete(1.0, tk.END)
            self.system_info_text.insert(tk.END, info)
            self.system_info_text.config(state=tk.DISABLED)
        except Exception as e:
            self.system_info_text.config(state=tk.NORMAL)
            self.system_info_text.delete(1.0, tk.END)
            self.system_info_text.insert(tk.END, f"获取系统信息失败: {e}")
            self.system_info_text.config(state=tk.DISABLED)

        # 自动刷新(5秒)
        if self._built:
            self._monitor_job = self.controller.root.after(5000, self._refresh_dashboard)

    # ─── 系统操作 ──────────────────────────────────────

    def system_operation(self, msg):
        ctrl = self.controller
        msg_lower = msg.lower() if isinstance(msg, str) else ""

        if "关机" in msg and "取消" not in msg:
            if messagebox.askyesno("确认", "确定关机?"):
                subprocess.run(["shutdown", "/s", "/t", "0"], shell=False)
                ctrl.say("系统", "🔴 正在关机...")
        elif "重启" in msg:
            if messagebox.askyesno("确认", "确定重启?"):
                subprocess.run(["shutdown", "/r", "/t", "0"], shell=False)
                ctrl.say("系统", "🔄 正在重启...")
        elif "睡眠" in msg or "休眠" in msg:
            if messagebox.askyesno("确认", "确定进入睡眠模式?"):
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], shell=False)
                ctrl.say("系统", "💤 正在进入睡眠模式...")
        elif "锁定" in msg or "锁屏" in msg:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], shell=False)
            ctrl.say("系统", "🔒 屏幕已锁定")
        elif "注销" in msg:
            if messagebox.askyesno("确认", "确定注销?"):
                subprocess.run(["shutdown", "/l"], shell=False)
                ctrl.say("系统", "👋 正在注销...")
        elif "任务管理器" in msg:
            subprocess.run(["taskmgr"], shell=False)
            ctrl.say("系统", "🖥️ 已打开任务管理器")
        elif "取消关机" in msg or "停止关机" in msg:
            subprocess.run(["shutdown", "/a"], shell=False)
            ctrl.say("系统", "✅ 已取消关机/重启计划")
        else:
            ctrl.say("系统", f"⚠️ 未知系统操作: {msg}")

    def _safe_execute_command(self, action_name, cmd_str):
        ctrl = self.controller
        try:
            import ctypes

            def elevated_run(executable, args=None):
                try:
                    ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", executable, args or "", None, 1
                    )
                    return True
                except Exception:
                    return False

            if action_name == "open_settings":
                subprocess.Popen(["start", "ms-settings:"], shell=True)
            elif action_name == "open_task_manager":
                if not elevated_run("taskmgr.exe"):
                    subprocess.Popen(["taskmgr"], shell=False)
            elif action_name == "open_cmd":
                subprocess.Popen(["cmd"], shell=True)
            elif action_name == "open_powershell":
                if not elevated_run("powershell.exe", "-NoExit -Command Write-Host 'PowerShell 已启动'"):
                    subprocess.Popen(["powershell"], shell=True)
            else:
                subprocess.Popen(cmd_str, shell=True)
            ctrl.say("系统", f"✅ 已执行: {action_name}")
        except Exception as e:
            ctrl.say("系统", f"❌ 执行失败: {e}")

    def custom_command(self, cmd):
        ctrl = self.controller
        safe_commands = {
            "shutdown": ["shutdown", "/s", "/t", "0"],
            "restart": ["shutdown", "/r", "/t", "0"],
            "cancel shutdown": ["shutdown", "/a"],
            "taskmgr": ["taskmgr"],
            "calc": ["calc"],
            "notepad": ["notepad"],
            "cmd": ["cmd", "/c", "echo", "Safe command"],
        }

        cmd_lower = cmd.strip().lower()
        if cmd_lower in safe_commands:
            try:
                args = safe_commands[cmd_lower]
                result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    ctrl.say("系统", f"✅ 命令执行成功:\n{result.stdout}")
                else:
                    ctrl.say("系统", f"❌ 命令执行失败:\n{result.stderr}")
            except subprocess.TimeoutExpired:
                ctrl.say("系统", "❌ 命令执行超时")
            except Exception as e:
                ctrl.say("系统", f"❌ 命令执行异常:{e}")
        else:
            ctrl.say("系统", f"❌ 不允许执行该命令。安全命令列表:{', '.join(safe_commands.keys())}")

    def open_app(self, msg):
        ctrl = self.controller
        app_name = msg.replace("打开", "").replace("启动", "").replace("运行", "").replace("开启", "").strip()

        for app, paths in ctrl.app_paths.items():
            if app in app_name:
                for path in paths:
                    if os.path.exists(path):
                        try:
                            subprocess.Popen([path])
                            ctrl.say("系统", f"✅ 已启动 {app}")
                            return
                        except Exception as e:
                            logger.error(f"启动 {app} 失败: {e}")
                ctrl.say("系统", f"❌ 未找到 {app} 的可执行文件")
                return

        detected_path = ctrl.detect_app_executable(app_name)
        if detected_path and os.path.exists(detected_path):
            try:
                subprocess.Popen([detected_path])
                if app_name not in ctrl.app_paths:
                    ctrl.app_paths[app_name] = []
                if detected_path not in ctrl.app_paths[app_name]:
                    ctrl.app_paths[app_name].append(detected_path)
                    ctrl.config_manager.set("app_paths", ctrl.app_paths)
                ctrl.say("系统", f"✅ 已自动检测并启动 {app_name}")
                logger.info(f"自动检测到应用 {app_name} 路径: {detected_path}")
                return
            except Exception as e:
                logger.error(f"启动 {app_name} 失败: {e}")
                ctrl.say("系统", f"❌ 启动 {app_name} 失败: {e}")
        else:
            ctrl.say("系统", f"❌ 未找到应用: {app_name}")
            if messagebox.askyesno("应用未找到", f"未找到应用 '{app_name}',是否手动添加?"):
                ctrl.add_custom_app()

    def execute_ai_command(self, cmd_data):
        self.controller.execute_ai_command(cmd_data)
