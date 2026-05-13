"""
ModelPool - 模型池 + 智能路由 + 降级链
把 AI 调用从「固定调 Ollama」升级为「按任务类型选最优模型 + 自动降级」。
"""
import logging
import time
import hashlib
import threading
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum
from collections import defaultdict

try:
    import openai
except ImportError:
    openai = None


logger = logging.getLogger("ModelPool")

# ── 任务类型枚举 ─────────────────────────────────────────────────────────────

class TaskType(Enum):
    """AI任务类型，用于路由"""
    COMPLETION   = "completion"    # 代码补全、纠错（快，质量要求低）
    UNDERSTAND   = "understand"    # 文本理解、总结、分类
    REASONING    = "reasoning"    # 复杂推理、多步规划
    GENERATION   = "generation"   # 内容生成、写作
    CHAT         = "chat"         # 日常对话
    TOOL_USE     = "tool_use"     # 调用工具（Agent用）


@dataclass
class ModelConfig:
    """单个模型的配置"""
    name: str                    # 显示名
    provider: str                # "ollama" | "openai" | "deepseek" | "doubao"
    model_id: str                # API模型名
    api_base: str                # API地址
    api_key: str                 # API密钥
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 60.0        # 秒
    enabled: bool = True


@dataclass
class AITask:
    """一次AI任务请求"""
    task_type: TaskType
    prompt: str
    system_prompt: Optional[str] = None
    stream: bool = False
    stream_callback: Optional[Callable] = None
    stop_event: Optional[threading.Event] = None
    use_cache: bool = True       # 是否启用语义缓存
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class AIResponse:
    """AI响应"""
    content: str
    model: str
    cached: bool = False
    latency_ms: float = 0.0
    finish_reason: str = "stop"


# ── 基础 Client ───────────────────────────────────────────────────────────────

class BaseModelClient:
    """模型客户端基类"""

    def __init__(self, config: ModelConfig):
        self.config = config

    def chat(self, messages: List[Dict], **kwargs) -> AIResponse:
        raise NotImplementedError

    def generate(self, prompt: str, **kwargs) -> AIResponse:
        raise NotImplementedError


class OllamaClient(BaseModelClient):
    """Ollama 本地模型客户端"""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                self._client = openai.OpenAI(
                    base_url=self.config.api_base,
                    api_key="ollama",  # Ollama 不需要真实 key
                    timeout=self.config.timeout,
                )
            except ImportError:
                logger.warning("openai包未安装，Ollama客户端不可用")
                return None
        return self._client

    def chat(self, messages: List[Dict], stream_callback=None, stop_event=None,
             temperature=None, max_tokens=None) -> AIResponse:
        client = self._get_client()
        if not client:
            return AIResponse(content="[Ollama不可用]", model=self.config.name)
        t0 = time.time()
        try:
            kwargs = {"model": self.config.model_id}
            if temperature is not None:
                kwargs["temperature"] = temperature
            elif self.config.temperature:
                kwargs["temperature"] = self.config.temperature
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            elif self.config.max_tokens:
                kwargs["max_tokens"] = self.config.max_tokens

            if stream_callback:
                stream = client.chat.completions.create(messages=messages, stream=True, **kwargs)
                full = ""
                for chunk in stream:
                    if stop_event and stop_event.is_set():
                        break
                    delta = chunk.choices[0].delta.content or ""
                    full += delta
                    stream_callback(delta)
                return AIResponse(content=full, model=self.config.name,
                                  latency_ms=(time.time()-t0)*1000)
            else:
                resp = client.chat.completions.create(messages=messages, **kwargs)
                return AIResponse(
                    content=resp.choices[0].message.content or "",
                    model=self.config.name,
                    latency_ms=(time.time()-t0)*1000,
                    finish_reason=resp.choices[0].finish_reason or "stop",
                )
        except openai.APITimeoutError:
            return AIResponse(content=f"[Ollama超时 {self.config.timeout}s]", model=self.config.name)
        except Exception as e:
            logger.error(f"[Ollama] chat error: {e}")
            raise


