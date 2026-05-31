"""
CommandHandler -- 命令解析与执行控制器

将 main.py AppShell 中 ~200 行命令处理逻辑抽离到独立控制器，
支持自然语言命令解析、关键词匹配、参数验证、命令分发。
"""

import re
import os
import logging
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox

logger = logging.getLogger("CommandHandler")


_REQUIRED_AI_PARAMS = {
    # 基本操作
    "open_app": ["app_name"],
    "open_file": ["file_path"],
    "open_folder": ["folder_path"],
    "sort_files": [],
    "find_duplicates": [],
    "find_large": [],
    "clean_empty": [],
    "rename_files": ["pattern"],
    "rename": ["description"],
    "list_files": [],
    "ai_chat": [],
    # 系统控制
    "shutdown": [],
    "restart": [],
    "logout": [],
    "sleep": [],
    "lock": [],
    "hibernate": [],
    "turn_off_display": [],
    "cancel_shutdown": [],
    # 微信相关
    "send_wechat": ["target", "message"],
    "schedule_wechat": ["target", "message", "send_time"],
    "start_listening": [],
    "stop_listening": [],
    # 定时任务
    "schedule_task": ["task", "send_time"],
    # 自动化任务
    "run_automation": ["task_name"],
    # 自定义命令
    "custom_command": ["command"],
    # 进程管理
    "kill_process": [],
    "list_processes": [],
    # 窗口管理
    "minimize_window": ["window_title"],
    "maximize_window": ["window_title"],
    "close_window": ["window_title"],
    "activate_window": ["window_title"],
    "list_windows": [],
    # 音量控制
    "volume_up": [],
    "volume_down": [],
    "set_volume": ["level"],
    "toggle_mute": [],
    # 截图和剪贴板
    "take_screenshot": [],
    "get_clipboard": [],
    "set_clipboard": ["content"],
    # 系统信息
    "get_system_info": [],
    "get_network_info": [],
    "get_cpu_usage": [],
    "get_memory_usage": [],
    "get_disk_usage": [],
    "get_battery_status": [],
    # 网络控制
    "toggle_wifi": [],
    "disconnect_network": [],
    "connect_network": [],
    "ping_host": ["host"],
    "get_ip_address": [],
    # 文件操作
    "delete_file": ["file_path"],
    "move_file": ["source", "destination"],
    "copy_file": ["source", "destination"],
    "create_folder": ["folder_path"],
    "delete_folder": ["folder_path"],
    "read_file": ["file_path"],
    "write_file": ["file_path", "content"],
    # 浏览器控制
    "open_browser": [],
    "close_browser": [],
    "navigate_url": ["url"],
    "refresh_page": [],
    "go_back": [],
    "go_forward": [],
    # 输入模拟
    "type_text": ["text"],
    "press_key": ["key"],
    "move_mouse": ["x", "y"],
    "click_mouse": ["x", "y"],
    "scroll": ["amount"],
    # 媒体控制
    "play_media": [],
    "pause_media": [],
    "next_track": [],
    "prev_track": [],
    # 系统工具
    "open_settings": [],
    "open_control_panel": [],
    "open_task_manager": [],
    "open_cmd": [],
    "open_powershell": [],
    "open_explorer": [],
    "open_notepad": [],
    "open_calculator": [],
    "open_camera": [],
    # 时间日期
    "get_current_time": [],
    "get_current_date": [],
    # 回收站
    "empty_recycle_bin": [],
    # 桌面操作
    "show_desktop": [],
    "show_start_menu": [],
    "switch_user": [],
    # 拍照录屏
    "take_photo": [],
    "record_screen": [],
    "stop_recording": [],
    # 天气闹钟
    "get_weather": ["city"],
    "set_alarm": ["time"],
    # AI智能体
    "ai_agent": ["task"],
    # 语音合成
    "speak_text": ["text"],
}


