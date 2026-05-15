"""
main_upgrade.py - AI电脑管家 模块化解耦版（升级版）
基于 EventBus + AppContext 的新架构。

与原 main.py 并存，原版不动，新版逐步接管。
"""
import sys
import os

# ── 0. 启动顺序控制 ─────────────────────────────────────────────────────────

# 确保项目根目录在 path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import logging
import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, ttk, simpledialog
import threading
import time
from pathlib import Path
from datetime import datetime

# ── 1. 核心基础设施 ──────────────────────────────────────────────────────────
from core.event_bus import event_bus, EventPriority
from core.app_context import get_app_context, AppContext
from core.macro_interpreter import MacroVM
from core.workflow_engine import WorkflowEngine

# ── 2. Agent & AI 层 ───────────────────────────────────────────────────────
from agent.model_pool import ModelRouter, TaskType, AITask
from agent.agent import AIAgentCore, get_agent_core, register_builtin_skills
from agent.async_email import AsyncEmailProcessor, AccountConfig, EmailCategory, EmailPriority
from agent.vector_memory import VectorMemory

# ── 3. 知识库解析层 ────────────────────────────────────────────────────────
from kb_parser.semantic_chunker import SemanticChunker
from kb_parser.chromadb_client import get_chromadb_client, CHROMADB_AVAILABLE

# ── 4. 原有模块（保持兼容，逐步迁移）────────────────────────────────────────
from utils.config import ConfigManager
from modules.file_manager import FileManager
from modules.ai_helper import AIHelper
from modules.wechat_controller import WeChatController
from modules.task_scheduler import TaskScheduler
from modules.macro_recorder import MacroRecorder
from modules.system_controller import get_system_controller
from modules.knowledge_base_builder import KnowledgeBaseBuilder
from modules.email_classifier import EmailClassifier
from modules.conversation_memory import ConversationMemory

# ── 日志配置 ─────────────────────────────────────────────────────────────────
log_path = Path.home() / "aipc_helper_upgrade.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(str(log_path), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("MainUpgrade")


# ── App 初始化 ─────────────────────────────────────────────────────────────

def _build_app_context() -> AppContext:
    """
    构建应用上下文，注册所有模块工厂。
    这是 DI 容器，所有模块通过这里获取依赖，而非直接 import。
    """
    ctx = get_app_context()

    # 配置管理器（最基础，其他模块都依赖它）
    ctx.register("config_manager", factory=lambda: ConfigManager())

    # AI 路由层（P0）
    ctx.register("model_router", factory=lambda: ModelRouter(
        config_manager=ctx.get("config_manager")
    ))

    # AI Helper（兼容旧版）
    ctx.register("ai_helper", factory=lambda: AIHelper(
        config_manager=ctx.get("config_manager")
    ))

    # 事件总线（已经在全局单例，这里显式注册）
    ctx.register_instance("event_bus", event_bus)

    # 文件管理器
    ctx.register("file_manager", factory=lambda: FileManager())

    # 系统控制器
    ctx.register("system_controller", factory=lambda: get_system_controller())

    # 微信控制器（依赖 system_controller）
    def _make_wechat():
        sc = ctx.get_or_none("system_controller")
        return WeChatController(system_controller=sc)
    ctx.register("wechat_controller", factory=_make_wechat)

    # 宏录制器
    ctx.register("macro_recorder", factory=lambda: MacroRecorder())

    # 对话记忆（升级版向量记忆）
    def _make_memory():
        config = ctx.get_or_none("config_manager")
        return ConversationMemory(config_manager=config)
    ctx.register("conversation_memory", factory=_make_memory)

    # 知识库
    def _make_kb():
        config = ctx.get_or_none("config_manager")
        return KnowledgeBaseBuilder(config_manager=config)
    ctx.register("knowledge_base", factory=_make_kb)

    # 邮件分类器（原有）
    def _make_email():
        kb = ctx.get_or_none("knowledge_base")
        config = ctx.get_or_none("config_manager")
        return EmailClassifier(config_manager=config, knowledge_base_builder=kb)
    ctx.register("email_classifier", factory=_make_email)

    # 异步邮件处理器（新）
    ctx.register("async_email", factory=lambda: AsyncEmailProcessor(
        config_manager=ctx.get("config_manager"),
        event_bus=event_bus,
    ))

    # Agent 核心（新）
    def _make_agent():
        router = ctx.get_or_none("model_router")
        helper = ctx.get_or_none("ai_helper")
        agent = AIAgentCore(ai_helper=helper, model_router=router)
        register_builtin_skills()
        return agent
    ctx.register("agent_core", factory=_make_agent)

    # 向量记忆（新）
    def _make_vector_memory():
        return VectorMemory()
    ctx.register("vector_memory", factory=_make_vector_memory)

    # 工作流引擎（新）
    def _make_workflow():
        return WorkflowEngine(app_context=ctx, event_bus=event_bus)
    ctx.register("workflow_engine", factory=_make_workflow)

    # 定时任务调度器
    ctx.register("task_scheduler", factory=lambda: TaskScheduler())

    return ctx


