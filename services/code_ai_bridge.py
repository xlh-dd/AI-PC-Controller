"""
CodeAIBridge - 代码AI桥接器

连接 CodeProjectMonitor 与 Hermes/AgentService,实现:
  1. 文件变更 → 自动触发AI审查
  2. 代码生成 → 多文件并行
  3. 代码修复 → AI自动修复建议
  4. 项目重构 → 批量重构工作流
"""

import os
import time
import logging
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from pathlib import Path
import re

logger = logging.getLogger("CodeAIBridge")


@dataclass
class AIGenerationTask:
    """AI生成任务"""
    file_path: str
    requirement: str
    context: str = ""  # 相关文件内容作为上下文
    priority: int = 1
    status: str = "pending"  # pending/running/completed/failed
    result: str = ""
    error: str = ""
    start_time: float = 0
    end_time: float = 0


class CodeAIBridge:
    """代码AI桥接器"""

    def __init__(self, agent_service=None, config_manager=None):
        self._agent = agent_service
        self._config = config_manager
        self._task_queue: List[AIGenerationTask] = []
        self._queue_lock = threading.Lock()
        self._max_concurrent = 2  # 最大并发数
        self._running_tasks = 0
        self._on_task_complete: Optional[Callable] = None

    def set_agent_service(self, agent_service):
        self._agent = agent_service

    def set_on_complete(self, callback: Callable):
        self._on_task_complete = callback

    # ── 智能审查 ────────────────────────────────────────────────────────

    def review_code(self, file_path: str, content: str = None) -> Dict:
        """使用AI审查代码（JSON结构化输出）
        
        Returns:
            {
                "score": int,           # 0-100
                "bug_count": int,
                "issues": [{"severity": str, "title": str, "description": str}],
                "optimizations": [str],
                "security": [str],
                "summary": str
            }
        """
        if not self._agent or not self._agent.ensure_ready():
            return {"error": "AI服务不可用"}

        if content is None:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception as e:
                return {"error": f"读取文件失败: {e}"}

        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {'.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
                    '.java': 'Java', '.go': 'Go', '.rs': 'Rust',
                    '.cpp': 'C++', '.c': 'C', '.cs': 'C#'}
        lang = lang_map.get(ext, '代码')
        
        schema = '''{
  "score": 85,
  "bug_count": 2,
  "issues": [
    {"severity": "critical|high|medium|low", "title": "简短标题", "description": "详细描述"}
  ],
  "optimizations": ["性能优化1", "性能优化2"],
  "security": ["安全问题1"],
  "summary": "总体评价（中文）"
}'''
        
        prompt = f"""请审查以下{lang}代码，返回结构化分析。

文件: {os.path.basename(file_path)}

```
{content[:8000]}
```"""
        
        try:
            if hasattr(self._agent, 'json_chat'):
                result = self._agent.json_chat(prompt, json_schema=schema, timeout=300)
                if "error" not in result:
                    result["file"] = file_path
                    result["language"] = lang
                    return result
            
            # fallback to plain text
            full_prompt = f"""请审查以下{lang}代码，提供：
1. 潜在bug或问题
2. 性能优化建议
3. 代码风格改进
4. 安全漏洞检查
5. 总体评分(0-100)

文件: {os.path.basename(file_path)}

```
{content[:8000]}
```

请用中文回复，格式：
【评分】X/100
【问题】...
【优化】...
【安全】...
"""
            result = self._agent.chat(full_prompt, timeout=300)
            return self._parse_review_text(result, file_path, lang)
        except Exception as e:
            return {"error": str(e), "file": file_path}

    def _parse_review_text(self, text: str, file_path: str, lang: str) -> Dict:
        """解析文本格式的审查结果"""
        result = {"file": file_path, "language": lang, "score": 0, "bug_count": 0,
                  "issues": [], "optimizations": [], "security": [], "summary": text}
        
        score_match = re.search(r'【评分】\s*(\d+)', text)
        if score_match:
            result["score"] = int(score_match.group(1))
        
        return result

    # ── 代码生成 ────────────────────────────────────────────────────────

    def generate_file(self, requirement: str, file_path: str,
                      context_files: List[str] = None) -> str:
        """生成单个文件代码"""
        if not self._agent or not self._agent.ensure_ready():
            return "# AI服务不可用\n"

        # 收集上下文
        context = ""
        if context_files:
            for cf in context_files[:3]:  # 最多3个上下文文件
                try:
                    with open(cf, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    context += f"\n# --- {os.path.basename(cf)} ---\n{content[:2000]}\n"
                except Exception:
                    pass

        ext = os.path.splitext(file_path)[1].lower()
        lang = {'.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
                '.java': 'Java', '.go': 'Go', '.rs': 'Rust',
                '.cpp': 'C++', '.c': 'C', '.cs': 'C#'}.get(ext, '')

        prompt = f"""请生成{lang}代码文件: {os.path.basename(file_path)}

需求:
{requirement}

{context}

要求:
- 只输出代码,不要解释
- 包含必要的注释
- 遵循最佳实践
- 处理边界情况
"""

        try:
            code = self._agent.chat(prompt, timeout=300)
            # 清理markdown代码块
            code = self._clean_code_block(code)
            return code
        except Exception as e:
            logger.error(f"生成失败 [{file_path}]: {e}")
            return f"# 生成失败: {e}\n"

    def generate_project(self, requirements: str, output_dir: str,
                         structure: List[Dict] = None) -> Dict:
        """生成完整项目

        structure: [{"path": "src/main.py", "description": "入口文件"}, ...]
        """
        results = {"success": [], "failed": []}

        if not structure:
            # 让AI生成项目结构
            structure = self._generate_structure(requirements)

        if not structure:
            return results

        # 先生成所有文件的内容规划
        files_to_generate = []
        for item in structure:
            task = AIGenerationTask(
                file_path=os.path.join(output_dir, item["path"]),
                requirement=item.get("description", ""),
                priority=item.get("priority", 1)
            )
            files_to_generate.append(task)

        # 按优先级排序,先生成核心文件
        files_to_generate.sort(key=lambda t: t.priority)

        # 串行生成(避免AI上下文混乱)
        generated_contents = {}  # 已生成文件内容作为后续文件上下文

        for task in files_to_generate:
            try:
                task.status = "running"
                task.start_time = time.time()

                # 收集相关上下文
                context_files = []
                rel_path = os.path.relpath(task.file_path, output_dir)

                # 找同目录已生成文件作为上下文
                task_dir = os.path.dirname(rel_path)
                for path, content in generated_contents.items():
                    other_dir = os.path.dirname(os.path.relpath(path, output_dir))
                    if other_dir == task_dir or other_dir.startswith(task_dir):
                        context_files.append(path)

                # 生成代码
                code = self.generate_file(
                    f"{requirements}\n\n文件职责: {task.requirement}",
                    task.file_path,
                    context_files=context_files[:2]
                )

                # 写入文件
                os.makedirs(os.path.dirname(task.file_path), exist_ok=True)
                with open(task.file_path, 'w', encoding='utf-8') as f:
                    f.write(code)

                task.result = code
                task.status = "completed"
                task.end_time = time.time()
                generated_contents[task.file_path] = code
                results["success"].append(task)

                logger.info(f"✅ 生成: {os.path.relpath(task.file_path, output_dir)}")

            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                task.end_time = time.time()
                results["failed"].append(task)
                logger.error(f"❌ 失败: {task.file_path} - {e}")

        return results

    def _generate_structure(self, requirements: str) -> List[Dict]:
        """让AI生成项目结构"""
        if not self._agent:
            return []

        prompt = f"""根据需求生成项目文件结构,只输出JSON格式:

需求: {requirements}

输出格式:
[
  {{"path": "src/main.py", "description": "入口文件,负责...", "priority": 1}},
  {{"path": "src/utils.py", "description": "工具函数", "priority": 2}}
]

priority: 1=核心文件(先生成), 2=依赖文件, 3=辅助文件
"""

        try:
            result = self._agent.chat(prompt, timeout=180)
            # 提取JSON
            import json
            # 找方括号包裹的内容
            start = result.find('[')
            end = result.rfind(']')
            if start >= 0 and end > start:
                return json.loads(result[start:end+1])
            return []
        except Exception as e:
            logger.error(f"生成结构失败: {e}")
            return []

    # ── 代码修复 ────────────────────────────────────────────────────────

    def fix_code(self, file_path: str, issues: List[str]) -> str:
        """根据问题列表修复代码"""
        if not self._agent:
            return ""

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            return f"# 读取失败: {e}"

        issues_text = "\n".join(f"- {i}" for i in issues)

        prompt = f"""请修复以下代码中的问题:

问题列表:
{issues_text}

原始代码:
```
{content[:6000]}
```

要求:
- 只输出修复后的完整代码
- 不要解释修改内容
- 保持原有功能不变
"""

        try:
            fixed = self._agent.chat(prompt, timeout=300)
            return self._clean_code_block(fixed)
        except Exception as e:
            return content  # 失败返回原代码

    # ── 批量重构 ────────────────────────────────────────────────────────

    def refactor_batch(self, files: List[str], instruction: str) -> Dict:
        """批量重构多个文件"""
        results = {}

        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()

                prompt = f"""请重构以下代码:

重构要求: {instruction}

代码:
```
{content[:6000]}
```

只输出重构后的完整代码,不要解释。
"""
                refactored = self._agent.chat(prompt, timeout=300)
                refactored = self._clean_code_block(refactored)

                # 备份原文件
                backup = file_path + ".backup"
                with open(backup, 'w', encoding='utf-8') as f:
                    f.write(content)

                # 写入重构后代码
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(refactored)

                results[file_path] = {"success": True, "backup": backup}

            except Exception as e:
                results[file_path] = {"success": False, "error": str(e)}

        return results

    # ── 工具方法 ────────────────────────────────────────────────────────

    def _clean_code_block(self, text: str) -> str:
        """清理markdown代码块,提取代码内容"""

        # 策略1: 匹配 ```lang\ncode\n``` 格式
        pattern = r'^```[\w]*\n(.*?)\n```$'
        match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()

        # 策略2: 匹配文本中任意位置的代码块
        pattern2 = r'```[\w]*\n(.*?)\n```'
        match2 = re.search(pattern2, text, re.DOTALL)
        if match2:
            return match2.group(1).strip()

        # 策略3: 手动解析行
        lines = text.split('\n')
        in_code_block = False
        code_block_start = -1

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_block_start = i
                else:
                    in_code_block = False
                    block_content = lines[code_block_start + 1:i]
                    if block_content:
                        # 检查第一行是否是语言标识
                        first = block_content[0].strip()
                        if first and len(first) < 20 and not any(c in first for c in '(){}[]=;:/\"\''):
                            if len(block_content) > 1:
                                return '\n'.join(block_content[1:]).strip()
                        return '\n'.join(block_content).strip()
                    code_block_start = -1
                continue

        # 如果没有代码块标记,直接返回原文
        return text.strip()

    def get_task_status(self) -> Dict:
        """获取任务队列状态"""
        with self._queue_lock:
            pending = sum(1 for t in self._task_queue if t.status == "pending")
            running = sum(1 for t in self._task_queue if t.status == "running")
            completed = sum(1 for t in self._task_queue if t.status == "completed")
            failed = sum(1 for t in self._task_queue if t.status == "failed")

        return {
            "pending": pending,
            "running": running,
            "completed": completed,
            "failed": failed,
            "concurrent": self._running_tasks
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════════════

_bridge: Optional[CodeAIBridge] = None
_bridge_lock = threading.Lock()


def get_code_ai_bridge(agent_service=None, config_manager=None) -> CodeAIBridge:
    """获取或创建CodeAIBridge单例。如果已存在但agent不同,更新agent。"""
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:
                _bridge = CodeAIBridge(agent_service, config_manager)
    elif agent_service is not None and _bridge._agent is None:
        # 单例已存在但agent未设置,补充设置
        _bridge.set_agent_service(agent_service)
    return _bridge
