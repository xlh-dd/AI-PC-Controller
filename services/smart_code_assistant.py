"""
SmartCodeAssistant — 智能代码助手

提供6种AI能力, 连接到CodeWorkspacePanel的智能助手标签页:
  1. explain_code     — 解释代码逻辑
  2. generate_tests   — 生成单元测试
  3. generate_doc     — 生成API文档
  4. optimize_performance — 性能分析+优化代码
  5. convert_code     — 跨语言转换
  6. security_review  — 安全审查
"""

import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger("SmartCodeAssistant")


class SmartCodeAssistant:
    """智能代码助手"""

    def __init__(self, agent_service=None):
        self._agent = agent_service

    def set_agent(self, agent_service):
        self._agent = agent_service

    def _ensure_agent(self):
        return self._agent and self._agent.ensure_ready()

    # ── 解释代码 ────────────────────────────────────────────────────────

    def explain_code(self, code: str, language: str = "python") -> str:
        """解释代码逻辑"""
        if not self._ensure_agent():
            return "❌ AI服务不可用"
        prompt = f"""请详细解释以下{language}代码的逻辑、数据流和关键设计决策：

```{language}
{code[:8000]}
```

请用中文回答，从以下角度分析：
1. 整体功能和用途
2. 关键函数/类的作用
3. 数据流向
4. 可能的边界情况
"""
        try:
            return self._agent.chat(prompt, timeout=180)
        except Exception as e:
            return f"❌ 解释失败: {e}"

    # ── 生成测试 ────────────────────────────────────────────────────────

    def generate_tests(self, code: str, language: str = "python",
                       framework: str = None) -> str:
        """生成单元测试"""
        if not self._ensure_agent():
            return "❌ AI服务不可用"

        framework_map = {
            'python': 'pytest',
            'javascript': 'jest',
            'typescript': 'jest',
            'java': 'JUnit 5',
            'go': 'testing',
            'rust': '#[test]',
        }
        fw = framework or framework_map.get(language, '标准测试框架')

        prompt = f"""请为以下{language}代码生成完整的单元测试（使用{fw}）：

```{language}
{code[:6000]}
```

要求：
- 覆盖所有公共函数/方法
- 包含正常输入、边界值、异常情况的测试
- 使用mock模拟外部依赖
- 只输出测试代码，不要解释
"""
        try:
            result = self._agent.chat(prompt, timeout=300)
            return self._clean_response(result)
        except Exception as e:
            return f"❌ 生成测试失败: {e}"

    # ── 生成文档 ────────────────────────────────────────────────────────

    def generate_doc(self, code: str, language: str = "python",
                     style: str = "google") -> str:
        """生成API文档"""
        if not self._ensure_agent():
            return "❌ AI服务不可用"

        prompt = f"""请为以下{language}代码生成API文档（{style}风格）：

```{language}
{code[:8000]}
```

要求：
- 列出所有公开的类、方法、函数
- 包含参数说明、返回值、异常
- 包含使用示例
- 用Markdown格式输出
"""
        try:
            return self._agent.chat(prompt, timeout=180)
        except Exception as e:
            return f"❌ 生成文档失败: {e}"

    # ── 性能优化 ────────────────────────────────────────────────────────

    def optimize_performance(self, code: str, language: str = "python") -> Dict:
        """性能分析和优化建议（JSON结构化输出）"""
        if not self._ensure_agent():
            return {"analysis": "❌ AI服务不可用", "optimized": ""}

        schema = '''{
  "bottlenecks": ["瓶颈1", "瓶颈2"],
  "suggestions": ["建议1", "建议2"],
  "optimized_code": "优化后的完整代码"
}'''
        
        prompt = f"""请分析以下{language}代码的性能并给出优化建议和优化后的代码。

```{language}
{code[:6000]}
```"""
        
        try:
            result = self._agent.json_chat(prompt, json_schema=schema, timeout=300)
            if "error" in result:
                # fallback: raw text parsing
                return self._parse_optimize_fallback(result.get("raw", str(result)))
            return {
                "analysis": "\n".join(result.get("bottlenecks", [])) + "\n\n建议:\n" + "\n".join(result.get("suggestions", [])),
                "optimized": result.get("optimized_code", "")
            }
        except Exception as e:
            return {"analysis": f"❌ 失败: {e}", "optimized": ""}

    def _parse_optimize_fallback(self, text: str) -> Dict:
        """JSON解析失败时的文本回退"""
        analysis = text
        optimized = ""
        if "【优化后代码】" in text:
            parts = text.split("【优化后代码】")
            analysis = parts[0].strip()
            optimized = self._clean_response(parts[1]) if len(parts) > 1 else ""
        return {"analysis": analysis, "optimized": optimized}

    # ── 代码转换 ────────────────────────────────────────────────────────

    def convert_code(self, code: str, source_lang: str,
                     target_lang: str) -> str:
        """跨语言转换代码"""
        if not self._ensure_agent():
            return "❌ AI服务不可用"

        prompt = f"""请将以下{source_lang}代码转换为等效的{target_lang}代码：

```{source_lang}
{code[:6000]}
```

要求：
- 保持完全相同的功能和逻辑
- 使用{target_lang}的惯用写法和最佳实践
- 处理语言差异（类型系统、异常处理、内存管理等）
- 只输出转换后代码，不要解释
"""
        try:
            result = self._agent.chat(prompt, timeout=300)
            return self._clean_response(result)
        except Exception as e:
            return f"❌ 转换失败: {e}"

    # ── 安全审查 ────────────────────────────────────────────────────────

    def security_review(self, code: str, language: str = "python") -> Dict:
        """安全审查（JSON结构化输出）"""
        if not self._ensure_agent():
            return {"review": "❌ AI服务不可用", "fixed": ""}

        schema = '''{
  "vulnerabilities": [
    {"severity": "critical|high|medium|low", "issue": "描述", "line": "大致行号"}
  ],
  "fixes": ["修复方案1", "修复方案2"],
  "fixed_code": "修复后的完整代码"
}'''
        
        prompt = f"""请审查以下{language}代码的安全漏洞。

```{language}
{code[:6000]}
```"""
        
        try:
            result = self._agent.json_chat(prompt, json_schema=schema, timeout=300)
            if "error" in result:
                return self._parse_security_fallback(result.get("raw", str(result)))
            
            vulns = result.get("vulnerabilities", [])
            review_lines = []
            for v in vulns:
                sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(v.get("severity", ""), "⚪")
                review_lines.append(f"{sev_emoji} [{v.get('severity', '?')}] {v.get('issue', '?')}")
            
            fixes = result.get("fixes", [])
            if fixes:
                review_lines.append("\n修复方案:")
                review_lines.extend(f"  {i+1}. {f}" for i, f in enumerate(fixes))
            
            return {"review": "\n".join(review_lines), "fixed": result.get("fixed_code", "")}
        except Exception as e:
            return {"review": f"❌ 失败: {e}", "fixed": ""}

    def _parse_security_fallback(self, text: str) -> Dict:
        """安全审查 JSON解析失败时的回退"""
        review = text
        fixed = ""
        if "【修复后代码】" in text:
            parts = text.split("【修复后代码】")
            review = parts[0].strip()
            fixed = self._clean_response(parts[1]) if len(parts) > 1 else ""
        return {"review": review, "fixed": fixed}

    # ── 工具 ────────────────────────────────────────────────────────────

    def _clean_response(self, text: str) -> str:
        """清理响应中的markdown代码块"""
        import re
        pattern = r'```[\w]*\n(.*?)\n```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════════════

_assistant: Optional[SmartCodeAssistant] = None
_assistant_lock = threading.Lock()


def get_smart_code_assistant(agent_service=None) -> SmartCodeAssistant:
    global _assistant
    if _assistant is None:
        with _assistant_lock:
            if _assistant is None:
                _assistant = SmartCodeAssistant(agent_service)
    elif agent_service is not None:
        _assistant.set_agent(agent_service)
    return _assistant