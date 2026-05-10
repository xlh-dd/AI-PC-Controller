#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WSL 保持运行脚本
在后台保持 WSL 活动状态，减少响应延迟
"""

import subprocess
import time
import sys
import os

def check_wsl_running(distro="Ubuntu-22.04"):
    """检查 WSL 是否正在运行"""
    try:
        result = subprocess.run(
            ["wsl", "-l", "--running"],
            capture_output=True,
            timeout=5
        )
        output = result.stdout.decode('utf-8', errors='ignore')
        return distro in output
    except:
        return False

def start_wsl(distro="Ubuntu-22.04"):
    """启动 WSL"""
    try:
        # 使用 Popen 启动后台进程
        subprocess.Popen(
            ["wsl", "-d", distro, "-e", "bash", "-c", "while true; do sleep 60; done"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )
        print(f"[*] WSL ({distro}) 已启动")
        return True
    except Exception as e:
        print(f"[✗] 启动 WSL 失败: {e}")
        return False

def main():
    print("=" * 50)
    print("WSL 保持运行服务")
    print("=" * 50)
    print()
    
    distro = "Ubuntu-22.04"
    
    # 检查 WSL 是否已在运行
    if check_wsl_running(distro):
        print(f"[✓] WSL ({distro}) 已在运行")
    else:
        print(f"[*] 启动 WSL ({distro})...")
        if start_wsl(distro):
            # 等待 WSL 启动
            for i in range(15):
                time.sleep(1)
                if check_wsl_running(distro):
                    print(f"[✓] WSL 启动成功")
                    break
            else:
                print(f"[✗] WSL 启动超时")
                return 1
    
    print()
    print("[*] 保持 WSL 运行中...")
    print("[*] 按 Ctrl+C 停止")
    print()
    
    try:
        while True:
            if not check_wsl_running(distro):
                print(f"[*] WSL 已停止，重新启动...")
                start_wsl(distro)
            time.sleep(30)
    except KeyboardInterrupt:
        print()
        print("[*] 服务已停止")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
