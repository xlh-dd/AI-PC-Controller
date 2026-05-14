"""
系统控制器模块 - 增强AI操控电脑的能力
提供音量控制、网络控制、进程管理、窗口管理等系统级功能
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union

logger = logging.getLogger("SystemController")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None
    logger.warning("pyautogui未安装，GUI自动化功能受限")

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False
    pyperclip = None
    logger.warning("pyperclip未安装，剪贴板功能受限")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil未安装，进程管理功能受限")

try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False
    logger.warning("pygetwindow未安装，窗口管理功能受限")

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import win32service
    import win32com.client
    import pythoncom
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    logger.warning("pywin32未安装，部分高级系统控制功能受限")

try:
    import ctypes
    from ctypes import wintypes
    CTYPES_AVAILABLE = True
except ImportError:
    CTYPES_AVAILABLE = False
    logger.warning("ctypes不可用，部分系统控制功能受限")

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL未安装，截图功能受限")

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logger.warning("pyttsx3未安装，语音合成功能不可用")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract未安装，OCR功能不可用")

import socket
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

class SystemController:
    """系统控制器 - 提供各种系统级控制功能"""
    
    def __init__(self):
        self._volume_controller = None
        self._network_controller = None
        self._brightness_controller = None
        self._tts_engine = None
        logger.info("系统控制器初始化完成")
    
    # ===== 音量控制 =====
    
    def get_volume(self) -> Dict[str, Any]:
        """获取当前音量信息
        
        Returns:
            包含音量信息的字典
        """
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "需要pywin32库"}
        
        try:
            
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            
            current_volume = volume.GetMasterVolumeLevelScalar()
            is_muted = volume.GetMute()
            
            return {
                "success": True,
                "volume": round(current_volume * 100, 1),  # 百分比
                "is_muted": bool(is_muted),
                "volume_scalar": current_volume
            }
        except ImportError:
            # 备选方案：使用Windows API
            try:
                # 使用Windows API获取音量
                
                # 定义函数和常量
                user32 = ctypes.windll.user32
                
                # 简单方法：发送按键模拟
                return {
                    "success": True,
                    "volume": "未知",
                    "is_muted": False,
                    "note": "需要安装pycaw库获取精确音量"
                }
            except Exception as e:
                return {"success": False, "error": f"获取音量失败: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"获取音量失败: {str(e)}"}
    
    def set_volume(self, level: int, mute: Optional[bool] = None) -> Dict[str, Any]:
        """设置系统音量（精确到百分比）
        
        Args:
            level: 目标音量 (0-100)
            mute: 是否静音 (None表示不改变静音状态)
            
        Returns:
            操作结果
        """
        if not WIN32_AVAILABLE:
            return {"success": False, "error": "需要pywin32库"}
        
        try:
            # 尝试使用pycaw进行精确音量设置
            try:
                
                pythoncom.CoInitialize()
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = interface.QueryInterface(IAudioEndpointVolume)
                
                # 设置音量（0.0到1.0的浮点数）
                target_scalar = max(0.0, min(1.0, level / 100.0))
                volume.SetMasterVolumeLevelScalar(target_scalar, None)
                
                # 设置静音状态
                if mute is not None:
                    volume.SetMute(1 if mute else 0, None)
                
                pythoncom.CoUninitialize()
                
                return {
                    "success": True,
                    "message": f"音量已精确设置为{level}%",
                    "target_volume": level,
                    "target_volume_scalar": target_scalar,
                    "method": "pycaw"
                }
                
            except ImportError:
                # pycaw不可用，回退到按键模拟
                if not PYAUTOGUI_AVAILABLE:
                    return {"success": False, "error": "需要pyautogui库"}
                
                
                # 获取当前音量
                current_info = self.get_volume()
                if not current_info.get("success"):
                    return current_info
                
                current_volume = current_info.get("volume", 50)
                
                # 计算需要按多少次音量键
                volume_diff = level - current_volume
                
                if volume_diff > 0:
                    # 增大音量
                    key = "volumeup"
                    presses = min(int(volume_diff / 2), 50)  # 每次大约增加2%
                elif volume_diff < 0:
                    # 减小音量
                    key = "volumedown"
                    presses = min(int(abs(volume_diff) / 2), 50)
                else:
                    presses = 0
                
                # 执行按键
                for _ in range(presses):
                    pyautogui.press(key)
                    time.sleep(0.05)
                
                # 设置静音状态
                if mute is not None:
                    pyautogui.press("volumemute")
                
                return {
                    "success": True,
                    "message": f"音量已调整到约{level}%（使用按键模拟，可能不精确）",
                    "target_volume": level,
                    "presses": presses,
                    "method": "keyboard_simulation"
                }
                
        except Exception as e:
            return {"success": False, "error": f"设置音量失败: {str(e)}"}
    
    def volume_up(self, steps: int = 5) -> Dict[str, Any]:
        """增大音量
        
        Args:
            steps: 增加的步数，每步约2%
            
        Returns:
            操作结果
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "需要pyautogui库"}
        
        try:
            for _ in range(steps):
                pyautogui.press("volumeup")
                time.sleep(0.05)
            
            return {
                "success": True,
                "message": f"音量已增大{steps}步",
                "steps": steps
            }
        except Exception as e:
            return {"success": False, "error": f"增大音量失败: {str(e)}"}
    
    def volume_down(self, steps: int = 5) -> Dict[str, Any]:
        """减小音量
        
        Args:
            steps: 减小的步数，每步约2%
            
        Returns:
            操作结果
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "需要pyautogui库"}
        
        try:
            for _ in range(steps):
                pyautogui.press("volumedown")
                time.sleep(0.05)
            
            return {
                "success": True,
                "message": f"音量已减小{steps}步",
                "steps": steps
            }
        except Exception as e:
            return {"success": False, "error": f"减小音量失败: {str(e)}"}
    
    def toggle_mute(self) -> Dict[str, Any]:
        """切换静音状态
        
        Returns:
            操作结果
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "需要pyautogui库"}
        
        try:
            pyautogui.press("volumemute")
            
            # 尝试获取当前静音状态
            try:
                info = self.get_volume()
                is_muted = info.get("is_muted", False) if info.get("success") else False
                return {
                    "success": True,
                    "message": f"静音已{'开启' if is_muted else '关闭'}",
                    "is_muted": is_muted
                }
            except:
                return {
                    "success": True,
                    "message": "已切换静音状态"
                }
        except Exception as e:
            return {"success": False, "error": f"切换静音失败: {str(e)}"}
    
    # ===== 网络控制 =====
    
    def get_network_info(self) -> Dict[str, Any]:
        """获取网络信息
        
        Returns:
            包含网络信息的字典
        """
        try:
            
            net_info = []
            
            # 获取网络接口信息
            net_io = psutil.net_io_counters(pernic=True)
            net_addrs = psutil.net_if_addrs()
            net_stats = psutil.net_if_stats()
            
            for iface, addrs in net_addrs.items():
                # 获取IPv4地址
                ipv4 = None
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ipv4 = addr.address
                        break
                
                # 获取状态
                is_up = False
                if iface in net_stats:
                    is_up = net_stats[iface].isup
                
                # 获取流量统计
                bytes_sent = 0
                bytes_recv = 0
                if iface in net_io:
                    bytes_sent = net_io[iface].bytes_sent
                    bytes_recv = net_io[iface].bytes_recv
                
                net_info.append({
                    "interface": iface,
                    "ipv4": ipv4,
                    "status": "在线" if is_up else "离线",
                    "bytes_sent": bytes_sent,
                    "bytes_recv": bytes_recv
                })
            
            # 获取连接信息
            connections = []
            try:
                for conn in psutil.net_connections(kind='inet'):
                    connections.append({
                        "protocol": conn.type.name,
                        "local_address": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "",
                        "remote_address": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "",
                        "status": conn.status
                    })
            except Exception:
                connections = []
            
            return {
                "success": True,
                "interfaces": net_info,
                "connections": connections[:20],  # 限制数量
                "total_interfaces": len(net_info)
            }
        except Exception as e:
            return {"success": False, "error": f"获取网络信息失败: {str(e)}"}
    
    def toggle_wifi(self, enable: Optional[bool] = None) -> Dict[str, Any]:
        """切换Wi-Fi状态
        
        Args:
            enable: True=开启, False=关闭, None=切换
            
        Returns:
            操作结果
        """
        try:
            # 使用netsh命令控制Wi-Fi
            if enable is None:
                # 获取当前状态
                result = subprocess.run(
                    ["netsh", "interface", "show", "interface", "Wi-Fi"],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                
                if "已启用" in result.stdout or "Enabled" in result.stdout:
                    enable = False  # 当前开启，需要关闭
                else:
                    enable = True  # 当前关闭，需要开启
            
            action = "enable" if enable else "disable"
            result = subprocess.run(
                ["netsh", "interface", "set", "interface", "Wi-Fi", action],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Wi-Fi已{ '开启' if enable else '关闭' }",
                    "action": action
                }
            else:
                return {
                    "success": False,
                    "error": f"Wi-Fi控制失败: {result.stderr}",
                    "action": action
                }
        except Exception as e:
            return {"success": False, "error": f"切换Wi-Fi失败: {str(e)}"}
    
    def get_wifi_status(self) -> Dict[str, Any]:
        """获取Wi-Fi状态
        
        Returns:
            Wi-Fi状态信息
        """
        try:
            result = subprocess.run(
                ["netsh", "interface", "show", "interface", "Wi-Fi"],
                capture_output=True,
                text=True,
                shell=True
            )
            
            output = result.stdout
            is_enabled = "已启用" in output or "Enabled" in output
            
            # 获取连接的SSID
            ssid = "未连接"
            try:
                result2 = subprocess.run(
                    ["netsh", "wlan", "show", "interfaces"],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                for line in result2.stdout.split('\n'):
                    if "SSID" in line and "BSSID" not in line:
                        parts = line.split(":")
                        if len(parts) > 1:
                            ssid = parts[1].strip()
                            break
            except:
                pass
            
            return {
                "success": True,
                "enabled": is_enabled,
                "ssid": ssid,
                "status": "已连接" if ssid != "未连接" else "未连接"
            }
        except Exception as e:
            return {"success": False, "error": f"获取Wi-Fi状态失败: {str(e)}"}
    
    # ===== 进程管理 =====
    
    def list_processes(self, filter_str: str = "") -> Dict[str, Any]:
        """列出所有进程
        
        Args:
            filter_str: 过滤字符串
            
        Returns:
            进程列表
        """
        if not PSUTIL_AVAILABLE:
            return {"success": False, "error": "需要psutil库"}
        
        try:
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent']):
                try:
                    process_info = proc.info
                    
                    # 过滤
                    if filter_str and filter_str.lower() not in process_info['name'].lower():
                        continue
                    
                    processes.append({
                        "pid": process_info['pid'],
                        "name": process_info['name'],
                        "status": process_info['status'],
                        "cpu_percent": round(process_info['cpu_percent'], 1),
                        "memory_percent": round(process_info['memory_percent'], 1)
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            # 按CPU使用率排序
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            
            return {
                "success": True,
                "processes": processes[:50],  # 限制数量
                "total": len(processes)
            }
        except Exception as e:
            return {"success": False, "error": f"获取进程列表失败: {str(e)}"}
    
    def kill_process(self, pid: int, force: bool = False) -> Dict[str, Any]:
        """结束进程
        
        Args:
            pid: 进程ID
            force: 是否强制结束
            
        Returns:
            操作结果
        """
        if not PSUTIL_AVAILABLE:
            return {"success": False, "error": "需要psutil库"}
        
        try:
            process = psutil.Process(pid)
            
            if force:
                process.kill()
                action = "强制结束"
            else:
                process.terminate()
                action = "结束"
            
            # 等待进程结束
            try:
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                return {
                    "success": False,
                    "error": f"进程{pid}没有及时结束",
                    "pid": pid
                }
            
            return {
                "success": True,
                "message": f"已{action}进程: {process.name()} (PID: {pid})",
                "pid": pid,
                "name": process.name()
            }
        except psutil.NoSuchProcess:
            return {"success": False, "error": f"进程{pid}不存在"}
        except psutil.AccessDenied:
            return {"success": False, "error": f"没有权限结束进程{pid}"}
        except Exception as e:
            return {"success": False, "error": f"结束进程失败: {str(e)}"}
    
    def kill_process_by_name(self, process_name: str, force: bool = False) -> Dict[str, Any]:
        """通过进程名结束进程
        
        Args:
            process_name: 进程名（不区分大小写）
            force: 是否强制结束
            
        Returns:
            操作结果
        """
        if not PSUTIL_AVAILABLE:
            return {"success": False, "error": "需要psutil库"}
        
        try:
            killed = []
            failed = []
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if process_name.lower() in proc.info['name'].lower():
                        pid = proc.info['pid']
                        result = self.kill_process(pid, force)
                        if result['success']:
                            killed.append(pid)
                        else:
                            failed.append({"pid": pid, "error": result['error']})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            return {
                "success": True,
                "message": f"已结束{killed}个进程，失败{len(failed)}个",
                "killed": killed,
                "failed": failed,
                "total_killed": len(killed)
            }
        except Exception as e:
            return {"success": False, "error": f"结束进程失败: {str(e)}"}
    
    # ===== 窗口管理 =====
    
    def list_windows(self, filter_str: str = "") -> Dict[str, Any]:
        """列出所有窗口
        
        Args:
            filter_str: 过滤字符串
            
        Returns:
            窗口列表
        """
        if not PYGETWINDOW_AVAILABLE:
            return {"success": False, "error": "需要pygetwindow库"}
        
        try:
            windows = gw.getAllWindows()
            window_list = []
            
            for win in windows:
                try:
                    title = win.title
                    
                    # 过滤
                    if filter_str and filter_str.lower() not in title.lower():
                        continue
                    
                    window_list.append({
                        "title": title,
                        "left": win.left,
                        "top": win.top,
                        "width": win.width,
                        "height": win.height,
                        "is_active": win.isActive,
                        "is_minimized": win.isMinimized,
                        "is_maximized": win.isMaximized
                    })
                except Exception:
                    continue
            
            return {
                "success": True,
                "windows": window_list,
                "total": len(window_list)
            }
        except Exception as e:
            return {"success": False, "error": f"获取窗口列表失败: {str(e)}"}
    
    def find_window(self, title_pattern: str) -> Dict[str, Any]:
        """查找窗口
        
        Args:
            title_pattern: 窗口标题模式（支持通配符*）
            
        Returns:
            窗口信息
        """
        if not PYGETWINDOW_AVAILABLE:
            return {"success": False, "error": "需要pygetwindow库"}
        
        try:
            windows = gw.getWindowsWithTitle(title_pattern)
            
            if not windows:
                # 尝试模糊匹配
                all_windows = gw.getAllWindows()
                matched = []
                for win in all_windows:
                    if title_pattern.lower() in win.title.lower():
                        matched.append(win)
                windows = matched
            
            window_list = []
            for win in windows:
                window_list.append({
                    "title": win.title,
                    "left": win.left,
                    "top": win.top,
                    "width": win.width,
                    "height": win.height,
                    "is_active": win.isActive,
                    "is_minimized": win.isMinimized,
                    "is_maximized": win.isMaximized
                })
            
            return {
                "success": True,
                "windows": window_list,
                "count": len(window_list)
            }
        except Exception as e:
            return {"success": False, "error": f"查找窗口失败: {str(e)}"}
    
    def activate_window(self, title_pattern: str) -> Dict[str, Any]:
        """激活窗口
        
        Args:
            title_pattern: 窗口标题模式
            
        Returns:
            操作结果
        """
        if not PYGETWINDOW_AVAILABLE:
            return {"success": False, "error": "需要pygetwindow库"}
        
        try:
            windows = gw.getWindowsWithTitle(title_pattern)
            
            if not windows:
                # 尝试模糊匹配
                all_windows = gw.getAllWindows()
                matched = []
                for win in all_windows:
                    if title_pattern.lower() in win.title.lower():
                        matched.append(win)
                windows = matched
            
            if not windows:
                return {"success": False, "error": f"未找到标题包含'{title_pattern}'的窗口"}
            
            # 激活第一个匹配的窗口
            window = windows[0]
            if window.isMinimized:
                window.restore()
            window.activate()
            
            return {
                "success": True,
                "message": f"已激活窗口: {window.title}",
                "title": window.title
            }
        except Exception as e:
            return {"success": False, "error": f"激活窗口失败: {str(e)}"}
    
    def minimize_window(self, title_pattern: str) -> Dict[str, Any]:
        """最小化窗口
        
        Args:
            title_pattern: 窗口标题模式
            
        Returns:
            操作结果
        """
        if not PYGETWINDOW_AVAILABLE:
            return {"success": False, "error": "需要pygetwindow库"}
        
        try:
            windows = self.find_window(title_pattern)
            if not windows.get("success") or not windows.get("windows"):
                return windows
            
            for win_info in windows["windows"]:
                # 通过pygetwindow最小化
                matched_windows = gw.getWindowsWithTitle(win_info["title"])
                if matched_windows:
                    matched_windows[0].minimize()
            
            return {
                "success": True,
                "message": f"已最小化{len(windows['windows'])}个窗口",
                "count": len(windows["windows"])
            }
        except Exception as e:
            return {"success": False, "error": f"最小化窗口失败: {str(e)}"}
    
    def maximize_window(self, title_pattern: str) -> Dict[str, Any]:
        """最大化窗口
        
        Args:
            title_pattern: 窗口标题模式
            
        Returns:
            操作结果
        """
        if not PYGETWINDOW_AVAILABLE:
            return {"success": False, "error": "需要pygetwindow库"}
        
        try:
            windows = self.find_window(title_pattern)
            if not windows.get("success") or not windows.get("windows"):
                return windows
            
            for win_info in windows["windows"]:
                # 通过pygetwindow最大化
                matched_windows = gw.getWindowsWithTitle(win_info["title"])
                if matched_windows:
                    matched_windows[0].maximize()
            
            return {
                "success": True,
                "message": f"已最大化{len(windows['windows'])}个窗口",
                "count": len(windows["windows"])
            }
        except Exception as e:
            return {"success": False, "error": f"最大化窗口失败: {str(e)}"}
    
    def close_window(self, title_pattern: str) -> Dict[str, Any]:
        """关闭窗口
        
        Args:
            title_pattern: 窗口标题模式
            
        Returns:
            操作结果
        """
        if not PYGETWINDOW_AVAILABLE:
            return {"success": False, "error": "需要pygetwindow库"}
        
        try:
            windows = self.find_window(title_pattern)
            if not windows.get("success") or not windows.get("windows"):
                return windows
            
            for win_info in windows["windows"]:
                # 通过pygetwindow关闭
                matched_windows = gw.getWindowsWithTitle(win_info["title"])
                if matched_windows:
                    matched_windows[0].close()
            
            return {
                "success": True,
                "message": f"已关闭{len(windows['windows'])}个窗口",
                "count": len(windows["windows"])
            }
        except Exception as e:
            return {"success": False, "error": f"关闭窗口失败: {str(e)}"}
    
    # ===== 屏幕截图 =====
    
    def take_screenshot(self, region: Optional[Tuple[int, int, int, int]] = None, 
                        save_path: Optional[str] = None) -> Dict[str, Any]:
        """截取屏幕
        
        Args:
            region: 截图区域 (left, top, width, height)，None表示全屏
            save_path: 保存路径，None表示不保存
            
        Returns:
            截图结果
        """
        if not PIL_AVAILABLE:
            return {"success": False, "error": "需要PIL库"}
        
        try:
            screenshot = ImageGrab.grab(bbox=region)
            
            if save_path:
                filepath = Path(save_path)
                filepath.parent.mkdir(parents=True, exist_ok=True)
                screenshot.save(filepath)
                
                return {
                    "success": True,
                    "message": f"截图已保存到: {save_path}",
                    "path": str(filepath),
                    "size": screenshot.size,
                    "mode": screenshot.mode
                }
            else:
                # 返回临时文件路径
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    screenshot.save(f.name)
                    
                    return {
                        "success": True,
                        "message": "截图已完成",
                        "path": f.name,
                        "size": screenshot.size,
                        "mode": screenshot.mode
                    }
        except Exception as e:
            return {"success": False, "error": f"截图失败: {str(e)}"}
    
    # ===== 剪贴板增强 =====
    
    def get_clipboard(self) -> Dict[str, Any]:
        """获取剪贴板内容
        
        Returns:
            剪贴板内容
        """
        if not PYPERCLIP_AVAILABLE:
            return {"success": False, "error": "需要pyperclip库"}
        
        try:
            content = pyperclip.paste()
            
            return {
                "success": True,
                "content": content,
                "length": len(content),
                "type": "text"  # 目前只支持文本
            }
        except Exception as e:
            return {"success": False, "error": f"获取剪贴板失败: {str(e)}"}
    
    def set_clipboard(self, content: str) -> Dict[str, Any]:
        """设置剪贴板内容
        
        Args:
            content: 要设置的内容
            
        Returns:
            操作结果
        """
        if not PYPERCLIP_AVAILABLE:
            return {"success": False, "error": "需要pyperclip库"}
        
        try:
            pyperclip.copy(content)
            
            return {
                "success": True,
                "message": "剪贴板内容已设置",
                "length": len(content)
            }
        except Exception as e:
            return {"success": False, "error": f"设置剪贴板失败: {str(e)}"}
    
    def clear_clipboard(self) -> Dict[str, Any]:
        """清空剪贴板
        
        Returns:
            操作结果
        """
        if not PYPERCLIP_AVAILABLE:
            return {"success": False, "error": "需要pyperclip库"}
        
        try:
            pyperclip.copy("")
            
            return {
                "success": True,
                "message": "剪贴板已清空"
            }
        except Exception as e:
            return {"success": False, "error": f"清空剪贴板失败: {str(e)}"}
    
    # ===== 电源管理 =====
    
    def turn_off_display(self) -> Dict[str, Any]:
        """关闭显示器
        
        Returns:
            操作结果
        """
        try:
            # 使用Windows API关闭显示器
            if WIN32_AVAILABLE:
                
                # 发送关闭显示器的消息
                win32gui.SendMessage(win32con.HWND_BROADCAST, win32con.WM_SYSCOMMAND, 
                                    win32con.SC_MONITORPOWER, 2)
                return {"success": True, "message": "显示器已关闭"}
            else:
                # 使用命令行
                subprocess.run(["powershell", "-Command", "(Add-Type '[DllImport(\"user32.dll\")]public static extern int SendMessage(int hWnd, int hMsg, int wParam, int lParam);' -Name a -Pas)::SendMessage(-1,0x0112,0xF170,2)"], 
                             shell=True, capture_output=True)
                return {"success": True, "message": "已发送关闭显示器命令"}
        except Exception as e:
            return {"success": False, "error": f"关闭显示器失败: {str(e)}"}
    
    def hibernate(self) -> Dict[str, Any]:
        """休眠系统
        
        Returns:
            操作结果
        """
        try:
            subprocess.run(["shutdown", "/h"], shell=False)
            return {"success": True, "message": "正在进入休眠状态..."}
        except Exception as e:
            return {"success": False, "error": f"休眠失败: {str(e)}"}
    
    # ===== 语音合成 =====
    
    def speak_text(self, text: str, rate: int = 150, volume: float = 1.0) -> Dict[str, Any]:
        """语音合成
        
        Args:
            text: 要合成的文本
            rate: 语速 (默认150)
            volume: 音量 (0.0-1.0)
            
        Returns:
            操作结果
        """
        if not TTS_AVAILABLE:
            return {"success": False, "error": "需要pyttsx3库"}
        
        try:
            if self._tts_engine is None:
                self._tts_engine = pyttsx3.init()
            
            self._tts_engine.setProperty('rate', rate)
            self._tts_engine.setProperty('volume', volume)
            
            # 在后台线程中播放
            def speak_in_thread():
                self._tts_engine.say(text)
                self._tts_engine.runAndWait()
            
            thread = threading.Thread(target=speak_in_thread, daemon=True)
            thread.start()
            
            return {
                "success": True,
                "message": f"正在播放语音: {text[:50]}...",
                "length": len(text)
            }
        except Exception as e:
            return {"success": False, "error": f"语音合成失败: {str(e)}"}
    
    # ===== 文本识别 (OCR) =====
    
    def ocr_image(self, image_path: str, lang: str = "chi_sim+eng") -> Dict[str, Any]:
        """识别图片中的文字
        
        Args:
            image_path: 图片路径
            lang: 语言代码
            
        Returns:
            识别结果
        """
        if not TESSERACT_AVAILABLE:
            return {"success": False, "error": "需要pytesseract库"}
        
        try:
            from PIL import Image
            
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang=lang)
            
            return {
                "success": True,
                "text": text,
                "length": len(text),
                "language": lang
            }
        except Exception as e:
            return {"success": False, "error": f"OCR识别失败: {str(e)}"}
    
    def ocr_screen(self, region: Optional[Tuple[int, int, int, int]] = None, 
                   lang: str = "chi_sim+eng") -> Dict[str, Any]:
        """识别屏幕区域的文字
        
        Args:
            region: 屏幕区域
            lang: 语言代码
            
        Returns:
            识别结果
        """
        if not TESSERACT_AVAILABLE or not PIL_AVAILABLE:
            return {"success": False, "error": "需要pytesseract和PIL库"}
        
        try:
            # 先截图
            screenshot_result = self.take_screenshot(region)
            if not screenshot_result.get("success"):
                return screenshot_result
            
            image_path = screenshot_result.get("path")
            
            # 进行OCR识别
            ocr_result = self.ocr_image(image_path, lang)
            
            # 删除临时文件
            try:
                os.remove(image_path)
            except:
                pass
            
            return ocr_result
        except Exception as e:
            return {"success": False, "error": f"屏幕OCR识别失败: {str(e)}"}
    
    def get_installed_software(self) -> Dict[str, Any]:
        """获取已安装软件列表
        
        Returns:
            包含软件列表的字典，可能包含warnings字段
        """
        try:
            import winreg
            software_list = []
            warnings = []
            paths_accessed = 0
            total_paths = 0
            
            # 注册表路径
            registry_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM\\SOFTWARE..."),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM\\SOFTWARE\\WOW6432Node..."),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU\\SOFTWARE...")
            ]
            
            total_paths = len(registry_paths)
            
            for hive, path, display_path in registry_paths:
                try:
                    key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY if hive == winreg.HKEY_LOCAL_MACHINE else winreg.KEY_READ)
                    paths_accessed += 1
                    self._enumerate_registry_subkeys(key, path, display_path, software_list, warnings)
                    winreg.CloseKey(key)
                except PermissionError as pe:
                    warnings.append(f"权限不足，无法访问注册表路径 {display_path}: {pe}")
                    logger.warning(f"权限不足，无法打开注册表路径 {path}: {pe}")
                except FileNotFoundError as fnfe:
                    warnings.append(f"注册表路径不存在 {display_path}: {fnfe}")
                    logger.warning(f"注册表路径不存在 {path}: {fnfe}")
                except Exception as e:
                    warnings.append(f"无法打开注册表路径 {display_path}: {e}")
                    logger.warning(f"无法打开注册表路径 {path}: {e}")
            
            # 检查是否所有路径都访问失败
            if paths_accessed == 0 and total_paths > 0:
                error_msg = f"无法访问任何注册表路径，可能需要管理员权限。警告: {', '.join(warnings[:3])}"
                return {
                    "success": False,
                    "error": error_msg,
                    "warnings": warnings
                }
            
            # 去重（按软件名）
            unique_software = {}
            for software in software_list:
                name = software.get("name", "")
                if name and name not in unique_software:
                    unique_software[name] = software
            
            software_list = list(unique_software.values())
            
            # 按名称排序
            software_list.sort(key=lambda x: x.get("name", "").lower())
            
            result = {
                "success": True,
                "software_count": len(software_list),
                "software_list": software_list,
                "paths_accessed": f"{paths_accessed}/{total_paths}",
                "has_warnings": len(warnings) > 0
            }
            
            # 如果有警告，添加到结果中
            if warnings:
                result["warnings"] = warnings[:10]  # 限制警告数量
            
            return result
        except Exception as e:
            return {"success": False, "error": f"获取已安装软件列表失败: {str(e)}"}

    def _enumerate_registry_subkeys(self, key, path, display_path, software_list, warnings):
        """枚举注册表子键并读取软件信息"""
        import winreg
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                try:
                    subkey = winreg.OpenKey(key, subkey_name, 0, winreg.KEY_READ)

                    # 获取软件信息
                    software = {}
                    try:
                        software["name"] = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    except:
                        software["name"] = subkey_name

                    try:
                        software["version"] = winreg.QueryValueEx(subkey, "DisplayVersion")[0]
                    except:
                        software["version"] = "未知"

                    try:
                        software["publisher"] = winreg.QueryValueEx(subkey, "Publisher")[0]
                    except:
                        software["publisher"] = "未知"

                    try:
                        software["install_date"] = winreg.QueryValueEx(subkey, "InstallDate")[0]
                    except:
                        software["install_date"] = "未知"

                    try:
                        software["install_location"] = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                    except:
                        software["install_location"] = ""

                    try:
                        software["uninstall_string"] = winreg.QueryValueEx(subkey, "UninstallString")[0]
                    except:
                        software["uninstall_string"] = ""

                    # 只添加有DisplayName的软件（避免系统组件）
                    if "name" in software and software["name"] and not software["name"].startswith("{"):
                        software_list.append(software)

                    winreg.CloseKey(subkey)
                except PermissionError as pe:
                    warnings.append(f"权限不足，无法访问 {display_path}\\{subkey_name}: {pe}")
                    logger.warning(f"权限不足，无法访问注册表子键 {path}\\{subkey_name}: {pe}")
                except Exception as e:
                    warnings.append(f"读取 {display_path}\\{subkey_name} 失败: {e}")
                    logger.warning(f"读取软件信息失败: {e}")
                i += 1
            except OSError:
                # 没有更多子键
                break
            except Exception as e:
                warnings.append(f"枚举 {display_path} 子键失败: {e}")
                logger.warning(f"枚举注册表子键失败: {e}")
                break
    
    # ===== 综合功能 =====
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息
        
        Returns:
            系统信息
        """
        try:
            import platform
            
            # 基本信息
            system_info = {
                "platform": platform.system(),
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.architecture()[0],
                "hostname": socket.gethostname(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
            }
            
            # 内存信息
            if PSUTIL_AVAILABLE:
                mem = psutil.virtual_memory()
                system_info["memory_total"] = mem.total
                system_info["memory_available"] = mem.available
                system_info["memory_percent"] = mem.percent
                
                disk = psutil.disk_usage('/')
                system_info["disk_total"] = disk.total
                system_info["disk_used"] = disk.used
                system_info["disk_percent"] = disk.percent
            
            # CPU信息
            if PSUTIL_AVAILABLE:
                system_info["cpu_count"] = psutil.cpu_count()
                system_info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            
            return {
                "success": True,
                "system_info": system_info
            }
        except Exception as e:
            return {"success": False, "error": f"获取系统信息失败: {str(e)}"}
    
    def execute_powershell(self, command: str) -> Dict[str, Any]:
        """执行PowerShell命令
        
        Args:
            command: PowerShell命令
            
        Returns:
            执行结果
        """
        try:
            result = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True,
                text=True,
                shell=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "命令执行超时"}
        except Exception as e:
            return {"success": False, "error": f"执行PowerShell命令失败: {str(e)}"}


# 全局实例和辅助函数
_system_controller_instance = None


def get_system_controller() -> SystemController:
    """获取系统控制器实例"""
    global _system_controller_instance
    if _system_controller_instance is None:
        _system_controller_instance = SystemController()
    return _system_controller_instance


def test_system_controller():
    """测试系统控制器"""
    controller = get_system_controller()
    
    # 测试获取系统信息
    print("测试系统信息:")
    result = controller.get_system_info()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 测试音量控制
    print("\n测试音量控制:")
    result = controller.get_volume()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 测试网络信息
    print("\n测试网络信息:")
    result = controller.get_network_info()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 测试进程列表
    print("\n测试进程列表:")
    result = controller.list_processes()
    print(f"找到{result.get('total', 0)}个进程")
    
    # 测试窗口列表
    print("\n测试窗口列表:")
    result = controller.list_windows()
    print(f"找到{result.get('total', 0)}个窗口")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    test_system_controller()