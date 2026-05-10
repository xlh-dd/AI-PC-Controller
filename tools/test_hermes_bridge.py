#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Hermes 桥接模块
"""

import sys
import os

# 添加项目目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.hermes_bridge import get_hermes_bridge, get_hermes_ai_helper

def test_hermes_bridge():
    print("=" * 50)
    print("测试 Hermes 桥接模块")
    print("=" * 50)
    
    # 获取桥接实例
    bridge = get_hermes_bridge()
    
    # 检查状态
    status = bridge.get_status()
    print(f"\n📊 Hermes 状态:")
    print(f"  可用: {'✅' if status['available'] else '❌'}")
    print(f"  WSL 发行版: {status['wsl_distro']}")
    print(f"  Hermes 目录: {status['hermes_dir']}")
    
    if not status['available']:
        print("\n⚠️ Hermes 不可用，跳过消息测试")
        return
    
    # 测试发送消息
    print(f"\n📤 测试发送消息...")
    test_messages = [
        "你好",
        "1+1等于几？",
    ]
    
    for msg in test_messages:
        print(f"\n  用户: {msg}")
        response = bridge.send_message(msg)
        print(f"  Hermes: {response[:200]}...")
    
    # 测试 AI Helper
    print(f"\n🤖 测试 HermesAIHelper...")
    ai = get_hermes_ai_helper()
    print(f"  可用: {'✅' if ai.is_available() else '❌'}")
    
    if ai.is_available():
        response = ai.chat("你好，请做个自我介绍")
        print(f"  回复: {response[:200]}...")
    
    print("\n" + "=" * 50)
    print("测试完成!")
    print("=" * 50)

if __name__ == "__main__":
    test_hermes_bridge()
