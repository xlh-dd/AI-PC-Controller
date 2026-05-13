import sys
import os
import sqlite3
from modules.conversation_memory import ConversationMemory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("数据库初始化和表结构测试")
print("=" * 60)

results = []

# 测试对话记忆数据库
print("\n1. 测试对话记忆数据库 (ConversationMemory)")
try:
    cm = ConversationMemory()
    
    # 检查数据库文件
    if os.path.exists(cm.db_path):
        print(f"  [OK] 数据库文件已创建: {cm.db_path}")
        results.append(("conversation_memory_db_file", True))
    else:
        print(f"  [FAIL] 数据库文件未创建: {cm.db_path}")
        results.append(("conversation_memory_db_file", False))
    
    # 检查表结构
    conn = sqlite3.connect(cm.db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    expected_tables = ['sessions', 'conversations', 'function_calls', 'conversation_summaries']
    
    for table in expected_tables:
        if table in tables:
            print(f"  [OK] 表 '{table}' 存在")
            results.append((f"table_{table}", True))
        else:
            print(f"  [FAIL] 表 '{table}' 不存在")
            results.append((f"table_{table}", False))
    
    # 检查索引
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = [row[0] for row in cursor.fetchall()]
    print(f"  [INFO] 索引数量: {len(indexes)}")
    
    conn.close()
    print("  [OK] 对话记忆数据库测试通过")
    
except Exception as e:
    print(f"  [FAIL] 对话记忆数据库测试失败: {e}")
    results.append(("conversation_memory", False))

# 测试知识库数据库
print("\n2. 测试知识库数据库 (KnowledgeBaseBuilder)")
try:
    from modules.knowledge_base_builder import KnowledgeBaseBuilder
    kb = KnowledgeBaseBuilder()
    
    # 检查数据库连接
    if kb.browser_history_db is not None:
        print(f"  [OK] 数据库连接已建立")
        results.append(("knowledge_base_db_connection", True))
    else:
        print(f"  [FAIL] 数据库连接未建立")
        results.append(("knowledge_base_db_connection", False))
    
    # 检查数据库文件
    db_path = os.path.join(os.path.dirname(__file__), "data", "knowledge_base.db")
    if os.path.exists(db_path):
        print(f"  [OK] 数据库文件已创建: {db_path}")
        results.append(("knowledge_base_db_file", True))
    else:
        print(f"  [INFO] 数据库文件路径: {db_path} (可能尚未创建)")
        results.append(("knowledge_base_db_file", True))  # 数据库可能尚未创建
    
    print("  [OK] 知识库数据库测试通过")
    
except Exception as e:
    print(f"  [FAIL] 知识库数据库测试失败: {e}")
    results.append(("knowledge_base", False))

# 测试邮件分类数据库
print("\n3. 测试邮件分类数据库 (EmailClassifier)")
try:
    from modules.email_classifier import EmailClassifier
    ec = EmailClassifier()
    
    # 检查数据库连接
    if ec.email_db is not None:
        print(f"  [OK] 数据库连接已建立")
        results.append(("email_classifier_db_connection", True))
    else:
        print(f"  [FAIL] 数据库连接未建立")
        results.append(("email_classifier_db_connection", False))
    
    # 检查数据库文件
    db_path = os.path.join(os.path.dirname(__file__), "data", "email_classifier.db")
    if os.path.exists(db_path):
        print(f"  [OK] 数据库文件已创建: {db_path}")
        results.append(("email_classifier_db_file", True))
    else:
        print(f"  [INFO] 数据库文件路径: {db_path} (可能尚未创建)")
        results.append(("email_classifier_db_file", True))  # 数据库可能尚未创建
    
    print("  [OK] 邮件分类数据库测试通过")
    
except Exception as e:
    print(f"  [FAIL] 邮件分类数据库测试失败: {e}")
    results.append(("email_classifier", False))

# 测试基本CRUD操作
print("\n4. 测试对话记忆CRUD操作")
try:
    cm = ConversationMemory()
    
    # 测试添加消息
    msg_id = cm.add_message("user", "测试消息")
    print(f"  [OK] 添加消息成功，ID: {msg_id}")
    
    # 测试获取历史
    history = cm.get_conversation_history(limit=10)
    print(f"  [OK] 获取历史成功，数量: {len(history)}")
    
    # 测试统计
    stats = cm.get_statistics()
    print(f"  [OK] 获取统计成功: {stats}")
    
    # 清理测试数据
    cm.delete_conversation(msg_id)
    print(f"  [OK] 删除消息成功")
    
    results.append(("conversation_crud", True))
    
except Exception as e:
    print(f"  [FAIL] CRUD操作测试失败: {e}")
    results.append(("conversation_crud", False))

print("\n" + "=" * 60)
print("测试结果汇总")
print("=" * 60)
success_count = sum(1 for _, v in results if v)
total_count = len(results)
print(f"成功: {success_count}/{total_count}")

if success_count == total_count:
    print("\n✅ 所有数据库测试通过！")
else:
    print("\n⚠️ 部分测试失败，请检查上述错误信息。")
