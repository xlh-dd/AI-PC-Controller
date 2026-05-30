import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, ttk
import os
import threading
import time
import logging
import re
from pathlib import Path

logger = logging.getLogger("WeChatPanel")


class WeChatPanel:
    """微信通讯面板 - 消息监听、定时发送、远程指令"""

    def __init__(self, parent: tk.Widget, controller):
        """构建微信通讯标签页

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
        """实际构建微信通讯UI"""
        self._loading_label.pack_forget()
        self._built = True

        ctrl = self.controller

        ctrl_frame = ttk.LabelFrame(self.parent, text="微信控制", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=10)

        self.listener_btn = ttk.Button(ctrl_frame, text="▶️ 开始监听", command=self.toggle_wechat_listener, bootstyle="success", width=15)
        self.listener_btn.pack(side=tk.LEFT, padx=3)
        ttk.Button(ctrl_frame, text="📱 发送消息", command=ctrl.schedule_wechat_message, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(ctrl_frame, text="🔧 诊断", command=ctrl.diagnose_wechat, bootstyle="secondary", width=15).pack(side=tk.LEFT, padx=3)

        task_frame = ttk.LabelFrame(self.parent, text="定时任务", padding=10)
        task_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(task_frame, text="📋 查看任务", command=ctrl.show_scheduled_tasks, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)
        ttk.Button(task_frame, text="➕ 添加任务", command=ctrl.schedule_wechat_message, bootstyle="primary", width=15).pack(side=tk.LEFT, padx=3)

        status_frame = ttk.LabelFrame(self.parent, text="状态信息", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.wechat_status_text = scrolledtext.ScrolledText(
            status_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg="#1e1e2e", fg="#cdd6f4",
            height=8
        )
        self.wechat_status_text.pack(fill=tk.BOTH, expand=True)

        self._update_wechat_status()

    def _update_wechat_status(self):
        """更新微信状态显示"""
        ctrl = self.controller
        status = "微信监听: " + ("运行中" if ctrl.wechat_listener_running else "已停止")
        status += f"\n监听间隔: {ctrl.config_manager.get('wechat_check_interval', 3)}秒"
        status += f"\nOCR模式: {'开启' if ctrl.config_manager.get('use_ocr', True) else '关闭'}"

        self.wechat_status_text.config(state=tk.NORMAL)
        self.wechat_status_text.delete(1.0, tk.END)
        self.wechat_status_text.insert(tk.END, status)
        self.wechat_status_text.config(state=tk.DISABLED)

    def toggle_wechat_listener(self):
        """切换微信监听状态"""
        ctrl = self.controller
        with ctrl.listener_lock:
            if not ctrl.wechat_listener_running:
                if not ctrl.wechat_controller.is_wechat_window_visible():
                    ctrl.say("系统", "🔍 微信窗口未找到,尝试自动打开微信...")
                    auto_opened = self._try_auto_open_wechat()
                    if not auto_opened:
                        ctrl.say("系统", "❌ 无法自动打开微信,请确保微信已安装。")
                        return
                    ctrl.say("系统", "⏳ 等待微信启动...")
                    time.sleep(5)
                    if not ctrl.wechat_controller.is_wechat_window_visible():
                        ctrl.say("系统", "❌ 微信启动失败,请手动打开微信。")
                        return

                ctrl.wechat_controller.update_last_message_id()
                ctrl.wechat_listener_running = True
                ctrl.listener_paused = False
                ctrl.root.after(0, lambda: self.listener_btn.config(text="⏸️ 停止监听"))
                ctrl.wechat_listener_thread = threading.Thread(target=self.wechat_listener_loop, daemon=True)
                ctrl.wechat_listener_thread.start()
                ctrl.say("系统", f"已开始监听来自「{ctrl.wechat_controller.contact}」的微信消息,间隔 {ctrl.wechat_controller.check_interval} 秒。")
            else:
                ctrl.wechat_listener_running = False
                ctrl.listener_paused = False
                ctrl.root.after(0, lambda: self.listener_btn.config(text="▶️ 开始监听"))
                ctrl.say("系统", "已停止监听微信指令。")

    def _try_auto_open_wechat(self):
        """尝试自动打开微信(通过宏或直接启动)"""
        ctrl = self.controller
        try:
            macros = get_recorder().list_macros()
            open_wechat_macro = None
            for macro in macros:
                name = macro.get("name", "").lower()
                if "微信" in name and ("打开" in name or "open" in name):
                    open_wechat_macro = macro
                    break

            if open_wechat_macro:
                ctrl.say("系统", f"🎬 正在播放宏: {open_wechat_macro['name']}")
                get_player().play(open_wechat_macro["file"])
                return True

            ctrl.say("系统", "📂 未找到打开微信的宏,尝试直接启动...")
            wechat_paths = [
                r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
                r"C:\Program Files\Tencent\WeChat\WeChat.exe",
                str(Path.home() / "AppData" / "Local" / "Tencent" / "WeChat" / "WeChat.exe")
            ]

            for path in wechat_paths:
                if Path(path).exists():
                    os.startfile(path)
                    ctrl.say("系统", f"✅ 已启动微信: {path}")
                    return True

            ctrl.say("系统", "⚠️ 未找到微信安装路径,请先录制「打开微信」的宏")
            return False

        except Exception as e:
            logger.error(f"自动打开微信失败: {e}")
            return False

    def wechat_listener_loop(self):
        """微信消息监听循环"""
        import random
        ctrl = self.controller
        processing = False
        consecutive_failures = 0
        max_consecutive_failures = 5

        base_interval = ctrl.wechat_controller.check_interval
        last_check = time.time()

        while True:
            current_time = time.time()
            with ctrl.listener_lock:
                if not ctrl.wechat_listener_running or not ctrl.running:
                    break
                if ctrl.listener_paused:
                    should_check = False
                else:
                    should_check = (current_time - last_check) >= base_interval

            if should_check:
                last_check = current_time
                try:
                    msg_data = ctrl.wechat_controller.check_wechat_message()
                    if msg_data:
                        logger.debug(f"检测到微信消息: {msg_data}")
                    if msg_data and not processing:
                        text = msg_data['text'].strip()
                        logger.debug(f"处理消息文本: '{text}'")
                        command = ctrl._extract_command(text)

                        if command:
                            logger.info(f"成功提取命令: '{command}'")
                            processing = True
                            consecutive_failures = 0

                            with ctrl.listener_lock:
                                ctrl.listener_paused = True
                                logger.info("检测到命令,暂停微信监听")

                            def exec_and_reply():
                                try:
                                    feedback = ctrl.execute_command_with_feedback(command)
                                    contact = ctrl.wechat_controller.contact
                                    ctrl.say("系统", f"📤 微信回复: {feedback}")
                                    ctrl.wechat_controller.send_wechat_message(contact, feedback)
                                except Exception as e:
                                    err = f"❌ 执行失败: {str(e)}"
                                    ctrl.say("系统", err)
                                    try:
                                        ctrl.wechat_controller.send_wechat_message(
                                            ctrl.wechat_controller.contact, err
                                        )
                                    except Exception:
                                        pass
                                finally:
                                    with ctrl.listener_lock:
                                        ctrl.listener_paused = False
                                    logger.info("微信监听已恢复")

                            threading.Thread(target=exec_and_reply, daemon=True).start()

                            processing = False
                        else:
                            logger.debug("未提取到命令(command为None或空)")
                except Exception as e:
                    logger.error(f"监听微信消息异常:{e}")
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        ctrl.say("系统", f"⚠️ 连续失败 {consecutive_failures} 次,自动停止监听")
                        with ctrl.listener_lock:
                            ctrl.wechat_listener_running = False
                        ctrl.root.after(0, lambda: self.listener_btn.config(text="▶️ 开始监听"))
                        break

            time.sleep(0.5)