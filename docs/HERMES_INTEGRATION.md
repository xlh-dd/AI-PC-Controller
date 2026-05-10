# Hermes 整合说明

## 概述

AI电脑管家 8.0 现已整合 Hermes AI 助手！你现在可以在 AI 电脑管家中直接与 Hermes 交互。

## 新功能

### 1. AI 引擎切换
- **Hermes 模式**: 使用 WSL 中的 Hermes Agent (DeepSeek V4 Pro)
- **Ollama 模式**: 使用本地 Ollama 服务（默认）

### 2. 状态显示
- 主界面底部状态栏显示 Hermes 连接状态
- 显示当前使用的 AI 引擎

### 3. AI 助手对话框
- 点击 "💬 AI助手" 打开对话框
- 对话框标题显示 "AI助手 (Hermes)"
- 右上角显示 Hermes 连接状态
- 可以切换使用 Hermes 或 Ollama

## 使用方法

### 启动程序
双击 `start_hermes.bat` 启动 AI电脑管家

### 切换 AI 引擎
1. 点击 "💬 AI助手" 打开对话框
2. 点击右上角的 "Hermes" 按钮切换
3. 或使用主界面的 "🤖 Hermes" 按钮打开 Hermes 终端

### 使用 Hermes 对话
1. 确保 Hermes 已连接（状态栏显示 🟢）
2. 在 AI 助手对话框中切换到 Hermes 模式
3. 输入消息并发送

## 文件变更

### 新增文件
- `modules/hermes_bridge.py` - Hermes 桥接模块
- `start_hermes.bat` - 启动脚本
- `test_hermes_bridge.py` - 测试脚本
- `HERMES_INTEGRATION.md` - 本说明文件

### 修改文件
- `main.py` - 整合 Hermes 功能

## 配置

### 配置文件
在 `config.json` 中添加以下配置：

```json
{
  "use_hermes": false,
  "hermes_wsl_distro": "Ubuntu-22.04",
  "hermes_dir": "/home/xlh/hermes-agent"
}
```

### 环境要求
1. **WSL2** - Windows Subsystem for Linux
2. **Hermes** - 安装在 WSL 中 (`/home/xlh/hermes-agent`)
3. **Python 3.8+** - AI电脑管家运行环境

## 故障排除

### Hermes 未连接
- 检查 WSL 是否运行: `wsl --list --running`
- 检查 Hermes 是否安装: 
  ```bash
  wsl -d Ubuntu-22.04 -e bash -c "cd /home/xlh/hermes-agent && source venv/bin/activate && python3 hermes --version"
  ```

### 切换失败
- 确保 Hermes 可用后再切换
- 检查日志文件 `aipc_helper.log`

### 响应超时
- Hermes 可能需要更长时间响应
- 默认超时时间为 120 秒

## 技术细节

### 架构
```
AI电脑管家 (Windows)
    ↓
HermesBridge (Python)
    ↓
WSL2 → Hermes Agent (Ubuntu-22.04)
    ↓
DeepSeek V4 Pro API
```

### 通信方式
- 使用 `subprocess` 调用 WSL
- 通过 `wsl -d Ubuntu-22.04` 执行 Hermes 命令
- 使用 `-z` 参数进行非交互式对话
- 自动处理 UTF-8 编码

### 测试
运行测试脚本验证整合：
```bash
python3 test_hermes_bridge.py
```

## 更新日志

### v8.1 - Hermes 整合
- ✅ 添加 Hermes 桥接模块
- ✅ AI 引擎切换功能
- ✅ 状态栏显示
- ✅ AI 助手对话框整合
- ✅ 保持原有 Ollama 功能
- ✅ 自动检测 WSL 发行版
- ✅ 编码问题修复
