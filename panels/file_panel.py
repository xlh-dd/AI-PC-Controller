import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog, simpledialog, ttk
import os
import subprocess
import threading
import logging
from datetime import datetime

logger = logging.getLogger("FilePanel")


class FilePanel:
    """文件管理面板 - 智能整理、查重、大文件扫描等功能"""

    def __init__(self, parent: tk.Widget, controller):
        """构建文件管理标签页

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
        """实际构建文件管理UI"""
        self._loading_label.pack_forget()
        self._built = True

        ctrl = self.controller

        btn_frame = ttk.LabelFrame(self.parent, text="文件操作", padding=10)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        row1 = ttk.Frame(btn_frame)
        row1.pack(fill=tk.X, pady=3)

        ttk.Button(row1, text="🗂️ 智能整理", command=self.auto_sort_files, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row1, text="🔍 查找重复", command=self.find_duplicate_files, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row1, text="💽 大文件", command=self.find_large_files, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row1, text="🧹 清理空文件", command=self.clean_empty_files, bootstyle="warning", width=15).pack(side=tk.LEFT, padx=3)

        row2 = ttk.Frame(btn_frame)
        row2.pack(fill=tk.X, pady=3)

        ttk.Button(row2, text="📂 选择目录", command=self.choose_folder, bootstyle="secondary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2, text="📋 列出文件", command=self.list_files, bootstyle="secondary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2, text="✏️ 批量重命名", command=lambda: self.rename_folder(""), bootstyle="secondary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(row2, text="↶ 撤销", command=self.undo, bootstyle="secondary", width=15).pack(side=tk.LEFT, padx=3)

        info_frame = ttk.LabelFrame(self.parent, text="目录信息", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.file_info_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg="#1e1e2e", fg="#cdd6f4",
            height=10
        )
        self.file_info_text.pack(fill=tk.BOTH, expand=True)

        self._update_file_info()

    def _update_file_info(self):
        """更新文件信息显示"""
        try:
            ctrl = self.controller
            folder = ctrl.current_folder
            if os.path.exists(folder):
                files = os.listdir(folder)
                file_count = len([f for f in files if os.path.isfile(os.path.join(folder, f))])
                dir_count = len([f for f in files if os.path.isdir(os.path.join(folder, f))])

                info = f"📁 当前目录: {folder}\n"
                info += f"📄 文件数: {file_count}\n"
                info += f"📂 文件夹数: {dir_count}\n"
                info += f"📊 总计: {len(files)} 项\n"

                total_size = 0
                for f in files:
                    try:
                        fp = os.path.join(folder, f)
                        if os.path.isfile(fp):
                            total_size += os.path.getsize(fp)
                    except:
                        pass

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

    def auto_sort_files(self):
        """智能整理文件 - 按类型分类"""
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
        """查找重复文件"""
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
        """AI智能分析重复文件"""
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
        """清理空文件"""
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
        """查找大文件"""
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
        """列出当前目录文件"""
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
        """批量重命名文件夹"""
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
        """选择工作目录"""
        ctrl = self.controller
        folder = filedialog.askdirectory(title="选择工作目录")
        if folder:
            ctrl.current_folder = folder
            ctrl.config_manager.set("current_folder", folder)
            ctrl.folder_label.config(text=f"📁 {folder}")
            ctrl.say("系统", f"✅ 已切换到目录:{folder}")
            self._update_file_info()

    def undo(self):
        """撤销上次重命名操作"""
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