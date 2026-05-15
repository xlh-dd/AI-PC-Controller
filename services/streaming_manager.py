"""
StreamingManager - 统一的流式输出管理器

职责:
1. 管理流式输出的UI状态（token插入、状态栏动画、取消）
2. 消除 _chat_with_history 和 launch_hermes_task 的代码重复
3. 修复 after_cancel 线程安全问题（统一调度回主线程）
4. 错误类型区分（超时 vs 取消 vs 异常）
"""

import time
import threading
import logging
import tkinter as tk
from datetime import datetime
from typing import Callable, Optional
from enum import Enum

logger = logging.getLogger("StreamingManager")


class StreamError(Enum):
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


class StreamingManager:
    """流式输出管理器 — 单次流式会话的生命周期管理"""

    def __init__(self, root: tk.Tk, chat_widget, status_label,
                 on_complete: Optional[Callable] = None,
                 on_cancel_button: Optional[Callable] = None):
        """
        Args:
            root: tkinter 根窗口
            chat_widget: 聊天显示控件 (ScrolledText)
            status_label: 状态栏标签 (ttk.Label)
            on_complete: 流式完成回调 (可选，用于更新历史状态等)
            on_cancel_button: 取消按钮管理回调: (show: bool) -> None
        """
        self.root = root
        self.chat = chat_widget
        self.status_label = status_label
        self._on_complete = on_complete
        self._on_cancel_button = on_cancel_button

        # 状态
        self._cancel_event = threading.Event()
        self._timer_id: Optional[str] = None
        self._start_time: float = 0
        self._header_inserted: bool = False
        self._active: bool = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time if self._start_time else 0

    def cancel(self):
        """取消当前流式会话"""
        self._cancel_event.set()

    def can_start(self) -> bool:
        """检查是否可以开始新的流式会话"""
        return not self._active

    # ── 流式入口 ────────────────────────────────────────────────────────

    def start(self, task_fn: Callable, *,
              header_label: str = "AI",
              status_prefix: str = "处理中",
              timeout: int = 300,
              color_stops: tuple = (30, 90, 180)):
        """启动流式会话

        Args:
            task_fn: 后台任务函数，签名为 fn(stream_callback, cancel_event) -> str
            header_label: 聊天显示的标签 (如 "AI", "Hermes")
            status_prefix: 状态栏前缀 (如 "生成中", "处理中")
            timeout: 任务超时秒数
            color_stops: 颜色渐变时间节点 (绿, 橙, 黄) 秒
        """
        if self._active:
            logger.warning("StreamingManager: 已有活动会话，忽略重复启动")
            return

        self._cancel_event.clear()
        self._active = True
        self._start_time = time.time()
        self._header_inserted = False
        self._timer_id = None

        gs, os_, ys = color_stops[:3]

        def _on_token(token: str):
            if self._cancel_event.is_set():
                return

            def _update():
                if self._cancel_event.is_set():
                    return
                try:
                    self.chat.config(state=tk.NORMAL)
                    if not self._header_inserted:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.chat.insert(tk.END, f"[{ts}] [🤖 {header_label}] ")
                        self._header_inserted = True
                    self.chat.insert(tk.END, token)
                    self.chat.see(tk.END)
                    self.chat.config(state=tk.DISABLED)
                except Exception:
                    pass
            self.root.after(0, _update)

        def _run():
            try:
                # 启动动画 & 取消按钮
                self.root.after(0, lambda: self._animate_status(gs, os_, ys, header_label, status_prefix))
                if self._on_cancel_button:
                    self.root.after(0, lambda: self._on_cancel_button(True))

                result = task_fn(_on_token, self._cancel_event)

                if self._cancel_event.is_set():
                    self._finalize(StreamError.CANCELLED, "已取消")
                    return

                # 检查超时
                if result and (result.startswith("[超时]") or "超时" in result):
                    self._finalize(StreamError.TIMEOUT, result)
                    return

                # 检查错误
                if result and (
                    result.startswith("Hermes 错误:") or
                    result.startswith("[错误]") or
                    result.startswith("Error:")
                ):
                    self._finalize(StreamError.ERROR, result)
                    return

                self._finalize(None, result=result, elapsed=self.elapsed)

            except Exception as e:
                self._finalize(StreamError.ERROR, str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _animate_status(self, gs: int, os_: int, ys: int, header_label: str, status_prefix: str):
        """流式状态栏动画（提取自 start()）"""
        if self._cancel_event.is_set() or not self._active:
            return
        elapsed = self.elapsed
        frames = ["⟳", "⏳", "⏱", "⟲"]
        idx = int(elapsed * 2) % len(frames)

        if elapsed < gs:
            color = "#a6e3a1"
        elif elapsed < os_:
            color = "#fab387"
        elif elapsed < ys:
            color = "#f9e2af"
        else:
            color = "#f38ba8"

        if elapsed >= 60:
            m, s = divmod(int(elapsed), 60)
            timer = f"{m}:{s:02d}"
        else:
            timer = f"{elapsed:.0f}s"
        self._update_status(f"{frames[idx]} {header_label} {status_prefix}... {timer}", color)

        if self._active and not self._cancel_event.is_set():
            self._timer_id = self.root.after(500, lambda: self._animate_status(gs, os_, ys, header_label, status_prefix))

    # ── 内部方法 ────────────────────────────────────────────────────────────────────

    def _update_status(self, text: str, color: str):
        """更新状态栏（线程安全 — 通过 after 调度）"""
        def _update():
            try:
                self.status_label.config(text=text, foreground=color)
            except Exception:
                pass
        self.root.after(0, _update)

    def _finalize(self, error_type: Optional[StreamError],
                  message: str = "", elapsed: float = 0, result: str = None):
        """结束流式输出 — 修复 after_cancel 线程安全"""
        self._active = False

        # 清理定时器 — 通过主线程安全取消
        if self._timer_id:
            timer = self._timer_id
            self._timer_id = None
            self.root.after(0, lambda t=timer: self.root.after_cancel(t))

        def _done():
            try:
                if error_type is None:
                    # 成功完成
                    self.chat.config(state=tk.NORMAL)
                    self.chat.insert(tk.END, "\n\n")
                    self.chat.see(tk.END)
                    self.chat.config(state=tk.DISABLED)
                    if elapsed >= 60:
                        m, s = divmod(int(elapsed), 60)
                        timer = f"{m}:{s:02d}"
                    else:
                        timer = f"{elapsed:.1f}s"
                    self._update_status(f"✅ 就绪 ({timer})", "#a6e3a1")

                elif error_type == StreamError.CANCELLED:
                    # 用户取消
                    if self._header_inserted:
                        self.chat.config(state=tk.NORMAL)
                        self.chat.insert(tk.END, f"\n⏹ {message}\n\n")
                        self.chat.see(tk.END)
                        self.chat.config(state=tk.DISABLED)
                    self._update_status("⏹ 已取消", "#fab387")

                elif error_type == StreamError.TIMEOUT:
                    # 超时 — 区分于普通错误
                    timeout_hint = "💡 提示：任务可能过于复杂，请尝试简化问题或稍后重试"
                    if self._header_inserted:
                        self.chat.config(state=tk.NORMAL)
                        self.chat.insert(tk.END, f"\n⏰ {message}\n{timeout_hint}\n\n")
                        self.chat.see(tk.END)
                        self.chat.config(state=tk.DISABLED)
                    else:
                        self._insert_alert(f"⏰ {message}", "system")
                        self._insert_alert(timeout_hint, "system")
                    self._update_status("⏰ 超时", "#f9e2af")

                else:
                    # 通用错误
                    err_prefix = "❌ " if not message.startswith("❌") else ""
                    if self._header_inserted:
                        self.chat.config(state=tk.NORMAL)
                        self.chat.insert(tk.END, f"\n{err_prefix}{message}\n\n")
                        self.chat.see(tk.END)
                        self.chat.config(state=tk.DISABLED)
                    else:
                        self._insert_alert(f"AI 处理失败: {message}", "system")
                    self._update_status("❌ 错误", "#f38ba8")

                # 清理
                if self._on_cancel_button:
                    self._on_cancel_button(False)
                if self._on_complete:
                    try:
                        self._on_complete(error_type is None, result)
                    except TypeError:
                        self._on_complete()  # 向后兼容

            except Exception as e:
                logger.error(f"StreamingManager._finalize 异常: {e}")

        self.root.after(0, _done)

    def _insert_alert(self, msg: str, sender: str = "系统"):
        """插入系统消息 — 线程安全"""
        def _do():
            try:
                self.chat.config(state=tk.NORMAL)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.chat.insert(tk.END, f"[{ts}] [{sender}] {msg}\n")
                self.chat.see(tk.END)
                self.chat.config(state=tk.DISABLED)
            except Exception:
                pass
        self.root.after(0, _do)