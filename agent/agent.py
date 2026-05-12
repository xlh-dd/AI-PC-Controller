"""
Agent - 结构化Agent框架
ReAct 循环：Thought → Action → Observation → ...
把原来 75KB 的 ai_agent.py 拆成标准架构。
"""
import logging
import time
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Type
from enum import Enum
from datetime import datetime
import subprocess

logger = logging.getLogger("Agent")

# ── Skill 接口 ────────────────────────────────────────────────────────────────

class SkillResult:
    """技能执行结果"""
    def __init__(self, success: bool, output: Any = None, error: str = "",
                 observation: str = "", metadata: Dict = None):
        self.success = success
        self.output = output
        self.error = error
        self.observation = observation  # 给 Agent 看的结果摘要
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        return asdict(self)


class BaseSkill:
    """Skill 基类，所有工具技能都继承它"""
    name: str = "base"
    description: str = ""
    params_schema: Dict = {}   # {"param_name": {"type": "str", "required": True, "desc": "..."}}

    def execute(self, context: "AgentContext", **params) -> SkillResult:
        raise NotImplementedError

    def can_handle(self, action_name: str) -> bool:
        return action_name == self.name


# ── Agent 上下文 ─────────────────────────────────────────────────────────────

@dataclass
class AgentStep:
    """Agent 单步执行记录"""
    step: int
    thought: str
    action: str
    action_input: Dict
    observation: str = ""
    result: Optional[SkillResult] = None
    timestamp: datetime = field(default_factory=datetime.now)
    elapsed_ms: float = 0.0


@dataclass
class AgentContext:
    """Agent 运行时的上下文数据"""
    task: str
    max_steps: int = 10
    early_stop_keywords: List[str] = field(default_factory=lambda: [
        "完成了", "done", "任务完成", "✅", "问题已解决"
    ])
    extra: Dict = field(default_factory=dict)

    def to_history(self) -> List[Dict]:
        return []  # 子类实现


# ── 技能注册表 ────────────────────────────────────────────────────────────────

class SkillRegistry:
    """全局技能注册表"""

    _instance = None

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    @classmethod
    def get_instance(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, skill: BaseSkill):
        self._skills[skill.name] = skill
        logger.debug(f"[Agent] Registered skill: {skill.name}")

    def unregister(self, name: str):
        self._skills.pop(name, None)

    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Dict]:
        return [
            {"name": s.name, "description": s.description}
            for s in self._skills.values()
        ]

    def find_skill(self, action_name: str) -> Optional[BaseSkill]:
        """根据 action name 找技能"""
        return self._skills.get(action_name)


# ── Agent ─────────────────────────────────────────────────────────────────────

