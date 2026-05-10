import pyautogui
import time
import json
import os
import logging
import threading
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple

try:
    from pynput import mouse, keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logging.warning("pynput未安装，将使用pyautogui替代")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("PIL未安装，图像识别功能不可用")

logger = logging.getLogger("MacroRecorder")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

MACRO_DIR = Path.home() / "aipc_macros"
MACRO_DIR.mkdir(exist_ok=True)

SCREENSHOT_DIR = MACRO_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


class MacroAction:
    """宏动作基类"""
    
    def __init__(self, action_type: str, **kwargs):
        self.type = action_type
        self.timestamp = kwargs.get("timestamp", 0)
        self.params = kwargs
        self.condition = kwargs.get("condition", None)
        self.retry_count = kwargs.get("retry_count", 0)
        self.retry_interval = kwargs.get("retry_interval", 1.0)
        self.on_error = kwargs.get("on_error", "stop")
        self.description = kwargs.get("description", "")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "timestamp": self.timestamp,
            **self.params,
            "condition": self.condition,
            "retry_count": self.retry_count,
            "retry_interval": self.retry_interval,
            "on_error": self.on_error,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MacroAction":
        action_type = data.pop("type", "unknown")
        return cls(action_type, **data)


class SmartMacroRecorder:
    """智能宏录制器 - 增强版"""
    
    def __init__(self):
        self.recording = False
        self.paused = False
        self.macro_name = ""
        self.actions: List[Dict[str, Any]] = []
        self.start_time = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._last_mouse_pos = None
        self._last_action_time = None
        self._action_count = 0
        self._variables: Dict[str, Any] = {}
        self._screenshots: List[str] = []
        self._callback: Optional[Callable[[str, Dict], None]] = None
        self._smart_mode = True
        self._min_move_distance = 5
        self._min_action_interval = 0.1
    
    def set_callback(self, callback: Callable[[str, Dict], None]):
        """设置回调函数"""
        self._callback = callback
    
    def _notify(self, event: str, data: Dict = None):
        """通知事件"""
        if self._callback:
            self._callback(event, data or {})
    
    def set_smart_mode(self, enabled: bool, min_move_distance: int = 5, min_action_interval: float = 0.1):
        """设置智能录制模式
        
        Args:
            enabled: 是否启用智能模式
            min_move_distance: 最小移动距离（像素），小于此距离的移动将被忽略
            min_action_interval: 最小动作间隔（秒），小于此间隔的重复动作将被合并
        """
        self._smart_mode = enabled
        self._min_move_distance = min_move_distance
        self._min_action_interval = min_action_interval
        logger.info(f"智能录制模式: {'启用' if enabled else '禁用'}, 最小移动距离: {min_move_distance}px, 最小间隔: {min_action_interval}s")
    
    def start_recording(self, name: str, variables: Dict[str, Any] = None) -> bool:
        """开始录制宏
        
        Args:
            name: 宏名称
            variables: 变量字典
        """
        if self.recording:
            logger.warning("已经在录制中")
            return False
        
        self.macro_name = name
        self.actions = []
        self.recording = True
        self.paused = False
        self.start_time = time.time()
        self._last_mouse_pos = None
        self._last_action_time = None
        self._action_count = 0
        self._variables = variables or {}
        self._screenshots = []
        
        if PYNPUT_AVAILABLE:
            self._start_pynput_listeners()
        else:
            self._start_pyautogui_listeners()
        
        logger.info(f"开始录制宏: {name}")
        self._notify("recording_started", {"name": name})
        return True
    
    def pause_recording(self):
        """暂停录制"""
        if self.recording and not self.paused:
            self.paused = True
            logger.info("录制已暂停")
            self._notify("recording_paused", {})
    
    def resume_recording(self):
        """恢复录制"""
        if self.recording and self.paused:
            self.paused = False
            logger.info("录制已恢复")
            self._notify("recording_resumed", {})
    
    def _start_pynput_listeners(self):
        """启动pynput监听"""
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll
        )
        self._mouse_listener.start()
        
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self._keyboard_listener.start()
    
    def _start_pyautogui_listeners(self):
        """启动pyautogui监听（备选方案）"""
        try:
            import win32api
            win32api_available = True
        except ImportError:
            win32api_available = False
            logger.error("win32api未安装，无法录制鼠标移动")
        
        def poll_mouse():
            last_pos = None
            while self.recording:
                if not self.paused:
                    try:
                        if win32api_available:
                            pos = win32api.GetCursorPos()
                            if last_pos != pos:
                                last_pos = pos
                                if self._smart_mode:
                                    if self._last_mouse_pos:
                                        dist = ((pos[0] - self._last_mouse_pos[0])**2 + 
                                               (pos[1] - self._last_mouse_pos[1])**2)**0.5
                                        if dist < self._min_move_distance:
                                            continue
                                self._record_action("move", x=pos[0], y=pos[1])
                    except Exception:
                        pass
                time.sleep(0.05)
        
        self._poll_thread = threading.Thread(target=poll_mouse, daemon=True)
        self._poll_thread.start()
    
    def _on_mouse_move(self, x, y):
        if not self.recording or self.paused:
            return
        
        if self._smart_mode and self._last_mouse_pos:
            dist = ((x - self._last_mouse_pos[0])**2 + (y - self._last_mouse_pos[1])**2)**0.5
            if dist < self._min_move_distance:
                return
        
        self._last_mouse_pos = (x, y)
    
    def _on_mouse_click(self, x, y, button, pressed):
        if not self.recording or self.paused:
            return
        
        if pressed:
            btn = "left" if button == mouse.Button.left else "right" if button == mouse.Button.right else "middle"
            
            if self._smart_mode and self._last_action_time:
                elapsed = time.time() - self._last_action_time
                if elapsed < self._min_action_interval:
                    if self.actions and self.actions[-1].get("type") == "click":
                        last = self.actions[-1]
                        if last.get("x") == x and last.get("y") == y and last.get("button") == btn:
                            last["clicks"] = last.get("clicks", 1) + 1
                            return
            
            self._record_action("click", x=x, y=y, button=btn, clicks=1)
    
    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.recording or self.paused:
            return
        self._record_action("scroll", x=x, y=y, dx=dx, dy=dy)
    
    def _on_key_press(self, key):
        if not self.recording or self.paused:
            return
        
        try:
            if hasattr(key, 'char') and key.char:
                key_name = key.char
            else:
                key_name = str(key).replace('Key.', '')
            
            modifiers = []
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                modifiers.append('ctrl')
            elif key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                modifiers.append('alt')
            elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                modifiers.append('shift')
            elif key == keyboard.Key.cmd or key == keyboard.Key.cmd_l:
                modifiers.append('win')
            else:
                self._record_action("key", key=key_name, modifiers=modifiers if modifiers else None)
        except Exception as e:
            logger.error(f"录制键盘事件失败: {e}")
    
    def _on_key_release(self, key):
        pass
    
    def _record_action(self, action_type: str, **kwargs):
        """记录动作"""
        if not self.recording or self.paused:
            return
        
        action = {
            "type": action_type,
            "timestamp": time.time() - self.start_time,
            **kwargs
        }
        
        self.actions.append(action)
        self._action_count += 1
        self._last_action_time = time.time()
        
        self._notify("action_recorded", {"type": action_type, "count": self._action_count})
    
    def add_screenshot(self, region: Tuple[int, int, int, int] = None, name: str = None) -> str:
        """添加截图动作
        
        Args:
            region: 截图区域 (left, top, width, height)，None表示全屏
            name: 截图名称
        
        Returns:
            截图文件路径
        """
        if not PIL_AVAILABLE:
            logger.warning("PIL未安装，无法截图")
            return ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name or 'screenshot'}_{timestamp}.png"
        filepath = SCREENSHOT_DIR / filename
        
        if region:
            screenshot = pyautogui.screenshot(region=region)
        else:
            screenshot = pyautogui.screenshot()
        
        screenshot.save(filepath)
        self._screenshots.append(str(filepath))
        
        self._record_action("screenshot", path=str(filepath), region=region)
        return str(filepath)
    
    def add_wait(self, duration: float, description: str = ""):
        """添加等待动作"""
        self._record_action("wait", duration=duration, description=description)
    
    def add_condition(self, condition_type: str, condition_value: Any, true_actions: List[Dict], false_actions: List[Dict] = None):
        """添加条件动作
        
        Args:
            condition_type: 条件类型 (image_exists, pixel_color, window_exists, variable)
            condition_value: 条件值
            true_actions: 条件为真时执行的动作
            false_actions: 条件为假时执行的动作
        """
        self._record_action(
            "condition",
            condition_type=condition_type,
            condition_value=condition_value,
            true_actions=true_actions,
            false_actions=false_actions or []
        )
    
    def add_loop(self, count: int, actions: List[Dict], interval: float = 0):
        """添加循环动作"""
        self._record_action("loop", count=count, actions=actions, interval=interval)
    
    def add_variable(self, name: str, value: Any):
        """添加变量"""
        self._variables[name] = value
        self._record_action("set_variable", name=name, value=value)
    
    def stop_recording(self) -> Optional[Dict[str, Any]]:
        """停止录制宏"""
        if not self.recording:
            logger.warning("没有在录制")
            return None
        
        self.recording = False
        self.paused = False
        
        # 安全停止鼠标监听器
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception as e:
                logger.error(f"停止鼠标监听器失败: {e}")
            finally:
                self._mouse_listener = None
        
        # 安全停止键盘监听器
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception as e:
                logger.error(f"停止键盘监听器失败: {e}")
            finally:
                self._keyboard_listener = None
        
        if hasattr(self, '_poll_thread'):
            self._poll_thread = None
        
        duration = time.time() - self.start_time
        
        macro_data = {
            "name": self.macro_name,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": duration,
            "actions": self.actions,
            "variables": self._variables,
            "screenshots": self._screenshots,
            "version": "2.0",
            "action_count": self._action_count
        }
        
        logger.info(f"停止录制宏: {self.macro_name}, 共 {len(self.actions)} 个动作")
        self._notify("recording_stopped", {"name": self.macro_name, "actions": len(self.actions)})
        return macro_data
    
    def save_macro(self, macro_data: Dict, filename: str = None) -> str:
        """保存宏到文件"""
        if filename is None:
            safe_name = "".join(c for c in macro_data['name'] if c.isalnum() or c in (' ', '-', '_'))
            filename = f"{safe_name}.json"
        
        filepath = MACRO_DIR / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(macro_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"宏已保存: {filepath}")
        return str(filepath)
    
    def load_macro(self, filename: str) -> Optional[Dict]:
        """从文件加载宏"""
        if not filename.endswith(".json"):
            filename = f"{filename}.json"
        
        filepath = MACRO_DIR / filename
        if not filepath.exists():
            logger.error(f"宏文件不存在: {filepath}")
            return None
        
        with open(filepath, 'r', encoding='utf-8') as f:
            macro_data = json.load(f)
        
        logger.info(f"宏已加载: {filename}")
        return macro_data
    
    def list_macros(self) -> List[Dict]:
        """列出所有宏"""
        macros = []
        for file in MACRO_DIR.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    macros.append({
                        "name": data.get("name", file.stem),
                        "file": file.name,
                        "actions": len(data.get("actions", [])),
                        "created": data.get("created", "未知"),
                        "duration": data.get("duration", 0),
                        "version": data.get("version", "1.0")
                    })
            except Exception as e:
                logger.warning(f"读取宏文件失败: {file}, {e}")
        return sorted(macros, key=lambda x: x.get("created", ""), reverse=True)
    
    def delete_macro(self, filename: str) -> bool:
        """删除宏"""
        if not filename.endswith(".json"):
            filename = f"{filename}.json"
        
        filepath = MACRO_DIR / filename
        if filepath.exists():
            filepath.unlink()
            logger.info(f"宏已删除: {filename}")
            return True
        return False

    def add_image_click(self, region: Tuple[int, int, int, int] = None, name: str = None) -> str:
        """添加图像识别点击动作（录制时自动截取目标区域保存）

        Args:
            region: 截图区域 (left, top, width, height)，None则截取全屏
            name: 图像名称后缀

        Returns:
            保存的图像路径，失败返回空字符串
        """
        if not PIL_AVAILABLE:
            logger.warning("PIL未安装，无法截图")
            return ""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"image_{name or timestamp}.png"
            filepath = SCREENSHOT_DIR / filename
            screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
            screenshot.save(filepath)
            self._record_action("image_click", image=str(filepath), confidence=0.9)
            logger.info(f"图像点击已录制: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"图像点击录制失败: {e}")
            return ""


class SmartMacroPlayer:
    """智能宏播放器 - 增强版"""
    
    def __init__(self):
        self.playing = False
        self.paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._current_action = 0
        self._total_actions = 0
        self._variables: Dict[str, Any] = {}
        self._callback: Optional[Callable[[str, Dict], None]] = None
        self._breakpoints: set = set()
        self._debug_mode = False
        self._speed = 1.0
    
    def set_callback(self, callback: Callable[[str, Dict], None]):
        """设置回调函数"""
        self._callback = callback
    
    def _notify(self, event: str, data: Dict = None):
        """通知事件"""
        if self._callback:
            self._callback(event, data or {})
    
    def set_debug_mode(self, enabled: bool):
        """设置调试模式"""
        self._debug_mode = enabled
        logger.info(f"调试模式: {'启用' if enabled else '禁用'}")
    
    def add_breakpoint(self, action_index: int):
        """添加断点"""
        self._breakpoints.add(action_index)
        logger.info(f"添加断点: 动作 {action_index}")
    
    def remove_breakpoint(self, action_index: int):
        """移除断点"""
        self._breakpoints.discard(action_index)
        logger.info(f"移除断点: 动作 {action_index}")
    
    def clear_breakpoints(self):
        """清除断点"""
        self._breakpoints.clear()
        logger.info("已清除断点")
    
    def set_speed(self, speed: float):
        """设置播放速度
        
        Args:
            speed: 播放速度倍率 (0.5 = 半速, 1.0 = 正常, 2.0 = 两倍速)
        """
        self._speed = max(0.1, min(10.0, speed))
        logger.info(f"播放速度: {self._speed}x")
    
    def play(self, macro_name, speed: float = 1.0, repeat: int = 1, 
             variables: Dict[str, Any] = None, start_from: int = 0) -> bool:
        """播放宏
        
        Args:
            macro_name: 宏名称或宏数据
            speed: 播放速度
            repeat: 重复次数
            variables: 变量覆盖
            start_from: 从第几个动作开始播放
        """
        if isinstance(macro_name, dict):
            macro_data = macro_name
        else:
            recorder = SmartMacroRecorder()
            macro_data = recorder.load_macro(macro_name)
        
        if not macro_data:
            logger.error(f"无法加载宏: {macro_name}")
            return False
        
        self._stop_event.clear()
        self._pause_event.clear()
        self.playing = True
        self.paused = False
        self._speed = speed
        self._variables = {**macro_data.get("variables", {}), **(variables or {})}
        self._total_actions = len(macro_data.get("actions", []))
        
        logger.info(f"开始播放宏: {macro_data.get('name', '未知')}")
        self._notify("play_started", {"name": macro_data.get("name", "未知"), "actions": self._total_actions})
        
        success = True
        for i in range(repeat):
            if self._stop_event.is_set():
                break
            
            logger.info(f"播放第 {i+1}/{repeat} 次")
            self._notify("repeat", {"current": i+1, "total": repeat})
            
            if not self._play_actions(macro_data.get("actions", []), start_from if i == 0 else 0):
                success = False
                break
            
            if i < repeat - 1 and not self._stop_event.is_set():
                time.sleep(0.5)
        
        self.playing = False
        logger.info(f"宏播放{'完成' if success else '中断'}: {macro_data.get('name', '未知')}")
        self._notify("play_finished", {"name": macro_data.get("name", "未知"), "success": success})
        return success
    
    def pause(self):
        """暂停播放"""
        if self.playing and not self.paused:
            self.paused = True
            self._pause_event.set()
            logger.info("播放已暂停")
            self._notify("play_paused", {})
    
    def resume(self):
        """恢复播放"""
        if self.playing and self.paused:
            self.paused = False
            self._pause_event.clear()
            logger.info("播放已恢复")
            self._notify("play_resumed", {})
    
    def stop(self):
        """停止播放"""
        self._stop_event.set()
        self._pause_event.clear()
        self.playing = False
        self.paused = False
        logger.info("宏播放已停止")
        self._notify("play_stopped", {})
    
    def _wait_if_paused(self):
        """如果暂停则等待"""
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.1)
    
    def _play_actions(self, actions: List[Dict], start_from: int = 0) -> bool:
        """播放动作列表"""
        last_time = 0
        
        for idx, action in enumerate(actions):
            if self._stop_event.is_set():
                return False
            
            self._wait_if_paused()
            
            if idx < start_from:
                continue
            
            self._current_action = idx
            
            if self._debug_mode and idx in self._breakpoints:
                logger.info(f"命中断点: 动作 {idx}")
                self._notify("breakpoint_hit", {"action_index": idx, "action": action})
                self.pause()
                self._wait_if_paused()
            
            self._notify("action_executing", {"index": idx, "total": len(actions), "action": action})
            
            try:
                if not self._execute_action(action):
                    return False
            except Exception as e:
                logger.error(f"播放动作失败: {action}, 错误: {e}")
                self._notify("action_error", {"action": action, "error": str(e)})
                
                on_error = action.get("on_error", "stop")
                if on_error == "stop":
                    return False
                elif on_error == "skip":
                    continue
                elif on_error == "retry":
                    retry_count = action.get("retry_count", 3)
                    for retry in range(retry_count):
                        logger.info(f"重试动作 {idx} ({retry+1}/{retry_count})")
                        time.sleep(action.get("retry_interval", 1.0))
                        try:
                            if self._execute_action(action):
                                break
                        except Exception:
                            if retry == retry_count - 1:
                                return False
            
            timestamp = action.get("timestamp", 0)
            if last_time > 0:
                wait = (timestamp - last_time) / self._speed
                if wait > 0:
                    for _ in range(int(wait * 10)):
                        if self._stop_event.is_set():
                            return False
                        self._wait_if_paused()
                        time.sleep(0.1)
            last_time = timestamp
        
        return True
    
    def _execute_action(self, action: Dict) -> bool:
        """执行单个动作"""
        action_type = action.get("type")
        
        if action_type == "move":
            x = self._get_variable_value(action.get("x"))
            y = self._get_variable_value(action.get("y"))
            duration = action.get("duration", 0) / self._speed
            if duration > 0:
                pyautogui.moveTo(x, y, duration=duration)
            else:
                pyautogui.moveTo(x, y)
        
        elif action_type == "click":
            x = self._get_variable_value(action.get("x"))
            y = self._get_variable_value(action.get("y"))
            button = action.get("button", "left")
            clicks = action.get("clicks", 1)
            interval = action.get("interval", 0) / self._speed
            
            for _ in range(clicks):
                if self._stop_event.is_set():
                    return False
                pyautogui.click(x, y, button=button)
                if interval > 0:
                    time.sleep(interval)
        
        elif action_type == "doubleclick":
            x = self._get_variable_value(action.get("x"))
            y = self._get_variable_value(action.get("y"))
            button = action.get("button", "left")
            pyautogui.doubleClick(x, y, button=button)
        
        elif action_type == "rightclick":
            x = self._get_variable_value(action.get("x"))
            y = self._get_variable_value(action.get("y"))
            pyautogui.rightClick(x, y)
        
        elif action_type == "scroll":
            dx = action.get("dx", 0)
            dy = action.get("dy", 0)
            pyautogui.scroll(dy)
        
        elif action_type == "drag":
            start_x = self._get_variable_value(action.get("start_x"))
            start_y = self._get_variable_value(action.get("start_y"))
            end_x = self._get_variable_value(action.get("end_x"))
            end_y = self._get_variable_value(action.get("end_y"))
            duration = action.get("duration", 0.5) / self._speed
            pyautogui.moveTo(start_x, start_y)
            pyautogui.dragTo(end_x, end_y, duration=duration)
        
        elif action_type == "key":
            key = self._get_variable_value(action.get("key"))
            modifiers = action.get("modifiers", [])
            if modifiers:
                pyautogui.hotkey(*modifiers, key)
            else:
                pyautogui.press(key)
        
        elif action_type == "type":
            text = self._get_variable_value(action.get("text"))
            interval = action.get("interval", 0) / self._speed
            pyautogui.write(text, interval=interval)
        
        elif action_type == "wait":
            wait_time = action.get("duration", 1) / self._speed
            for _ in range(int(wait_time * 10)):
                if self._stop_event.is_set():
                    return False
                self._wait_if_paused()
                time.sleep(0.1)
        
        elif action_type == "condition":
            return self._execute_condition(action)
        
        elif action_type == "loop":
            return self._execute_loop(action)
        
        elif action_type == "set_variable":
            self._variables[action.get("name")] = self._get_variable_value(action.get("value"))
        
        elif action_type == "screenshot":
            pass
        
        elif action_type == "image_click":
            return self._execute_image_click(action)
        
        return True
    
    def _execute_condition(self, action: Dict) -> bool:
        """执行条件动作"""
        condition_type = action.get("condition_type")
        condition_value = action.get("condition_value")
        true_actions = action.get("true_actions", [])
        false_actions = action.get("false_actions", [])
        
        condition_result = False
        
        if condition_type == "image_exists":
            if PIL_AVAILABLE:
                try:
                    location = pyautogui.locateOnScreen(condition_value, confidence=0.9)
                    condition_result = location is not None
                except Exception:
                    condition_result = False
        
        elif condition_type == "pixel_color":
            x, y, expected_color = condition_value
            actual_color = pyautogui.pixel(x, y)
            condition_result = actual_color == expected_color
        
        elif condition_type == "window_exists":
            try:
                import pygetwindow as gw
                windows = gw.getWindowsWithTitle(condition_value)
                condition_result = len(windows) > 0
            except Exception:
                condition_result = False
        
        elif condition_type == "variable":
            var_name, expected_value = condition_value
            condition_result = self._variables.get(var_name) == expected_value
        
        if condition_result:
            return self._play_actions(true_actions)
        else:
            return self._play_actions(false_actions)
    
    def _execute_loop(self, action: Dict) -> bool:
        """执行循环动作"""
        count = self._get_variable_value(action.get("count", 1))
        actions = action.get("actions", [])
        interval = action.get("interval", 0) / self._speed
        
        for i in range(count):
            if self._stop_event.is_set():
                return False
            
            self._notify("loop_iteration", {"current": i+1, "total": count})
            
            if not self._play_actions(actions):
                return False
            
            if interval > 0 and i < count - 1:
                time.sleep(interval)
        
        return True
    
    def _execute_image_click(self, action: Dict) -> bool:
        """执行图像识别点击"""
        if not PIL_AVAILABLE:
            logger.warning("PIL未安装，无法执行图像识别点击")
            return False
        
        image_path = action.get("image")
        confidence = action.get("confidence", 0.9)
        timeout = action.get("timeout", 10)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._stop_event.is_set():
                return False
            
            try:
                location = pyautogui.locateOnScreen(image_path, confidence=confidence)
                if location:
                    center = pyautogui.center(location)
                    pyautogui.click(center.x, center.y)
                    return True
            except Exception:
                pass
            
            time.sleep(0.5)
        
        logger.warning(f"图像识别超时: {image_path}")
        return False
    
    def _get_variable_value(self, value):
        """获取变量值，支持变量替换"""
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            return self._variables.get(var_name, value)
        return value


