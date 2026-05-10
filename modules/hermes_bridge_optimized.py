# -*- coding: utf-8 -*-
"""
Hermes 桥接模块 - 高性能常驻进程优化版
使用后台常驻进程保持 WSL 连接，减少响应延迟
"""

import subprocess
import json
import logging
import os
import sys
import threading
import time
import queue
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

logger = logging.getLogger("HermesBridge")

class HermesProcessPool:
    """Hermes 进程池 - 保持 WSL 进程常驻"""
    
    def __init__(self, wsl_distro: str = "Ubuntu-22.04", pool_size: int = 2):
        self.wsl_distro = wsl_distro
        self.hermes_dir = "/home/xlh/hermes-agent"
        self.pool_size = pool_size
        self._processes = []
        self._available = False
        self._lock = threading.Lock()
        self._init_pool()
    
    def _init_pool(self):
        """初始化进程池"""
        try:
            for i in range(self.pool_size):
                process = self._create_process()
                if process:
                    self._processes.append({
                        'process': process,
                        'busy': False,
                        'created_at': time.time()
                    })
            self._available = len(self._processes) > 0
            logger.info(f"Hermes 进程池初始化完成: {len(self._processes)}/{self.pool_size}")
        except Exception as e:
            logger.error(f"进程池初始化失败: {e}")
            self._available = False
    
    def _create_process(self):
        """创建单个 Hermes 进程"""
        try:
            # 创建交互式 bash 进程
            cmd = [
                'wsl', '-d', self.wsl_distro, 'bash', '-l'
            ]
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1  # 行缓冲
            )
            
            # 初始化 Hermes 环境
            init_cmd = (
                f'cd {self.hermes_dir} && '
                f'source venv/bin/activate && '
                f'echo "HERMES_READY"\n'
            )
            
            process.stdin.write(init_cmd)
            process.stdin.flush()
            
            # 等待就绪信号
            start_time = time.time()
            while time.time() - start_time < 30:
                line = process.stdout.readline()
                if 'HERMES_READY' in line:
                    logger.info("Hermes 进程就绪")
                    return process
                time.sleep(0.1)
            
            # 超时，终止进程
            process.terminate()
            return None
            
        except Exception as e:
            logger.error(f"创建 Hermes 进程失败: {e}")
            return None
    
    def get_process(self):
        """获取可用进程"""
        with self._lock:
            for proc_info in self._processes:
                if not proc_info['busy']:
                    proc_info['busy'] = True
                    return proc_info
            
            # 所有进程都忙，创建临时进程
            logger.warning("所有进程忙，创建临时进程")
            process = self._create_process()
            if process:
                return {
                    'process': process,
                    'busy': True,
                    'created_at': time.time(),
                    'temp': True
                }
            return None
    
    def release_process(self, proc_info):
        """释放进程"""
        with self._lock:
            if proc_info.get('temp'):
                # 临时进程，直接终止
                try:
                    proc_info['process'].terminate()
                except:
                    pass
                return
            
            for p in self._processes:
                if p['process'] == proc_info['process']:
                    p['busy'] = False
                    break
    
    def send_message(self, message: str, timeout: int = 180) -> str:
        """发送消息到 Hermes"""
        proc_info = self.get_process()
        if not proc_info:
            return "Hermes 进程池不可用"
        
        try:
            process = proc_info['process']
            
            # 使用 base64 编码避免转义问题
            import base64
            message_b64 = base64.b64encode(message.encode('utf-8')).decode('ascii')
            
            # 发送命令
            cmd = (
                f'TASK_B64="{message_b64}"; '
                f'TASK=$(echo "$TASK_B64" | base64 -d); '
                f'hermes -z "$TASK" --accept-hooks --ignore-rules; '
                f'echo "HERMES_END_$?"\n'
            )
            
            process.stdin.write(cmd)
            process.stdin.flush()
            
            # 读取响应
            response_lines = []
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                line = process.stdout.readline()
                if not line:
                    break
                
                if 'HERMES_END_' in line:
                    # 命令结束
                    break
                
                response_lines.append(line)
            
            response = ''.join(response_lines).strip()
            return response if response else "Hermes 未返回回复"
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return f"发送消息失败: {str(e)}"
        finally:
            self.release_process(proc_info)
    
    def cleanup(self):
        """清理进程池"""
        for proc_info in self._processes:
            try:
                proc_info['process'].terminate()
            except:
                pass
        self._processes.clear()


