"""
CodeWorkspacePanel — 编程工作区面板

集成到 main.py 的自动化标签页，提供：
  1. 项目监控开关 + 实时变更日志
  2. 代码质量仪表盘
  3. 批量代码生成工作流
  4. AI代码审查触发
  5. 代码片段管理
  6. Git集成增强
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import threading
import time
import os
import json
from pathlib import Path
from typing import Optional, Callable


import subprocess
try:
    import pyperclip
except ImportError:
    pyperclip = None

from services.code_project_monitor import get_code_project_monitor, MonitorAction
from services.project_templates import ProjectTemplates

class CodeWorkspacePanel:
    """编程工作区面板"""

    def __init__(self, parent_frame, app_context):
        self.parent = parent_frame
        self.app = app_context
        self.monitor = None
        self.ai_bridge = None
        self._snippet_file = Path.home() / ".aipc_code_snippets.json"
        self._snippets = self._load_snippets()
        self._build_ui()

    # ── 代码片段管理 ────────────────────────────────────────────────────

    def _load_snippets(self) -> dict:
        """加载代码片段"""
        if self._snippet_file.exists():
            try:
                with open(self._snippet_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_snippets(self):
        """保存代码片段"""
        try:
            with open(self._snippet_file, 'w', encoding='utf-8') as f:
                json.dump(self._snippets, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"❌ 保存片段失败: {e}")

    def _build_ui(self):
        """构建UI"""
        # 创建Notebook
        notebook = ttk.Notebook(self.parent)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # === Tab 1: 项目监控 ===
        monitor_tab = ttk.Frame(notebook)
        notebook.add(monitor_tab, text="👁️ 监控")
        self._build_monitor_tab(monitor_tab)

        # === Tab 2: 代码生成 ===
        gen_tab = ttk.Frame(notebook)
        notebook.add(gen_tab, text="🚀 生成")
        self._build_generate_tab(gen_tab)

        # === Tab 3: 代码片段 ===
        snippet_tab = ttk.Frame(notebook)
        notebook.add(snippet_tab, text="📎 片段")
        self._build_snippet_tab(snippet_tab)

        # === Tab 4: Git工具 ===
        git_tab = ttk.Frame(notebook)
        notebook.add(git_tab, text="🔀 Git")
        self._build_git_tab(git_tab)

        # === Tab 5: Diff可视化 ===
        diff_tab = ttk.Frame(notebook)
        notebook.add(diff_tab, text="🔍 Diff")
        self._build_diff_tab(diff_tab)

        # === Tab 6: 智能助手 ===
        assistant_tab = ttk.Frame(notebook)
        notebook.add(assistant_tab, text="🤖 助手")
        self._build_assistant_tab(assistant_tab)

    def _build_monitor_tab(self, parent):
        """构建监控标签页"""
        # 项目路径选择
        path_frame = ttk.LabelFrame(parent, text="📁 项目路径", padding=10)
        path_frame.pack(fill=tk.X, padx=10, pady=5)

        self.path_var = tk.StringVar(value=os.getcwd())
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var, width=50)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(path_frame, text="浏览", command=self._browse_project).pack(side=tk.LEFT, padx=2)
        ttk.Button(path_frame, text="扫描", command=self._scan_project).pack(side=tk.LEFT, padx=2)

        # 监控控制
        ctrl_frame = ttk.LabelFrame(parent, text="👁️ 文件监控", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        self.monitor_btn = tk.Button(
            ctrl_frame, text="▶️ 开始监控", command=self._toggle_monitor,
            bg="#2a5a2a", fg="#a0d0a0", width=12
        )
        self.monitor_btn.pack(side=tk.LEFT, padx=5)

        self.action_var = tk.StringVar(value="auto_review")
        ttk.Label(ctrl_frame, text="自动动作:").pack(side=tk.LEFT, padx=(15, 5))
        action_combo = ttk.Combobox(
            ctrl_frame, textvariable=self.action_var,
            values=["none", "auto_review", "auto_doc", "auto_format"],
            state="readonly", width=15
        )
        action_combo.pack(side=tk.LEFT, padx=5)

        self.monitor_status = ttk.Label(ctrl_frame, text="⏹ 未启动", foreground="gray")
        self.monitor_status.pack(side=tk.LEFT, padx=15)

        # AI审查按钮
        ttk.Button(ctrl_frame, text="🔍 AI审查", command=self._ai_review_current).pack(side=tk.LEFT, padx=10)

        # 变更日志
        log_frame = ttk.LabelFrame(parent, text="📝 实时变更", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.change_log = scrolledtext.ScrolledText(
            log_frame, height=8, state=tk.DISABLED,
            bg="#1e1e2e", fg="#cdd6f4", font=("Consolas", 9)
        )
        self.change_log.pack(fill=tk.BOTH, expand=True)

        # 代码质量仪表盘
        quality_frame = ttk.LabelFrame(parent, text="📊 代码质量", padding=10)
        quality_frame.pack(fill=tk.X, padx=10, pady=5)

        self.quality_labels = {}
        metrics = [
            ("文件数", "0"), ("总行数", "0"), ("平均分数", "-"),
            ("问题数", "0"), ("严重问题", "0"),
        ]
        for i, (name, val) in enumerate(metrics):
            ttk.Label(quality_frame, text=f"{name}:").grid(row=0, column=i*2, padx=5, pady=2, sticky=tk.E)
            lbl = ttk.Label(quality_frame, text=val, font=("Consolas", 10, "bold"))
            lbl.grid(row=0, column=i*2+1, padx=5, pady=2, sticky=tk.W)
            self.quality_labels[name] = lbl

    def _build_generate_tab(self, parent):
        """构建代码生成标签页"""
        # 需求输入
        req_frame = ttk.LabelFrame(parent, text="📝 需求描述", padding=10)
        req_frame.pack(fill=tk.X, padx=10, pady=5)

        self.gen_req = scrolledtext.ScrolledText(req_frame, height=4, bg="#313244", fg="#cdd6f4")
        self.gen_req.pack(fill=tk.X)
        self.gen_req.insert(tk.END, "创建一个Python Flask REST API，包含用户认证和CRUD操作")

        # 输出目录
        out_frame = ttk.Frame(req_frame)
        out_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(out_frame, text="输出:").pack(side=tk.LEFT)
        self.gen_out_var = tk.StringVar(value=os.path.join(os.getcwd(), "generated"))
        ttk.Entry(out_frame, textvariable=self.gen_out_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(out_frame, text="浏览", command=self._browse_output).pack(side=tk.LEFT, padx=2)

        # 模板选择
        template_frame = ttk.Frame(req_frame)
        template_frame.pack(fill=tk.X, pady=5)
        ttk.Label(template_frame, text="快速模板:").pack(side=tk.LEFT)
        self.template_var = tk.StringVar(value="")
        templates = ProjectTemplates.list_templates()
        template_names = [""] + [f"{t['name']} ({t['language']})" for t in templates]
        self.template_ids = [""] + [t['id'] for t in templates]
        template_combo = ttk.Combobox(template_frame, textvariable=self.template_var, values=template_names, state="readonly", width=30)
        template_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(template_frame, text="📦 使用模板", command=self._use_template).pack(side=tk.LEFT, padx=5)

        # 生成按钮
        btn_frame = ttk.Frame(req_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="🚀 AI生成项目", command=self._generate_project).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📄 AI生成单文件", command=self._generate_single).pack(side=tk.LEFT, padx=5)

        # 生成结果
        result_frame = ttk.LabelFrame(parent, text="📋 生成结果", padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.gen_result = scrolledtext.ScrolledText(
            result_frame, height=8, state=tk.DISABLED,
            bg="#1e1e2e", fg="#cdd6f4", font=("Consolas", 9)
        )
        self.gen_result.pack(fill=tk.BOTH, expand=True)

    def _build_snippet_tab(self, parent):
        """构建代码片段标签页"""
        # 片段列表
        list_frame = ttk.LabelFrame(parent, text="📎 代码片段列表", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 搜索框
        search_frame = ttk.Frame(list_frame)
        search_frame.pack(fill=tk.X, pady=2)
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.snippet_search = ttk.Entry(search_frame, width=30)
        self.snippet_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(search_frame, text="🔍", command=self._search_snippets).pack(side=tk.LEFT, padx=2)

        # 列表框
        self.snippet_listbox = tk.Listbox(list_frame, height=10, bg="#1e1e2e", fg="#cdd6f4")
        self.snippet_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self._refresh_snippet_list()

        # 按钮
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="➕ 添加", command=self._add_snippet).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="👁️ 查看", command=self._view_snippet).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📋 复制", command=self._copy_snippet).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ 删除", command=self._delete_snippet).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🚀 插入到AI", command=self._insert_snippet_to_ai).pack(side=tk.LEFT, padx=2)

    def _build_git_tab(self, parent):
        """构建Git工具标签页"""
        # Git状态
        status_frame = ttk.LabelFrame(parent, text="🔀 Git状态", padding=10)
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        self.git_status_text = scrolledtext.ScrolledText(
            status_frame, height=6, state=tk.DISABLED,
            bg="#1e1e2e", fg="#cdd6f4", font=("Consolas", 9)
        )
        self.git_status_text.pack(fill=tk.X)

        btn_frame = ttk.Frame(status_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="🔄 刷新状态", command=self._git_status).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="➕ 添加全部", command=self._git_add_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="💾 提交", command=self._git_commit).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📤 推送", command=self._git_push).pack(side=tk.LEFT, padx=2)

        # AI提交信息生成
        ai_frame = ttk.LabelFrame(parent, text="🤖 AI辅助提交", padding=10)
        ai_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(ai_frame, text="让AI根据变更生成提交信息:").pack(anchor=tk.W)
        ttk.Button(ai_frame, text="✨ 生成提交信息", command=self._ai_generate_commit).pack(pady=5)

        self.ai_commit_msg = scrolledtext.ScrolledText(ai_frame, height=2, bg="#313244", fg="#cdd6f4")
        self.ai_commit_msg.pack(fill=tk.X)

    def _build_diff_tab(self, parent):
        """构建Diff可视化标签页"""
        # 文件选择区
        select_frame = ttk.LabelFrame(parent, text="📂 文件对比", padding=10)
        select_frame.pack(fill=tk.X, padx=10, pady=5)

        # 原始文件
        row1 = ttk.Frame(select_frame)
        row1.pack(fill=tk.X, pady=3)
        ttk.Label(row1, text="原始文件:", width=10).pack(side=tk.LEFT)
        self.diff_orig_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.diff_orig_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row1, text="📂", width=3, command=lambda: self._diff_browse(self.diff_orig_var)).pack(side=tk.LEFT)

        # 修改后文件
        row2 = ttk.Frame(select_frame)
        row2.pack(fill=tk.X, pady=3)
        ttk.Label(row2, text="修改文件:", width=10).pack(side=tk.LEFT)
        self.diff_mod_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.diff_mod_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(row2, text="📂", width=3, command=lambda: self._diff_browse(self.diff_mod_var)).pack(side=tk.LEFT)

        # 按钮区
        btn_frame = ttk.Frame(select_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="🔍 对比", command=self._diff_compare).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔄 交换", command=self._diff_swap).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📋 复制差异", command=self._diff_copy).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="💾 保存为新文件", command=self._diff_save_as).pack(side=tk.LEFT, padx=2)

        # Diff 显示区
        result_frame = ttk.LabelFrame(parent, text="📊 差异结果", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.diff_text = scrolledtext.ScrolledText(
            result_frame, wrap=tk.NONE, state=tk.DISABLED,
            bg="#1e1e2e", fg="#cdd6f4", font=("Consolas", 9),
            relief=tk.FLAT
        )
        self.diff_text.pack(fill=tk.BOTH, expand=True)

        # 水平滚动条
        h_scroll = ttk.Scrollbar(result_frame, orient=tk.HORIZONTAL, command=self.diff_text.xview)
        h_scroll.pack(fill=tk.X)
        self.diff_text.config(xscrollcommand=h_scroll.set)

        # 配置语法高亮标签
        self.diff_text.tag_config("added", foreground="#a6e3a1", background="#1e2a1e")
        self.diff_text.tag_config("removed", foreground="#f38ba8", background="#2a1e1e")
        self.diff_text.tag_config("header", foreground="#89b4fa", font=("Consolas", 9, "bold"))
        self.diff_text.tag_config("info", foreground="#f9e2af")

    def _diff_browse(self, var):
        """浏览选择文件"""
        path = filedialog.askopenfilename(title="选择文件")
        if path:
            var.set(path)

    def _diff_compare(self):
        """执行文件对比"""
        orig = self.diff_orig_var.get()
        mod = self.diff_mod_var.get()

        if not orig or not mod:
            messagebox.showwarning("提示", "请选择两个文件")
            return

        if not os.path.exists(orig):
            messagebox.showerror("错误", f"原始文件不存在: {orig}")
            return
        if not os.path.exists(mod):
            messagebox.showerror("错误", f"修改文件不存在: {mod}")
            return

        try:
            with open(orig, 'r', encoding='utf-8', errors='replace') as f:
                orig_lines = f.readlines()
            with open(mod, 'r', encoding='utf-8', errors='replace') as f:
                mod_lines = f.readlines()
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败: {e}")
            return

        self.diff_text.config(state=tk.NORMAL)
        self.diff_text.delete(1.0, tk.END)

        # 简单的逐行对比
        import difflib
        diff = difflib.unified_diff(
            orig_lines, mod_lines,
            fromfile=f"原始: {os.path.basename(orig)}",
            tofile=f"修改: {os.path.basename(mod)}",
            lineterm=""
        )

        added = 0
        removed = 0
        for line in diff:
            if line.startswith('+++') or line.startswith('---'):
                self.diff_text.insert(tk.END, line + "\n", "header")
            elif line.startswith('@@'):
                self.diff_text.insert(tk.END, line + "\n", "info")
            elif line.startswith('+'):
                self.diff_text.insert(tk.END, line + "\n", "added")
                added += 1
            elif line.startswith('-'):
                self.diff_text.insert(tk.END, line + "\n", "removed")
                removed += 1
            else:
                self.diff_text.insert(tk.END, line + "\n")

        # 摘要
        self.diff_text.insert(tk.END, f"\n─── 摘要 ───\n", "header")
        self.diff_text.insert(tk.END, f"+{added} 行添加  -{removed} 行删除\n", "info")

        self.diff_text.config(state=tk.DISABLED)

    def _diff_swap(self):
        """交换两个文件路径"""
        orig = self.diff_orig_var.get()
        mod = self.diff_mod_var.get()
        self.diff_orig_var.set(mod)
        self.diff_mod_var.set(orig)

    def _diff_copy(self):
        """复制差异到剪贴板"""
        content = self.diff_text.get(1.0, tk.END)
        if content.strip():
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(content)
            messagebox.showinfo("提示", "差异已复制到剪贴板")

    def _diff_save_as(self):
        """保存差异为新文件"""
        content = self.diff_text.get(1.0, tk.END)
        if not content.strip():
            messagebox.showwarning("提示", "请先执行对比")
            return
        path = filedialog.asksaveasfilename(
            title="保存差异文件",
            defaultextension=".diff",
            filetypes=[("Diff文件", "*.diff"), ("所有文件", "*.*")]
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("提示", f"已保存到: {path}")

    # ── 事件处理 ────────────────────────────────────────────────────────

    def _browse_project(self):
        path = filedialog.askdirectory(title="选择项目目录")
        if path:
            self.path_var.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.gen_out_var.set(path)

    def _toggle_monitor(self):
        if self.monitor and self.monitor.is_watching:
            self._stop_monitor()
        else:
            self._start_monitor()

    def _start_monitor(self):
        try:
            self.monitor = get_code_project_monitor(
                project_path=self.path_var.get(),
                config_manager=self.app.config_manager if hasattr(self.app, 'config_manager') else None
            )

            self.monitor.auto_action = MonitorAction(self.action_var.get())

            self.monitor.on_change(self._on_file_change)
            self.monitor.on_review(self._on_review_complete)

            if self.monitor.start():
                self.monitor_btn.config(text="⏹ 停止监控", bg="#5a2a2a", fg="#d0a0a0")
                self.monitor_status.config(text="👁️ 监控中", foreground="#00ff00")
                self._log("✅ 监控已启动")
            else:
                self._log("❌ 启动失败")
        except Exception as e:
            self._log(f"❌ 错误: {e}")

    def _stop_monitor(self):
        if self.monitor:
            self.monitor.stop()
        self.monitor_btn.config(text="▶️ 开始监控", bg="#2a5a2a", fg="#a0d0a0")
        self.monitor_status.config(text="⏹ 已停止", foreground="gray")
        self._log("⏹ 监控已停止")

    def _on_file_change(self, change):
        ts = time.strftime("%H:%M:%S", time.localtime(change.timestamp))
        icon = {"created": "🟢", "modified": "🟡", "deleted": "🔴", "moved": "🔵"}.get(change.change_type.value, "⚪")
        msg = f"[{ts}] {icon} {change.change_type.value.upper():8} {os.path.basename(change.path)}"
        self._log(msg)

    def _on_review_complete(self, report):
        score_color = "#00ff00" if report.score >= 80 else "#ffaa00" if report.score >= 60 else "#ff0000"
        msg = f"📋 [{os.path.basename(report.file_path)}] 分数: {report.score} 问题: {len(report.issues)}"
        self._log(msg, tag=score_color)
        self._update_quality_display()

    def _scan_project(self):
        def do_scan():
            try:
                monitor = get_code_project_monitor(project_path=self.path_var.get())
                health = monitor.scan_project()
                self.app.root.after(0, lambda: self._update_health_display(health))
                self._log(f"✅ 扫描完成: {health.total_files} 文件, {health.total_lines} 行, 平均分 {health.avg_quality_score}")
            except Exception as e:
                self._log(f"❌ 扫描失败: {e}")

        threading.Thread(target=do_scan, daemon=True).start()
        self._log("⏳ 正在扫描项目...")

    def _update_health_display(self, health):
        self.quality_labels["文件数"].config(text=str(health.total_files))
        self.quality_labels["总行数"].config(text=str(health.total_lines))
        self.quality_labels["平均分数"].config(text=str(health.avg_quality_score))
        self.quality_labels["问题数"].config(text=str(health.issue_count))
        self.quality_labels["严重问题"].config(text=str(health.critical_issues))

    def _update_quality_display(self):
        if self.monitor:
            self._update_health_display(self.monitor.project_health)

    # ── AI代码生成 ──────────────────────────────────────────────────────

    def _get_ai_bridge(self):
        """获取AI桥接器（自动注入agent_service）"""
        from services.code_ai_bridge import get_code_ai_bridge
        agent = self.app.agent_service if hasattr(self.app, 'agent_service') else None
        self.ai_bridge = get_code_ai_bridge(agent)
        # Complementary: singleton may exist without agent from earlier call
        if agent is not None and self.ai_bridge._agent is None:
            self.ai_bridge.set_agent_service(agent)
        return self.ai_bridge

    def _generate_project(self):
        """生成完整项目"""
        req = self.gen_req.get("1.0", tk.END).strip()
        out = self.gen_out_var.get()

        if not req:
            messagebox.showwarning("提示", "请输入需求描述")
            return

        def do_generate():
            try:
                bridge = self._get_ai_bridge()
                self._gen_log("🚀 开始生成项目结构...")

                results = bridge.generate_project(req, out)

                success = len(results.get("success", []))
                failed = len(results.get("failed", []))

                msg = f"✅ 生成完成: 成功 {success}, 失败 {failed}"
                self._gen_log(msg)

                for task in results.get("success", []):
                    self._gen_log(f"  ✅ {os.path.basename(task.file_path)}")
                for task in results.get("failed", []):
                    self._gen_log(f"  ❌ {os.path.basename(task.file_path)}: {task.error}")

            except Exception as e:
                self._gen_log(f"❌ 生成失败: {e}")

        threading.Thread(target=do_generate, daemon=True).start()
        self._gen_log("⏳ 正在分析需求并生成项目...")

    def _generate_single(self):
        """生成单个文件"""
        req = self.gen_req.get("1.0", tk.END).strip()
        out = self.gen_out_var.get()

        if not req:
            messagebox.showwarning("提示", "请输入需求描述")
            return

        file_name = simpledialog.askstring("文件名", "请输入文件名:", initialvalue="main.py")
        if not file_name:
            return

        def do_generate():
            try:
                bridge = self._get_ai_bridge()
                file_path = os.path.join(out, file_name)

                self._gen_log(f"🚀 生成 {file_name}...")
                code = bridge.generate_file(req, file_path)

                os.makedirs(out, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code)

                self._gen_log(f"✅ 已保存: {file_path}")
                self._gen_log(f"📄 代码长度: {len(code)} 字符")

            except Exception as e:
                self._gen_log(f"❌ 生成失败: {e}")

        threading.Thread(target=do_generate, daemon=True).start()

    def _ai_review_current(self):
        """AI审查当前项目"""
        path = self.path_var.get()

        def do_review():
            try:
                monitor = get_code_project_monitor(project_path=path)

                # 扫描所有代码文件
                code_files = []
                for root, dirs, files in os.walk(path):
                    for f in files:
                        if monitor.is_code_file(os.path.join(root, f)):
                            code_files.append(os.path.join(root, f))

                self._log(f"🔍 发现 {len(code_files)} 个代码文件，开始AI审查...")

                bridge = self._get_ai_bridge()
                for i, file_path in enumerate(code_files[:5]):  # 最多审查5个
                    self._log(f"  ⏳ 审查 {os.path.basename(file_path)}...")
                    result = bridge.review_code(file_path)

                    if "error" in result:
                        self._log(f"  ❌ {os.path.basename(file_path)}: {result['error']}")
                    else:
                        # 截取前200字
                        summary = result['result'][:200].replace('\n', ' ')
                        self._log(f"  ✅ {os.path.basename(file_path)}: {summary}...")

                self._log("✅ AI审查完成")

            except Exception as e:
                self._log(f"❌ 审查失败: {e}")

        threading.Thread(target=do_review, daemon=True).start()
        self._log("⏳ 启动AI代码审查...")

    def _use_template(self):
        """使用预定义模板生成项目"""
        idx = self.template_ids.index(self.template_var.get().split(" (")[0]) if self.template_var.get() else -1
        if idx <= 0:
            messagebox.showwarning("提示", "请先选择一个模板")
            return

        template_id = self.template_ids[idx]
        out = self.gen_out_var.get()

        def do_generate():
            try:
                result = ProjectTemplates.generate(template_id, out)

                if result["success"]:
                    self._gen_log(f"✅ 模板项目生成完成: {result['project_dir']}")
                    self._gen_log(f"📄 文件数: {len(result['files'])}")
                    for f in result['files']:
                        self._gen_log(f"  ✅ {f}")

                    # 显示依赖信息
                    template = result['template']
                    if template.dependencies:
                        self._gen_log(f"📦 依赖: {', '.join(template.dependencies)}")
                    if template.post_commands:
                        self._gen_log(f"⚡ 后续命令: {'; '.join(template.post_commands)}")
                else:
                    self._gen_log(f"❌ 生成失败: {result['errors']}")

            except Exception as e:
                self._gen_log(f"❌ 错误: {e}")

        threading.Thread(target=do_generate, daemon=True).start()
        self._gen_log(f"⏳ 正在使用模板 {template_id} 生成项目...")

    # ── 代码片段 ────────────────────────────────────────────────────────

    def _refresh_snippet_list(self, filter_text=""):
        self.snippet_listbox.delete(0, tk.END)
        for name, data in sorted(self._snippets.items()):
            if filter_text.lower() in name.lower() or filter_text.lower() in data.get("desc", "").lower():
                lang = data.get("lang", "?")
                self.snippet_listbox.insert(tk.END, f"[{lang}] {name}")

    def _search_snippets(self):
        self._refresh_snippet_list(self.snippet_search.get())

    def _add_snippet(self):
        name = simpledialog.askstring("片段名称", "输入名称:")
        if not name:
            return

        win = tk.Toplevel(self.parent)
        win.title(f"添加片段: {name}")
        win.geometry("500x400")
        win.configure(bg="#1e1e2e")

        ttk.Label(win, text="语言:").pack(anchor=tk.W, padx=10)
        lang_var = tk.StringVar(value="python")
        ttk.Combobox(win, textvariable=lang_var, values=["python", "javascript", "typescript", "java", "go", "rust", "cpp", "c", "sql", "html", "css", "other"]).pack(anchor=tk.W, padx=10)

        ttk.Label(win, text="描述:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        desc_entry = ttk.Entry(win, width=50)
        desc_entry.pack(anchor=tk.W, padx=10)

        ttk.Label(win, text="代码:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        code_text = scrolledtext.ScrolledText(win, height=10, bg="#313244", fg="#cdd6f4")
        code_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        def save():
            self._snippets[name] = {
                "lang": lang_var.get(),
                "desc": desc_entry.get(),
                "code": code_text.get("1.0", tk.END).strip(),
                "created": time.time()
            }
            self._save_snippets()
            self._refresh_snippet_list()
            win.destroy()

        ttk.Button(win, text="💾 保存", command=save).pack(pady=10)

    def _view_snippet(self):
        sel = self.snippet_listbox.curselection()
        if not sel:
            return
        name = self._get_snippet_name_from_selection(sel[0])
        data = self._snippets.get(name)
        if not data:
            return

        win = tk.Toplevel(self.parent)
        win.title(f"查看: {name}")
        win.geometry("500x400")
        win.configure(bg="#1e1e2e")

        ttk.Label(win, text=f"语言: {data['lang']}").pack(anchor=tk.W, padx=10)
        ttk.Label(win, text=f"描述: {data.get('desc', '')}").pack(anchor=tk.W, padx=10)

        text = scrolledtext.ScrolledText(win, height=15, bg="#313244", fg="#cdd6f4", font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        text.insert(tk.END, data['code'])
        text.config(state=tk.DISABLED)

    def _copy_snippet(self):
        sel = self.snippet_listbox.curselection()
        if not sel:
            return
        name = self._get_snippet_name_from_selection(sel[0])
        data = self._snippets.get(name)
        if data:
            try:
                pyperclip.copy(data['code'])
                self._log(f"📋 已复制片段: {name}")
            except ImportError:
                messagebox.showwarning("提示", "请安装 pyperclip: pip install pyperclip")

    def _delete_snippet(self):
        sel = self.snippet_listbox.curselection()
        if not sel:
            return
        name = self._get_snippet_name_from_selection(sel[0])
        if messagebox.askyesno("确认", f"删除片段 '{name}'?"):
            del self._snippets[name]
            self._save_snippets()
            self._refresh_snippet_list()

    def _insert_snippet_to_ai(self):
        """将片段插入到AI输入框"""
        sel = self.snippet_listbox.curselection()
        if not sel:
            return
        name = self._get_snippet_name_from_selection(sel[0])
        data = self._snippets.get(name)
        if data and hasattr(self.app, 'input_text'):
            current = self.app.input_text.get()
            snippet = f"\n\n# 代码片段: {name}\n{data['code']}\n"
            self.app.input_text.delete(0, tk.END)
            self.app.input_text.insert(0, current + snippet)
            self._log(f"🚀 已插入片段到输入框: {name}")

    def _get_snippet_name_from_selection(self, index):
        text = self.snippet_listbox.get(index)
        # 格式: [lang] name
        return text.split("] ", 1)[1] if "] " in text else text

    # ── Git工具 ─────────────────────────────────────────────────────────

    def _git_status(self):
        def do_status():
            try:
                result = subprocess.run(
                    ["git", "-C", self.path_var.get(), "status", "-sb"],
                    capture_output=True, text=True, timeout=10
                )
                self._git_log(result.stdout if result.returncode == 0 else result.stderr)
            except Exception as e:
                self._git_log(f"❌ {e}")

        threading.Thread(target=do_status, daemon=True).start()

    def _git_add_all(self):
        def do_add():
            try:
                result = subprocess.run(
                    ["git", "-C", self.path_var.get(), "add", "."],
                    capture_output=True, text=True, timeout=10
                )
                self._git_log("✅ 已添加所有变更" if result.returncode == 0 else f"❌ {result.stderr}")
            except Exception as e:
                self._git_log(f"❌ {e}")

        threading.Thread(target=do_add, daemon=True).start()

    def _git_commit(self):
        msg = self.ai_commit_msg.get("1.0", tk.END).strip()
        if not msg:
            msg = simpledialog.askstring("提交信息", "输入提交信息:")
        if not msg:
            return

        def do_commit():
            try:
                result = subprocess.run(
                    ["git", "-C", self.path_var.get(), "commit", "-m", msg],
                    capture_output=True, text=True, timeout=10
                )
                self._git_log(result.stdout if result.returncode == 0 else f"❌ {result.stderr}")
            except Exception as e:
                self._git_log(f"❌ {e}")

        threading.Thread(target=do_commit, daemon=True).start()

    def _git_push(self):
        def do_push():
            try:
                result = subprocess.run(
                    ["git", "-C", self.path_var.get(), "push"],
                    capture_output=True, text=True, timeout=30
                )
                self._git_log(result.stdout if result.returncode == 0 else f"❌ {result.stderr}")
            except Exception as e:
                self._git_log(f"❌ {e}")

        threading.Thread(target=do_push, daemon=True).start()

    def _ai_generate_commit(self):
        """AI生成提交信息"""
        def do_generate():
            try:
                # 获取git diff
                diff_result = subprocess.run(
                    ["git", "-C", self.path_var.get(), "diff", "--cached", "--stat"],
                    capture_output=True, text=True, timeout=10
                )

                if not diff_result.stdout.strip():
                    self._git_log("⚠️ 没有暂存的变更，请先添加文件")
                    return

                # 获取详细diff（限制长度）
                diff_detail = subprocess.run(
                    ["git", "-C", self.path_var.get(), "diff", "--cached"],
                    capture_output=True, text=True, timeout=10
                )

                diff_text = diff_detail.stdout[:3000]  # 限制长度

                prompt = f"""根据以下Git变更生成简洁的提交信息（中文，一行）：

