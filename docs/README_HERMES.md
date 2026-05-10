# 🤖 AI电脑管家 8.0 - Hermes 整合版

## 概述

AI电脑管家现已整合 **Hermes Agent** - 一个强大的 AI 助手，支持 DeepSeek V4 Pro 模型！

## ✨ 新功能

### 1. 双 AI 引擎支持
- **Hermes** (默认): 通过 WSL2 运行，使用 DeepSeek V4 Pro
- **Ollama**: 本地 AI 模型支持

### 2. 智能切换
- 在 AI 助手对话框中一键切换 AI 引擎
- 实时显示当前使用的引擎状态

### 3. 状态监控
- 主界面底部状态栏显示 Hermes 连接状态
- 自动检测 WSL 和 Hermes 可用性

## 🚀 快速开始

### 启动程序
```bash
# 方式1: 双击桌面快捷方式 "AI电脑管家"
# 方式2: 运行启动脚本
start_hermes.bat
```

### 使用 Hermes
1. 点击主界面 "💬 AI助手" 按钮
2. 在对话框右上角点击 "Hermes" 切换按钮
3. 开始对话！

### 使用 Ollama
1. 确保 Ollama 服务正在运行
2. 在 AI 助手对话框中切换到 Ollama 模式
3. 开始对话！

## 📁 文件说明

```
AI电脑控制器/
├── main.py                    # 主程序（已整合 Hermes）
├── modules/
│   ├── hermes_bridge.py       # Hermes 桥接模块
│   └── ...                    # 其他模块
├── start_hermes.bat           # 启动脚本
├── test_hermes_bridge.py      # 测试脚本
├── fix_hermes.py              # 诊断工具
└── README_HERMES.md           # 本说明文件
```

## ⚙️ 配置

### 配置文件位置
`config.json` (自动创建)

### 可用配置项
```json
{
  "use_hermes": false,           // 默认使用 Hermes
  "hermes_wsl_distro": "Ubuntu-22.04",  // WSL 发行版
  "hermes_dir": "/home/xlh/hermes-agent"  // Hermes 安装目录
}
```

## 🔧 故障排除

### Hermes 未连接
```bash
# 检查 WSL 状态
wsl --list --running

# 检查 Hermes 安装
wsl -d Ubuntu-22.04 -e bash -c "cd /home/xlh/hermes-agent && source venv/bin/activate && python3 hermes --version"
```

### 启动超时
- WSL2 首次启动需要 10-30 秒
- 请耐心等待，后续启动会更快

### 编码错误
- 已自动处理 UTF-8 编码
- 如有问题请检查 WSL  locale 设置

## 🧪 测试

运行测试脚本验证整合：
```bash
python3 test_hermes_bridge.py
```

运行诊断工具：
```bash
python3 fix_hermes.py
```

## 📝 更新日志

### v8.1 (2026-04-30)
- ✅ 整合 Hermes Agent
- ✅ 双 AI 引擎支持
- ✅ 智能引擎切换
- ✅ 状态实时监控
- ✅ 自动编码处理
- ✅ WSL2 自动检测

## 🤝 支持

如有问题，请检查：
1. WSL2 是否正确安装
2. Hermes 是否正确安装
3. 查看日志文件 `aipc_helper.log`

---

**享受 AI 带来的便利！** 🎉
