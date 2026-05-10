@echo off
chcp 65001 >nul
title AI电脑管家 8.0 - 修复测试
color 0A

echo ==========================================
echo     AI电脑管家 8.0 - GUI卡死修复测试
echo ==========================================
echo.

echo [*] 检查 Python 环境...
python3 --version >nul 2>&1
if errorlevel 1 (
    echo [✗] 未找到 Python3
    pause
    exit /b 1
)
echo [✓] Python 环境正常

echo [*] 检查代码语法...
python3 -m py_compile main.py
if errorlevel 1 (
    echo [✗] 代码语法错误
    pause
    exit /b 1
)
echo [✓] 代码语法正常

echo [*] 启动程序...
echo.
echo 提示：
echo - 使用 "💬 AI助手" 测试 Hermes 对话
echo - 界面应该不会卡死
echo - 响应时间约 3-5 秒
echo.

python3 main.py

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出
    pause
)