# ── 事件订阅 ────────────────────────────────────────────────────────────────

def _subscribe_events(ctx: AppContext):
    """注册事件处理器，把 EventBus 事件路由到 UI 更新"""

    def on_email_new(event):
        email = event.data
        logger.info(f"[Event] New email: {email.subject}")
        # 可以在这里弹窗或更新状态栏

    def on_agent_started(event):
        logger.info(f"[Event] Agent started task")

    def on_agent_completed(event):
        logger.info(f"[Event] Agent completed")

    def on_wechat_message(event):
        logger.info(f"[Event] WeChat message: {str(event.data)[:50]}")

    event_bus.subscribe("email:new", on_email_new, priority=EventPriority.HIGH)
    event_bus.subscribe("agent:started", on_agent_started)
    event_bus.subscribe("agent:completed", on_agent_completed)
    event_bus.subscribe("wechat:message", on_wechat_message)

    logger.info("[MainUpgrade] Event subscriptions registered")


# ── UI 层（新版 Tkinter）────────────────────────────────────────────────────

class UpgradeGUI:
    """
    升级版 GUI。

    改动要点：
    - 所有模块调用走 event_bus，不直接引用
    - 状态面板实时反映各模块健康状态
    - 新增「Agent」面板，可直接调用 AIAgent
    - 新增「知识库」面板，显示 ChromaDB 状态
    """

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.root = tk.Tk()
        self.root.title("AI电脑管家 v2.0（升级版）")
        self.root.geometry("1100x700")

        self._setup_ui()
        self._start_status_updater()

        # 注册关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 绑定快捷键
        self.root.bind("<Control-q>", lambda e: self._on_close())
        self.root.bind("<Control-r>", lambda e: self._reload_modules())

    # ── UI 布局 ─────────────────────────────────────────────────────────

    def _setup_ui(self):
        # 顶部状态栏
        self.status_bar = tk.Label(self.root, text="就绪", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Notebook：多标签页
        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 1: Agent 对话
        nb.add(self._make_agent_tab(nb), text="🤖 Agent")

        # Tab 2: 模块状态
        nb.add(self._make_status_tab(nb), text="📊 状态")

        # Tab 3: 知识库
        nb.add(self._make_kb_tab(nb), text="📚 知识库")

        # Tab 4: 邮件
        nb.add(self._make_email_tab(nb), text="📧 邮件")

        # Tab 5: 宏脚本
        nb.add(self._make_macro_tab(nb), text="⌨️ 宏脚本")

        # Tab 6: 工作流（暂时隐藏，workflow_skills 已删除）
        # nb.add(self._make_workflow_tab(nb), text="🔄 工作流")

    def _make_agent_tab(self, parent):
        frame = ttk.Frame(parent)

        # 输入区
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(input_frame, text="任务描述：").pack(anchor=tk.W)
        self.agent_input = tk.Text(input_frame, height=4, wrap=tk.WORD)
        self.agent_input.pack(fill=tk.X, pady=(5, 5))
        self.agent_input.insert("1.0", "例如：帮我整理桌面的文件，按类型分类")

        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="🚀 执行 Agent", command=self._run_agent).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="⏹ 停止", command=self._stop_agent).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="🧠 查看技能", command=self._list_skills).pack(side=tk.LEFT, padx=5)

        # 输出区
        ttk.Label(frame, text="执行结果：").pack(anchor=tk.W, padx=10)
        self.agent_output = scrolledtext.ScrolledText(frame, height=20, state=tk.DISABLED, wrap=tk.WORD)
        self.agent_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))
        self.agent_output.tag_config("info", foreground="blue")
        self.agent_output.tag_config("error", foreground="red")
        self.agent_output.tag_config("success", foreground="green")

        return frame

    def _make_status_tab(self, parent):
        frame = ttk.Frame(parent)
        self.status_text = scrolledtext.ScrolledText(frame, state=tk.DISABLED, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        return frame

    def _make_kb_tab(self, parent):
        frame = ttk.Frame(parent)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(toolbar, text="📥 添加文件到知识库",
                   command=self._add_kb_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="🔍 语义检索",
                   command=self._kb_search_gui).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="🔄 重新索引",
                   command=self._rebuild_index).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="📂 扫描下载文件夹",
                   command=self._scan_download_folder).pack(side=tk.LEFT, padx=(0, 5))

        # 监控控制按钮
        self.kb_monitor_btn = ttk.Button(toolbar, text="▶️ 启动监控",
                   command=self._toggle_kb_monitor)
        self.kb_monitor_btn.pack(side=tk.LEFT)

        # 状态显示
        self.kb_status_var = tk.StringVar(value="监控状态: 未启动 | 最后扫描: 从未")
        ttk.Label(frame, textvariable=self.kb_status_var, font=("Arial", 9)).pack(anchor=tk.W, padx=10)

        ttk.Label(frame, text="搜索：").pack(anchor=tk.W, padx=10, pady=(10,0))
        self.kb_query_input = ttk.Entry(frame)
        self.kb_query_input.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.kb_query_input.bind("<Return>", lambda e: self._kb_search_gui())

        self.kb_output = scrolledtext.ScrolledText(frame, state=tk.DISABLED, wrap=tk.WORD)
        self.kb_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        return frame

    def _make_email_tab(self, parent):
        frame = ttk.Frame(parent)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(toolbar, text="⚙️ 配置邮箱",
                   command=self._config_email).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="📬 启动邮件监控",
                   command=self._start_email).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="⏹ 停止监控",
                   command=self._stop_email).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="📋 查看草稿",
                   command=self._show_drafts).pack(side=tk.LEFT)

        self.email_output = scrolledtext.ScrolledText(frame, state=tk.DISABLED, wrap=tk.WORD)
        self.email_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        return frame

    def _make_macro_tab(self, parent):
        frame = ttk.Frame(parent)

        ttk.Label(frame, text="宏脚本（DSL）：").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.macro_input = scrolledtext.ScrolledText(frame, height=8, wrap=tk.WORD)
        self.macro_input.pack(fill=tk.X, padx=10, pady=5)
        self.macro_input.insert("1.0", """# 示例：打开微信并发送消息
打开微信
等待(图像: "发送按钮.png", 超时=10)
输入("{clipboard}")
发送()
""")

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, padx=10)
        ttk.Button(btn_frame, text="▶ 执行宏", command=self._run_macro).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="⏹ 停止", command=self._stop_macro).pack(side=tk.LEFT)

        ttk.Label(frame, text="输出：").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.macro_output = scrolledtext.ScrolledText(frame, state=tk.DISABLED, height=12, wrap=tk.WORD)
        self.macro_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        return frame

    def _make_workflow_tab(self, parent):
        frame = ttk.Frame(parent)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(toolbar, text="📋 列出工作流",
                   command=self._list_workflows).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="▶ 运行选中",
                   command=self._run_workflow).pack(side=tk.LEFT)

        self.workflow_output = scrolledtext.ScrolledText(frame, state=tk.DISABLED, wrap=tk.WORD)
        self.workflow_output.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        return frame

    # ── 事件处理 ─────────────────────────────────────────────────────────

    def _run_agent(self):
        task = self.agent_input.get("1.0", tk.END).strip()
        if not task:
            return

        def _do():
            self.agent_output.config(state=tk.NORMAL)
            self.agent_output.insert(tk.END, f"\n[Agent] 开始任务: {task[:60]}...\n", "info")
            self.agent_output.see(tk.END)
            self.agent_output.config(state=tk.DISABLED)

            agent = self.ctx.get("agent_core")
            from agent.agent import AgentContext
            ctx = AgentContext(task=task, max_steps=10)
            result = agent.run(task, ctx)

            self.agent_output.config(state=tk.NORMAL)
            status_tag = "success" if result["success"] else "error"
            self.agent_output.insert(tk.END, f"\n[结果] {result['result']}\n", status_tag)
            self.agent_output.insert(tk.END, f"[步骤数] {result['step_count']}\n", "info")
            self.agent_output.see(tk.END)
            self.agent_output.config(state=tk.DISABLED)

            # 事件通知
            event_bus.post("agent:completed", result, source="UpgradeGUI")

        threading.Thread(target=_do, daemon=True).start()

    def _stop_agent(self):
        agent = self.ctx.get_or_none("agent_core")
        if agent:
            agent.stop()
            self._append_output(self.agent_output, "[已停止]", "error")

    def _list_skills(self):
        agent = self.ctx.get_or_none("agent_core")
        if not agent:
            return
        skills = agent.registry.list_skills()
        self._append_output(self.agent_output, "可用技能：\n", "info")
        for s in skills:
            self._append_output(self.agent_output, f"  • {s['name']}: {s['description']}\n", "info")

    def _config_email(self):
        """配置邮箱对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("配置邮箱")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # 当前配置
        email_classifier = self.ctx.get_or_none("email_classifier")
        current_config = email_classifier.email_config if email_classifier else {}

        # 表单
        ttk.Label(dialog, text="邮箱地址:").pack(anchor=tk.W, padx=10, pady=(10,0))
        email_var = tk.StringVar(value=current_config.get("email_address", ""))
        ttk.Entry(dialog, textvariable=email_var).pack(fill=tk.X, padx=10)

        ttk.Label(dialog, text="密码/授权码:").pack(anchor=tk.W, padx=10, pady=(10,0))
        pwd_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=pwd_var, show="*").pack(fill=tk.X, padx=10)

        ttk.Label(dialog, text="IMAP 服务器:").pack(anchor=tk.W, padx=10, pady=(10,0))
        imap_var = tk.StringVar(value=current_config.get("imap_server", "imap.gmail.com"))
        ttk.Entry(dialog, textvariable=imap_var).pack(fill=tk.X, padx=10)

        ttk.Label(dialog, text="SMTP 服务器:").pack(anchor=tk.W, padx=10, pady=(10,0))
        smtp_var = tk.StringVar(value=current_config.get("smtp_server", "smtp.gmail.com"))
        ttk.Entry(dialog, textvariable=smtp_var).pack(fill=tk.X, padx=10)

        def _save():
            if not email_classifier:
                messagebox.showerror("错误", "邮件分类器未初始化")
                return

            email = email_var.get().strip()
            pwd = pwd_var.get()

            if not email:
                messagebox.showerror("错误", "邮箱地址不能为空")
                return

            # 更新配置
            email_classifier.email_config["email_address"] = email
            email_classifier.email_config["imap_server"] = imap_var.get()
            email_classifier.email_config["smtp_server"] = smtp_var.get()

            # 密码存 keyring
            if pwd:
                EmailClassifier._set_password(email, pwd)

            email_classifier.save_config()
            messagebox.showinfo("成功", "邮箱配置已保存")
            dialog.destroy()

        ttk.Button(dialog, text="保存", command=_save).pack(pady=20)

    def _start_email(self):
        async_email = self.ctx.get_or_none("async_email")
        if async_email:
            async_email.run_async(async_email.start())
            self._append_output(self.email_output, "[邮件监控已启动]\n", "success")
        else:
            self._append_output(self.email_output, "[async_email 未就绪]\n", "error")

    def _stop_email(self):
        async_email = self.ctx.get_or_none("async_email")
        if async_email:
            async_email.run_async(async_email.stop())
            self._append_output(self.email_output, "[邮件监控已停止]\n", "info")

    def _show_drafts(self):
        async_email = self.ctx.get_or_none("async_email")
        if not async_email:
            return
        drafts = async_email.get_pending_drafts()
        self._append_output(self.email_output, f"待确认草稿 ({len(drafts)})：\n", "info")
        for i, d in enumerate(drafts):
            self._append_output(self.email_output, f"  {i+1}. To: {d.get('to')} | {d.get('subject')}\n", "info")

    def _add_kb_file(self):
        path = filedialog.askopenfilename(title="选择文件添加知识库")
        if not path:
            return

        def _do():
            kb = self.ctx.get_or_none("knowledge_base")
            if kb:
                try:
                    # 使用新的语义分块器
                    chunker = SemanticChunker()
                    chunks = chunker.chunk_file(path)
                    # 尝试用 ChromaDB
                    chroma = get_chromadb_client()
                    if chroma:
                        added = chroma.add_chunks(chunks)
                        self._append_output(self.kb_output, f"已添加 {added} 个块到 ChromaDB\n", "success")
                    else:
                        # 回退到旧知识库
                        kb.add_file(path)
                        self._append_output(self.kb_output, f"已添加文件（SQLite模式）\n", "success")
                except Exception as e:
                    self._append_output(self.kb_output, f"添加失败: {e}\n", "error")

        threading.Thread(target=_do, daemon=True).start()

    def _kb_search_gui(self):
        query = self.kb_query_input.get().strip()
        if not query:
            return

        def _do():
            chroma = get_chromadb_client()
            if chroma:
                results = chroma.hybrid_search(query, top_k=5)
                self._append_output(self.kb_output, f"检索「{query}」找到 {len(results)} 条：\n\n", "info")
                for r in results:
                    snippet = r["content"][:200].replace("\n", " ")
                    self._append_output(self.kb_output,
                                       f"[{r['score']:.3f}] {snippet}...\n"
                                       f"  来源: {r.get('metadata', {}).get('source', 'N/A')}\n\n", "info")
            else:
                self._append_output(self.kb_output, "[ChromaDB 未安装，搜索不可用]\n", "error")

        threading.Thread(target=_do, daemon=True).start()

    def _rebuild_index(self):
        def _do():
            try:
                chroma = get_chromadb_client()
                if chroma:
                    count = chroma.count()
                    self._append_output(self.kb_output, f"当前知识库共 {count} 条记录\n", "info")
                else:
                    self._append_output(self.kb_output, "[ChromaDB 不可用]\n", "error")
            except Exception as e:
                self._append_output(self.kb_output, f"错误: {e}\n", "error")
        threading.Thread(target=_do, daemon=True).start()

    def _scan_download_folder(self):
        """扫描下载文件夹并添加到知识库"""

        download_path = Path.home() / "Downloads"
        if not download_path.exists():
            self._append_output(self.kb_output, "下载文件夹不存在\n", "error")
            return

        def _do():
            kb = self.ctx.get_or_none("knowledge_base")
            if not kb:
                self._append_output(self.kb_output, "知识库未初始化\n", "error")
                return

            self._append_output(self.kb_output, f"开始扫描: {download_path}\n", "info")

            # 支持的文件类型
            supported_exts = {'.txt', '.md', '.pdf', '.docx', '.py', '.json', '.csv'}
            files = [f for f in download_path.iterdir() if f.is_file() and f.suffix.lower() in supported_exts]

            if not files:
                self._append_output(self.kb_output, "未找到支持的文件\n", "info")
                return

            added = 0
            for i, file_path in enumerate(files):
                try:
                    kb.add_file(str(file_path))
                    added += 1
                    if (i + 1) % 5 == 0:
                        self._append_output(self.kb_output, f"已处理 {i+1}/{len(files)}...\n", "info")
                except Exception as e:
                    self._append_output(self.kb_output, f"跳过 {file_path.name}: {e}\n", "error")

            self._append_output(self.kb_output, f"扫描完成，新增 {added} 个文件\n", "success")
            self._update_kb_status(f"最后扫描: {datetime.now().strftime('%H:%M:%S')} | 新增 {added} 个文件")

        threading.Thread(target=_do, daemon=True).start()

    def _toggle_kb_monitor(self):
        """切换知识库监控状态"""
        kb = self.ctx.get_or_none("knowledge_base")
        if not kb:
            self._append_output(self.kb_output, "知识库未初始化\n", "error")
            return

        # 检查当前监控状态（通过检查是否有监控线程）
        if hasattr(kb, '_monitoring') and kb._monitoring:
            # 停止监控
            kb._monitoring = False
            self.kb_monitor_btn.config(text="▶️ 启动监控")
            self._update_kb_status("监控状态: 已停止")
            self._append_output(self.kb_output, "监控已停止\n", "info")
        else:
            # 启动监控
            kb._monitoring = True
            self.kb_monitor_btn.config(text="⏹ 停止监控")
            self._update_kb_status("监控状态: 运行中")
            self._append_output(self.kb_output, "监控已启动\n", "success")

            # 启动后台线程
            def _monitor():
                while kb._monitoring:
                    try:
                        # 这里可以添加实际的监控逻辑
                        time.sleep(5)
                    except Exception as e:
                        self._append_output(self.kb_output, f"监控异常: {e}\n", "error")
                        break

            threading.Thread(target=_monitor, daemon=True).start()

    def _update_kb_status(self, text):
        """更新知识库状态显示"""
        self.kb_status_var.set(text)

    def _run_macro(self):
        script = self.macro_input.get("1.0", tk.END).strip()
        if not script:
            return

        self._append_output(self.macro_output, f"\n执行宏...\n", "info")

        def _do():
            vm = MacroVM()
            try:
                result = vm.run(script)
                self._append_output(self.macro_output, f"结果: {result}\n", "success")
            except Exception as e:
                self._append_output(self.macro_output, f"错误: {e}\n", "error")

        threading.Thread(target=_do, daemon=True).start()

    def _stop_macro(self):
        pass  # MacroVM 暂无 stop

    def _list_workflows(self):
        engine = self.ctx.get_or_none("workflow_engine")
        if engine:
            wfs = engine.list_workflows()
            self._append_output(self.workflow_output, f"已保存工作流 ({len(wfs)})：\n", "info")
            for w in wfs:
                self._append_output(self.workflow_output,
                                   f"  {w['id']}: {w['name']} ({w['node_count']}节点)\n", "info")

    def _run_workflow(self):
        self._append_output(self.workflow_output, "[请先选择工作流 ID]\n", "info")

    def _reload_modules(self):
        """热重载所有模块"""
        self._append_output(self.agent_output, "[热重载中...]\n", "info")
        for name in self.ctx.list_modules():
            self.ctx.reload(name)
        self._append_output(self.agent_output, "[热重载完成]\n", "success")

    # ── 状态更新 ─────────────────────────────────────────────────────────

    def _start_status_updater(self):
        def _update():
            while True:
                try:
                    self._refresh_status()
                except Exception as e:
                    logger.warning(f"[StatusUpdate] Error: {e}")
                time.sleep(5)

        t = threading.Thread(target=_update, daemon=True)
        t.start()

    def _refresh_status(self):
        modules = self.ctx.list_modules()
        status_lines = [
            f"[{datetime.now().strftime('%H:%M:%S')}] AI电脑管家 v2.0 模块状态",
            "=" * 50,
        ]

        for name, ready in modules.items():
            marker = "✅" if ready else "⏳"
            status_lines.append(f"  {marker} {name}")

        # 模型池统计
        router = self.ctx.get_or_none("model_router")
        if router:
            stats = router.list_providers()
            cache_stats = router.cache_stats()
            status_lines.append(f"\n📡 AI模型池：")
            for p, info in stats.items():
                e = "启用" if info["enabled"] else "禁用"
                status_lines.append(f"  [{e}] {p} → {info['model']}")
            status_lines.append(f"  缓存命中率: {cache_stats.get('hit_rate', 0):.1%}")

        # ChromaDB
        if CHROMADB_AVAILABLE:
            chroma = get_chromadb_client()
            if chroma:
                status_lines.append(f"\n📚 知识库向量数: {chroma.count()}")
        else:
            status_lines.append("\n📚 ChromaDB 未安装")

        text = "\n".join(status_lines)
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert("1.0", text)
        self.status_text.config(state=tk.DISABLED)

        self.status_bar.config(text=f"就绪 | {len(modules)} 模块已注册")

    # ── 工具 ─────────────────────────────────────────────────────────────

    def _append_output(self, widget: scrolledtext.ScrolledText, text: str, tag: str = ""):
        widget.config(state=tk.NORMAL)
        widget.insert(tk.END, text, tag)
        widget.see(tk.END)
        widget.config(state=tk.DISABLED)

    def _on_close(self):
        logger.info("[MainUpgrade] Shutting down...")
        self.ctx.shutdown()
        event_bus.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("AI电脑管家 v2.0 启动中...")
    logger.info("=" * 60)

    # 1. 构建上下文（注册所有模块）
    ctx = _build_app_context()

    # 2. 预热（提前实例化关键模块）
    try:
        ctx.start()
        logger.info("[Startup] 所有模块预热完成")
    except Exception as e:
        logger.error(f"[Startup] 预热失败: {e}", exc_info=True)
        messagebox.showwarning("启动警告", f"部分模块预热失败：{e}")

    # 3. 订阅事件
    _subscribe_events(ctx)

    # 4. 启动 UI
    gui = UpgradeGUI(ctx)
    gui.root.after(100, lambda: logger.info("[Startup] UI 就绪"))
    gui.run()


if __name__ == "__main__":
    main()