class AIAgentCore:
    """
    结构化 Agent 核心。

    使用 ReAct (Reason + Act) 循环：
      1. LLM 生成 Thought + Action + Input
      2. 执行 Action（调用 Skill）
      3. 收集 Observation
      4. 重复，直到完成或达到 max_steps
    """

    SYSTEM_PROMPT = """你是一个智能助手，正在帮助用户完成任务。

任务执行原则：
1. 先理解任务，再分解步骤
2. 每一步只做一个操作
3. 优先使用已有工具，而不是自己生成代码
4. 遇到问题先尝试解决，无效则换方案
5. 完成后给用户清晰的总结

你必须以以下 JSON 格式回复每一步（不要输出其他内容）：
{
  "thought": "你当前的想法/分析",
  "action": "要执行的技能名（如 read_file, run_command）",
  "action_input": {"param1": "value1"}
}

如果任务已完成，直接输出：
{
  "thought": "任务已完成...",
  "action": "finish",
  "action_input": {"summary": "完成情况总结"}
}
"""

    def __init__(self, ai_helper=None, model_router=None):
        self.ai_helper = ai_helper
        self.model_router = model_router
        self.registry = SkillRegistry.get_instance()
        self._stop_event = threading.Event()
        self._current_steps: List[AgentStep] = []

    # ── 核心运行 ──────────────────────────────────────────────────────────

    def run(self, task: str, context: Optional[AgentContext] = None,
            max_steps: int = 10) -> Dict[str, Any]:
        """
        运行 Agent 处理一个任务。
        返回执行结果和步骤历史。
        """
        if context is None:
            context = AgentContext(task=task, max_steps=max_steps)
        self._stop_event.clear()
        self._current_steps = []
        step = 0

        logger.info(f"[Agent] Starting task: {task[:80]}...")

        while step < context.max_steps:
            if self._stop_event.is_set():
                logger.info("[Agent] Stopped by stop event")
                break

            # 1. LLM 生成下一步指令
            llm_output = self._think(context, step)
            if not llm_output:
                break

            action_name = llm_output.get("action", "")
            action_input = llm_output.get("action_input", {})
            thought = llm_output.get("thought", "")

            # 2. 执行或结束
            if action_name == "finish":
                summary = action_input.get("summary", "任务完成")
                logger.info(f"[Agent] Task finished at step {step}")
                return {
                    "success": True,
                    "result": summary,
                    "steps": self._serialize_steps(),
                    "step_count": step,
                }

            # 执行 Skill
            skill = self.registry.find_skill(action_name)
            if not skill:
                observation = f"[错误] 未找到技能: {action_name}，可用: {list(self.registry._skills.keys())}"
                result = SkillResult(success=False, observation=observation)
            else:
                result = self._execute_skill(skill, context, action_input)

            agent_step = AgentStep(
                step=step + 1,
                thought=thought,
                action=action_name,
                action_input=action_input,
                observation=result.observation,
                result=result,
            )
            self._current_steps.append(agent_step)

            # 3. 检查提前结束
            for kw in context.early_stop_keywords:
                if kw in (result.observation or ""):
                    logger.info(f"[Agent] Early stop triggered by: {kw}")
                    return {
                        "success": True,
                        "result": result.observation,
                        "steps": self._serialize_steps(),
                        "step_count": step + 1,
                    }

            step += 1

        # 超时或达到上限
        return {
            "success": False,
            "result": f"达到最大步数 {max_steps}，任务未完成",
            "steps": self._serialize_steps(),
            "step_count": step,
        }

    def stop(self):
        self._stop_event.set()

    # ── 内部 ─────────────────────────────────────────────────────────────

    def _think(self, context: AgentContext, step: int) -> Optional[Dict]:
        """调用 LLM 生成下一步"""
        history = self._build_history(context)

        prompt = f"""当前任务：{context.task}

执行历史（最近优先）：
{history}

这是第 {step + 1} 步思考。请分析当前情况，决定下一步做什么。"""

        if self.model_router:
            # 用路由层
            from agent.model_pool import AITask, TaskType
            task_obj = AITask(
                task_type=TaskType.REASONING,
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                use_cache=False,
            )
            resp = self.model_router.chat(task_obj)
            raw = resp.content
        elif self.ai_helper:
            raw = self.ai_helper.ai_query(
                prompt,
                system_prompt=self.SYSTEM_PROMPT,
                use_memory=False,
            ) or ""
        else:
            return None

        # 尝试解析 JSON
        return self._parse_json(raw)

    def _execute_skill(self, skill: BaseSkill, context: AgentContext,
                       params: Dict) -> SkillResult:
        """执行单个 Skill"""
        t0 = time.time()
        try:
            result = skill.execute(context, **params)
            result.metadata["elapsed_ms"] = (time.time() - t0) * 1000
            return result
        except Exception as e:
            logger.error(f"[Agent] Skill {skill.name} error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                error=str(e),
                observation=f"执行出错: {e}",
            )

    def _build_history(self, context: AgentContext) -> str:
        """把执行历史拼成 prompt"""
        if not self._current_steps:
            return "(空，尚无执行历史)"
        lines = []
        for s in self._current_steps[-5:]:  # 只展示最近5步
            lines.append(f"  Step {s.step}: {s.thought}")
            lines.append(f"    → Action: {s.action}({json.dumps(s.action_input, ensure_ascii=False)[:100]})")
            if s.observation:
                lines.append(f"    Observed: {s.observation[:200]}")
        return "\n".join(lines)

    def _parse_json(self, raw: str) -> Optional[Dict]:
        """从 LLM 输出中提取 JSON"""
        import re
        raw = raw.strip()
        # 尝试直接解析
        try:
            return json.loads(raw)
        except Exception:
            pass
        # 尝试提取 ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception:
                pass
        # 尝试提取第一个 { ... }
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end+1])
            except Exception:
                pass
        logger.warning(f"[Agent] Failed to parse JSON from: {raw[:200]}")
        return None

    def _serialize_steps(self) -> List[Dict]:
        return [
            {
                "step": s.step,
                "thought": s.thought,
                "action": s.action,
                "action_input": s.action_input,
                "observation": s.observation,
                "success": s.result.success if s.result else None,
            }
            for s in self._current_steps
        ]


