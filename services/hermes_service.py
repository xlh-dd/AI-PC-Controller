"""
HermesService - 全能力 Hermes Agent 集成入口

Hermes 全部能力矩阵：
  基础:  chat | oneshot (-z) | session (--resume/--continue)
  技能:  skills | plugins | hooks | tools
  记忆:  memory (语义记忆/向量存储)
  联网:  browser (浏览器自动化)
  协议:  MCP servers | ACP | gateway
  任务:  cron | scheduled tasks
  数据:  import | backup | export
  调试:  doctor | dump | debug | logs
  管理:  config | setup | update | uninstall
  会话:  sessions (历史/恢复/继续)

本模块实现：
  1. 会话持久化管理 (--resume / --continue)
  2. 流式输出 (实时逐行获取)
  3. 技能注册与工具透传
  4. 记忆系统集成
  5. 浏览器能力
  6. 健康检查与断线重连
  7. 多实例并发支持
"""

import subprocess
import json
import logging
import os
import sys
import threading
import time
import tempfile
import base64
import re
from typing import Optional, Dict, Any, List, Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("HermesService")


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════════

class HermesCapability(Enum):
    """Hermes 能力枚举"""
    CHAT = "chat"
    ONESHOT = "oneshot"
    SESSION = "session"
    SKILLS = "skills"
    PLUGINS = "plugins"
    MEMORY = "memory"
    TOOLS = "tools"
    MCP = "mcp"
    BROWSER = "browser"
    CRON = "cron"
    GATEWAY = "gateway"
    ACP = "acp"
    WEBHOOK = "webhook"


@dataclass
class HermesSession:
    """Hermes 会话状态"""
    session_id: str
    name: str = ""
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    message_count: int = 0
    model: str = ""
    provider: str = ""
    context: List[Dict] = field(default_factory=list)

    def touch(self):
        self.last_active = time.time()
        self.message_count += 1

    def to_dict(self) -> Dict:
        return {
            "id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "messages": self.message_count,
        }


@dataclass
class HermesStatus:
    """Hermes 状态快照"""
    available: bool = False
    wsl_ready: bool = False
    version: str = ""
    capabilities: List[str] = field(default_factory=list)
    sessions: List[Dict] = field(default_factory=list)
    active_session: Optional[str] = None
    last_error: str = ""
    uptime_seconds: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 核心服务类
# ═══════════════════════════════════════════════════════════════════════════════

