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


class SystemPanel:
    """系统控制面板 - 电源控制、系统工具、音量控制、系统信息"""

    def __init__(self, parent: tk.Widget, controller):
        """构建系统控制标签页

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
        """实际构建系统控制UI"""
        self._loading_label.pack_forget()
        self._built = True

        ctrl = self.controller

        power_frame = ttk.LabelFrame(self.parent, text="电源控制", padding=10)
        power_frame.pack(fill=tk.X, padx=10, pady=10)

        power_row1 = ttk.Frame(power_frame)
        power_row1.pack(fill=tk.X, pady=2)
        ttk.Button(power_row1, text="🔴 关机", command=lambda: self.system_operation("关机"), width=12).pack(side=tk.LEFT, padx=3)
        ttk.Button(power_row1, text="🔄 重启", command=lambda: self.system_operation("重启"), width=12).pack(side=tk.LEFT, padx=3)
        ttk.Button(power_row1, text="💤 睡眠", command=lambda: self.system_operation("睡眠"), width=12).pack(side=tk.LEFT, padx=3)

        power_row2 = ttk.Frame(power_frame)
        power_row2.pack(fill=tk.X, pady=2)
        ttk.Button(power_row2, text="🔒 锁定", command=lambda: self.system_operation("锁定"), width=12).pack(side=tk.LEFT, padx=3)
        ttk.Button(power_row2, text="❌ 取消关机", command=lambda: self.system_operation("取消关机"), width=12).pack(side=tk.LEFT, padx=3)

        tools_frame = ttk.LabelFrame(self.parent, text="系统工具", padding=10)
        tools_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(tools_frame, text="🖥️ 任务管理器", command=lambda: self._safe_execute_command("open_task_manager", "taskmgr"), bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools_frame, text="⚙️ 系统设置", command=lambda: self._safe_execute_command("open_settings", "start ms-settings:"), bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools_frame, text="🖥️ CMD", command=lambda: self._safe_execute_command("open_cmd", "start cmd"), bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(tools_frame, text="💻 PowerShell", command=lambda: self._safe_execute_command("open_powershell", "start powershell"), bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)

        vol_frame = ttk.LabelFrame(self.parent, text="音量控制", padding=10)
        vol_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(vol_frame, text="🔊 增大", command=lambda: self.execute_ai_command({"action": "volume_up"}), bootstyle="info", width=12).pack(side=tk.LEFT, padx=3)
        ttk.Button(vol_frame, text="🔉 减小", command=lambda: self.execute_ai_command({"action": "volume_down"}), bootstyle="info", width=12).pack(side=tk.LEFT, padx=3)
        ttk.Button(vol_frame, text="🔇 静音", command=lambda: self.execute_ai_command({"action": "toggle_mute"}), bootstyle="info", width=12).pack(side=tk.LEFT, padx=3)

        info_frame = ttk.LabelFrame(self.parent, text="系统信息", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.system_info_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg="#1e1e2e", fg="#cdd6f4",
            height=8
        )
        self.system_info_text.pack(fill=tk.BOTH, expand=True)

        ttk.Button(self.parent, text="🔄 刷新信息", command=self._update_system_info).pack(pady=5)

        self._update_system_info()

    def _update_system_info(self):
        """更新系统信息"""
        try:
            import platform
            import psutil

            info = f"🖥️ 系统: {platform.system()} {platform.release()}\n"
            info += f"💻 处理器: {platform.processor()}\n"
            info += f"🧠 内存: {psutil.virtual_memory().percent}% 使用率\n"
            info += f"💾 CPU: {psutil.cpu_percent()}% 使用率\n"
            info += f"📊 磁盘: {psutil.disk_usage('/').percent}% 已用\n"
            info += f"🔋 电池: {psutil.sensors_battery().percent if psutil.sensors_battery() else 'N/A'}%\n"

            self.system_info_text.config(state=tk.NORMAL)
            self.system_info_text.delete(1.0, tk.END)
            self.system_info_text.insert(tk.END, info)
            self.system_info_text.config(state=tk.DISABLED)
        except Exception as e:
            self.system_info_text.config(state=tk.NORMAL)
            self.system_info_text.delete(1.0, tk.END)
            self.system_info_text.insert(tk.END, f"获取系统信息失败: {e}")
            self.system_info_text.config(state=tk.DISABLED)

    def system_operation(self, msg):
        """处理系统操作指令

        Args:
            msg: 操作描述字符串(如"关机"、"重启"等)
        """
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
        """安全执行系统命令 - 自动处理权限提升"""
        ctrl = self.controller
        try:
            import ctypes

            def elevated_run(executable, args=None):
                """以管理员权限运行程序(自动提权)"""
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
        """执行自定义命令(白名单模式)"""
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
        """打开应用程序"""
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
        """执行AI命令 - 委托给 controller"""
        self.controller.execute_ai_command(cmd_data)