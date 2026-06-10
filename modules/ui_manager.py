import tkinter as tk
from tkinter import ttk
import threading
import time
import math
import logging
import re

logger = logging.getLogger("UIManager")

# ─── Catppuccin Mocha 配色常量 ───────────────────────────────────
THEME = {
    "base":       "#1e1e2e",  # 背景
    "mantle":     "#181825",  # 深背景
    "crust":      "#11111b",  # 最深
    "surface0":   "#313244",  # 表面0
    "surface1":   "#45475a",  # 表面1
    "surface2":   "#585b70",  # 表面2
    "overlay0":   "#6c7086",  # 叠加0
    "overlay1":   "#7f849c",  # 叠加1
    "text":       "#cdd6f4",  # 主文字
    "subtext0":   "#a6adc8",  # 副文字
    "subtext1":   "#bac2de",  # 副文字1
    "blue":       "#89b4fa",  # 蓝色(用户气泡)
    "blue_dim":   "#2a3a5c",  # 蓝色暗底(用户气泡背景)
    "green":      "#a6e3a1",  # 绿色
    "green_dim":  "#2a3a2c",  # 绿色暗底
    "red":        "#f38ba8",  # 红色
    "yellow":     "#f9e2af",  # 黄色
    "mauve":      "#cba6f7",  # 紫色
    "peach":      "#fab387",  # 橘色
    "teal":       "#94e2d5",  # 青色
    "lavender":   "#b4befe",  # 薰衣草
    "pink":       "#f5c2e7",  # 粉色
    "sky":        "#89dceb",  # 天蓝
    "rosewater":  "#f5e0dc",  # 玫瑰
    "flamingo":   "#f2cdcd",  # 火烈鸟
}