class HermesService:
    """Hermes Agent 全能力集成服务"""

    def __init__(self, config_manager=None, wsl_distro: str = "Ubuntu-22.04"):
        self.config_manager = config_manager
        self._wsl_distro = wsl_distro
        self._hermes_dir = "~/hermes-agent"
        self._venv_path = "~/hermes-agent/venv"
        self._available = False
        self._wsl_ready = False
        self._version = ""
        self._initialized = False
        self._lock = threading.RLock()
        self._start_time = 0.0

        # 会话管理
        self._sessions: Dict[str, HermesSession] = {}
        self._active_session_id: Optional[str] = None

        # 能力检测
        self._capabilities: List[HermesCapability] = []
        self._capability_cache: Dict[str, bool] = {}

        # 回调
        self._cleanup_hooks: List[Callable] = []
        self._status_callbacks: List[Callable] = []

        # 模型切换器（延迟初始化）
        self._model_switcher = None
        self._current_active_model: Optional[str] = None

        # 超时配置（渐进式）
        self._default_timeout = 180
        self._max_timeout = 600
        self._timeout_step = 120  # 每次超时递增

        # 从配置加载路径 + 超时
        if config_manager:
            self._hermes_dir = config_manager.get("hermes_install_path", self._hermes_dir)
            self._venv_path = config_manager.get("hermes_venv_path", self._venv_path)
            self._default_timeout = config_manager.get("hermes_timeout", 180)
            self._max_timeout = config_manager.get("hermes_max_timeout", 600)

    # ── 生命周期 ────────────────────────────────────────────────────────────

    def initialize(self) -> bool:
        """初始化 Hermes 服务"""
        if self._initialized:
            return self._available

        with self._lock:
            if self._initialized:
                return self._available
            self._initialized = True
            self._start_time = time.time()

        logger.info("🚀 初始化 Hermes Service...")

        # 1. 检查 WSL
        self._wsl_ready = self._probe_wsl()
        if not self._wsl_ready:
            self._wsl_ready = self._boot_wsl()

        if not self._wsl_ready:
            logger.warning("WSL 不可用")
            return False

        # 2. 检查 Hermes
        self._available, self._version = self._probe_hermes()
        if not self._available:
            logger.warning("Hermes 不可用")
            return False

        # 3. 检测可用能力
        self._detect_capabilities()

        # 4. 恢复已有会话
        self._restore_sessions()

        # 5. 初始化模型切换器
        try:
            from services.model_switcher import get_model_switcher
            self._model_switcher = get_model_switcher(
                hermes_service=self,
                config_manager=config_manager
            )
        except Exception as e:
            logger.debug(f"ModelSwitcher 初始化跳过: {e}")

        logger.info(
            f"✅ Hermes Service 就绪 "
            f"(v{self._version}, "
            f"能力: {len(self._capabilities)}, "
            f"会话: {len(self._sessions)})"
        )
        return True

    def shutdown(self):
        """关闭服务"""
        with self._lock:
            for hook in self._cleanup_hooks:
                try: hook()
                except Exception: pass
            self._cleanup_hooks.clear()
            self._available = False
            self._initialized = False
        logger.info("Hermes Service 已关闭")

    # ── WSL 探测 ─────────────────────────────────────────────────────────────

    def _probe_wsl(self, timeout: int = 5) -> bool:
        """快速探测 WSL 是否就绪"""
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-c', 'echo ok'],
                capture_output=True, timeout=timeout,
                encoding='utf-8', errors='replace'
            )
            return r.returncode == 0 and 'ok' in r.stdout
        except Exception:
            return False

    def _boot_wsl(self, max_wait: int = 30) -> bool:
        """冷启动 WSL"""
        logger.info("冷启动 WSL...")
        subprocess.Popen(
            ['wsl', '-d', self._wsl_distro, '-e', 'echo', 'boot'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(2)
            if self._probe_wsl():
                logger.info("WSL 启动完成")
                return True
        logger.error(f"WSL 启动超时 ({max_wait}s)")
        return False

    # ── Hermes 探测 ──────────────────────────────────────────────────────────

    def _probe_hermes(self) -> tuple:
        """探测 Hermes 是否可用，返回 (bool, version_str)"""
        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'test -x {hermes_bin} && {hermes_bin} --version 2>&1'],
                capture_output=True, timeout=20,
                encoding='utf-8', errors='replace'
            )
            if r.returncode == 0 and r.stdout.strip():
                return True, r.stdout.strip()
        except Exception as e:
            logger.debug(f"Hermes 探测失败: {e}")
        return False, ""

    # ── 能力检测 ─────────────────────────────────────────────────────────────

    def _detect_capabilities(self):
        """检测 Hermes 支持的能力"""
        if not self._available:
            return

        # 基础能力总是可用
        self._capabilities = [
            HermesCapability.CHAT,
            HermesCapability.ONESHOT,
            HermesCapability.SESSION,
        ]

        # 通过 hermes --help 解析子命令
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'{self._hermes_dir}/venv/bin/hermes --help 2>&1'],
                capture_output=True, timeout=10,
                encoding='utf-8', errors='replace'
            )
            help_text = r.stdout + r.stderr

            capability_map = {
                'skills': HermesCapability.SKILLS,
                'plugins': HermesCapability.PLUGINS,
                'memory': HermesCapability.MEMORY,
                'tools': HermesCapability.TOOLS,
                'mcp': HermesCapability.MCP,
                'browser': HermesCapability.BROWSER,
                'cron': HermesCapability.CRON,
                'gateway': HermesCapability.GATEWAY,
                'webhook': HermesCapability.WEBHOOK,
                'acp': HermesCapability.ACP,
            }

            for keyword, cap in capability_map.items():
                if keyword in help_text.lower():
                    self._capabilities.append(cap)
                    self._capability_cache[cap.value] = True

        except Exception as e:
            logger.debug(f"能力检测失败: {e}")

    def has_capability(self, cap: HermesCapability) -> bool:
        """检查是否支持某项能力"""
        return cap in self._capabilities

    # ── 会话管理 ─────────────────────────────────────────────────────────────

    def _restore_sessions(self):
        """恢复已有会话列表"""
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'{self._hermes_dir}/venv/bin/hermes sessions list --json 2>/dev/null || echo "[]"'],
                capture_output=True, timeout=15,
                encoding='utf-8', errors='replace'
            )
            sessions_data = json.loads(r.stdout.strip() or '[]')
            for s in sessions_data:
                sid = s.get('id', '')
                if sid:
                    self._sessions[sid] = HermesSession(
                        session_id=sid,
                        name=s.get('name', ''),
                        created_at=s.get('created_at', time.time()),
                        last_active=s.get('last_active', time.time()),
                        message_count=s.get('message_count', 0),
                    )
        except Exception as e:
            logger.debug(f"恢复会话失败: {e}")

    def new_session(self, name: str = "", model: str = None) -> HermesSession:
        """创建新会话"""
        sid = f"win_{int(time.time())}"
        session = HermesSession(
            session_id=sid,
            name=name or f"聊天_{time.strftime('%H:%M')}",
            model=model or self.config_manager.get("model", "deepseek/deepseek-v4-flash") if self.config_manager else "deepseek/deepseek-v4-flash",
        )
        with self._lock:
            self._sessions[sid] = session
            self._active_session_id = sid
        return session

    def resume_session(self, session_id: str) -> Optional[HermesSession]:
        """恢复已有会话"""
        with self._lock:
            if session_id in self._sessions:
                self._active_session_id = session_id
                self._sessions[session_id].touch()
                return self._sessions[session_id]
        return None

    def get_active_session(self) -> Optional[HermesSession]:
        """获取当前活跃会话"""
        with self._lock:
            if self._active_session_id:
                return self._sessions.get(self._active_session_id)
        return None

    def list_sessions(self) -> List[Dict]:
        """列出所有会话"""
        with self._lock:
            return [s.to_dict() for s in self._sessions.values()]

    # ── 模型切换器 ──────────────────────────────────────────────────────────

    @property
    def model_switcher(self):
        return self._model_switcher

    def get_current_model_id(self) -> str:
        """获取当前应使用的模型ID（通过切换器）"""
        if self._model_switcher:
            current = self._model_switcher.get_current()
            if current:
                return current.model_id
        return "ds-v4-flash"

    def select_model_for_task(self, prompt: str) -> Optional[str]:
        """根据任务选择模型，返回 model_id"""
        if self._model_switcher and self._model_switcher.auto_switch_enabled:
            selected = self._model_switcher.select_model(prompt)
            if selected:
                return selected.model_id
        return None

    # ── 核心接口: Oneshot 一次性问答 ──────────────────────────────────────────

    def oneshot(self, prompt: str, system_prompt: str = "",
                model: str = None, timeout: int = None,
                stream_callback: Callable[[str], None] = None) -> str:
        """一次性问答模式 (hermes -z)

        Args:
            prompt: 用户消息
            system_prompt: 系统提示
            model: 指定模型
            timeout: 超时秒数
            stream_callback: 流式回调 (可选，实时推送每行输出)
        """
        if not self.ensure_ready():
            return self._fallback_error("Hermes 不可用")

        # 构建完整 prompt
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"

        # 写入 WSL 原生临时文件（避免 9p 挂载缓存问题）
        wsl_file = self._write_wsl_tmp(full_prompt, "hermes_prompt_")
        try:
            # 自动选择模型（通过切换器）
            if not model and self._model_switcher:
                auto_model = self._model_switcher.select_model(prompt)
                if auto_model and auto_model.provider != "ollama":
                    model = auto_model.model_id
            elif not model:
                model = self.get_current_model_id()

            model_arg = f' -m "{model}"' if model else ''
            actual_timeout = timeout or self._default_timeout

            cmd = (
                f'PROMPT=$(cat "{wsl_file}"); '
                f'{hermes_bin} -z "$PROMPT"{model_arg} '
                f'--accept-hooks --ignore-rules 2>&1'
            )

            logger.info(f"📤 Hermes oneshot: {prompt[:60]}...")
            start = time.time()

            if stream_callback:
                result = self._run_streaming(cmd, stream_callback, actual_timeout)
            else:
                result = self._run_blocking(cmd, actual_timeout)

            # 记录调用结果到模型切换器
            elapsed = time.time() - start
            self._record_call_result(model or "default", result, elapsed, actual_timeout)
            return result

        finally:
            self._remove_wsl_tmp(wsl_file)

    def oneshot_with_escalation(self, prompt: str, system_prompt: str = "",
                                 stream_callback: Callable[[str], None] = None,
                                 max_retries: int = 2) -> str:
        """渐进式超时：从默认超时开始，每次超时增加 timeout_step，最多重试 max_retries 次

        遇到超时会自动尝试降级模型
        """
        if not self.ensure_ready():
            return self._fallback_error("Hermes 不可用")

        timeout = self._default_timeout

        for attempt in range(max_retries + 1):
            # 选择模型
            model = None
            if self._model_switcher:
                selected = self._model_switcher.select_model(prompt)
                if selected:
                    model = selected.model_id

            logger.info(f"📤 Hermes oneshot (尝试 {attempt+1}/{max_retries+1}, 超时={timeout}s, 模型={model or 'auto'})")

            result = self.oneshot(
                prompt, system_prompt=system_prompt,
                model=model, timeout=timeout,
                stream_callback=stream_callback
            )

            # 检查是否超时
            if result.startswith("[超时]"):
                logger.warning(f"⏰ Hermes 超时 ({timeout}s)，尝试 {attempt+1}/{max_retries+1}")

                # 尝试降级模型
                if self._model_switcher and attempt < max_retries:
                    elapsed = timeout * 1000
                    # 获取内部 model_id 以匹配 ModelSwitcher
                    current_internal = self._model_switcher.find_by_api_model_id(model) if model else self.get_current_model_id()
                    fallback, desc = self._model_switcher.handle_timeout(
                        current_internal or self.get_current_model_id(), elapsed
                    )
                    if fallback:
                        self._current_active_model = fallback.model_id
                        model = fallback.model_id  # 下次重试用降级模型

                # 增加超时时间
                timeout = min(timeout + self._timeout_step, self._max_timeout)
                continue

            # 检查是否慢响应（<timeout 但 >60s）
            if result.startswith("[错误]"):
                if self._model_switcher and attempt < max_retries:
                    current_internal = self._model_switcher.find_by_api_model_id(model) if model else self.get_current_model_id()
                    self._model_switcher.record_failure(current_internal or self.get_current_model_id())
                    fallback = self._model_switcher.get_fallback_model(current_internal or self.get_current_model_id())
                    if fallback:
                        self._current_active_model = fallback.model_id
                        model = fallback.model_id  # 下次重试用降级模型
                        continue

            return result

        return "[超时] Hermes 在所有重试后仍未响应，请检查网络或 API 状态"

    def _record_call_result(self, model_id: str, result: str, elapsed: float, timeout: int):
        """记录调用结果到模型切换器"""
        if not self._model_switcher:
            return

        # 将 API model_id 转换为内部 ID 以匹配 ModelSwitcher 统计
        internal_id = self._model_switcher.find_by_api_model_id(model_id) or model_id

        is_timeout = result.startswith("[超时]") or elapsed >= timeout * 0.95
        is_error = result.startswith("[错误]")

        latency_ms = elapsed * 1000

        if is_timeout or is_error:
            self._model_switcher.record_failure(internal_id)
            # 超时自动降级
            if is_timeout:
                self._model_switcher.handle_timeout(internal_id, latency_ms)
        else:
            self._model_switcher.record_success(internal_id, latency_ms)

    # ── 核心接口: Chat 对话模式 ──────────────────────────────────────────────

    def chat(self, message: str, system_prompt: str = "",
             stream_callback: Callable[[str], None] = None,
             timeout: int = None) -> str:
        """对话模式：自动管理会话

        首次调用创建会话，后续使用 --resume 恢复上下文
        """
        if not self.ensure_ready():
            return self._fallback_error("Hermes 不可用")

        session = self.get_active_session()
        if not session:
            session = self.new_session()

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"

        if session.message_count == 0:
            # 首次消息：使用 session 名称
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', session.name or 'chat')

            # 将 system_prompt 和消息合并
            full_msg = message
            if system_prompt:
                full_msg = f"System instruction: {system_prompt}\n\nUser: {message}"

            # 写入 WSL 原生临时文件
            wsl_file_msg = self._write_wsl_tmp(full_msg, "hermes_chat_")
            try:
                cmd = (
                    f'PROMPT=$(cat "{wsl_file_msg}"); '
                    f'{hermes_bin} -z "$PROMPT" '
                    f'--accept-hooks --ignore-rules '
                    f'--resume "{safe_name}" 2>&1'
                )

                if stream_callback:
                    result = self._run_streaming(cmd, stream_callback, timeout)
                else:
                    result = self._run_blocking(cmd, timeout)

            finally:
                self._remove_wsl_tmp(wsl_file_msg)
        else:
            # 后续消息：使用 --resume 恢复
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', session.name or 'chat')

            wsl_file_msg = self._write_wsl_tmp(message, "hermes_msg_")
            try:
                cmd = (
                    f'MSG=$(cat "{wsl_file_msg}"); '
                    f'{hermes_bin} -z "$MSG" '
                    f'--accept-hooks --ignore-rules '
                    f'--resume "{safe_name}" 2>&1'
                )

                if stream_callback:
                    result = self._run_streaming(cmd, stream_callback, timeout)
                else:
                    result = self._run_blocking(cmd, timeout)

            finally:
                self._remove_wsl_tmp(wsl_file_msg)

        session.touch()
        return result

    # ── 核心接口: Session 会话持久化 ─────────────────────────────────────────

    def continue_session(self, session_name: str, message: str = "",
                         stream_callback: Callable[[str], None] = None,
                         timeout: int = 180) -> str:
        """继续已有会话 (hermes --continue)

        不传入消息则仅仅恢复会话上下文，用于查看历史
        """
        if not self.ensure_ready():
            return self._fallback_error("Hermes 不可用")

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"

        if message:
            wsl_file_cont = self._write_wsl_tmp(message, "hermes_cont_")
            try:
                cmd = (
                    f'MSG=$(cat "{wsl_file_cont}"); '
                    f'{hermes_bin} -z "$MSG" '
                    f'--accept-hooks --ignore-rules '
                    f'--continue "{session_name}" 2>&1'
                )

                if stream_callback:
                    return self._run_streaming(cmd, stream_callback, timeout)
                else:
                    return self._run_blocking(cmd, timeout)
            finally:
                self._remove_wsl_tmp(wsl_file_cont)
        else:
            # 仅恢复会话
            cmd = (
                f'{hermes_bin} --continue "{session_name}" '
                f'--accept-hooks --ignore-rules 2>&1'
            )
            return self._run_blocking(cmd, timeout)

    # ── 核心接口: 任务执行模式 ──────────────────────────────────────────────

    def execute_task(self, task: str,
                     stream_callback: Callable[[str], None] = None,
                     timeout: int = None) -> str:
        """任务执行模式 - 向 Hermes 发送结构化任务

        与 chat 不同，execute 会使用 worktree 和 pass-session-id
        """
        if not self.ensure_ready():
            return self._fallback_error("Hermes 不可用")

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"

        wsl_file_task = self._write_wsl_tmp(task, "hermes_task_")
        try:
            cmd = (
                f'TASK=$(cat "{wsl_file_task}"); '
                f'{hermes_bin} -z "$TASK" '
                f'--accept-hooks --ignore-rules '
                f'--worktree --pass-session-id 2>&1'
            )

            if stream_callback:
                return self._run_streaming(cmd, stream_callback, timeout)
            else:
                return self._run_blocking(cmd, timeout)

        finally:
            self._remove_wsl_tmp(wsl_file_task)

    # ── 核心接口: 解析自然语言指令 ───────────────────────────────────────────

    def parse_command(self, natural_text: str) -> Dict[str, Any]:
        """用 Hermes 解析自然语言为结构化指令"""
        prompt = (
            "你是一个电脑指令解析器。解析以下用户指令为JSON。\n"
            '格式: {"action": "命令", "params": {...}}\n'
            "可用命令: open_app, search_web, manage_file, system_control, "
            "send_message, create_task, query_knowledge, execute_macro\n"
            f"用户指令: {natural_text}\n"
            "仅返回JSON:"
        )
        raw = self.oneshot(prompt)
        try:
            s = raw.find('{')
            e = raw.rfind('}')
            if s >= 0 and e > s:
                return json.loads(raw[s:e+1])
        except json.JSONDecodeError:
            pass
        return {"action": "unknown", "original": natural_text, "raw": raw}

    # ── 工具与技能透传 ──────────────────────────────────────────────────────

    def list_skills(self) -> List[Dict]:
        """列出 Hermes 可用技能"""
        if not self.has_capability(HermesCapability.SKILLS):
            return []

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'{hermes_bin} skills list --json 2>/dev/null || echo "[]"'],
                capture_output=True, timeout=15,
                encoding='utf-8', errors='replace'
            )
            return json.loads(r.stdout.strip() or '[]')
        except Exception:
            return []

    def invoke_skill(self, skill_name: str, **params) -> str:
        """调用 Hermes 技能"""
        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"
        skill_args = ' '.join(f'--{k} "{v}"' for k, v in params.items())

        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'{hermes_bin} skills {skill_name} {skill_args} '
                 f'--accept-hooks --ignore-rules 2>&1'],
                capture_output=True, timeout=60,
                encoding='utf-8', errors='replace'
            )
            return r.stdout.strip() or r.stderr.strip()
        except Exception as e:
            return f"技能调用失败: {e}"

    def list_tools(self) -> List[Dict]:
        """列出可用工具"""
        if not self.has_capability(HermesCapability.TOOLS):
            return []

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'{hermes_bin} tools list --json 2>/dev/null || echo "[]"'],
                capture_output=True, timeout=15,
                encoding='utf-8', errors='replace'
            )
            return json.loads(r.stdout.strip() or '[]')
        except Exception:
            return []

    # ── 记忆集成 ─────────────────────────────────────────────────────────────

    def query_memory(self, query: str, top_k: int = 5) -> List[Dict]:
        """查询 Hermes 语义记忆"""
        if not self.has_capability(HermesCapability.MEMORY):
            return []

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'{hermes_bin} memory search "{query}" --limit {top_k} '
                 f'--json 2>/dev/null || echo "[]"'],
                capture_output=True, timeout=15,
                encoding='utf-8', errors='replace'
            )
            return json.loads(r.stdout.strip() or '[]')
        except Exception:
            return []

    # ── 浏览器能力 ───────────────────────────────────────────────────────────

    def browse(self, url: str) -> str:
        """让 Hermes 浏览器访问指定URL"""
        if not self.has_capability(HermesCapability.BROWSER):
            return "浏览器能力不可用"

        hermes_bin = f"{self._hermes_dir}/venv/bin/hermes"
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c',
                 f'{hermes_bin} -z "请访问并分析这个网页: {url}" '
                 f'--accept-hooks --ignore-rules --yolo 2>&1'],
                capture_output=True, timeout=120,
                encoding='utf-8', errors='replace'
            )
            return r.stdout.strip()
        except Exception as e:
            return f"浏览失败: {e}"

    # ── 状态查询 ─────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        return self._available

    def ensure_ready(self) -> bool:
        """确保就绪，必要时重连"""
        if self._available:
            return True
        if not self._initialized:
            return self.initialize()
        # 尝试重新探测
        self._available, self._version = self._probe_hermes()
        return self._available

    def get_status(self) -> HermesStatus:
        """获取完整状态"""
        return HermesStatus(
            available=self._available,
            wsl_ready=self._wsl_ready,
            version=self._version,
            capabilities=[c.value for c in self._capabilities],
            sessions=self.list_sessions(),
            active_session=self._active_session_id,
            uptime_seconds=time.time() - self._start_time if self._start_time else 0,
        )

    def get_status_dict(self) -> Dict[str, Any]:
        """获取状态字典"""
        s = self.get_status()
        return {
            "available": s.available,
            "wsl_ready": s.wsl_ready,
            "version": s.version,
            "capabilities": s.capabilities,
            "sessions": len(s.sessions),
            "active_session": s.active_session,
        }

    def add_status_callback(self, cb: Callable):
        self._status_callbacks.append(cb)

    def on_cleanup(self, hook: Callable):
        self._cleanup_hooks.append(hook)

    # ── 内部辅助 ─────────────────────────────────────────────────────────────

    def _win_to_wsl_path(self, win_path: str) -> str:
        """C:\\Users\\... → /mnt/c/Users/..."""
        drive = win_path[0].lower()
        rest = win_path[2:].replace('\\', '/')
        return f"/mnt/{drive}{rest}"

    def _write_wsl_tmp(self, content: str, prefix: str = "hermes_") -> str:
        """将内容写入 WSL 原生 /tmp/ 文件系统，返回 WSL 路径。

        避免 Windows→WSL 的 9p 挂载缓存问题：文件直接在 WSL 内创建，
        不经过 /mnt/c/ 通道路由。
        """
        import hashlib
        file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
        wsl_path = f"/tmp/{prefix}{file_hash}.txt"
        # 用 base64 安全传递内容，避免 shell 转义问题
        b64 = base64.b64encode(content.encode('utf-8')).decode('ascii')
        r = subprocess.run(
            ['wsl', '-d', self._wsl_distro, 'bash', '-c',
             f'echo {b64} | base64 -d > "{wsl_path}"'],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            raise RuntimeError(f"写入 WSL 临时文件失败: {r.stderr.strip()}")
        return wsl_path

    def _remove_wsl_tmp(self, wsl_path: str):
        """清理 WSL /tmp/ 临时文件（静默失败）"""
        try:
            subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-c', f'rm -f "{wsl_path}"'],
                capture_output=True, timeout=5
            )
        except Exception:
            pass

    def _run_blocking(self, cmd: str, timeout: int) -> str:
        """阻塞执行 WSL 命令"""
        try:
            r = subprocess.run(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c', cmd],
                capture_output=True, timeout=timeout,
                encoding='utf-8', errors='replace'
            )
            elapsed = time.time() - self._start_time if self._start_time else 0
            logger.debug(f"Hermes 响应: {elapsed:.1f}s")

            if r.returncode == 0:
                return r.stdout.strip() or "(空响应)"
            else:
                err = r.stderr.strip() or f"返回码={r.returncode}"
                logger.error(f"Hermes 错误: {err[:200]}")
                return f"[错误] {err}"
        except subprocess.TimeoutExpired:
            return f"[超时] Hermes 在 {timeout}s 内未响应"
        except Exception as e:
            return f"[异常] {e}"

    def _run_streaming(self, cmd: str, callback: Callable[[str], None],
                       timeout: int) -> str:
        """流式执行 WSL 命令，逐行回调"""
        full_output = []
        try:
            proc = subprocess.Popen(
                ['wsl', '-d', self._wsl_distro, 'bash', '-l', '-c', cmd],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=0
            )

            deadline = time.time() + timeout
            for line in iter(proc.stdout.readline, ''):
                if time.time() > deadline:
                    proc.kill()
                    break
                if line:
                    full_output.append(line)
                    callback(line)
                if proc.poll() is not None:
                    break

            proc.wait(timeout=5)
            return ''.join(full_output).strip()

        except Exception as e:
            return f"[流式异常] {e}"

    def _fallback_error(self, reason: str) -> str:
        return f"[Hermes 不可用: {reason}]"


# ═══════════════════════════════════════════════════════════════════════════════
# 单例工厂
# ═══════════════════════════════════════════════════════════════════════════════

_hermes_service: Optional[HermesService] = None
_hermes_lock = threading.Lock()


def get_hermes_service(config_manager=None, wsl_distro: str = "Ubuntu-22.04") -> HermesService:
    """获取全局 HermesService 单例"""
    global _hermes_service
    if _hermes_service is None:
        with _hermes_lock:
            if _hermes_service is None:
                _hermes_service = HermesService(
                    config_manager=config_manager,
                    wsl_distro=wsl_distro
                )
    return _hermes_service


def reset_hermes_service():
    """重置服务 (测试用)"""
    global _hermes_service
    with _hermes_lock:
        if _hermes_service:
            _hermes_service.shutdown()
        _hermes_service = None
