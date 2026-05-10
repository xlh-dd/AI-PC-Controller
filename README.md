# AI电脑管家

Windows 桌面 AI 助手，集成文件管理、AI 对话、系统控制、知识库检索、邮件管理等功能。

## 快速启动

双击 `launcher.bat` 打开启动菜单，选择启动模式：
- **[1] 标准启动** - 正常启动 main.py
- **[2] 快速启动** - 预启动 WSL 加速
- **[3] 升级版启动** - 带 Hermes 增强功能
- **[4] Hermes 模式** - Hermes 专用模式
- **[5] 健康检查** - 运行项目健康检查
- **[6] 安装依赖** - 安装/更新 Python 依赖
- **[7] 测试 Hermes** - 测试 Hermes 连接

也可以直接运行各 .bat 文件：
- `prestart_wsl.bat` - 仅预启动 WSL（不启动主程序）
- `test_gui.bat` - 测试 GUI 组件

## 项目结构

```
AI电脑控制器/
├── main.py                     # 主程序入口
├── main_upgrade.py             # 升级版入口（带 Hermes）
├── launcher.bat                # 统一启动器
├── prestart_wsl.bat            # WSL 预启动
├── test_gui.bat                # GUI 测试
├── requirements.txt             # Python 依赖
├── utils/                      # 工具函数
├── modules/                    # 功能模块
├── core/                       # 核心组件
├── agent/                      # AI Agent
├── tools/                      # 工具脚本（修复、测试、健康检查）
├── docs/                       # 项目文档
└── knowledge_base/             # 知识库
```

## 健康检查

运行 `python tools/health_check.py` 检查项目状态，包括：
- 系统环境
- Python 依赖
- 文件完整性
- 配置文件
- WSL/Hermes 状态
- 日志文件
- 磁盘空间

## 依赖安装

```bash
python -m pip install -r requirements.txt
```

## 知识库

知识库配置位于 `knowledge_base/config/`，包括：
- `knowledge_base_config.json` - 知识库主配置
- `email_config.json` - 邮件分类配置

## 模块说明

| 模块 | 功能 |
|------|------|
| `modules/file_manager.py` | 文件管理 |
| `modules/ai_helper.py` | AI 对话助手 |
| `modules/ai_agent.py` | AI Agent 核心 |
| `modules/system_controller.py` | 系统控制 |
| `modules/hermes_bridge_optimized.py` | Hermes 桥接（优化版）|
| `modules/knowledge_base_builder.py` | 知识库构建 |
| `modules/email_classifier.py` | 邮件分类 |
| `modules/ui_manager.py` | UI 管理 |

## 工具脚本 (tools/)

| 脚本 | 功能 |
|------|------|
| `health_check.py` | 项目健康检查 |
| `fix_hermes.py` | 修复 Hermes 问题 |
| `keep_wsl_alive.py` | 保持 WSL 运行 |
| `test_hermes_bridge.py` | 测试 Hermes 桥接 |
| `test_hermes_fix.py` | 测试 Hermes 修复 |
| `replace_ai_agent_calls.py` | 替换 AI Agent 调用 |
| `_fix_registry.py` | 修复注册表 |

## 文档 (docs/)

项目文档已移至 `docs/` 目录：
- `系统全面评估报告.md`
- `问题分析与解决方案.md`
- `UPGRADE-v2.md`
- `HERMES_INTEGRATION.md`
- `README_HERMES.md`
- `UI_OPTIMIZATION.md`
- `OPTIMIZATION.md`
- `FIXED_NOTES.md`

## 注意事项

- 确保磁盘空间 > 10G（低于 5G 可能导致程序异常）
- WSL 功能需要提前安装 Ubuntu-22.04 或对应发行版
- 首次运行需要安装依赖：`python -m pip install -r requirements.txt`

## 版本

当前版本：v8.0+ (持续升级中)