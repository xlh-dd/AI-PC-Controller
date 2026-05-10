@echo off
chcp 65001 >nul
title WSL 预启动服务
color 0B

echo ==========================================
echo     WSL 预启动服务
echo ==========================================
echo.

REM 检查 WSL 是否已在运行
wsl -l --running | findstr "Ubuntu-22.04" >nul
if %errorlevel% == 0 (
    echo [✓] WSL 已在运行
    goto :check_hermes
)

echo [1/3] 启动 WSL...
wsl -d Ubuntu-22.04 -e echo "WSL 启动成功" >nul 2>&1
if %errorlevel% neq 0 (
    echo [✗] WSL 启动失败
    pause
    exit /b 1
)
echo [✓] WSL 启动成功

:check_hermes
echo [2/3] 检查 Hermes...
wsl -d Ubuntu-22.04 -e bash -c "cd /home/xlh/hermes-agent && source venv/bin/activate && python3 hermes --version" >nul 2>&1
if %errorlevel% neq 0 (
    echo [✗] Hermes 检查失败
    pause
    exit /b 1
)
echo [✓] Hermes 可用

echo [3/3] 保持 WSL 运行...
echo.
echo ==========================================
echo 提示: 不要关闭此窗口！
echo 此窗口保持 WSL 在后台运行，
echo 可以显著提高 AI 电脑管家的响应速度。
echo ==========================================
echo.

REM 保持 WSL 运行
:loop
wsl -d Ubuntu-22.04 -e bash -c "echo 'heartbeat'" >nul 2>&1
if %errorlevel% neq 0 (
    echo [✗] WSL 连接断开，尝试重启...
    wsl -d Ubuntu-22.04 -e echo "restart" >nul 2>&1
)
timeout /t 30 /nobreak >nul
goto :loop
