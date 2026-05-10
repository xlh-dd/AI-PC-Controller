"""
WorkflowEngine - 工作流引擎
把 workflow_skills.py 的手工流程升级为可编程工作流。
支持：节点图、依赖声明、状态机、持久化。
"""
import logging
import time
import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum
from pathlib import Path

logger = logging.getLogger("WorkflowEngine")


class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_DEPS = "waiting_deps"


class WorkflowEvent(Enum):
    STARTED = "workflow:started"
    NODE_STARTED = "workflow:node_started"
    NODE_COMPLETED = "workflow:node_completed"
    NODE_FAILED = "workflow:node_failed"
    COMPLETED = "workflow:completed"
    FAILED = "workflow:failed"


@dataclass
class WorkflowNode:
    """工作流节点"""
    id: str
    name: str
    task_type: str                 # "action" | "delay" | "condition" | "branch"
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)  # 依赖的节点ID
    retry: int = 0                 # 重试次数
    timeout: float = 60.0          # 超时秒数
    condition: Optional[str] = None  # 条件表达式（用于 condition 节点）
    next_on_success: Optional[str] = None  # 成功后跳转
    next_on_fail: Optional[str] = None    # 失败后跳转


@dataclass
class Workflow:
    """工作流定义"""
    id: str
    name: str
    description: str = ""
    nodes: List[WorkflowNode] = field(default_factory=list)
    entry: Optional[str] = None    # 入口节点ID
    max_parallel: int = 4           # 最大并发节点数
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Workflow":
        data["nodes"] = [WorkflowNode(**n) for n in data.get("nodes", [])]
        return cls(**data)


@dataclass
class NodeResult:
    """节点执行结果"""
    node_id: str
    status: NodeStatus
    output: Any = None
    error: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    retries: int = 0

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds() * 1000
        return 0.0


