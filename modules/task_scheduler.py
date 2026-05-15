import threading
import time
import json
import logging
import uuid
import subprocess
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Dict, List, Any, Union

logger = logging.getLogger("TaskScheduler")

if not logger.handlers and not logging.root.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

try:
    import schedule
    SCHEDULE_AVAILABLE = True
    logger.info("schedule模块已加载，定时任务功能可用")
except ImportError:
    schedule = None
    SCHEDULE_AVAILABLE = False
    logger.warning("schedule模块未安装，定时任务功能不可用。请运行: pip install schedule")

try:
    import requests
    REQUESTS_AVAILABLE = True
    logger.info("requests模块已加载，HTTP请求功能可用")
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False
    logger.warning("requests模块未安装，HTTP请求功能不可用。请运行: pip install requests")


class TaskPriority:
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class TaskStatus:
    """任务状态"""
    PENDING = "等待执行"
    RUNNING = "正在执行"
    COMPLETED = "执行成功"
    FAILED = "执行失败"
    CANCELLED = "已取消"
    RETRYING = "重试中"
    SKIPPED = "已跳过"


class TaskType:
    """任务类型"""
    WECHAT_MESSAGE = "wechat_message"
    WEBHOOK = "webhook"
    MACRO = "macro"
    SYSTEM_COMMAND = "system_command"
    FILE_OPERATION = "file_operation"
    PYTHON_SCRIPT = "python_script"
    HTTP_REQUEST = "http_request"
    CUSTOM = "custom"


class Task:
    """任务类"""

    def __init__(self, name: str, task_type: str, **kwargs):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.task_type = task_type
        self.params = kwargs
        self.status = TaskStatus.PENDING
        self.priority = kwargs.get("priority", TaskPriority.NORMAL)
        self.retry_count = kwargs.get("retry_count", 0)
        self.retry_interval = kwargs.get("retry_interval", 60)
        self.max_retries = kwargs.get("max_retries", 3)
        self.timeout = kwargs.get("timeout", 300)
        self.dependencies = kwargs.get("dependencies", [])
        self.condition = kwargs.get("condition", None)
        self.on_success = kwargs.get("on_success", None)
        self.on_failure = kwargs.get("on_failure", None)
        self.created_at = datetime.now().isoformat()
        self.executed_at = None
        self.completed_at = None
        self.error_message = None
        self.result = None
        self.execution_history = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type,
            "params": self.params,
            "status": self.status,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "retry_interval": self.retry_interval,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "dependencies": self.dependencies,
            "condition": self.condition,
            "on_success": self.on_success,
            "on_failure": self.on_failure,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "result": self.result,
            "execution_history": self.execution_history
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        task = cls(data["name"], data["task_type"], **data.get("params", {}))
        for key, value in data.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return task


