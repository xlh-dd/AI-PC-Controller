import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog, ttk
import os
import subprocess
import threading
import logging
from datetime import datetime

logger = logging.getLogger("FilePanel")

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
}


class FilePanel:
    """文件管理面板 - 工具栏风格按钮 + 磁盘使用可视化"""

    def __init__(self, parent: tk.Widget, controller):
        self.parent = parent
        self.controller = controller
        self._built = False

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
        ctrl = self.controller

        # ── 工具栏 ──
        self._build_toolbar()

        # ── 目录信息(含磁盘可视化) ──
        self._build_info_section()

        self._update_file_info()

    # ─── 工具栏(图标+文字竖排) ──────────────────────────

    def _build_toolbar(self):
        base = CATPPUCCIN
        toolbar = tk.Frame(self.parent, bg=base["mantle"],
                           highlightbackground=base["surface0"],
                           highlightthickness=1)
        toolbar.pack(fill=tk.X, padx=10, pady=(10, 4))

        # 第一行: 主要操作
        row1 = tk.Frame(toolbar, bg=base["mantle"])
        row1.pack(fill=tk.X, padx=6, pady=(6, 2))

        primary_actions = [
            ("🗂️", "智能整理", base["blue_dim"], base["blue"], self.auto_sort_files),
            ("🔍", "查找重复", base["blue_dim"], base["teal"], self.find_duplicate_files),
            ("💽", "大文件", base["blue_dim"], base["sky"], self.find_large_files),
            ("🧹", "清理空文件", base["green_dim"], base["green"], self.clean_empty_files),
        ]

        for icon, text, card_bg, icon_fg, cmd in primary_actions:
            self._make_tool_button(row1, icon, text, card_bg, icon_fg, cmd)

        # 第二行: 辅助操作
        row2 = tk.Frame(toolbar, bg=base["mantle"])
        row2.pack(fill=tk.X, padx=6, pady=(2, 6))

        secondary_actions = [
            ("📂", "选择目录", base["surface0"], base["subtext0"], self.choose_folder),
            ("📋", "列出文件", base["surface0"], base["subtext0"], self.list_files),
            ("✏️", "批量重命名", base["surface0"], base["subtext0"], lambda: self.rename_folder("")),
            ("↶", "撤销", base["surface0"], base["subtext0"], self.undo),
        ]

        for icon, text, card_bg, icon_fg, cmd in secondary_actions:
            self._make_tool_button(row2, icon, text, card_bg, icon_fg, cmd)

    def _make_tool_button(self, parent, icon, text, card_bg, icon_fg, command):
        """创建工具栏按钮(图标+文字竖排)"""
        base = CATPPUCCIN

        card = tk.Frame(parent, bg=card_bg, cursor="hand2",
                        highlightbackground=base["surface1"],
                        highlightthickness=1, padx=8, pady=5)

        icon_lbl = tk.Label(card, text=icon, font=("Segoe UI Emoji", 16),
                            bg=card_bg, fg=icon_fg)
        icon_lbl.pack(pady=(0, 1))

        text_lbl = tk.Label(card, text=text, font=("微软雅黑", 8),
                            bg=card_bg, fg=base["subtext0"])
        text_lbl.pack()

        def make_hover(c, i, t, bg):
            hbg = base["surface1"]
            def on_enter(e):
                c.config(bg=hbg); i.config(bg=hbg); t.config(bg=hbg)
            def on_leave(e):
                c.config(bg=bg); i.config(bg=bg); t.config(bg=bg)
            return on_enter, on_leave

        on_enter, on_leave = make_hover(card, icon_lbl, text_lbl, card_bg)
        for w in (card, icon_lbl, text_lbl):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e, c=command: c())

        card.pack(side=tk.LEFT, padx=3, pady=2)

    # ─── 目录信息(含磁盘可视化) ─────────────────────────

    def _build_info_section(self):
        base = CATPPUCCIN

        info_outer = tk.Frame(self.parent, bg=base["base"])
        info_outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        # 磁盘使用进度条区
        self._disk_bar_frame = tk.Frame(info_outer, bg=base["base"])
        self._disk_bar_frame.pack(fill=tk.X, pady=(0, 6))

        # 详细信息文本
        info_frame = tk.Frame(info_outer, bg=base["crust"],
                              highlightbackground=base["surface0"],
                              highlightthickness=1)
        info_frame.pack(fill=tk.BOTH, expand=True)

        self.file_info_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg=base["crust"], fg=base["subtext0"],
            height=8, relief=tk.FLAT, padx=8, pady=6,
            insertbackground=base["text"],
        )
        self.file_info_text.pack(fill=tk.BOTH, expand=True)

    def _update_file_info(self):
        """更新文件信息 + 磁盘可视化"""
        base = CATPPUCCIN
        try:
            ctrl = self.controller
            folder = ctrl.current_folder
            if os.path.exists(folder):
                files = os.listdir(folder)
                file_count = len([f for f in files if os.path.isfile(os.path.join(folder, f))])
                dir_count = len([f for f in files if os.path.isdir(os.path.join(folder, f))])

                total_size = 0
                for f in files:
                    try:
                        fp = os.path.join(folder, f)
                        if os.path.isfile(fp):
                            total_size += os.path.getsize(fp)
                    except Exception:
                        pass

                if total_size > 1024**3:
                    size_str = f"{total_size / 1024**3:.2f} GB"
                elif total_size > 1024**2:
                    size_str = f"{total_size / 1024**2:.2f} MB"
                else:
                    size_str = f"{total_size / 1024:.2f} KB"

                info = f"📁 当前目录: {folder}\n"
                info += f"📄 文件数: {file_count}  |  📂 文件夹数: {dir_count}  |  📊 总计: {len(files)} 项\n"
                info += f"💾 总大小: {size_str}"

                self.file_info_text.config(state=tk.NORMAL)
                self.file_info_text.delete(1.0, tk.END)
                self.file_info_text.insert(tk.END, info)
                self.file_info_text.config(state=tk.DISABLED)

                # 更新磁盘进度条
                self._update_disk_bars(folder)
        except Exception as e:
            pass

    def _update_disk_bars(self, folder):
        """更新磁盘使用进度条"""
        base = CATPPUCCIN

        # 清空旧进度条
        for w in self._disk_bar_frame.winfo_children():
            w.destroy()

        try:
            import psutil
            # 获取文件夹所在磁盘
            drive = os.path.splitdrive(folder)[0] or "C:"
            disk = psutil.disk_usage(drive)

            # 磁盘使用条
            row = tk.Frame(self._disk_bar_frame, bg=base["base"])
            row.pack(fill=tk.X, pady=2)

            tk.Label(row, text=f"💿 {drive}", font=("微软雅黑", 9, "bold"),
                     bg=base["base"], fg=base["text"]).pack(side=tk.LEFT)

            pct = disk.percent
            pct_color = base["blue"] if pct < 70 else (base["yellow"] if pct < 90 else base["red"])
            tk.Label(row, text=f"{pct}%", font=("微软雅黑", 9, "bold"),
                     bg=base["base"], fg=pct_color).pack(side=tk.RIGHT)

            bar_canvas = tk.Canvas(self._disk_bar_frame, height=12,
                                   bg=base["surface0"], highlightthickness=0, bd=0)
            bar_canvas.pack(fill=tk.X, pady=(2, 0))

            bar_id = bar_canvas.create_rectangle(0, 0, 0, 12, fill=pct_color, outline="")

            def on_resize(event, bid=bar_id, p=pct/100.0, c=bar_canvas, clr=pct_color):
                bar_w = int(p * event.width)
                c.coords(bid, 0, 0, bar_w, 12)

            bar_canvas.bind("<Configure>", on_resize)

            used_gb = disk.used // (1024**3)
            total_gb = disk.total // (1024**3)
            tk.Label(self._disk_bar_frame,
                     text=f"  {used_gb} GB / {total_gb} GB 已使用",
                     font=("微软雅黑", 8), bg=base["base"], fg=base["overlay0"]).pack(anchor="w")

        except Exception:
            # psutil 不可用时静默跳过
            pass

    # ─── 文件操作方法(保持原有逻辑不变) ──────────────────

    def auto_sort_files(self):
        ctrl = self.controller
        target_base = filedialog.askdirectory(title="选择分类后的根目录")
        if not target_base:
            return

        def sort_files_thread():
            try:
                ctrl.say("AI管家", f"正在扫描文件...")
                move_plan = ctrl.file_manager.auto_sort_files(
                    ctrl.current_folder, target_base,
                    ctrl.ai_helper if ctrl.use_ai_features else None
                )

                if not move_plan:
                    ctrl.say("AI管家", "没有需要整理的文件。")
                    return

                preview = "\n".join([
                    f"• {os.path.relpath(s, ctrl.current_folder)} -> {os.path.relpath(d, target_base)}"
                    for s, d in move_plan[:20]
                ])
                if len(move_plan) > 20:
                    preview += f"\n... 还有 {len(move_plan)-20} 个文件"
                ctrl.say("AI管家", f"📊 整理方案预览(共{len(move_plan)}个文件):\n{preview}")

                def confirm_and_execute():
                    if messagebox.askyesno("确认", "确定执行整理?"):
                        moved = 0
                        for src, dst in move_plan:
                            if ctrl.file_manager.safe_move(src, dst):
                                moved += 1
                        ctrl.say("系统", f"✅ 整理完成,成功移动 {moved}/{len(move_plan)} 个文件。")

                ctrl.root.after(0, confirm_and_execute)
            except Exception as e:
                logger.exception("按类型整理失败")
                ctrl.say("系统", f"❌ 整理失败:{e}")

        threading.Thread(target=sort_files_thread, daemon=True).start()

    def find_duplicate_files(self):
        ctrl = self.controller

        def find_duplicates_thread():
            try:
                ctrl.say("AI管家", "正在扫描重复文件...")
                duplicates = ctrl.file_manager.find_duplicate_files(ctrl.current_folder)

                if not duplicates:
                    ctrl.say("AI管家", "没有发现重复文件。")
                    return

                lines = [f"发现 {len(duplicates)} 组重复文件,每组保留第一个,其余将删除:"]
                for group in duplicates[:10]:
                    lines.append(f"• {os.path.basename(group[0])} 等 {len(group)} 个文件")
                if len(duplicates) > 10:
                    lines.append(f"... 还有 {len(duplicates)-10} 组")
                ctrl.say("AI管家", "\n".join(lines))

                def confirm_and_cleanup():
                    if ctrl.use_ai_features and messagebox.askyesno(
                        "智能清理", "是否让AI分析哪些文件可以安全删除?(否则将删除每组除第一个外的所有副本)"
                    ):
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
                        ctrl.say("系统", f"✅ 已删除 {deleted} 个重复文件。")

                ctrl.root.after(0, confirm_and_cleanup)
            except Exception as e:
                logger.exception("查找重复文件失败")
                ctrl.say("系统", f"❌ 查找重复文件失败:{e}")

        threading.Thread(target=find_duplicates_thread, daemon=True).start()

    def smart_duplicate_cleanup(self, duplicates):
        ctrl = self.controller
        ctrl.say("AI管家", "正在分析重复文件,请稍候...")
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
            del_list = ctrl.ai_helper.analyze_duplicate_files(files_info)
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
                ctrl.say("系统", f"✅ 已删除 {deleted} 个文件。")
        else:
            ctrl.say("系统", "AI未给出有效建议,请手动处理。")

    def clean_empty_files(self):
        ctrl = self.controller

        def clean_empty_thread():
            try:
                ctrl.say("AI管家", "正在扫描空文件...")
                empty_files = ctrl.file_manager.clean_empty_files(ctrl.current_folder)
                if not empty_files:
                    ctrl.say("AI管家", "没有空文件。")
                    return

                lines = [f"发现 {len(empty_files)} 个空文件:"]
                for e in empty_files[:20]:
                    lines.append(f"• {os.path.basename(e)}")
                if len(empty_files) > 20:
                    lines.append(f"... 还有 {len(empty_files)-20} 个")
                ctrl.say("AI管家", "\n".join(lines))

                def confirm_and_delete():
                    if messagebox.askyesno("确认", f"确定删除这 {len(empty_files)} 个空文件?"):
                        deleted = 0
                        for path in empty_files:
                            try:
                                os.remove(path)
                                deleted += 1
                            except Exception as e:
                                logger.error(f"删除失败 {path}: {e}")
                        ctrl.say("系统", f"✅ 已删除 {deleted} 个空文件。")

                ctrl.root.after(0, confirm_and_delete)
            except Exception as e:
                logger.exception("清理空文件失败")
                ctrl.say("系统", f"❌ 清理空文件失败:{e}")

        threading.Thread(target=clean_empty_thread, daemon=True).start()

    def find_large_files(self, min_size_gb=1):
        ctrl = self.controller

        def find_large_files_thread():
            try:
                ctrl.say("AI管家", f"正在扫描大于 {min_size_gb}GB 的文件...")
                large_files = ctrl.file_manager.find_large_files(ctrl.current_folder, min_size_gb)
                if not large_files:
                    ctrl.say("AI管家", f"没有大于 {min_size_gb}GB 的文件。")
                    return
                lines = [f"发现 {len(large_files)} 个大文件(前20):"]
                for path, size in large_files[:20]:
                    lines.append(f"• {os.path.basename(path)} ({size/1024**3:.2f} GB)")
                ctrl.say("AI管家", "\n".join(lines))
            except Exception as e:
                logger.exception("查找大文件失败")
                ctrl.say("系统", f"❌ 查找大文件失败:{e}")

        threading.Thread(target=find_large_files_thread, daemon=True).start()

    def list_files(self):
        ctrl = self.controller

        def list_files_thread():
            try:
                folders, files = ctrl.file_manager.list_files(ctrl.current_folder)
                if not folders and not files:
                    ctrl.say("AI管家", "当前目录为空。")
                    return
                msg = "📁 文件夹:\n" + "\n".join([f"• {f}" for f in folders[:10]])
                if len(folders) > 10:
                    msg += f"\n... 还有 {len(folders)-10} 个文件夹"
                msg += "\n\n📄 文件:\n" + "\n".join([f"• {f}" for f in files[:20]])
                if len(files) > 20:
                    msg += f"\n... 还有 {len(files)-20} 个文件"
                ctrl.say("AI管家", msg)
            except Exception as e:
                logger.exception("列出文件失败")
                ctrl.say("系统", f"❌ 列出文件失败:{e}")

        threading.Thread(target=list_files_thread, daemon=True).start()

    def rename_folder(self, msg):
        ctrl = self.controller
        try:
            ctrl.say("AI管家", "正在分析改名需求...")
            folders = [
                d for d in os.listdir(ctrl.current_folder)
                if os.path.isdir(os.path.join(ctrl.current_folder, d))
            ]
            if not folders:
                ctrl.say("AI管家", "当前目录没有子文件夹。")
                return

            pairs = ctrl.ai_helper.generate_rename_plan(folders, msg)
            if not pairs:
                ctrl.say("AI管家", "无法理解您的指令,请换个说法。")
                return

            valid_pairs = []
            for p in pairs:
                old = p.get("original") or p.get("old")
                new = p.get("new")
                if old in folders and new and new not in folders:
                    valid_pairs.append((
                        os.path.join(ctrl.current_folder, old),
                        os.path.join(ctrl.current_folder, new)
                    ))

            if not valid_pairs:
                ctrl.say("AI管家", "没有有效的改名项。")
                return

            preview = "\n".join([
                f"{os.path.basename(o)} → {os.path.basename(n)}"
                for o, n in valid_pairs
            ])
            ctrl.say("AI管家", f"📊 改名方案:\n{preview}")

            if messagebox.askyesno("确认", "执行改名?"):
                renamed = 0
                for o, n in valid_pairs:
                    try:
                        os.rename(o, n)
                        ctrl.rename_history.append((o, n))
                        renamed += 1
                    except Exception as e:
                        logger.error(f"改名失败 {o} -> {n}: {e}")
                ctrl.say("系统", f"✅ 改名完成,成功修改 {renamed}/{len(valid_pairs)} 个文件夹。")
        except Exception as e:
            logger.exception("改名失败")
            ctrl.say("系统", f"❌ 改名失败:{e}")

    def choose_folder(self):
        ctrl = self.controller
        folder = filedialog.askdirectory(title="选择工作目录")
        if folder:
            ctrl.current_folder = folder
            ctrl.config_manager.set("current_folder", folder)
            ctrl.folder_label.config(text=f"📁 {folder}")
            ctrl.say("系统", f"✅ 已切换到目录:{folder}")
            self._update_file_info()

    def undo(self):
        ctrl = self.controller
        if not ctrl.rename_history:
            ctrl.say("系统", "❌ 没有可撤销的操作")
            return
        src, dst = ctrl.rename_history.pop()
        try:
            if os.path.exists(dst):
                os.rename(dst, src)
                ctrl.say("系统", f"✅ 已撤销:{os.path.basename(dst)} → {os.path.basename(src)}")
            else:
                ctrl.say("系统", "❌ 撤销失败:目标文件不存在")
        except Exception as e:
            logger.error(f"撤销失败 {dst} -> {src}: {e}")
            ctrl.say("系统", f"❌ 撤销失败:{e}")
