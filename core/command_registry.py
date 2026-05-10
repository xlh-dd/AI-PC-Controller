"""
命令注册表 — 重构 execute_ai_command 的 if-elif 链
将 99 个命令动作拆分为独立的处理器函数
"""
import logging
from typing import Dict, Callable, Any, Optional
from functools import wraps

logger = logging.getLogger("CommandRegistry")


class CommandRegistry:
    """命令注册表，管理 action -> handler 映射"""

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, action: str, description: str = ""):
        """装饰器：注册命令处理器"""

        def decorator(fn: Callable):
            self._handlers[action] = fn
            if description:
                self._descriptions[action] = description
            else:
                self._descriptions[action] = fn.__doc__ or ""
            return fn
        return decorator

    def register_handler(self, action: str, handler: Callable, description: str = ""):
        """直接注册处理器函数"""
        self._handlers[action] = handler
        self._descriptions[action] = description or handler.__doc__ or ""

    def execute(self, action: str, context, cmd_data: Dict) -> Any:
        """执行命令"""
        if action not in self._handlers:
            raise KeyError(f"未知命令: {action}")

        handler = self._handlers[action]
        try:
            # 注入 context (AIPCHelperV8 实例) 和 cmd_data
            return handler(context, cmd_data)
        except Exception as e:
            logger.error(f"命令执行失败 [{action}]: {e}", exc_info=True)
            raise

    def list_commands(self) -> Dict[str, str]:
        """返回所有注册的命令及描述"""
        return {action: self._descriptions.get(action, "") for action in self._handlers}

    def has_command(self, action: str) -> bool:
        """检查命令是否已注册"""
        return action in self._handlers


# 全局单例
_registry: Optional[CommandRegistry] = None


def get_registry() -> CommandRegistry:
    """获取全局命令注册表单例"""
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
    return _registry


def register_command(action: str, description: str = ""):
    """全局注册命令的装饰器"""
    return get_registry().register(action, description)


def execute_command(action: str, context, cmd_data: Dict) -> Any:
    """全局执行命令"""
    return get_registry().execute(action, context, cmd_data)


def list_commands() -> Dict[str, str]:
    """全局列出所有命令"""
    return get_registry().list_commands()


# ===== 内置命令注册 =====

def _register_builtin_commands():
    """注册内置命令（示例）"""
    registry = get_registry()
    
    # 1. open_app
    def cmd_open_app(context, cmd_data):
        """打开应用程序"""
        app = cmd_data.get("app_name")
        if app:
            context.open_app(app)
        else:
            context.say("系统", "无法识别要打开的应用。")
    registry.register_handler("open_app", cmd_open_app, "打开应用程序")
    
    # 2. open_file
    def cmd_open_file(context, cmd_data):
        """打开文件"""
        import subprocess
        file_path = cmd_data.get("file_path")
        if file_path:
            try:
                subprocess.Popen(['start', '', file_path], shell=True)
                context.say("系统", f"✅ 正在打开文件：{file_path}")
            except Exception as e:
                context.say("系统", f"❌ 打开文件失败：{str(e)}")
        else:
            context.say("系统", "无法识别要打开的文件路径。")
    registry.register_handler("open_file", cmd_open_file, "打开文件")
    
    # 3. open_folder
    def cmd_open_folder(context, cmd_data):
        """打开文件夹"""
        import subprocess
        folder_path = cmd_data.get("folder_path")
        if folder_path:
            try:
                subprocess.Popen(['explorer', folder_path])
                context.say("系统", f"✅ 正在打开文件夹：{folder_path}")
            except Exception as e:
                context.say("系统", f"❌ 打开文件夹失败：{str(e)}")
        else:
            context.say("系统", "无法识别要打开的文件夹路径。")
    registry.register_handler("open_folder", cmd_open_folder, "打开文件夹")
    
    # 4. sort_files
    def cmd_sort_files(context, cmd_data):
        """自动分类文件"""
        context.auto_sort_files()
    registry.register_handler("sort_files", cmd_sort_files, "自动分类文件")
    
    # 5. 更多命令可在此添加...
    
    # 6. 迁移自 main.py 的 elif 链命令
    try:
        from .command_registry_migrated import _register_migrated_commands
        _register_migrated_commands(registry)
    except ImportError as e:
        logger.warning(f"迁移命令注册失败: {e}")


# 自动注册内置命令（首次导入时）
_register_builtin_commands()