# ── 内置基础 Skill ───────────────────────────────────────────────────────────

class ReadFileSkill(BaseSkill):
    name = "read_file"
    description = "读取文件内容"
    params_schema = {
        "path": {"type": "str", "required": True, "desc": "文件路径"},
        "limit": {"type": "int", "required": False, "desc": "最多读多少行"},
    }

    def execute(self, context: AgentContext, **params) -> SkillResult:
        try:
            path = params["path"]
            limit = params.get("limit", 0)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read() if not limit else "\n".join(f.readlines()[:limit])
            return SkillResult(
                success=True,
                output=content,
                observation=f"读取成功，共 {len(content)} 字符",
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e), observation=f"读取失败: {e}")


class RunCommandSkill(BaseSkill):
    name = "run_command"
    description = "执行系统命令"
    params_schema = {
        "command": {"type": "str", "required": True, "desc": "要执行的命令"},
        "shell": {"type": "bool", "required": False, "desc": "是否用shell执行"},
    }

    def execute(self, context: AgentContext, **params) -> SkillResult:
        try:
            result = subprocess.run(
                params["command"],
                shell=params.get("shell", True),
                capture_output=True,
                timeout=60,
            )
            output = result.stdout.decode("utf-8", errors="replace")
            return SkillResult(
                success=result.returncode == 0,
                output=output,
                observation=f"返回码={result.returncode}，输出{len(output)}字符",
            )
        except Exception as e:
            return SkillResult(success=False, error=str(e), observation=f"执行失败: {e}")


class WriteFileSkill(BaseSkill):
    name = "write_file"
    description = "写入文件"
    params_schema = {
        "path": {"type": "str", "required": True, "desc": "文件路径"},
        "content": {"type": "str", "required": True, "desc": "文件内容"},
    }

    def execute(self, context: AgentContext, **params) -> SkillResult:
        try:
            path = params["path"]
            content = params["content"]
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return SkillResult(success=True, observation=f"写入成功: {path}")
        except Exception as e:
            return SkillResult(success=False, error=str(e), observation=f"写入失败: {e}")


class SearchSkill(BaseSkill):
    name = "search"
    description = "搜索信息（用联网搜索）"
    params_schema = {
        "query": {"type": "str", "required": True, "desc": "搜索关键词"},
        "max_results": {"type": "int", "required": False, "desc": "最大结果数"},
    }

    def execute(self, context: AgentContext, **params) -> SkillResult:
        # 复用 prosearch 脚本
        try:
            script = r"D:\AI\Qclaw\resources\openclaw\config\skills\online-search\scripts\prosearch.cjs"
            result = subprocess.run(
                ["node", script, json.dumps({"keyword": params["query"], "cnt": params.get("max_results", 5)})],
                capture_output=True, timeout=15,
            )
            output = result.stdout.decode("utf-8", errors="replace")
            try:
                data = json.loads(output)
                return SkillResult(
                    success=data.get("success", False),
                    output=data.get("data", {}),
                    observation=data.get("message", output)[:500],
                )
            except Exception:
                return SkillResult(success=False, observation=output[:500])
        except Exception as e:
            return SkillResult(success=False, error=str(e), observation=f"搜索失败: {e}")


# 注册内置 Skill
def register_builtin_skills():
    registry = SkillRegistry.get_instance()
    for skill in [ReadFileSkill(), RunCommandSkill(), WriteFileSkill(), SearchSkill()]:
        registry.register(skill)
    logger.info(f"[Agent] {len(registry.list_skills())} built-in skills registered")


def get_agent_core(ai_helper=None, model_router=None) -> AIAgentCore:
    agent = AIAgentCore(ai_helper=ai_helper, model_router=model_router)
    register_builtin_skills()
    return agent