class HermesBridgeOptimized:
    """Hermes 桥接器 - 优化版（带自动保活 + 延迟检查）"""
    
    def __init__(self, wsl_distro: str = "Ubuntu-22.04", use_pool: bool = True):
        self.wsl_distro = wsl_distro
        self.hermes_dir = "/home/xlh/hermes-agent"
        self.available = False
        self._wsl_ready = False
        self._process_pool = None
        self._use_pool = use_pool
        self._keepalive_thread = None
        self._keepalive_stop = threading.Event()
        self._checked = False
        self._check_lock = threading.Lock()
    
    def _ensure_checked(self):
        """延迟检查可用性（首次使用时调用）"""
        if self._checked:
            return
        with self._check_lock:
            if self._checked:
                return
            self._checked = True
            self._check_availability()
            
            if self.available and self._use_pool:
                self._init_process_pool()
            
            # 启动自动保活
            if self.available:
                self._start_keepalive()
    
    def _run_wsl_command(self, cmd: list, timeout: int = 5) -> subprocess.CompletedProcess:
        """运行 WSL 命令"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout
            )
            try:
                result.stdout_text = result.stdout.decode('utf-8', errors='ignore').strip()
            except:
                result.stdout_text = ""
            try:
                result.stderr_text = result.stderr.decode('utf-8', errors='ignore').strip()
            except:
                result.stderr_text = ""
            return result
        except Exception as e:
            logger.warning(f"WSL 命令失败: {e}")
            raise
    
    def _check_wsl_ready(self) -> bool:
        """检查 WSL 是否已就绪"""
        try:
            result = self._run_wsl_command(
                ["wsl", "-d", self.wsl_distro, "bash", "-c", "echo 'ready'"],
                timeout=5
            )
            return result.returncode == 0 and "ready" in result.stdout_text
        except:
            return False
    
    def _check_availability(self) -> bool:
        """检查 Hermes 是否可用"""
        try:
            self._wsl_ready = self._check_wsl_ready()
            
            if not self._wsl_ready:
                logger.info("WSL 未就绪，尝试启动...")
                subprocess.Popen(
                    ["wsl", "-d", self.wsl_distro, "-e", "echo", "wsl_started"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                for i in range(10):
                    time.sleep(2)
                    if self._check_wsl_ready():
                        self._wsl_ready = True
                        break
                
                if not self._wsl_ready:
                    logger.warning("WSL 启动超时")
                    self.available = False
                    return False
            
            result = self._run_wsl_command(
                ["wsl", "-d", self.wsl_distro, "bash", "-c", f"test -d {self.hermes_dir} && echo 'exists'"],
                timeout=10
            )
            if result.returncode != 0 or "exists" not in result.stdout_text:
                logger.warning(f"Hermes 目录不存在: {self.hermes_dir}")
                self.available = False
                return False
            
            result = self._run_wsl_command(
                ["wsl", "-d", self.wsl_distro, "bash", "-c", 
                 f"cd {self.hermes_dir} && source venv/bin/activate && python3 hermes --version"],
                timeout=20
            )
            if result.returncode == 0:
                version = result.stdout_text.strip()
                logger.info(f"Hermes 可用: {version}")
                self.available = True
                return True
            else:
                logger.warning(f"Hermes 无法运行: {result.stderr_text}")
                self.available = False
                return False
                
        except subprocess.TimeoutExpired:
            logger.warning("检查 Hermes 超时")
            self.available = True
            return True
        except Exception as e:
            logger.warning(f"检查 Hermes 可用性失败: {e}")
            self.available = False
            return False
    
    def _init_process_pool(self):
        """初始化进程池"""
        try:
            self._process_pool = HermesProcessPool(self.wsl_distro)
            if self._process_pool._available:
                logger.info("Hermes 进程池已启动")
            else:
                logger.warning("Hermes 进程池启动失败，回退到普通模式")
                self._process_pool = None
        except Exception as e:
            logger.error(f"初始化进程池失败: {e}")
            self._process_pool = None
    
    def _start_keepalive(self):
        """启动 WSL 保活线程，避免 WSL 超时休眠"""
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            return
        
        def keepalive_loop():
            while not self._keepalive_stop.is_set():
                try:
                    # 每 30 秒发送一次心跳
                    subprocess.run(
                        ['wsl', '-d', self.wsl_distro, 'bash', '-l', '-c', 'echo "heartbeat"'],
                        capture_output=True, timeout=10
                    )
                except Exception:
                    pass
                self._keepalive_stop.wait(30)
        
        self._keepalive_thread = threading.Thread(target=keepalive_loop, daemon=True)
        self._keepalive_thread.start()
        logger.info("Hermes WSL 保活线程已启动")
    
    def send_message(self, message: str, system_prompt: Optional[str] = None) -> str:
        """发送消息给 Hermes 并获取回复"""
        self._ensure_checked()
        if not self.available:
            return "Hermes 不可用，请检查 WSL 和 Hermes 安装"
        
        # 优先使用进程池
        if self._process_pool and self._process_pool._available:
            return self._process_pool.send_message(message)
        
        # 回退到普通模式
        try:
            import base64
            task_bytes = message.encode('utf-8')
            task_b64 = base64.b64encode(task_bytes).decode('ascii')
            
            cmd = (
                f'TASK_B64="{task_b64}"; '
                f'TASK=$(echo "$TASK_B64" | base64 -d); '
                f'cd {self.hermes_dir} && '
                f'source venv/bin/activate && '
                f'hermes -z "$TASK" --accept-hooks --ignore-rules'
            )
            
            logger.info(f"发送消息到 Hermes: {message[:50]}...")
            start_time = time.time()
            
            process = subprocess.Popen(
                ['wsl', '-d', self.wsl_distro, 'bash', '-l', '-c', cmd],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8'
            )
            
            try:
                stdout, stderr = process.communicate(timeout=180)
                elapsed = time.time() - start_time
                logger.info(f"Hermes 响应时间: {elapsed:.2f}秒")
                
                if process.returncode == 0 and stdout.strip():
                    return stdout.strip()
                else:
                    err = stderr.strip() or f"返回码: {process.returncode}"
                    return f"Hermes 错误: {err}"
            except subprocess.TimeoutExpired:
                process.kill()
                return "Hermes 响应超时（180秒），请稍后重试"
                
        except Exception as e:
            logger.error(f"调用 Hermes 失败: {e}")
            return f"调用 Hermes 失败: {str(e)}"
    
    def chat(self, message: str, context: list = None) -> str:
        """与 Hermes 进行对话"""
        self._ensure_checked()
        if context:
            full_prompt = ""
            for msg in context[-3:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    full_prompt += f"User: {content}\n"
                else:
                    full_prompt += f"Assistant: {content}\n"
            full_prompt += f"User: {message}\nAssistant:"
        else:
            full_prompt = message
        
        return self.send_message(full_prompt)
    
    def get_status(self) -> Dict[str, Any]:
        """获取 Hermes 状态"""
        return {
            "available": self.available,
            "wsl_ready": self._wsl_ready,
            "wsl_distro": self.wsl_distro,
            "hermes_dir": self.hermes_dir,
            "process_pool": self._process_pool is not None,
            "pool_available": self._process_pool._available if self._process_pool else False
        }
    
    def cleanup(self):
        """清理资源"""
        self._keepalive_stop.set()
        if self._process_pool:
            self._process_pool.cleanup()


class HermesAIHelperOptimized:
    """Hermes AI 辅助类 - 优化版"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.bridge = HermesBridgeOptimized()
        self.model = "hermes"
        self.ollama_url = "wsl://hermes"
        
    def generate(self, prompt: str, **kwargs) -> str:
        """生成回复"""
        self.bridge._ensure_checked()
        return self.bridge.send_message(prompt)
    
    def chat(self, message: str, context: Optional[list] = None) -> str:
        """聊天"""
        return self.bridge.chat(message, context)
    
    def is_available(self) -> bool:
        """检查是否可用"""
        self.bridge._ensure_checked()
        return self.bridge.available


# 全局实例
_hermes_bridge_optimized = None

def get_hermes_bridge_optimized() -> HermesBridgeOptimized:
    """获取全局优化版 HermesBridge 实例"""
    global _hermes_bridge_optimized
    if _hermes_bridge_optimized is None:
        _hermes_bridge_optimized = HermesBridgeOptimized()
    return _hermes_bridge_optimized


def get_hermes_ai_helper_optimized(config_manager=None) -> HermesAIHelperOptimized:
    """获取优化版 HermesAIHelper 实例"""
    return HermesAIHelperOptimized(config_manager)
