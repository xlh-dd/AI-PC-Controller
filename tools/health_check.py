# -*- coding: utf-8 -*-
"""
AI电脑管家 项目健康检查工具

检查项目完整性、依赖安装、配置状态、WSL可用性等。
运行: python tools/health_check.py
"""

import os
import sys
import json
import platform
import subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    @staticmethod
    def OK(text):
        return f"{Colors.GREEN}{text}{Colors.RESET}"

    @staticmethod
    def WARN(text):
        return f"{Colors.YELLOW}{text}{Colors.RESET}"

    @staticmethod
    def ERR(text):
        return f"{Colors.RED}{text}{Colors.RESET}"

    @staticmethod
    def INFO(text):
        return f"{Colors.CYAN}{text}{Colors.RESET}"


def check_section(title):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}  {title}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")


def status(label, condition, detail=""):
    mark = Colors.OK("✓") if condition else Colors.ERR("✗")
    msg = f"  {mark} {label}"
    if detail:
        msg += f" {Colors.INFO(f'({detail})')}"
    print(msg)
    return condition


# ===== 系统环境 =====
def check_system():
    check_section("系统环境")
    all_ok = True
    all_ok &= status("操作系统", True, platform.system())
    all_ok &= status("Python 版本", sys.version_info >= (3, 10), sys.version.split()[0])
    return all_ok


# ===== Python 依赖 =====
def check_deps():
    check_section("Python 依赖")
    deps = {
        "tkinter": None,
        "psutil": "系统监控",
        "PIL": "图像处理",
        "openai": "AI 调用",
        "requests": "HTTP 请求",
        "chromadb": "向量数据库",
        "pandas": "数据处理",
    }
    all_ok = True
    for mod_name, desc in deps.items():
        try:
            __import__(mod_name)
            all_ok &= status(f"{mod_name} ({desc or '核心'})", True)
        except ImportError:
            all_ok &= status(f"{mod_name} ({desc or '核心'})", False, "未安装")
    return all_ok


# ===== 项目文件完整性 =====
def check_files():
    check_section("项目文件完整性")
    required_files = [
        "main.py",
        "main_upgrade.py",
        "requirements.txt",
        "utils/config.py",
        "utils/helpers.py",
        "modules/__init__.py",
        "modules/file_manager.py",
        "modules/ai_helper.py",
        "modules/ai_agent.py",
        "modules/system_controller.py",
        "modules/hermes_bridge_optimized.py",
        "core/event_bus.py",
        "core/app_context.py",
        "agent/model_pool.py",
        "agent/agent.py",
    ]
    all_ok = True
    for f in required_files:
        exists = (PROJECT_ROOT / f).exists()
        all_ok &= status(f, exists, "缺失" if not exists else "")
    return all_ok


# ===== 配置文件检查 =====
def check_configs():
    check_section("配置文件")
    all_ok = True
    kb_config = PROJECT_ROOT / "knowledge_base" / "config" / "knowledge_base_config.json"
    all_ok &= status("knowledge_base_config.json", kb_config.exists())
    email_config = PROJECT_ROOT / "knowledge_base" / "config" / "email_config.json"
    all_ok &= status("email_config.json", email_config.exists())
    return all_ok


# ===== WSL 检查 =====
def check_wsl():
    check_section("WSL / Hermes")
    all_ok = True
    try:
        result = subprocess.run(
            ["wsl", "--list", "--running"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        output = (result.stdout or "").strip()
        if not output:
            all_ok &= status("WSL 运行中", False, "未启动或 wsl 输出为空")
        else:
            # 第一行是标题，后续行是发行版
            lines = output.split("\n")
            running = len(lines) > 1 and len(output) > 50
            all_ok &= status("WSL 运行中", running, output[:60] if running else "未检测到运行中的发行版")
    except FileNotFoundError:
        all_ok &= status("WSL 已安装", False, "wsl 命令不可用")
    except subprocess.TimeoutExpired:
        all_ok &= status("WSL 检查", False, "超时")
    except Exception as e:
        all_ok &= status("WSL 检查", False, str(e)[:50])
    return all_ok


# ===== 日志检查 =====
def check_logs():
    check_section("日志文件")
    all_ok = True
    log_path = Path.home() / "aipc_helper.log"
    if log_path.exists():
        size_kb = log_path.stat().st_size / 1024
        mtime = datetime.fromtimestamp(log_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        healthy = size_kb < 50 * 1024  # < 50MB
        all_ok &= status(f"主日志 ({size_kb:.1f} KB)", healthy, f"最后更新: {mtime}")
    else:
        all_ok &= status("主日志", False, "未生成")

    upgrade_log = Path.home() / "aipc_helper_upgrade.log"
    if upgrade_log.exists():
        size_kb = upgrade_log.stat().st_size / 1024
        all_ok &= status(f"升级日志 ({size_kb:.1f} KB)", True)
    return all_ok


# ===== 磁盘空间 =====
def check_disk():
    check_section("磁盘空间")
    try:
        import shutil
        usage = shutil.disk_usage(PROJECT_ROOT)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        pct = usage.free / usage.total * 100
        if free_gb < 5:
            healthy = False
            detail = f"仅剩 {free_gb:.1f}G/{total_gb:.0f}G ({pct:.0f}%) - 磁盘空间严重不足"
        elif free_gb < 10:
            healthy = False
            detail = f"可用 {free_gb:.1f}G/{total_gb:.0f}G ({pct:.0f}%) - 建议清理"
        else:
            healthy = True
            detail = f"可用 {free_gb:.1f}G/{total_gb:.0f}G ({pct:.0f}%)"
        return status("磁盘空间", healthy, detail)
    except Exception:
        return status("磁盘检测", False, "检测失败")


def main():
    print(f"\n{Colors.BOLD}{Colors.CYAN}  AI电脑管家 - 项目健康检查{Colors.RESET}")
    print(f"  项目路径: {PROJECT_ROOT}")
    print(f"  检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    results.append(("系统环境", check_system()))
    results.append(("Python依赖", check_deps()))
    results.append(("文件完整性", check_files()))
    results.append(("配置文件", check_configs()))
    results.append(("WSL/Hermes", check_wsl()))
    results.append(("日志文件", check_logs()))
    results.append(("磁盘空间", check_disk()))

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"  {Colors.BOLD}结果: {passed}/{total} 项通过{Colors.RESET}")

    if passed == total:
        print(f"  {Colors.OK('✓ 项目状态健康！可以正常启动。')}")
    else:
        failed = [(name, ok) for name, ok in results if not ok]
        print(f"  {Colors.WARN(f'⚠ {len(failed)} 项未通过:')}")
        for name, _ in failed:
            print(f"    - {name}")
        print(f"\n  建议运行: {Colors.INFO('python tools/fix_hermes.py')} 修复 Hermes 问题")
        print(f"  或查看: {Colors.INFO('tools/ 目录')} 下的其他修复脚本")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())