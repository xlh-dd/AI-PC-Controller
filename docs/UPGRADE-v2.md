# AI电脑管家 v2.0 升级说明

## 📦 新增文件

```
core/                          # 核心基础设施层（全新）
├── event_bus.py               # 事件总线（发布订阅）
├── app_context.py             # 依赖注入容器（模块生命周期管理）
├── macro_interpreter.py        # 宏脚本 DSL 解释器
└── workflow_engine.py         # 工作流引擎

agent/                         # Agent 框架（全新）
├── model_pool.py              # 模型池 + 智能路由 + 降级链 + 语义缓存
├── agent.py                   # 结构化 Agent（ReAct 循环）
├── async_email.py             # 异步邮件处理器（多账号 + ML 分类）
└── vector_memory.py           # 向量化长期记忆（语义检索 + 衰减）

kb_parser/                     # 知识库解析层（全新）
├── semantic_chunker.py        # 语义分块器
└── chromadb_client.py         # ChromaDB 向量存储封装

main_upgrade.py               # 新版主程序（模块化解耦）
start_upgrade.bat             # 升级版启动脚本
```

## 🔑 核心升级

### 1. 架构：EventBus 解耦
- **Before**: 模块间直接调用 `module_a.call_b()`
- **After**: 所有通信走 `event_bus.post("topic", data)`
- 好处：改任意模块不影响其他模块，支持热重载

### 2. AI 层：ModelRouter 模型池
- **Before**: 硬编码 Ollama + qwen2.5:1.5b，无降级
- **After**: 路由层自动选模型 + 3级降级链 + 语义缓存
- 支持：Ollama / Doubao / DeepSeek / GPT，运行时动态切换

### 3. Agent：结构化 ReAct 循环
- **Before**: 75KB 单文件，Prompt 拼字符串
- **After**: 技能注册表 + 标准 Skill 接口 + JSON 输出解析
- 内置：read_file / run_command / write_file / search

### 4. 知识库：ChromaDB + 语义分块
- **Before**: SQLite FTS，固定字数截断
- **After**: ChromaDB 向量检索 + 语义分块 + 混合检索

### 5. 邮件：异步多账号 + ML 分类
- **Before**: 单账号同步轮询
- **After**: 多账号并发 + asyncio + sklearn TF-IDF 分类 + 回复草稿确认

### 6. 记忆：向量检索
- **Before**: SQLite 按时间检索
- **After**: sentence-transformers 语义索引 + 记忆衰减 + 自动摘要

### 7. 宏：DSL 解释器
- **Before**: JSON 动作序列，坐标硬编码
- **After**: 可编程脚本，支持条件/循环/变量/图像模板

### 8. 工作流：节点引擎
- **Before**: 手工流程
- **After**: 可编程节点图 + 依赖声明 + 状态机 + 持久化

## ⚙️ 运行要求

```bash
# 1. 新增 Python 依赖
pip install chromadb sentence-transformers scikit-learn

# 2. 确保 Ollama 运行（AI 功能必需）
ollama serve

# 3. 拉取模型（选其一）
ollama pull qwen2.5:1.5b      # 本地快速补全
ollama pull deepseek-r1        # 复杂推理

# 4. 启动
# 方式 A: 启动脚本（自动装依赖）
start_upgrade.bat

# 方式 B: 直接运行
python main_upgrade.py
```

## 🚀 使用方式

### 新旧版并存
- `main.py` → 原版（不动）
- `main_upgrade.py` → 升级版（并行跑）
- 建议先跑升级版，功能验证通过后再逐步迁移

### Agent 使用
```
Tab: 🤖 Agent
输入：帮我整理桌面的AI文件夹里的文件，按类型分类
点击：🚀 执行 Agent
```

### 宏脚本示例
```
打开微信
等待(图像: "发送按钮.png", 超时=10)
输入("{clipboard}")
发送()
如果 图像存在("确认.png") 则
    点击(图像: "确认.png")
结束
```

### 工作流定义示例
```python
from core.workflow_engine import Workflow, WorkflowNode, WorkflowEngine

wf = Workflow(
    id="daily_backup",
    name="每日备份",
    nodes=[
        WorkflowNode(id="scan", name="扫描文件", task_type="action",
                    params={"module": "file_manager", "method": "scan_desktop"}),
        WorkflowNode(id="classify", name="分类", task_type="action",
                    params={"module": "file_manager", "method": "auto_sort_files"},
                    depends_on=["scan"]),
    ],
    entry="scan",
)
engine.run(wf)
```

## 🔧 后续迁移路线

| 阶段 | 内容 |
|---|---|
| Phase 1（当前） | 新增模块 + 新主程序并行 |
| Phase 2 | 把 `modules/` 下的模块逐步注册到 AppContext |
| Phase 3 | UI 迁移到 CustomTkinter / Flet |
| Phase 4 | 去掉旧 main.py，完全用 main_upgrade.py |

## ⚠️ 注意事项

1. **ChromaDB 首次启动会下载模型**（~90MB），耐心等待
2. **Ollama 建议同时拉取 qwen2.5:1.5b + deepseek-r1**，路由层需要
3. **Macros 图像模板** 放在 `macros/screenshots/` 目录
4. **工作流定义** 放在 `~/aipc_workflows/` 目录
