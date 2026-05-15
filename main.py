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
from modules.macro_recorder import get_recorder, get_player
from modules.ai_agent import get_ai_agent
from modules.social_skills import SocialSkills
from modules.conversation_memory import ConversationMemory
from modules.system_controller import get_system_controller
from modules.knowledge_base_builder import KnowledgeBaseBuilder
from modules.email_classifier import EmailClassifier
from modules.ui_manager import init_ui_manager
# Hermes 桥接 (已优化, 旧版本 hermes_bridge.py 已移除)
from modules.hermes_bridge_optimized import get_hermes_bridge_optimized, get_hermes_ai_helper_optimized
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

class AIPCHelperV8:
    """AI电脑管家 8.0 模块化版本"""

    def __init__(self, root):
        self.root = root
        self.root.title("Hermes | AI电脑管家 8.0")
        self.root.geometry("1000x700")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)

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
                    # 同步 HermesBridge 状态 + 更新开关按钮UI
                    try:
                        self.hermes_bridge._ensure_checked()
                    except Exception:
                        pass
                    self.root.after(0, self._update_hermes_toggle_ui)
                    self.root.after(500, self._update_model_display)  # 延迟更新模型列表
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
            callback=self.on_wechat_message,
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
        self.build_ui()

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
    def build_ui(self):
        """构建主界面 - 采用清晰的模块化布局"""

        # ========== 顶部状态栏 ==========
        self._build_status_bar()

        # ========== 核心功能区(标签页) ==========
        self._build_notebook()

        # ========== 底部状态栏 ==========
        self._build_bottom_status()

    def _build_status_bar(self):
        """构建顶部状态栏"""
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, padx=10, pady=3)

        self.status_label = ttk.Label(self.status_frame, text="✅ 就绪", foreground="green", font=("微软雅黑", 10, "bold"))
        self.status_label.pack(side=tk.LEFT)

        # 取消按钮(Hermes处理时显示)
        self._cancel_btn = ttk.Button(
            self.status_frame, text="⏹ 停止", command=self._cancel_hermes,
            width=8
        )

        self.folder_label = ttk.Label(self.status_frame, text=f"📁 {self.current_folder}", foreground="gray", font=("微软雅黑", 9))
        self.folder_label.pack(side=tk.RIGHT)

    def _build_notebook(self):
        """构建标签页 - 仅聊天标签立即构建,其余按需加载"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # 追踪哪些标签已构建
        self._tab_built = {"file": False, "system": False, "wechat": False, "auto": False}

        # ===== 标签页1: 智能对话(首屏立即构建)=====
        self.chat_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.chat_tab, text="💬 智能对话")
        self._build_chat_tab()

        # ===== 标签页2-5: 仅创建空壳,点击时才构建 =====
        self.file_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.file_tab, text="📁 文件管理")

        self.system_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.system_tab, text="⚙️ 系统控制")

        self.wechat_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.wechat_tab, text="📱 微信通讯")

        self.auto_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.auto_tab, text="🤖 自动化")

        # 切换标签时按需构建
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        """标签切换 - 首次点击时构建内容"""
        idx = self.notebook.index("current")
        tab_names = ["chat", "file", "system", "wechat", "auto"]
        if idx >= len(tab_names):
            return

        tab = tab_names[idx]

        if tab == "file" and not self._tab_built["file"]:
            self._tab_built["file"] = True
            self._build_file_tab()
        elif tab == "system" and not self._tab_built["system"]:
            self._tab_built["system"] = True
            self._build_system_tab()
        elif tab == "wechat" and not self._tab_built["wechat"]:
            self._tab_built["wechat"] = True
            self._build_wechat_tab()
        elif tab == "auto" and not self._tab_built["auto"]:
            self._tab_built["auto"] = True
            self._build_auto_tab()

        # 同时绑定 <<Visibility>> 事件确保内容可见
        if tab != "chat":
            target_tab = getattr(self, f"{tab}_tab", None)
            if target_tab:
                target_tab.bind("<<Visibility>>", lambda e: None, add="+")

    def _build_chat_tab(self):
        """构建智能对话标签页 - 左侧对话列表 + 右侧聊天区"""
        # 初始化对话管理器
        from services.conversation_manager import get_conversation_manager
        self._conv_mgr = get_conversation_manager()

        # ── 主分割: 侧栏 | 聊天区 ──
        self.chat_paned = tk.PanedWindow(
            self.chat_tab, orient=tk.HORIZONTAL, sashwidth=3,
            bg="#45475a", sashrelief=tk.RAISED
        )
        self.chat_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 左侧: 对话列表
        self.conv_panel = ttk.Frame(self.chat_paned)
        self._build_conversation_sidebar()
        self.chat_paned.add(self.conv_panel, minsize=180)

        # 右侧: 聊天区
        self.chat_right = ttk.Frame(self.chat_paned)
        self.chat_paned.add(self.chat_right, minsize=400)

        # 聊天显示区
        self.chat = scrolledtext.ScrolledText(
            self.chat_right, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 10), bg="#1e1e2e", fg="#cdd6f4",
            relief=tk.FLAT, padx=8, pady=5
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        # 输入区
        input_frame = ttk.Frame(self.chat_right)
        input_frame.pack(fill=tk.X, padx=3, pady=3)

        self.input_text = ttk.Entry(input_frame, font=("微软雅黑", 10), foreground="#cdd6f4")
        self.input_text.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 8), ipady=5)
        self.input_text.bind("<Return>", self.send_msg)
        self.input_text.focus()

        send_btn = ttk.Button(input_frame, text="🚀 发送", command=self.send_msg)
        send_btn.pack(side=tk.RIGHT, ipady=3)

        # ── 引擎控制栏 ──
        engine_frame = ttk.LabelFrame(self.chat_right, text="引擎控制", padding=5)
        engine_frame.pack(fill=tk.X, padx=3, pady=(0, 2))

        self.hermes_toggle_var = tk.BooleanVar(value=getattr(self, 'use_hermes', False))
        self.hermes_toggle_btn = tk.Button(
            engine_frame, text="🤖 Hermes 关闭",
            command=self._toggle_hermes_switch,
            width=14, font=("微软雅黑", 9, "bold"),
            bg="#333333", fg="#888888",
            activebackground="#444444", activeforeground="#aaaaaa",
            relief=tk.RAISED, bd=2, cursor="hand2"
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

        self.auto_switch_var = tk.BooleanVar(value=True)
        self.auto_switch_btn = tk.Button(
            engine_frame, text="🔄 智能路由",
            command=self._toggle_auto_switch,
            width=10, font=("微软雅黑", 8),
            bg="#2a5a2a", fg="#a0d0a0",
            activebackground="#3a6a3a", activeforeground="#c0e0c0",
            relief=tk.RAISED, bd=1, cursor="hand2"
        )
        self.auto_switch_btn.pack(side=tk.LEFT, padx=2)

        ttk.Label(engine_frame, text=" ").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(engine_frame, text="⚙️ 设置", command=self.ai_settings, width=8).pack(side=tk.RIGHT, padx=2)

        self._update_hermes_toggle_ui()

        # ── 操作栏 ──
        action_frame = ttk.Frame(self.chat_right)
        action_frame.pack(fill=tk.X, padx=3, pady=(0, 3))

        ttk.Button(action_frame, text="🗑️ 清空聊天", command=self._clear_chat_display, width=10).pack(side=tk.LEFT, padx=2)
        self._history_label = ttk.Label(action_frame, text="💬 新对话", font=("微软雅黑", 8))
        self._history_label.pack(side=tk.RIGHT, padx=5)
        ttk.Button(action_frame, text="❓ 帮助", command=self.show_help, width=8).pack(side=tk.RIGHT, padx=2)

        # 初始化:加载当前对话到聊天区
        self._load_active_conversation()

    # ── 对话侧边栏 ─────────────────────────────────────────────────────────

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

        v_scroll = ttk.Scrollbar(list_frame, command=self.conv_listbox.yview)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.conv_listbox.config(yscrollcommand=v_scroll.set)

        btn_frame = ttk.Frame(panel)
        btn_frame.pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="+ 新建", command=self._new_conversation, width=9).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑", command=self._delete_conversation, width=3).pack(side=tk.RIGHT, padx=2)

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

    def _delete_conversation(self):
        """删除当前对话"""
        active = self._conv_mgr.active_id
        if not active:
            return
        if len(self._conv_mgr.list_conversations()) <= 1:
            return  # 至少保留一个对话
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
                    self.say("你", content)
                elif role == "assistant":
                    self.say("AI", content)
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

    def _build_file_tab(self):
        """构建文件管理标签页"""
        # 文件操作按钮区
        btn_frame = ttk.LabelFrame(self.file_tab, text="文件操作", padding=10)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        # 第一行:常用操作
        row1 = ttk.Frame(btn_frame)
        row1.pack(fill=tk.X, pady=3)

        ttk.Button(row1, text="🗂️ 智能整理", command=self.auto_sort_files, width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row1, text="🔍 查找重复", command=self.find_duplicate_files, width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row1, text="💽 大文件", command=self.find_large_files, width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row1, text="🧹 清理空文件", command=self.clean_empty_files, width=15).pack(side=tk.LEFT, padx=3)

        # 第二行:目录操作
        row2 = ttk.Frame(btn_frame)
        row2.pack(fill=tk.X, pady=3)

        ttk.Button(row2, text="📂 选择目录", command=self.choose_folder, width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2, text="📋 列出文件", command=self.list_files, width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2, text="✏️ 批量重命名", command=lambda: self.rename_folder(""), width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2, text="↶ 撤销", command=self.undo, width=15).pack(side=tk.LEFT, padx=3)

        # 当前目录信息
        info_frame = ttk.LabelFrame(self.file_tab, text="目录信息", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.file_info_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg="#1e1e2e", fg="#cdd6f4",
            height=10
        )
        self.file_info_text.pack(fill=tk.BOTH, expand=True)

        # 更新目录信息
        self._update_file_info()

    def _update_file_info(self):
        """更新文件信息显示"""
        try:
            folder = self.current_folder
            if os.path.exists(folder):
                files = os.listdir(folder)
                file_count = len([f for f in files if os.path.isfile(os.path.join(folder, f))])
                dir_count = len([f for f in files if os.path.isdir(os.path.join(folder, f))])

                info = f"📁 当前目录: {folder}\n"
                info += f"📄 文件数: {file_count}\n"
                info += f"📂 文件夹数: {dir_count}\n"
                info += f"📊 总计: {len(files)} 项\n"

                # 计算总大小
                total_size = 0
                for f in files:
                    try:
                        fp = os.path.join(folder, f)
                        if os.path.isfile(fp):
                            total_size += os.path.getsize(fp)
                    except:
                        pass

                # 格式化大小
                if total_size > 1024**3:
                    info += f"💾 总大小: {total_size / 1024**3:.2f} GB"
                elif total_size > 1024**2:
                    info += f"💾 总大小: {total_size / 1024**2:.2f} MB"
                else:
                    info += f"💾 总大小: {total_size / 1024:.2f} KB"

                self.file_info_text.config(state=tk.NORMAL)
                self.file_info_text.delete(1.0, tk.END)
                self.file_info_text.insert(tk.END, info)
                self.file_info_text.config(state=tk.DISABLED)
        except Exception as e:
            pass

    def _build_system_tab(self):
        """构建系统控制标签页"""
        # 电源控制
        power_frame = ttk.LabelFrame(self.system_tab, text="电源控制", padding=10)
        power_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(power_frame, text="🔴 关机", command=lambda: self.system_operation("关机"), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(power_frame, text="🔄 重启", command=lambda: self.system_operation("重启"), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(power_frame, text="💤 睡眠", command=lambda: self.system_operation("睡眠"), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(power_frame, text="🔒 锁定", command=lambda: self.system_operation("锁定"), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(power_frame, text="❌ 取消关机", command=lambda: self.system_operation("取消关机"), width=12).pack(side=tk.LEFT, padx=5)

        # 系统工具
        tools_frame = ttk.LabelFrame(self.system_tab, text="系统工具", padding=10)
        tools_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(tools_frame, text="🖥️ 任务管理器", command=lambda: self._safe_execute_command("open_task_manager", "taskmgr"), width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(tools_frame, text="⚙️ 系统设置", command=lambda: self._safe_execute_command("open_settings", "start ms-settings:"), width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(tools_frame, text="🖥️ CMD", command=lambda: self._safe_execute_command("open_cmd", "start cmd"), width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(tools_frame, text="💻 PowerShell", command=lambda: self._safe_execute_command("open_powershell", "start powershell"), width=15).pack(side=tk.LEFT, padx=5)

        # 音量控制
        vol_frame = ttk.LabelFrame(self.system_tab, text="音量控制", padding=10)
        vol_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(vol_frame, text="🔊 增大", command=lambda: self.execute_ai_command({"action": "volume_up"}), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(vol_frame, text="🔉 减小", command=lambda: self.execute_ai_command({"action": "volume_down"}), width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(vol_frame, text="🔇 静音", command=lambda: self.execute_ai_command({"action": "toggle_mute"}), width=12).pack(side=tk.LEFT, padx=5)

        # 系统信息
        info_frame = ttk.LabelFrame(self.system_tab, text="系统信息", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.system_info_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg="#1e1e2e", fg="#cdd6f4",
            height=8
        )
        self.system_info_text.pack(fill=tk.BOTH, expand=True)

        # 刷新按钮
        ttk.Button(self.system_tab, text="🔄 刷新信息", command=self._update_system_info).pack(pady=5)

        # 初始化系统信息
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

    def _build_wechat_tab(self):
        """构建微信通讯标签页"""
        # 微信控制
        ctrl_frame = ttk.LabelFrame(self.wechat_tab, text="微信控制", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=10)

        self.listener_btn = ttk.Button(ctrl_frame, text="▶️ 开始监听", command=self.toggle_wechat_listener, width=15)
        self.listener_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="📱 发送消息", command=self.schedule_wechat_message, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame, text="🔧 诊断", command=self.diagnose_wechat, width=15).pack(side=tk.LEFT, padx=5)

        # 定时任务
        task_frame = ttk.LabelFrame(self.wechat_tab, text="定时任务", padding=10)
        task_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(task_frame, text="📋 查看任务", command=self.show_scheduled_tasks, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(task_frame, text="➕ 添加任务", command=self.schedule_wechat_message, width=15).pack(side=tk.LEFT, padx=5)

        # 微信状态
        status_frame = ttk.LabelFrame(self.wechat_tab, text="状态信息", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.wechat_status_text = scrolledtext.ScrolledText(
            status_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg="#1e1e2e", fg="#cdd6f4",
            height=8
        )
        self.wechat_status_text.pack(fill=tk.BOTH, expand=True)

        # 初始化状态
        self._update_wechat_status()

    def _update_wechat_status(self):
        """更新微信状态显示"""
        status = "微信监听: " + ("运行中" if self.wechat_listener_running else "已停止")
        status += f"\n监听间隔: {self.config_manager.get('wechat_check_interval', 3)}秒"
        status += f"\nOCR模式: {'开启' if self.config_manager.get('use_ocr', True) else '关闭'}"

        self.wechat_status_text.config(state=tk.NORMAL)
        self.wechat_status_text.delete(1.0, tk.END)
        self.wechat_status_text.insert(tk.END, status)
        self.wechat_status_text.config(state=tk.DISABLED)

    def _build_auto_tab(self):
        """构建自动化标签页"""
        # 自动化工具
        tools_frame = ttk.LabelFrame(self.auto_tab, text="自动化工具", padding=10)
        tools_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(tools_frame, text="🎬 宏录制", command=self.show_macro_panel, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(tools_frame, text="🔄 自动化任务", command=self.show_automation_panel, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(tools_frame, text="🤖 AI智能体", command=self.show_ai_agent_panel, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(tools_frame, text="💻 编程工作区", command=self.show_code_workspace, width=15).pack(side=tk.LEFT, padx=5)

        # 应用管理
        app_frame = ttk.LabelFrame(self.auto_tab, text="应用管理", padding=10)
        app_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(app_frame, text="➕ 添加应用", command=self.add_custom_app, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(app_frame, text="📋 应用列表", command=self.list_custom_apps, width=15).pack(side=tk.LEFT, padx=5)

        # 说明
        help_frame = ttk.LabelFrame(self.auto_tab, text="使用说明", padding=10)
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

    def _build_bottom_status(self):
        """构建底部状态栏"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=10, pady=3)

        # Hermes 状态(延迟检查,避免启动时阻塞)
        self.hermes_status_label = ttk.Label(
            status_frame,
            text="Hermes: ⏳ 检查中...",
            font=("微软雅黑", 8),
            foreground="#888888"
        )
        self.hermes_status_label.pack(side=tk.LEFT, padx=5)
        # 后台更新 Hermes 状态
        self.root.after(500, self._update_hermes_status)

        # AI 引擎状态
        ai_engine = "Hermes" if self.use_hermes else "Ollama"
        self.ai_engine_label = ttk.Label(
            status_frame,
            text=f"AI引擎: {ai_engine}",
            font=("微软雅黑", 8)
        )
        self.ai_engine_label.pack(side=tk.LEFT, padx=5)

        # 版本信息
        version_label = ttk.Label(
            status_frame,
            text="v8.0",
            font=("微软雅黑", 8),
            foreground="gray"
        )
        version_label.pack(side=tk.RIGHT, padx=5)

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

    def _say(self, who, what):
        """内部方法:实际更新 UI"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, f"[{timestamp}] [{who}] {what}\n\n")
        self.chat.config(state=tk.DISABLED)
        self.chat.see(tk.END)

    # ── 任务分类 ────────────────────────────────────────────────────────────

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

        # 极短系统消息
        if len(msg) < 10:
            trivial = ['help', '帮助', 'status', '状态', 'clear', 'cls', 'hi', '你好', 'hello', '在吗']
            if any(k in msg_lower for k in trivial):
                result.update(type='system', complexity='trivial', timeout=60, reasoning='问候/系统 → Flash')
                return result
            result['reasoning'] = '短消息 → Flash 默认'
            return result

        # 代码生成 (优先)
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

        # 搜索/知识查询
        search_kw = ['搜索', '查询', '查找', '怎么', '如何', '为什么', '什么是',
                    '定义', '区别', '对比', '有哪些', '介绍一下']
        if any(k in msg_lower for k in search_kw):
            result.update(type='search', model='ds-v4-flash', reasoning='搜索查询 → Flash')
            return result

        # 分析任务
        analysis_kw = ['分析', '诊断', '审核', '评估', '总结', '摘要', '深入分析']
        if any(k in msg_lower for k in analysis_kw):
            result.update(type='analysis', complexity='moderate', model='ds-v4-flash-r',
                          reasoning='分析任务 → Flash 深度思考')
            return result

        # 创意任务
        creative_kw = ['创意', '设计', '头脑风暴', '想法', '建议', '推荐', '方案']
        if any(k in msg_lower for k in creative_kw):
            result.update(type='creative', model='ds-v4-flash-r', reasoning='创意 → Flash 深度思考')
            return result

        # 命令行/系统操作
        cmd_kw = ['打开', '关闭', '启动', '停止', '重启', '清理', '整理',
                 '下载', '安装', '配置', '检查', '查看']
        if any(k in msg_lower for k in cmd_kw):
            result.update(type='command', timeout=120, reasoning='系统命令 → 快速执行')
            return result

        # 长文本 → 深度思考
        if len(msg) > 200:
            result.update(complexity='moderate', model='ds-v4-flash-r',
                          timeout=300, reasoning='长文本 → Flash 深度思考')

        return result

    # ---------- 发送消息 ----------
    def send_msg(self, event=None):
        """发送消息 - 主入口(日常对话直达 DeepSeek,复杂任务走 Hermes)"""
        try:
            msg = self.input_text.get().strip()
            if not msg:
                return

            self.input_text.delete(0, tk.END)
            self.say("你", msg)

            # 获取当前对话
            conv = self._get_active_conversation()

            # 检查是否是命令(以/开头)
            if msg.startswith('/'):
                cmd = msg[1:].strip().lower()
                if cmd == 'clear' or cmd == 'cls':
                    self._conv_mgr.clear_conversation(conv.id)
                    self._clear_chat_display()
                    self.say("系统", "✅ 对话历史已清空")
                elif cmd in ('hermes', 'h'):
                    self.launch_hermes_task(msg)
                elif cmd == 'history':
                    self._show_conversation_history()
                elif cmd == 'new':
                    self._new_conversation()
                else:
                    self.say("系统", f"未知命令: /{cmd}")
                return

            # 用户消息保存到对话
            conv.add_message("user", msg)
            self._refresh_conv_listbox()

            # ── 路由决策 ──
            task_info = self._classify_task(msg)

            if self.use_hermes and task_info.get('complexity') in ('complex', 'heavy'):
                # 复杂任务 → Hermes 代理
                self._chat_with_history(msg, task_info=task_info)
            else:
                # 日常对话 → DeepSeek 直连
                self._chat_with_deepseek(msg, conv)
        except Exception as e:
            print(f"send_msg异常:{e}")
            traceback.print_exc()
            self.say("系统", f"❌ 发送消息时发生错误:{str(e)}")

    def _chat_with_deepseek(self, msg: str, conv):
        """使用 DeepSeek API 直连进行对话 - 轻量快速,不走 Hermes/WSL"""
        from services.deepseek_client import get_deepseek_client

        client = get_deepseek_client(config_manager=self.config_manager)
        sm = self._get_streaming_manager()

        if not sm.can_start():
            self.say("系统", "⏳ 正在处理中,请稍候...")
            return

        # 同步模型选择
        model_id = self._current_model_id()
        client.set_model(model_id)

        # 构建上下文
        context = conv.get_context(max_messages=10)

        # 结果捕获
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

        # 轮询保存结果(stream.start 不阻塞)
        def _check_done():
            if sm.is_active:
                self.root.after(300, _check_done)
            elif result_holder[0]:
                conv.add_message("assistant", result_holder[0])
                self._refresh_conv_listbox()

        self.root.after(500, _check_done)

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

        agent = get_agent_service(self.config_manager)
        sm = self._get_streaming_manager()

        if not sm.can_start():
            self.say("系统", "⏳ Hermes 正在处理上一轮对话,请稍候...")
            return

        # 任务感知参数
        if task_info is None:
            task_info = {}
        timeout = task_info.get('timeout', 300)

        # ── 智能模型路由 ──
        if self.auto_switch_var.get():
            try:
                from services.model_switcher import get_model_switcher
                switcher = get_model_switcher()
                recommended = switcher.select_model(msg)
                current = switcher.get_current()
                if recommended.id != (current.id if current else 'ds-v4-flash'):
                    switcher.set_model(recommended.id)
                    self.config_manager.set("hermes_model", recommended.id)
                    logger.info(f"🎯 智能路由: {current.id if current else 'default'} → {recommended.id}")
            except Exception as e:
                logger.warning(f"智能路由失败,使用当前模型: {e}")

        def _task(callback, cancel_event):
            return agent.chat_with_history(
                message=msg,
                stream_callback=callback,
                timeout=timeout
            )

        # 动态选择状态栏前缀
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

    def _show_cancel_button(self):
        """显示取消按钮(Hermes处理时)"""
        try:
            self._cancel_btn.pack(side=tk.RIGHT, padx=5)
        except Exception:
            pass

    def _hide_cancel_button(self):
        """隐藏取消按钮"""
        try:
            self._cancel_btn.pack_forget()
        except Exception:
            pass

    def _get_streaming_manager(self):
        """懒加载 StreamingManager 单例"""
        if self._streaming_manager is None:
            from services.streaming_manager import StreamingManager
            self._streaming_manager = StreamingManager(
                root=self.root,
                chat_widget=self.chat,
                status_label=self.status_label,
                on_complete=self._on_stream_complete,
                on_cancel_button=lambda show: (
                    self._show_cancel_button() if show else self._hide_cancel_button()
                )
            )
        return self._streaming_manager

    def _on_stream_complete(self):
        """流式完成回调 - 更新对话历史状态"""
        self._update_history_status()

    def _cancel_hermes(self):
        """取消当前 Hermes 任务"""
        if self._streaming_manager and self._streaming_manager.is_active:
            self._streaming_manager.cancel()
            self.say("系统", "⏹ 正在停止 Hermes...")
        elif hasattr(self, '_stream_cancel'):
            # 兼容旧代码
            self._stream_cancel.set()
            self.say("系统", "⏹ 正在停止 Hermes...")

    def _clear_conversation(self):
        """清空对话历史"""
        try:
            from services.agent_service import get_agent_service
            agent = get_agent_service(self.config_manager)
            agent.clear_history()
        except Exception:
            pass
        self._update_history_status()

    def _show_conversation_history(self):
        """显示对话历史摘要"""
        try:
            from services.agent_service import get_agent_service
            agent = get_agent_service(self.config_manager)
            history = agent.get_history()
            turns = agent.history_turns

            if not history:
                self.say("系统", "📜 对话历史为空")
                return

            summary = f"📜 对话历史 ({turns} 轮)\n" + "─" * 40 + "\n"
            for i, msg in enumerate(history):
                role = "👤" if msg["role"] == "user" else "🤖"
                content = msg["content"][:80] + ("..." if len(msg["content"]) > 80 else "")
                summary += f"{i+1}. {role} {content}\n"
            self.say("系统", summary)
        except Exception as e:
            self.say("系统", f"❌ 获取历史失败: {e}")

    def _update_history_status(self):
        """更新对话历史状态显示"""
        if not hasattr(self, '_history_label'):
            return
        try:
            from services.agent_service import get_agent_service
            agent = get_agent_service(self.config_manager)
            turns = agent.history_turns
            self._history_label.config(text=f"💬 {turns}轮" if turns > 0 else "💬 新对话")
        except Exception:
            pass

    # ---------- 智能指令解析 ----------
    _quick_patterns = None

    def _get_quick_patterns(self):
        if self._quick_patterns is None:
            self._quick_patterns = {
                'cancel_shutdown': re.compile(r"(?:取消关机|撤销关机|停止关机)"),
                'restart': re.compile(r"(?:重启|重新启动)"),
                'restart_delay': re.compile(r"(\d+)\s*(?:分钟|分|小时|时|秒)"),
                'shutdown': re.compile(r"(?:关机|停止|关闭|断电)"),
                'shutdown_delay': re.compile(r"(\d+)\s*(?:分钟|分|小时|时|秒)"),
                'sleep': re.compile(r"(?:睡眠|待机|休眠)"),
                'lock': re.compile(r"(?:锁定|锁屏)"),
                'wechat_msg': re.compile(r"给(.+?)发[送]消息[::]?\s*(.+)"),
                'open_app1': re.compile(r"打开\s*(.+?)(?:\s|$)"),
                'open_app2': re.compile(r"启动\s*(.+?)(?:\s|$)"),
                'open_app3': re.compile(r"运行\s*(.+?)(?:\s|$)"),
            }
        return self._quick_patterns

    def quick_parse_command(self, msg):
        msg = msg.strip()
        if not msg:
            return None

        patterns = self._get_quick_patterns()
        msg_lower = msg.lower()

        if patterns['cancel_shutdown'].search(msg_lower):
            return ("cancel_shutdown", {})

        if patterns['restart'].search(msg_lower):
            delay_match = patterns['restart_delay'].search(msg_lower)
            if delay_match:
                delay = self._parse_time_to_minutes(delay_match.group())
                return ("timer_restart", {"delay": delay})
            return ("restart", {})

        if patterns['shutdown'].search(msg_lower):
            delay_match = patterns['shutdown_delay'].search(msg_lower)
            if delay_match:
                delay = self._parse_time_to_minutes(delay_match.group())
                return ("timer_shutdown", {"delay": delay})
            return ("shutdown", {})

        if patterns['sleep'].search(msg_lower):
            return ("sleep", {})

        if patterns['lock'].search(msg_lower):
            return ("lock", {})

        match = patterns['wechat_msg'].search(msg)
        if match:
            target = match.group(1).strip()
            message = match.group(2).strip().replace('"', '').replace('"', '').replace('"', '')
            return ("send_wechat", {"target": target, "message": message})

        for pat in [patterns['open_app1'], patterns['open_app2'], patterns['open_app3']]:
            match = pat.search(msg)
            if match:
                app_name = match.group(1).strip()
                if app_name:
                    return ("open_app", {"app_name": app_name})

        return None

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
        quick_result = self.quick_parse_command(msg)
        if quick_result:
            action, params = quick_result
            self._execute_quick_action(action, params)
            return

        msg_lower = msg.lower().strip()
        if any(k in msg_lower for k in ["按类型整理", "分类", "排序"]):
            self.auto_sort_files()
        elif any(k in msg_lower for k in ["重复文件", "去重"]):
            self.find_duplicate_files()
        elif any(k in msg_lower for k in ["空文件"]):
            self.clean_empty_files()
        elif any(k in msg_lower for k in ["大文件", "占用空间"]):
            self.find_large_files()
        elif any(k in msg_lower for k in ["改名", "重命名", "序号", "替换"]):
            self.rename_folder(msg)
        elif any(k in msg_lower for k in ["打开", "启动", "运行", "开启"]):
            self.open_app(msg)
        elif any(k in msg_lower for k in ["列出", "显示", "查看", "文件", "内容", "有什么"]):
            self.list_files()
        elif any(k in msg_lower for k in ["关机", "重启", "注销", "任务管理器", "取消关机"]):
            self.system_operation(msg)
        elif "执行命令" in msg_lower:
            cmd = msg.replace("执行命令:", "").strip()
            self.custom_command(cmd)
        elif "ai助手" in msg_lower:
            self.ai_chat_dialog()
        elif "开始监听" in msg_lower:
            self.toggle_wechat_listener()
        elif "停止监听" in msg_lower:
            if self.wechat_listener_running:
                self.toggle_wechat_listener()

        # ---------- 新增50条指令支持 ----------
        elif any(k in msg_lower for k in ["截图", "截屏", "屏幕截图"]):
            self.execute_ai_command({"action": "take_screenshot"})
        elif any(k in msg_lower for k in ["录屏", "录影", "屏幕录制", "录制屏幕"]):
            self.execute_ai_command({"action": "record_screen"})
        elif any(k in msg_lower for k in ["停止录屏", "停止录制", "结束录屏"]):
            self.execute_ai_command({"action": "stop_recording"})
        elif any(k in msg_lower for k in ["静音", "关闭声音", "关闭音量", "静音模式"]):
            self.execute_ai_command({"action": "toggle_mute"})
        elif any(k in msg_lower for k in ["音量增大", "提高音量", "音量加大", "调高音量"]):
            self.execute_ai_command({"action": "volume_up"})
        elif any(k in msg_lower for k in ["音量减小", "降低音量", "音量降低", "调低音量"]):
            self.execute_ai_command({"action": "volume_down"})
        elif any(k in msg_lower for k in ["播放音乐", "播放媒体", "开始播放", "播放音频"]):
            self.execute_ai_command({"action": "play_media"})
        elif any(k in msg_lower for k in ["暂停音乐", "暂停媒体", "停止播放", "暂停音频"]):
            self.execute_ai_command({"action": "pause_media"})
        elif any(k in msg_lower for k in ["下一曲", "下一首", "下一首歌", "下一个"]):
            self.execute_ai_command({"action": "next_track"})
        elif any(k in msg_lower for k in ["上一曲", "上一首", "上一首歌", "上一个"]):
            self.execute_ai_command({"action": "prev_track"})
        elif any(k in msg_lower for k in ["显示桌面", "回到桌面", "最小化所有"]):
            self.execute_ai_command({"action": "show_desktop"})
        elif any(k in msg_lower for k in ["显示开始菜单", "开始菜单", "打开开始菜单"]):
            self.execute_ai_command({"action": "show_start_menu"})
        elif any(k in msg_lower for k in ["切换用户", "切换账户", "注销登录"]):
            self.execute_ai_command({"action": "switch_user"})
        elif any(k in msg_lower for k in ["清空回收站", "清理回收站", "回收站清空"]):
            self.execute_ai_command({"action": "empty_recycle_bin"})
        elif any(k in msg_lower for k in ["计算器", "打开计算器", "启动计算器"]):
            self.execute_ai_command({"action": "open_calculator"})
        elif any(k in msg_lower for k in ["记事本", "打开记事本", "启动记事本"]):
            self.execute_ai_command({"action": "open_notepad"})
        elif any(k in msg_lower for k in ["相机", "摄像头", "打开相机", "启动相机"]):
            self.execute_ai_command({"action": "open_camera"})
        elif any(k in msg_lower for k in ["拍照", "照相", "拍摄照片"]):
            self.execute_ai_command({"action": "take_photo"})
        elif any(k in msg_lower for k in ["当前时间", "现在几点", "现在时间", "查看时间"]):
            self.execute_ai_command({"action": "get_current_time"})
        elif any(k in msg_lower for k in ["当前日期", "今天日期", "今天几号", "查看日期"]):
            self.execute_ai_command({"action": "get_current_date"})
        elif any(k in msg_lower for k in ["ip地址", "本机ip", "查看ip", "网络地址"]):
            self.execute_ai_command({"action": "get_ip_address"})
        elif any(k in msg_lower for k in ["系统信息", "电脑信息", "查看系统信息", "硬件信息"]):
            self.execute_ai_command({"action": "get_system_info"})
        elif any(k in msg_lower for k in ["cpu使用率", "cpu占用", "查看cpu", "处理器使用率"]):
            self.execute_ai_command({"action": "get_cpu_usage"})
        elif any(k in msg_lower for k in ["内存使用率", "内存占用", "查看内存", "内存情况"]):
            self.execute_ai_command({"action": "get_memory_usage"})
        elif any(k in msg_lower for k in ["磁盘使用率", "磁盘空间", "查看磁盘", "硬盘空间"]):
            self.execute_ai_command({"action": "get_disk_usage"})
        elif any(k in msg_lower for k in ["电池状态", "电量", "查看电池", "电池电量"]):
            self.execute_ai_command({"action": "get_battery"})
        elif any(k in msg_lower for k in ["休眠", "睡眠模式", "进入休眠", "电脑休眠"]):
            self.execute_ai_command({"action": "hibernate"})
        elif any(k in msg_lower for k in ["锁定屏幕", "锁定电脑", "屏幕锁定", "锁屏"]):
            self.execute_ai_command({"action": "lock"})
        elif any(k in msg_lower for k in ["注销", "登出", "退出登录", "切换账户"]):
            self.execute_ai_command({"action": "logout"})
        elif any(k in msg_lower for k in ["关闭显示器", "关闭屏幕", "息屏", "屏幕关闭"]):
            self.execute_ai_command({"action": "turn_off_display"})
        elif any(k in msg_lower for k in ["刷新页面", "刷新", "重新加载", "刷新网页"]):
            self.execute_ai_command({"action": "refresh_page"})
        elif any(k in msg_lower for k in ["前进", "下一页", "下一个页面", "向前"]):
            self.execute_ai_command({"action": "go_forward"})
        elif any(k in msg_lower for k in ["后退", "上一页", "上一个页面", "向后"]):
            self.execute_ai_command({"action": "go_back"})
        elif any(k in msg_lower for k in ["浏览器", "打开浏览器", "启动浏览器", "网页浏览器"]):
            self.execute_ai_command({"action": "open_browser"})
        elif any(k in msg_lower for k in ["关闭浏览器", "退出浏览器", "结束浏览器"]):
            self.execute_ai_command({"action": "close_browser"})
        elif any(k in msg_lower for k in ["文件资源管理器", "资源管理器", "打开文件管理器", "文件管理"]):
            self.execute_ai_command({"action": "open_explorer"})
        elif any(k in msg_lower for k in ["命令提示符", "cmd", "打开cmd", "启动命令提示符"]):
            self.execute_ai_command({"action": "open_cmd"})
        elif any(k in msg_lower for k in ["powershell", "打开powershell", "启动powershell"]):
            self.execute_ai_command({"action": "open_powershell"})
        elif any(k in msg_lower for k in ["任务管理器", "打开任务管理器", "启动任务管理器"]):
            self.execute_ai_command({"action": "open_task_manager"})
        elif any(k in msg_lower for k in ["控制面板", "打开控制面板", "启动控制面板"]):
            self.execute_ai_command({"action": "open_control_panel"})
        elif any(k in msg_lower for k in ["系统设置", "打开系统设置", "启动系统设置"]):
            self.execute_ai_command({"action": "open_settings"})
        elif any(k in msg_lower for k in ["复制到剪贴板", "复制文本", "复制内容"]):
            # 尝试提取要复制的文本
            match = re.search(r'复制(?:文本|内容)?[::]\s*(.+)', msg)
            if match:
                text = match.group(1).strip()
                self.execute_ai_command({"action": "set_clipboard", "content": text})
            else:
                self.say("系统", "请指定要复制的文本,例如:复制文本:你好世界")
        elif any(k in msg_lower for k in ["从剪贴板粘贴", "粘贴文本", "粘贴内容", "读取剪贴板"]):
            self.execute_ai_command({"action": "get_clipboard"})
        elif any(k in msg_lower for k in ["鼠标点击", "点击鼠标", "单击"]):
            self.execute_ai_command({"action": "click_mouse"})
        elif any(k in msg_lower for k in ["滚动", "滚轮", "鼠标滚轮", "上下滚动"]):
            # 尝试提取滚动数量
            match = re.search(r'滚动\s*(\d+)', msg_lower)
            amount = int(match.group(1)) if match else 3
            self.execute_ai_command({"action": "scroll", "amount": amount})
        elif any(k in msg_lower for k in ["输入文本", "打字", "模拟输入"]):
            # 尝试提取要输入的文本
            match = re.search(r'输入(?:文本)?[::]\s*(.+)', msg)
            if match:
                text = match.group(1).strip()
                self.execute_ai_command({"action": "type_text", "text": text})
            else:
                self.say("系统", "请指定要输入的文本,例如:输入文本:你好世界")
        elif any(k in msg_lower for k in ["按键", "按键盘", "模拟按键"]):
            # 尝试提取按键
            match = re.search(r'按键(?:[::]|\s*)(\w+)', msg_lower)
            if match:
                key = match.group(1).strip()
                self.execute_ai_command({"action": "press_key", "key": key})
            else:
                self.say("系统", "请指定要按的按键,例如:按键:enter")
        elif any(k in msg_lower for k in ["鼠标移动", "移动鼠标", "移动光标"]):
            # 尝试提取坐标
            match = re.search(r'移动到\s*(\d+)\s*[,,]\s*(\d+)', msg_lower)
            if match:
                x, y = int(match.group(1)), int(match.group(2))
                self.execute_ai_command({"action": "move_mouse", "x": x, "y": y})
            else:
                self.say("系统", "请指定鼠标坐标,例如:移动到100,200")
        elif any(k in msg_lower for k in ["ping", "网络测试", "连接测试"]):
            # 尝试提取主机
            match = re.search(r'ping\s+(\S+)', msg_lower) or re.search(r'测试\s+(\S+)\s*连接', msg_lower)
            if match:
                host = match.group(1).strip()
                self.execute_ai_command({"action": "ping_host", "host": host})
            else:
                self.execute_ai_command({"action": "ping_host", "host": "baidu.com"})
        elif any(k in msg_lower for k in ["断开网络", "断开连接", "关闭网络"]):
            self.execute_ai_command({"action": "disconnect_network"})
        elif any(k in msg_lower for k in ["连接网络", "启用网络", "打开网络"]):
            self.execute_ai_command({"action": "connect_network"})
        elif any(k in msg_lower for k in ["删除文件", "移除文件", "删除"]):
            # 尝试提取文件路径
            match = re.search(r'删除(?:文件)?[::]\s*(.+)', msg)
            if match:
                file_path = match.group(1).strip()
                self.execute_ai_command({"action": "delete_file", "file_path": file_path})
            else:
                self.say("系统", "请指定要删除的文件路径,例如:删除文件:C:\\test.txt")
        elif any(k in msg_lower for k in ["创建文件夹", "新建文件夹", "建立目录"]):
            # 尝试提取文件夹路径
            match = re.search(r'创建(?:文件夹)?[::]\s*(.+)', msg)
            if match:
                folder_path = match.group(1).strip()
                self.execute_ai_command({"action": "create_folder", "folder_path": folder_path})
            else:
                self.say("系统", "请指定要创建的文件夹路径,例如:创建文件夹:C:\\new_folder")
        elif any(k in msg_lower for k in ["读取文件", "查看文件", "打开文件"]):
            # 尝试提取文件路径
            match = re.search(r'读取(?:文件)?[::]\s*(.+)', msg)
            if match:
                file_path = match.group(1).strip()
                self.execute_ai_command({"action": "read_file", "file_path": file_path})
            else:
                self.say("系统", "请指定要读取的文件路径,例如:读取文件:C:\\test.txt")
        else:
            self.say("AI管家", f"🤔 我不太明白\"{msg}\",请尝试更详细的描述或使用一键操作按钮。")

    def _process_ai_command(self, msg):
        try:
            result = self.ai_helper.parse_command(msg)
            if result:
                self.execute_ai_command(result)
            else:
                if any(keyword in msg for keyword in ["给", "发消息", "微信"]):
                    match = re.search(r'给(.+?)发[送]消息[::]?\s*(.+)', msg)
                    if not match:
                        match = re.search(r'发[送]消息给(.+?)[::]\s*(.+)', msg)
                    if match:
                        target = match.group(1).strip()
                        message = match.group(2).strip()
                        message = message.replace('"', '').replace('"', '').replace('"', '')
                        if target and message:
                            success = self.wechat_controller.send_wechat_message(target, message)
                            if success:
                                self.say("系统", f"✅ 已成功给{target}发送消息:{message}")
                            else:
                                self.say("系统", f"❌ 发送消息失败,请检查微信是否正常运行。")
                            return
                self.say("AI管家", "🤔 我不太明白,试试一键操作按钮或输入更明确的指令。")
        except Exception as e:
            self.say("系统", f"❌ 解析指令时发生错误:{str(e)}")

    def _execute_quick_action(self, action, params):
        """执行快速操作按钮 - 统一通过 CommandRegistry"""
        try:
            from core.command_registry import execute_command
            # params from quick action -> cmd_data for registry
            cmd_data = dict(params) if params else {}
            cmd_data["action"] = action
            execute_command(action, self, cmd_data)
        except KeyError:
            self.say("AI管家", f"无法执行该操作(未知操作类型:{action})。")
        except Exception as e:
            logger.error(f"快速操作执行失败 [{action}]: {e}", exc_info=True)
            self.say("系统", f"❌ 执行失败: {str(e)}")

    def _validate_ai_result(self, result):
        """验证AI解析结果是否包含必要参数"""
        if not result or "action" not in result:
            return False

        action = result.get("action")
        # 必要参数映射
        required_params = {
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
            "shutdown": [],  # delay可选
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
            "kill_process": [],  # process_name或pid至少一个
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

        if action not in required_params:
            # 未知动作,视为无效
            return False

        for param in required_params[action]:
            if param not in result or not result[param]:
                return False

        return True

    def execute_ai_command(self, cmd_data):
        action = cmd_data.get("action")

        # 命令注册表执行(所有命令已迁移到 registry)
        try:
            from core.command_registry import execute_command
            execute_command(action, self, cmd_data)
        except KeyError:
            self.say("AI管家", f"无法执行该指令(未知操作类型:{action})。")
        except Exception as e:
            logger.error(f"命令执行失败 [{action}]: {e}", exc_info=True)
            self.say("系统", f"❌ 执行失败: {str(e)}")
    # ---------- 文件管理功能 ----------
    def auto_sort_files(self):
        target_base = filedialog.askdirectory(title="选择分类后的根目录")
        if not target_base:
            return

        def sort_files_thread():
            try:
                self.say("AI管家", f"正在扫描文件...")
                move_plan = self.file_manager.auto_sort_files(self.current_folder, target_base, self.ai_helper if self.use_ai_features else None)

                if not move_plan:
                    self.say("AI管家", "没有需要整理的文件。")
                    return

                preview = "\n".join([f"• {os.path.relpath(s, self.current_folder)} -> {os.path.relpath(d, target_base)}" for s, d in move_plan[:20]])
                if len(move_plan) > 20:
                    preview += f"\n... 还有 {len(move_plan)-20} 个文件"
                self.say("AI管家", f"📊 整理方案预览(共{len(move_plan)}个文件):\n{preview}")

                # 在主线程中显示确认对话框
                def confirm_and_execute():
                    if messagebox.askyesno("确认", "确定执行整理?"):
                        moved = 0
                        for src, dst in move_plan:
                            if self.file_manager.safe_move(src, dst):
                                moved += 1
                        self.say("系统", f"✅ 整理完成,成功移动 {moved}/{len(move_plan)} 个文件。")

                self.root.after(0, confirm_and_execute)
            except Exception as e:
                logger.exception("按类型整理失败")
                self.say("系统", f"❌ 整理失败:{e}")

        # 启动子线程执行文件整理
        threading.Thread(target=sort_files_thread, daemon=True).start()

    def find_duplicate_files(self):
        def find_duplicates_thread():
            try:
                self.say("AI管家", "正在扫描重复文件...")
                duplicates = self.file_manager.find_duplicate_files(self.current_folder)

                if not duplicates:
                    self.say("AI管家", "没有发现重复文件。")
                    return

                lines = [f"发现 {len(duplicates)} 组重复文件,每组保留第一个,其余将删除:"]
                for group in duplicates[:10]:
                    lines.append(f"• {os.path.basename(group[0])} 等 {len(group)} 个文件")
                if len(duplicates) > 10:
                    lines.append(f"... 还有 {len(duplicates)-10} 组")
                self.say("AI管家", "\n".join(lines))

                # 在主线程中显示确认对话框
                def confirm_and_cleanup():
                    if self.use_ai_features and messagebox.askyesno("智能清理", "是否让AI分析哪些文件可以安全删除?(否则将删除每组除第一个外的所有副本)"):
                        self.smart_duplicate_cleanup(duplicates)
                    elif messagebox.askyesno("确认", "确定删除所有重复文件的副本吗?"):
                        deleted = 0
                        for group in duplicates:
                            for path in group[1:]:
                                try:
                                    os.remove(path)
                                    deleted += 1
                                except Exception as e:
                                    logger.error(f"删除失败 {path}: {e}")
                        self.say("系统", f"✅ 已删除 {deleted} 个重复文件。")

                self.root.after(0, confirm_and_cleanup)
            except Exception as e:
                logger.exception("查找重复文件失败")
                self.say("系统", f"❌ 查找重复文件失败:{e}")

        # 启动子线程执行文件扫描
        threading.Thread(target=find_duplicates_thread, daemon=True).start()

    def smart_duplicate_cleanup(self, duplicates):
        self.say("AI管家", "正在分析重复文件,请稍候...")
        to_delete = []
        for group in duplicates:
            files_info = []
            for path in group:
                stat = os.stat(path)
                info = {
                    "path": path,
                    "name": os.path.basename(path),
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                }
                files_info.append(info)
            del_list = self.ai_helper.analyze_duplicate_files(files_info)
            to_delete.extend(del_list)
        if to_delete:
            preview = "\n".join([f"• {path}" for path in to_delete[:20]])
            if len(to_delete) > 20:
                preview += f"\n... 还有 {len(to_delete)-20} 个"
            if messagebox.askyesno("确认", f"AI建议删除以下 {len(to_delete)} 个文件,确定?\n{preview}"):
                deleted = 0
                for path in to_delete:
                    try:
                        os.remove(path)
                        deleted += 1
                    except Exception as e:
                        logger.error(f"删除失败 {path}: {e}")
                self.say("系统", f"✅ 已删除 {deleted} 个文件。")
        else:
            self.say("系统", "AI未给出有效建议,请手动处理。")

    def clean_empty_files(self):
        def clean_empty_thread():
            try:
                self.say("AI管家", "正在扫描空文件...")
                empty_files = self.file_manager.clean_empty_files(self.current_folder)
                if not empty_files:
                    self.say("AI管家", "没有空文件。")
                    return

                lines = [f"发现 {len(empty_files)} 个空文件:"]
                for e in empty_files[:20]:
                    lines.append(f"• {os.path.basename(e)}")
                if len(empty_files) > 20:
                    lines.append(f"... 还有 {len(empty_files)-20} 个")
                self.say("AI管家", "\n".join(lines))

                # 在主线程中显示确认对话框
                def confirm_and_delete():
                    if messagebox.askyesno("确认", f"确定删除这 {len(empty_files)} 个空文件?"):
                        deleted = 0
                        for path in empty_files:
                            try:
                                os.remove(path)
                                deleted += 1
                            except Exception as e:
                                logger.error(f"删除失败 {path}: {e}")
                        self.say("系统", f"✅ 已删除 {deleted} 个空文件。")

                self.root.after(0, confirm_and_delete)
            except Exception as e:
                logger.exception("清理空文件失败")
                self.say("系统", f"❌ 清理空文件失败:{e}")

        # 启动子线程执行文件扫描
        threading.Thread(target=clean_empty_thread, daemon=True).start()

    def find_large_files(self, min_size_gb=1):
        def find_large_files_thread():
            try:
                self.say("AI管家", f"正在扫描大于 {min_size_gb}GB 的文件...")
                large_files = self.file_manager.find_large_files(self.current_folder, min_size_gb)
                if not large_files:
                    self.say("AI管家", f"没有大于 {min_size_gb}GB 的文件。")
                    return
                lines = [f"发现 {len(large_files)} 个大文件(前20):"]
                for path, size in large_files[:20]:
                    lines.append(f"• {os.path.basename(path)} ({size/1024**3:.2f} GB)")
                self.say("AI管家", "\n".join(lines))
            except Exception as e:
                logger.exception("查找大文件失败")
                self.say("系统", f"❌ 查找大文件失败:{e}")

        # 启动子线程执行文件扫描
        threading.Thread(target=find_large_files_thread, daemon=True).start()

    def list_files(self):
        def list_files_thread():
            try:
                folders, files = self.file_manager.list_files(self.current_folder)
                if not folders and not files:
                    self.say("AI管家", "当前目录为空。")
                    return
                msg = "📁 文件夹:\n" + "\n".join([f"• {f}" for f in folders[:10]])
                if len(folders) > 10:
                    msg += f"\n... 还有 {len(folders)-10} 个文件夹"
                msg += "\n\n📄 文件:\n" + "\n".join([f"• {f}" for f in files[:20]])
                if len(files) > 20:
                    msg += f"\n... 还有 {len(files)-20} 个文件"
                self.say("AI管家", msg)
            except Exception as e:
                logger.exception("列出文件失败")
                self.say("系统", f"❌ 列出文件失败:{e}")

        # 启动子线程执行文件扫描
        threading.Thread(target=list_files_thread, daemon=True).start()

    def rename_folder(self, msg):
        try:
            self.say("AI管家", "正在分析改名需求...")
            folders = [d for d in os.listdir(self.current_folder) if os.path.isdir(os.path.join(self.current_folder, d))]
            if not folders:
                self.say("AI管家", "当前目录没有子文件夹。")
                return

            pairs = self.ai_helper.generate_rename_plan(folders, msg)
            if not pairs:
                self.say("AI管家", "无法理解您的指令,请换个说法。")
                return

            valid_pairs = []
            for p in pairs:
                old = p.get("original") or p.get("old")
                new = p.get("new")
                if old in folders and new and new not in folders:
                    valid_pairs.append((os.path.join(self.current_folder, old), os.path.join(self.current_folder, new)))

            if not valid_pairs:
                self.say("AI管家", "没有有效的改名项。")
                return

            preview = "\n".join([f"{os.path.basename(o)} → {os.path.basename(n)}" for o, n in valid_pairs])
            self.say("AI管家", f"📊 改名方案:\n{preview}")

            if messagebox.askyesno("确认", "执行改名?"):
                renamed = 0
                for o, n in valid_pairs:
                    try:
                        os.rename(o, n)
                        self.rename_history.append((o, n))
                        renamed += 1
                    except Exception as e:
                        logger.error(f"改名失败 {o} -> {n}: {e}")
                self.say("系统", f"✅ 改名完成,成功修改 {renamed}/{len(valid_pairs)} 个文件夹。")
        except Exception as e:
            logger.exception("改名失败")
            self.say("系统", f"❌ 改名失败:{e}")

    # ---------- 应用管理 ----------
    def detect_app_executable(self, app_name):
        """自动检测应用程序的可执行文件路径

        Args:
            app_name: 应用程序名称

        Returns:
            可执行文件路径,如果找不到返回None
        """
        # 1. 首先检查已配置的应用路径
        if app_name in self.app_paths:
            for path in self.app_paths[app_name]:
                if os.path.exists(path):
                    return path

        # 2. 通过系统控制器获取已安装软件列表
        if hasattr(self, 'system_controller'):
            result = self.system_controller.get_installed_software()
            if result.get("success"):
                for software in result.get("software_list", []):
                    soft_name = software.get("name", "").lower()
                    if app_name.lower() in soft_name or soft_name in app_name.lower():
                        # 检查安装位置是否有可执行文件
                        install_location = software.get("install_location", "")
                        if install_location and os.path.exists(install_location):
                            # 查找.exe文件
                            for root, dirs, files in os.walk(install_location):
                                for file in files:
                                    if file.endswith('.exe') and not file.lower().startswith('uninst'):
                                        exe_path = os.path.join(root, file)
                                        # 检查是否是可执行文件(通过文件名判断)
                                        if any(keyword in file.lower() for keyword in [app_name.lower(), soft_name.replace(' ', '').lower()]):
                                            return exe_path
                            # 如果没有找到,返回安装目录
                            return install_location

        # 3. 搜索常见安装目录
        common_paths = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.path.expanduser("~\\AppData\\Local"),
            os.path.expanduser("~\\AppData\\Roaming"),
            "C:\\"
        ]

        for base_path in common_paths:
            if not os.path.exists(base_path):
                continue
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file.endswith('.exe'):
                        # 检查文件名是否包含应用名
                        if app_name.lower() in file.lower():
                            exe_path = os.path.join(root, file)
                            # 避免系统文件
                            if any(sys_dir in exe_path.lower() for sys_dir in ['windows', 'system32', 'winsxs']):
                                continue
                            return exe_path

        return None

    def open_app(self, msg):
        # 提取应用名称
        app_name = msg.replace("打开", "").replace("启动", "").replace("运行", "").replace("开启", "").strip()

        # 1. 首先尝试已配置的应用路径
        for app, paths in self.app_paths.items():
            if app in app_name:
                for path in paths:
                    if os.path.exists(path):
                        try:
                            subprocess.Popen([path])
                            self.say("系统", f"✅ 已启动 {app}")
                            return
                        except Exception as e:
                            logger.error(f"启动 {app} 失败: {e}")
                self.say("系统", f"❌ 未找到 {app} 的可执行文件")
                return

        # 2. 自动检测应用
        detected_path = self.detect_app_executable(app_name)
        if detected_path and os.path.exists(detected_path):
            try:
                subprocess.Popen([detected_path])
                # 自动添加到应用路径配置中
                if app_name not in self.app_paths:
                    self.app_paths[app_name] = []
                if detected_path not in self.app_paths[app_name]:
                    self.app_paths[app_name].append(detected_path)
                    self.config_manager.set("app_paths", self.app_paths)
                self.say("系统", f"✅ 已自动检测并启动 {app_name}")
                logger.info(f"自动检测到应用 {app_name} 路径: {detected_path}")
                return
            except Exception as e:
                logger.error(f"启动 {app_name} 失败: {e}")
                self.say("系统", f"❌ 启动 {app_name} 失败: {e}")
        else:
            self.say("系统", f"❌ 未找到应用: {app_name}")
            # 建议用户手动添加
            if messagebox.askyesno("应用未找到", f"未找到应用 '{app_name}',是否手动添加?"):
                self.add_custom_app()

    def add_custom_app(self):
        app_name = simpledialog.askstring("添加应用", "请输入应用名称:")
        if not app_name:
            return
        app_path = filedialog.askopenfilename(title=f"选择 {app_name} 的可执行文件", filetypes=[("可执行文件", "*.exe")])
        if not app_path:
            return
        if app_name not in self.app_paths:
            self.app_paths[app_name] = []
        self.app_paths[app_name].append(app_path)
        self.config_manager.set("app_paths", self.app_paths)
        self.say("系统", f"✅ 已添加应用: {app_name}")

    def list_custom_apps(self):
        """显示已添加的应用列表"""
        if not self.app_paths:
            messagebox.showinfo("应用列表", "暂无自定义应用")
            return

        app_list = "📋 已添加的应用:\n\n"
        for name, paths in self.app_paths.items():
            app_list += f"📌 {name}:\n"
            for path in paths:
                app_list += f"   {path}\n"
            app_list += "\n"

        # 创建显示窗口
        win = tk.Toplevel(self.root)
        win.title("应用列表")
        win.geometry("500x400")
        win.configure(bg="#1e1e2e")

        text = scrolledtext.ScrolledText(
            win, wrap=tk.WORD, font=("微软雅黑", 10),
            bg="#1e1e2e", fg="#cdd6f4", padx=10, pady=10
        )
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert(tk.END, app_list)
        text.config(state=tk.DISABLED)

        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=10)

    # ---------- 系统操作 ----------
    def system_operation(self, msg):
        """处理系统操作指令

        Args:
            msg: 操作描述字符串(如"关机"、"重启"等)
        """
        msg_lower = msg.lower() if isinstance(msg, str) else ""

        if "关机" in msg and "取消" not in msg:
            if messagebox.askyesno("确认", "确定关机?"):
                subprocess.run(["shutdown", "/s", "/t", "0"], shell=False)
                self.say("系统", "🔴 正在关机...")
        elif "重启" in msg:
            if messagebox.askyesno("确认", "确定重启?"):
                subprocess.run(["shutdown", "/r", "/t", "0"], shell=False)
                self.say("系统", "🔄 正在重启...")
        elif "睡眠" in msg or "休眠" in msg:
            if messagebox.askyesno("确认", "确定进入睡眠模式?"):
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], shell=False)
                self.say("系统", "💤 正在进入睡眠模式...")
        elif "锁定" in msg or "锁屏" in msg:
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], shell=False)
            self.say("系统", "🔒 屏幕已锁定")
        elif "注销" in msg:
            if messagebox.askyesno("确认", "确定注销?"):
                subprocess.run(["shutdown", "/l"], shell=False)
                self.say("系统", "👋 正在注销...")
        elif "任务管理器" in msg:
            subprocess.run(["taskmgr"], shell=False)
            self.say("系统", "🖥️ 已打开任务管理器")
        elif "取消关机" in msg or "停止关机" in msg:
            subprocess.run(["shutdown", "/a"], shell=False)
            self.say("系统", "✅ 已取消关机/重启计划")
        else:
            self.say("系统", f"⚠️ 未知系统操作: {msg}")

    def _safe_execute_command(self, action_name, cmd_str):
        """安全执行系统命令 - 自动处理权限提升"""
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
            self.say("系统", f"✅ 已执行: {action_name}")
        except Exception as e:
            self.say("系统", f"❌ 执行失败: {e}")

    def custom_command(self, cmd):
        """执行自定义命令(白名单模式)"""
        # 安全命令白名单
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
                    self.say("系统", f"✅ 命令执行成功:\n{result.stdout}")
                else:
                    self.say("系统", f"❌ 命令执行失败:\n{result.stderr}")
            except subprocess.TimeoutExpired:
                self.say("系统", "❌ 命令执行超时")
            except Exception as e:
                self.say("系统", f"❌ 命令执行异常:{e}")
        else:
            self.say("系统", f"❌ 不允许执行该命令。安全命令列表:{', '.join(safe_commands.keys())}")

    # ---------- AI功能 ----------
    def ai_chat_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("AI助手 (Hermes)")
        win.geometry("600x600")  # 增大窗口大小
        win.minsize(500, 400)  # 设置最小大小
        win.configure(bg="#1e1e2e")
        win.transient(self.root)
        win.grab_set()

        # 标题框架
        title_frame = ttk.Frame(win)
        title_frame.pack(pady=10, fill=tk.X, padx=10)

        ttk.Label(title_frame, text="💬 AI助手", font=("微软雅黑", 14, "bold")).pack(side=tk.LEFT)

        # Hermes 切换按钮(不阻塞检查状态)
        hermes_btn = ttk.Button(
            title_frame,
            text="Hermes ⏳",
            command=lambda: self.toggle_hermes(hermes_btn)
        )
        hermes_btn.pack(side=tk.RIGHT)
        # 后台更新按钮状态
        self.root.after(500, lambda: self._update_hermes_btn(hermes_btn))

        # 显示当前使用的 AI 后端(通过 AgentService 自动检测)
        backend_name = "检测中..."
        try:
            agent_svc = self.agent_service
            if agent_svc and agent_svc.ensure_ready():
                backend = agent_svc.get_preferred_backend()
                backend_name = {"hermes": "Hermes", "agent": "AgentCore", "ollama": "Ollama"}.get(backend, backend)
            else:
                backend_name = "Hermes" if self.use_hermes else "Ollama"
        except:
            backend_name = "Hermes" if self.use_hermes else "Ollama"
        ai_label = ttk.Label(title_frame, text=f"当前: {backend_name}", font=("微软雅黑", 10))
        ai_label.pack(side=tk.RIGHT, padx=10)

        text_area = scrolledtext.ScrolledText(
            win, font=("微软雅黑", 11),
            bg="#313244", fg="#cdd6f4"
        )
        text_area.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        # 显示历史对话记录(从永久记忆加载) - 只显示用户和AI助手的聊天内容
        history = self.conversation_memory.get_conversation_history(
            session_id=self.conversation_memory.current_session_id,
            limit=50,
            role_filter=None
        )
        # 清空内存历史记录,然后加载数据库中的历史(按时间顺序)
        self.ai_chat_history.clear()
        if history:
            # history是按时间倒序排列的,需要反转以保持时间顺序
            history_chronological = list(reversed(history))
            for msg in history_chronological:
                # 只显示用户和AI助手的聊天内容,过滤掉系统消息等其他内容
                if msg["role"] not in ["user", "assistant"]:
                    continue
                # 添加到内存历史记录(用于向后兼容)
                self.ai_chat_history.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
                # 显示到文本框
                role = "你" if msg["role"] == "user" else "AI"
                text_area.insert(tk.END, f"{role}: {msg['content']}\n")
            text_area.insert(tk.END, "\n")
        else:
            text_area.insert(tk.END, "AI: 你好!我是AI助手,有什么可以帮你的吗?\n\n")

        entry_frame = ttk.Frame(win)
        entry_frame.pack(padx=10, pady=5, fill=tk.X)

        entry = ttk.Entry(entry_frame, font=("微软雅黑", 12))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        entry.bind("<Return>", lambda e: send_question())

        def send_question():
            question = entry.get().strip()
            if not question:
                return

            # 保存用户消息到历史记录(永久记忆)
            self.conversation_memory.add_message("user", question)

            # 同时保存到内存历史记录(用于向后兼容)
            self.ai_chat_history.append({"role": "user", "content": question})

            # 限制历史长度(最大100条)
            MAX_HISTORY = 100
            if len(self.ai_chat_history) > MAX_HISTORY:
                self.ai_chat_history = self.ai_chat_history[-MAX_HISTORY:]

            text_area.insert(tk.END, f"你: {question}\n")
            text_area.insert(tk.END, "AI: ")
            text_area.see(tk.END)
            entry.delete(0, tk.END)
            # 禁用输入框和发送按钮,启用停止按钮
            entry.config(state=tk.DISABLED)
            send_btn.config(state=tk.DISABLED)
            stop_btn.config(state=tk.NORMAL)

            # 创建停止标志和锁
            stop_flag = threading.Event()
            # 将停止标志存储到容器中,以便stop_generation函数可以访问
            stop_flag_container["flag"] = stop_flag

            def stream_callback(chunk):
                """流式响应回调 - 接收增量内容"""
                # 检查停止标志
                if stop_flag.is_set():
                    return
                # 直接传递增量内容给UI更新
                self.root.after(0, lambda: update_ai_response(chunk))

            def update_ai_response(chunk):
                """更新AI回复 - 追加增量内容"""
                # 直接追加到文本区域末尾
                text_area.insert(tk.END, chunk)
                text_area.see(tk.END)



            def ai_response():
                """AI 响应处理 - 优先通过 AgentService → Hermes"""
                answer = None
                error_msg = None

                try:
                    # 1. 优先使用 AgentService(自动最优后端 + 降级)
                    agent_svc = self.agent_service
                    if agent_svc and agent_svc.ensure_ready():
                        backend = agent_svc.get_preferred_backend()

                        if backend == "hermes":
                            # Hermes 全能力模式 -- 流式输出 + 会话持久化
                            system_prompt = "你是一个友好、有帮助的 AI 助手。请用自然、简洁的中文回答用户问题。"
                            answer = agent_svc.chat(
                                question,
                                system_prompt=system_prompt,
                                stream_callback=stream_callback,
                            )
                            if answer.startswith("[Hermes 不可用") or answer.startswith("[错误]"):
                                error_msg = answer
                                answer = None
                        else:
                            # Ollama/AgentCore 后端
                            chat_history = []
                            for msg in self.ai_chat_history[-10:]:
                                role = "用户" if msg["role"] == "user" else "助手"
                                chat_history.append(f"{role}: {msg['content']}")
                            prompt = "\n".join(chat_history) + "\n助手: "
                            system_prompt = "你是一个友好、有帮助的 AI 助手。请用自然、简洁的中文回答用户问题。不要返回 JSON 格式,直接以对话形式回复。"
                            answer = self.ai_helper.ai_query(
                                prompt,
                                system_prompt=system_prompt,
                                stream_callback=stream_callback,
                                stop_event=stop_flag,
                                timeout=30
                            )
                    else:
                        # 2. 回退:旧代码
                        chat_history = []
                        for msg in self.ai_chat_history[-10:]:
                            role = "用户" if msg["role"] == "user" else "助手"
                            chat_history.append(f"{role}: {msg['content']}")
                        prompt = "\n".join(chat_history) + "\n助手: "
                        system_prompt = "你是一个友好、有帮助的 AI 助手。请用自然、简洁的中文回答用户问题。不要返回 JSON 格式,直接以对话形式回复。"
                        answer = self.ai_helper.ai_query(
                            prompt,
                            system_prompt=system_prompt,
                            stream_callback=stream_callback,
                            stop_event=stop_flag,
                            timeout=30
                        )

                except Exception as e:
                    logger.error(f"AI 调用失败: {e}")
                    error_msg = f"AI 调用失败: {str(e)}"

                # UI 更新
                if stop_flag.is_set():
                    self.root.after(0, lambda: text_area.insert(tk.END, "\n[已停止]\n\n"))
                elif error_msg:
                    self.root.after(0, lambda: text_area.insert(tk.END, f"\n{error_msg}\n\n"))
                elif answer:
                    self.conversation_memory.add_message("assistant", answer)
                    self.ai_chat_history.append({"role": "assistant", "content": answer})
                    if len(self.ai_chat_history) > MAX_HISTORY:
                        self.ai_chat_history = self.ai_chat_history[-MAX_HISTORY:]
                    self.root.after(0, lambda: text_area.insert(tk.END, "\n\n"))
                else:
                    self.root.after(0, lambda: text_area.insert(tk.END, "\nAI 未返回回复,请检查服务状态。\n\n"))

                self.root.after(0, lambda: entry.config(state=tk.NORMAL))
                self.root.after(0, lambda: send_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: stop_btn.config(state=tk.DISABLED))
                self.root.after(0, lambda: text_area.see(tk.END))
                stop_flag_container["flag"] = None



            threading.Thread(target=ai_response, daemon=True).start()

        # 用于存储停止标志的容器
        stop_flag_container = {"flag": None}

        def stop_generation():
            """停止AI生成"""
            if stop_flag_container["flag"]:
                stop_flag_container["flag"].set()
                # 重置停止标志容器
                stop_flag_container["flag"] = None
                # 禁用停止按钮,启用发送按钮
                stop_btn.config(state=tk.DISABLED)
                send_btn.config(state=tk.NORMAL)
                entry.config(state=tk.NORMAL)
                text_area.insert(tk.END, "\n[已停止]\n\n")
                text_area.see(tk.END)

        stop_btn = ttk.Button(entry_frame, text="⏹️ 停止", state=tk.DISABLED, command=stop_generation)
        stop_btn.pack(side=tk.RIGHT, padx=(0, 5))

        send_btn = ttk.Button(entry_frame, text="发送", command=send_question)
        send_btn.pack(side=tk.RIGHT)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=5)

        def clear_history():
            if messagebox.askyesno("确认", "确定清空对话历史?"):
                # 清空内存历史记录
                self.ai_chat_history.clear()
                # 开始新的对话会话(旧的对话记录仍然保存在数据库中,但不再显示)
                self.conversation_memory.start_new_session()
                # 清空文本框
                text_area.delete(1.0, tk.END)
                text_area.insert(tk.END, "AI: 你好!我是AI助手,有什么可以帮你的吗?\n\n")
                text_area.see(tk.END)

        ttk.Button(btn_frame, text="🗑️ 清空历史", command=clear_history).pack(side=tk.LEFT, padx=5)

    def launch_hermes_terminal(self):
        """在新窗口中启动 Hermes Agent 交互模式"""
        try:
            hermes_cmd = (
                'wsl -d Ubuntu-22.04 bash -l -c '
                '"export TERM=xterm-256color && '
                'source /home/xlh/hermes-agent/venv/bin/activate && '
                'cd /home/xlh/hermes-agent && '
                'echo \"── Hermes Agent ─ DeepSeek V4 ──\" && '
                'echo \"输入 /help 查看帮助, Ctrl+C 退出\" && '
                'echo && '
                'hermes"'
            )

            # 打开新控制台窗口运行 Hermes
            subprocess.Popen(
                f'start "Hermes Agent" cmd /k {hermes_cmd}',
                shell=True
            )
            self.say("系统", "🚀 正在启动 Hermes Agent 终端...")
        except Exception as e:
            logger.error(f"启动 Hermes 终端失败: {e}")
            self.say("系统", f"❌ 启动失败: {e}")

    def _toggle_hermes_switch(self):
        """Hermes 开关按钮点击处理"""
        # 检查 HermesBridge 可用性,回退检查 AgentService
        hermes_available = self.hermes_bridge.available or (
            self._agent_service and self._agent_service.get_status().get("hermes")
        )
        if not hermes_available:
            messagebox.showwarning("Hermes 不可用",
                "Hermes 未检测到。\n请确保:\n1. WSL 已安装\n2. Hermes 已安装在 WSL 中")
            return

        self.use_hermes = not self.use_hermes
        self.hermes_toggle_var.set(self.use_hermes)
        self.config_manager.set("use_hermes", self.use_hermes)
        self._update_hermes_toggle_ui()

        # 同步更新状态栏
        if hasattr(self, 'ai_engine_label'):
            ai_engine = "Hermes" if self.use_hermes else "Ollama"
            self.ai_engine_label.config(text=f"AI引擎: {ai_engine}")

        self.say("系统", f"Hermes {'已启用' if self.use_hermes else '已禁用'}")
        logger.info(f"Hermes 切换为: {'启用' if self.use_hermes else '禁用'}")

    def _update_hermes_toggle_ui(self):
        """更新 Hermes 开关按钮的显示状态"""
        if self.use_hermes:
            self.hermes_toggle_btn.config(
                text="🟢 Hermes: 开",
                bg="#2d5a27", fg="#ffffff",
                activebackground="#3a7a32", activeforeground="#ffffff"
            )
            self.model_combo.config(state="readonly")
            self.auto_switch_btn.config(state="normal")
        else:
            self.hermes_toggle_btn.config(
                text="⚪ Hermes: 关",
                bg="#333333", fg="#888888",
                activebackground="#444444", activeforeground="#aaaaaa"
            )
            self.model_combo.config(state="disabled")
            self.auto_switch_btn.config(state="disabled")

    # 模型显示名 → 内部ID 映射
    MODEL_DISPLAY_MAP = {
        "DeepSeek V4 Flash · 快速": "ds-v4-flash",
        "DeepSeek V4 Flash · 深度": "ds-v4-flash-r",
        "DeepSeek V4 Pro · 通用": "ds-v4-pro",
        "DeepSeek V4 Pro · 推理": "ds-v4-pro-r",
    }
    MODEL_ID_TO_DISPLAY = {v: k for k, v in MODEL_DISPLAY_MAP.items()}

    def _on_model_selected(self, event=None):
        """模型下拉框切换事件"""
        display_name = self.model_var.get()
        model_id = self.MODEL_DISPLAY_MAP.get(display_name)
        if not model_id:
            model_id = display_name  # 兼容旧的 raw model_id
        if self.use_hermes:
            try:
                from services.model_switcher import get_model_switcher
                switcher = get_model_switcher()
                for m in switcher.list_models(enabled_only=False):
                    if m.id == model_id:
                        switcher.set_model(m.id)
                        self.say("系统", f"🔄 已切换到: {m.name}")
                        self._update_model_display()
                        return
                self.say("系统", f"⚠️ 未找到模型: {display_name}")
            except Exception as e:
                self.say("系统", f"❌ 模型切换失败: {e}")

    def _toggle_auto_switch(self):
        """切换自动模型选择"""
        try:
            from services.model_switcher import get_model_switcher
            switcher = get_model_switcher()
            is_auto = switcher.toggle_auto_switch()
            self.auto_switch_var.set(is_auto)

            if is_auto:
                self.auto_switch_btn.config(
                    text="🔄 自动", bg="#2a5a2a", fg="#a0d0a0"
                )
                self.model_combo.config(state="disabled")
                self.say("系统", "🔄 自动模型选择已开启 - 根据任务复杂度自动匹配最优模型")
            else:
                self.auto_switch_btn.config(
                    text="🔒 手动", bg="#5a3a2a", fg="#d0a080"
                )
                if self.use_hermes:
                    self.model_combo.config(state="readonly")
                self.say("系统", "🔒 手动模型选择 - 请从下拉框选择模型")
        except Exception as e:
            self.say("系统", f"❌ 切换失败: {e}")

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
                    self.auto_switch_btn.config(text="🔄 自动", bg="#2a5a2a", fg="#a0d0a0")
                    self.model_combo.config(state="disabled")
                else:
                    self.auto_switch_btn.config(text="🔒 手动", bg="#5a3a2a", fg="#d0a080")

                # 更新模型下拉列表(使用显示名)
                models = [
                    self.MODEL_ID_TO_DISPLAY.get(m.id, m.name)
                    for m in switcher.list_models(enabled_only=False)
                ]
                self.model_combo['values'] = models
        except Exception:
            pass

    def _update_hermes_status(self):
        """后台更新 Hermes 状态显示(含模型信息)"""
        try:
            # 优先检查 HermesBridge,回退检查 AgentService
            if self.hermes_bridge.available:
                status_text = "Hermes: 🟢 已连接"
            elif self._agent_service and self._agent_service.get_status().get("hermes"):
                status_text = "Hermes: 🟢 已连接"
            elif self.use_hermes:
                status_text = "Hermes: 🟡 切换中"
            else:
                status_text = "Hermes: 🔴 未连接"

            # 追加模型信息
            try:
                from services.model_switcher import get_model_switcher
                switcher = get_model_switcher()
                current = switcher.get_current()
                if current:
                    auto_tag = "🔄" if switcher.auto_switch_enabled else "🔒"
                    status_text += f" | {auto_tag} {current.name}"
            except Exception:
                pass

            self.hermes_status_label.config(text=status_text, foreground="#00ff00" if "🟢" in status_text else "#888888")
        except Exception:
            self.hermes_status_label.config(text="Hermes: ⚪ 未知", foreground="#888888")

    def _update_hermes_btn(self, btn):
        """后台更新 Hermes 按钮状态"""
        try:
            if self.hermes_bridge.available:
                btn.config(text="Hermes 🟢")
            else:
                btn.config(text="Hermes 🔴")
        except Exception:
            btn.config(text="Hermes ⚪")

    def toggle_hermes(self, btn=None):
        """切换 Hermes/Ollama AI 引擎(兼容旧接口)"""
        self._toggle_hermes_switch()

    def launch_hermes_task(self, task=None):
        """向 Hermes 发送任务 - 使用 StreamingManager"""
        if task is None:
            task = self.input_text.get().strip()

        if not task:
            self.say("系统", "⚠️ 请先在输入框中输入任务内容")
            return

        self.input_text.delete(0, tk.END)
        self.say("你", task)

        # 检查可用性
        agent_svc = self.agent_service
        agent_hermes_ok = agent_svc and agent_svc.ensure_ready() and agent_svc.get_preferred_backend() == "hermes"
        if not agent_hermes_ok and not self.hermes_bridge.available:
            self.say("系统", "❌ Hermes 不可用,请检查 WSL 和 Hermes 安装")
            return

        sm = self._get_streaming_manager()

        if not sm.can_start():
            self.say("系统", "⏳ Hermes 正在处理上一轮对话,请稍候...")
            return

        # ── 智能模型路由 ──
        if self.auto_switch_var.get():
            try:
                from services.model_switcher import get_model_switcher
                switcher = get_model_switcher()
                recommended = switcher.select_model(task)
                current = switcher.get_current()
                if recommended.id != (current.id if current else 'ds-v4-flash'):
                    switcher.set_model(recommended.id)
                    self.config_manager.set("hermes_model", recommended.id)
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
                return self.hermes_bridge.send_message(task)

        # 任务分类用于动态状态显示
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

    def _run_ai_agent_task_from_command(self, task):
        """从指令框执行 AI 任务 - 优先通过 AgentService"""
        try:
            # 优先使用统一 AgentService
            agent_svc = self.agent_service
            if agent_svc and agent_svc.ensure_ready():
                result = agent_svc.execute_task(task)
                if result.get("success"):
                    output = result.get("output", "")
                    self.say("系统", f"✅ AI任务完成!\n{output[:200]}" if len(output) > 200 else f"✅ AI任务完成!\n{output}")
                else:
                    self.say("系统", f"❌ AI任务执行失败:{result.get('error', '未知错误')}")
                return

            # 回退到旧 AIAgent
            if not hasattr(self, 'ai_agent') or self.ai_agent is None:
                from modules.ai_agent import get_ai_agent
                self.ai_agent = get_ai_agent(
                    ai_helper=self.ai_helper,
                    config_manager=self.config_manager
                )
                self.ai_agent.set_wechat_controller(self.wechat_controller)
                self.ai_agent.set_command_executor(self.execute_system_command)

            steps = self.ai_agent.plan_task(task)
            if not steps:
                self.say("系统", "❌ 任务规划失败,请检查模型服务是否运行")
                return

            results = self.ai_agent.execute_plan(steps)
            success_count = sum(1 for r in results if r.get("success"))
            self.say("系统", f"✅ AI任务完成!成功 {success_count}/{len(results)} 个步骤")
        except Exception as e:
            self.say("系统", f"❌ AI任务执行失败:{str(e)}")

    def ai_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("450x500")
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

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        ttk.Label(content_frame, text="⚙️ 系统设置", font=("微软雅黑", 14, "bold")).pack(pady=10)

        # AI 设置
        ai_frame = ttk.LabelFrame(content_frame, text="🤖 AI功能", padding=10)
        ai_frame.pack(fill=tk.X, padx=10, pady=5)

        var_ai = tk.BooleanVar(value=self.use_ai_features)
        ttk.Checkbutton(ai_frame, text="启用AI功能", variable=var_ai).pack(anchor=tk.W)

        providers = self.config_manager.get_api_providers()
        current_provider_id = self.config_manager.get_current_provider()

        provider_names = []
        provider_ids = []
        for pid, pdata in providers.items():
            name = pdata.get("name", pid)
            if pdata.get("api_key"):
                name = f"✓ {name}"
            provider_names.append(name)
            provider_ids.append(pid)

        ttk.Label(ai_frame, text="AI服务商:").pack(anchor=tk.W, pady=(5, 0))
        provider_var = tk.StringVar(value=current_provider_id)
        provider_combo = ttk.Combobox(ai_frame, textvariable=provider_var, values=provider_ids, state="readonly", width=30)
        provider_combo.pack(anchor=tk.W, pady=5)

        ttk.Label(ai_frame, text="模型名称:").pack(anchor=tk.W)
        current_models = providers.get(current_provider_id, {}).get("models", [])
        model_var = tk.StringVar(value=self.ai_helper.model)
        model_combo = ttk.Combobox(ai_frame, textvariable=model_var, values=current_models, width=30)
        model_combo.pack(anchor=tk.W, pady=5)

        def on_provider_changed(event):
            selected = provider_var.get()
            models = providers.get(selected, {}).get("models", [])
            model_combo['values'] = models
            if models:
                model_var.set(models[0])

        provider_combo.bind("<<ComboboxSelected>>", on_provider_changed)

        def open_api_config():
            win.destroy()
            self.show_api_provider_config()

        ttk.Button(ai_frame, text="⚙️ API配置", command=open_api_config).pack(anchor=tk.W, pady=(5, 0))

        # 微信设置
        wechat_frame = ttk.LabelFrame(content_frame, text="📱 微信监听", padding=10)
        wechat_frame.pack(fill=tk.X, padx=10, pady=5)

        ocr_status = "✅ OCR可用" if OCR_AVAILABLE else "❌ OCR不可用(请安装Tesseract)"
        ocr_status_label = ttk.Label(wechat_frame, text=f"OCR状态: {ocr_status}", foreground="green" if OCR_AVAILABLE else "red")
        ocr_status_label.pack(anchor=tk.W, pady=(0, 5))

        # 使用配置值避免触发 wechat_controller 延迟初始化
        var_ocr = tk.BooleanVar(value=self.config_manager.get("use_ocr", True))
        ttk.Checkbutton(wechat_frame, text="使用OCR识别消息(需Tesseract)", variable=var_ocr).pack(anchor=tk.W)

        ttk.Label(wechat_frame, text="Tesseract路径:").pack(anchor=tk.W, pady=(10, 0))
        tesseract_entry = ttk.Entry(wechat_frame, width=45)
        tesseract_entry.pack(anchor=tk.W)
        tesseract_entry.insert(0, self.config_manager.get("tesseract_cmd", ""))
        ttk.Button(wechat_frame, text="浏览", command=lambda: tesseract_entry.delete(0, tk.END) or tesseract_entry.insert(0, filedialog.askopenfilename(title="选择Tesseract", filetypes=[("exe", "*.exe"), ("所有文件", "*.*")]))).pack(anchor=tk.W)

        var_debug = tk.BooleanVar(value=self.config_manager.get("debug_mode", False))
        ttk.Checkbutton(wechat_frame, text="调试模式(保存截图到用户目录)", variable=var_debug).pack(anchor=tk.W)

        ttk.Label(wechat_frame, text="检查间隔(秒):").pack(anchor=tk.W)
        interval_entry = ttk.Entry(wechat_frame, width=10)
        interval_entry.pack(anchor=tk.W)
        interval_entry.insert(0, str(self.config_manager.get("wechat_check_interval", 10)))

        ttk.Label(wechat_frame, text="指令触发词(每行一个):").pack(anchor=tk.W, pady=(5, 0))
        triggers_text = scrolledtext.ScrolledText(wechat_frame, height=4, width=30, bg="#313244", fg="#cdd6f4", relief=tk.FLAT)
        triggers_text.pack(anchor=tk.W, pady=5)

        # 延迟插入确保UI就绪
        def safe_insert_triggers():
            try:
                current_triggers = self.config_manager.get("command_triggers", ["¥", "¥"])
                if not current_triggers:
                    current_triggers = ["¥", "¥"]
                triggers_text.insert("1.0", "\n".join(current_triggers))
            except Exception as e:
                logger = logging.getLogger("AIPCHelper")
                logger.error(f"触发词插入失败: {e}")

        triggers_text.after(100, safe_insert_triggers)

        def open_ocr_calibration():
            win.destroy()
            self.show_ocr_calibration()

        def open_search_calibration():
            win.destroy()
            self.show_search_calibration()

        def open_ocr_region_calibration():
            win.destroy()
            self.show_ocr_region_calibration()

        btn_frame_wechat = ttk.Frame(wechat_frame)
        btn_frame_wechat.pack(anchor=tk.W, pady=(10, 0))
        ttk.Button(btn_frame_wechat, text="🎯 OCR坐标校准", command=open_ocr_calibration).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_wechat, text="🔍 搜索框校准", command=open_search_calibration).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_wechat, text="📷 截图区域", command=open_ocr_region_calibration).pack(side=tk.LEFT, padx=5)

        def save():
            self.use_ai_features = var_ai.get()
            self.ai_helper.use_ai_features = self.use_ai_features

            selected_provider = provider_var.get()
            selected_model = model_var.get()
            self.ai_helper.set_config(model=selected_model, provider_id=selected_provider)
            # 显式设置当前服务商,确保配置被保存
            self.config_manager.set_current_provider(selected_provider)
            self.config_manager.set("model", selected_model)
            self.config_manager.set("use_ai_features", self.use_ai_features)

            self.wechat_controller.set_use_ocr(var_ocr.get())
            self.wechat_controller.set_debug_mode(var_debug.get())
            self.config_manager.set("use_ocr", var_ocr.get())
            self.config_manager.set("debug_mode", var_debug.get())

            tesseract_path = tesseract_entry.get().strip()
            if tesseract_path:
                self.wechat_controller.tesseract_cmd = tesseract_path
                self.config_manager.set("tesseract_cmd", tesseract_path)

            try:
                interval = int(interval_entry.get().strip())
                if interval >= 5:
                    self.wechat_controller.set_check_interval(interval)
                    self.config_manager.set("wechat_check_interval", interval)
            except ValueError:
                pass

            # 保存指令触发词列表
            triggers = triggers_text.get("1.0", tk.END).strip().splitlines()
            triggers = [t.strip() for t in triggers if t.strip()]
            if triggers:
                self.command_prefix = triggers[0]
                self.config_manager.set("command_prefix", triggers[0])
                self.config_manager.set("command_triggers", triggers)

            self.say("系统", "设置已保存。")
            win.destroy()

        ttk.Button(win, text="保存", command=save).pack(pady=10)

    def show_api_provider_config(self):
        """API服务商配置窗口"""
        win = tk.Toplevel(self.root)
        win.title("⚙️ API服务商配置")
        win.geometry("650x550")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        main_frame = ttk.Frame(win)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(main_frame, text="⚙️ API服务商配置", font=("微软雅黑", 14, "bold")).pack(pady=10)
        ttk.Label(main_frame, text="选择要配置的服务商,填写API密钥和自定义模型", foreground="gray").pack(pady=(0, 10))

        providers = self.config_manager.get_api_providers()
        provider_ids = list(providers.keys())

        ttk.Label(main_frame, text="选择服务商:").pack(anchor=tk.W, pady=(5, 0))
        selected_provider = tk.StringVar(value=provider_ids[0] if provider_ids else "ollama")
        provider_combo = ttk.Combobox(main_frame, textvariable=selected_provider, values=provider_ids, state="readonly", width=30)
        provider_combo.pack(anchor=tk.W, pady=5)

        config_frame = ttk.LabelFrame(main_frame, text="服务商配置", padding=10)
        config_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        ttk.Label(config_frame, text="显示名称:").grid(row=0, column=0, sticky=tk.W, pady=5)
        name_entry = ttk.Entry(config_frame, width=35)
        name_entry.grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(config_frame, text="Base URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
        base_url_entry = ttk.Entry(config_frame, width=35)
        base_url_entry.grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(config_frame, text="API Key:").grid(row=2, column=0, sticky=tk.W, pady=5)
        api_key_entry = ttk.Entry(config_frame, width=35, show="*")
        api_key_entry.grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(config_frame, text="模型列表 (逗号分隔):").grid(row=3, column=0, sticky=tk.W, pady=5)
        models_entry = ttk.Entry(config_frame, width=35)
        models_entry.grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(config_frame, text="默认模型:").grid(row=4, column=0, sticky=tk.W, pady=5)
        default_model_entry = ttk.Entry(config_frame, width=35)
        default_model_entry.grid(row=4, column=1, sticky=tk.W, pady=5)

        def load_provider_config():
            pid = selected_provider.get()
            p = providers.get(pid, {})
            name_entry.delete(0, tk.END)
            name_entry.insert(0, p.get("name", ""))
            base_url_entry.delete(0, tk.END)
            base_url_entry.insert(0, p.get("base_url", ""))
            api_key_entry.delete(0, tk.END)
            api_key_entry.insert(0, p.get("api_key", ""))
            models = p.get("models", [])
            models_entry.delete(0, tk.END)
            models_entry.insert(0, ", ".join(models))
            default_model_entry.delete(0, tk.END)
            default_model_entry.insert(0, p.get("default_model", ""))

        def save_provider_config():
            pid = selected_provider.get()
            models_str = models_entry.get().strip()
            models = [m.strip() for m in models_str.split(",") if m.strip()]

            providers[pid] = {
                "name": name_entry.get().strip(),
                "base_url": base_url_entry.get().strip(),
                "api_key": api_key_entry.get().strip(),
                "models": models,
                "default_model": default_model_entry.get().strip()
            }
            self.config_manager.set_api_providers(providers)
            messagebox.showinfo("成功", f"已保存 {name_entry.get().strip()} 的配置")

        def test_connection():
            pid = selected_provider.get()
            save_provider_config()

            from modules.unified_api_client import get_unified_client
            client = get_unified_client(self.config_manager)
            client.load_provider_config(pid)

            test_prompt = "请回复'测试成功',不要有其他内容。"
            result = client.query(test_prompt)

            if result and "成功" in result:
                messagebox.showinfo("成功", f"✅ 连接测试成功!\n\n响应: {result[:100]}")
            else:
                messagebox.showerror("失败", f"❌ 连接测试失败\n\n响应: {result}")

        provider_combo.bind("<<ComboboxSelected>>", lambda e: load_provider_config())
        load_provider_config()

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="💾 保存配置", command=save_provider_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔗 测试连接", command=test_connection).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❌ 关闭", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def show_ocr_calibration(self):
        """OCR坐标校准工具 - 完整版本"""
        win = tk.Toplevel(self.root)
        win.title("🎯 OCR坐标校准")
        win.geometry("550x500")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        ttk.Label(win, text="🎯 OCR坐标校准", font=("微软雅黑", 14, "bold")).pack(pady=10)

        info_text = """校准步骤:
1. 确保微信窗口已打开并可见
2. 点击「进入校准模式」
3. 此时请点击微信窗口中的「最后一条消息」
4. 点击后自动记录坐标
5. 点击「保存坐标」保存到配置

提示:校准后可以提高消息识别准确率"""
        ttk.Label(win, text=info_text, justify=tk.LEFT).pack(pady=10)

        self.calibration_step = tk.StringVar(value="就绪")
        step_label = ttk.Label(win, textvariable=self.calibration_step, font=("微软雅黑", 12), foreground="orange")
        step_label.pack(pady=5)

        coords_label = ttk.Label(win, text="当前坐标: 未获取", font=("微软雅黑", 10))
        coords_label.pack(pady=5)

        saved_coords = self.config_manager.get("last_msg_pos", None)
        if saved_coords:
            coords_label.config(text=f"当前坐标: 未获取 | 已保存: {saved_coords}")

        self.calibrating = False
        self.calibration_window = None
        self.calibration_coords = None

        def start_calibration():
            try:

                self.calibrating = True
                self.calibration_step.set("校准模式已激活!请点击微信窗口中的最后一条消息")

                def monitor_click():
                    while self.calibrating:
                        # 检查鼠标左键状态
                        if win32api.GetKeyState(win32con.VK_LBUTTON) < 0:
                            # 左键按下,获取坐标
                            x, y = win32api.GetCursorPos()

                            # 获取微信窗口信息
                            try:
                                windows = gw.getWindowsWithTitle('微信')
                                if not windows:
                                    windows = gw.getWindowsWithTitle('WeChat')

                                if windows:
                                    win = windows[0]
                                    win_left = win.left
                                    win_top = win.top
                                    win_width = win.width
                                    win_height = win.height

                                    # 计算比例坐标(相对于窗口)
                                    rx = (x - win_left) / win_width if win_width > 0 else 0
                                    ry = (y - win_top) / win_height if win_height > 0 else 0

                                    # 限制比例在0-1之间
                                    rx = max(0.0, min(1.0, rx))
                                    ry = max(0.0, min(1.0, ry))

                                    # 存储比例坐标
                                    self.calibration_coords = (rx, ry)

                                    def update_ui():
                                        coords_label.config(text=f"获取坐标成功: 绝对坐标({x}, {y}) | 比例坐标({rx:.3f}, {ry:.3f})")
                                        self.calibration_step.set("坐标已获取!请点击保存")

                                    self.root.after(0, update_ui)
                                else:
                                    # 未找到窗口,不保存坐标,提示用户
                                    self.calibration_coords = None

                                    def update_ui():
                                        coords_label.config(text=f"获取坐标成功: 绝对坐标({x}, {y}) | 未找到微信窗口,请确保微信窗口已打开并重试")
                                        self.calibration_step.set("微信窗口未找到,请确保微信窗口已打开并重试")

                                    self.root.after(0, update_ui)
                            except Exception as e:
                                # 出错时不保存坐标,提示用户
                                self.calibration_coords = None

                                def update_ui():
                                    coords_label.config(text=f"获取坐标成功: 绝对坐标({x}, {y}) | 计算比例失败: {e},请重新校准")
                                    self.calibration_step.set("坐标计算失败,请重新校准")

                                self.root.after(0, update_ui)

                            self.calibrating = False
                            break
                        time.sleep(0.05)

                threading.Thread(target=monitor_click, daemon=True).start()

            except ImportError:
                coords_label.config(text="请先安装 pywin32")
                messagebox.showerror("错误", "需要先安装 pywin32\n运行: pip install pywin32")

        def stop_calibration():
            self.calibrating = False
            self.calibration_step.set("校准已停止")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="进入校准模式", command=start_calibration).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="停止", command=stop_calibration).pack(side=tk.LEFT, padx=5)

        ttk.Label(win, text="保存坐标到配置:", font=("微软雅黑", 10)).pack(pady=(15, 5))

        coord_frame = ttk.Frame(win)
        coord_frame.pack(pady=5)
        ttk.Label(coord_frame, text="X:").pack(side=tk.LEFT)
        x_entry = ttk.Entry(coord_frame, width=8)
        if self.calibration_coords:
            x_entry.insert(0, str(self.calibration_coords[0]))
        elif saved_coords:
            x_entry.insert(0, str(saved_coords[0]))
        x_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(coord_frame, text="Y:").pack(side=tk.LEFT)
        y_entry = ttk.Entry(coord_frame, width=8)
        if self.calibration_coords:
            y_entry.insert(0, str(self.calibration_coords[1]))
        elif saved_coords:
            y_entry.insert(0, str(saved_coords[1]))
        y_entry.pack(side=tk.LEFT, padx=5)

        def save_coords():
            try:
                # 获取输入值(可能是整数或浮点数)
                x_str = x_entry.get().strip()
                y_str = y_entry.get().strip()

                # 尝试解析为浮点数
                x = float(x_str)
                y = float(y_str)

                # 判断坐标类型:如果值在0-1之间,可能是比例坐标
                is_likely_ratio = (0.0 <= x <= 1.0) and (0.0 <= y <= 1.0)

                # 获取微信窗口信息,尝试转换为比例坐标
                try:
                    windows = gw.getWindowsWithTitle('微信')
                    if not windows:
                        windows = gw.getWindowsWithTitle('WeChat')

                    if windows:
                        win = windows[0]
                        win_left = win.left
                        win_top = win.top
                        win_width = win.width
                        win_height = win.height

                        if win_width > 0 and win_height > 0:
                            # 如果输入的是绝对坐标,转换为比例坐标
                            if not is_likely_ratio or (x > 1.0 or y > 1.0):
                                rx = (x - win_left) / win_width
                                ry = (y - win_top) / win_height
                                # 限制在0-1之间
                                rx = max(0.0, min(1.0, rx))
                                ry = max(0.0, min(1.0, ry))
                                save_coords = (rx, ry)
                                coord_type = "比例坐标"
                            else:
                                # 输入已经是比例坐标
                                save_coords = (x, y)
                                coord_type = "比例坐标"
                        else:
                            # 窗口尺寸无效,保存原始坐标
                            save_coords = (x, y)
                            coord_type = "原始坐标(窗口尺寸无效)"
                    else:
                        # 未找到微信窗口,保存原始坐标
                        save_coords = (x, y)
                        coord_type = "原始坐标(未找到窗口)"
                except Exception as e:
                    # 出错时保存原始坐标
                    save_coords = (x, y)
                    coord_type = f"原始坐标(转换失败: {e})"

                # 保存坐标
                self.wechat_controller.last_msg_pos = save_coords
                self.config_manager.set("last_msg_pos", save_coords)
                messagebox.showinfo("成功", f"坐标已保存: {save_coords}\n类型: {coord_type}")
                win.destroy()
            except ValueError:
                messagebox.showerror("错误", "请输入有效的数字坐标")

        def fill_coords():
            if self.calibration_coords:
                x_entry.delete(0, tk.END)
                x_entry.insert(0, str(self.calibration_coords[0]))
                y_entry.delete(0, tk.END)
                y_entry.insert(0, str(self.calibration_coords[1]))
            elif saved_coords:
                x_entry.delete(0, tk.END)
                x_entry.insert(0, str(saved_coords[0]))
                y_entry.delete(0, tk.END)
                y_entry.insert(0, str(saved_coords[1]))

        btn_frame2 = ttk.Frame(win)
        btn_frame2.pack(pady=10)

        ttk.Button(btn_frame2, text="填充坐标", command=fill_coords).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame2, text="保存坐标", command=save_coords).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame2, text="关闭", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def show_search_calibration(self):
        """搜索框坐标校准工具"""
        win = tk.Toplevel(self.root)
        win.title("🔍 搜索框坐标校准")
        win.geometry("550x450")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)

        ttk.Label(win, text="🔍 搜索框坐标校准", font=("微软雅黑", 14, "bold")).pack(pady=10)

        info_text = """校准步骤:
