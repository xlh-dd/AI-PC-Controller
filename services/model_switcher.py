"""
ModelSwitcher — Hermes 自助模型切换器

功能:
  1. 模型池管理（多模型注册，含价格/性能元数据）
  2. 智能路由（任务复杂度 → 最优性价比模型）
  3. 自动降级（主模型超时/失败 → 备选模型）
  4. 成本追踪（累计 token 消耗 + 预估费用）
  5. 性能监控（响应时间统计 + 成功率）

定价参考 (CNY/1M tokens, 2026 Q2):
  deepseek-v4-flash:          输入 0.5, 输出 1   (V4 Flash · 快速响应)
  deepseek-v4-flash-reasoner: 输入 2,   输出 8   (V4 Flash · 深度思考)
  deepseek-v4-pro:            输入 2,   输出 8   (V4 Pro · 通用专业)
  deepseek-v4-pro-reasoner:   输入 8,   输出 32  (V4 Pro · 最强推理)
  qwen2.5:1.5b:      免费 (本地 Ollama · 极速)
"""

import threading
import time
import logging
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from enum import Enum
from collections import defaultdict

logger = logging.getLogger("ModelSwitcher")

# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════════

class TaskComplexity(Enum):
    """任务复杂度分级"""
    TRIVIAL = 0     # 简单问答、问候
    SIMPLE = 1      # 翻译、总结、分类
    MODERATE = 2    # 代码生成、分析
    COMPLEX = 3     # 多步推理、长文生成
    HEAVY = 4       # 复杂规划、深度推理


class ModelTier(Enum):
    """模型性价比分级"""
    BUDGET = "budget"       # 最便宜 / 本地免费
    FAST = "fast"           # 极速响应（V4 Flash）
    BALANCED = "balanced"   # 性价比平衡（V4 Flash 深度）
    STANDARD = "standard"   # 专业通用（V4 Pro）
    PREMIUM = "premium"     # 最强推理（V4 Pro 深度）


@dataclass
class ModelSpec:
    """模型规格"""
    id: str                          # 模型唯一标识
    name: str                        # 显示名
    provider: str                    # "deepseek" | "ollama" | "openai" | "doubao"
    model_id: str                    # API 模型名 (如 deepseek-v4-flash)
    tier: ModelTier = ModelTier.STANDARD

    # 成本 (CNY / 1M tokens)
    price_input: float = 1.0         # 输入价格
    price_output: float = 2.0        # 输出价格

    # 性能特征
    max_tokens: int = 8192
    avg_latency_ms: float = 3000     # 平均延迟
    supports_streaming: bool = True

    # 优先级
    priority: int = 50               # 0-100，越高越优先
    enabled: bool = True

    # 统计
    total_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    success_rate: float = 1.0
    last_latency_ms: float = 0.0

    def estimated_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """预估单次调用费用"""
        return (prompt_tokens * self.price_input + completion_tokens * self.price_output) / 1_000_000

    def record_call(self, latency_ms: float, prompt_tokens: int, completion_tokens: int, success: bool):
        """记录一次调用"""
        self.total_calls += 1
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost += self.estimated_cost(prompt_tokens, completion_tokens)
        self.last_latency_ms = latency_ms
        # EMA 更新成功率
        alpha = 0.1
        self.success_rate = self.success_rate * (1 - alpha) + (1.0 if success else 0.0) * alpha


