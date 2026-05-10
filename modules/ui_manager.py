import tkinter as tk
from tkinter import ttk
import threading
import time
import logging

logger = logging.getLogger("UIManager")

class UIManager:
    """UI管理器 - 统一管理所有UI相关操作，确保线程安全和状态保持"""

    def __init__(self, root):
        self.root = root
        self._window_states = {}  # 保存各功能窗口的状态
        self._locks = {}
        self._callbacks = {}
        self._global_vars = {}

    def save_window_state(self, window_name, state):
        """保存窗口状态"""
        self._window_states[window_name] = state
        logger.debug(f"窗口状态已保存: {window_name}")

    def get_window_state(self, window_name, default=None):
        """获取窗口状态"""
        return self._window_states.get(window_name, default)

    def get_or_create_var(self, var_name, var_type, default=None):
        """获取或创建全局变量（线程安全）"""
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
        """安全更新UI（通过root.after调度）"""
        def update():
            try:
                widget.config(**kwargs)
            except Exception as e:
                logger.error(f"UI更新失败: {e}")
        self.root.after(0, update)

    def safe_say(self, say_func, speaker, message):
        """安全调用say函数"""
        def say():
            try:
                say_func(speaker, message)
            except Exception as e:
                logger.error(f"消息发送失败: {e}")
        self.root.after(0, say)

    def safe_enable_widget(self, widget, state=True):
        """安全启用/禁用控件"""
        def update():
            try:
                widget.config(state=tk.NORMAL if state else tk.DISABLED)
            except Exception as e:
                logger.error(f"控件状态更新失败: {e}")
        self.root.after(0, update)

    def safe_text_insert(self, text_widget, text):
        """安全插入文本到文本控件"""
        def insert():
            try:
                text_widget.config(state=tk.NORMAL)
                text_widget.insert(tk.END, text)
                text_widget.see(tk.END)
                text_widget.config(state=tk.DISABLED)
            except Exception as e:
                logger.error(f"文本插入失败: {e}")
        self.root.after(0, insert)


ui_manager = None

def init_ui_manager(root):
    """初始化UI管理器"""
    global ui_manager
    ui_manager = UIManager(root)
    return ui_manager

def get_ui_manager():
    """获取UI管理器"""
    return ui_manager


class ProgressManager:
    """进度管理器 - 统一管理进度显示"""

    def __init__(self):
        self._progress_vars = {}
        self._progress_callbacks = {}
        self._lock = threading.Lock()

    def create_progress_bar(self, name, max_value=100):
        """创建进度条变量"""
        with self._lock:
            if name not in self._progress_vars:
                from tkinter import DoubleVar
                self._progress_vars[name] = DoubleVar(value=0.0)
                self._progress_vars[name + "_max"] = max_value
        return self._progress_vars[name]

    def update_progress(self, name, value, max_value=None):
        """更新进度"""
        with self._lock:
            if name in self._progress_vars:
                if max_value is not None:
                    self._progress_vars[name + "_max"] = max_value
                current_max = self._progress_vars.get(name + "_max", 100)
                percentage = (value / current_max) * 100 if current_max > 0 else 0
                self._progress_vars[name].set(percentage)
                
                if name in self._progress_callbacks:
                    from tkinter import Tk
                    try:
                        self._progress_callbacks[name](percentage)
                    except Exception as e:
                        logger.error(f"进度回调失败: {e}")

    def finish_progress(self, name):
        """完成进度"""
        self.update_progress(name, 100)

    def set_callback(self, name, callback):
        """设置进度回调"""
        with self._lock:
            self._progress_callbacks[name] = callback


progress_manager = ProgressManager()
