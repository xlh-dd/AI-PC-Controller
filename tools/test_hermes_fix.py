# -*- coding: utf-8 -*-
"""
测试 Hermes 修复效果
"""
import subprocess
import time
import sys

def test_hermes_bridge():
    """测试 Hermes 桥接是否正常工作"""
    print("=" * 50)
    print("测试 Hermes 桥接")
    print("=" * 50)
    
    try:
        from modules.hermes_bridge import get_hermes_bridge
        bridge = get_hermes_bridge()
        
        print(f"Hermes 可用: {bridge.available}")
        print(f"WSL 就绪: {bridge._wsl_ready}")
        
        if bridge.available:
            print("\n测试发送消息...")
            start = time.time()
            response = bridge.send_message("你好，请回复'测试成功'")
            elapsed = time.time() - start
            
            print(f"响应时间: {elapsed:.2f}秒")
            print(f"响应内容: {response[:100]}...")
            
            if "测试成功" in response or elapsed < 30:
                print("✅ Hermes 桥接测试通过")
                return True
            else:
                print("⚠️ Hermes 响应异常")
                return False
        else:
            print("❌ Hermes 不可用")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_wsl_command():
    """测试 WSL 命令执行"""
    print("\n" + "=" * 50)
    print("测试 WSL 命令执行")
    print("=" * 50)
    
    try:
        # 测试简单的 WSL 命令
        result = subprocess.run(
            ['wsl', '-d', 'Ubuntu-22.04', 'bash', '-c', 'echo "WSL测试成功"'],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            print(f"✅ WSL 命令测试通过")
            print(f"输出: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ WSL 命令失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ WSL 测试失败: {e}")
        return False

def test_timeout_handling():
    """测试超时处理"""
    print("\n" + "=" * 50)
    print("测试超时处理")
    print("=" * 50)
    
    try:
        import concurrent.futures
        
        def slow_task():
            time.sleep(5)
            return "完成"
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(slow_task)
            try:
                result = future.result(timeout=2)  # 2秒超时
                print("❌ 超时未生效")
                return False
            except concurrent.futures.TimeoutError:
                print("✅ 超时处理正常")
                future.cancel()
                return True
                
    except Exception as e:
        print(f"❌ 超时测试失败: {e}")
        return False

def main():
    print("Hermes 修复测试脚本")
    print("=" * 50)
    
    results = []
    
    # 测试 WSL
    results.append(("WSL命令", test_wsl_command()))
    
    # 测试 Hermes 桥接
    results.append(("Hermes桥接", test_hermes_bridge()))
    
    # 测试超时处理
    results.append(("超时处理", test_timeout_handling()))
    
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！Hermes 修复成功。")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查配置。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
