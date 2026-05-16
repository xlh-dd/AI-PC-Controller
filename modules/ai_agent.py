import json
import time
import os
import logging
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from contextlib import contextmanager

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False
    BeautifulSoup = None

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

# 导入系统控制器
try:
    from modules.system_controller import get_system_controller
    SYSTEM_CONTROLLER_AVAILABLE = True
except ImportError:
    SYSTEM_CONTROLLER_AVAILABLE = False

logger = logging.getLogger("AIAgent")

class AIAgent:
    """AI智能体 - 任务规划、执行、反馈

    支持依赖注入，允许传入自定义的 ai_helper 实例
    """


    _TOOL_CATEGORIES = {
        "搜索与信息收集": {
            "keywords": ["搜索", "查找", "查询", "搜索", "google", "bing", "百度", "查找信息", "搜索资料"],
            "tools": [
                "search_browser - 在浏览器中搜索信息",
                "search_and_collect - 搜索并收集信息，返回结构化数据",
                "collect_and_save - ★推荐★ 搜索、整理并保存为文档"
            ]
        },
        "文档与文件操作": {
            "keywords": ["保存", "文档", "文件", "写入", "创建", "编辑", "整理", "笔记", "记事本"],
            "tools": [
                "save_document - 保存文档到指定位置",
                "file_operation - 执行文件操作（复制/移动/删除）"
            ]
        },
        "通信与社交": {
            "keywords": ["微信", "发送", "消息", "通知", "提醒", "聊天", "沟通", "邮件"],
            "tools": [
                "send_wechat - 发送微信消息",
                "speak_text - 语音合成(文本转语音)"
            ]
        },
        "系统控制与自动化": {
            "keywords": ["执行", "运行", "命令", "自动化", "宏", "录制", "播放", "定时", "计划"],
            "tools": [
                "execute_command - 执行系统命令",
                "play_macro - 播放录制的宏",
                "record_macro - 开始录制宏",
                "schedule_task - 创建定时任务"
            ]
        },
        "应用程序管理": {
            "keywords": ["打开", "启动", "应用", "程序", "软件", "窗口", "最小化", "激活", "关闭"],
            "tools": [
                "open_app - 打开应用程序",
                "manage_windows - 管理应用程序窗口",
                "manage_processes - 管理系统进程"
            ]
        },
        "多媒体与界面": {
            "keywords": ["截图", "屏幕", "图像", "点击", "识别", "文字", "OCR", "音量", "声音", "静音"],
            "tools": [
                "take_screenshot - 截取屏幕",
                "click_image - 在屏幕上查找并点击图像",
                "ocr_screen - 识别屏幕区域的文字(OCR)",
                "control_volume - 控制电脑音量"
            ]
        },
        "网络与通信": {
            "keywords": ["网络", "wifi", "连接", "HTTP", "请求", "API", "访问", "网站"],
            "tools": [
                "control_network - 控制网络连接",
                "http_request - 发送HTTP请求"
            ]
        },
        "系统信息": {
            "keywords": ["信息", "状态", "CPU", "内存", "磁盘", "系统", "剪贴板", "配置"],
            "tools": [
                "system_info - 获取系统信息",
                "control_clipboard - 控制剪贴板"
            ]
        },
        "编程与代码": {
            "keywords": ["python", "代码", "编程", "运行代码", "脚本", "执行代码"],
            "tools": [
                "run_python - 执行Python代码"
            ]
        }
    }

    def __init__(self, ai_helper=None, config_manager=None, ollama_url=None, model=None, event_bus=None, **kwargs):
        """初始化 AI 智能体

        Args:
            ai_helper: AIHelper 实例（可选，支持依赖注入）
            config_manager: 配置管理器实例（可选，用于创建默认 AIHelper）
            ollama_url: Ollama 服务 URL（可选，向后兼容）
            model: 模型名称（可选，向后兼容）
            event_bus: EventBus 实例（可选，用于事件发布）
            **kwargs: 其他可选参数
        """
        # 依赖注入：优先使用传入的 ai_helper
        self.ai_helper = ai_helper

        # EventBus 集成
        if event_bus is None:
            try:
                from core.event_bus import event_bus as default_event_bus
                self.event_bus = default_event_bus
            except ImportError:
                self.event_bus = None
                logger.warning("EventBus 不可用，事件发布功能受限")
        else:
            self.event_bus = event_bus

        # 如果没有传入 ai_helper，尝试通过 config_manager 创建或使用回退方案
        if self.ai_helper is None:
            if config_manager is not None:
                try:
                    from modules.ai_helper import AIHelper
                    self.ai_helper = AIHelper(
                        ollama_url=config_manager.get("ollama_url", "http://localhost:11434/api/generate"),
                        model=config_manager.get("model", "qwen2.5:1.5b"),
                        config_manager=config_manager
                    )
                    logger.info("通过 config_manager 创建 AIHelper 实例")
                except Exception as e:
                    logger.warning(f"创建 AIHelper 失败: {e}")
            elif ollama_url and model:
                # 向后兼容：使用传入的 ollama_url 和 model 创建
                self.ollama_url = ollama_url
                self.model = model
                logger.info("使用传统参数模式（ollama_url, model）")

        # 保存配置引用（如果提供）
        self.config_manager = config_manager

        # 保存 URL 和 model（向后兼容，也可能从 ai_helper 获取）
        if self.ai_helper and hasattr(self.ai_helper, 'ollama_url'):
            self.ollama_url = self.ai_helper.ollama_url or ollama_url or "http://localhost:11434/api/generate"
            self.model = self.ai_helper.model or model or "qwen2.5:1.5b"
        else:
            self.ollama_url = ollama_url or "http://localhost:11434/api/generate"
            self.model = model or "qwen2.5:1.5b"

        self._wechat_controller = None
        self._command_executor = None
        self._feedback_callback = None

        # 系统控制器
        self._system_controller = None
        if SYSTEM_CONTROLLER_AVAILABLE:
            try:
                self._system_controller = get_system_controller()
                logger.info("系统控制器已加载")
            except Exception as e:
                logger.warning(f"加载系统控制器失败: {e}")

        self.tools = {
            "search_browser": self.search_browser,
            "search_and_collect": self.search_and_collect,
            "collect_and_save": self.collect_and_save,
            "send_wechat": self.send_wechat_message,
            "save_document": self.save_document,
            "execute_command": self.execute_command,
            "play_macro": self.play_macro,
            "record_macro": self.record_macro,
            "schedule_task": self.schedule_task,
            "file_operation": self.file_operation,
            "http_request": self.http_request,
            "run_python": self.run_python_code,
            "open_app": self.open_application,
            "click_image": self.click_image,
            # 新增系统控制工具
            "control_volume": self.control_volume,
            "control_network": self.control_network,
            "manage_processes": self.manage_processes,
            "manage_windows": self.manage_windows,
            "take_screenshot": self.take_screenshot,
            "control_clipboard": self.control_clipboard,
            "system_info": self.get_system_info,
            "speak_text": self.speak_text,
            "ocr_screen": self.ocr_screen,
        }
        self._macro_player = None
        self._macro_recorder = None
        self._task_scheduler = None
        self._setup_tool_descriptions()

    def set_feedback_callback(self, callback):
        """设置反馈回调函数"""
        self._feedback_callback = callback
        logger.info("反馈回调已设置")

    def _send_feedback(self, message, is_error=False):
        """发送反馈"""
        if self._feedback_callback:
            try:
                self._feedback_callback(message, is_error)
            except Exception as e:
                logger.error(f"发送反馈失败: {e}")

    def _publish_event(self, event_type, data=None):
        """发布事件到 EventBus（安全包装）"""
        if self.event_bus is None:
            return
        try:
            payload = {"type": event_type, "timestamp": __import__("time").time()}
            if data:
                payload["data"] = data
            self.event_bus.publish(f"ai.{event_type}", payload)
        except Exception as e:
            logger.debug(f"事件发布失败 [{event_type}]: {e}")

    TOOL_DESCRIPTIONS = {
            "search_browser": {
                "description": "在浏览器中搜索信息，需要提供搜索关键词",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"}
                    },
                    "required": ["query"]
    }
            },
            "search_and_collect": {
                "description": "搜索并收集信息，返回结构化数据（无需打开浏览器）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "max_results": {"type": "integer", "description": "最大结果数，默认5"}
                    },
                    "required": ["query"]
    }
            },
            "collect_and_save": {
                "description": "搜索信息、收集并整理后保存为文档（推荐使用）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "save_path": {"type": "string", "description": "保存路径，如 D:/文档/result.md"},
                        "format": {"type": "string", "description": "文档格式，默认markdown"},
                        "max_results": {"type": "integer", "description": "最大搜索结果数，默认10"}
                    },
                    "required": ["query", "save_path"]
    }
            },
            "send_wechat": {
                "description": "发送微信消息给指定联系人",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "联系人名称"},
                        "message": {"type": "string", "description": "消息内容"}
                    },
                    "required": ["target", "message"]
    }
            },
            "save_document": {
                "description": "将内容保存到指定路径的文档中",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文档内容"}
                    },
                    "required": ["path", "content"]
    }
            },
            "execute_command": {
                "description": "执行系统命令",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的命令"}
                    },
                    "required": ["command"]
    }
            },
            "play_macro": {
                "description": "播放录制的宏（自动化脚本）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "macro_name": {"type": "string", "description": "宏名称"},
                        "speed": {"type": "number", "description": "播放速度，默认1.0"},
                        "repeat": {"type": "integer", "description": "重复次数，默认1"}
                    },
                    "required": ["macro_name"]
    }
            },
            "record_macro": {
                "description": "开始录制宏（记录鼠标键盘操作）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "宏名称"}
                    },
                    "required": ["name"]
    }
            },
            "schedule_task": {
                "description": "创建定时任务",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "任务名称"},
                        "task_type": {"type": "string", "description": "任务类型：wechat_message/macro/system_command"},
                        "schedule_type": {"type": "string", "description": "调度类型：daily/weekly/once/interval"},
                        "time": {"type": "string", "description": "执行时间，如 09:00"},
                        "params": {"type": "object", "description": "任务参数"}
                    },
                    "required": ["name", "task_type", "schedule_type", "time"]
    }
            },
            "file_operation": {
                "description": "执行文件操作",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string", "description": "操作类型：copy/move/delete/rename/mkdir"},
                        "source": {"type": "string", "description": "源文件路径"},
                        "destination": {"type": "string", "description": "目标路径"}
                    },
                    "required": ["operation"]
    }
            },
            "http_request": {
                "description": "发送HTTP请求",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "请求URL"},
                        "method": {"type": "string", "description": "请求方法：GET/POST/PUT/DELETE"},
                        "data": {"type": "object", "description": "请求数据"}
                    },
                    "required": ["url"]
    }
            },
            "run_python": {
                "description": "执行Python代码",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python代码"}
                    },
                    "required": ["code"]
    }
            },
            "open_app": {
                "description": "打开应用程序",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "应用名称或路径"}
                    },
                    "required": ["app_name"]
    }
            },
            "click_image": {
                "description": "在屏幕上查找并点击图像",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "图像文件路径"},
                        "confidence": {"type": "number", "description": "匹配置信度，默认0.9"},
                        "timeout": {"type": "integer", "description": "超时时间（秒），默认10"}
                    },
                    "required": ["image_path"]
    }
            },
            # 新增系统控制工具描述
            "control_volume": {
                "description": "控制电脑音量",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "操作类型: get(获取当前音量)/up(增大)/down(减小)/set(设置音量)/toggle_mute(切换静音)"},
                        "level": {"type": "integer", "description": "音量级别(0-100)，当action='set'时使用"},
                        "steps": {"type": "integer", "description": "步数(每步约2%)，当action='up'或'down'时使用，默认5"},
                        "mute": {"type": "boolean", "description": "静音状态，当action='set'时使用"}
                    },
                    "required": ["action"]
    }
            },
            "control_network": {
                "description": "控制网络连接",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "操作类型: get_info(获取网络信息)/toggle_wifi(切换Wi-Fi)/get_wifi(获取Wi-Fi状态)"},
                        "enable": {"type": "boolean", "description": "开启/关闭Wi-Fi，当action='toggle_wifi'时使用"}
                    },
                    "required": ["action"]
    }
            },
            "manage_processes": {
                "description": "管理系统进程",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "操作类型: list(列出进程)/kill(结束指定PID进程)/kill_by_name(结束指定名称进程)"},
                        "filter_str": {"type": "string", "description": "过滤字符串，当action='list'时使用"},
                        "pid": {"type": "integer", "description": "进程ID，当action='kill'时使用"},
                        "process_name": {"type": "string", "description": "进程名，当action='kill_by_name'时使用"},
                        "force": {"type": "boolean", "description": "是否强制结束，默认false"}
                    },
                    "required": ["action"]
    }
            },
            "manage_windows": {
                "description": "管理应用程序窗口",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "操作类型: list(列出窗口)/find(查找窗口)/activate(激活窗口)/minimize(最小化窗口)/maximize(最大化窗口)/close(关闭窗口)"},
                        "title_pattern": {"type": "string", "description": "窗口标题模式(支持模糊匹配)，当action不是'list'时使用"},
                        "filter_str": {"type": "string", "description": "过滤字符串，当action='list'时使用"}
                    },
                    "required": ["action"]
    }
            },
            "take_screenshot": {
                "description": "截取屏幕",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "region": {"type": "array", "description": "截图区域[left, top, width, height]，空表示全屏"},
                        "save_path": {"type": "string", "description": "保存路径，空表示保存到临时文件"}
                    },
                    "required": []
    }
            },
            "control_clipboard": {
                "description": "控制剪贴板",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "操作类型: get(获取剪贴板内容)/set(设置剪贴板内容)/clear(清空剪贴板)"},
                        "content": {"type": "string", "description": "要设置的内容，当action='set'时使用"}
                    },
                    "required": ["action"]
    }
            },
            "system_info": {
                "description": "获取系统信息(CPU、内存、磁盘、网络等)",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
    }
            },
            "speak_text": {
                "description": "语音合成(文本转语音)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要合成的文本"},
                        "rate": {"type": "integer", "description": "语速(默认150)"},
                        "volume": {"type": "number", "description": "音量(0.0-1.0，默认1.0)"}
                    },
                    "required": ["text"]
    }
            },
            "ocr_screen": {
                "description": "识别屏幕区域的文字(OCR)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "region": {"type": "array", "description": "屏幕区域[left, top, width, height]，空表示全屏"},
                        "lang": {"type": "string", "description": "语言代码(默认chi_sim+eng)"}
                    },
                    "required": []
    }
    }
    }

    def _setup_tool_descriptions(self):
        """工具描述(从 TOOL_DESCRIPTIONS 类常量加载)"""
        self.tool_descriptions = TOOL_DESCRIPTIONS


    def plan_task(self, user_command):
        """使用LLM将用户指令分解为可执行步骤"""
        self._publish_event("plan.started", {"command": user_command})
        # 根据用户指令选择相关的工具类别，动态构建提示词
        prompt = self._build_planning_prompt(user_command)

        try:
            response = self._call_llm(prompt)
            steps = self._parse_steps(response)
            logger.info(f"任务规划完成，共{len(steps)}个步骤")
            self._publish_event("plan.completed", {"command": user_command, "steps_count": len(steps)})
            return steps
        except Exception as e:
            logger.error(f"任务规划失败: {e}")
            self._publish_event("plan.failed", {"command": user_command, "error": str(e)})
            return []

    def _build_planning_prompt(self, user_command):
        """构建任务规划提示词，根据用户指令动态选择相关工具"""
        # 定义工具类别和关键字映射
        tool_categories = self._TOOL_CATEGORIES

        # 根据用户指令确定相关工具类别
        user_command_lower = user_command.lower()
        relevant_categories = []

        for category_name, category_info in tool_categories.items():
            if any(keyword in user_command_lower for keyword in category_info["keywords"]):
                relevant_categories.append(category_name)

        # 如果没有匹配的类别，使用前3个最常见的类别
        if not relevant_categories:
            relevant_categories = ["搜索与信息收集", "文档与文件操作", "系统控制与自动化"]

        # 构建工具列表
        tools_list = []
        seen_tools = set()

        for category_name in relevant_categories[:3]:  # 最多3个类别，避免提示词过长
            if category_name in tool_categories:
                for tool_desc in tool_categories[category_name]["tools"]:
                    tool_name = tool_desc.split(" - ")[0]
                    if tool_name not in seen_tools:
                        tools_list.append(tool_desc)
                        seen_tools.add(tool_name)

        # 确保至少有一些工具
        if not tools_list:
            tools_list = [
                "collect_and_save - 搜索、整理并保存为文档",
                "send_wechat - 发送微信消息",
                "open_app - 打开应用程序"
            ]

        tools_text = "\n".join([f"- {tool}" for tool in tools_list])

        prompt = f"""将指令分解为步骤，输出JSON数组。

指令: {user_command}

可用工具:
{tools_text}

输出格式:
[{{"step":1,"tool":"工具名","action":"描述","parameters":{{}}}}]

示例:
[{{"step":1,"tool":"collect_and_save","action":"搜索XX并保存","parameters":{{"query":"XX","save_path":"C:\\\\Users\\\\Administrator\\\\Desktop\\\\XX.md","format":"markdown"}}}}]

只输出JSON，无其他内容。"""

        return prompt

    def _validate_params(self, tool, params):
        """验证工具参数是否完整"""
        if tool not in self.tool_descriptions:
            return None, f"未知工具: {tool}"

        tool_desc = self.tool_descriptions[tool]
        required_params = tool_desc.get("parameters", {}).get("required", [])

        missing_params = []
        for param in required_params:
            if param not in params or params[param] is None or params[param] == "":
                missing_params.append(param)

        if missing_params:
            return None, f"缺少必需参数: {', '.join(missing_params)}"

        return True, None

    def execute_plan(self, steps, context=None):
        """执行任务计划"""
        self._publish_event("execute.started", {"steps_count": len(steps)})
        results = []
        context = context or {}

        for step in steps:
            try:
                tool = step.get("tool")
                params = step.get("parameters", {})

                logger.info(f"执行步骤 {step.get('step')}: {step.get('action')}")
                step_info = f"步骤 {step.get('step')}: {step.get('action')}"
                self._send_feedback(f"▶ {step_info}", is_error=False)

                if tool in self.tools:
                    valid, error = self._validate_params(tool, params)
                    if not valid:
                        results.append({
                            "step": step.get('step'),
                            "tool": tool,
                            "action": step.get('action'),
                            "success": False,
                            "error": error
                        })
                        self._send_feedback(f"❌ {step_info} - {error}", is_error=True)
                        continue

                    result = self.tools[tool](**params)
                    results.append({
                        "step": step.get('step'),
                        "tool": tool,
                        "action": step.get('action'),
                        "success": True,
                        "result": result,
                        "context": context
                    })
                    context[f"step_{step.get('step')}_result"] = result
                    self._send_feedback(f"✅ {step_info} - 执行成功", is_error=False)
                else:
                    error_msg = f"未知工具: {tool}"
                    results.append({
                        "step": step.get('step'),
                        "tool": tool,
                        "action": step.get('action'),
                        "success": False,
                        "error": error_msg
                    })
                    self._send_feedback(f"❌ {step_info} - {error_msg}", is_error=True)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"步骤执行失败: {e}")
                results.append({
                    "step": step.get('step'),
                    "tool": step.get('tool'),
                    "action": step.get('action'),
                    "success": False,
                    "error": error_msg
                })
                step_info = f"步骤 {step.get('step')}: {step.get('action')}"
                self._send_feedback(f"❌ {step_info} - {error_msg}", is_error=True)

        success_count = sum(1 for r in results if r.get("success"))
        self._publish_event("execute.completed", {
            "steps_count": len(steps),
            "success_count": success_count,
            "failed_count": len(steps) - success_count
        })
        return results

    def _call_llm(self, prompt, max_retries=3):
        """调用LLM API"""
        # 如果提供了ai_helper，使用统一API客户端
        if self.ai_helper:
            for attempt in range(max_retries):
                try:
                    result = self.ai_helper.ai_query(prompt)
                    if result:
                        return result
                    else:
                        logger.warning(f"AI helper返回空结果，尝试 {attempt+1}/{max_retries}")
                        time.sleep(2 ** attempt)
                except Exception as e:
                    logger.warning(f"AI helper调用异常: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            return ""

        # 否则回退到旧的Ollama API
        if not REQUESTS_AVAILABLE:
            logger.error("requests模块未安装，无法调用LLM API")
            return ""

        for attempt in range(max_retries):
            try:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                }
                response = requests.post(self.ollama_url, json=payload, timeout=60)
                if response.status_code == 200:
                    return response.json().get("response", "")
                else:
                    logger.warning(f"LLM调用失败，状态码: {response.status_code}")
                    time.sleep(2 ** attempt)
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"LLM连接失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"LLM调用异常: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return ""

    def _parse_steps(self, response):
        """解析LLM返回的步骤，支持多种格式"""
        import re, ast
        # 1. 直接解析
        try:
            return json.loads(response)
        except Exception:
            pass
        # 2. 提取 ```json ... ```
        match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        # 3. 提取 ``` ... ```（无语言标记）
        match = re.search(r'```([\s\S]*?)```', response)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        # 4. 提取第一个 [ ... ] 或 { ... }
        for pattern in [r'\[[\s\S]*\]', r'\{[\s\S]*\}']:
            match = re.search(pattern, response)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        # 5. 最后尝试 ast.literal_eval
        try:
            return ast.literal_eval(response.strip())
        except Exception:
            pass
        return []

    def search_browser(self, query, engine="baidu"):
        """浏览器搜索 - 增强版：搜索并收集结果"""
        try:
            search_url = f"https://www.baidu.com/s?wd={quote_plus(query)}"
            os.startfile(search_url)
            logger.info(f"已打开浏览器搜索: {query}")
            return f"已在浏览器中搜索: {query}"
        except Exception as e:
            logger.error(f"浏览器搜索失败: {e}")
            return f"搜索失败: {str(e)}"

    def search_and_collect(self, query, max_results=5):
        """搜索并收集信息，返回结构化数据（三层降级：DDGS -> 百度 -> 浏览器）"""
        self._publish_event("search.started", {"query": query, "max_results": max_results})
        try:
            # === 第一层：DuckDuckGo ===
            try:
                from duckduckgo_search import DDGS
                ddgs = DDGS()
                results = []
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
                if results:
                    logger.info(f"DDGS搜索完成: {query}, {len(results)}条")
                    self._publish_event("search.completed", {"query": query, "count": len(results), "source": "duckduckgo"})
                    return {"success": True, "query": query, "count": len(results), "results": results, "source": "duckduckgo"}
            except Exception as ddgs_err:
                logger.warning(f"DDGS搜索失败: {ddgs_err}")

            # === 第二层：百度搜索 ===
            try:
                import html as html_mod
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                bd_url = f"https://www.baidu.com/s?wd={quote_plus(query)}&rn={max_results}"
                resp = requests.get(bd_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    results = []
                    for item in soup.select('.result.c-container, .c-container'):
                        title_elem = item.select_one('h3 a')
                        url_elem = title_elem.get('href') if title_elem else None
                        title = title_elem.get_text(strip=True) if title_elem else ''
                        snippet_elem = item.select_one('.c-span-last, .content-right_8Zs40')
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                        if title and url_elem:
                            results.append({
                                "title": html_mod.unescape(title),
                                "url": url_elem,
                                "snippet": html_mod.unescape(snippet)
                            })
                        if len(results) >= max_results:
                            break
                    if results:
                        logger.info(f"百度搜索完成: {query}, {len(results)}条")
                        self._publish_event("search.completed", {"query": query, "count": len(results), "source": "baidu"})
                        return {"success": True, "query": query, "count": len(results), "results": results, "source": "baidu"}
            except Exception as bd_err:
                logger.warning(f"百度搜索失败: {bd_err}")

            # === 第三层：打开浏览器 ===
            search_url = f"https://www.baidu.com/s?wd={quote_plus(query)}"
            try:
                os.startfile(search_url)
            except:
                search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
                os.startfile(search_url)
            self._publish_event("search.completed", {"query": query, "count": 0, "source": "browser", "note": "已打开浏览器"})
            return {
                "success": True, "query": query,
                "note": "搜索引擎不可用，已在浏览器中打开搜索页面",
                "search_url": search_url
            }
        except Exception as e:
            logger.error(f"搜索并收集失败: {e}")
            self._publish_event("search.failed", {"query": query, "error": str(e)})
            return {"success": False, "error": str(e)}

    def collect_and_save(self, query, save_path, format="markdown", max_results=10):
        """搜索、收集信息并保存为文档

        Args:
            query: 搜索关键词
            save_path: 保存路径
            format: 文档格式 (markdown/txt/json)
            max_results: 最大搜索结果数

        Returns:
            保存结果
        """
        try:
            search_result = self.search_and_collect(query, max_results)
            if not search_result.get("success"):
                return search_result

            note = search_result.get("note")
            results = search_result.get("results", [])

            # AI summary
            ai_summary = None
            if results and self.ai_helper:
                ai_summary = self.ai_helper.ai_query(
                    self._build_summarize_prompt(query, results))

            content = self._build_collect_content(query, results, ai_summary, note)
            return self.save_document(save_path, content)
        except Exception as e:
            logger.error(f"收集并保存失败: {e}")
            return {"success": False, "error": str(e)}

    def _build_summarize_prompt(self, query, results):
        """构建AI摘要提示"""
        prompt = f"""请整理以下搜索结果，提取关键信息，生成一份简洁的摘要。

搜索关键词：{query}

搜索结果：
"""
        for i, r in enumerate(results, 1):
            prompt += f"\n{i}. {r.get("title", "")}\n"
            prompt += f"   来源: {r.get("url", "")}\n"
            prompt += f"   内容: {r.get("snippet", "")}\n"
        prompt += """

请生成一份结构化的摘要，包括：
1. 概述（用一句话概括搜索主题）
2. 关键要点（3-5个）
3. 每个搜索结果的核心信息
4. 相关链接列表

请用中文回复。"""
        return prompt

    def _build_collect_content(self, query, results, ai_summary=None, note=None):
        """构建收集结果的文档内容"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if note:
            content = f"# {query}\n\n"
            content += f"*搜索时间: {timestamp}*\n\n"
            content += f"## 说明\n\n{note}\n\n"
            content += "**提示**: 由于未安装duckduckgo_search库，已直接在浏览器中打开搜索页面。\n"
            content += "请查看搜索结果后，手动保存需要的信息。\n\n"
            content += f"搜索链接: https://www.bing.com/search?q={quote_plus(query)}\n"
            return content

        if not results:
            content = f"# {query}\n\n"
            content += f"*搜索时间: {timestamp}*\n\n"
            content += "## 搜索结果\n\n未找到相关结果。\n\n"
            content += f"**搜索关键词**: {query}\n"
            return content

        if ai_summary:
            content = f"# {query}\n\n"
            content += f"*搜索时间: {timestamp}*\n\n"
            content += ai_summary
            content += "\n\n---\n\n"
            content += "## 参考来源\n\n"
            for r in results:
                content += f"- [{r.get("title", "无标题")}]({r.get("url", "")})\n"
            return content

        # Raw results without AI summary
        content = f"# {query} - 搜索结果\n\n"
        content += f"*搜索时间: {timestamp}*\n\n"
        for i, r in enumerate(results, 1):
            content += f"## {i}. {r.get("title", "无标题")}\n"
            content += f"来源: {r.get("url", "")}\n\n"
            content += f"{r.get("snippet", "")}\n\n"
        return content

    def send_wechat_message(self, target, message):
        """发送微信消息"""
        if self._wechat_controller:
            try:
                success = self._wechat_controller.send_wechat_message(target, message)
                if success:
                    logger.info(f"微信消息发送成功: 给 {target} 的消息")
                    return {"success": True, "message": f"已发送消息给 {target}"}
                else:
                    logger.error(f"微信消息发送失败: 给 {target}")
                    return {"success": False, "error": "发送失败"}
            except Exception as e:
                logger.error(f"发送微信消息异常: {e}")
                return {"success": False, "error": str(e)}
        else:
            logger.warning("未设置微信控制器")
            return {"success": False, "error": "未配置微信控制器"}

    def execute_command(self, command):
        """执行系统命令"""
        if self._command_executor:
            try:
                result = self._command_executor(command)
                return result
            except Exception as e:
                logger.error(f"执行命令异常: {e}")
                return {"success": False, "error": str(e)}
        else:
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    def save_document(self, path, content):
        """保存文档"""
        try:
            filepath = Path(path)
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"文档已保存: {path}")
            return {"success": True, "path": str(filepath)}
        except Exception as e:
            logger.error(f"保存文档失败: {e}")
            return {"success": False, "error": str(e)}

    def set_wechat_controller(self, wechat_controller):
        """设置微信控制器"""
        self._wechat_controller = wechat_controller
        logger.info("微信控制器已设置")

    def set_command_executor(self, executor_func):
        """设置命令执行器"""
        self._command_executor = executor_func
        logger.info("命令执行器已设置")

    def set_macro_player(self, player):
        """设置宏播放器"""
        self._macro_player = player
        logger.info("宏播放器已设置")

    def set_macro_recorder(self, recorder):
        """设置宏录制器"""
        self._macro_recorder = recorder
        logger.info("宏录制器已设置")

    def set_task_scheduler(self, scheduler):
        """设置任务调度器"""
        self._task_scheduler = scheduler
        logger.info("任务调度器已设置")

    def play_macro(self, macro_name, speed=1.0, repeat=1):
        """播放宏"""
        try:
            if self._macro_player:
                success = self._macro_player.play(macro_name, speed=speed, repeat=repeat)
            else:
                from modules.macro_recorder import get_player
                player = get_player()
                success = player.play(macro_name, speed=speed, repeat=repeat)

            if success:
                logger.info(f"宏播放成功: {macro_name}")
                return {"success": True, "message": f"宏 {macro_name} 播放完成"}
            else:
                return {"success": False, "error": "宏播放失败"}
        except Exception as e:
            logger.error(f"播放宏失败: {e}")
            return {"success": False, "error": str(e)}

    def record_macro(self, name):
        """开始录制宏"""
        try:
            if self._macro_recorder:
                self._macro_recorder.start_recording(name)
            else:
                from modules.macro_recorder import get_recorder
                recorder = get_recorder()
                recorder.start_recording(name)

            logger.info(f"开始录制宏: {name}")
            return {"success": True, "message": f"开始录制宏 {name}，请进行操作后手动停止"}
        except Exception as e:
            logger.error(f"开始录制宏失败: {e}")
            return {"success": False, "error": str(e)}

    def schedule_task(self, name, task_type, schedule_type, time, params=None):
        """创建定时任务"""
        try:
            if self._task_scheduler:
                schedule_config = {
                    "type": schedule_type,
                    "time": time
                }
                task_id = self._task_scheduler.add_task(
                    name=name,
                    task_type=task_type,
                    schedule_config=schedule_config,
                    params=params or {}
                )
                logger.info(f"创建定时任务: {name}")
                return {"success": True, "task_id": task_id, "message": f"任务 {name} 已创建"}
            else:
                return {"success": False, "error": "任务调度器未设置"}
        except Exception as e:
            logger.error(f"创建定时任务失败: {e}")
            return {"success": False, "error": str(e)}

    def file_operation(self, operation, source=None, destination=None):
        """执行文件操作（含路径安全校验）"""
        import shutil

        # 路径安全校验：禁止访问系统关键目录
        _FORBIDDEN_PREFIXES = (
            os.environ.get('SystemRoot', r'C:\Windows').lower(),
            r'c:\program files',
            r'c:\programdata',
            r'c:\program files (x86)',
        )

        def _is_safe(p):
            if not p:
                return True
            real = os.path.realpath(p).lower()
            for prefix in _FORBIDDEN_PREFIXES:
                if real.startswith(prefix):
                    return False
            return True

        if not _is_safe(source) or not _is_safe(destination):
            return {"success": False, "error": "路径不安全：禁止操作系统目录"}

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
                return {"success": False, "error": f"未知操作: {operation}"}

            logger.info(f"文件操作成功: {operation}")
            return {"success": True, "message": f"文件操作 {operation} 完成"}
        except Exception as e:
            logger.error(f"文件操作失败: {e}")
            return {"success": False, "error": str(e)}

    def http_request(self, url, method="GET", data=None):
        """发送HTTP请求"""
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, json=data, timeout=30)
            elif method.upper() == "PUT":
                response = requests.put(url, json=data, timeout=30)
            elif method.upper() == "DELETE":
                response = requests.delete(url, timeout=30)
            else:
                return {"success": False, "error": f"不支持的请求方法: {method}"}

            logger.info(f"HTTP请求成功: {method} {url}")
            return {
                "success": True,
                "status_code": response.status_code,
                "content": response.text[:1000] if len(response.text) > 1000 else response.text
            }
        except Exception as e:
            logger.error(f"HTTP请求失败: {e}")
            return {"success": False, "error": str(e)}

    def run_python_code(self, code):
        """执行Python代码（受限沙箱）"""
        # 安全：限制 builtins，禁止危险操作
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
        try:
            exec_globals = {"__builtins__": {k: __builtins__[k] for k in safe_builtins if k in __builtins__}}
            exec_locals = {}
            exec(code, exec_globals, exec_locals)
            logger.info("Python代码执行成功")
            return {"success": True, "message": "代码执行成功", "locals": str(exec_locals)[:500]}
        except Exception as e:
            logger.error(f"Python代码执行失败: {e}")
            return {"success": False, "error": str(e)}

    def open_application(self, app_name):
        """打开应用程序"""
        try:
            common_apps = {
                "记事本": "notepad",
                "计算器": "calc",
                "画图": "mspaint",
                "浏览器": "explorer",
                "资源管理器": "explorer",
                "命令提示符": "cmd",
                "控制面板": "control",
                "微信": r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
            }

            app_path = common_apps.get(app_name, app_name)

            if os.path.exists(app_path):
                os.startfile(app_path)
            else:
                os.startfile(app_path)

            logger.info(f"打开应用程序: {app_name}")
            return {"success": True, "message": f"已打开 {app_name}"}
        except Exception as e:
            logger.error(f"打开应用程序失败: {e}")
            return {"success": False, "error": str(e)}

    def click_image(self, image_path, confidence=0.9, timeout=10):
        """在屏幕上查找并点击图像"""
        if not PYAUTOGUI_AVAILABLE:
            logger.error("pyautogui模块未安装，无法执行图像点击。请运行: pip install pyautogui")
            return {"success": False, "error": "pyautogui模块未安装，无法执行图像点击。请运行: pip install pyautogui"}

        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    location = pyautogui.locateOnScreen(image_path, confidence=confidence)
                    if location:
                        center = pyautogui.center(location)
                        pyautogui.click(center.x, center.y)
                        logger.info(f"图像点击成功: {image_path}")
                        return {"success": True, "message": f"已点击图像位置: ({center.x}, {center.y})"}
                except Exception:
                    pass
                time.sleep(0.5)

            logger.warning(f"图像查找超时: {image_path}")
            return {"success": False, "error": "未找到图像"}
        except Exception as e:
            logger.error(f"图像点击失败: {e}")
            return {"success": False, "error": str(e)}

    # ===== 新增系统控制方法 =====

    def control_volume(self, action="get", level=50, steps=5, mute=None):
        """控制音量

        Args:
            action: 操作类型 (get/up/down/set/toggle_mute)
            level: 音量级别 (0-100)，当action='set'时使用
            steps: 步数，当action='up'或'down'时使用
            mute: 静音状态，当action='set'时使用

        Returns:
            操作结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            if action == "get":
                return self._system_controller.get_volume()
            elif action == "up":
                return self._system_controller.volume_up(steps)
            elif action == "down":
                return self._system_controller.volume_down(steps)
            elif action == "set":
                return self._system_controller.set_volume(level, mute)
            elif action == "toggle_mute":
                return self._system_controller.toggle_mute()
            else:
                return {"success": False, "error": f"未知音量操作: {action}"}
        except Exception as e:
            return {"success": False, "error": f"音量控制失败: {str(e)}"}

    def control_network(self, action="get_info", enable=None):
        """控制网络

        Args:
            action: 操作类型 (get_info/toggle_wifi/get_wifi)
            enable: 开启/关闭Wi-Fi，当action='toggle_wifi'时使用

        Returns:
            操作结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            if action == "get_info":
                return self._system_controller.get_network_info()
            elif action == "toggle_wifi":
                return self._system_controller.toggle_wifi(enable)
            elif action == "get_wifi":
                return self._system_controller.get_wifi_status()
            else:
                return {"success": False, "error": f"未知网络操作: {action}"}
        except Exception as e:
            return {"success": False, "error": f"网络控制失败: {str(e)}"}

    def manage_processes(self, action="list", filter_str="", pid=None, process_name=None, force=False):
        """管理进程

        Args:
            action: 操作类型 (list/kill/kill_by_name)
            filter_str: 过滤字符串，当action='list'时使用
            pid: 进程ID，当action='kill'时使用
            process_name: 进程名，当action='kill_by_name'时使用
            force: 是否强制结束

        Returns:
            操作结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            if action == "list":
                return self._system_controller.list_processes(filter_str)
            elif action == "kill":
                if pid is None:
                    return {"success": False, "error": "需要指定进程ID"}
                return self._system_controller.kill_process(pid, force)
            elif action == "kill_by_name":
                if process_name is None:
                    return {"success": False, "error": "需要指定进程名"}
                return self._system_controller.kill_process_by_name(process_name, force)
            else:
                return {"success": False, "error": f"未知进程操作: {action}"}
        except Exception as e:
            return {"success": False, "error": f"进程管理失败: {str(e)}"}

    def manage_windows(self, action="list", title_pattern="", filter_str=""):
        """管理窗口

        Args:
            action: 操作类型 (list/find/activate/minimize/maximize/close)
            title_pattern: 窗口标题模式
            filter_str: 过滤字符串，当action='list'时使用

        Returns:
            操作结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            if action == "list":
                return self._system_controller.list_windows(filter_str)
            elif action == "find":
                if not title_pattern:
                    return {"success": False, "error": "需要指定窗口标题"}
                return self._system_controller.find_window(title_pattern)
            elif action == "activate":
                if not title_pattern:
                    return {"success": False, "error": "需要指定窗口标题"}
                return self._system_controller.activate_window(title_pattern)
            elif action == "minimize":
                if not title_pattern:
                    return {"success": False, "error": "需要指定窗口标题"}
                return self._system_controller.minimize_window(title_pattern)
            elif action == "maximize":
                if not title_pattern:
                    return {"success": False, "error": "需要指定窗口标题"}
                return self._system_controller.maximize_window(title_pattern)
            elif action == "close":
                if not title_pattern:
                    return {"success": False, "error": "需要指定窗口标题"}
                return self._system_controller.close_window(title_pattern)
            else:
                return {"success": False, "error": f"未知窗口操作: {action}"}
        except Exception as e:
            return {"success": False, "error": f"窗口管理失败: {str(e)}"}

    def take_screenshot(self, region=None, save_path=None):
        """截取屏幕

        Args:
            region: 截图区域 (left, top, width, height)，None表示全屏
            save_path: 保存路径，None表示保存到临时文件

        Returns:
            截图结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            return self._system_controller.take_screenshot(region, save_path)
        except Exception as e:
            return {"success": False, "error": f"截图失败: {str(e)}"}

    def control_clipboard(self, action="get", content=""):
        """控制剪贴板

        Args:
            action: 操作类型 (get/set/clear)
            content: 要设置的内容，当action='set'时使用

        Returns:
            操作结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            if action == "get":
                return self._system_controller.get_clipboard()
            elif action == "set":
                if not content:
                    return {"success": False, "error": "需要指定内容"}
                return self._system_controller.set_clipboard(content)
            elif action == "clear":
                return self._system_controller.clear_clipboard()
            else:
                return {"success": False, "error": f"未知剪贴板操作: {action}"}
        except Exception as e:
            return {"success": False, "error": f"剪贴板控制失败: {str(e)}"}

    def get_system_info(self):
        """获取系统信息

        Returns:
            系统信息
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            return self._system_controller.get_system_info()
        except Exception as e:
            return {"success": False, "error": f"获取系统信息失败: {str(e)}"}

    def speak_text(self, text, rate=150, volume=1.0):
        """语音合成

        Args:
            text: 要合成的文本
            rate: 语速 (默认150)
            volume: 音量 (0.0-1.0)

        Returns:
            操作结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            return self._system_controller.speak_text(text, rate, volume)
        except Exception as e:
            return {"success": False, "error": f"语音合成失败: {str(e)}"}

    def ocr_screen(self, region=None, lang="chi_sim+eng"):
        """识别屏幕区域的文字

        Args:
            region: 屏幕区域
            lang: 语言代码

        Returns:
            识别结果
        """
        if not self._system_controller:
            return {"success": False, "error": "系统控制器未加载"}

        try:
            return self._system_controller.ocr_screen(region, lang)
        except Exception as e:
            return {"success": False, "error": f"OCR识别失败: {str(e)}"}


class BrowserAutomation:
    """浏览器自动化模块 - 增强版"""
import subprocess

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    webdriver = None
    Service = None
    ChromeDriverManager = None


    def __init__(self):
        self.search_results = []
        self.driver = None
        self._selenium_available = None

    def _check_selenium(self):
        if self._selenium_available is None:
            try:
                self._selenium_available = True
            except ImportError:
                self._selenium_available = False
        return self._selenium_available

    def search(self, query, engine="baidu"):
        """通用搜索引擎搜索"""
        search_engines = {
            "baidu": f"https://www.baidu.com/s?wd={quote_plus(query)}",
            "google": f"https://www.google.com/search?q={quote_plus(query)}",
            "bing": f"https://www.bing.com/search?q={quote_plus(query)}"
        }

        url = search_engines.get(engine, search_engines["baidu"])

        try:
            os.startfile(url)
            logger.info(f"已打开{engine}搜索: {query}")
            return {"success": True, "url": url}
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"success": False, "error": str(e)}

    @contextmanager
    def selenium_session(self, browser="chrome"):
        """Selenium会话上下文管理器"""
        if not self._check_selenium():
            raise ImportError("Selenium未安装，请运行: pip install selenium webdriver-manager")


        driver = None
        try:
            if browser == "chrome":
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service)
            elif browser == "firefox":
                from webdriver_manager.firefox import GeckoDriverManager
                from selenium.webdriver.firefox.service import Service
                service = Service(GeckoDriverManager().install())
                driver = webdriver.Firefox(service=service)

            self.driver = driver
            yield driver
        finally:
            if driver:
                driver.quit()
            self.driver = None

    def get_page(self, url, use_selenium=False):
        """获取网页内容"""
        if use_selenium and self._check_selenium():
            with self.selenium_session() as driver:
                driver.get(url)
                time.sleep(2)
                return {
                    "success": True,
                    "content": driver.page_source,
                    "url": driver.current_url
                }
        else:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=10)
                return {
                    "success": True,
                    "content": response.text,
                    "url": response.url
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    def extract_page_content(self, url):
        """提取网页内容（需要安装selenium）"""
        try:

            with self.selenium_session() as driver:
                driver.get(url)
                time.sleep(2)

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)

                return {"success": True, "content": text[:5000]}
        except ImportError:
            return {"success": False, "error": "需要安装: pip install selenium beautifulsoup4 webdriver-manager"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None


class DocumentOrganizer:
    """文档整理模块"""

    def __init__(self, output_dir=None):
        self.output_dir = output_dir or Path.home() / "Documents" / "AI_整理文档"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_summary_document(self, title, sections):
        """创建摘要文档"""
        content = f"""# {title}

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

"""

        for section in sections:
            content += f"## {section.get('title', '无标题')}\n\n"
            content += section.get('content', '') + "\n\n---\n\n"

        filename = f"{self._sanitize_filename(title)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"摘要文档已创建: {filepath}")
        return str(filepath)

    def create_table_document(self, title, headers, rows):
        """创建表格文档"""
        content = f"""# {title}

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

| {' | '.join(headers)} |
|{'---|' * len(headers)}
"""

        for row in rows:
            content += f"| {' | '.join(str(cell) for cell in row)} |\n"

        filename = f"{self._sanitize_filename(title)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"表格文档已创建: {filepath}")
        return str(filepath)

    def organize_search_results(self, query, results):
        """整理搜索结果为文档"""
        sections = []
        for i, result in enumerate(results[:10], 1):
            sections.append({
                "title": f"结果 {i}: {result.get('title', '无标题')}",
                "content": result.get('snippet', result.get('content', '无内容'))
            })

        return self.create_summary_document(f"搜索结果: {query}", sections)

    def _sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        return filename[:50]


class TaskExecutor:
    """任务执行器"""

    def __init__(self):
        self.wechat_controller = None

    def execute_command(self, command):
        """执行系统命令"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def open_app(self, app_path):
        """打开应用程序"""
        try:
            os.startfile(app_path)
            return {"success": True, "message": f"已打开: {app_path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_wechat(self, target, message):
        """发送微信消息"""
        if self.wechat_controller:
            success = self.wechat_controller.send_wechat_message(target, message)
            return {"success": success}
        return {"success": False, "error": "未设置微信控制器"}


_ai_agent_instance = None
_browser_instance = None
_doc_org_instance = None


def get_ai_agent(ai_helper=None, config_manager=None, **kwargs):
    """获取 AIAgent 单例实例

    Args:
        ai_helper: AIHelper 实例（可选，支持依赖注入）
        config_manager: 配置管理器实例（可选）
        **kwargs: 其他参数（ollama_url, model 等，向后兼容）

    Returns:
        AIAgent 实例
    """
    global _ai_agent_instance
    if _ai_agent_instance is None:
        _ai_agent_instance = AIAgent(
            ai_helper=ai_helper,
            config_manager=config_manager,
            **kwargs
        )
    elif ai_helper is not None:
        # 如果实例已存在但需要更新 ai_helper
        _ai_agent_instance.ai_helper = ai_helper
        if hasattr(ai_helper, 'ollama_url'):
            _ai_agent_instance.ollama_url = ai_helper.ollama_url
        if hasattr(ai_helper, 'model'):
            _ai_agent_instance.model = ai_helper.model
    return _ai_agent_instance


def get_browser():
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = BrowserAutomation()
    return _browser_instance


def get_document_organizer(**kwargs):
    global _doc_org_instance
    if _doc_org_instance is None:
        _doc_org_instance = DocumentOrganizer(**kwargs)
    return _doc_org_instance
