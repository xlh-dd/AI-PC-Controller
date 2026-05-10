"""
MacroInterpreter - 宏脚本 DSL 解释器
把宏从"JSON 动作序列"升级为可编程脚本。
语法示例：
    打开微信
    等待(图像: "发送按钮.png", 超时=10)
    点击(图像: "输入框.png")
    输入("{clipboard}")
    发送()
    如果 图像存在("确认.png") 则
        点击(图像: "确认.png")
    否则
        等待(2)
    结束
"""
import re
import time
import logging
import threading
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger("MacroInterpreter")

# ── 虚拟机 ───────────────────────────────────────────────────────────────────

class MacroValue:
    """宏变量"""
    def __init__(self, value: Any, vtype: str = "str"):
        self.value = value
        self.type = vtype

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return f"MacroValue({self.value!r}, {self.type})"

    def as_int(self) -> int:
        try: return int(self.value)
        except: return 0

    def as_float(self) -> float:
        try: return float(self.value)
        except: return 0.0

    def as_str(self) -> str:
        return str(self.value)

    def as_bool(self) -> bool:
        if isinstance(self.value, bool):
            return self.value
        if isinstance(self.value, str):
            return self.value.lower() in ("true", "1", "yes", "是")
        return bool(self.value)


class MacroContext:
    """宏执行上下文（变量表）"""
    def __init__(self):
        self.variables: Dict[str, MacroValue] = {}
        self.clipboard = ""
        self.last_result: Optional[MacroValue] = None
        self._lock = threading.Lock()

    def set(self, name: str, value: Any, vtype: str = "str"):
        with self._lock:
            self.variables[name] = MacroValue(value, vtype)

    def get(self, name: str) -> MacroValue:
        with self._lock:
            return self.variables.get(name, MacroValue(""))

    def resolve(self, text: str) -> str:
        """把 {变量名} 替换成实际值"""
        def replacer(m):
            var_name = m.group(1).strip()
            return str(self.get(var_name).value)
        return re.sub(r"\{([^}]+)\}", replacer, text)


# ── 基础 Action ──────────────────────────────────────────────────────────────

@dataclass
class MacroAction:
    name: str
    params: Dict[str, Any]
    condition: Optional[str] = None  # "image" | "var" | "always"


@dataclass
class MacroInstruction:
    """一条指令"""
    type: str        # "action" | "if" | "while" | "for" | "assign" | "label" | "goto" | "wait"
    raw: str         # 原始文本
    action: Optional[MacroAction] = None
    # if / while
    condition_expr: Optional[str] = None
    then_block: List["MacroInstruction"] = None
    else_block: List["MacroInstruction"] = None
    # for
    for_var: Optional[str] = None
    for_range: Optional[range] = None
    for_block: Optional[List["MacroInstruction"]] = None
    # assign
    assign_var: Optional[str] = None
    assign_expr: Optional[str] = None
    # wait
    wait_seconds: Optional[float] = None
    wait_image: Optional[str] = None
    wait_timeout: Optional[float] = None