class WorkflowEngine:
    """
    工作流执行引擎。

    使用方式：
        engine = WorkflowEngine(app_context)
        # 定义工作流
        wf = Workflow(id="test", name="测试", nodes=[...], entry="start")
        # 执行
        results = engine.run(wf)
    """

    def __init__(self, app_context=None, event_bus=None):
        self.app_context = app_context
        self.event_bus = event_bus
        self._running_workflows: Dict[str, "RunningWorkflow"] = {}
        self._lock = threading.Lock()
        self._builtin_actions = self._register_builtins()

    def _register_builtins(self) -> Dict[str, Callable]:
        """注册内置动作"""
        return {
            "delay": lambda params, ctx: (time.sleep(params.get("seconds", 1)), NodeStatus.SUCCESS)[1],
            "log": lambda params, ctx: (logger.info(params.get("message", "")), NodeStatus.SUCCESS)[1],
            "email_send": self._action_email_send,
            "file_copy": self._action_file_copy,
            "run_macro": self._action_run_macro,
            "notify": self._action_notify,
        }

    def _action_email_send(self, params: Dict, ctx: Any) -> NodeStatus:
        email_cls = self.app_context and self.app_context.get_or_none("email_classifier")
        if email_cls:
            try:
                email_cls.send_email(
                    to=params.get("to", ""),
                    subject=params.get("subject", ""),
                    body=params.get("body", ""),
                )
            except Exception as e:
                logger.error(f"[Workflow] email_send failed: {e}")
                return NodeStatus.FAILED
        return NodeStatus.SUCCESS

    def _action_file_copy(self, params: Dict, ctx: Any) -> NodeStatus:
        import shutil
        try:
            shutil.copy2(params["src"], params["dst"])
            return NodeStatus.SUCCESS
        except Exception as e:
            logger.error(f"[Workflow] file_copy failed: {e}")
            return NodeStatus.FAILED

    def _action_run_macro(self, params: Dict, ctx: Any) -> NodeStatus:
        try:
            from core.macro_interpreter import MacroVM
            vm = MacroVM()
            result = vm.run(params.get("script", ""))
            return NodeStatus.SUCCESS if result.type != "error" else NodeStatus.FAILED
        except Exception as e:
            logger.error(f"[Workflow] run_macro failed: {e}")
            return NodeStatus.FAILED

    def _action_notify(self, params: Dict, ctx: Any) -> NodeStatus:
        msg = params.get("message", "")
        channel = params.get("channel", "log")
        logger.info(f"[Workflow notify][{channel}] {msg}")
        return NodeStatus.SUCCESS

    # ── 执行 ─────────────────────────────────────────────────────────────

    def run(self, workflow: Workflow, context: Optional[Dict] = None) -> Dict[str, NodeResult]:
        """
        执行工作流，返回 {node_id: NodeResult}
        同步执行，阻塞直到完成。
        """
        run_id = uuid.uuid4().hex
        logger.info(f"[Workflow] Starting {workflow.name} (run={run_id})")

        running = _RunningWorkflow(
            workflow=workflow,
            run_id=run_id,
            context=context or {},
            results={},
            node_threads={},
            pending_nodes=set(),
            completed_nodes=set(),
            lock=threading.Lock(),
        )
        with self._lock:
            self._running_workflows[run_id] = running

        self._emit(WorkflowEvent.STARTED, {"run_id": run_id, "workflow_id": workflow.id})

        # 找到入口节点，开始执行
        entry_node = next((n for n in workflow.nodes if n.id == workflow.entry), None)
        if entry_node:
            self._schedule_node(running, entry_node)

        # 等待完成
        running.wait_event.wait(timeout=workflow.nodes[0].timeout * len(workflow.nodes) * 2 if workflow.nodes else 300)

        with running.lock:
            running.done = True
            running.wait_event.set()

        with self._lock:
            self._running_workflows.pop(run_id, None)

        self._emit(
            WorkflowEvent.COMPLETED if all(r.status != NodeStatus.FAILED for r in running.results.values())
            else WorkflowEvent.FAILED,
            {"run_id": run_id, "results": {k: v.status.value for k, v in running.results.items()}},
        )

        return running.results

    def stop(self, run_id: str):
        """停止工作流"""
        with self._lock:
            running = self._running_workflows.get(run_id)
        if running:
            running.stop_event.set()
            logger.info(f"[Workflow] Stopped run={run_id}")

    # ── 调度 ─────────────────────────────────────────────────────────────

    def _schedule_node(self, running: "_RunningWorkflow", node: WorkflowNode):
        """调度一个节点（满足依赖后启动）"""
        with running.lock:
            if node.id in running.completed_nodes or node.id in running.pending_nodes:
                return
            # 检查依赖
            for dep in node.depends_on:
                if dep not in running.completed_nodes:
                    return  # 依赖未完成，等待
            running.pending_nodes.add(node.id)

        t = threading.Thread(target=self._execute_node, args=(running, node), daemon=True)
        with running.lock:
            running.node_threads[node.id] = t
        t.start()

    def _execute_node(self, running: "_RunningWorkflow", node: WorkflowNode):
        """执行单个节点"""
        result = NodeResult(
            node_id=node.id,
            status=NodeStatus.RUNNING,
            started_at=datetime.now(),
            retries=0,
        )
        with running.lock:
            running.results[node.id] = result

        self._emit(WorkflowEvent.NODE_STARTED, {
            "run_id": running.run_id, "node_id": node.id, "node_name": node.name,
        })

        # 重试循环
        for attempt in range(node.retry + 1):
            try:
                status = self._do_execute(running, node)
                result.status = status
                break
            except Exception as e:
                logger.warning(f"[Workflow] Node {node.id} attempt {attempt+1} failed: {e}")
                result.retries = attempt + 1
                if attempt < node.retry:
                    time.sleep(2 ** attempt)  # 指数退避
                    continue
                result.status = NodeStatus.FAILED
                result.error = str(e)

        result.finished_at = datetime.now()

        with running.lock:
            running.completed_nodes.add(node.id)
            running.pending_nodes.discard(node.id)
            # 尝试调度等待中的节点
            for n in running.workflow.nodes:
                self._schedule_node(running, n)
            # 检查是否全部完成
            if len(running.completed_nodes) == len(running.workflow.nodes):
                running.done = True
                running.wait_event.set()

        self._emit(
            WorkflowEvent.NODE_COMPLETED if result.status == NodeStatus.SUCCESS
            else WorkflowEvent.NODE_FAILED,
            {"run_id": running.run_id, "node_id": node.id, "status": result.status.value,
             "duration_ms": result.duration_ms},
        )

    def _do_execute(self, running: "_RunningWorkflow", node: WorkflowNode) -> NodeStatus:
        """执行节点逻辑"""
        if node.task_type == "action":
            action_fn = self._builtin_actions.get(node.params.get("action", ""))
            if action_fn:
                result = action_fn(node.params.get("params", {}), running.context)
                return result
            # 尝试从 AppContext 获取
            module = self.app_context.get_or_none(node.params.get("module", ""))
            method = node.params.get("method", "")
            if module and hasattr(module, method):
                fn = getattr(module, method)
                timeout = node.timeout
                result_container = [None]
                def target():
                    result_container[0] = fn(**node.params.get("kwargs", {}))
                t = threading.Thread(target=target)
                t.start()
                t.join(timeout=timeout)
                if t.is_alive():
                    return NodeStatus.FAILED
                return NodeStatus.SUCCESS
            return NodeStatus.FAILED

        if node.task_type == "delay":
            seconds = node.params.get("seconds", 1)
            time.sleep(seconds)
            return NodeStatus.SUCCESS

        if node.task_type == "log":
            logger.info(f"[Workflow log] {node.params.get('message', '')}")
            return NodeStatus.SUCCESS

        return NodeStatus.SUCCESS

    def _emit(self, event: WorkflowEvent, data: Dict):
        if self.event_bus:
            self.event_bus.post(event.value, data, source="workflow_engine")

    # ── 工具方法 ─────────────────────────────────────────────────────────

    def save_workflow(self, workflow: Workflow, path: Optional[str] = None):
        """持久化工作流定义"""
        if path is None:
            path = str(Path.home() / "aipc_workflows" / f"{workflow.id}.json")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(workflow.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"[Workflow] Saved to {path}")

    def load_workflow(self, workflow_id: str, path: Optional[str] = None) -> Optional[Workflow]:
        """加载工作流定义"""
        if path is None:
            path = str(Path.home() / "aipc_workflows" / f"{workflow_id}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return Workflow.from_dict(json.load(f))
        except Exception as e:
            logger.error(f"[Workflow] Load failed: {e}")
            return None

    def list_workflows(self) -> List[Dict]:
        """列出所有已保存的工作流"""
        wf_dir = Path.home() / "aipc_workflows"
        wf_dir.mkdir(exist_ok=True)
        results = []
        for f in wf_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    d = json.load(fp)
                    results.append({"id": d.get("id"), "name": d.get("name"),
                                   "path": str(f), "node_count": len(d.get("nodes", []))})
            except:
                pass
        return results


class _RunningWorkflow:
    """运行时工作流实例（内部用）"""
    def __init__(self, workflow: Workflow, run_id: str, context: Dict, results: Dict,
                 node_threads: Dict, pending_nodes: Set, completed_nodes: Set, lock):
        self.workflow = workflow
        self.run_id = run_id
        self.context = context
        self.results: Dict[str, NodeResult] = results
        self.node_threads: Dict[str, threading.Thread] = node_threads
        self.pending_nodes = pending_nodes
        self.completed_nodes = completed_nodes
        self.lock = lock
        self.done = False
        self.wait_event = threading.Event()
        self.stop_event = threading.Event()