class MacroEditor:
    """宏编辑器 - 编辑已录制的宏"""
    
    def __init__(self):
        self.macro_data: Optional[Dict] = None
    
    def load(self, macro_data: Dict):
        """加载宏数据"""
        self.macro_data = macro_data.copy()
    
    def get_actions(self) -> List[Dict]:
        """获取所有动作"""
        return self.macro_data.get("actions", [])
    
    def add_action(self, action: Dict, index: int = -1):
        """添加动作"""
        actions = self.macro_data.get("actions", [])
        if index < 0 or index >= len(actions):
            actions.append(action)
        else:
            actions.insert(index, action)
        self.macro_data["actions"] = actions
    
    def remove_action(self, index: int) -> bool:
        """删除动作"""
        actions = self.macro_data.get("actions", [])
        if 0 <= index < len(actions):
            actions.pop(index)
            self.macro_data["actions"] = actions
            return True
        return False
    
    def update_action(self, index: int, action: Dict) -> bool:
        """更新动作"""
        actions = self.macro_data.get("actions", [])
        if 0 <= index < len(actions):
            actions[index] = action
            self.macro_data["actions"] = actions
            return True
        return False
    
    def move_action(self, from_index: int, to_index: int) -> bool:
        """移动动作"""
        actions = self.macro_data.get("actions", [])
        if 0 <= from_index < len(actions) and 0 <= to_index < len(actions):
            action = actions.pop(from_index)
            actions.insert(to_index, action)
            self.macro_data["actions"] = actions
            return True
        return False
    
    def optimize_actions(self):
        """优化动作序列"""
        actions = self.macro_data.get("actions", [])
        optimized = []
        
        for action in actions:
            if optimized:
                last = optimized[-1]
                
                if last["type"] == "move" and action["type"] == "move":
                    last["x"] = action["x"]
                    last["y"] = action["y"]
                    continue
                
                if last["type"] == "wait" and action["type"] == "wait":
                    last["duration"] += action["duration"]
                    continue
            
            optimized.append(action)
        
        self.macro_data["actions"] = optimized
        logger.info(f"动作优化完成: {len(actions)} -> {len(optimized)}")
    
    def set_variable(self, name: str, value: Any):
        """设置变量"""
        if "variables" not in self.macro_data:
            self.macro_data["variables"] = {}
        self.macro_data["variables"][name] = value
    
    def get_macro(self) -> Dict:
        """获取宏数据"""
        return self.macro_data


_global_recorder = None
_global_player = None
_global_editor = None


def get_recorder() -> SmartMacroRecorder:
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = SmartMacroRecorder()
    return _global_recorder


def get_player() -> SmartMacroPlayer:
    global _global_player
    if _global_player is None:
        _global_player = SmartMacroPlayer()
    return _global_player


def get_editor() -> MacroEditor:
    global _global_editor
    if _global_editor is None:
        _global_editor = MacroEditor()
    return _global_editor


MacroRecorder = SmartMacroRecorder
MacroPlayer = SmartMacroPlayer
