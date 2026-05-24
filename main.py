import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, ttk, simpledialog
import os
import subprocess
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
import re

# 导入模块化组件
from utils.config import ConfigManager
from utils.helpers import register_dependency
from modules.file_manager import FileManager
from modules.ai_helper import AIHelper
from modules.wechat_controller import WeChatController, OCR_AVAILABLE
from modules.task_scheduler import TaskScheduler
try:
    from modules.macro_recorder import PYAUTOGUI_AVAILABLE, get_recorder, get_player
    MACRO_AVAILABLE = PYAUTOGUI_AVAILABLE
except ImportError:
    MACRO_AVAILABLE = False
    get_recorder = None
    get_player = None
    PYAUTOGUI_AVAILABLE = False
from modules.ai_agent import get_ai_agent
from modules.social_skills import SocialSkills
from modules.conversation_memory import ConversationMemory
from modules.system_controller import get_system_controller
from modules.knowledge_base_builder import KnowledgeBaseBuilder
from modules.email_classifier import EmailClassifier
from modules.ui_manager import init_ui_manager
# Hermes 桥接 (已优化, 旧版本 hermes_bridge.py 已移除)
from modules.hermes_bridge_optimized import get_hermes_bridge_optimized, get_hermes_ai_helper_optimized
from core.command_registry import execute_command
from controllers import AppController
from controllers.message_router import MessageRouter
from controllers.command_handler import CommandHandler
from panels import ChatPanel, FilePanel, SystemPanel, WeChatPanel, AutomationPanel
import traceback

try:
    import win32api
    import win32con
except ImportError:
    win32api = None
    win32con = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

# 静默注册可选依赖(失败不打印警告)
_optional_deps = [
    "pyautogui", "pyperclip", "pygetwindow", "requests", "yagmail",
    "selenium", "pandas", "openpyxl", "speech_recognition", "deep_translator",
    "pytesseract", "PIL", "matplotlib", "bs4", "ttkbootstrap"
]
for dep in _optional_deps:
    register_dependency(dep)

try:
    from ttkbootstrap import Style
    USE_BOOTSTRAP = True
except ImportError:
    USE_BOOTSTRAP = False
    Style = None
    logging.warning("ttkbootstrap未安装,将使用ttk主题")

# 配置日志
log_path = Path.home() / "aipc_helper.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=3, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AIPCHelper")