@dataclass
class SwitchDecision:
    """切换决策"""
    from_model: str
    to_model: str
    reason: str
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════════════════
# 默认模型池
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_MODELS = [
    # 本地免费 — 兜底最快
    ModelSpec(
        id="qwen2.5-1.5b",
        name="Qwen2.5 1.5B (本地)",
        provider="ollama",
        model_id="qwen2.5:1.5b",
        tier=ModelTier.BUDGET,
        price_input=0, price_output=0,
        max_tokens=2048, avg_latency_ms=500,
        priority=80,
    ),
    # V4 Flash · 快速 — 日常对话首选，极速响应
    ModelSpec(
        id="ds-v4-flash",
        name="DeepSeek V4 Flash · 快速",
        provider="deepseek",
        model_id="deepseek-v4-flash",
        tier=ModelTier.FAST,
        price_input=0.5, price_output=1.0,
        max_tokens=8192, avg_latency_ms=1200,
        priority=95,
    ),
    # V4 Flash · 深度 — 轻量推理，性价比平衡
    ModelSpec(
        id="ds-v4-flash-r",
        name="DeepSeek V4 Flash · 深度",
        provider="deepseek",
        model_id="deepseek-v4-flash-reasoner",
        tier=ModelTier.BALANCED,
        price_input=2.0, price_output=8.0,
        max_tokens=16384, avg_latency_ms=4000,
        priority=85,
    ),
    # V4 Pro · 通用 — 专业级通用对话
    ModelSpec(
        id="ds-v4-pro",
        name="DeepSeek V4 Pro · 通用",
        provider="deepseek",
        model_id="deepseek-v4-pro",
        tier=ModelTier.STANDARD,
        price_input=2.0, price_output=8.0,
        max_tokens=32768, avg_latency_ms=3000,
        priority=75,
    ),
    # V4 Pro · 推理 — 最强深度推理
    ModelSpec(
        id="ds-v4-pro-r",
        name="DeepSeek V4 Pro · 推理",
        provider="deepseek",
        model_id="deepseek-v4-pro-reasoner",
        tier=ModelTier.PREMIUM,
        price_input=8.0, price_output=32.0,
        max_tokens=65536, avg_latency_ms=10000,
        priority=60,
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 复杂度启发式
# ═══════════════════════════════════════════════════════════════════════════════

COMPLEXITY_PATTERNS = [
    # (正则, 复杂度)
    (r'(写|编写|生成|创作)一(篇|段|个|份)', TaskComplexity.COMPLEX),
    (r'(分析|推理|规划|设计|架构)', TaskComplexity.COMPLEX),
    (r'(代码|编程|debug|调试|优化|重构)', TaskComplexity.MODERATE),
    (r'(翻译|总结|概括|摘要|提取)', TaskComplexity.SIMPLE),
    (r'(你好|嗨|hello|hi|谢谢|再见|拜拜)', TaskComplexity.TRIVIAL),
    (r'(多步|逐步|step.*step|复杂|深入研究)', TaskComplexity.HEAVY),
    (r'(长篇|长文|报告|论文|手册|文档)', TaskComplexity.COMPLEX),
]


class ModelSwitcher:
    """Hermes 模型自助切换器"""

    def __init__(self, hermes_service=None, config_manager=None):
        self._hermes = hermes_service
        self._config = config_manager
        self._models: Dict[str, ModelSpec] = {}
        self._current_model_id = "ds-v4-flash"
        self._auto_switch = True
        self._switch_history: List[SwitchDecision] = []
        self._lock = threading.RLock()

        # 性能窗口 (最近N次响应时间)
        self._latency_window: Dict[str, list] = defaultdict(list)
        self._max_window_size = 20

        # 阈值
        self._timeout_threshold_ms = 180_000   # 180s 超时阈值
        self._slow_threshold_ms = 60_000       # 60s 称慢
        self._fail_threshold = 3               # 连续失败N次触发切换
        self._consecutive_failures: Dict[str, int] = defaultdict(int)

        # 加载模型池
        self._load_models()

        self._on_switch_callbacks: List[Callable] = []

    def _load_models(self):
        """加载模型池"""
        # 从配置加载自定义模型
        saved = None
        if self._config:
            try:
                saved = self._config.get("model_pool_models")
            except Exception:
                pass

        if saved:
            for m in saved:
                spec = ModelSpec(**m)
                self._models[spec.id] = spec
        else:
            for m in DEFAULT_MODELS:
                self._models[m.id] = m

        # 恢复当前模型
        if self._config:
            saved_model = self._config.get("current_hermes_model")
            if saved_model and saved_model in self._models:
                self._current_model_id = saved_model
            self._auto_switch = self._config.get("auto_switch_model", True)

    def _save_models(self):
        """保存模型配置"""
        if self._config:
            self._config.set("model_pool_models", [
                {
                    "id": m.id, "name": m.name, "provider": m.provider,
                    "model_id": m.model_id, "tier": m.tier.value,
                    "price_input": m.price_input, "price_output": m.price_output,
                    "max_tokens": m.max_tokens, "priority": m.priority,
                    "enabled": m.enabled,
                }
                for m in self._models.values()
            ])
            self._config.set("current_hermes_model", self._current_model_id)
            self._config.set("auto_switch_model", self._auto_switch)

    # ── 模型管理 ────────────────────────────────────────────────────────

    def list_models(self, enabled_only: bool = True) -> List[ModelSpec]:
        with self._lock:
            models = list(self._models.values())
            if enabled_only:
                models = [m for m in models if m.enabled]
            return sorted(models, key=lambda m: m.priority, reverse=True)

    def get_current(self) -> Optional[ModelSpec]:
        with self._lock:
            return self._models.get(self._current_model_id)

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        with self._lock:
            return self._models.get(model_id)

    def find_by_api_model_id(self, api_model_id: str) -> Optional[str]:
        """根据 API model_id (如 deepseek-v4-pro) 查找内部 ID (如 ds-v4-pro)"""
        with self._lock:
            for m in self._models.values():
                if m.model_id == api_model_id or m.model_id == f"deepseek/{api_model_id}":
                    return m.id
            return None

    def set_model(self, model_id: str) -> bool:
        with self._lock:
            if model_id not in self._models:
                return False
            old = self._current_model_id
            self._current_model_id = model_id
            self._save_models()

            decision = SwitchDecision(
                from_model=old, to_model=model_id,
                reason="手动切换"
            )
            self._switch_history.append(decision)
            self._notify_switch(decision)

            logger.info(f"🔄 模型切换: {old} → {model_id} (手动)")
            return True

    def toggle_auto_switch(self) -> bool:
        with self._lock:
            self._auto_switch = not self._auto_switch
            self._save_models()
            return self._auto_switch

    @property
    def auto_switch_enabled(self) -> bool:
        return self._auto_switch

    def enable_model(self, model_id: str, enabled: bool = True):
        with self._lock:
            if model_id in self._models:
                self._models[model_id].enabled = enabled
                self._save_models()

    # ── 复杂度评估 ──────────────────────────────────────────────────────

    def estimate_complexity(self, prompt: str) -> TaskComplexity:
        """根据用户输入估算任务复杂度"""
        import re
        prompt_lower = prompt.lower().strip()

        # 1. 长度启发式
        if len(prompt) > 2000:
            return TaskComplexity.HEAVY
        if len(prompt) > 1000:
            return TaskComplexity.COMPLEX
        if len(prompt) > 500:
            return TaskComplexity.MODERATE

        # 2. 关键词模式匹配
        for pattern, complexity in COMPLEXITY_PATTERNS:
            if re.search(pattern, prompt_lower):
                return complexity

        # 3. 默认
        if len(prompt) < 20:
            return TaskComplexity.TRIVIAL
        return TaskComplexity.SIMPLE

    # ── 智能路由 ────────────────────────────────────────────────────────

    def select_model(self, prompt: str, force_model: str = None) -> ModelSpec:
        """根据任务复杂度选择最优模型

        Returns:
            选中的 ModelSpec
        """
        with self._lock:
            # 强制指定
            if force_model and force_model in self._models:
                return self._models[force_model]

            # 手动模式 — 始终使用当前模型
            if not self._auto_switch:
                return self._models.get(self._current_model_id)

            # 自动模式 — 按复杂度路由
            complexity = self.estimate_complexity(prompt)
            enabled = [m for m in self._models.values() if m.enabled]

            if not enabled:
                return self._models.get(self._current_model_id)

            # 路由策略
            route_map = {
                TaskComplexity.TRIVIAL:  [ModelTier.BUDGET, ModelTier.FAST, ModelTier.STANDARD],
                TaskComplexity.SIMPLE:   [ModelTier.FAST, ModelTier.BALANCED, ModelTier.STANDARD],
                TaskComplexity.MODERATE: [ModelTier.BALANCED, ModelTier.STANDARD, ModelTier.PREMIUM],
                TaskComplexity.COMPLEX:  [ModelTier.STANDARD, ModelTier.PREMIUM, ModelTier.BALANCED],
                TaskComplexity.HEAVY:    [ModelTier.PREMIUM, ModelTier.STANDARD, ModelTier.BALANCED],
            }

            preferred_tiers = route_map.get(complexity, [ModelTier.STANDARD])

            for tier in preferred_tiers:
                tier_models = [m for m in enabled if m.tier == tier]
                if tier_models:
                    # 同 tier 内选 priority 最高 + 成功率最好的
                    best = max(tier_models, key=lambda m: (m.success_rate, m.priority))

                    # 如果当前模型够用就不切换（减少不必要的切换）
                    current = self._models.get(self._current_model_id)
                    if current and current.enabled and current.tier in preferred_tiers:
                        return current

                    if current and current.id != best.id:
                        logger.info(
                            f"🎯 自动路由: {current.id} → {best.id} "
                            f"(复杂度: {complexity.name}, 层级: {tier.value})"
                        )

                    return best

            return enabled[0]

    # ── 超时/失败处理 — 自动降级 ─────────────────────────────────────────

    def should_downgrade(self, model_id: str, latency_ms: float) -> bool:
        """判断是否因超时/慢响应需要降级"""
        if not self._auto_switch:
            return False

        with self._lock:
            # 更新延迟窗口
            window = self._latency_window[model_id]
            window.append(latency_ms)
            if len(window) > self._max_window_size:
                window.pop(0)

            # 更新模型统计
            model = self._models.get(model_id)
            if model:
                model.last_latency_ms = latency_ms

            # 最近3次都超时 → 降级
            if len(window) >= 3 and all(t > self._timeout_threshold_ms for t in window[-3:]):
                return True

            # 最近5次都>60s → 降级
            if len(window) >= 5 and all(t > self._slow_threshold_ms for t in window[-5:]):
                return True

            return False

    def record_failure(self, model_id: str):
        """记录模型调用失败"""
        with self._lock:
            self._consecutive_failures[model_id] += 1
            if model_id in self._models:
                self._models[model_id].record_call(0, 0, 0, False)

    def record_success(self, model_id: str, latency_ms: float,
                       prompt_tokens: int = 0, completion_tokens: int = 0):
        """记录模型调用成功"""
        with self._lock:
            self._consecutive_failures[model_id] = 0
            if model_id in self._models:
                self._models[model_id].record_call(latency_ms, prompt_tokens, completion_tokens, True)

    def get_fallback_model(self, failed_model_id: str) -> Optional[ModelSpec]:
        """获取降级模型"""
        with self._lock:
            enabled = [m for m in self._models.values() if m.enabled and m.id != failed_model_id]
            if not enabled:
                return None

            # 优先选 BUDGET（本地最快最稳定）作为降级
            budget = [m for m in enabled if m.tier == ModelTier.BUDGET]
            if budget:
                return budget[0]

            # 否则选 priority 最高
            return max(enabled, key=lambda m: (m.success_rate, m.priority))

    def handle_timeout(self, model_id: str, latency_ms: float) -> Tuple[Optional[ModelSpec], str]:
        """处理超时 — 返回降级模型

        Returns:
            (新模型, 动作描述) 或 (None, "") 表示无需切换
        """
        if not self._auto_switch:
            return None, ""

        with self._lock:
            if not self.should_downgrade(model_id, latency_ms):
                return None, ""

            fallback = self.get_fallback_model(model_id)
            if not fallback:
                return None, ""

            # 执行切换
            old = self._current_model_id
            self._current_model_id = fallback.id
            self._save_models()

            decision = SwitchDecision(
                from_model=old, to_model=fallback.id,
                reason=f"超时降级 (平均 {latency_ms/1000:.0f}s)"
            )
            self._switch_history.append(decision)
            self._notify_switch(decision)

            logger.warning(f"⚠️ 超时降级: {old} → {fallback.id} (延迟 {latency_ms/1000:.0f}s)")

            # 禁止超时模型一段时间
            if old in self._models:
                self._models[old].enabled = False
                # 60秒后自动恢复
                threading.Timer(60.0, self._reenable_model, args=[old]).start()

            return fallback, f"已自动切换至 {fallback.name}"

    def _reenable_model(self, model_id: str):
        """自动恢复被降级的模型"""
        with self._lock:
            if model_id in self._models:
                self._models[model_id].enabled = True
                logger.info(f"✅ 模型 {model_id} 已自动恢复")

    # ── 成本统计 ────────────────────────────────────────────────────────

    def get_cost_summary(self) -> Dict:
        """获取成本摘要"""
        total_cost = 0.0
        total_tokens = 0
        total_calls = 0

        model_stats = {}
        for m in self._models.values():
            total_cost += m.total_cost
            total_tokens += m.total_tokens
            total_calls += m.total_calls
            model_stats[m.id] = {
                "name": m.name,
                "tier": m.tier.value,
                "calls": m.total_calls,
                "tokens": m.total_tokens,
                "cost": round(m.total_cost, 4),
                "success_rate": round(m.success_rate * 100, 1),
                "avg_latency_ms": round(m.last_latency_ms),
            }

        return {
            "total_cost": round(total_cost, 4),
            "total_tokens": total_tokens,
            "total_calls": total_calls,
            "models": model_stats,
            "switch_count": len(self._switch_history),
            "current_model": self._current_model_id,
            "auto_switch": self._auto_switch,
        }

    # ── 回调 ────────────────────────────────────────────────────────────

    def on_switch(self, callback: Callable):
        """注册切换回调: callback(SwitchDecision)"""
        self._on_switch_callbacks.append(callback)

    def _notify_switch(self, decision: SwitchDecision):
        for cb in self._on_switch_callbacks:
            try:
                cb(decision)
            except Exception:
                pass

    # ── Hermes 模型命令构建 ─────────────────────────────────────────────

    def get_hermes_model_arg(self) -> str:
        """构建 hermes -m 参数"""
        model = self.get_current()
        if not model or model.provider == "ollama":
            return ""
        return model.model_id

    def get_current_model_display(self) -> str:
        """获取当前模型显示文本"""
        model = self.get_current()
        if not model:
            return "未知"
        auto = "🔄自动" if self._auto_switch else "🔒手动"
        return f"{model.name} ({auto})"


# ═══════════════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════════════

_switcher: Optional[ModelSwitcher] = None
_switcher_lock = threading.Lock()


def get_model_switcher(hermes_service=None, config_manager=None) -> ModelSwitcher:
    global _switcher
    if _switcher is None:
        with _switcher_lock:
            if _switcher is None:
                _switcher = ModelSwitcher(
                    hermes_service=hermes_service,
                    config_manager=config_manager,
                )
    return _switcher
