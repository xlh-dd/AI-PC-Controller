@echo off
chcp 65001 >nul
title AI电脑管家 - 启动器 v2.0
color 0B

:menu
cls
echo ======================================
echo   AI电脑管家 启动器
echo ======================================
echo.
echo  [1] 标准启动 (main.py)
echo  [2] 极速启动 (预加载WSL环境)
echo  [3] 高级功能 (main_upgrade.py + Hermes)
echo  [4] Hermes 模式切换
echo  [5] 项目环境检查
echo  [6] 安装/更新依赖
echo  [7] 测试 Hermes 环境
echo  [0] 退出
echo.
echo ======================================
set /p choice=请选择 (0-7):

if "%choice%"=="1" goto start_standard
if "%choice%"=="2" goto start_fast
if "%choice%"=="3" goto start_upgrade
if "%choice%"=="4" goto start_hermes
if "%choice%"=="5" goto health_check
if "%choice%"=="6" goto install_deps
if "%choice%"=="7" goto test_hermes
if "%choice%"=="0" goto exit
echo 无效选项,请重新选择
timeout /t 2 >nul
goto menu

:start_standard
echo 启动 AI电脑管家 (标准模式)...
start "" python main.py
goto menu

:start_fast
echo 预加载 WSL 守护进程...
start /min "WSL守护进程" python tools/keep_wsl_alive.py
echo 等待 WSL 就绪 (10秒)...
timeout /t 10 >nul
echo 启动 AI电脑管家...
start "" python main.py
goto menu

:start_upgrade
echo 启动 AI电脑管家 (高级版 + Hermes)...
start "" python main_upgrade.py
goto menu

:start_hermes
echo 启动 AI电脑管家 (Hermes 模式)...
start "" python main.py --hermes
goto menu

:health_check
echo 检查项目运行状态...
python tools/health_check.py
echo.
pause
goto menu

:install_deps
echo 安装 Python 依赖...
python -m pip install -r requirements.txt --upgrade
echo.
echo 安装完成!
pause
goto menu

:test_hermes
echo 测试 Hermes 环境...
python tools/test_hermes_bridge.py
echo.
pause
goto menu

:exit
echo 再见!
timeout /t 1 >nul
exit