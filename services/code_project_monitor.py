"""
CodeProjectMonitor — 代码项目监控器

功能:
  1. 监听指定目录文件变更 (创建/修改/删除/重命名)
  2. 自动触发AI处理 (代码审查/补全/重构建议)
  3. 批量代码生成工作流
  4. 代码质量检查自动化
  5. 项目健康度评分

适用场景:
  - 长时间自动化编程: 保存文件后自动触发AI审查
  - 批量生成: 根据需求文档自动生成多文件代码
  - 持续监控: 实时检测代码质量问题
"""

import os
import time
import json
import logging
import threading
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from enum import Enum

logger = logging.getLogger("CodeProjectMonitor")

# 可选依赖
try:
    import watchdog
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent, FileMovedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog未安装，文件监控功能受限。运行: pip install watchdog")

try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


class ChangeType(Enum):
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


class MonitorAction(Enum):
    NONE = "none"
    AUTO_REVIEW = "auto_review"      # 自动代码审查
    AUTO_COMPLETE = "auto_complete"  # 自动补全
    AUTO_FORMAT = "auto_format"      # 自动格式化
    AUTO_DOC = "auto_doc"            # 自动生成文档
    BATCH_GENERATE = "batch_generate" # 批量生成


@dataclass
class FileChange:
    """文件变更记录"""
    path: str
    change_type: ChangeType
    timestamp: float
    old_path: Optional[str] = None  # 用于move事件
    content_hash: Optional[str] = None
    size: int = 0


@dataclass
class CodeQualityReport:
    """代码质量报告"""
    file_path: str
    issues: List[Dict] = field(default_factory=list)
    score: float = 100.0  # 0-100
    suggestions: List[str] = field(default_factory=list)
    complexity: int = 0   # 圈复杂度
    line_count: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProjectHealth:
    """项目健康度"""
    total_files: int = 0
    total_lines: int = 0
    avg_quality_score: float = 100.0
    issue_count: int = 0
    critical_issues: int = 0
    last_scan: Optional[float] = None
    language_stats: Dict[str, int] = field(default_factory=dict)


class CodeFileHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """文件系统事件处理器"""
    
    def __init__(self, monitor, callback: Optional[Callable] = None):
        self.monitor = monitor
        self.callback = callback
        self._debounce_timers: Dict[str, threading.Timer] = {}
        self._debounce_delay = 1.5  # 防抖延迟(秒)
    
    def _debounce(self, path: str, change_type: ChangeType):
        """防抖处理：短时间内多次变更只触发一次"""
        # 取消之前的定时器
        if path in self._debounce_timers:
            self._debounce_timers[path].cancel()
        
        def delayed_process():
            self._process_change(path, change_type)
            del self._debounce_timers[path]
        
        timer = threading.Timer(self._debounce_delay, delayed_process)
        self._debounce_timers[path] = timer
        timer.start()
    
    def _process_change(self, path: str, change_type: ChangeType):
        """处理文件变更"""
        if not self.monitor._should_watch(path):
            return
        
        change = FileChange(
            path=path,
            change_type=change_type,
            timestamp=time.time()
        )
        
        # 计算内容hash
        if change_type in (ChangeType.CREATED, ChangeType.MODIFIED) and os.path.isfile(path):
            try:
                change.size = os.path.getsize(path)
                with open(path, 'rb') as f:
                    change.content_hash = hashlib.md5(f.read()).hexdigest()
            except Exception:
                pass
        
        self.monitor._on_file_change(change)
        
        if self.callback:
            try:
                self.callback(change)
            except Exception as e:
                logger.error(f"变更回调异常: {e}")
    
    def on_created(self, event):
        if not event.is_directory:
            self._debounce(event.src_path, ChangeType.CREATED)
    
    def on_modified(self, event):
        if not event.is_directory:
            self._debounce(event.src_path, ChangeType.MODIFIED)
    
    def on_deleted(self, event):
        if not event.is_directory:
            self._process_change(event.src_path, ChangeType.DELETED)
    
    def on_moved(self, event):
        if not event.is_directory:
            change = FileChange(
                path=event.dest_path,
                change_type=ChangeType.MOVED,
                timestamp=time.time(),
                old_path=event.src_path
            )
            self.monitor._on_file_change(change)


