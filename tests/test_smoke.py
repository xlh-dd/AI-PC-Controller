"""
Smoke Test - 端到端功能验证
运行: python tests/test_smoke.py
"""
import sys
import time
import subprocess
from pathlib import Path

# 确保 AI 电脑控制器目录在路径中
AI_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(AI_DIR))


def run_test(name, fn):
    """运行单个测试"""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print('='*60)
    try:
        result = fn()
        if result:
            print(f"  [PASS] {name}")
            return True
        else:
            print(f"  [FAIL] {name}")
            return False
    except Exception as e:
        print(f"  [ERROR] {name}: {e}")
        return False


def test_module_imports():
    """测试所有核心模块能否正常导入"""
    modules = [
        "main", "main_upgrade",
        "modules.ai_agent", "modules.wechat_controller",
        "modules.email_classifier", "modules.knowledge_base_builder",
        "modules.conversation_memory", "modules.macro_recorder",
        "modules.system_controller", "modules.social_skills",
        "core.db_manager", "core.event_bus", "core.app_context",
    ]
    for mod in modules:
        try:
            __import__(mod)
            print(f"  [OK] {mod}")
        except Exception as e:
            print(f"  [FAIL] {mod}: {e}")
            return False
    return True


def test_app_context():
    """测试 AppContext 能正常构建"""
    from core.app_context import AppContext
    ctx = AppContext()
    print("  AppContext 构建成功")
    return True


def test_db_manager():
    """测试 DatabaseManager"""
    from core.db_manager import get_db_manager, execute_sql
    db = get_db_manager()
    execute_sql("smoke.db", "CREATE TABLE IF NOT EXISTS t (id INT)")
    execute_sql("smoke.db", "DROP TABLE t")
    print("  DatabaseManager 读写正常")
    return True


def test_open_notepad():
    """测试打开记事本并关闭"""
    try:
        # 启动记事本
        proc = subprocess.Popen(["notepad.exe"])
        print(f"  启动记事本 (PID={proc.pid})")
        time.sleep(2)
        # 发送关闭命令
        proc.terminate()
        proc.wait(timeout=5)
        print("  记事本已关闭")
        return True
    except Exception as e:
        print(f"  记事本测试失败: {e}")
        return False


def test_file_manager():
    """测试 FileManager 基本功能"""
    from modules.file_manager import FileManager
    fm = FileManager()
    # 测试磁盘信息
    # 测试 list_files
    results = fm.list_files(str(Path.home() / "Desktop"))
    print(f"  文件列表: Desktop 下找到 {len(results)} 个条目")
    return True


def test_system_controller():
    """测试 SystemController"""
    from modules.system_controller import get_system_controller
    sc = get_system_controller()
    # 测试音量获取
    vol = sc.get_volume()
    print(f"  系统音量: {vol}")
    return True


def test_paddleocr():
    """测试 PaddleOCR 可用性"""
    from modules.wechat_controller import PADDLEOCR_AVAILABLE
    print(f"  PaddleOCR: {'可用' if PADDLEOCR_AVAILABLE else '不可用'}")
    return True


def test_email_keyring():
    """测试邮件密码 keyring"""
    from modules.email_classifier import EmailClassifier
    has_keyring = hasattr(EmailClassifier, '_resolve_password')
    print(f"  邮件密码 keyring 方法: {'存在' if has_keyring else '缺失'}")
    return True


def main():
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║         AI电脑管家 v2.0 — Smoke Test                 ║
    ╚══════════════════════════════════════════════════════╝
    """)

    tests = [
        ("模块导入", test_module_imports),
        ("AppContext 构建", test_app_context),
        ("DatabaseManager", test_db_manager),
        ("打开记事本", test_open_notepad),
        ("FileManager", test_file_manager),
        ("SystemController", test_system_controller),
        ("PaddleOCR 状态", test_paddleocr),
        ("邮件密码 Keyring", test_email_keyring),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        if run_test(name, fn):
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"  结果: {passed} 通过, {failed} 失败")
    print('='*60)

    # 清理测试数据库
    test_db = AI_DIR / "knowledge_base" / "data" / "smoke.db"
    if test_db.exists():
        try:
            test_db.unlink()
        except PermissionError:
            pass  # 文件可能被锁定，忽略

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
