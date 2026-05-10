import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("全面模块导入测试")
print("=" * 60)

results = {
    "success": [],
    "failed": []
}

modules_to_test = [
    ("modules.knowledge_base_builder", "KnowledgeBaseBuilder"),
    ("modules.email_classifier", "EmailClassifier"),
    ("modules.conversation_memory", "ConversationMemory"),
    ("modules.system_controller", "get_system_controller"),
    ("modules.social_skills", "SocialSkills"),
    ("modules.research_skills", "ResearchSkills"),
    ("modules.learning_skills", "LearningSkills"),
    # workflow_skills 已移除
    ("modules.ai_helper", "AIHelper"),
    ("modules.ai_agent", "get_ai_agent"),
    ("modules.wechat_controller", "WeChatController"),
    ("modules.task_scheduler", "TaskScheduler"),
    ("modules.file_manager", "FileManager"),
    ("modules.thread_manager", "thread_manager"),
    ("modules.ui_manager", "get_ui_manager"),
    ("utils.config", "ConfigManager"),
]

for module_name, class_name in modules_to_test:
    try:
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name)
        results["success"].append(f"{module_name}.{class_name}")
        print(f"[OK] {module_name}.{class_name}")
    except Exception as e:
        results["failed"].append(f"{module_name}.{class_name}: {str(e)}")
        print(f"[FAIL] {module_name}.{class_name}: {str(e)}")

print("\n" + "=" * 60)
print("测试结果汇总")
print("=" * 60)
print(f"成功: {len(results['success'])}/{len(modules_to_test)}")
print(f"失败: {len(results['failed'])}/{len(modules_to_test)}")

if results["failed"]:
    print("\n失败的模块:")
    for item in results["failed"]:
        print(f"  - {item}")

print("\n" + "=" * 60)
print("依赖库检查")
print("=" * 60)

dependencies = [
    "tkinter",
    "sqlite3",
    "threading",
    "logging",
    "json",
    "pathlib",
    "datetime",
    "typing",
    "collections",
    "hashlib",
    "base64",
    "time",
    "re",
    "uuid",
]

optional_deps = [
    ("requests", "HTTP请求库"),
    ("PIL", "图像处理库"),
    ("pyautogui", "GUI自动化库"),
    ("pyperclip", "剪贴板库"),
    ("pytesseract", "OCR库"),
]

for dep in dependencies:
    try:
        __import__(dep)
        print(f"[OK] {dep}")
    except ImportError as e:
        print(f"[FAIL] {dep}: {e}")

print("\n可选依赖:")
for dep, desc in optional_deps:
    try:
        __import__(dep)
        print(f"[OK] {dep} - {desc}")
    except ImportError:
        print(f"[OPTIONAL] {dep} - {desc} (未安装，可选)")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