class CodeProjectMonitor:
    """代码项目监控器"""
    
    # 默认忽略模式
    DEFAULT_IGNORE_PATTERNS = [
        r'\.git', r'\.svn', r'\.hg',
        r'__pycache__', r'\.pytest_cache',
        r'node_modules', r'vendor',
        r'\.idea', r'\.vscode', r'\.vs',
        r'build', r'dist', r'target',
        r'\.egg-info', r'\.tox',
        r'\.env', r'\.venv', r'venv',
        r'\.log$', r'\.tmp$', r'\.temp$',
        r'\.pyc$', r'\.pyo$', r'\.class$',
        r'\.so$', r'\.dll$', r'\.exe$',
        r'\.min\.', r'\.bundle\.', r'\.map$',
    ]
    
    # 支持的代码文件扩展名
    CODE_EXTENSIONS = {
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.jsx': 'React', '.tsx': 'ReactTS', '.vue': 'Vue',
        '.java': 'Java', '.kt': 'Kotlin', '.scala': 'Scala',
        '.go': 'Go', '.rs': 'Rust', '.cpp': 'C++', '.c': 'C',
        '.h': 'C Header', '.hpp': 'C++ Header', '.cs': 'C#',
        '.rb': 'Ruby', '.php': 'PHP', '.swift': 'Swift',
        '.dart': 'Dart', '.lua': 'Lua', '.r': 'R',
        '.m': 'Objective-C', '.mm': 'Objective-C++',
        '.sh': 'Shell', '.ps1': 'PowerShell', '.bat': 'Batch',
        '.sql': 'SQL', '.html': 'HTML', '.css': 'CSS',
        '.scss': 'SCSS', '.sass': 'Sass', '.less': 'Less',
        '.json': 'JSON', '.xml': 'XML', '.yaml': 'YAML', '.yml': 'YAML',
        '.md': 'Markdown', '.rst': 'reStructuredText',
        '.dockerfile': 'Dockerfile', '.tf': 'Terraform',
        '.proto': 'Protobuf', '.graphql': 'GraphQL',
    }
    
    def __init__(self, project_path: str = None, config_manager=None):
        self.project_path = project_path or os.getcwd()
        self.config_manager = config_manager
        self._observer: Optional['Observer'] = None
        self._handler: Optional[CodeFileHandler] = None
        self._watching = False
        self._lock = threading.RLock()
        
        # 配置
        self.ignore_patterns = self.DEFAULT_IGNORE_PATTERNS.copy()
        self.auto_action = MonitorAction.AUTO_REVIEW
        self.auto_trigger_extensions = {'.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.c'}
        self.debounce_seconds = 1.5
        self.max_file_size_kb = 500  # 超过此大小不处理
        
        # 状态
        self.change_history: List[FileChange] = []
        self.max_history = 1000
        self.quality_reports: Dict[str, CodeQualityReport] = {}
        self.project_health = ProjectHealth()
        
        # 回调
        self._on_change_callbacks: List[Callable[[FileChange], None]] = []
        self._on_review_callbacks: List[Callable[[CodeQualityReport], None]] = []
        
        # 加载配置
        self._load_config()
    
    def _load_config(self):
        if self.config_manager:
            self.ignore_patterns = self.config_manager.get(
                "code_monitor_ignore", self.DEFAULT_IGNORE_PATTERNS
            )
            action_str = self.config_manager.get("code_monitor_action", "auto_review")
            try:
                self.auto_action = MonitorAction(action_str)
            except ValueError:
                self.auto_action = MonitorAction.AUTO_REVIEW
            self.debounce_seconds = self.config_manager.get("code_monitor_debounce", 1.5)
    
    def _save_config(self):
        if self.config_manager:
            self.config_manager.set("code_monitor_ignore", self.ignore_patterns)
            self.config_manager.set("code_monitor_action", self.auto_action.value)
            self.config_manager.set("code_monitor_debounce", self.debounce_seconds)
    
    # ── 公共API ─────────────────────────────────────────────────────────
    
    def start(self, callback: Optional[Callable[[FileChange], None]] = None) -> bool:
        """启动监控"""
        if not WATCHDOG_AVAILABLE:
            logger.error("watchdog未安装，无法启动文件监控")
            return False
        
        with self._lock:
            if self._watching:
                return True
            
            try:
                self._handler = CodeFileHandler(self, callback)
                self._observer = Observer()
                self._observer.schedule(
                    self._handler,
                    self.project_path,
                    recursive=True
                )
                self._observer.start()
                self._watching = True
                logger.info(f"✅ 开始监控项目: {self.project_path}")
                return True
            except Exception as e:
                logger.error(f"启动监控失败: {e}")
                return False
    
    def stop(self):
        """停止监控"""
        with self._lock:
            if not self._watching:
                return
            
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)
                self._observer = None
            
            self._watching = False
            logger.info("⏹ 停止监控")
    
    @property
    def is_watching(self) -> bool:
        return self._watching
    
    def set_project(self, path: str):
        """切换监控项目"""
        was_watching = self._watching
        if was_watching:
            self.stop()
        self.project_path = path
        if was_watching:
            self.start()
    
    def add_ignore_pattern(self, pattern: str):
        """添加忽略模式 (正则表达式)"""
        if pattern not in self.ignore_patterns:
            self.ignore_patterns.append(pattern)
            self._save_config()
    
    def remove_ignore_pattern(self, pattern: str):
        """移除忽略模式"""
        if pattern in self.ignore_patterns:
            self.ignore_patterns.remove(pattern)
            self._save_config()
    
    def on_change(self, callback: Callable[[FileChange], None]):
        """注册文件变更回调"""
        self._on_change_callbacks.append(callback)
    
    def on_review(self, callback: Callable[[CodeQualityReport], None]):
        """注册代码审查回调"""
        self._on_review_callbacks.append(callback)
    
    # ── 内部处理 ────────────────────────────────────────────────────────
    
    def _should_watch(self, path: str) -> bool:
        """判断是否应该监控此文件"""
        # 检查忽略模式
        rel_path = os.path.relpath(path, self.project_path)
        for pattern in self.ignore_patterns:
            try:
                if re.search(pattern, rel_path):
                    return False
            except re.error:
                continue
        
        # 检查文件大小
        try:
            if os.path.isfile(path):
                size_kb = os.path.getsize(path) / 1024
                if size_kb > self.max_file_size_kb:
                    return False
        except OSError:
            return False
        
        return True
    
    def _on_file_change(self, change: FileChange):
        """文件变更处理入口"""
        # 记录历史
        self.change_history.append(change)
        if len(self.change_history) > self.max_history:
            self.change_history = self.change_history[-self.max_history:]
        
        # 触发回调
        for cb in self._on_change_callbacks:
            try:
                cb(change)
            except Exception as e:
                logger.error(f"变更回调异常: {e}")
        
        # 自动触发AI处理
        if self.auto_action != MonitorAction.NONE:
            ext = os.path.splitext(change.path)[1].lower()
            if ext in self.auto_trigger_extensions:
                threading.Thread(
                    target=self._auto_process,
                    args=(change,),
                    daemon=True
                ).start()
    
    def _auto_process(self, change: FileChange):
        """自动处理文件变更"""
        try:
            if self.auto_action == MonitorAction.AUTO_REVIEW:
                self._auto_review(change.path)
            elif self.auto_action == MonitorAction.AUTO_DOC:
                self._auto_document(change.path)
            elif self.auto_action == MonitorAction.AUTO_FORMAT:
                self._auto_format(change.path)
        except Exception as e:
            logger.error(f"自动处理失败 [{change.path}]: {e}")
    
    def _auto_review(self, file_path: str):
        """自动代码审查"""
        report = self.review_file(file_path)
        for cb in self._on_review_callbacks:
            try:
                cb(report)
            except Exception as e:
                logger.error(f"审查回调异常: {e}")
    
    # ── 代码质量分析 ────────────────────────────────────────────────────
    
    def review_file(self, file_path: str) -> CodeQualityReport:
        """审查单个文件，返回质量报告"""
        report = CodeQualityReport(file_path=file_path)
        
        if not os.path.isfile(file_path):
            return report
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception:
            return report
        
        lines = content.split('\n')
        report.line_count = len(lines)
        ext = os.path.splitext(file_path)[1].lower()
        
        # 基础检查
        issues = []
        
        # 1. 行长度检查
        long_lines = [(i+1, len(line)) for i, line in enumerate(lines) if len(line) > 120]
        if long_lines:
            issues.append({
                "type": "style",
                "severity": "warning",
                "message": f"发现 {len(long_lines)} 行超过120字符",
                "lines": [l[0] for l in long_lines[:5]]
            })
        
        # 2. TODO/FIXME 检查
        todos = []
        for i, line in enumerate(lines):
            if re.search(r'\b(TODO|FIXME|HACK|XXX|BUG)\b', line, re.IGNORECASE):
                todos.append(i+1)
        if todos:
            issues.append({
                "type": "todo",
                "severity": "info",
                "message": f"发现 {len(todos)} 个待办标记",
                "lines": todos[:5]
            })
        
        # 3. Python 专用检查
        if ext == '.py':
            issues.extend(self._check_python(content, lines))
        
        # 4. JavaScript/TypeScript 专用检查
        elif ext in ('.js', '.ts', '.jsx', '.tsx'):
            issues.extend(self._check_javascript(content, lines))
        
        # 5. 圈复杂度估算
        report.complexity = self._estimate_complexity(content, ext)
        if report.complexity > 10:
            issues.append({
                "type": "complexity",
                "severity": "warning",
                "message": f"圈复杂度过高: {report.complexity} (建议<10)",
                "lines": []
            })
        
        # 计算分数
        report.issues = issues
        report.score = self._calculate_score(report)
        
        # 保存报告
        self.quality_reports[file_path] = report
        
        return report
    
    def _check_python(self, content: str, lines: List[str]) -> List[Dict]:
        """Python 代码检查"""
        issues = []
        
        # 检查裸 except
        bare_excepts = [i+1 for i, line in enumerate(lines) if re.search(r'^\s*except\s*:', line)]
        if bare_excepts:
            issues.append({
                "type": "error",
                "severity": "error",
                "message": f"发现 {len(bare_excepts)} 个裸 except",
                "lines": bare_excepts[:5]
            })
        
        # 检查 print 调试语句
        prints = [i+1 for i, line in enumerate(lines) if re.search(r'^\s*print\(', line)]
        if prints:
            issues.append({
                "type": "debug",
                "severity": "info",
                "message": f"发现 {len(prints)} 个 print 语句",
                "lines": prints[:5]
            })
        
        # 检查未使用的 import (简单检查)
        imports = re.findall(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))', content, re.MULTILINE)
        
        return issues
    
    def _check_javascript(self, content: str, lines: List[str]) -> List[Dict]:
        """JavaScript/TypeScript 代码检查"""
        issues = []
        
        # 检查 console.log
        consoles = [i+1 for i, line in enumerate(lines) if 'console.log' in line]
        if consoles:
            issues.append({
                "type": "debug",
                "severity": "info",
                "message": f"发现 {len(consoles)} 个 console.log",
                "lines": consoles[:5]
            })
        
        # 检查 var 使用
        var_uses = [i+1 for i, line in enumerate(lines) if re.search(r'^\s*var\s+', line)]
        if var_uses:
            issues.append({
                "type": "style",
                "severity": "warning",
                "message": f"发现 {len(var_uses)} 处 var 声明，建议使用 let/const",
                "lines": var_uses[:5]
            })
        
        return issues
    
    def _estimate_complexity(self, content: str, ext: str) -> int:
        """估算圈复杂度"""
        complexity = 1
        
        if ext == '.py':
            # 简单估算: if/elif/else/for/while/except/and/or/with
            patterns = [
                r'\bif\b', r'\belif\b', r'\bfor\b', r'\bwhile\b',
                r'\bexcept\b', r'\bwith\b', r'\band\b', r'\bor\b',
                r'\blambda\b', r'\bassert\b'
            ]
        elif ext in ('.js', '.ts', '.jsx', '.tsx'):
            patterns = [
                r'\bif\b', r'\belse\s+if\b', r'\bfor\b', r'\bwhile\b',
                r'\b&&\b', r'\b\|\|\b', r'\?\b', r'\bcase\b',
                r'\bcatch\b'
            ]
        else:
            return 1
        
        for pattern in patterns:
            complexity += len(re.findall(pattern, content))
        
        return min(complexity, 50)  # 上限50
    
    def _calculate_score(self, report: CodeQualityReport) -> float:
        """计算质量分数"""
        score = 100.0
        
        for issue in report.issues:
            severity = issue.get("severity", "info")
            if severity == "error":
                score -= 10
            elif severity == "warning":
                score -= 5
            elif severity == "info":
                score -= 1
        
        # 复杂度扣分
        if report.complexity > 15:
            score -= 15
        elif report.complexity > 10:
            score -= 10
        elif report.complexity > 5:
            score -= 5
        
        return max(0, min(100, score))
    
    # ── 项目扫描 ────────────────────────────────────────────────────────
    
    def scan_project(self) -> ProjectHealth:
        """扫描整个项目，计算健康度"""
        health = ProjectHealth()
        health.last_scan = time.time()
        
        if not os.path.isdir(self.project_path):
            return health
        
        total_score = 0
        file_count = 0
        
        for root, dirs, files in os.walk(self.project_path):
            # 跳过忽略目录
            dirs[:] = [d for d in dirs if not any(
                re.search(p, os.path.join(root, d)) for p in self.ignore_patterns
            )]
            
            for file in files:
                file_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()
                
                if ext in self.CODE_EXTENSIONS:
                    health.total_files += 1
                    health.language_stats[self.CODE_EXTENSIONS[ext]] = \
                        health.language_stats.get(self.CODE_EXTENSIONS[ext], 0) + 1
                    
                    # 审查文件
                    report = self.review_file(file_path)
                    health.total_lines += report.line_count
                    total_score += report.score
                    file_count += 1
                    health.issue_count += len(report.issues)
                    health.critical_issues += sum(
                        1 for i in report.issues if i.get("severity") == "error"
                    )
        
        if file_count > 0:
            health.avg_quality_score = round(total_score / file_count, 1)
        
        self.project_health = health
        return health
    
    # ── 批量生成工作流 ──────────────────────────────────────────────────
    
    def batch_generate(self, requirements: str, output_dir: str,
                       file_list: Optional[List[str]] = None,
                       ai_callback: Optional[Callable[[str, str], str]] = None) -> Dict:
        """批量代码生成工作流
        
        Args:
            requirements: 需求描述
            output_dir: 输出目录
            file_list: 预定义文件列表 (可选)
            ai_callback: AI生成回调 fn(requirement, context) -> code
        
        Returns:
            {"success": [...], "failed": [...], "skipped": [...]}
        """
        results = {"success": [], "failed": [], "skipped": []}
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 如果没有预定义文件列表，让AI生成
        if not file_list and ai_callback:
            prompt = f"""根据以下需求，列出需要创建的文件清单（仅文件名，每行一个）：

需求: {requirements}

请只输出文件路径列表，不要其他内容。"""
            response = ai_callback(prompt, "")
            file_list = [line.strip() for line in response.split('\n') 
                        if line.strip() and not line.startswith('#')]
        
        if not file_list:
            return results
        
        # 生成每个文件
        for file_path in file_list:
            full_path = os.path.join(output_dir, file_path)
            
            # 检查是否已存在
            if os.path.exists(full_path):
                results["skipped"].append(file_path)
                continue
            
            # 创建目录
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            if ai_callback:
                try:
                    prompt = f"""根据需求生成代码文件：

需求: {requirements}
文件: {file_path}

请只输出代码内容，不要其他说明。"""
                    code = ai_callback(prompt, "")
                    
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(code)
                    
                    results["success"].append(file_path)
                    logger.info(f"✅ 生成文件: {file_path}")
                except Exception as e:
                    results["failed"].append({"file": file_path, "error": str(e)})
                    logger.error(f"❌ 生成失败 [{file_path}]: {e}")
            else:
                # 创建空文件
                open(full_path, 'a').close()
                results["success"].append(file_path)
        
        return results
    
    # ── 工具方法 ────────────────────────────────────────────────────────
    
    def get_change_summary(self, since: float = None) -> Dict:
        """获取变更摘要"""
        if since is None:
            since = time.time() - 3600  # 默认最近1小时
        
        recent = [c for c in self.change_history if c.timestamp >= since]
        
        by_type = defaultdict(int)
        by_ext = defaultdict(int)
        
        for c in recent:
            by_type[c.change_type.value] += 1
            ext = os.path.splitext(c.path)[1].lower()
            by_ext[ext or "no_ext"] += 1
        
        return {
            "total": len(recent),
            "by_type": dict(by_type),
            "by_extension": dict(by_ext),
            "period_seconds": time.time() - since
        }
    
    def get_file_language(self, file_path: str) -> Optional[str]:
        """获取文件语言类型"""
        ext = os.path.splitext(file_path)[1].lower()
        return self.CODE_EXTENSIONS.get(ext)
    
    def is_code_file(self, file_path: str) -> bool:
        """判断是否为代码文件"""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.CODE_EXTENSIONS


# ═══════════════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════════════

_monitor: Optional[CodeProjectMonitor] = None
_monitor_lock = threading.Lock()


def get_code_project_monitor(project_path: str = None, config_manager=None) -> CodeProjectMonitor:
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                _monitor = CodeProjectMonitor(project_path, config_manager)
    return _monitor