class UIManager:
    """UI管理器 - 统一管理所有UI相关操作，确保线程安全和状态保持"""

    def __init__(self, root):
        self.root = root
        self._window_states = {}
        self._locks = {}
        self._callbacks = {}
        self._global_vars = {}
        self._pulse_jobs = {}  # 脉冲动画 job id

    def save_window_state(self, window_name, state):
        self._window_states[window_name] = state
        logger.debug(f"窗口状态已保存: {window_name}")

    def get_window_state(self, window_name, default=None):
        return self._window_states.get(window_name, default)

    def get_or_create_var(self, var_name, var_type, default=None):
        if var_name not in self._locks:
            self._locks[var_name] = threading.Lock()
        with self._locks[var_name]:
            if var_name not in self._global_vars:
                if var_type == "string":
                    self._global_vars[var_name] = tk.StringVar(value=default if default is not None else "")
                elif var_type == "int":
                    self._global_vars[var_name] = tk.IntVar(value=default if default is not None else 0)
                elif var_type == "double":
                    self._global_vars[var_name] = tk.DoubleVar(value=default if default is not None else 0.0)
                elif var_type == "boolean":
                    self._global_vars[var_name] = tk.BooleanVar(value=default if default is not None else False)
            return self._global_vars[var_name]

    def safe_update_ui(self, widget, **kwargs):
        def update():
            try:
                widget.config(**kwargs)
            except Exception as e:
                logger.error(f"UI更新失败: {e}")
        self.root.after(0, update)

    def safe_say(self, say_func, speaker, message):
        def say():
            try:
                say_func(speaker, message)
            except Exception as e:
                logger.error(f"消息发送失败: {e}")
        self.root.after(0, say)

    def safe_enable_widget(self, widget, state=True):
        def update():
            try:
                widget.config(state=tk.NORMAL if state else tk.DISABLED)
            except Exception as e:
                logger.error(f"控件状态更新失败: {e}")
        self.root.after(0, update)

    def safe_text_insert(self, text_widget, text):
        def insert():
            try:
                text_widget.config(state=tk.NORMAL)
                text_widget.insert(tk.END, text)
                text_widget.see(tk.END)
                text_widget.config(state=tk.DISABLED)
            except Exception as e:
                logger.error(f"文本插入失败: {e}")
        self.root.after(0, insert)

    # ─── 气泡渲染 ─────────────────────────────────────────────

    def render_bubble(self, chat_widget, who, text, timestamp=""):
        """在 ScrolledText 中渲染聊天气泡

        Args:
            chat_widget: ScrolledText 控件
            who: 'user' 或 'assistant' (或 '你'/'AI')
            text: 消息内容
            timestamp: 可选时间戳字符串
        """
        is_user = who in ("user", "你", "我")

        # 确保可编辑
        chat_widget.config(state=tk.NORMAL)

        # 时间戳(小灰字)
        if timestamp:
            chat_widget.insert(tk.END, f"  {timestamp}\n", "timestamp")

        # 处理代码块高亮
        parts = self._split_code_blocks(text)

        for part_type, part_text in parts:
            if part_type == "code":
                # 代码块: 带背景色
                tag_name = f"code_block_{id(part_text)}"
                chat_widget.tag_configure(
                    tag_name,
                    background=THEME["crust"],
                    foreground=THEME["green"],
                    font=("Cascadia Code", 9) if self._font_exists("Cascadia Code") else ("Consolas", 9),
                    relief=tk.FLAT,
                    borderwidth=0,
                    lmargin1=20,
                    lmargin2=20,
                    rmargin=20,
                    spacing1=4,
                    spacing3=4,
                )
                code_text = part_text.strip()
                if code_text:
                    chat_widget.insert(tk.END, f"  {code_text}\n", tag_name)
            else:
                # 普通文本: 使用气泡色
                if is_user:
                    tag_name = "user_bubble"
                    chat_widget.tag_configure(
                        tag_name,
                        foreground=THEME["blue"],
                        font=("微软雅黑", 10),
                    )
                    chat_widget.insert(tk.END, f"  {part_text}", tag_name)
                else:
                    tag_name = "ai_bubble"
                    chat_widget.tag_configure(
                        tag_name,
                        foreground=THEME["text"],
                        font=("微软雅黑", 10),
                    )
                    chat_widget.insert(tk.END, f"  {part_text}", tag_name)

        # 分隔线
        chat_widget.insert(tk.END, "\n")
        sep_tag = f"sep_{id(text)}"
        chat_widget.tag_configure(sep_tag, foreground=THEME["surface0"])
        chat_widget.insert(tk.END, "  ─────────────────────────────────\n", sep_tag)

        chat_widget.config(state=tk.DISABLED)
        chat_widget.see(tk.END)

    def _split_code_blocks(self, text):
        """将消息拆分为 (type, content) 列表, type 为 'text' 或 'code'"""
        pattern = r'(```[\s\S]*?```|`[^`\n]+`)'
        parts = []
        last = 0
        for m in re.finditer(pattern, text):
            if m.start() > last:
                parts.append(("text", text[last:m.start()]))
            code = m.group(0)
            # 去掉首尾反引号标记
            if code.startswith("```"):
                lines = code.split("\n")
                # 去掉第一行(可能含语言名)和最后的```
                if len(lines) > 2:
                    code_body = "\n".join(lines[1:-1])
                elif len(lines) == 2:
                    code_body = lines[1].rstrip("`")
                else:
                    code_body = code[3:].rstrip("`")
                parts.append(("code", code_body))
            else:
                parts.append(("code", code[1:-1]))
            last = m.end()
        if last < len(text):
            parts.append(("text", text[last:]))
        if not parts:
            parts.append(("text", text))
        return parts

    @staticmethod
    def _font_exists(font_name):
        """检查字体是否可用"""
        try:
            import tkinter.font as tkfont
            root = tk._default_root
            if root:
                families = tkfont.families(root)
                return font_name in families
        except Exception:
            pass
        return False

    # ─── 进度条渲染 ──────────────────────────────────────────

    def create_progress_bar(self, parent, label="", value=0.0, max_value=100.0,
                            bar_color=None, height=18, width=280):
        """创建一个带标签的现代风格进度条

        Returns:
            dict: {frame, label_widget, canvas, bar_id, text_id, update(value)}
        """
        if bar_color is None:
            bar_color = THEME["blue"]

        frame = tk.Frame(parent, bg=THEME["base"])

        if label:
            lbl = tk.Label(frame, text=label, font=("微软雅黑", 9),
                           bg=THEME["base"], fg=THEME["subtext1"], anchor="w")
            lbl.pack(fill=tk.X)

        canvas = tk.Canvas(frame, width=width, height=height,
                           bg=THEME["surface0"], highlightthickness=0, bd=0)
        canvas.pack(fill=tk.X, pady=(2, 0))

        # 圆角进度条
        bar_id = canvas.create_rectangle(
            0, 0, 0, height, fill=bar_color, outline="", width=0
        )

        text_id = canvas.create_text(
            width // 2, height // 2,
            text=f"{value:.0f}%", fill=THEME["text"],
            font=("微软雅黑", 8, "bold")
        )

        result = {
            "frame": frame,
            "label_widget": lbl if label else None,
            "canvas": canvas,
            "bar_id": bar_id,
            "text_id": text_id,
            "max_value": max_value,
            "width": width,
            "height": height,
        }

        def update_fn(val):
            pct = min(val / max_value, 1.0) if max_value > 0 else 0
            bar_w = int(pct * width)
            # 颜色: <70% blue, 70-90% yellow, >90% red
            if pct < 0.7:
                color = bar_color
            elif pct < 0.9:
                color = THEME["yellow"]
            else:
                color = THEME["red"]
            try:
                canvas.coords(bar_id, 0, 0, bar_w, height)
                canvas.itemconfig(bar_id, fill=color)
                canvas.itemconfig(text_id, text=f"{val:.0f}%")
            except Exception:
                pass

        result["update"] = update_fn
        update_fn(value)
        return result

    # ─── Chip/Badge 标签 ─────────────────────────────────────

    def create_chip(self, parent, text="", color=None, text_color=None, padx=10, pady=3):
        """创建 Chip 风格标签(圆角标签)

        Returns:
            tk.Label
        """
        if color is None:
            color = THEME["surface0"]
        if text_color is None:
            text_color = THEME["text"]

        chip = tk.Label(
            parent, text=text,
            bg=color, fg=text_color,
            font=("微软雅黑", 8),
            padx=padx, pady=pady,
            relief=tk.FLAT, bd=0,
        )
        return chip

    def create_status_chip(self, parent, text="", status="info"):
        """创建状态 Chip (带颜色)

        status: info/green/red/yellow/orange
        """
        colors = {
            "info":    (THEME["surface0"], THEME["text"]),
            "green":   (THEME["green_dim"], THEME["green"]),
            "red":     ("#3a2a2a", THEME["red"]),
            "yellow":  ("#3a3a2a", THEME["yellow"]),
            "orange":  ("#3a2e2a", THEME["peach"]),
        }
        bg, fg = colors.get(status, colors["info"])
        return self.create_chip(parent, text=text, color=bg, text_color=fg)

    # ─── 脉冲动画 ────────────────────────────────────────────

    def start_pulse(self, widget, on_color, off_color, interval=600):
        """启动脉冲动画(如监听指示器)

        Args:
            widget: tk.Label 或 tk.Canvas
            on_color: 亮色
            off_color: 暗色
            interval: 间隔毫秒
        """
        widget_id = id(widget)
        state = {"on": True}

        def pulse():
            if widget_id not in self._pulse_jobs:
                return
            try:
                if state["on"]:
                    widget.config(bg=on_color)
                else:
                    widget.config(bg=off_color)
                state["on"] = not state["on"]
            except Exception:
                return
            self._pulse_jobs[widget_id] = self.root.after(interval, pulse)

        self._pulse_jobs[widget_id] = self.root.after(interval, pulse)

    def stop_pulse(self, widget):
        """停止脉冲动画"""
        widget_id = id(widget)
        job = self._pulse_jobs.pop(widget_id, None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    # ─── 卡片式按钮 ──────────────────────────────────────────

    def create_card_button(self, parent, text="", icon="", command=None,
                           color=None, hover_color=None, width=100, height=60):
        """创建卡片式按钮(带图标+文字竖排)

        Returns:
            tk.Frame
        """
        if color is None:
            color = THEME["surface0"]
        if hover_color is None:
            hover_color = THEME["surface1"]

        card = tk.Frame(parent, bg=color, cursor="hand2",
                        highlightbackground=THEME["surface1"],
                        highlightthickness=1, padx=8, pady=6)

        icon_label = tk.Label(card, text=icon, font=("Segoe UI Emoji", 16),
                              bg=color, fg=THEME["text"])
        icon_label.pack(pady=(0, 2))

        text_label = tk.Label(card, text=text, font=("微软雅黑", 8),
                              bg=color, fg=THEME["subtext0"])
        text_label.pack()

        def on_enter(e):
            card.config(bg=hover_color)
            icon_label.config(bg=hover_color)
            text_label.config(bg=hover_color)

        def on_leave(e):
            card.config(bg=color)
            icon_label.config(bg=color)
            text_label.config(bg=color)

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
        icon_label.bind("<Enter>", on_enter)
        icon_label.bind("<Leave>", on_leave)
        text_label.bind("<Enter>", on_enter)
        text_label.bind("<Leave>", on_leave)

        if command:
            card.bind("<Button-1>", lambda e: command())
            icon_label.bind("<Button-1>", lambda e: command())
            text_label.bind("<Button-1>", lambda e: command())

        return card


ui_manager = None

def init_ui_manager(root):
    global ui_manager
    ui_manager = UIManager(root)
    return ui_manager

def get_ui_manager():
    return ui_manager


class ProgressManager:
    """进度管理器 - 统一管理进度显示"""

    def __init__(self):
        self._progress_vars = {}
        self._progress_callbacks = {}
        self._lock = threading.Lock()

    def create_progress_bar(self, name, max_value=100):
        with self._lock:
            if name not in self._progress_vars:
                from tkinter import DoubleVar
                self._progress_vars[name] = DoubleVar(value=0.0)
                self._progress_vars[name + "_max"] = max_value
        return self._progress_vars[name]

    def update_progress(self, name, value, max_value=None):
        with self._lock:
            if name in self._progress_vars:
                if max_value is not None:
                    self._progress_vars[name + "_max"] = max_value
                current_max = self._progress_vars.get(name + "_max", 100)
                percentage = (value / current_max) * 100 if current_max > 0 else 0
                self._progress_vars[name].set(percentage)
                if name in self._progress_callbacks:
                    try:
                        self._progress_callbacks[name](percentage)
                    except Exception as e:
                        logger.error(f"进度回调失败: {e}")

    def finish_progress(self, name):
        self.update_progress(name, 100)

    def set_callback(self, name, callback):
        with self._lock:
            self._progress_callbacks[name] = callback


progress_manager = ProgressManager()
