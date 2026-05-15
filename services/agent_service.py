"""
AgentService - 统一 AI 决策入口

职责:
1. 统一管理所有 AI 后端: Hermes(全能力) > Ollama(本地) > AIAgent(Core)
2. 提供 chat / execute / parse / analyze / browse 核心接口
3. 自动降级链，确保始终有可用后端
4. 流式输出透传
5. 会话持久化
"""

import logging
import re
import threading
import time
import json
from typing import Optional, Dict, Any, List, Callable
from enum import Enum

logger = logging.getLogger("AgentService")


class BackendPriority(Enum):
    HERMES_FIRST = "hermes_first"
    AGENT_FIRST = "agent_first"
    OLLAMA_ONLY = "ollama_only"
    HERMES_ONLY = "hermes_only"
    AUTO = "auto"


class AgentService:
    """统一 AI 代理服务"""

    def __init__(self):
        self._hermes = None
        self._agent_core = None
        self._model_router = None
        self._priority = BackendPriority.AUTO
        self._initialized = False
        self._lock = threading.Lock()
        self._ollama_available = False
        self._hermes_available = False
        self._config_manager = None
        # 多轮对话历史
        self.conversation_history: List[Dict[str, str]] = []
        self._system_prompt: str = ""
        self._max_history_turns: int = 20

    def initialize(self, config_manager=None) -> bool:
        if self._initialized:
            return True
        with self._lock:
            if self._initialized:
                return True

        self._config_manager = config_manager

        # 1. 初始化 Hermes
        try:
            from services.hermes_service import get_hermes_service
            self._hermes = get_hermes_service(config_manager=config_manager)
            self._hermes_available = self._hermes.initialize()
        except Exception as e:
            logger.warning(f"Hermes 初始化失败: {e}")
            self._hermes_available = False

        # 2. 检查 Ollama
        self._ollama_available = self._check_ollama()

        # 3. 初始化 ModelRouter + AIAgentCore（延迟）
        try:
            from agent.model_pool import ModelRouter
            self._model_router = ModelRouter(config_manager=config_manager)
        except Exception as e:
            logger.warning(f"ModelRouter 初始化失败: {e}")

        try:
            from agent.agent import get_agent_core
            self._agent_core = get_agent_core(model_router=self._model_router)
        except Exception as e:
            logger.warning(f"AIAgentCore 初始化失败: {e}")

        # 4. 自动选择优先级
        if self._hermes_available:
            self._priority = BackendPriority.HERMES_FIRST
        elif self._ollama_available:
            self._priority = BackendPriority.AGENT_FIRST
        else:
            self._priority = BackendPriority.OLLAMA_ONLY

        self._initialized = True
        logger.info(
            f"AgentService 就绪: Hermes={self._hermes_available}, "
            f"Ollama={self._ollama_available}, "
            f"策略={self._priority.value}"
        )
        return True

    def _check_ollama(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return len(json.loads(resp.read()).get("models", [])) > 0
        except Exception:
            return False

    def ensure_ready(self) -> bool:
        if not self._initialized:
            return self.initialize(self._config_manager)
        return True

    def set_priority(self, priority: BackendPriority):
        self._priority = priority

    @property
    def hermes(self):
        return self._hermes

    # ── 后端选择 ──────────────────────────────────────────────────────────

    def _select_backend(self) -> str:
        if self._priority == BackendPriority.HERMES_ONLY:
            return "hermes" if self._hermes_available else "none"
        if self._priority == BackendPriority.OLLAMA_ONLY:
            return "ollama"

        # AUTO / HERMES_FIRST / AGENT_FIRST
        if self._hermes_available:
            return "hermes"
        if self._agent_core is not None:
            return "agent"
        if self._ollama_available:
            return "ollama"
        return "none"

    # ── Chat 对话 ─────────────────────────────────────────────────────────

    def chat(self, message: str, system_prompt: str = "",
             stream_callback: Callable[[str], None] = None,
             timeout: int = None) -> str:
        """统一对话接口（支持流式），使用渐进式超时 + 模型切换

        注意：此方法为无状态调用，不维护对话历史。
        如需多轮对话，请使用 chat_with_history()。
        """
        self.ensure_ready()
        backend = self._select_backend()

        if backend == "hermes" and self._hermes:
            try:
                # 使用渐进式超时（oneshot_with_escalation）处理复杂查询
                actual_timeout = timeout or 180
                result = self._hermes.oneshot_with_escalation(
                    message, system_prompt=system_prompt,
                    stream_callback=stream_callback,
                    max_retries=2
                )
                # 如果不是超时/错误，直接返回
                if not result.startswith("[超时]") and not result.startswith("[错误]"):
                    return result
                # 超时后回退到普通 chat
                return self._hermes.chat(
                    message, system_prompt=system_prompt,
                    stream_callback=stream_callback, timeout=actual_timeout
                )
            except Exception as e:
                logger.error(f"Hermes chat 失败，降级: {e}")

        if backend == "agent" and self._agent_core:
            try:
                full = message
                if system_prompt:
                    full = f"{system_prompt}\n\n{message}"
                result = self._agent_core.run(full)
                answer = result.get("output", str(result))
                if stream_callback:
                    stream_callback(answer)
                return answer
            except Exception as e:
                logger.error(f"AgentCore 失败: {e}")

        # 回退 Ollama
        try:
            from modules.ai_helper import AIHelper
            helper = AIHelper(config_manager=self._config_manager)
            result = helper.generate(f"{system_prompt}\n\n{message}" if system_prompt else message)
            if stream_callback:
                stream_callback(result)
            return result
        except Exception as e:
            return f"所有 AI 服务不可用: {e}"

        return "AI 服务不可用。请检查 Hermes 或 Ollama。"

    # ── 多轮对话 ────────────────────────────────────────────────────────

    def chat_with_history(self, message: str,
                          stream_callback: Callable[[str], None] = None,
                          timeout: int = None) -> str:
        """多轮对话：自动拼接历史上下文

        DeepSeek API 无状态，每次请求需将历史传递给后端。
        AgentService 在本地维护 messages 数组实现多轮对话。
        """
        self.ensure_ready()

        # 添加用户消息到历史
        self.conversation_history.append({"role": "user", "content": message})

        # 构建带历史的完整 prompt
        full_prompt = self._format_history_prompt()

        # 调用后端
        try:
            response = self.chat(full_prompt, stream_callback=stream_callback, timeout=timeout)

            # 将 AI 回复添加到历史
            self.conversation_history.append({"role": "assistant", "content": response})

            # 限制历史轮数，避免超出上下文窗口
            self._trim_history()

            return response
        except Exception as e:
            # 失败时移除用户消息（保留历史完整性）
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                self.conversation_history.pop()
            raise

    def _format_history_prompt(self) -> str:
        """将历史消息格式化为 prompt 文本"""
        parts = []

        if self._system_prompt:
            parts.append(f"[系统指令]\n{self._system_prompt}")

        if len(self.conversation_history) > 1:  # 超过当前这条用户消息
            parts.append("[对话历史]")
            for msg in self.conversation_history[:-1]:  # 除最后一条（当前用户消息）
                role_label = "👤 用户" if msg["role"] == "user" else "🤖 AI"
                parts.append(f"{role_label}: {msg['content']}")

        # 当前消息
        current = self.conversation_history[-1]["content"] if self.conversation_history else ""
        parts.append(f"[当前消息]\n{current}")

        return "\n\n".join(parts)

    def _trim_history(self):
        """限制历史长度，保留最近 N 轮对话（每轮 = 1 user + 1 assistant）"""
        max_messages = self._max_history_turns * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []
        self._system_prompt = ""
        logger.info("🗑️ 对话历史已清空")

    def get_history(self) -> List[Dict[str, str]]:
        """获取对话历史副本"""
        return list(self.conversation_history)

    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self._system_prompt = prompt

    @property
    def history_turns(self) -> int:
        """当前对话轮数"""
        user_msgs = sum(1 for m in self.conversation_history if m["role"] == "user")
        return user_msgs

    # ── JSON 结构化输出 ──────────────────────────────────────────────

    def json_chat(self, message: str, json_schema: str = "",
                  stream_callback: Callable[[str], None] = None,
                  timeout: int = None) -> Dict[str, Any]:
        """结构化 JSON 输出（通过强 prompt 引导而非 API response_format）

        Args:
            message: 用户消息
            json_schema: JSON 格式描述

        Returns:
            解析后的 dict，或 {"error": "...", "raw": "..."}
        """
        prompt = message
        if json_schema:
            prompt = (
                f"请严格按照以下 JSON 格式输出，不要包含任何其他文字：\n"
                f"{json_schema}\n\n"
                f"用户需求：{message}"
            )

        response = self.chat(prompt, stream_callback=stream_callback, timeout=timeout)

        # 尝试解析 JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            # 尝试找 { 到 } 的最长匹配
            start = response.find('{')
            end = response.rfind('}')
            if start >= 0 and end > start:
                try:
                    return json.loads(response[start:end+1])
                except json.JSONDecodeError:
                    pass
            return {"error": "JSON 解析失败", "raw": response}

    # ── Execute 任务执行 ──────────────────────────────────────────────────

    def execute(self, task: str,
                stream_callback: Callable[[str], None] = None,
                timeout: int = None) -> Dict[str, Any]:
        """执行 AI 任务"""
        self.ensure_ready()
        backend = self._select_backend()

        if backend == "hermes":
            try:
                result = self._hermes.execute_task(
                    task, stream_callback=stream_callback, timeout=timeout
                )
                return {"success": True, "output": result, "backend": "hermes"}
            except Exception as e:
                logger.error(f"Hermes 执行失败: {e}")

        if backend == "agent" and self._agent_core:
            try:
                return self._agent_core.run(task)
            except Exception as e:
                return {"success": False, "error": str(e), "backend": "agent"}

        try:
            from modules.ai_helper import AIHelper
            helper = AIHelper(config_manager=self._config_manager)
            return {"success": True, "output": helper.generate(task), "backend": "ollama"}
        except Exception as e:
            return {"success": False, "error": str(e), "backend": "none"}

    # ── 指令解析 ──────────────────────────────────────────────────────────

    def parse_command(self, natural_text: str) -> Dict[str, Any]:
        self.ensure_ready()

        if self._hermes_available:
            try:
                return self._hermes.parse_command(natural_text)
            except Exception:
                pass

        if self._agent_core:
            try:
                result = self._agent_core.run(
                    f"将以下用户指令解析为命令JSON: {natural_text}"
                )
                output = result.get("output", "")
                s = output.find('{')
                e = output.rfind('}')
                if s >= 0 and e > s:
                    return json.loads(output[s:e+1])
            except Exception:
                pass

        return self._local_parse(natural_text)

    def _local_parse(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower().strip()

        if any(kw in text_lower for kw in ["关机", "shutdown"]):
            m = re.search(r'(\d+)\s*分', text)
            return {"action": "shutdown", "delay": int(m.group(1)) if m else 0}
        if any(kw in text_lower for kw in ["重启", "restart"]):
            return {"action": "restart"}

        open_match = re.match(r'^(打开|启动|运行|open)\s*(.+)', text, re.IGNORECASE)
        if open_match:
            return {"action": "open_app", "app_name": open_match.group(2).strip()}

        return {"action": "unknown", "original": text}

    # ── 分析 ──────────────────────────────────────────────────────────────

    def analyze(self, prompt: str, data: Any = None) -> str:
        full = prompt
        if data:
            full = f"{prompt}\n\n数据:\n{str(data)[:3000]}"
        return self.chat(full)

    # ── 浏览器 ────────────────────────────────────────────────────────────

    def browse(self, url: str) -> str:
        self.ensure_ready()
        if self._hermes_available:
            return self._hermes.browse(url)
        return "浏览器功能需要 Hermes 支持"

    # ── 记忆查询 ──────────────────────────────────────────────────────────

    def query_memory(self, query: str, top_k: int = 5) -> List[Dict]:
        self.ensure_ready()
        if self._hermes_available:
            return self._hermes.query_memory(query, top_k)
        return []

    # ── 技能列表 ──────────────────────────────────────────────────────────

    def list_skills(self) -> List[Dict]:
        self.ensure_ready()
        if self._hermes_available:
            return self._hermes.list_skills()
        return []

    # ── 会话管理 ──────────────────────────────────────────────────────────

    def new_session(self, name: str = ""):
        if self._hermes_available:
            return self._hermes.new_session(name)
        return None

    def resume_session(self, session_id: str):
        if self._hermes_available:
            return self._hermes.resume_session(session_id)
        return None

    def list_sessions(self) -> List[Dict]:
        if self._hermes_available:
            return self._hermes.list_sessions()
        return []

    # ── 状态 ──────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        status = {
            "initialized": self._initialized,
            "priority": self._priority.value,
            "hermes": self._hermes_available,
            "ollama": self._ollama_available,
            "agent_core": self._agent_core is not None,
            "model_router": self._model_router is not None,
        }
        if self._hermes:
            status["hermes_detail"] = self._hermes.get_status_dict()
        return status

    def get_preferred_backend(self) -> str:
        return self._select_backend()

    def shutdown(self):
        if self._hermes:
            self._hermes.shutdown()
        self._initialized = False
        logger.info("AgentService 已关闭")


_agent_service: Optional[AgentService] = None
_agent_lock = threading.Lock()


def get_agent_service(config_manager=None) -> AgentService:
    global _agent_service
    if _agent_service is None:
        with _agent_lock:
            if _agent_service is None:
                _agent_service = AgentService()
                if config_manager:
                    _agent_service.initialize(config_manager)
    elif config_manager and not _agent_service._initialized:
        _agent_service.initialize(config_manager)
    return _agent_service
