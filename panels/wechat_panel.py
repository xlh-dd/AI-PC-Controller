import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog, ttk
import os
import threading
import time
import logging
import re
from pathlib import Path

logger = logging.getLogger("WeChatPanel")

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


class WeChatPanel:
    """微信通讯面板 - 脉冲动画指示器 + 现代卡片布局"""

    def __init__(self, parent: tk.Widget, controller):
        self.parent = parent
        self.controller = controller
        self._built = False
        self._pulse_job = None  # 脉冲动画 job

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

        # ── 监听状态指示器 ──
        self._build_listener_section()

        # ── 操作区 ──
        self._build_actions()

        # ── 定时任务 ──
        self._build_tasks_section()

        # ── 状态信息 ──
        self._build_status_section()

        self._update_wechat_status()

    # ─── 监听状态(脉冲动画) ────────────────────────────

    def _build_listener_section(self):
        base = CATPPUCCIN

        section = tk.Frame(self.parent, bg=base["base"])
        section.pack(fill=tk.X, padx=12, pady=(10, 4))

        # 标题行 + 状态指示
        header = tk.Frame(section, bg=base["base"])
        header.pack(fill=tk.X, pady=(0, 6))

        tk.Label(header, text="📱 微信监听", font=("微软雅黑", 11, "bold"),
                 bg=base["base"], fg=base["text"]).pack(side=tk.LEFT)

        # 脉冲状态指示器
        self._pulse_frame = tk.Frame(header, bg=base["base"])
        self._pulse_frame.pack(side=tk.RIGHT, padx=4)

        self._pulse_canvas = tk.Canvas(self._pulse_frame, width=14, height=14,
                                        bg=base["base"], highlightthickness=0, bd=0)
        self._pulse_canvas.pack(side=tk.LEFT, padx=(0, 4))
        self._pulse_dot = self._pulse_canvas.create_oval(2, 2, 12, 12,
                                                           fill=base["overlay0"], outline="")

        self._pulse_label = tk.Label(self._pulse_frame, text="已停止",
                                      font=("微软雅黑", 8),
                                      bg=base["base"], fg=base["overlay0"])
        self._pulse_label.pack(side=tk.LEFT)

        # 监听按钮(大号卡片式)
        btn_frame = tk.Frame(section, bg=base["base"])
        btn_frame.pack(fill=tk.X)

        self.listener_btn = tk.Button(
            btn_frame, text="▶️  开始监听", font=("微软雅黑", 11, "bold"),
            bg=base["green_dim"], fg=base["green"],
            activebackground=base["surface1"], activeforeground=base["green"],
            relief=tk.FLAT, cursor="hand2", padx=20, pady=8,
            command=self.toggle_wechat_listener,
        )
        self.listener_btn.pack(side=tk.LEFT, padx=4)

    def _start_pulse_animation(self):
        """启动脉冲动画"""
        base = CATPPUCCIN
        state = {"on": True}

        def pulse():
            if not self._built:
                return
            try:
                if state["on"]:
                    self._pulse_canvas.itemconfig(self._pulse_dot, fill=base["green"])
                else:
                    self._pulse_canvas.itemconfig(self._pulse_dot, fill=base["green_dim"])
                state["on"] = not state["on"]
            except Exception:
                return
            self._pulse_job = self.controller.root.after(600, pulse)

        self._pulse_job = self.controller.root.after(600, pulse)

    def _stop_pulse_animation(self):
        """停止脉冲动画"""
        if self._pulse_job:
            try:
                self.controller.root.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        try:
            self._pulse_canvas.itemconfig(self._pulse_dot, fill=CATPPUCCIN["overlay0"])
        except Exception:
            pass

    # ─── 操作区 ────────────────────────────────────────

    def _build_actions(self):
        base = CATPPUCCIN
        section = tk.Frame(self.parent, bg=base["base"])
        section.pack(fill=tk.X, padx=12, pady=6)

        actions = [
            ("📱", "发送消息", base["blue_dim"], base["blue"],
             self.controller.schedule_wechat_message),
            ("🔧", "诊断", base["surface0"], base["subtext0"],
             self.controller.diagnose_wechat),
        ]

        for icon, text, card_bg, icon_fg, cmd in actions:
            card = tk.Frame(section, bg=card_bg, cursor="hand2",
                            highlightbackground=base["surface1"],
                            highlightthickness=1, padx=12, pady=5)

            icon_lbl = tk.Label(card, text=icon, font=("Segoe UI Emoji", 14),
                                bg=card_bg, fg=icon_fg)
            icon_lbl.pack(side=tk.LEFT, padx=(0, 6))

            text_lbl = tk.Label(card, text=text, font=("微软雅黑", 9),
                                bg=card_bg, fg=base["subtext0"])
            text_lbl.pack(side=tk.LEFT)

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
                w.bind("<Button-1>", lambda e, c=cmd: c())

            card.pack(side=tk.LEFT, padx=4)

    # ─── 定时任务 ──────────────────────────────────────

    def _build_tasks_section(self):
        base = CATPPUCCIN
        section = tk.Frame(self.parent, bg=base["base"])
        section.pack(fill=tk.X, padx=12, pady=6)

        tk.Label(section, text="⏰ 定时任务", font=("微软雅黑", 11, "bold"),
                 bg=base["base"], fg=base["text"]).pack(fill=tk.X, pady=(0, 4))

        task_btns = tk.Frame(section, bg=base["base"])
        task_btns.pack(fill=tk.X)

        for icon, text, card_bg, icon_fg, cmd in [
            ("📋", "查看任务", base["surface0"], base["subtext0"],
             self.controller.show_scheduled_tasks),
            ("➕", "添加任务", base["blue_dim"], base["blue"],
             self.controller.schedule_wechat_message),
        ]:
            btn = tk.Button(
                task_btns, text=f"{icon} {text}", font=("微软雅黑", 9),
                bg=card_bg, fg=icon_fg,
                activebackground=base["surface1"], activeforeground=base["text"],
                relief=tk.FLAT, cursor="hand2", padx=12, pady=4,
                command=cmd,
            )
            btn.pack(side=tk.LEFT, padx=4)

    # ─── 状态信息 ──────────────────────────────────────

    def _build_status_section(self):
        base = CATPPUCCIN
        section = tk.Frame(self.parent, bg=base["base"])
        section.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))

        info_frame = tk.Frame(section, bg=base["crust"],
                              highlightbackground=base["surface0"],
                              highlightthickness=1)
        info_frame.pack(fill=tk.BOTH, expand=True)

        self.wechat_status_text = scrolledtext.ScrolledText(
            info_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("微软雅黑", 9), bg=base["crust"], fg=base["subtext0"],
            height=8, relief=tk.FLAT, padx=8, pady=6,
            insertbackground=base["text"],
        )
        self.wechat_status_text.pack(fill=tk.BOTH, expand=True)

    def _update_wechat_status(self):
        ctrl = self.controller
        status = "微信监听: " + ("🟢 运行中" if ctrl.wechat_listener_running else "⚪ 已停止")
        status += f"\n监听间隔: {ctrl.config_manager.get('wechat_check_interval', 3)}秒"
        status += f"\nOCR模式: {'开启' if ctrl.config_manager.get('use_ocr', True) else '关闭'}"
        status += f"\n监听联系人: {ctrl.config_manager.get('wechat_contact', '文件传输助手')}"

        self.wechat_status_text.config(state=tk.NORMAL)
        self.wechat_status_text.delete(1.0, tk.END)
        self.wechat_status_text.insert(tk.END, status)
        self.wechat_status_text.config(state=tk.DISABLED)

    # ─── 监听控制 ──────────────────────────────────────

    def toggle_wechat_listener(self):
        base = CATPPUCCIN
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
                self.listener_btn.config(text="⏸️  停止监听",
                                          bg=base["red_dim"], fg=base["red"])
                self._pulse_label.config(text="监听中", fg=base["green"])
                self._start_pulse_animation()
                ctrl.wechat_listener_thread = threading.Thread(target=self.wechat_listener_loop, daemon=True)
                ctrl.wechat_listener_thread.start()
                ctrl.say("系统", f"已开始监听来自「{ctrl.wechat_controller.contact}」的微信消息,间隔 {ctrl.wechat_controller.check_interval} 秒。")
            else:
                ctrl.wechat_listener_running = False
                ctrl.listener_paused = False
                self.listener_btn.config(text="▶️  开始监听",
                                          bg=base["green_dim"], fg=base["green"])
                self._pulse_label.config(text="已停止", fg=base["overlay0"])
                self._stop_pulse_animation()
                ctrl.say("系统", "已停止监听微信指令。")

    def _try_auto_open_wechat(self):
        ctrl = self.controller
        try:
            from modules.macro_recorder import get_recorder, get_player
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
                        base = CATPPUCCIN
                        ctrl.root.after(0, lambda: (
                            self.listener_btn.config(text="▶️  开始监听",
                                                      bg=base["green_dim"], fg=base["green"]),
                            self._pulse_label.config(text="已停止", fg=base["overlay0"]),
                            self._stop_pulse_animation()
                        ))
                        break

            time.sleep(0.5)
