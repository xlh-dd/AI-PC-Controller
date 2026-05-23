# -*- coding: utf-8 -*-
"""
AI电脑管家 启动前依赖检查工具

检查所有关键第三方依赖是否已安装，以表格形式展示状态，
缺失项自动给出 pip install 提示。
运行: python tools/preflight_check.py
返回: 全部就绪 -> exit 0; 有缺失 -> exit 1
"""

import sys
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEPENDENCIES = [
    ("comtypes",       "comtypes",       "COM 类型库"),
    ("pycaw",          "pycaw",          "Windows 音频控制"),
    ("pyautogui",      "pyautogui",      "GUI 自动化"),
    ("pynput",         "pynput",         "键盘/鼠标监听"),
    ("psutil",         "psutil",         "系统资源监控"),
    ("pygetwindow",    "pygetwindow",    "窗口管理"),
    ("win32com",       "pywin32",        "Windows COM API"),
    ("PIL",            "Pillow",         "图像处理"),
    ("pytesseract",    "pytesseract",    "OCR 文字识别"),
    ("pyttsx3",        "pyttsx3",        "语音合成"),
    ("ttkbootstrap",   "ttkbootstrap",   "现代 UI 主题"),
    ("requests",       "requests",       "HTTP 请求"),
]

HEADER_FMT = "{:<18} {:<16} {:<6}  {:}"
SEP = "-" * 72


def check_import(module_name):
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def main():
    print()
    print("  AI电脑管家 - 启动前依赖检查")
    print(f"  项目路径: {PROJECT_ROOT}")
    print()
    print("  " + SEP)
    print("  " + HEADER_FMT.format("模块", "pip 包名", "状态", "用途"))
    print("  " + SEP)

    all_ok = True
    for module_name, pip_name, desc in DEPENDENCIES:
        ok = check_import(module_name)
        status_icon = "✅" if ok else "❌"
        hint = "" if ok else f"  -> pip install {pip_name}"
        print(f"  {HEADER_FMT.format(module_name, pip_name, status_icon, desc)}")
        if hint:
            print(f"  {'':>40}{hint}")
        if not ok:
            all_ok = False

    print("  " + SEP)

    missing = [d for d in DEPENDENCIES if not check_import(d[0])]
    if missing:
        print()
        print(f"  ❌ {len(missing)} 个依赖缺失，请安装后重试：")
        print()
        pip_packages = " ".join(d[1] for d in missing)
        print(f"      pip install {pip_packages}")
        print()
        return 1
    else:
        print()
        print("  ✅ 所有依赖就绪，可以启动。")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())