class BaseMacroBuiltIn:
    """内置宏动作基类"""

    def __init__(self, macro_vm: "MacroVM"):
        self.vm = macro_vm
        self.ctx = macro_vm.ctx

    def click(self, x=None, y=None, image=None, **kwargs) -> MacroValue:
        """点击（坐标或图像）"""
        if image:
            pos = self._wait_image(image, kwargs.get("timeout", 10))
            if pos:
                x, y = pos
            else:
                raise RuntimeError(f"未找到图像: {image}")
        if x is not None and y is not None:
            try:
                import pyautogui
                pyautogui.click(x, y)
            except Exception as e:
                raise RuntimeError(f"点击失败: {e}")
        return MacroValue("ok")

    def input_text(self, text: str, **kwargs) -> MacroValue:
        """输入文本"""
        resolved = self.ctx.resolve(text)
        try:
            import pyautogui
            pyautogui.write(resolved, **kwargs)
        except Exception as e:
            raise RuntimeError(f"输入失败: {e}")
        return MacroValue("ok")

    def press(self, key: str, **kwargs) -> MacroValue:
        """按键"""
        try:
            import pyautogui
            pyautogui.press(key)
        except Exception as e:
            raise RuntimeError(f"按键失败: {e}")
        return MacroValue("ok")

    def wait(self, seconds: float = None, image: str = None, timeout: float = 10) -> MacroValue:
        """等待（时间或图像出现）"""
        if image:
            pos = self._wait_image(image, timeout)
            return MacroValue(pos is not None)
        if seconds:
            time.sleep(seconds)
        return MacroValue("ok")

    def image_exists(self, image: str, timeout: float = 0) -> MacroValue:
        """图像是否存在"""
        if timeout > 0:
            pos = self._wait_image(image, timeout)
            return MacroValue(pos is not None)
        pos = self._find_image(image)
        return MacroValue(pos is not None)

    def get_clipboard(self) -> MacroValue:
        try:
            import pyperclip
            return MacroValue(pyperclip.paste())
        except:
            return MacroValue("")

    def _find_image(self, template_name: str) -> Optional[Tuple[int, int]]:
        """查找图像位置"""
        try:
            import pyautogui
            import os
            macro_dir = Path(__file__).parent.parent / "macros"
            template_path = str(macro_dir / "screenshots" / template_name)
            if not os.path.exists(template_path):
                # 在 screenshots 目录找
                for ext in ("", ".png", ".jpg"):
                    candidate = template_path + ext
                    if os.path.exists(candidate):
                        template_path = candidate
                        break
            if os.path.exists(template_path):
                pos = pyautogui.locateOnScreen(template_path, confidence=0.8)
                if pos:
                    return pyautogui.center(pos)
        except Exception as e:
            logger.warning(f"[MacroVM] _find_image error: {e}")
        return None

    def _wait_image(self, template_name: str, timeout: float) -> Optional[Tuple[int, int]]:
        """等待图像出现"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pos = self._find_image(template_name)
            if pos:
                return pos
            time.sleep(0.5)
        return None


# ── 虚拟机 ────────────────────────────────────────────────────────────────────

class MacroVM:
    """
    宏脚本虚拟机。
    解析 → AST → 执行。
    """

    # 保留关键字
    KEYWORDS = {
        "如果", "则", "否则", "结束", "否则如果",
        "当", "循环", "次", "范围",
        "点击", "输入", "按键", "等待", "发送",
        "复制", "粘贴", "截图", "移动到", "滚动",
    }

    def __init__(self, macros_dir: Optional[str] = None):
        self.macros_dir = macros_dir or str(Path.home() / "aipc_macros" / "scripts")
        self.ctx = MacroContext()
        self._builtin = BaseMacroBuiltIn(self)
        self._running = False
        self._stop_event = threading.Event()
        self._labels: Dict[str, int] = {}  # label -> instruction index

    # ── 解析 ───────────────────────────────────────────────────────────────

    def parse(self, script: str) -> List[MacroInstruction]:
        """把脚本文本解析成 AST"""
        lines = [l.strip() for l in script.splitlines() if l.strip() and not l.strip().startswith("#")]
        instructions = []
        i = 0
        while i < len(lines):
            line = lines[i]
            inst = self._parse_line(line, lines, i)
            if inst:
                instructions.append(inst)
                if inst.type == "label":
                    self._labels[inst.raw] = len(instructions) - 1
            i += 1
        return instructions

    def _parse_line(self, line: str, lines: List[str], idx: int) -> Optional[MacroInstruction]:
        """解析单行，返回 MacroInstruction"""
        # 赋值
        m = re.match(r"(.+?)\s*[=：:=]\s*(.+)", line)
        if m:
            return MacroInstruction(
                type="assign",
                raw=line,
                assign_var=m.group(1).strip(),
                assign_expr=m.group(2).strip(),
            )

        # 等待
        m = re.match(r"等待\s*[（(]?\s*(.+)", line)
        if m:
            args_str = m.group(1).rstrip(")")
            args = self._parse_call_args(args_str)
            if "图像" in args or "image" in args:
                return MacroInstruction(
                    type="wait_image",
                    raw=line,
                    wait_image=args.get("图像") or args.get("image"),
                    wait_seconds=float(args.get("秒", args.get("seconds", 1))),
                    wait_timeout=float(args.get("超时", args.get("timeout", 10))),
                )
            return MacroInstruction(
                type="wait",
                raw=line,
                wait_seconds=float(args.get("秒", args.get("seconds", 1))),
            )

        # 如果
        if re.match(r"如果\s+", line):
            # 找对应的 "则" / "否则" / "结束"
            then_block, else_block, new_idx = self._collect_block(lines, idx + 1, "则", "否则", "结束")
            cond = re.sub(r"如果\s+", "", line).rstrip("则").strip()
            return MacroInstruction(
                type="if",
                raw=line,
                condition_expr=cond,
                then_block=then_block,
                else_block=else_block,
            )

        # 标签
        m = re.match(r"标签\s+(.+)", line)
        if m:
            return MacroInstruction(type="label", raw=m.group(1).strip())

        # 跳转
        if re.match(r"跳转\s+", line):
            target = re.sub(r"跳转\s+", "", line).strip()
            return MacroInstruction(type="goto", raw=target)

        # 循环
        m = re.match(r"循环\s+(\d+)\s*次", line)
        if m:
            count = int(m.group(1))
            block, _, new_idx = self._collect_block(lines, idx + 1, "结束")
            return MacroInstruction(
                type="for",
                raw=line,
                for_range=range(count),
                for_block=block,
            )

        # 普通动作调用
        m = re.match(r"(.+?)\s*[（(](.*?)[）)]$", line)
        if m:
            action_name = m.group(1).strip()
            args_str = m.group(2)
            args = self._parse_call_args(args_str)
            return MacroInstruction(
                type="action",
                raw=line,
                action=MacroAction(name=action_name, params=args),
            )

        # 无参动作
        return MacroInstruction(
            type="action",
            raw=line,
            action=MacroAction(name=line, params={}),
        )

    def _parse_call_args(self, args_str: str) -> Dict[str, str]:
        """解析参数串 'key1: value1, key2: value2' 或 'value'"""
        args_str = args_str.strip().rstrip(",").rstrip("；")
        if not args_str:
            return {}
        # 尝试 key: value 格式
        kv = re.findall(r"([^:,，:=]+?)\s*[:：=]\s*([^:,，]+)", args_str)
        if kv:
            return {k.strip(): v.strip() for k, v in kv}
        # 纯值格式
        return {"_": args_str.strip()}

    def _collect_block(self, lines: List[str], start: int,
                       *enders: str) -> Tuple[List[MacroInstruction], Optional[List[MacroInstruction]], int]:
        """收集代码块直到遇到 ender，返回 (block, else_block, end_idx)"""
        block = []
        else_block = None
        i = start
        while i < len(lines):
            line = lines[i].strip()
            if line in enders:
                return block, else_block, i
            if line == "否则":
                # 切换到 else 块
                i += 1
                while i < len(lines):
                    l2 = lines[i].strip()
                    if l2 == "结束":
                        break
                    sub = self._parse_line(l2, lines, i)
                    if sub:
                        (else_block or block).append(sub)
                    i += 1
                return block, else_block or block, i
            inst = self._parse_line(line, lines, i)
            if inst:
                block.append(inst)
            i += 1
        return block, else_block, i

    # ── 执行 ───────────────────────────────────────────────────────────────

    def run(self, script: str) -> MacroValue:
        """解析并执行脚本"""
        self._running = True
        self._stop_event.clear()
        instructions = self.parse(script)
        try:
            self._exec_block(instructions)
        except Exception as e:
            logger.error(f"[MacroVM] Runtime error: {e}", exc_info=True)
            return MacroValue(str(e), "error")
        finally:
            self._running = False
        return self.ctx.last_result or MacroValue("完成")

    def stop(self):
        self._stop_event.set()
        self._running = False

    def _exec_block(self, instructions: List[MacroInstruction]):
        """执行一个指令块"""
        for inst in instructions:
            if not self._running:
                break
            if self._stop_event.is_set():
                break
            self._exec_inst(inst)

    def _exec_inst(self, inst: MacroInstruction):
        if inst.type == "assign":
            value = self._eval_expr(inst.assign_expr)
            self.ctx.set(inst.assign_var, value.value)
            self.ctx.last_result = value
            return

        if inst.type == "label":
            return  # 标签本身不执行

        if inst.type == "goto":
            # 简化：找到标签后从那里继续（不支持嵌套 goto，略）
            target_idx = self._labels.get(inst.raw)
            if target_idx is not None:
                logger.info(f"[MacroVM] Goto {inst.raw} (idx={target_idx})")
            return

        if inst.type == "if":
            cond_result = self._eval_condition(inst.condition_expr)
            if cond_result.as_bool():
                self._exec_block(inst.then_block or [])
            elif inst.else_block:
                self._exec_block(inst.else_block)
            return

        if inst.type == "for":
            for _ in inst.for_range:
                if not self._running:
                    break
                self._exec_block(inst.for_block or [])
            return

        if inst.type == "wait":
            time.sleep(inst.wait_seconds or 1)
            return

        if inst.type == "wait_image":
            pos = self._builtin._wait_image(inst.wait_image, inst.wait_timeout or 10)
            self.ctx.last_result = MacroValue(pos is not None)
            return

        if inst.type == "action" and inst.action:
            self._exec_action(inst.action)

    def _exec_action(self, action: MacroAction):
        """执行一个动作"""
        name = action.name
        params = action.params

        # 内置动作映射
        builtin_map = {
            "点击": lambda: self._builtin.click(
                x=params.get("x"), y=params.get("y"),
                image=params.get("图像") or params.get("image"),
                timeout=float(params.get("超时", 10)),
            ),
            "输入": lambda: self._builtin.input_text(params.get("_") or params.get("text", "")),
            "按键": lambda: self._builtin.press(params.get("键") or params.get("key", "enter")),
            "等待": lambda: self._builtin.wait(
                seconds=float(params.get("秒", 0)),
                image=params.get("图像") or params.get("image"),
                timeout=float(params.get("超时", 10)),
            ),
            "发送": lambda: self._builtin.press("enter"),
            "图像存在": lambda: self._builtin.image_exists(
                params.get("图像") or params.get("image"),
                timeout=float(params.get("超时", 0)),
            ),
            "复制": lambda: self.ctx.set("_clipboard", self._builtin.get_clipboard().value),
            "获取剪贴板": lambda: self._builtin.get_clipboard(),
            "移动到": lambda: self._builtin.click(
                x=int(params.get("x", 0)),
                y=int(params.get("y", 0)),
            ),
        }

        if name in builtin_map:
            result = builtin_map[name]()
            self.ctx.last_result = result
        else:
            logger.warning(f"[MacroVM] Unknown action: {name}")
            self.ctx.last_result = MacroValue(f"[未知动作: {name}]")

    def _eval_expr(self, expr: str) -> MacroValue:
        """求值表达式"""
        expr = expr.strip()
        # 字符串字面量
        if expr.startswith('"') and expr.endswith('"'):
            return MacroValue(expr[1:-1])
        if expr.startswith("'") and expr.endswith("'"):
            return MacroValue(expr[1:-1])
        # 数字
        try:
            if "." in expr:
                return MacroValue(float(expr), "float")
            return MacroValue(int(expr), "int")
        except ValueError:
            pass
        # 变量
        val = self.ctx.get(expr)
        if val.type != "str" or val.value:
            return val
        # 尝试解析简单表达式
        return MacroValue(self.ctx.resolve(expr))

    def _eval_condition(self, expr: str) -> MacroValue:
        """求值条件表达式"""
        expr = expr.strip()
        # "图像存在 xxx"
        m = re.match(r"图像存在[（(]?\s*(.+?)\s*[）)]?", expr)
        if m:
            img = m.group(1).strip().strip("'\"").strip("图像").strip("image").strip(":=")
            return self._builtin.image_exists(img)
        # "not 图像存在"
        if expr.startswith("不") or expr.startswith("not"):
            inner = self._eval_condition(expr.replace("不", "").replace("not", "").strip())
            return MacroValue(not inner.as_bool())
        return self._eval_expr(expr)