1. 确保微信窗口已打开并可见
2. 点击「进入校准模式」
3. 此时请点击微信窗口中的「搜索框」位置
4. 点击后自动记录坐标
5. 点击「保存坐标」保存到配置

提示:校准后可以精确定位搜索框"""
        ttk.Label(win, text=info_text, justify=tk.LEFT).pack(pady=10)

        self.search_calibration_step = tk.StringVar(value="就绪")
        step_label = ttk.Label(win, textvariable=self.search_calibration_step, font=("微软雅黑", 12), foreground="orange")
        step_label.pack(pady=5)

        coords_label = ttk.Label(win, text="当前坐标: 未获取", font=("微软雅黑", 10))
        coords_label.pack(pady=5)

        saved_coords = self.config_manager.get("search_pos", None)
        if saved_coords:
            coords_label.config(text=f"已保存: {saved_coords}")

        self.search_calibrating = False
        self.search_calibration_coords = None

        def start_calibration():
            try:

                self.search_calibrating = True
                self.search_calibration_step.set("校准模式已激活!请点击微信窗口中的搜索框")

                def monitor_click():
                    while self.search_calibrating:
                        if win32api.GetKeyState(win32con.VK_LBUTTON) < 0:
                            x, y = win32api.GetCursorPos()
                            self.search_calibration_coords = (x, y)

                            def update_ui():
                                coords_label.config(text=f"获取坐标成功: ({x}, {y})")
                                self.search_calibration_step.set("坐标已获取!请点击保存")

                            self.root.after(0, update_ui)

                            self.search_calibrating = False
                            break
                        time.sleep(0.05)

                threading.Thread(target=monitor_click, daemon=True).start()

            except ImportError:
                coords_label.config(text="请先安装 pywin32")
                messagebox.showerror("错误", "需要先安装 pywin32\n运行: pip install pywin32")

        def stop_calibration():
            self.search_calibrating = False
            self.search_calibration_step.set("校准已停止")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="进入校准模式", command=start_calibration).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="停止", command=stop_calibration).pack(side=tk.LEFT, padx=5)

        ttk.Label(win, text="保存坐标到配置:", font=("微软雅黑", 10)).pack(pady=(15, 5))

        coord_frame = ttk.Frame(win)
        coord_frame.pack(pady=5)
        ttk.Label(coord_frame, text="X:").pack(side=tk.LEFT)
        x_entry = ttk.Entry(coord_frame, width=8)
        if saved_coords:
            x_entry.insert(0, str(saved_coords[0]))
        x_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(coord_frame, text="Y:").pack(side=tk.LEFT)
        y_entry = ttk.Entry(coord_frame, width=8)
        if saved_coords:
            y_entry.insert(0, str(saved_coords[1]))
        y_entry.pack(side=tk.LEFT, padx=5)

        def save_coords():
            try:
                x = int(x_entry.get())
                y = int(y_entry.get())
                self.wechat_controller.search_pos = (x, y)
                self.config_manager.set("search_pos", (x, y))
                messagebox.showinfo("成功", f"搜索框坐标已保存: ({x}, {y})")
                win.destroy()
            except ValueError:
                messagebox.showerror("错误", "请输入有效的坐标")

        def fill_coords():
            if self.search_calibration_coords:
                x_entry.delete(0, tk.END)
                x_entry.insert(0, str(self.search_calibration_coords[0]))
                y_entry.delete(0, tk.END)
                y_entry.insert(0, str(self.search_calibration_coords[1]))
            elif saved_coords:
                x_entry.delete(0, tk.END)
                x_entry.insert(0, str(saved_coords[0]))
                y_entry.delete(0, tk.END)
                y_entry.insert(0, str(saved_coords[1]))

        btn_frame2 = ttk.Frame(win)
        btn_frame2.pack(pady=10)

        ttk.Button(btn_frame2, text="填充坐标", command=fill_coords).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame2, text="保存坐标", command=save_coords).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame2, text="关闭", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def show_ocr_region_calibration(self):
        """OCR截图区域校准工具"""
        win = tk.Toplevel(self.root)
        win.title("📷 OCR截图区域校准")
        win.geometry("600x500")
        win.configure(bg="#1e1e2e")
        win.transient(self.root)
        ttk.Label(win, text="📷 OCR截图区域校准", font=("微软雅黑", 14, "bold")).pack(pady=10)
        info_text = """说明:
此功能用于调整OCR识别区域的范围。
区域使用相对于窗口的比例表示(0.0-1.0之间)。
- left: 左侧起始位置比例
- top: 顶部起始位置比例
- width: 区域宽度比例
- height: 区域高度比例
默认:left=0.3, top=0.1, width=0.65, height=0.75
提示:校准后OCR将使用新的区域进行截图识别。"""
        ttk.Label(win, text=info_text, justify=tk.LEFT).pack(pady=10)
        saved_region = self.config_manager.get("ocr_region", None)
        if saved_region:
            ttk.Label(win, text=f"已保存区域: {saved_region}", foreground="green").pack(pady=5)
        else:
            ttk.Label(win, text="当前使用默认区域", foreground="gray").pack(pady=5)
        ttk.Label(win, text="输入区域比例(相对窗口大小):", font=("微软雅黑", 11)).pack(pady=(10, 5))

        region_frame = ttk.Frame(win)
        region_frame.pack(pady=10)

        ttk.Label(region_frame, text="left:").grid(row=0, column=0, padx=5, pady=5)
        left_entry = ttk.Entry(region_frame, width=8)
        left_entry.grid(row=0, column=1, padx=5, pady=5)
        if saved_region:
            left_entry.insert(0, str(saved_region[0]))
        else:
            left_entry.insert(0, "0.3")

        ttk.Label(region_frame, text="top:").grid(row=0, column=2, padx=5, pady=5)
        top_entry = ttk.Entry(region_frame, width=8)
        top_entry.grid(row=0, column=3, padx=5, pady=5)
        if saved_region:
            top_entry.insert(0, str(saved_region[1]))
        else:
            top_entry.insert(0, "0.1")

        ttk.Label(region_frame, text="width:").grid(row=1, column=0, padx=5, pady=5)
        width_entry = ttk.Entry(region_frame, width=8)
        width_entry.grid(row=1, column=1, padx=5, pady=5)
        if saved_region:
            width_entry.insert(0, str(saved_region[2]))
        else:
            width_entry.insert(0, "0.65")

        ttk.Label(region_frame, text="height:").grid(row=1, column=2, padx=5, pady=5)
        height_entry = ttk.Entry(region_frame, width=8)
        height_entry.grid(row=1, column=3, padx=5, pady=5)
        if saved_region:
            height_entry.insert(0, str(saved_region[3]))
        else:
            height_entry.insert(0, "0.75")

        def reset_to_default():
            left_entry.delete(0, tk.END)
            left_entry.insert(0, "0.3")
            top_entry.delete(0, tk.END)
            top_entry.insert(0, "0.1")
            width_entry.delete(0, tk.END)
            width_entry.insert(0, "0.65")
            height_entry.delete(0, tk.END)
            height_entry.insert(0, "0.75")

        def save_region():
            try:
                left = float(left_entry.get())
                top = float(top_entry.get())
                width = float(width_entry.get())
                height = float(height_entry.get())

                if not (0 <= left < 1 and 0 <= top < 1 and 0 < width <= 1 and 0 < height <= 1):
                    messagebox.showerror("错误", "比例值必须在 0-1 之间(width和height必须大于0)")
                    return

                if left + width > 1 or top + height > 1:
                    messagebox.showerror("错误", "区域超出窗口范围")
                    return

                region = (left, top, width, height)
                self.wechat_controller.ocr_region = region
                self.config_manager.set("ocr_region", region)
                messagebox.showinfo("成功", f"OCR截图区域已保存: {region}")
                win.destroy()
            except ValueError:
                messagebox.showerror("错误", "请输入有效的数字")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="恢复默认", command=reset_to_default).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="保存区域", command=save_region).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def toggle_ai(self, enabled):
        self.use_ai_features = enabled

    def execute_command_with_feedback(self, command):
        """执行命令并返回执行结果(线程安全版本)"""
        try:
            # 直接执行指令,不捕获 UI 输出
            self.do_task(command)
            # 等待一小段时间,确保异步任务有机会开始
            time.sleep(1)
            return f"✅ 指令已执行:{command}"
        except Exception as e:
            return f"❌ 指令执行失败:{str(e)}"

    def execute_system_command(self, command):
        """供AI智能体使用的命令执行器"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                self.say("系统", f"✅ 命令执行成功: {command[:30]}...")
                return {"success": True, "stdout": result.stdout, "stderr": result.stderr}
            else:
                self.say("系统", f"❌ 命令执行失败: {result.stderr or '未知错误'}")
                return {"success": False, "error": result.stderr or "未知错误", "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            self.say("系统", f"❌ 命令执行超时: {command[:30]}...")
            return {"success": False, "error": "命令执行超时"}
        except Exception as e:
            self.say("系统", f"❌ 命令执行异常: {str(e)}")
            return {"success": False, "error": str(e)}

    # ---------- 微信功能 ----------
    def toggle_wechat_listener(self):
        with self.listener_lock:
            if not self.wechat_listener_running:
                if not self.wechat_controller.is_wechat_window_visible():
                    # 尝试自动打开微信
                    self.say("系统", "🔍 微信窗口未找到,尝试自动打开微信...")
                    auto_opened = self._try_auto_open_wechat()
                    if not auto_opened:
                        self.say("系统", "❌ 无法自动打开微信,请确保微信已安装。")
                        return
                    # 等待微信打开
                    self.say("系统", "⏳ 等待微信启动...")
                    time.sleep(5)
                    if not self.wechat_controller.is_wechat_window_visible():
                        self.say("系统", "❌ 微信启动失败,请手动打开微信。")
                        return

                # 获取最新消息,初始化 last_message_id
                self.wechat_controller.update_last_message_id()
                self.wechat_listener_running = True
                self.listener_paused = False  # 确保暂停标志被重置
                self.root.after(0, lambda: self.listener_btn.config(text="⏸️ 停止监听"))
                self.wechat_listener_thread = threading.Thread(target=self.wechat_listener_loop, daemon=True)
                self.wechat_listener_thread.start()
                self.say("系统", f"已开始监听来自「{self.wechat_controller.contact}」的微信消息,间隔 {self.wechat_controller.check_interval} 秒。")
            else:
                self.wechat_listener_running = False
                self.listener_paused = False  # 重置暂停标志
                self.root.after(0, lambda: self.listener_btn.config(text="▶️ 开始监听"))
                self.say("系统", "已停止监听微信指令。")

    def _try_auto_open_wechat(self):
        """尝试自动打开微信(通过宏或直接启动)"""
        try:
            # 首先检查是否有"打开微信"的宏
            macros = get_recorder().list_macros()
            open_wechat_macro = None
            for macro in macros:
                name = macro.get("name", "").lower()
                if "微信" in name and ("打开" in name or "open" in name):
                    open_wechat_macro = macro
                    break

            if open_wechat_macro:
                self.say("系统", f"🎬 正在播放宏: {open_wechat_macro['name']}")
                get_player().play(open_wechat_macro["file"])
                return True

            # 如果没有宏,尝试直接启动微信
            self.say("系统", "📂 未找到打开微信的宏,尝试直接启动...")
            wechat_paths = [
                r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
                r"C:\Program Files\Tencent\WeChat\WeChat.exe",
                str(Path.home() / "AppData" / "Local" / "Tencent" / "WeChat" / "WeChat.exe")
            ]

            for path in wechat_paths:
                if Path(path).exists():
                    os.startfile(path)
                    self.say("系统", f"✅ 已启动微信: {path}")
                    return True

            self.say("系统", "⚠️ 未找到微信安装路径,请先录制「打开微信」的宏")
            return False

        except Exception as e:
            logger.error(f"自动打开微信失败: {e}")
            return False

    def _get_command_triggers(self):
        """获取指令触发词列表"""
        return self.config_manager.get("command_triggers", ["¥", "¥"])

    def _extract_command(self, text):
        """从消息中提取命令,支持多个触发词"""
        if not text:
            return None

        triggers = self._get_command_triggers()

        # 调试:记录触发词列表
        logger = logging.getLogger("AIPCHelper")
        logger.debug(f"提取命令: 原始文本='{text}', 触发词列表={triggers}")

        # 预处理:标准化文本一次
        normalized_text = self._normalize_text(text)
        if not normalized_text:
            logger.debug(f"文本标准化后为空")
            return None

        logger.debug(f"标准化后文本='{normalized_text}'")

        for trigger in triggers:
            if not trigger:
                continue

            # 标准化触发词
            normalized_trigger = self._normalize_text(trigger)
            if not normalized_trigger:
                continue

            logger.debug(f"检查触发词: '{trigger}' -> 标准化: '{normalized_trigger}'")

            # 在标准化文本中检查是否以标准化触发词开头
            if normalized_text.startswith(normalized_trigger):
                logger.debug(f"匹配成功! 触发词: '{trigger}', 标准化触发词: '{normalized_trigger}'")
                # 从标准化文本中提取命令部分
                # 标准化后字符数不变,使用标准化触发词长度提取
                command = normalized_text[len(normalized_trigger):].strip()
                logger.debug(f"提取到命令: '{command}'")
                return command

        logger.debug(f"未找到匹配的触发词")
        return None

    def _normalize_text(self, text):
        """标准化文本:去除不可见字符,处理全角/半角符号差异"""
        if not text:
            return ""

        # 保存原始文本用于调试
        original = text

        # 去除首尾空白字符
        text = text.strip()

        # 替换常见的不可见字符和零宽字符
        # 移除零宽空格、零宽连字符、零宽非连接符等
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)

        # 处理全角/半角符号映射
        # 货币符号
        text = text.replace('\uffe5', '\u00a5')  # 全角"¥" -> 半角"¥"

        # 其他常见全角符号映射
        fullwidth_to_halfwidth = {
            '\uff01': '!',  # 全角感叹号
            '\uff0c': ',',  # 全角逗号
            '\uff0e': '.',  # 全角句号
            '\uff1a': ':',  # 全角冒号
            '\uff1b': ';',  # 全角分号
            '\uff1f': '?',  # 全角问号
            '\uff08': '(',  # 全角左括号
            '\uff09': ')',  # 全角右括号
            '\uff3b': '[',  # 全角左方括号
            '\uff3d': ']',  # 全角右方括号
            '\uff5b': '{',  # 全角左大括号
            '\uff5d': '}',  # 全角右大括号
            '\uff0d': '-',  # 全角连字符
            '\uff5e': '~',  # 全角波浪号
        }

        for full, half in fullwidth_to_halfwidth.items():
            text = text.replace(full, half)

        # 调试:记录标准化前后的差异
        if original != text:
            logger = logging.getLogger("AIPCHelper")
            logger.debug(f"文本标准化: '{original}' -> '{text}'")

        return text

    def wechat_listener_loop(self):
        import random
        processing = False
        consecutive_failures = 0
        max_consecutive_failures = 5

        base_interval = self.wechat_controller.check_interval
        last_check = time.time()

        while True:
            current_time = time.time()
            with self.listener_lock:
                if not self.wechat_listener_running or not self.running:
                    break
                # 如果监听被暂停,跳过检查
                if self.listener_paused:
                    should_check = False
                else:
                    should_check = (current_time - last_check) >= base_interval

            if should_check:
                last_check = current_time
                try:
                    msg_data = self.wechat_controller.check_wechat_message()
                    if msg_data:
                        logger.debug(f"检测到微信消息: {msg_data}")
                    if msg_data and not processing:
                        text = msg_data['text'].strip()
                        logger.debug(f"处理消息文本: '{text}'")
                        command = self._extract_command(text)

                        if command:
                            logger.info(f"成功提取命令: '{command}'")
                            processing = True
                            consecutive_failures = 0

                            # 暂停监听
                            with self.listener_lock:
                                self.listener_paused = True
                                logger.info("检测到命令,暂停微信监听")

                            # # 直接执行命令并回复微信
                            def exec_and_reply():
                                try:
                                    feedback = self.execute_command_with_feedback(command)
                                    contact = self.wechat_controller.contact
                                    self.say("系统", f"📤 微信回复: {feedback}")
                                    self.wechat_controller.send_wechat_message(contact, feedback)
                                except Exception as e:
                                    err = f"❌ 执行失败: {str(e)}"
                                    self.say("系统", err)
                                    try:
                                        self.wechat_controller.send_wechat_message(self.wechat_controller.contact, err)
                                    except:
                                        pass
                                finally:
                                    with self.listener_lock:
                                        self.listener_paused = False
                                    logger.info("微信监听已恢复")

                            threading.Thread(target=exec_and_reply, daemon=True).start()

                            processing = False
                        else:
                            logger.debug("未提取到命令(command为None或空)")
                except Exception as e:
                    logger.error(f"监听微信消息异常:{e}")
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        self.say("系统", f"⚠️ 连续失败 {consecutive_failures} 次,自动停止监听")
                        with self.listener_lock:
                            self.wechat_listener_running = False
                        self.root.after(0, lambda: self.listener_btn.config(text="▶️ 开始监听"))
                        break

            time.sleep(0.5)

    def _process_wechat_command(self, command):
        """处理微信指令的公共方法"""
        try:
            self.say("系统", f"📨 收到微信指令:{command}")
            try:
                feedback = self.execute_command_with_feedback(command)
                feedback_contact = self.wechat_controller.contact
                self.say("系统", f"📤 发送反馈给{feedback_contact}:{feedback}")
                self.wechat_controller.send_wechat_message(feedback_contact, feedback)
            except Exception as e:
                error_msg = f"❌ 指令执行失败:{str(e)}"
                feedback_contact = self.wechat_controller.contact
                self.say("系统", f"📤 发送错误反馈给{feedback_contact}:{error_msg}")
                try:
                    self.wechat_controller.send_wechat_message(feedback_contact, error_msg)
                except Exception as send_err:
                    logger.error(f"发送错误反馈失败:{send_err}")
        except Exception as e:
            logger.error(f"处理微信指令异常: {e}")

    def on_wechat_message(self, msg_text):
        """微信新消息回调函数(线程安全,通过root.after调用)"""
        msg_text = msg_text.strip()
        if not msg_text:
            return
        self.say("微信", f"📨 新消息:{msg_text}")

        # 尝试自动回复
        try:
            auto_reply = self.social_skills.auto_reply_wechat(msg_text)
            if auto_reply:
                self.say("系统", f"🤖 自动回复:{auto_reply}")
                # 延迟1秒后发送回复
                self.root.after(1000, lambda: self.wechat_controller.send_wechat_message(target="文件传输助手", message=auto_reply))
        except Exception as e:
            logger.error(f"自动回复失败: {e}")

        command = self._extract_command(msg_text)
        if command:
            self._process_wechat_command(command)

    def set_wechat_contact(self):
        contact = simpledialog.askstring("设置联系人", "请输入要监听的微信好友/群聊名称:", initialvalue=self.wechat_controller.contact)
        if contact:
            self.wechat_controller.set_contact(contact)
            interval = simpledialog.askinteger("检查间隔", "请输入检查间隔(秒,建议5-30):", minvalue=2, maxvalue=60, initialvalue=self.wechat_controller.check_interval)
            if interval:
                self.wechat_controller.set_check_interval(interval)
            self.config_manager.set("wechat_contact", contact)
            self.config_manager.set("wechat_check_interval", interval)
            self.say("系统", f"监听联系人已设置为:{contact},间隔 {interval} 秒。")

    def diagnose_wechat(self):
        """诊断微信连接状态"""
        def run_diagnosis():
            self.say("系统", "🔍 开始诊断微信连接...")
            try:
                result = self.wechat_controller.test_wechat_connection()

                if result["success"]:
                    info = "\n".join(result["steps"])
                    self.say("系统", f"✅ 微信连接诊断通过!\n{info}")
                else:
                    steps_info = "\n".join(result["steps"]) if result["steps"] else ""
                    error_info = result.get("error", "未知错误")
                    self.say("系统", f"❌ 微信连接诊断失败\n{steps_info}\n错误: {error_info}")

                    diagnostic_info = self.wechat_controller.get_diagnostic_info()
                    self.say("系统", f"📋 诊断信息:\n"
                             f"- OCR可用: {diagnostic_info.get('ocr_available', False)}\n"
                             f"- OCR启用: {diagnostic_info.get('ocr_enabled', False)}\n"
                             f"- 监听联系人: {diagnostic_info.get('contact', 'N/A')}\n"
                             f"- 检查间隔: {diagnostic_info.get('check_interval', 'N/A')}秒\n"
                             f"- 上次错误: {diagnostic_info.get('last_error', '无')}")
            except Exception as e:
                self.say("系统", f"❌ 诊断过程异常: {str(e)}")
                traceback.print_exc()

        threading.Thread(target=run_diagnosis, daemon=True).start()

    # ---------- 定时任务 ----------
    def schedule_wechat_message(self):
        win = tk.Toplevel(self.root)
        win.title("定时微信消息")
        win.geometry("600x500")
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
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        ttk.Label(content_frame, text="📱 定时微信消息", font=("微软雅黑", 14, "bold")).pack(pady=10)
        ttk.Label(content_frame, text="关闭窗口后任务继续运行,到时间自动发送", foreground="gray").pack(pady=(0, 10))
        ttk.Label(content_frame, text="目标好友/群聊名称:", font=("微软雅黑", 11)).pack(pady=5)
        target_entry = ttk.Entry(content_frame, font=("微软雅黑", 12), width=40)
        target_entry.pack(pady=5)
        ttk.Label(content_frame, text="消息内容:", font=("微软雅黑", 11)).pack(pady=5)
        msg_text = scrolledtext.ScrolledText(
            content_frame, font=("微软雅黑", 11), height=6, width=40,
            bg="#313244", fg="#cdd6f4"
        )
        msg_text.pack(pady=5)
        ttk.Label(content_frame, text="发送方式:", font=("微软雅黑", 11)).pack(pady=5)
        send_mode = tk.StringVar(value="immediate")
        frame_mode = ttk.Frame(content_frame)
        frame_mode.pack(pady=5)
        ttk.Radiobutton(frame_mode, text="立即发送", variable=send_mode, value="immediate").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(frame_mode, text="定时发送", variable=send_mode, value="scheduled").pack(side=tk.LEFT, padx=10)
        ttk.Label(content_frame, text="发送时间(每天执行):", font=("微软雅黑", 11)).pack(pady=5)
        frame_time = ttk.Frame(content_frame)
        frame_time.pack(pady=5)
        now = datetime.now()
        hour = now.hour
        minute = now.minute

        ttk.Label(frame_time, text="时:").pack(side=tk.LEFT, padx=5)
        hour_var = tk.StringVar(value=str(hour).zfill(2))
        hour_combo = ttk.Combobox(frame_time, textvariable=hour_var, values=[str(i).zfill(2) for i in range(0, 24)], width=4, state="readonly")
        hour_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(frame_time, text="分:").pack(side=tk.LEFT, padx=5)
        minute_var = tk.StringVar(value=str(minute).zfill(2))
        minute_combo = ttk.Combobox(frame_time, textvariable=minute_var, values=[str(i).zfill(2) for i in range(0, 60, 5)], width=4, state="readonly")
        minute_combo.pack(side=tk.LEFT, padx=5)

        var_repeat = tk.BooleanVar(value=True)
        ttk.Checkbutton(content_frame, text="每天重复", variable=var_repeat).pack(pady=5)

        def confirm():
            target = target_entry.get().strip()
            message = msg_text.get("1.0", tk.END).strip()
            if not target or not message:
                messagebox.showerror("错误", "请填写完整信息!")
                return

            mode = send_mode.get()
            if mode == "immediate":
                # 立即发送
                def send_with_feedback():
                    success = self.wechat_controller.send_wechat_message(target, message)
                    if success:
                        self.say("系统", f"✅ 微信消息发送成功!\n目标:{target}\n内容:{message[:20]}...")
                    else:
                        self.say("系统", f"❌ 微信消息发送失败\n目标:{target}")
                threading.Thread(target=send_with_feedback, daemon=True).start()
                self.say("系统", f"⏳ 正在发送微信消息给:{target}")
                win.destroy()
            else:
                # 定时发送
                try:
                    hour = int(hour_var.get())
                    minute = int(minute_var.get())
                    if not (0 <= hour < 24):
                        messagebox.showerror("错误", "小时必须在 0-23 之间!")
                        return
                    if not (0 <= minute < 60):
                        messagebox.showerror("错误", "分钟必须在 0-59 之间!")
                        return
                except ValueError:
                    messagebox.showerror("错误", "时间格式错误,请重新选择!")
                    return

                send_time = f"{hour_var.get()}:{minute_var.get()}"
                self.add_wechat_scheduled_task(target, message, send_time)
                win.destroy()

        frame_buttons = ttk.Frame(win)
        frame_buttons.pack(pady=10)
        ttk.Button(frame_buttons, text="✅ 确认发送", command=confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(frame_buttons, text="❌ 取消", command=win.destroy).pack(side=tk.LEFT, padx=10)

    def add_wechat_scheduled_task(self, target, message, send_time):
        try:
            datetime.strptime(send_time, "%H:%M")
        except ValueError:
            self.say("系统", "时间格式错误,请使用 HH:MM 格式。")
            return
        # 生成任务名称
        name = f"{target}任务{send_time}"
        self.task_scheduler.add_task(
            name=name,
            task_type="wechat_message",
            schedule_config={"type": "daily", "time": send_time},
            params={"target": target, "message": message}
        )
        self.scheduled_tasks = self.task_scheduler.scheduled_tasks
        self.config_manager.set("scheduled_tasks", self.scheduled_tasks)
        self.say("系统", f"✅ 已添加定时任务:\n目标:{target}\n时间:{send_time}")

    def show_scheduled_tasks(self):
        """显示任务管理器窗口"""
        win = tk.Toplevel(self.root)
        win.title("📋 任务管理器")
        win.geometry("800x500")
        win.configure(bg="#1e1e2e")
        # 创建 Treeview
        columns = ("类型", "名称", "执行时间/间隔", "状态", "操作")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        tree.heading("类型", text="类型")
        tree.heading("名称", text="名称")
        tree.heading("执行时间/间隔", text="执行时间/间隔")
        tree.heading("状态", text="状态")
        tree.heading("操作", text="操作")

        # 设置列宽
        tree.column("类型", width=100)
        tree.column("名称", width=200)
        tree.column("执行时间/间隔", width=150)
        tree.column("状态", width=100)
        tree.column("操作", width=100)

        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # 添加滚动条
        scrollbar = ttk.Scrollbar(win, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_task_list():
            # 清空现有数据
            for item in tree.get_children():
                tree.delete(item)

            # 显示定时任务
            for task in self.task_scheduler.get_tasks():
                tree.insert("", tk.END, values=(
                    "定时",
                    task.get("name", "未命名"),
                    task.get("send_time", ""),
                    task.get("status", ""),
                    "查看"
                ))

            # 显示循环任务
            for task in self.task_scheduler.get_loop_tasks():
                tree.insert("", tk.END, values=(
                    "循环",
                    task.get("name", "未命名"),
                    f"{task.get('interval_minutes', 60)}分钟",
                    "运行中" if task.get("running") else "已停止",
                    "查看"
                ))

        # 删除按钮的回调
        def delete_task():
            selected = tree.selection()
            if selected:
                item = tree.item(selected[0])
                values = item['values']
                # 根据类型删除
                if values[0] == "定时":
                    # 根据名称查找索引
                    tasks = self.task_scheduler.get_tasks()
                    for i, task in enumerate(tasks):
                        if task.get("name") == values[1]:
                            self.task_scheduler.remove_task(task["id"])
                            break
                elif values[0] == "循环":
                    self.task_scheduler.stop_loop_task(values[1])
                refresh_task_list()

        # 停止循环任务
        def stop_loop_task():
            selected = tree.selection()
            if selected:
                item = tree.item(selected[0])
                values = item['values']
                if values[0] == "循环":
                    task_name = values[1]
                    tasks = self.task_scheduler.get_loop_tasks()
                    for task in tasks:
                        if task.get("name") == task_name:
                            if task.get("running"):
                                self.task_scheduler.stop_loop_task(task_name)
                                self.say("系统", f"已停止循环任务: {task_name}")
                            else:
                                self.say("系统", f"任务 {task_name} 已停止,无法再次停止")
                            break
                    refresh_task_list()

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="删除选中", command=delete_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="停止任务", command=stop_loop_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="刷新", command=refresh_task_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=win.destroy).pack(side=tk.LEFT, padx=5)

        # 初始加载
        refresh_task_list()

    def show_automation_panel(self):
        """显示自动化任务面板"""
        win, content_frame = self.create_scrollable_window("🔄 自动化任务", 650, 600)

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
                self.task_scheduler.add_command_task(name, command, send_time)
                self.say("系统", f"✅ 已添加命令任务:{name},执行时间 {send_time}")
            else:
                messagebox.showwarning("警告", "请填写完整信息")

        ttk.Button(parent, text="添加任务", command=add_command_task).pack(pady=10)

    def _build_app_tab(self, parent):
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
                self.task_scheduler.add_app_task(name, app_path, send_time)
                self.say("系统", f"✅ 已添加应用任务:{name},执行时间 {send_time}")
            else:
                messagebox.showwarning("警告", "请填写完整信息")

        ttk.Button(parent, text="添加任务", command=add_app_task).pack(pady=10)

    def _build_script_tab(self, parent):
        ttk.Label(parent, text="任务名称:").pack(pady=5)
        script_name_entry = ttk.Entry(parent, width=40)
        script_name_entry.pack(pady=5)

        ttk.Label(parent, text="脚本路径:").pack(pady=5)
        script_path_entry = ttk.Entry(parent, width=40)
        script_path_entry.pack(pady=5)

        ttk.Button(parent, text="浏览", command=lambda: script_path_entry.insert(0, filedialog.askopenfilename(title="选择脚本", filetypes=[("脚本文件", "*.py *.bat *.ps1"), ("所有文件", "*.*")]))).pack(pady=5)

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
                self.task_scheduler.add_script_task(name, script_path, send_time)
                self.say("系统", f"✅ 已添加脚本任务:{name},执行时间 {send_time}")
            else:
                messagebox.showwarning("警告", "请填写完整信息")

        ttk.Button(parent, text="添加任务", command=add_script_task).pack(pady=10)

    def _build_loop_task_tab(self, parent):
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
                self.task_scheduler.add_loop_task(name, "command", interval, params={"command": task_value})
                self.say("系统", f"✅ 已添加循环命令任务:{name},间隔 {interval} 分钟")
            elif task_type == "app":
                self.task_scheduler.add_loop_task(name, "app", interval, params={"app_path": task_value})
                self.say("系统", f"✅ 已添加循环应用任务:{name},间隔 {interval} 分钟")
            elif task_type == "wechat":
                message = msg_entry.get().strip()
                if not message:
                    messagebox.showwarning("警告", "请填写微信消息内容")
                    return
                self.task_scheduler.add_loop_task(name, "wechat", interval, params={"target": task_value, "message": message})
                self.say("系统", f"✅ 已添加循环微信任务:{name},间隔 {interval} 分钟")

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
        if hasattr(self, 'loop_task_listbox'):
            self.loop_task_listbox.delete(0, tk.END)
            tasks = self.task_scheduler.get_loop_tasks()
            for task in tasks:
                status = "运行中" if task.get("running") else "已停止"
                self.loop_task_listbox.insert(tk.END, f"{task.get('name', '未命名')} - {task.get('interval_minutes', 60)}分钟 - {status}")

    def _stop_selected_loop_task(self):
        selection = self.loop_task_listbox.curselection()
        if selection:
            tasks = self.task_scheduler.get_loop_tasks()
            if selection[0] < len(tasks):
                name = tasks[selection[0]].get("name")
                self.task_scheduler.stop_loop_task(name)
                self.say("系统", f"⏹ 已停止循环任务:{name}")
                self._refresh_loop_tasks()

    def show_macro_panel(self):
        """显示宏录制面板"""
        win, content_frame = self.create_scrollable_window("🎬 宏录制", 550, 550)

        self.macro_recorder = get_recorder()
        self.macro_player = get_player()
        self.is_recording = False

        ttk.Label(content_frame, text="🎬 宏录制/回放", font=("微软雅黑", 14, "bold")).pack(pady=10)
        ttk.Label(content_frame, text="录制鼠标和键盘操作,自动执行重复任务", foreground="gray").pack(pady=(0, 10))

        ttk.Label(content_frame, text="录制说明:点击「开始录制」后进行操作,完成后点击「停止并保存」", font=("微软雅黑", 9), foreground="orange").pack(pady=5)

        speed_frame = ttk.Frame(content_frame)
        speed_frame.pack(pady=5)
        ttk.Label(speed_frame, text="播放速度:").pack(side=tk.LEFT)
        self.macro_speed_var = tk.DoubleVar(value=1.0)
        speed_combo = ttk.Combobox(speed_frame, textvariable=self.macro_speed_var, values=["0.5", "1.0", "1.5", "2.0"], width=5, state="readonly")
        speed_combo.pack(side=tk.LEFT, padx=5)

        self.macro_repeat_var = tk.IntVar(value=1)
        ttk.Label(speed_frame, text="  重复次数:").pack(side=tk.LEFT)
        repeat_combo = ttk.Combobox(speed_frame, textvariable=self.macro_repeat_var, values=["1", "2", "3", "5"], width=3, state="readonly")
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
        if not self.is_recording:
            name = "未命名宏"
            self.macro_recorder.start_recording(name)
            self.is_recording = True
            self.record_btn.config(text="⏸ 录制中...")
            self.say("系统", "🔴 开始录制宏,请在电脑上进行操作...")
        else:
            self.say("系统", "录制进行中,请点击\"停止并保存\"")

    def stop_and_save_macro(self):
        """停止并保存宏"""
        if self.is_recording:
            macro_data = self.macro_recorder.stop_recording()
            if macro_data:
                name = macro_data.get("name", "未命名宏")
                macro_name = simpledialog.askstring("保存宏", "请输入宏名称:", initialvalue=name)
                if macro_name:
                    macro_data["name"] = macro_name
                    self.macro_recorder.save_macro(macro_data)
                    self.say("系统", f"✅ 宏已保存:{macro_name}")
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
        selection = self.macro_listbox.curselection()
        if selection:
            macros = self.macro_recorder.list_macros()
            if selection[0] < len(macros):
                macro_name = macros[selection[0]]["file"]
                speed = self.macro_speed_var.get() if hasattr(self, 'macro_speed_var') else 1.0
                repeat = self.macro_repeat_var.get() if hasattr(self, 'macro_repeat_var') else 1
                self.say("系统", f"▶ 正在播放宏:{macros[selection[0]]['name']} (速度:{speed}x, 重复:{repeat}次)")
                threading.Thread(target=lambda: self.macro_player.play(macro_name, speed=speed, repeat=repeat), daemon=True).start()

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
                    self.say("系统", f"✅ 宏已删除")

    def show_code_workspace(self):
        """显示编程工作区面板"""
        win, content_frame = self.create_scrollable_window("💻 编程工作区", 800, 650)

        from modules.code_workspace_panel import CodeWorkspacePanel
        panel = CodeWorkspacePanel(content_frame, self)

        ttk.Button(content_frame, text="关闭", command=win.destroy).pack(pady=10)

    def show_ai_agent_panel(self):
        """显示AI智能体面板"""
        win, content_frame = self.create_scrollable_window("🤖 AI智能体", 700, 550)
        ttk.Label(content_frame, text="🤖 AI智能体 - 任务规划与执行", font=("微软雅黑", 14, "bold")).pack(pady=10)
        ttk.Label(content_frame, text="输入任务指令,AI自动规划并执行", foreground="gray").pack(pady=(0, 10))
        ttk.Label(content_frame, text="输入任务指令:", font=("微软雅黑", 11)).pack(pady=5)
        task_entry = ttk.Entry(content_frame, width=60)
        task_entry.pack(pady=5)
        ttk.Label(content_frame, text="示例:搜索Python教程并保存到文档", font=("微软雅黑", 9), foreground="gray").pack(pady=2)
        task_result_text = scrolledtext.ScrolledText(content_frame, height=8, width=60, state=tk.DISABLED)
        task_result_text.pack(pady=10, padx=10)
        def append_result(text):
            def update_ui():
                task_result_text.config(state=tk.NORMAL)
                task_result_text.insert(tk.END, text + "\n")
                task_result_text.see(tk.END)
                task_result_text.config(state=tk.DISABLED)
            self.root.after(0, update_ui)
        def execute_ai_task():
            task = task_entry.get().strip()
            if not task:
                messagebox.showwarning("警告", "请输入任务指令")
                return
            task_entry.config(state=tk.DISABLED)
            append_result(f"🤔 AI正在规划任务:{task}...")
            def run_task():
                try:
                    if not hasattr(self, 'ai_agent') or self.ai_agent is None:
                        self.ai_agent = get_ai_agent(
                            ai_helper=self.ai_helper,
                            config_manager=self.config_manager
                        )
                        self.ai_agent.set_wechat_controller(self.wechat_controller)
                        self.ai_agent.set_command_executor(self.execute_system_command)
                        self.ai_agent.set_feedback_callback(lambda msg, is_error: append_result(f"{'❌' if is_error else '✅'} {msg}"))
                    else:
                        self.ai_agent.ai_helper = self.ai_helper
                    steps = self.ai_agent.plan_task(task)
                    if not steps:
                        append_result("❌ 任务规划失败,请检查Ollama服务是否运行")
                        self.root.after(0, lambda: task_entry.config(state=tk.NORMAL))
                        return
                    plan_text = "\n".join([f"{s.get('step')}. {s.get('action')}" for s in steps])
                    append_result(f"📋 任务计划:\n{plan_text}")
                    if messagebox.askyesno("确认执行", f"共{len(steps)}个步骤,是否执行?"):
                        append_result("▶ 开始执行任务...")
                        results = self.ai_agent.execute_plan(steps)
                        for r in results:
                            if not r.get("success"):
                                append_result(f"❌ 步骤{r.get('step')}失败: {r.get('error', '未知错误')}")
                        success_count = sum(1 for r in results if r.get("success"))
                        append_result(f"✅ 任务完成!成功 {success_count}/{len(results)} 个步骤")
                        doc_org = DocumentOrganizer()
                        save_path = doc_org.create_summary_document(
                            f"任务执行结果: {task[:20]}",
                            [{"title": f"任务: {task}", "content": plan_text + "\n\n执行结果:\n" + "\n".join([f"步骤{r.get('step')}: {'成功' if r.get('success') else '失败'}" for r in results])}]
                        )
                        append_result(f"📄 结果已保存到:{save_path}")
                    else:
                        append_result("⏸ 用户取消执行")
                except Exception as e:
                    append_result(f"❌ 执行失败:{str(e)}")
                finally:
                    self.root.after(0, lambda: task_entry.config(state=tk.NORMAL))
            threading.Thread(target=run_task, daemon=True).start()
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="🚀 执行任务", command=execute_ai_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空结果", command=lambda: task_result_text.config(state=tk.NORMAL) or task_result_text.delete(1.0, tk.END) or task_result_text.config(state=tk.DISABLED)).pack(side=tk.LEFT, padx=5)

        ttk.Label(content_frame, text="快捷操作:", font=("微软雅黑", 11)).pack(pady=10)

        quick_frame = ttk.Frame(content_frame)
        quick_frame.pack(pady=5)

        def quick_search():
            query = simpledialog.askstring("快速搜索", "请输入搜索内容:")
            if query:
                browser = BrowserAutomation()
                browser.search(query)
                self.say("系统", f"🔍 正在搜索:{query}")

        def quick_save_doc():
            content = simpledialog.askstring("快速保存", "请输入要保存的内容:")
            if content:
                doc_org = DocumentOrganizer()
                path = doc_org.create_summary_document("快速记录", [{"title": "内容", "content": content}])
                self.say("系统", f"✅ 文档已保存:{path}")

        def quick_open_app():
            app = simpledialog.askstring("快速启动", "请输入应用名称或路径:")
            if app:
                self.open_app(app)

        ttk.Button(quick_frame, text="🔍 快速搜索", command=quick_search).pack(side=tk.LEFT, padx=5)
        ttk.Button(quick_frame, text="📄 快速记录", command=quick_save_doc).pack(side=tk.LEFT, padx=5)
        ttk.Button(quick_frame, text="📂 启动应用", command=quick_open_app).pack(side=tk.LEFT, padx=5)

        ttk.Button(content_frame, text="关闭", command=win.destroy).pack(pady=10)

    # ---------- 其他功能 ----------
    def choose_folder(self):
        folder = filedialog.askdirectory(title="选择工作目录")
        if folder:
            self.current_folder = folder
            self.config_manager.set("current_folder", folder)
            self.folder_label.config(text=f"📁 当前目录: {self.current_folder}")
            self.say("系统", f"✅ 已切换到目录:{folder}")

    def undo(self):
        if not self.rename_history:
            self.say("系统", "❌ 没有可撤销的操作")
            return
        src, dst = self.rename_history.pop()
        try:
            if os.path.exists(dst):
                os.rename(dst, src)
                self.say("系统", f"✅ 已撤销:{os.path.basename(dst)} → {os.path.basename(src)}")
            else:
                self.say("系统", "❌ 撤销失败:目标文件不存在")
        except Exception as e:
            logger.error(f"撤销失败 {dst} -> {src}: {e}")
            self.say("系统", f"❌ 撤销失败:{e}")

    def clear_chat(self):
        self.chat.config(state=tk.NORMAL)
        self.chat.delete(1.0, tk.END)
        self.chat.config(state=tk.DISABLED)

    def show_help(self):
        help_text = ("🖥️ AI电脑管家 · 功能索引\n\n"
            "━━━ 💬 智能对话 ━━━\n"
            "• 自然语言控制: 输入「打开微信」「截图」「清理临时文件」\n"
            "• AI 对话: 点击「AI助手」进入多轮对话\n"
            "• Hermes 引擎: 点击「🤖 Hermes」切换云端 DeepSeek 模型\n"
            "• 模型切换: 下拉选择 V4 Flash/Pro · 快速/深度/通用/推理\n"
            "• 自动路由: 简单任务→本地极速 · 复杂任务→云端深度\n\n"
            "━━━ 📁 文件管理 ━━━\n"
            "• 智能整理: 按类型自动分类文件到对应文件夹\n"
            "• 查找重复: 扫描并清理重复文件\n"
            "• 大文件: 找出占用空间最大的文件\n"
            "• 清理空文件: 删除大小为 0 的无效文件\n"
            "• 批量重命名: 一键批量修改文件名\n"
            "• 撤销: 撤回上次整理操作,安全无忧\n\n"
            "━━━ ⚙️ 系统控制 ━━━\n"
            "• 电源: 关机 / 重启 / 睡眠 / 锁定 / 取消关机\n"
            "• 工具: 任务管理器 / 系统设置 / CMD / PowerShell\n"
            "• 音量: 增大 / 减小 / 静音\n"
            "• 监控: CPU / 内存 / 磁盘实时状态\n\n"
            "━━━ 📱 微信通讯 ━━━\n"
            "• 消息监听: 启动后通过微信远程指令控制电脑\n"
            "• 定时发送: 设置定时微信消息\n"
            "• 微信指令: 用指令前缀在微信里对电脑发命令\n"
            "• 诊断工具: 检测微信窗口状态\n\n"
            "━━━ 🤖 自动化 ━━━\n"
            "• 宏录制: 录制鼠标键盘操作并回放\n"
            "• 自动化任务: 创建定时/条件触发任务\n"
            "• AI 智能体: 自动搜索信息并生成文档\n"
            "• 编程工作区: 项目监控 + 代码生成 + Git 集成\n\n"
            f"━━━ 🔧 快捷入口 ━━━\n"
            f"• Hermes 终端: 点击「🤖 Hermes」打开原生终端\n"
            f"• AI 设置: 配置 API 服务商和模型参数\n"
            f"• 帮助: 就是这个窗口~\n"
            f"• 状态栏: 底部实时显示 Hermes 连接状态")
        messagebox.showinfo("帮助", help_text)

    def on_closing(self):
        self.running = False
        self.task_scheduler.stop_scheduler()
        with self.listener_lock:
            if self.wechat_listener_running:
                self.wechat_listener_running = False
                if self.wechat_listener_thread:
                    self.wechat_listener_thread.join(timeout=5)
        self.config_manager.set("scheduled_tasks", self.task_scheduler.get_tasks())
        # 关闭对话记忆模块
        if hasattr(self, 'conversation_memory'):
            self.conversation_memory.close()
        self.say("系统", "👋 再见!")
        self.root.destroy()

# ---------- 主函数 ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = AIPCHelperV8(root)
    root.mainloop()