class AppShell:
    """AI电脑管家 8.0 模块化版本 - Shell架构"""

    def __init__(self, root):
        self.root = root
        self.root.title("Hermes | AI电脑管家 8.0")
        # 恢复上次窗口位置
        self._restore_geometry()
        self.root.minsize(900, 600)
        self.root.resizable(True, True)

        # 注册全局异常处理器，防止闪退
        self.root.report_callback_exception = self._report_callback_exception

        # 初始化模块
        self.config_manager = ConfigManager()
        self.file_manager = FileManager()
        self.ui_manager = init_ui_manager(self.root)
        self.ai_helper = AIHelper(
            self.config_manager.get("ollama_url", "http://localhost:11434/api/generate"),
            self.config_manager.get("model", "qwen2.5:1.5b"),
            self.config_manager
        )
        # AI相关配置
        self.model = self.config_manager.get("model", "qwen2.5:1.5b")
        self.ollama_url = self.config_manager.get("ollama_url", "http://localhost:11434/api/generate")
        self.api_key = None  # 保留向后兼容

        # ========== 延迟初始化模块(按需加载,加速启动)==========
        self._wechat_controller = None
        self._task_scheduler = None
        self._social_skills = None
        self._knowledge_base_builder = None
        self._email_classifier = None
        self._conversation_memory = None
        self._system_controller = None
        self._hermes_bridge = None
        self._hermes_ai = None
        self._agent_service = None
        self._streaming_manager = None  # 流式输出管理器(懒加载)

        # 立即初始化核心模块(轻量级)
        self.use_hermes = self.config_manager.get("use_hermes", False)

        self.app_controller = AppController(self.config_manager)
        self.message_router = MessageRouter()
        self.command_handler = CommandHandler(self)

        # 后台线程加载重模块
        self._init_thread = threading.Thread(target=self._lazy_init_modules, daemon=True)
        self._init_thread.start()

        # 完成剩余的初始化(主题、UI构建等)
        self._finish_init()

    def _lazy_init_modules(self):
        """后台线程延迟初始化重模块"""
        try:
            # 初始化系统控制器
            self._system_controller = get_system_controller()

            # 初始化对话记忆
            self._conversation_memory = ConversationMemory(
                config_manager=self.config_manager
            )
            self._conversation_memory.integrate_with_ai_helper(self.ai_helper)

            # 初始化统一 AgentService(Hermes + Ollama + AIAgentCore)
            try:
                from services.agent_service import get_agent_service
                self._agent_service = get_agent_service()
                self._agent_service.initialize(self.config_manager)
                status = self._agent_service.get_status()

                if status.get("hermes"):
                    self.use_hermes = True
                    hermes_detail = status.get("hermes_detail", {})
                    caps = hermes_detail.get("capabilities", [])
                    logger.info(
                        f"✨ Hermes 已就绪 (v{hermes_detail.get('version', '?')}, "
                        f"能力: {', '.join(caps) if caps else '基础'})"
                    )
                    self.root.after(0, self._safe_status_update,
                        f"✅ Hermes 已就绪 | 能力: {len(caps)}", "#a6e3a1")
                    try:
                        self.hermes_bridge._ensure_checked()
                    except Exception:
                        pass
                    self.root.after(500, lambda: self._safe_status_update(
                        f"✅ Hermes v{hermes_detail.get('version', '?')}", "#a6e3a1"))
                elif status.get("ollama"):
                    logger.info("Ollama 已就绪")
                    self.root.after(0, self._safe_status_update,
                        "✅ Ollama 已就绪", "green")
                else:
                    logger.warning("无可用 AI 后端")
                    self.root.after(0, self._safe_status_update,
                        "⚠️ 无可用 AI 后端", "orange")

                logger.info(
                    f"AgentService 已初始化,后端: {self._agent_service.get_preferred_backend()}"
                )
            except Exception as e:
                logger.warning(f"AgentService 初始化失败: {e}")

            logger.info("后台初始化完成")
        except Exception as e:
            logger.error(f"后台初始化失败: {e}")

    def _safe_status_update(self, text: str, color: str = "green"):
        """安全更新状态标签(防止 UI 未就绪时崩溃)"""
        if hasattr(self, 'status_label') and self.status_label is not None:
            try:
                self.status_label.config(text=text, foreground=color)
            except Exception:
                pass

    @property
    def hermes_bridge(self):
        if self._hermes_bridge is None:
            self._hermes_bridge = get_hermes_bridge_optimized()
        return self._hermes_bridge

    @property
    def hermes_ai(self):
        if self._hermes_ai is None:
            self._hermes_ai = get_hermes_ai_helper_optimized(self.config_manager)
        return self._hermes_ai

    @property
    def agent_service(self):
        if self._agent_service is None:
            try:
                from services.agent_service import get_agent_service
                self._agent_service = get_agent_service()
                self._agent_service.initialize(self.config_manager)
            except Exception as e:
                logger.warning(f"AgentService 延迟加载失败: {e}")
        return self._agent_service

    @property
    def wechat_controller(self):
        if self._wechat_controller is None:
            self._init_wechat()
        return self._wechat_controller

    def _init_wechat(self):
        """初始化微信控制器(首次使用时调用)"""
        self._wechat_controller = WeChatController(
            self.config_manager.get("wechat_contact", "文件传输助手"),
            self.config_manager.get("wechat_check_interval", 10),
            self.config_manager.get("use_ocr", True),
            self.config_manager.get("debug_mode", False),
            callback=lambda msg: self.say("微信", msg),
            root=self.root
        )

        # 加载保存的坐标
        saved_coords = self.config_manager.get("last_msg_pos", None)
        if saved_coords:
            self._wechat_controller.last_msg_pos = saved_coords
        saved_search_coords = self.config_manager.get("search_pos", None)
        if saved_search_coords:
            self._wechat_controller.search_pos = saved_search_coords
        saved_ocr_region = self.config_manager.get("ocr_region", None)
        if saved_ocr_region:
            self._wechat_controller.ocr_region = saved_ocr_region
        tesseract_path = self.config_manager.get("tesseract_cmd", None)
        if tesseract_path:
            self._wechat_controller.tesseract_cmd = tesseract_path

        # 同步任务调度器的微信控制器
        if self._task_scheduler:
            self._task_scheduler.wechat_controller = self._wechat_controller

    @property
    def task_scheduler(self):
        if self._task_scheduler is None:
            self._task_scheduler = TaskScheduler()
            self._task_scheduler.set_callback(
                lambda msg, is_err: self.root.after(0, lambda: self.say("系统", msg))
            )
            if self._wechat_controller:
                self._task_scheduler.wechat_controller = self._wechat_controller
        return self._task_scheduler

    @property
    def social_skills(self):
        if self._social_skills is None:
            self._social_skills = SocialSkills(
                wechat_controller=self.wechat_controller,
                config_manager=self.config_manager
            )
        return self._social_skills

    @property
    def knowledge_base_builder(self):
        if self._knowledge_base_builder is None:
            self._knowledge_base_builder = KnowledgeBaseBuilder(
                config_manager=self.config_manager
            )
        return self._knowledge_base_builder

    @property
    def email_classifier(self):
        if self._email_classifier is None:
            self._email_classifier = EmailClassifier(
                config_manager=self.config_manager,
                knowledge_base_builder=self.knowledge_base_builder,
                social_skills=self.social_skills
            )
        return self._email_classifier

    @property
    def conversation_memory(self):
        if self._conversation_memory is None:
            self._conversation_memory = ConversationMemory(
                config_manager=self.config_manager
            )
            self._conversation_memory.integrate_with_ai_helper(self.ai_helper)
        return self._conversation_memory

    @property
    def system_controller(self):
        if self._system_controller is None:
            self._system_controller = get_system_controller()
        return self._system_controller

    def _finish_init(self):
        """完成剩余的初始化工作(在 __init__ 末尾调用)"""
        # 加载配置
        self.app_paths = self.config_manager.get("app_paths", self.config_manager.get_default_app_paths())
        self.scheduled_tasks = self.config_manager.get("scheduled_tasks", [])
        self.current_folder = self.config_manager.get("current_folder", str(Path.home() / "Desktop"))
        self.use_ai_features = self.config_manager.get("use_ai_features", True)
        self.ai_helper.use_ai_features = self.use_ai_features
        self.rename_history = []
        self.running = True

        # AI助手对话历史
        self.ai_chat_history = []

        # 微信监听相关
        self.wechat_listener_running = False
        self.wechat_listener_thread = None
        self.listener_lock = threading.Lock()  # 全局锁,用于保护微信监听状态
        self.command_prefix = self.config_manager.get("command_prefix", "¥")  # 指令前缀
        self.listener_paused = False  # 监听暂停标志

        # 设置主题
        self.setup_theme()

        # 构建界面
        self._build_shell_ui()

        # 启动定时任务调度器
        self.task_scheduler.start_scheduler()

        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 显示欢迎消息
        self.say("AI管家",
            "━━━ 🖥️ AI电脑管家 · 功能概览 ━━━\n\n"
            "💬 智能对话 - AI聊天、任务执行、模型切换\n"
            "📁 文件管理 - 智能整理、查重、大文件扫描\n"
            "⚙️ 系统控制 - 关机重启、任务管理器、音量调节\n"
            "📱 微信通讯 - 消息监听、定时发送、远程指令\n"
            "🤖 自动化 - 宏录制、定时任务、编程工作区\n\n"
            "━━━ ⚡ 核心引擎 ━━━\n"
            "🧠 模型: DeepSeek V4 Flash/Pro · 智能切换\n"
            "💡 输入自然语言即可操控电脑\n"
            "🔄 自动路由: 简单任务→本地 · 复杂任务→云端\n\n"
            "🔹 输入框直接提问或下达指令\n"
            "🔹 点击 🤖 Hermes 切换云端 AI 引擎\n"
            "🔹 点击 🔄 自动 开启智能模型切换")

    # ---------- 主题设置 ----------
    def setup_theme(self):
        if USE_BOOTSTRAP:
            self.style = Style(theme="darkly")
            # 自定义 ttkbootstrap 配置
            self.style.configure('TNotebook.Tab', font=('微软雅黑', 10), padding=[12, 6])
            self.style.configure('TLabelframe.Label', font=('微软雅黑', 9, 'bold'))
            self.style.configure('TLabel', font=('微软雅黑', 9))
            self.style.configure('TButton', font=('微软雅黑', 9))
            self.style.configure('Treeview', rowheight=28, font=('微软雅黑', 9))
        else:
            # 先设置 Tk 根窗口背景(tk 组件,不受 ttk.Style 控制)
            self.root.configure(bg='#1e1e2e')

            self.style = ttk.Style()
            self.style.theme_use('clam')
            self.style.configure('.', background='#1e1e2e', foreground='#cdd6f4')
            self.style.configure('TButton', background='#313244', foreground='#cdd6f4')
            self.style.configure('TEntry', background='#313244', foreground='#cdd6f4', fieldbackground='#313244')
            self.style.configure('TLabel', background='#1e1e2e', foreground='#cdd6f4')
            self.style.configure('TFrame', background='#1e1e2e')
            self.style.configure('TLabelframe', background='#1e1e2e', foreground='#cdd6f4')
            self.style.configure('TLabelframe.Label', background='#1e1e2e', foreground='#cdd6f4')
            self.style.map('TCombobox',
                fieldbackground=[('readonly', '#313244')],
                background=[('readonly', '#313244')],
                foreground=[('readonly', '#cdd6f4')])

    def create_scrollable_frame(self, parent):
        """创建可滚动的框架"""
        canvas = tk.Canvas(parent, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style='TFrame')

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        return scrollable_frame

    def create_scrollable_window(self, title, width=600, height=500):
        """创建可滚动的窗口"""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(f"{width}x{height}")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)
        win.grab_set()

        main_frame = ttk.Frame(win)
        main_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(main_frame, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        content_frame = ttk.Frame(canvas, style='TFrame')

        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except tk.TclError:
                pass
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        return win, content_frame

    # ---------- 界面构建 ----------
    def _build_shell_ui(self):
        """构建主界面 - Shell架构,使用Panel组件"""

        # ========== 顶部状态栏 ==========
        self._build_status_bar()

        # ========== 核心功能区(标签页) ==========
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self._tab_built = {"file": False, "system": False, "wechat": False, "auto": False}

        self.chat_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.chat_tab, text="💬 智能对话")
        self.chat_panel = ChatPanel(self.chat_tab, self)

        self.file_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.file_tab, text="📁 文件管理")

        self.system_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.system_tab, text="⚙️ 系统控制")

        self.wechat_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.wechat_tab, text="📱 微信通讯")

        self.auto_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.auto_tab, text="🤖 自动化")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # 全局快捷键
        self.root.bind("<Control-q>", lambda e: self.on_closing())
        self.root.bind("<Control-Q>", lambda e: self.on_closing())
        self.root.bind("<Control-Tab>", self._switch_tab_next)
        self.root.bind("<Control-ISO_Left_Tab>", self._switch_tab_prev)
        self.root.bind("<Control-Shift-Tab>", self._switch_tab_prev)

        # ========== 底部状态栏 ==========
        self._build_bottom_status()

    def _build_status_bar(self):
        """构建顶部状态栏"""
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, padx=10, pady=(8, 2))

        self.status_label = ttk.Label(
            self.status_frame, text="✅ 就绪",
            font=("微软雅黑", 10, "bold")
        )
        self.status_label.pack(side=tk.LEFT)

        self._cancel_btn = ttk.Button(
            self.status_frame, text="⏹ 停止", command=self._cancel_hermes,
            width=8
        )

        ttk.Separator(self.status_frame, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self.folder_label = ttk.Label(
            self.status_frame, text=f"📁 {self.current_folder}",
            foreground="gray", font=("微软雅黑", 9)
        )
        self.folder_label.pack(side=tk.RIGHT)

    def _on_tab_changed(self, event=None):
        """标签切换 - 首次点击时按需实例化Panel"""
        idx = self.notebook.index("current")
        tab_names = ["chat", "file", "system", "wechat", "auto"]
        if idx >= len(tab_names):
            return

        tab = tab_names[idx]

        if tab == "file" and not self._tab_built.get("file"):
            self._tab_built["file"] = True
            self.file_panel = FilePanel(self.file_tab, self)
        elif tab == "system" and not self._tab_built.get("system"):
            self._tab_built["system"] = True
            self.system_panel = SystemPanel(self.system_tab, self)
        elif tab == "wechat" and not self._tab_built.get("wechat"):
            self._tab_built["wechat"] = True
            self.wechat_panel = WeChatPanel(self.wechat_tab, self)
        elif tab == "auto" and not self._tab_built.get("auto"):
            self._tab_built["auto"] = True
            self.automation_panel = AutomationPanel(self.auto_tab, self)

    def _build_bottom_status(self):
        """构建底部状态栏"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=(2, 8))

        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X, padx=10)

        self.hermes_status_label = ttk.Label(
            status_frame,
            text="Hermes: ⏳ 检查中...",
            font=("微软雅黑", 8),
            foreground="#888888"
        )
        self.hermes_status_label.pack(side=tk.LEFT, padx=5)
        self.root.after(500, lambda: self._safe_status_update("Hermes 状态: 运行中" if self.use_hermes else "Hermes 状态: 未启用"))

        ttk.Separator(status_frame, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ai_engine = "Hermes" if self.use_hermes else "Ollama"
        self.ai_engine_label = ttk.Label(
            status_frame,
            text=f"AI引擎: {ai_engine}",
            font=("微软雅黑", 8)
        )
        self.ai_engine_label.pack(side=tk.LEFT, padx=5)

        version_label = ttk.Label(
            status_frame,
            text="v8.0",
            font=("微软雅黑", 8),
            foreground="gray"
        )
        version_label.pack(side=tk.RIGHT, padx=5)

        # 快捷键提示
        ttk.Separator(status_frame, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=5)
        shortcuts_hint = ttk.Label(
            status_frame,
            text="Ctrl+Tab 切标签 | Ctrl+N 新建 | Ctrl+Q 退出",
            font=("微软雅黑", 7),
            foreground="#6c7086"
        )
        shortcuts_hint.pack(side=tk.LEFT, padx=5)

    # ---------- 消息显示 ----------
    def say(self, who, what):
        """线程安全的消息显示方法"""
        try:
            # 检查是否在主线程中
            if threading.current_thread() is not threading.main_thread():
                # 非主线程,通过 after 调度到主线程
                self.root.after(0, lambda: self._say(who, what))
            else:
                # 主线程,直接执行
                self._say(who, what)
        except Exception as e:
            print(f"say 方法异常:{e}")

    def _report_callback_exception(self, exc, val, tb):
        """全局异常回调 - 防止 Tkinter 异常导致闪退"""
        import traceback
        logger.error(f"[Tkinter 异常] {exc.__name__}: {val}\n{traceback.format_exception(exc, val, tb)}")
        try:
            from tkinter import messagebox
            messagebox.showerror("运行时错误", f"{exc.__name__}: {val}\n\n应用将继续运行。")
        except Exception:
            pass

    def _say(self, who, what):
        """内部方法:实际更新 UI"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(self, 'chat_panel') and self.chat_panel is not None:
            chat = self.chat_panel.chat
            chat.config(state=tk.NORMAL)
            chat.insert(tk.END, f"[{timestamp}] [{who}] {what}\n\n")
            chat.config(state=tk.DISABLED)
            chat.see(tk.END)

    def _parse_time_to_minutes(self, time_str):
        """将时间字符串转换为分钟"""
        time_str = time_str.lower()
        num_match = re.search(r"(\d+)", time_str)
        if not num_match:
            return 0
        num = int(num_match.group(1))
        if "小时" in time_str or "时" in time_str:
            return num * 60
        elif "秒" in time_str:
            return max(1, num // 60)
        return num

    def do_task(self, msg):
        """处理用户输入的自然语言指令,优先使用AI处理"""
        msg = msg.strip()
        if not msg:
            return

        # 首先尝试AI处理(自然语言理解)
        if self.use_ai_features:
            self.say("系统", "🤔 正在理解您的指令...")

            # 使用AI解析命令 - 在后台线程中执行,避免阻塞GUI
            def ai_process():
                try:
                    result, clarification = self.ai_helper.parse_command_with_clarification(msg)

                    if result:
                        if self._validate_ai_result(result):
                            # 使用 after 确保在主线程中执行GUI更新
                            self.root.after(0, lambda: self.execute_ai_command(result))
                        else:
                            # 参数不完整,回退到关键词匹配
                            self.root.after(0, lambda: self._fallback_keyword_parse(msg))
                    else:
                        # AI无法解析,尝试关键词匹配作为后备
                        self.root.after(0, lambda: self._fallback_keyword_parse(msg))
                except Exception as e:
                    logger.error(f"AI处理异常: {e}")
                    self.root.after(0, lambda: self._fallback_keyword_parse(msg))

            threading.Thread(target=ai_process, daemon=True).start()
        else:
            # AI功能未启用,使用关键词匹配
            self._fallback_keyword_parse(msg)

    def _ask_user_confirmation(self, original_msg, result, clarification):
        """询问用户确认AI的理解是否正确"""
        if not clarification:
            # 没有不确定的地方,直接执行
            self.execute_ai_command(result)
            return

        # 显示AI的理解和不确定的地方
        action = result.get("action", "未知") if result else "未知"
        details = result.get("action_details", "") if result else ""

        # 构建确认消息
        confirm_msg = f"我理解您想:{action}"
        if details:
            confirm_msg += f"\n详情:{details}"

        if clarification:
            confirm_msg += f"\n\n⚠️ 但我不太确定:{clarification}"

        confirm_msg += f"\n\n请问您想执行这个操作吗?"

        # 弹出确认对话框
        from tkinter import messagebox
        if messagebox.askyesno("确认指令", confirm_msg):
            # 用户确认,执行命令
            self.execute_ai_command(result)
        else:
            # 用户取消,询问更多细节
            self.say("系统", "请告诉我更多细节,例如:具体要打开什么应用?发给谁?")

    def _fallback_keyword_parse(self, msg):
        """关键词匹配解析(作为AI的后备方案)"""
        self.command_handler.fallback_keyword_parse(msg)

    def _execute_quick_action(self, action, params):
        """执行快速操作按钮 - 委托给 CommandHandler"""
        self.command_handler._execute_quick_action(action, params)

    # _REQUIRED_AI_PARAMS 已迁移到 controllers/command_handler.py
    _REQUIRED_AI_PARAMS = {}  # 向后兼容引用

    def _validate_ai_result(self, result):
        """验证AI解析结果是否包含必要参数"""
        return self.command_handler._validate_ai_result(result)

    def quick_parse_command(self, msg):
        """快速解析常见命令模式,返回(action, params)或None"""
        return self.command_handler.quick_parse_command(msg)

    def _process_ai_command(self, msg):
        """处理AI解析后的命令结果"""
        try:
            result, clarification = self.ai_helper.parse_command_with_clarification(msg)
            if result:
                if self._validate_ai_result(result):
                    self.execute_ai_command(result)
                else:
                    self._fallback_keyword_parse(msg)
            else:
                self._fallback_keyword_parse(msg)
        except Exception as e:
            logger.error(f"AI命令处理异常: {e}")
            self._fallback_keyword_parse(msg)

    def execute_ai_command(self, result):
        """执行AI解析后的命令"""
        self.command_handler.execute_ai_command(result)

    def detect_app_executable(self, app_name):
        """检测应用可执行文件路径"""
        return self.command_handler.detect_app_executable(app_name)

    def add_custom_app(self):
        """添加自定义应用"""
        self.command_handler.add_custom_app()

    def list_custom_apps(self):
        """显示已添加的应用列表"""
        self.command_handler.list_custom_apps()

    def ai_chat_dialog(self):
        """AI对话窗口"""
        win = tk.Toplevel(self.root)
        win.title("AI 对话")
        win.geometry("600x500")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        text_area = scrolledtext.ScrolledText(
            win, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 10), bg="#1e1e2e", fg="#cdd6f4"
        )
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        input_frame = ttk.Frame(win)
        input_frame.pack(fill=tk.X, padx=10, pady=5)

        entry = ttk.Entry(input_frame, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def send():
            question = entry.get().strip()
            if not question:
                return
            text_area.config(state=tk.NORMAL)
            text_area.insert(tk.END, f"你: {question}\n")
            text_area.config(state=tk.DISABLED)
            entry.delete(0, tk.END)

            def ai_respond():
                try:
                    response = self.hermes_ai.chat(message=question, timeout=60)
                    if response:
                        self.root.after(0, lambda: _show_response(response))
                    else:
                        self.root.after(0, lambda: _show_response("AI 未返回响应"))
                except Exception as e:
                    self.root.after(0, lambda: _show_response(f"错误: {e}"))

            def _show_response(text):
                text_area.config(state=tk.NORMAL)
                text_area.insert(tk.END, f"AI: {text}\n\n")
                text_area.see(tk.END)
                text_area.config(state=tk.DISABLED)

            threading.Thread(target=ai_respond, daemon=True).start()

        ttk.Button(input_frame, text="发送", command=send).pack(side=tk.RIGHT)
        entry.bind("<Return>", lambda e: send())

    def ai_settings(self):
        """AI设置窗口"""
        win = tk.Toplevel(self.root)
        win.title("AI 设置")
        win.geometry("500x400")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        content_frame = ttk.Frame(win)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ttk.Label(content_frame, text="AI 引擎设置", font=("微软雅黑", 14, "bold")).pack(pady=10)

        ttk.Button(content_frame, text="API 提供商配置",
                   command=self.show_api_provider_config, width=25).pack(pady=5)
        ttk.Button(content_frame, text="OCR 校准",
                   command=self.show_ocr_calibration, width=25).pack(pady=5)
        ttk.Button(content_frame, text="搜索校准",
                   command=self.show_search_calibration, width=25).pack(pady=5)
        ttk.Button(content_frame, text="OCR 区域校准",
                   command=self.show_ocr_region_calibration, width=25).pack(pady=5)

        ttk.Separator(content_frame, orient="horizontal").pack(fill=tk.X, pady=15)

        ttk.Button(content_frame, text="关闭", command=win.destroy, width=15).pack(pady=10)

    def show_api_provider_config(self):
        """显示API提供商配置"""
        win = tk.Toplevel(self.root)
        win.title("API 提供商配置")
        win.geometry("400x300")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ttk.Label(frame, text="API 提供商配置", font=("微软雅黑", 12, "bold")).pack(pady=10)
        ttk.Label(frame, text="此功能用于配置 AI 后端 API 密钥和端点。",
                  wraplength=350).pack(pady=5)
        ttk.Button(frame, text="关闭", command=win.destroy, width=15).pack(pady=20)

    def show_ocr_calibration(self):
        """显示OCR校准"""
        win = tk.Toplevel(self.root)
        win.title("OCR 校准")
        win.geometry("400x300")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ttk.Label(frame, text="OCR 校准", font=("微软雅黑", 12, "bold")).pack(pady=10)
        ttk.Label(frame, text="用于校准微信消息识别的 OCR 参数。",
                  wraplength=350).pack(pady=5)
        ttk.Button(frame, text="关闭", command=win.destroy, width=15).pack(pady=20)

    def show_search_calibration(self):
        """显示搜索校准"""
        win = tk.Toplevel(self.root)
        win.title("搜索校准")
        win.geometry("400x300")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ttk.Label(frame, text="搜索校准", font=("微软雅黑", 12, "bold")).pack(pady=10)
        ttk.Label(frame, text="用于校准微信搜索框的位置。",
                  wraplength=350).pack(pady=5)
        ttk.Button(frame, text="关闭", command=win.destroy, width=15).pack(pady=20)

    def show_ocr_region_calibration(self):
        """显示OCR区域校准"""
        win = tk.Toplevel(self.root)
        win.title("OCR 区域校准")
        win.geometry("400x300")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        ttk.Label(frame, text="OCR 区域校准", font=("微软雅黑", 12, "bold")).pack(pady=10)
        ttk.Label(frame, text="用于校准微信消息显示的 OCR 识别区域。",
                  wraplength=350).pack(pady=5)
        ttk.Button(frame, text="关闭", command=win.destroy, width=15).pack(pady=20)

    def launch_hermes_terminal(self):
        """启动Hermes终端"""
        self.say("系统", "Hermes 终端功能已迁移到新架构。请通过智能对话标签页使用 AI 功能。")

    def toggle_ai(self, enabled):
        """切换AI功能"""
        self.use_ai_features = enabled
        self.ai_helper.use_ai_features = enabled
        status = "启用" if enabled else "禁用"
        self.say("系统", f"AI 功能已{status}")

    def _cancel_hermes(self):
        """取消 Hermes 处理(由 ChatPanel 管理)"""
        pass


    def _restore_geometry(self):
        """恢复上次窗口位置和大小"""
        try:
            saved = self.config_manager.get("window_geometry", "")
            if saved:
                self.root.geometry(saved)
        except:
            self.root.geometry("1000x700")

    def _save_geometry(self):
        """保存当前窗口位置和大小"""
        try:
            self.config_manager.set("window_geometry", self.root.geometry())
        except:
            pass

    def _switch_tab_next(self, event=None):
        """切换到下一个标签"""
        idx = self.notebook.index("current")
        total = self.notebook.index("end")
        self.notebook.select((idx + 1) % total)

    def _switch_tab_prev(self, event=None):
        """切换到上一个标签"""
        idx = self.notebook.index("current")
        total = self.notebook.index("end")
        self.notebook.select((idx - 1) % total)

    def show_toast(self, text, duration=3000):
        """弹出短暂Toast提示"""
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        w = ttk.Label(toast, text=text, padding=15,
                       font=("微软雅黑", 11), relief="solid",
                       borderwidth=1, background="#313244",
                       foreground="#cdd6f4")
        w.pack()
        w.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - w.winfo_reqwidth()) // 2
        y = self.root.winfo_y() + self.root.winfo_height() - 80
        toast.geometry("+%d+%d" % (max(0, x), max(0, y)))
        self.root.after(duration, toast.destroy)

    def show_help(self):
        """显示帮助信息"""
        help_text = """AI电脑管家 v8.0 使用帮助

💬 智能对话 - 在聊天标签页输入自然语言指令
📁 文件管理 - 智能整理、查重、大文件扫描
⚙️ 系统控制 - 关机重启、任务管理器、音量调节
📱 微信通讯 - 消息监听、定时发送
🤖 自动化 - 宏录制、定时任务

快捷键:
  Enter - 发送消息
  Ctrl+N - 新建对话

更多帮助请访问项目文档。"""
        messagebox.showinfo("帮助", help_text)

    def on_closing(self):
        """窗口关闭时的清理工作"""
        self.running = False

        if self.wechat_listener_running:
            self.wechat_listener_running = False

        # 清理 Hermes 进程池和保活线程
        if self._hermes_bridge:
            try:
                self._hermes_bridge.cleanup()
            except Exception:
                pass

        # 清理 AgentService
        if self._agent_service:
            try:
                if hasattr(self._agent_service, 'shutdown'):
                    self._agent_service.shutdown()
            except Exception:
                pass

        # 清理 ConversationMemory 数据库连接
        if self._conversation_memory:
            try:
                self._conversation_memory.close()
            except Exception:
                pass

        if self._task_scheduler:
            try:
                self._task_scheduler.stop_scheduler()
            except Exception:
                pass

        self.config_manager.set("current_folder", self.current_folder)
        self.config_manager.set("scheduled_tasks", self.scheduled_tasks)
        self.config_manager.set("app_paths", self.app_paths)
        self.config_manager.save()

        try:
            self.root.destroy()
        except Exception:
            import os
            os._exit(0)

if __name__ == '__main__':
    root = tk.Tk()
    app = AppShell(root)
    root.mainloop()