QUICK_PARSE_PATTERNS = [
    (r"(取消关机|cancel\s*shutdown)", "cancel_shutdown", {}),
    (r"(定时关机|timer\s*shutdown)", "timer_shutdown", {}),
    (r"(定时重启|timer\s*restart)", "timer_restart", {}),
    (r"(关机|shutdown)", "shutdown", {}),
    (r"(重启|restart|reboot)", "restart", {}),
    (r"(睡眠|sleep)", "sleep", {}),
    (r"(锁定|锁屏|lock)", "lock", {}),
    (r"(注销|log\s*out)", "logout", {}),
    (r"(休眠|hibernat)", "hibernate", {}),
    (r"(任务管理器|task\s*man)", "open_task_manager", {}),
    (r"整理\s*(文件|桌面|下载)", "sort_files", {}),
    (r"(查重|重复|duplicate)\s*(文件)?", "find_duplicates", {}),
    (r"大文件\s*(\d+)?\s*(GB|G|gb|g)?", "find_large", {}),
    (r"(清理|删除)\s*空文件", "clean_empty", {}),
    (r"(列出|显示)\s*文件", "list_files", {}),
    (r"重命名\s*(文件|文件夹)?\s*[：:]\s*(.+)", "rename", {}),
    (r"打开\s*(.+?)(?:\s|$)", "open_app", {}),
    (r"启动\s*(.+?)(?:\s|$)", "open_app", {}),
    (r"运行\s*(.+?)(?:\s|$)", "open_app", {}),
    (r"搜索\s*(.+?)(?:\s|$)", "search", {}),
    (r"百度\s*(.+?)(?:\s|$)", "search", {}),
    (r"(扫描|查看|列出)\s*(电脑|系统|本机|我).{0,5}(软件|程序|应用)", "list_installed_software", {}),
    (r"(电脑|系统|本机|我).{0,5}(有哪些|有什么)(软件|程序|应用)", "list_installed_software", {}),
    (r"已?安装.{0,3}(软件|程序|应用)", "list_installed_software", {}),
]


