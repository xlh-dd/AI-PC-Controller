"""
LongSessionManager — 长时间会话管理器

专为长时间自动化编程设计：
  1. 会话持久化 — 保存/恢复编程上下文
  2. 断点续传 — 任务中断后自动恢复
  3. 批量任务队列 — 多任务串行/并行执行
  4. 进度追踪 — 实时进度报告
  5. 自动保存 — 定期保存工作进度
"""

import os
import time
import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger("LongSessionManager")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    CODE_GENERATE = "code_generate"
    CODE_REVIEW = "code_review"
    CODE_REFACTOR = "code_refactor"
    BATCH_PROCESS = "batch_process"
    PROJECT_SCAN = "project_scan"
    CUSTOM = "custom"


@dataclass
class Task:
    """任务定义"""
    id: str
    name: str
    task_type: TaskType
    params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 1  # 1=高, 2=中, 3=低
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: float = 0.0  # 0-100
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    depends_on: List[str] = field(default_factory=list)  # 依赖的任务ID


@dataclass
class Session:
    """编程会话"""
    id: str
    name: str
    project_path: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tasks: List[Task] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)  # 编程上下文
    notes: str = ""  # 会话笔记
    tags: List[str] = field(default_factory=list)
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0


class LongSessionManager:
    """长时间会话管理器"""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = Path(storage_dir or Path.home() / ".aipc_sessions")
        self.storage_dir.mkdir(exist_ok=True)
        
        self._sessions: Dict[str, Session] = {}
        self._current_session: Optional[str] = None
        self._task_queue: List[Task] = []
        self._queue_lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._on_progress: Optional[Callable[[str, float, str], None]] = None
        self._on_complete: Optional[Callable[[str, Any], None]] = None
        
        # 自动保存
        self._auto_save_interval = 60  # 60秒
        self._auto_save_thread: Optional[threading.Thread] = None
        
        self._load_all_sessions()
    
    # ── 会话管理 ────────────────────────────────────────────────────────
    
    def create_session(self, name: str, project_path: str, tags: List[str] = None) -> Session:
        """创建新会话"""
        session = Session(
            id=str(uuid.uuid4())[:8],
            name=name,
            project_path=project_path,
            tags=tags or []
        )
        self._sessions[session.id] = session
        self._current_session = session.id
        self._save_session(session)
        logger.info(f"✅ 创建会话: {name} ({session.id})")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        return self._sessions.get(session_id)
    
    def get_current_session(self) -> Optional[Session]:
        """获取当前会话"""
        if self._current_session:
            return self._sessions.get(self._current_session)
        return None
    
    def list_sessions(self) -> List[Dict]:
        """列出所有会话"""
        return [
            {
                "id": s.id,
                "name": s.name,
                "project": s.project_path,
                "created": datetime.fromtimestamp(s.created_at).strftime("%Y-%m-%d %H:%M"),
                "tasks": len(s.tasks),
                "progress": self._calc_session_progress(s)
            }
            for s in sorted(self._sessions.values(), key=lambda x: x.updated_at, reverse=True)
        ]
    
    def switch_session(self, session_id: str) -> bool:
        """切换会话"""
        if session_id in self._sessions:
            self._current_session = session_id
            logger.info(f"🔄 切换到会话: {self._sessions[session_id].name}")
            return True
        return False
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id in self._sessions:
            # 删除文件
            session_file = self.storage_dir / f"{session_id}.json"
            if session_file.exists():
                session_file.unlink()
            
            del self._sessions[session_id]
            if self._current_session == session_id:
                self._current_session = None
            
            logger.info(f"🗑️ 删除会话: {session_id}")
            return True
        return False
    
    def update_session_context(self, **kwargs):
        """更新当前会话上下文"""
        session = self.get_current_session()
        if session:
            session.context.update(kwargs)
            session.updated_at = time.time()
            self._save_session(session)
    
    # ── 任务队列 ────────────────────────────────────────────────────────
    
    def add_task(self, name: str, task_type: TaskType, params: Dict = None,
                 priority: int = 2, depends_on: List[str] = None) -> Task:
        """添加任务到队列"""
        task = Task(
            id=str(uuid.uuid4())[:8],
            name=name,
            task_type=task_type,
            params=params or {},
            priority=priority,
            depends_on=depends_on or []
        )
        
        with self._queue_lock:
            self._task_queue.append(task)
            # 按优先级排序
            self._task_queue.sort(key=lambda t: t.priority)
        
        # 添加到当前会话
        session = self.get_current_session()
        if session:
            session.tasks.append(task)
            session.total_tasks += 1
            session.updated_at = time.time()
            self._save_session(session)
        
        logger.info(f"➕ 添加任务: {name} ({task.id})")
        return task
    
    def start_worker(self):
        """启动工作线程"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        
        # 启动自动保存
        self._auto_save_thread = threading.Thread(target=self._auto_save_loop, daemon=True)
        self._auto_save_thread.start()
        
        logger.info("▶️ 工作线程已启动")
    
    def stop_worker(self):
        """停止工作线程"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("⏹ 工作线程已停止")
    
    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        with self._queue_lock:
            for task in self._task_queue:
                if task.id == task_id and task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.PAUSED
                    return True
        return False
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._queue_lock:
            for task in self._queue_lock:
                if task.id == task_id:
                    task.status = TaskStatus.CANCELLED
                    return True
        return False
    
    def get_queue_status(self) -> Dict:
        """获取队列状态"""
        with self._queue_lock:
            return {
                "pending": sum(1 for t in self._task_queue if t.status == TaskStatus.PENDING),
                "running": sum(1 for t in self._task_queue if t.status == TaskStatus.RUNNING),
                "completed": sum(1 for t in self._task_queue if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in self._task_queue if t.status == TaskStatus.FAILED),
                "total": len(self._task_queue)
            }
    
    def set_progress_callback(self, callback: Callable[[str, float, str], None]):
        """设置进度回调 fn(task_id, progress_pct, message)"""
        self._on_progress = callback
    
    def set_complete_callback(self, callback: Callable[[str, Any], None]):
        """设置完成回调 fn(task_id, result)"""
        self._on_complete = callback
    
    # ── 内部方法 ────────────────────────────────────────────────────────
    
    def _worker_loop(self):
        """工作线程主循环"""
        while self._running:
            task = None
            
            with self._queue_lock:
                # 找可执行的任务（依赖已满足）
                for t in self._task_queue:
                    if t.status == TaskStatus.PENDING:
                        # 检查依赖
                        deps_satisfied = all(
                            any(dt.id == dep and dt.status == TaskStatus.COMPLETED 
                                for dt in self._task_queue)
                            for dep in t.depends_on
                        )
                        if deps_satisfied:
                            task = t
                            t.status = TaskStatus.RUNNING
                            t.started_at = time.time()
                            break
            
            if task:
                self._execute_task(task)
            else:
                time.sleep(1)
    
    def _execute_task(self, task: Task):
        """执行任务"""
        try:
            logger.info(f"▶️ 执行任务: {task.name}")
            self._report_progress(task.id, 0, "开始执行...")
            
            # 根据任务类型执行
            if task.task_type == TaskType.CODE_GENERATE:
                result = self._task_code_generate(task)
            elif task.task_type == TaskType.CODE_REVIEW:
                result = self._task_code_review(task)
            elif task.task_type == TaskType.CODE_REFACTOR:
                result = self._task_code_refactor(task)
            elif task.task_type == TaskType.BATCH_PROCESS:
                result = self._task_batch_process(task)
            elif task.task_type == TaskType.PROJECT_SCAN:
                result = self._task_project_scan(task)
            else:
                result = {"status": "unknown_task_type"}
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.progress = 100.0
            
            # 更新会话统计
            session = self.get_current_session()
            if session:
                session.completed_tasks += 1
                session.updated_at = time.time()
                self._save_session(session)
            
            self._report_progress(task.id, 100, "完成")
            if self._on_complete:
                self._on_complete(task.id, result)
            
            logger.info(f"✅ 任务完成: {task.name}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            
            session = self.get_current_session()
            if session:
                session.failed_tasks += 1
            
            logger.error(f"❌ 任务失败 [{task.name}]: {e}")
            
            # 重试逻辑
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                logger.info(f"🔄 任务重试 ({task.retry_count}/{task.max_retries}): {task.name}")
    
    def _task_code_generate(self, task: Task) -> Dict:
        """代码生成任务"""
        self._report_progress(task.id, 10, "分析需求...")
        # 实际执行由外部回调处理
        return {"type": "code_generate", "params": task.params}
    
    def _task_code_review(self, task: Task) -> Dict:
        """代码审查任务"""
        self._report_progress(task.id, 10, "扫描文件...")
        return {"type": "code_review", "params": task.params}
    
    def _task_code_refactor(self, task: Task) -> Dict:
        """代码重构任务"""
        self._report_progress(task.id, 10, "分析代码结构...")
        return {"type": "code_refactor", "params": task.params}
    
    def _task_batch_process(self, task: Task) -> Dict:
        """批量处理任务"""
        self._report_progress(task.id, 10, "准备批量处理...")
        return {"type": "batch_process", "params": task.params}
    
    def _task_project_scan(self, task: Task) -> Dict:
        """项目扫描任务"""
        self._report_progress(task.id, 10, "扫描项目...")
        return {"type": "project_scan", "params": task.params}
    
    def _report_progress(self, task_id: str, progress: float, message: str):
        """报告进度"""
        if self._on_progress:
            try:
                self._on_progress(task_id, progress, message)
            except Exception as e:
                logger.error(f"进度回调异常: {e}")
    
    def _auto_save_loop(self):
        """自动保存循环"""
        while self._running:
            time.sleep(self._auto_save_interval)
            try:
                for session in self._sessions.values():
                    self._save_session(session)
            except Exception as e:
                logger.error(f"自动保存失败: {e}")
    
    # ── 持久化 ──────────────────────────────────────────────────────────
    
    def _save_session(self, session: Session):
        """保存会话到文件"""
        try:
            file_path = self.storage_dir / f"{session.id}.json"
            
            # 转换dataclass为dict
            data = asdict(session)
            # 转换枚举
            data['tasks'] = [
                {
                    **asdict(t),
                    'status': t.status.value,
                    'task_type': t.task_type.value
                }
                for t in session.tasks
            ]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存会话失败 [{session.id}]: {e}")
    
    def _load_all_sessions(self):
        """加载所有会话"""
        try:
            for file_path in self.storage_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 还原dataclass
                    session = Session(
                        id=data['id'],
                        name=data['name'],
                        project_path=data['project_path'],
                        created_at=data['created_at'],
                        updated_at=data['updated_at'],
                        context=data.get('context', {}),
                        notes=data.get('notes', ''),
                        tags=data.get('tags', []),
                        total_tasks=data.get('total_tasks', 0),
                        completed_tasks=data.get('completed_tasks', 0),
                        failed_tasks=data.get('failed_tasks', 0)
                    )
                    
                    # 还原任务
                    for t_data in data.get('tasks', []):
                        task = Task(
                            id=t_data['id'],
                            name=t_data['name'],
                            task_type=TaskType(t_data['task_type']),
                            params=t_data.get('params', {}),
                            status=TaskStatus(t_data['status']),
                            priority=t_data.get('priority', 2),
                            created_at=t_data['created_at'],
                            started_at=t_data.get('started_at'),
                            completed_at=t_data.get('completed_at'),
                            progress=t_data.get('progress', 0),
                            result=t_data.get('result'),
                            error=t_data.get('error'),
                            retry_count=t_data.get('retry_count', 0),
                            max_retries=t_data.get('max_retries', 2),
                            depends_on=t_data.get('depends_on', [])
                        )
                        session.tasks.append(task)
                        self._task_queue.append(task)
                    
                    self._sessions[session.id] = session
                    
                except Exception as e:
                    logger.error(f"加载会话失败 [{file_path}]: {e}")
            
            logger.info(f"📂 加载了 {len(self._sessions)} 个会话")
            
        except Exception as e:
            logger.error(f"加载会话目录失败: {e}")
    
    def _calc_session_progress(self, session: Session) -> float:
        """计算会话进度"""
        if not session.tasks:
            return 0.0
        completed = sum(1 for t in session.tasks if t.status == TaskStatus.COMPLETED)
        return round(completed / len(session.tasks) * 100, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════════════

_manager: Optional[LongSessionManager] = None
_manager_lock = threading.Lock()


def get_long_session_manager(storage_dir: str = None) -> LongSessionManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = LongSessionManager(storage_dir)
    return _manager
