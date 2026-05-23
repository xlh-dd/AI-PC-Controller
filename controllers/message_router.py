"""
MessageRouter — 消息路由控制器

功能:
  1. 命令路由: 以 "/" 开头的消息解析为命令，映射到对应 handler
  2. 任务分类路由: 根据关键词和消息长度将用户消息分类为
     CHAT_COMPLEX / CHAT_SIMPLE / SYSTEM 三种类型
  3. AI 分类扩展点: 预留 _ai_classify 供未来 AI 模型辅助路由

路由决策表:
  /xxx 命令        → COMMAND       → handler=对应处理函数名
  代码/编程关键词   → CHAT_COMPLEX  → backend=hermes
  搜索/查询关键词   → CHAT_SIMPLE   → backend=deepseek
  分析关键词        → CHAT_COMPLEX  → backend=hermes
  系统命令关键词    → SYSTEM        → backend=preferred
  创意关键词        → CHAT_SIMPLE   → backend=deepseek
  短消息(≤200)      → CHAT_SIMPLE   → backend=deepseek (默认)
  长消息(>200)      → CHAT_COMPLEX  → backend=hermes (默认)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

import logging

logger = logging.getLogger("MessageRouter")


class RouteType(Enum):
    """消息路由类型"""
    COMMAND = "COMMAND"
    CHAT_COMPLEX = "CHAT_COMPLEX"
    CHAT_SIMPLE = "CHAT_SIMPLE"
    SYSTEM = "SYSTEM"


@dataclass
class RouteTarget:
    """路由目标

    Attributes:
        type: 路由类型 (COMMAND / CHAT_COMPLEX / CHAT_SIMPLE / SYSTEM)
        backend: 推荐后端 (preferred / deepseek / hermes / ollama)
        handler: 命令处理函数名 (仅 COMMAND 类型有效)
        metadata: 额外信息 (如 timeout, model 推荐等)
    """
    type: str
    backend: str = "deepseek"
    handler: Optional[str] = None
    metadata: dict = field(default_factory=dict)


KNOWN_COMMANDS: Dict[str, str] = {
    "clear": "clear_conversation",
    "cls": "clear_conversation",
    "hermes": "toggle_hermes",
    "h": "toggle_hermes",
    "history": "show_history",
    "new": "new_conversation",
}


class MessageRouter:
    """消息路由器

    根据消息内容决定路由目标: 命令 → handler, 聊天 → 模型后端。
    """

    def route(self, message: str) -> RouteTarget:
        """路由消息到目标

        Args:
            message: 用户输入消息

        Returns:
            RouteTarget: 路由目标对象
        """
        if not message:
            return RouteTarget(
                type=RouteType.CHAT_SIMPLE.value,
                backend="deepseek",
                metadata={"reasoning": "空消息 → DeepSeek 默认"}
            )

        msg_stripped = message.strip()

        if msg_stripped.startswith("/"):
            return self._route_command(msg_stripped)

        return self._classify_task(msg_stripped)

    def _route_command(self, message: str) -> RouteTarget:
        """解析命令消息

        Args:
            message: 以 "/" 开头的消息

        Returns:
            RouteTarget: 命令路由目标
        """
        cmd_part = message[1:].strip().lower()

        if not cmd_part:
            return RouteTarget(
                type=RouteType.COMMAND.value,
                backend="preferred",
                handler=None,
                metadata={"reasoning": "空命令 → 无 handler"}
            )

        cmd_name = cmd_part.split()[0]

        if cmd_name in KNOWN_COMMANDS:
            handler = KNOWN_COMMANDS[cmd_name]
            return RouteTarget(
                type=RouteType.COMMAND.value,
                backend="preferred",
                handler=handler,
                metadata={"reasoning": f"已知命令 /{cmd_name} → {handler}"}
            )

        return RouteTarget(
            type=RouteType.COMMAND.value,
            backend="preferred",
            handler=cmd_name,
            metadata={"reasoning": f"未知命令 /{cmd_name} → 透传 handler"}
        )

    def _classify_task(self, message: str) -> RouteTarget:
        """基于关键词和长度进行任务分类

        复刻 main.py 中的 _classify_task 逻辑，输出 RouteTarget 而非 dict。

        Args:
            message: 用户输入消息

        Returns:
            RouteTarget: 分类后的路由目标
        """
        msg_lower = message.lower()

        if len(message) < 10:
            trivial = ["help", "帮助", "status", "状态", "clear", "cls",
                       "hi", "你好", "hello", "在吗"]
            if any(k in msg_lower for k in trivial):
                return RouteTarget(
                    type=RouteType.SYSTEM.value,
                    backend="preferred",
                    metadata={"reasoning": "问候/系统 → preferred"}
                )
            return RouteTarget(
                type=RouteType.CHAT_SIMPLE.value,
                backend="deepseek",
                metadata={"reasoning": "短消息 → DeepSeek 默认"}
            )

        code_kw = ["写", "生成代码", "代码", "函数", "def ", "class ",
                   "实现", "修复bug", "fix bug", "debug", "重构", "review",
                   "审查", "爬虫", "scraper", "算法", "数据结构",
                   "生成一个", "帮我写", "接口", "api"]
        if any(k in msg_lower for k in code_kw):
            complex_ind = ["重构", "架构", "系统设计", "大规模", "分布式",
                           "多线程", "并发", "全栈", "完整"]
            if any(k in msg_lower for k in complex_ind) or len(message) > 200:
                return RouteTarget(
                    type=RouteType.CHAT_COMPLEX.value,
                    backend="hermes",
                    metadata={"reasoning": "复杂代码/架构 → Hermes",
                              "timeout": 600, "model": "ds-v4-pro"}
                )
            return RouteTarget(
                type=RouteType.CHAT_COMPLEX.value,
                backend="hermes",
                metadata={"reasoning": "代码生成 → Hermes",
                          "timeout": 300, "model": "ds-v4-pro"}
            )

        search_kw = ["搜索", "查询", "查找", "怎么", "如何", "为什么",
                     "什么是", "定义", "区别", "对比", "有哪些", "介绍一下"]
        if any(k in msg_lower for k in search_kw):
            return RouteTarget(
                type=RouteType.CHAT_SIMPLE.value,
                backend="deepseek",
                metadata={"reasoning": "搜索查询 → DeepSeek"}
            )

        analysis_kw = ["分析", "诊断", "审核", "评估", "总结", "摘要",
                       "深入分析"]
        if any(k in msg_lower for k in analysis_kw):
            return RouteTarget(
                type=RouteType.CHAT_COMPLEX.value,
                backend="hermes",
                metadata={"reasoning": "分析任务 → Hermes",
                          "timeout": 300, "model": "ds-v4-flash-r"}
            )

        creative_kw = ["创意", "设计", "头脑风暴", "想法", "建议", "推荐",
                       "方案"]
        if any(k in msg_lower for k in creative_kw):
            return RouteTarget(
                type=RouteType.CHAT_SIMPLE.value,
                backend="deepseek",
                metadata={"reasoning": "创意 → DeepSeek",
                          "model": "ds-v4-flash-r"}
            )

        cmd_kw = ["打开", "关闭", "启动", "停止", "重启", "清理", "整理",
                  "下载", "安装", "配置", "检查", "查看"]
        if any(k in msg_lower for k in cmd_kw):
            return RouteTarget(
                type=RouteType.SYSTEM.value,
                backend="preferred",
                metadata={"reasoning": "系统命令 → 快速执行", "timeout": 120}
            )

        if len(message) > 200:
            return RouteTarget(
                type=RouteType.CHAT_COMPLEX.value,
                backend="hermes",
                metadata={"reasoning": "长文本 → Hermes",
                          "timeout": 300, "model": "ds-v4-flash-r"}
            )

        return RouteTarget(
            type=RouteType.CHAT_SIMPLE.value,
            backend="deepseek",
            metadata={"reasoning": "默认对话 → DeepSeek"}
        )

    def _ai_classify(self, message: str) -> Optional[RouteTarget]:
        """AI 辅助分类扩展点 (预留)

        未来可通过调用 AI 模型进行更精准的消息分类。

        Args:
            message: 用户输入消息

        Returns:
            Optional[RouteTarget]: 当前返回 None，预留扩展
        """
        return None