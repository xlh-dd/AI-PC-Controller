#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 Hermes 整合问题
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.hermes_bridge import get_hermes_bridge

print("=" * 60)
print("Hermes 整合诊断工具")
print("=" * 60)

bridge = get_hermes_bridge()

print(f"\n📊 状态:")
print(f"  可用: {'✅' if bridge.available else '❌'}")
print(f"  WSL 发行版: {bridge.wsl_distro}")
print(f"  Hermes 目录: {bridge.hermes_dir}")

if bridge.available:
    print(f"\n🧪 测试消息发送...")
    response = bridge.send_message("你好")
    print(f"  回复: {response[:100]}...")
    print(f"\n✅ Hermes 整合正常!")
else:
    print(f"\n⚠️ Hermes 不可用")
    print(f"  可能原因:")
    print(f"  1. WSL 未启动")
    print(f"  2. Hermes 未安装")
    print(f"  3. WSL 正在启动中（需要等待）")

print("\n" + "=" * 60)