class SmartTaskScheduler:
    """智能任务调度器 - 增强版"""

    def __init__(self, save_path: Optional[str] = None):
        self.tasks: List[Dict[str, Any]] = []
        self.loop_tasks: List[Dict[str, Any]] = []
        self.task_chains: Dict[str, List[str]] = {}
        self.running_loop_threads: Dict[str, threading.Thread] = {}
        self.loop_stop_events: Dict[str, threading.Event] = {}
        self._scheduled_jobs: Dict[str, Any] = {}
        self._save_lock: threading.Lock = threading.Lock()
        self._task_lock: threading.Lock = threading.Lock()
        self._execution_history: List[Dict[str, Any]] = []
        self._stats: Dict[str, Any] = {
            "total_executed": 0,
            "successful": 0,
            "failed": 0,
            "retried": 0
        }

        self.wechat_controller = None
        self.macro_player = None
        self.command_executor = None

        self._save_path: Path = Path(save_path) if save_path else Path.home() / "aipc_data" / "tasks.json"
        self._save_path.parent.mkdir(parents=True, exist_ok=True)

        self._callback: Optional[Callable[[str, bool], None]] = None
        self._scheduler_running: bool = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_scheduler_event: threading.Event = threading.Event()

        self.load_tasks()
        self._start_scheduler_thread()

    def set_callback(self, callback: Optional[Callable[[str, bool], None]]):
        self._callback = callback

    def set_wechat_controller(self, controller):
        self.wechat_controller = controller

    def set_macro_player(self, player):
        self.macro_player = player

    def set_command_executor(self, executor: Callable):
        self.command_executor = executor

    def _notify(self, message: str, is_error: bool = False):
        if self._callback:
            try:
                self._callback(message, is_error)
            except Exception as e:
                logger.warning(f"回调通知失败: {e}")

    def start_scheduler(self):
        """启动调度器（公共方法）"""
        self._start_scheduler_thread()

    def stop_scheduler(self):
        """停止调度器（公共方法）"""
        self._stop_scheduler_thread()

    def _start_scheduler_thread(self):
        if self._scheduler_running:
            return

        self._scheduler_running = True
        self._stop_scheduler_event.clear()
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        logger.info("定时任务调度器已启动")

    def _stop_scheduler_thread(self):
        if not self._scheduler_running:
            return

        self._scheduler_running = False
        self._stop_scheduler_event.set()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=2)
        logger.info("定时任务调度器已停止")

    def _scheduler_loop(self):
        while not self._stop_scheduler_event.is_set():
            try:
                if SCHEDULE_AVAILABLE:
                    schedule.run_pending()

                    idle_seconds = schedule.idle_seconds()
                    if idle_seconds is not None and idle_seconds > 0:
                        wait_time = min(idle_seconds, 10.0)
                        self._stop_scheduler_event.wait(timeout=wait_time)
                    else:
                        self._stop_scheduler_event.wait(timeout=1)
                else:
                    self._stop_scheduler_event.wait(timeout=5.0)
            except Exception as e:
                logger.error(f"调度器执行异常: {e}")
                time.sleep(1)

    def add_task(self, name: str, task_type: str, schedule_config: Dict[str, Any],
                 params: Dict[str, Any] = None, **kwargs) -> str:
        """添加任务

        Args:
            name: 任务名称
            task_type: 任务类型
            schedule_config: 调度配置
                - type: "daily", "once", "weekly", "monthly", "interval", "cron"
                - time: "HH:MM" 或 "HH:MM:SS"
                - date: "YYYY-MM-DD" (for once)
                - weekday: 0-6 (for weekly, 0=周一)
                - day: 1-31 (for monthly)
                - interval_minutes: 间隔分钟数 (for interval)
            params: 任务参数
            **kwargs: 其他选项 (priority, retry_count, dependencies, condition, etc.)

        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())[:8]

        task = {
            "id": task_id,
            "name": name,
            "task_type": task_type,
            "schedule_config": schedule_config,
            "params": params or {},
            "status": TaskStatus.PENDING,
            "priority": kwargs.get("priority", TaskPriority.NORMAL),
            "retry_count": 0,
            "max_retries": kwargs.get("max_retries", 3),
            "retry_interval": kwargs.get("retry_interval", 60),
            "timeout": kwargs.get("timeout", 300),
            "dependencies": kwargs.get("dependencies", []),
            "condition": kwargs.get("condition", None),
            "on_success": kwargs.get("on_success", None),
            "on_failure": kwargs.get("on_failure", None),
            "created_at": datetime.now().isoformat(),
            "executed_at": None,
            "completed_at": None,
            "error_message": None,
            "result": None
        }

        for existing_task in self.tasks:
            if existing_task.get("name") == name:
                logger.warning(f"任务名称 '{name}' 已存在")

        if SCHEDULE_AVAILABLE:
            self._register_task_to_schedule(task)

        with self._task_lock:
            self.tasks.append(task)

        self.save_tasks()
        logger.info(f"添加任务: {name} (ID: {task_id}, 类型: {task_type})")
        return task_id

    def _register_task_to_schedule(self, task: Dict) -> bool:
        """将任务注册到schedule"""
        if not SCHEDULE_AVAILABLE:
            return False

        task_id = task.get("id")
        config = task.get("schedule_config", {})
        schedule_type = config.get("type", "daily")

        try:
            if schedule_type == "daily":
                time_str = config.get("time", "09:00")
                job = schedule.every().day.at(time_str).do(
                    self._execute_task_by_id, task_id
                )
                self._scheduled_jobs[task_id] = job
                logger.debug(f"注册每日任务: {task.get('name')} at {time_str}")

            elif schedule_type == "once":
                date_str = config.get("date", datetime.now().strftime("%Y-%m-%d"))
                time_str = config.get("time", "09:00")
                datetime_str = f"{date_str} {time_str}"
                target_dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")

                if target_dt > datetime.now():
                    job = schedule.every().day.at(time_str).do(
                        self._execute_task_by_id, task_id
                    )
                    self._scheduled_jobs[task_id] = job
                    logger.debug(f"注册一次性任务: {task.get('name')} at {datetime_str}")

            elif schedule_type == "weekly":
                weekday = config.get("weekday", 0)
                time_str = config.get("time", "09:00")

                weekdays = [
                    schedule.every().monday,
                    schedule.every().tuesday,
                    schedule.every().wednesday,
                    schedule.every().thursday,
                    schedule.every().friday,
                    schedule.every().saturday,
                    schedule.every().sunday
                ]

                if 0 <= weekday < 7:
                    job = weekdays[weekday].at(time_str).do(
                        self._execute_task_by_id, task_id
                    )
                    self._scheduled_jobs[task_id] = job
                    logger.debug(f"注册每周任务: {task.get('name')} 星期{weekday+1} at {time_str}")

            elif schedule_type == "interval":
                interval_minutes = config.get("interval_minutes", 60)
                job = schedule.every(interval_minutes).minutes.do(
                    self._execute_task_by_id, task_id
                )
                self._scheduled_jobs[task_id] = job
                logger.debug(f"注册间隔任务: {task.get('name')} 每{interval_minutes}分钟")

            return True

        except Exception as e:
            logger.error(f"注册任务失败: {task.get('name')}, 错误: {e}")
            return False

    def _execute_task_by_id(self, task_id: str):
        """通过ID执行任务"""
        task = self._get_task_by_id(task_id)
        if task:
            self.execute_task(task)
        else:
            logger.warning(f"找不到任务: {task_id}")

    def _get_task_by_id(self, task_id: str) -> Optional[Dict]:
        """根据ID获取任务"""
        with self._task_lock:
            for task in self.tasks:
                if task.get("id") == task_id:
                    return task
        return None

    def _remove_scheduled_job(self, task_id: str):
        """从schedule中移除任务"""
        if SCHEDULE_AVAILABLE and task_id in self._scheduled_jobs:
            try:
                schedule.cancel_job(self._scheduled_jobs[task_id])
                del self._scheduled_jobs[task_id]
            except Exception as e:
                logger.warning(f"取消schedule任务失败: {e}")

    def execute_task(self, task: Dict) -> bool:
        """执行任务"""
        task_id = task.get("id")
        task_name = task.get("name", "未命名")
        task_type = task.get("task_type")
        params = task.get("params", {})

        if not self._check_dependencies(task):
            task["status"] = TaskStatus.SKIPPED
            task["error_message"] = "依赖任务未完成"
            self._notify(f"⏭️ 任务跳过: {task_name} (依赖未满足)", False)
            return False

        if not self._check_condition(task):
            task["status"] = TaskStatus.SKIPPED
            task["error_message"] = "条件不满足"
            self._notify(f"⏭️ 任务跳过: {task_name} (条件不满足)", False)
            return False

        task["status"] = TaskStatus.RUNNING
        task["executed_at"] = datetime.now().isoformat()

        logger.info(f"开始执行任务: {task_name}")
        self._notify(f"▶️ 开始执行: {task_name}", False)

        success = False
        error_msg = None

        try:
            if task_type == TaskType.WECHAT_MESSAGE:
                success = self._execute_wechat_message(params)
            elif task_type == TaskType.WEBHOOK:
                success = self._execute_webhook(params)
            elif task_type == TaskType.MACRO:
                success = self._execute_macro(params)
            elif task_type == TaskType.SYSTEM_COMMAND:
                success = self._execute_system_command(params)
            elif task_type == TaskType.FILE_OPERATION:
                success = self._execute_file_operation(params)
            elif task_type == TaskType.PYTHON_SCRIPT:
                success = self._execute_python_script(params)
            elif task_type == TaskType.HTTP_REQUEST:
                success = self._execute_http_request(params)
            elif task_type == TaskType.CUSTOM:
                success = self._execute_custom(params)
            else:
                error_msg = f"未知任务类型: {task_type}"

        except Exception as e:
            error_msg = str(e)
            logger.error(f"任务执行异常: {task_name}, 错误: {e}")

        if success:
            task["status"] = TaskStatus.COMPLETED
            task["completed_at"] = datetime.now().isoformat()
            self._stats["successful"] += 1
            self._notify(f"✅ 任务成功: {task_name}", False)

            if task.get("on_success"):
                self._execute_callback(task.get("on_success"))
        else:
            if task.get("retry_count", 0) < task.get("max_retries", 3):
                task["retry_count"] = task.get("retry_count", 0) + 1
                task["status"] = TaskStatus.RETRYING
                self._stats["retried"] += 1
                self._notify(f"🔄 任务重试: {task_name} ({task['retry_count']}/{task['max_retries']})", False)

                retry_interval = task.get("retry_interval", 60)
                threading.Timer(retry_interval, lambda: self.execute_task(task)).start()
            else:
                task["status"] = TaskStatus.FAILED
                task["error_message"] = error_msg
                self._stats["failed"] += 1
                self._notify(f"❌ 任务失败: {task_name} - {error_msg}", True)

                if task.get("on_failure"):
                    self._execute_callback(task.get("on_failure"))

        self._stats["total_executed"] += 1
        self._record_execution(task)
        self.save_tasks()
        return success

    def _check_dependencies(self, task: Dict) -> bool:
        """检查任务依赖"""
        dependencies = task.get("dependencies", [])
        for dep_id in dependencies:
            dep_task = self._get_task_by_id(dep_id)
            if dep_task and dep_task.get("status") != TaskStatus.COMPLETED:
                return False
        return True

    def _check_condition(self, task: Dict) -> bool:
        """检查任务条件"""
        condition = task.get("condition")
        if not condition:
            return True

        cond_type = condition.get("type")
        cond_value = condition.get("value")

        if cond_type == "time_range":
            start, end = cond_value.split("-")
            now = datetime.now().time()
            start_time = datetime.strptime(start, "%H:%M").time()
            end_time = datetime.strptime(end, "%H:%M").time()
            return start_time <= now <= end_time

        elif cond_type == "weekday":
            weekdays = cond_value if isinstance(cond_value, list) else [cond_value]
            return datetime.now().weekday() in weekdays

        elif cond_type == "window_exists":
            try:
                import pygetwindow as gw
                windows = gw.getWindowsWithTitle(cond_value)
                return len(windows) > 0
            except Exception:
                return False

        elif cond_type == "file_exists":
            return os.path.exists(cond_value)

        elif cond_type == "custom":
            if self.command_executor:
                try:
                    return bool(self.command_executor(cond_value))
                except Exception:
                    return False

        return True

    def _execute_callback(self, callback_config: Dict):
        """执行回调"""
        if not callback_config:
            return

        callback_type = callback_config.get("type")
        callback_params = callback_config.get("params", {})

        if callback_type == "task":
            task_id = callback_params.get("task_id")
            if task_id:
                task = self._get_task_by_id(task_id)
                if task:
                    threading.Thread(target=self.execute_task, args=(task,), daemon=True).start()

        elif callback_type == "chain":
            chain_name = callback_params.get("chain_name")
            if chain_name:
                self.execute_chain(chain_name)

    def _execute_wechat_message(self, params: Dict) -> bool:
        """执行微信消息任务"""
        if not self.wechat_controller:
            logger.warning("微信控制器未设置")
            return False

        target = params.get("target", "文件传输助手")
        message = params.get("message", "")

        try:
            success = self.wechat_controller.send_wechat_message(target, message)
            return success
        except Exception as e:
            logger.error(f"发送微信消息失败: {e}")
            return False

    def _execute_webhook(self, params: Dict) -> bool:
        """执行Webhook任务"""
        if not REQUESTS_AVAILABLE:
            logger.error("requests模块未安装，无法执行Webhook任务。请运行: pip install requests")
            return False

        url = params.get("url")
        method = params.get("method", "POST")
        headers = params.get("headers", {})
        data = params.get("data", {})

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            else:
                response = requests.post(url, json=data, headers=headers, timeout=30)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Webhook请求失败: {e}")
            return False

    def _execute_macro(self, params: Dict) -> bool:
        """执行宏任务"""
        macro_name = params.get("macro_name")
        speed = params.get("speed", 1.0)
        repeat = params.get("repeat", 1)

        if self.macro_player:
            try:
                return self.macro_player.play(macro_name, speed=speed, repeat=repeat)
            except Exception as e:
                logger.error(f"执行宏失败: {e}")
                return False
        else:
            try:
                from modules.macro_recorder import get_player
                player = get_player()
                return player.play(macro_name, speed=speed, repeat=repeat)
            except Exception as e:
                logger.error(f"执行宏失败: {e}")
                return False

    def _execute_system_command(self, params: Dict) -> bool:
        """执行系统命令任务"""
        command = params.get("command")
        cwd = params.get("cwd")
        timeout = params.get("timeout", 60)

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"执行系统命令失败: {e}")
            return False

    def _execute_file_operation(self, params: Dict) -> bool:
        """执行文件操作任务"""
        import shutil

        operation = params.get("operation")
        source = params.get("source")
        destination = params.get("destination")

        try:
            if operation == "copy":
                if os.path.isdir(source):
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
            elif operation == "move":
                shutil.move(source, destination)
            elif operation == "delete":
                if os.path.isdir(source):
                    shutil.rmtree(source)
                else:
                    os.remove(source)
            elif operation == "mkdir":
                os.makedirs(destination, exist_ok=True)
            elif operation == "rename":
                os.rename(source, destination)
            else:
                return False
            return True
        except Exception as e:
            logger.error(f"文件操作失败: {e}")
            return False

    def _execute_python_script(self, params: Dict) -> bool:
        """执行Python脚本任务"""
        script_path = params.get("script_path")
        script_code = params.get("script_code")
        script_args = params.get("args", [])

        try:
            if script_path:
                result = subprocess.run(
                    [sys.executable, script_path] + script_args,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0
            elif script_code:
                # 安全：限制 builtins
                safe_builtins = {
                    'abs', 'all', 'any', 'bin', 'bool', 'bytearray', 'bytes',
                    'chr', 'complex', 'dict', 'divmod', 'enumerate', 'filter',
                    'float', 'format', 'frozenset', 'hasattr', 'hash', 'hex',
                    'int', 'isinstance', 'issubclass', 'iter', 'len', 'list',
                    'map', 'max', 'min', 'next', 'oct', 'ord', 'pow', 'range',
                    'repr', 'reversed', 'round', 'set', 'slice', 'sorted',
                    'str', 'sum', 'tuple', 'type', 'vars', 'zip',
                    'print', 'input', 'open', 'help',
                    'True', 'False', 'None',
                    'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
                    'ArithmeticError', 'RuntimeError', 'StopIteration',
                }
                exec_globals = {"__builtins__": {k: __builtins__[k] for k in safe_builtins if k in __builtins__}}
                exec(script_code, exec_globals)
                return True
            return False
        except Exception as e:
            logger.error(f"执行Python脚本失败: {e}")
            return False

    def _execute_http_request(self, params: Dict) -> bool:
        """执行HTTP请求任务"""
        if not REQUESTS_AVAILABLE:
            logger.error("requests模块未安装，无法执行HTTP请求任务。请运行: pip install requests")
            return False

        url = params.get("url")
        method = params.get("method", "GET")
        headers = params.get("headers", {})
        data = params.get("data")
        json_data = params.get("json")
        timeout = params.get("timeout", 30)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=data,
                json=json_data,
                timeout=timeout
            )
            return 200 <= response.status_code < 300
        except Exception as e:
            logger.error(f"HTTP请求失败: {e}")
            return False

    def _execute_custom(self, params: Dict) -> bool:
        """执行自定义任务"""
        if self.command_executor:
            try:
                return bool(self.command_executor(params))
            except Exception as e:
                logger.error(f"自定义任务执行失败: {e}")
                return False
        return False

    def _record_execution(self, task: Dict):
        """记录任务执行历史"""
        record = {
            "task_id": task.get("id"),
            "task_name": task.get("name"),
            "status": task.get("status"),
            "executed_at": task.get("executed_at"),
            "completed_at": task.get("completed_at"),
            "error_message": task.get("error_message"),
            "retry_count": task.get("retry_count", 0)
        }

        self._execution_history.append(record)

        if len(self._execution_history) > 1000:
            self._execution_history = self._execution_history[-500:]

    def create_chain(self, name: str, task_ids: List[str]):
        """创建任务链"""
        self.task_chains[name] = task_ids
        logger.info(f"创建任务链: {name}, 包含 {len(task_ids)} 个任务")

    def execute_chain(self, name: str) -> bool:
        """执行任务链"""
        if name not in self.task_chains:
            logger.warning(f"任务链不存在: {name}")
            return False

        task_ids = self.task_chains[name]
        logger.info(f"开始执行任务链: {name}")

        all_success = True
        for task_id in task_ids:
            task = self._get_task_by_id(task_id)
            if task:
                if not self.execute_task(task):
                    all_success = False
                    break
            else:
                logger.warning(f"任务链中的任务不存在: {task_id}")
                all_success = False
                break

        logger.info(f"任务链执行{'完成' if all_success else '中断'}: {name}")
        return all_success

    def add_command_task(self, name: str, command: str, send_time: str) -> str:
        """添加命令任务（兼容旧版API）

        Args:
            name: 任务名称
            command: 要执行的命令
            send_time: 执行时间 (HH:MM格式)

        Returns:
            任务ID
        """
        schedule_config = {
            "type": "once",
            "time": send_time
        }
        params = {"command": command}
        return self.add_task(name, TaskType.SYSTEM_COMMAND, schedule_config, params)

    def add_app_task(self, name: str, app_path: str, send_time: str) -> str:
        """添加应用启动任务（兼容旧版API）

        Args:
            name: 任务名称
            app_path: 应用路径
            send_time: 执行时间 (HH:MM格式)

        Returns:
            任务ID
        """
        schedule_config = {
            "type": "once",
            "time": send_time
        }
        params = {"app_path": app_path}
        return self.add_task(name, TaskType.CUSTOM, schedule_config, params)

    def add_script_task(self, name: str, script_path: str, send_time: str) -> str:
        """添加脚本执行任务（兼容旧版API）

        Args:
            name: 任务名称
            script_path: 脚本路径
            send_time: 执行时间 (HH:MM格式)

        Returns:
            任务ID
        """
        schedule_config = {
            "type": "once",
            "time": send_time
        }
        params = {"script_path": script_path}
        return self.add_task(name, TaskType.PYTHON_SCRIPT, schedule_config, params)

    def add_loop_task(self, name: str, task_type: str, interval_minutes: int,
                      params: Dict[str, Any] = None, **kwargs) -> bool:
        """添加循环任务"""
        task = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "task_type": task_type,
            "interval_minutes": interval_minutes,
            "params": params or {},
            "running": False,
            "created_at": datetime.now().isoformat(),
            **kwargs
        }

        self.loop_tasks.append(task)
        self.save_tasks()
        logger.info(f"添加循环任务: {name}, 间隔: {interval_minutes}分钟")
        return True

    def start_loop_task(self, name: str) -> bool:
        """启动循环任务"""
        for task in self.loop_tasks:
            if task.get("name") == name:
                if task.get("running"):
                    logger.warning(f"循环任务已在运行: {name}")
                    return False

                task["running"] = True
                stop_event = threading.Event()
                self.loop_stop_events[name] = stop_event

                thread = threading.Thread(
                    target=self._run_loop_task,
                    args=(task, stop_event),
                    daemon=True
                )
                thread.start()
                self.running_loop_threads[name] = thread

                self.save_tasks()
                logger.info(f"启动循环任务: {name}")
                self._notify(f"✅ 循环任务已启动: {name}")
                return True
        return False

    def stop_loop_task(self, name: str) -> bool:
        """停止循环任务"""
        for task in self.loop_tasks:
            if task.get("name") == name:
                task["running"] = False

                if name in self.loop_stop_events:
                    self.loop_stop_events[name].set()

                if name in self.running_loop_threads:
                    del self.running_loop_threads[name]
                if name in self.loop_stop_events:
                    del self.loop_stop_events[name]

                self.save_tasks()
                logger.info(f"停止循环任务: {name}")
                self._notify(f"⏹ 循环任务已停止: {name}")
                return True
        return False

    def _run_loop_task(self, task: Dict, stop_event: threading.Event):
        """运行循环任务"""
        name = task.get("name")
        interval = task.get("interval_minutes", 60)

        logger.info(f"循环任务开始: {name}, 间隔: {interval}分钟")

        try:
            while not stop_event.is_set():
                try:
                    self.execute_task(task)

                    for _ in range(interval * 60):
                        if stop_event.wait(timeout=1):
                            break
                except Exception as e:
                    logger.error(f"循环任务执行异常: {name}, 错误: {e}")
                    self._notify(f"❌ 循环任务执行失败: {name}, 错误: {e}", True)
                    break
        finally:
            task["running"] = False
            if name in self.running_loop_threads:
                del self.running_loop_threads[name]
            if name in self.loop_stop_events:
                del self.loop_stop_events[name]
            logger.info(f"循环任务结束: {name}")

    def remove_task(self, task_id: str) -> bool:
        """删除任务"""
        with self._task_lock:
            for i, task in enumerate(self.tasks):
                if task.get("id") == task_id:
                    self._remove_scheduled_job(task_id)
                    self.tasks.pop(i)
                    self.save_tasks()
                    logger.info(f"删除任务: {task_id}")
                    return True
        return False

    def get_tasks(self) -> List[Dict]:
        """获取所有任务"""
        return self.tasks

    def get_loop_tasks(self) -> List[Dict]:
        """获取所有循环任务"""
        return self.loop_tasks

    def get_execution_history(self, limit: int = 100) -> List[Dict]:
        """获取执行历史"""
        return self._execution_history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()

    def clear_finished_tasks(self, only_success: bool = True) -> int:
        """清除已完成任务"""
        original_count = len(self.tasks)

        with self._task_lock:
            if only_success:
                self.tasks = [t for t in self.tasks if t.get("status") != TaskStatus.COMPLETED]
            else:
                self.tasks = [t for t in self.tasks if t.get("status") == TaskStatus.PENDING]

        self.save_tasks()
        removed_count = original_count - len(self.tasks)
        logger.info(f"已清除 {removed_count} 个任务")
        return removed_count

    def save_tasks(self):
        """保存任务到文件"""
        with self._save_lock:
            try:
                data = {
                    "tasks": self.tasks,
                    "loop_tasks": self.loop_tasks,
                    "task_chains": self.task_chains,
                    "stats": self._stats
                }
                with open(self._save_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存任务失败: {e}")

    def load_tasks(self):
        """从文件加载任务"""
        try:
            if self._save_path.exists():
                with open(self._save_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.tasks = data.get("tasks", [])
                    self.loop_tasks = data.get("loop_tasks", [])
                    self.task_chains = data.get("task_chains", {})
                    self._stats = data.get("stats", self._stats)

                    logger.info(f"已加载 {len(self.tasks)} 个任务, {len(self.loop_tasks)} 个循环任务")

                    for task in self.loop_tasks:
                        task["running"] = False

                    for task in self.tasks:
                        if "id" not in task:
                            task["id"] = str(uuid.uuid4())[:8]

                    self._register_all_tasks_to_schedule()
        except Exception as e:
            logger.error(f"加载任务失败: {e}")
            self.tasks = []
            self.loop_tasks = []

    def _register_all_tasks_to_schedule(self):
        """重新注册所有任务到schedule"""
        if not SCHEDULE_AVAILABLE:
            return

        if hasattr(schedule, 'clear'):
            schedule.clear()
        self._scheduled_jobs.clear()

        registered_count = 0
        for task in self.tasks:
            if task.get("status") == TaskStatus.PENDING:
                if self._register_task_to_schedule(task):
                    registered_count += 1

        logger.info(f"已重新注册 {registered_count}/{len(self.tasks)} 个任务")

    def cleanup(self):
        """清理资源"""
        self._stop_scheduler_thread()

        for name in list(self.running_loop_threads.keys()):
            self.stop_loop_task(name)

        logger.info("任务调度器已清理")

    @property
    def scheduled_tasks(self):
        return self.tasks

    @scheduled_tasks.setter
    def scheduled_tasks(self, tasks):
        self.tasks = tasks
        self._register_all_tasks_to_schedule()
        self.save_tasks()


TaskScheduler = SmartTaskScheduler