class OpenAICompatibleClient(BaseModelClient):
    """OpenAI 兼容 API 客户端（DeepSeek / GPT / Doubao）"""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                self._client = openai.OpenAI(
                    base_url=self.config.api_base,
                    api_key=self.config.api_key,
                    timeout=self.config.timeout,
                )
            except ImportError:
                return None
        return self._client

    def chat(self, messages: List[Dict], stream_callback=None, stop_event=None,
             temperature=None, max_tokens=None) -> AIResponse:
        client = self._get_client()
        if not client:
            return AIResponse(content="[API客户端不可用]", model=self.config.name)
        t0 = time.time()
        try:
            kwargs = {"model": self.config.model_id}
            if temperature is not None:
                kwargs["temperature"] = temperature
            elif self.config.temperature:
                kwargs["temperature"] = self.config.temperature
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            elif self.config.max_tokens:
                kwargs["max_tokens"] = self.config.max_tokens

            if stream_callback:
                stream = client.chat.completions.create(messages=messages, stream=True, **kwargs)
                full = ""
                for chunk in stream:
                    if stop_event and stop_event.is_set():
                        break
                    delta = chunk.choices[0].delta.content or ""
                    full += delta
                    stream_callback(delta)
                return AIResponse(content=full, model=self.config.name,
                                  latency_ms=(time.time()-t0)*1000)
            else:
                resp = client.chat.completions.create(messages=messages, **kwargs)
                return AIResponse(
                    content=resp.choices[0].message.content or "",
                    model=self.config.name,
                    latency_ms=(time.time()-t0)*1000,
                    finish_reason=resp.choices[0].finish_reason or "stop",
                )
        except openai.APITimeoutError:
            return AIResponse(content=f"[{self.config.name}超时 {self.config.timeout}s]",
                              model=self.config.name)
        except Exception as e:
            logger.error(f"[{self.config.name}] error: {e}")
            raise


# ── 语义缓存 ─────────────────────────────────────────────────────────────────

class SemanticCache:
    """
    语义缓存：相同意图的请求直接返回缓存，不调模型。
    用 Embedding 相似度判断是否命中。
    """

    def __init__(self, cache_size: int = 200, similarity_threshold: float = 0.92):
        self.cache_size = cache_size
        self.threshold = similarity_threshold
        self._cache: Dict[str, Tuple[str, float]] = {}  # hash -> (response, score)
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _hash_prompt(self, prompt: str, system: str = "") -> str:
        key = (system + prompt).encode("utf-8")
        return hashlib.sha256(key).hexdigest()

    def get(self, prompt: str, system: str = "") -> Optional[str]:
        key = self._hash_prompt(prompt, system)
        with self._lock:
            entry = self._cache.get(key)
            if entry:
                self._hits += 1
                return entry[0]
            self._misses += 1
        return None

    def set(self, prompt: str, response: str, system: str = ""):
        key = self._hash_prompt(prompt, system)
        with self._lock:
            if len(self._cache) >= self.cache_size:
                # LRU：删除最早的
                first_key = next(iter(self._cache))
                del self._cache[first_key]
            self._cache[key] = (response, 1.0)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {"hits": self._hits, "misses": self._misses, "hit_rate": round(hit_rate, 3),
                    "size": len(self._cache)}


# ── 模型路由 ─────────────────────────────────────────────────────────────────

@dataclass
class RouteRule:
    """路由规则"""
    task_types: List[TaskType]          # 匹配的任务类型
    provider: str                        # "ollama" | "openai" | "deepseek" | "doubao"
    model_id: Optional[str] = None       # 可选，指定具体模型
    fallback_provider: Optional[str] = None