变更统计:
{diff_result.stdout}

变更详情:
{diff_text}

请只输出提交信息，不要其他内容。"""

                bridge = self._get_ai_bridge()
                if bridge._agent and bridge._agent.ensure_ready():
                    msg = bridge._agent.chat(prompt, timeout=120)
                    msg = msg.strip().split('\n')[0]  # 取第一行

                    def update_ui():
                        self.ai_commit_msg.delete("1.0", tk.END)
                        self.ai_commit_msg.insert(tk.END, msg)

                    self.app.root.after(0, update_ui)
                    self._git_log(f"✨ AI生成提交信息: {msg}")
                else:
                    self._git_log("❌ AI服务不可用")

            except Exception as e:
                self._git_log(f"❌ {e}")

        threading.Thread(target=do_generate, daemon=True).start()
        self._git_log("⏳ AI正在分析变更...")

    # ── 日志工具 ────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = None):
        def update():
            self.change_log.config(state=tk.NORMAL)
            self.change_log.insert(tk.END, msg + "\n")
            if tag:
                self.change_log.tag_add(tag, "end-2l", "end-1l")
                self.change_log.tag_config(tag, foreground=tag)
            self.change_log.see(tk.END)
            self.change_log.config(state=tk.DISABLED)

        if hasattr(self.app, 'root'):
            self.app.root.after(0, update)
        else:
            update()

    def _gen_log(self, msg: str):
        def update():
            self.gen_result.config(state=tk.NORMAL)
            self.gen_result.insert(tk.END, msg + "\n")
            self.gen_result.see(tk.END)
            self.gen_result.config(state=tk.DISABLED)

        if hasattr(self.app, 'root'):
            self.app.root.after(0, update)
        else:
            update()

    def _git_log(self, msg: str):
        def update():
            self.git_status_text.config(state=tk.NORMAL)
            self.git_status_text.delete("1.0", tk.END)
            self.git_status_text.insert(tk.END, msg)
            self.git_status_text.config(state=tk.DISABLED)

        if hasattr(self.app, 'root'):
            self.app.root.after(0, update)
        else:
            update()

    # ── 智能助手标签页 ──────────────────────────────────────────────────

    def _build_assistant_tab(self, parent):
        """构建智能助手标签页"""
        # 操作选择
        ctrl_frame = ttk.LabelFrame(parent, text="🤖 智能操作", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        self.assistant_action = tk.StringVar(value="explain")
        actions = [
            ("explain", "📖 解释代码"),
            ("test", "🧪 生成测试"),
            ("doc", "📝 生成文档"),
            ("optimize", "⚡ 性能优化"),
            ("convert", "🔄 转换语言"),
            ("security", "🔒 安全审查"),
        ]
        for val, text in actions:
            ttk.Radiobutton(ctrl_frame, text=text, variable=self.assistant_action, value=val).pack(side=tk.LEFT, padx=5)

        # 代码输入
        input_frame = ttk.LabelFrame(parent, text="📄 代码输入", padding=5)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.assistant_code = scrolledtext.ScrolledText(
            input_frame, height=8, bg="#313244", fg="#cdd6f4", font=("Consolas", 10)
        )
        self.assistant_code.pack(fill=tk.BOTH, expand=True)

        # 语言选择
        lang_frame = ttk.Frame(input_frame)
        lang_frame.pack(fill=tk.X, pady=2)
        ttk.Label(lang_frame, text="语言:").pack(side=tk.LEFT)
        self.assistant_lang = tk.StringVar(value="python")
        ttk.Combobox(lang_frame, textvariable=self.assistant_lang, values=["python", "javascript", "typescript", "java", "go", "rust", "cpp", "c", "csharp"], width=15, state="readonly").pack(side=tk.LEFT, padx=5)

        # 目标语言（仅转换时使用）
        ttk.Label(lang_frame, text="目标语言:").pack(side=tk.LEFT, padx=(15, 0))
        self.target_lang = tk.StringVar(value="go")
        self.target_lang_combo = ttk.Combobox(lang_frame, textvariable=self.target_lang, values=["python", "javascript", "typescript", "java", "go", "rust", "cpp", "c", "csharp"], width=15, state="readonly")
        self.target_lang_combo.pack(side=tk.LEFT, padx=5)

        # 执行按钮
        ttk.Button(input_frame, text="✨ 执行", command=self._run_assistant).pack(pady=5)

        # 结果输出
        result_frame = ttk.LabelFrame(parent, text="📋 结果", padding=5)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.assistant_result = scrolledtext.ScrolledText(
            result_frame, height=8, state=tk.DISABLED,
            bg="#1e1e2e", fg="#cdd6f4", font=("Consolas", 10)
        )
        self.assistant_result.pack(fill=tk.BOTH, expand=True)

        # 快捷操作
        quick_frame = ttk.LabelFrame(parent, text="⚡ 快捷操作", padding=5)
        quick_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(quick_frame, text="📂 加载文件", command=self._load_file_to_assistant).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="💾 保存结果", command=self._save_assistant_result).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="📋 复制结果", command=self._copy_assistant_result).pack(side=tk.LEFT, padx=2)

    def _run_assistant(self):
        """执行智能助手操作"""
        code = self.assistant_code.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("提示", "请输入代码")
            return

        action = self.assistant_action.get()
        lang = self.assistant_lang.get()

        def do_work():
            try:
                from services.smart_code_assistant import get_smart_code_assistant
                agent = self.app.agent_service if hasattr(self.app, 'agent_service') else None
                assistant = get_smart_code_assistant(agent)

                self._assistant_log(f"⏳ 正在{self._get_action_name(action)}...")

                if action == "explain":
                    result = assistant.explain_code(code, lang)
                elif action == "test":
                    result = assistant.generate_tests(code, language=lang)
                elif action == "doc":
                    result = assistant.generate_doc(code, lang)
                elif action == "optimize":
                    result = assistant.optimize_performance(code, lang)["analysis"]
                elif action == "convert":
                    result = assistant.convert_code(code, lang, self.target_lang.get())
                elif action == "security":
                    result = assistant.security_review(code, lang)["review"]
                else:
                    result = "未知操作"

                self._assistant_log(result)

            except Exception as e:
                self._assistant_log(f"❌ 错误: {e}")

        threading.Thread(target=do_work, daemon=True).start()

    def _get_action_name(self, action: str) -> str:
        names = {
            "explain": "解释代码",
            "test": "生成测试",
            "doc": "生成文档",
            "optimize": "性能优化",
            "convert": "转换语言",
            "security": "安全审查",
        }
        return names.get(action, action)

    def _load_file_to_assistant(self):
        """加载文件到助手"""
        path = filedialog.askopenfilename(
            title="选择代码文件",
            filetypes=[("代码文件", "*.py *.js *.ts *.java *.go *.rs *.cpp *.c *.cs"), ("所有文件", "*.*")]
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                self.assistant_code.delete("1.0", tk.END)
                self.assistant_code.insert(tk.END, content)

                # 自动检测语言
                ext = os.path.splitext(path)[1].lower()
                lang_map = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.java': 'java', '.go': 'go', '.rs': 'rust', '.cpp': 'cpp', '.c': 'c', '.cs': 'csharp'}
                if ext in lang_map:
                    self.assistant_lang.set(lang_map[ext])
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败: {e}")

    def _save_assistant_result(self):
        """保存结果到文件"""
        path = filedialog.asksaveasfilename(
            title="保存结果",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if path:
            try:
                result = self.assistant_result.get("1.0", tk.END)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(result)
                messagebox.showinfo("成功", f"已保存到: {path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}")

    def _copy_assistant_result(self):
        """复制结果到剪贴板"""
        try:
            result = self.assistant_result.get("1.0", tk.END)
            pyperclip.copy(result)
            self._assistant_log("📋 已复制到剪贴板")
        except ImportError:
            messagebox.showwarning("提示", "请安装 pyperclip")

    def _assistant_log(self, msg: str):
        def update():
            self.assistant_result.config(state=tk.NORMAL)
            self.assistant_result.delete("1.0", tk.END)
            self.assistant_result.insert(tk.END, msg)
            self.assistant_result.config(state=tk.DISABLED)

        if hasattr(self.app, 'root'):
            self.app.root.after(0, update)
        else:
            update()