class CommandHandler:
    """命令解析与执行处理器

    从 AppShell 中抽离，负责：
    1. 快速正则匹配 (quick_parse_command)
    2. 参数完整性验证 (_validate_ai_result)
    3. 关键词回退解析 (fallback_keyword_parse)
    4. 命令分发执行 (execute_ai_command / _execute_quick_action)
    """

    def __init__(self, controller):
        """
        Args:
            controller: AppShell 主控制器实例
        """
        self.ctrl = controller

    # ---------- 快速正则匹配 ----------

    def quick_parse_command(self, msg):
        """快速解析常见命令模式，返回(action, params)或None"""
        msg_lower = msg.lower().strip()
        for pattern, action, default_params in QUICK_PARSE_PATTERNS:
            m = re.search(pattern, msg_lower)
            if m:
                params = dict(default_params)
                if m.groups():
                    for i, g in enumerate(m.groups()):
                        if g:
                            params[f"arg{i}"] = g.strip()
                    if action == "open_app":
                        params["app_name"] = m.group(1).strip()
                    elif action == "rename":
                        idx = m.lastindex if hasattr(m, "lastindex") else 0
                        params["pattern"] = m.group(2).strip() if idx >= 2 else ""
                    elif action == "search":
                        params["query"] = m.group(1).strip()
                return action, params
        return None

    # ---------- 参数验证 ----------

    def _validate_ai_result(self, result):
        """验证AI解析结果是否包含必要参数"""
        if not result or "action" not in result:
            return False
        action = result.get("action")
        if action not in _REQUIRED_AI_PARAMS:
            return False
        for param in _REQUIRED_AI_PARAMS[action]:
            if param not in result or not result[param]:
                return False
        return True

    # ---------- 关键词回退解析 ----------

    def fallback_keyword_parse(self, msg):
        """关键词匹配解析（作为AI的后备方案）"""
        quick_result = self.quick_parse_command(msg)
        if quick_result:
            action, params = quick_result
            self._execute_quick_action(action, params)
            return

        msg_lower = msg.lower().strip()
        ctrl = self.ctrl

        if any(k in msg_lower for k in ["按类型整理", "分类", "排序"]):
            self.execute_ai_command({"action": "sort_files"})
        elif any(k in msg_lower for k in ["重复文件", "去重"]):
            self.execute_ai_command({"action": "find_duplicates"})
        elif any(k in msg_lower for k in ["空文件"]):
            self.execute_ai_command({"action": "clean_empty"})
        elif any(k in msg_lower for k in ["大文件", "占用空间"]):
            self.execute_ai_command({"action": "find_large"})
        elif any(k in msg_lower for k in ["改名", "重命名", "序号", "替换"]):
            self.execute_ai_command({"action": "rename", "description": msg})
        elif any(k in msg_lower for k in ["打开", "启动", "运行", "开启"]):
            self.execute_ai_command({"action": "open_app", "app_name": msg})
        elif any(k in msg_lower for k in ["列出", "显示", "查看", "文件", "内容", "有什么"]):
            self.execute_ai_command({"action": "list_files"})
        elif any(k in msg_lower for k in ["关机", "重启", "注销", "任务管理器", "取消关机"]):
            self.execute_ai_command({"action": "system_operation", "operation": msg})
        elif "执行命令" in msg_lower:
            cmd = msg.replace("执行命令:", "").strip()
            self.execute_ai_command({"action": "custom_command", "command": cmd})
        elif "ai助手" in msg_lower:
            ctrl.ai_chat_dialog()
        elif "开始监听" in msg_lower:
            self.execute_ai_command({"action": "start_listening"})
        elif "停止监听" in msg_lower:
            if getattr(ctrl, "wechat_listener_running", False):
                self.execute_ai_command({"action": "stop_listening"})
        elif any(k in msg_lower for k in ["天气"]):
            ctrl.say("AI管家", "请告诉我城市名称，我来查询天气。")
        elif any(k in msg_lower for k in ["报时", "几点"]):
            from datetime import datetime
            ctrl.say("AI管家", f"现在是 {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}")
        elif any(k in msg_lower for k in ["版本"]):
            ctrl.say("AI管家", "AI电脑管家 v8.0 | DeepSeek V4 + Hermes 双引擎")
        else:
            ctrl.say("AI管家", "抱歉，我还不太理解您的意思。\n可以试试: 帮我写代码 / 分析文件 / 整理桌面 / 定时任务")

    # ---------- 快速操作执行 ----------

    def _execute_quick_action(self, action, params):
        """执行快速操作按钮 - 统一通过 execute_command 调度"""
        try:
            from main import execute_command
            cmd_data = dict(params) if params else {}
            cmd_data["action"] = action
            execute_command(action, self.ctrl, cmd_data)
        except KeyError:
            self.ctrl.say("AI管家", f"无法执行该操作（未知操作类型:{action}）。")
        except Exception as e:
            logger.error(f"快速操作执行失败 [{action}]: {e}", exc_info=True)
            self.ctrl.say("系统", f"ERROR 执行失败: {str(e)}")

    # ---------- AI命令执行 ----------

    def execute_ai_command(self, result):
        """执行AI解析后的命令"""
        try:
            action = result.get("action", "")
            from main import execute_command
            execute_command(action, self.ctrl, result)
        except Exception as e:
            logger.error(f"执行AI命令失败: {e}")
            self.ctrl.say("系统", f"命令执行失败: {e}")

    # ---------- 应用工具 ----------

    def detect_app_executable(self, app_name):
        """检测应用可执行文件路径"""
        app_name_lower = app_name.lower()
        ctrl = self.ctrl
        for name, paths in ctrl.app_paths.items():
            if app_name_lower in name.lower() or name.lower() in app_name_lower:
                # app_paths 值可能是 str 或 list[str]
                candidates = paths if isinstance(paths, list) else [paths]
                for path in candidates:
                    path = path.replace("/", "\\")
                    if os.path.exists(path):
                        return path
        common_paths = [
            os.path.expandvars(r"%ProgramFiles%"),
            os.path.expandvars(r"%ProgramFiles(x86)%"),
            os.path.expandvars(r"%LOCALAPPDATA%"),
            os.path.expandvars(r"%APPDATA%"),
        ]
        for base in common_paths:
            if not os.path.exists(base):
                continue
            for root, dirs, files in os.walk(base):
                depth = root.replace(base, "").count(os.sep)
                if depth > 2:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower().endswith(".exe") and app_name_lower in f.lower():
                        return os.path.join(root, f)
        return None

    def add_custom_app(self):
        """添加自定义应用"""
        ctrl = self.ctrl
        app_name = simpledialog.askstring("添加应用", "应用名称:", parent=ctrl.root)
        if not app_name:
            return
        app_path = filedialog.askopenfilename(
            title=f"选择 {app_name} 的可执行文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if app_path:
            ctrl.app_paths[app_name] = app_path
            ctrl.config_manager.set("app_paths", ctrl.app_paths)
            ctrl.say("系统", f"已添加应用: {app_name}")

    def list_custom_apps(self):
        """显示已添加的应用列表"""
        ctrl = self.ctrl
        apps = ctrl.app_paths
        if not apps:
            ctrl.say("系统", "暂无自定义应用")
            return
        lines = ["已添加的应用:"]
        for name, path in apps.items():
            exists = "OK" if os.path.exists(path) else "X"
            lines.append(f"  {exists} {name}: {path}")
        ctrl.say("系统", "\n".join(lines))