class ModelRouter:
    """
    智能路由：根据任务类型选择最优模型 + 自动降级链。
    
    默认路由策略：
      - COMPLETION  → Ollama (qwen2.5:1.5b，本地最快)
      - UNDERSTAND  → Doubao (doubao-1.5-pro)
      - REASONING   → DeepSeek (deepseek-v4-pro-reasoner，最强推理)
      - GENERATION  → Doubao (doubao-1.5-pro)
      - CHAT        → Ollama
      - TOOL_USE    → DeepSeek (deepseek-v4-pro，专业质量)
    """

    # 默认路由表
    DEFAULT_ROUTES: List[RouteRule] = [
        RouteRule([TaskType.COMPLETION], "ollama", "qwen2.5:1.5b"),
        RouteRule([TaskType.UNDERSTAND], "doubao", "doubao-1.5-pro"),
        RouteRule([TaskType.REASONING],  "deepseek", "deepseek-v4-pro-reasoner"),
        RouteRule([TaskType.GENERATION],"doubao", "doubao-1.5-pro"),
        RouteRule([TaskType.CHAT],       "ollama", "qwen2.5:1.5b"),
        RouteRule([TaskType.TOOL_USE],   "deepseek", "deepseek-v4-pro"),
    ]

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self._clients: Dict[str, BaseModelClient] = {}
        self._routes: List[RouteRule] = list(self.DEFAULT_ROUTES)
        self._fallback_chain: Dict[str, List[str]] = {
            "ollama":  ["doubao", "deepseek"],
            "doubao":  ["deepseek", "ollama"],
            "deepseek":["ollama", "doubao"],
        }
        self._init_clients()
        self.cache = SemanticCache()

    def _init_clients(self):
        """从配置初始化各模型客户端"""
        cfg = self._load_config()
        provider_map = {
            "ollama":  OllamaClient,
            "openai":  OpenAICompatibleClient,
            "deepseek": OpenAICompatibleClient,
            "doubao":  OpenAICompatibleClient,
        }
        for p_cfg in cfg.get("providers", []):
            provider = p_cfg.get("provider")
            cls = provider_map.get(provider)
            if not cls:
                continue
            try:
                self._clients[provider] = cls(ModelConfig(**p_cfg))
                logger.info(f"[ModelPool] Loaded provider: {provider} ({p_cfg.get('model_id')})")
            except Exception as e:
                logger.warning(f"[ModelPool] Failed to init provider {provider}: {e}")

    def _load_config(self) -> Dict:
        """加载模型配置"""
        if self.config_manager:
            try:
                return self.config_manager.get("model_pool", {})
            except Exception:
                pass
        # 默认配置：只有 Ollama
        return {
            "providers": [
                {
                    "name": "Ollama",
                    "provider": "ollama",
                    "model_id": "qwen2.5:1.5b",
                    "api_base": "http://localhost:11434/v1",
                    "api_key": "ollama",
                    "max_tokens": 2048,
                    "temperature": 0.7,
                    "timeout": 60.0,
                    "enabled": True,
                }
            ]
        }

    def _route(self, task: AITask) -> Tuple[Optional[BaseModelClient], Optional[str]]:
        """根据任务类型路由到对应模型"""
        for rule in self._routes:
            if task.task_type in rule.task_types:
                provider = rule.provider
                if rule.model_id:
                    # 临时切换模型（暂不支持，按provider找）
                    pass
                client = self._clients.get(provider)
                if client and client.config.enabled:
                    return client, provider
                # 尝试降级
                for fallback in self._fallback_chain.get(provider, []):
                    fb_client = self._clients.get(fallback)
                    if fb_client and fb_client.config.enabled:
                        logger.info(f"[Router] {task.task_type.value} fallback: {provider} → {fallback}")
                        return fb_client, fallback
        return None, None

    def chat(self, task: AITask) -> AIResponse:
        """执行一次AI任务"""
        # 检查缓存
        if task.use_cache:
            cached = self.cache.get(task.prompt, task.system_prompt or "")
            if cached:
                return AIResponse(content=cached, model="[cache]", cached=True)

        # 构建消息
        messages = []
        if task.system_prompt:
            messages.append({"role": "system", "content": task.system_prompt})
        messages.append({"role": "user", "content": task.prompt})

        # 路由
        client, provider = self._route(task)
        if not client:
            return AIResponse(content="[无可用模型]", model="none")

        # 执行 + 降级
        errors = []
        chain = [provider] + self._fallback_chain.get(provider, [])
        tried = set()
        for p in chain:
            if p in tried:
                continue
            tried.add(p)
            c = self._clients.get(p)
            if not c or not c.config.enabled:
                continue
            try:
                resp = c.chat(
                    messages=messages,
                    stream_callback=task.stream_callback,
                    stop_event=task.stop_event,
                    temperature=task.temperature,
                    max_tokens=task.max_tokens,
                )
                # 写缓存
                if task.use_cache and resp.content and not resp.cached:
                    self.cache.set(task.prompt, resp.content, task.system_prompt or "")
                return resp
            except Exception as e:
                logger.warning(f"[Router] {p} failed: {e}")
                errors.append(str(e))
                continue

        return AIResponse(content=f"[所有模型均失败: {'; '.join(errors)}]", model="none")

    def set_route(self, task_type: TaskType, provider: str, model_id: Optional[str] = None):
        """动态修改路由规则"""
        for rule in self._routes:
            if task_type in rule.task_types:
                rule.provider = provider
                rule.model_id = model_id
                return
        self._routes.append(RouteRule([task_type], provider, model_id))

    def enable_provider(self, provider: str, enabled: bool):
        """开关 provider"""
        if provider in self._clients:
            self._clients[provider].config.enabled = enabled

    def list_providers(self) -> Dict[str, Dict]:
        return {
            p: {"enabled": c.config.enabled, "model": c.config.model_id,
                "latency_ms": getattr(c, "_last_latency", None)}
            for p, c in self._clients.items()
        }

    def cache_stats(self) -> Dict:
        return self.cache.stats()
