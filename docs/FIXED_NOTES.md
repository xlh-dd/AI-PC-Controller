# GUI 卡死问题修复说明

## 问题原因

GUI 卡死是因为 Hermes 调用**阻塞了主线程**，导致界面无法响应。

## 修复内容

### 1. 修复 `do_task` 方法
- 将 AI 解析命令移到后台线程
- 使用 `self.root.after()` 更新 GUI

### 2. 修复 AI 聊天对话框
- Hermes 调用已在后台线程中执行
- 添加响应状态提示

## 使用方法

### 启动程序
```bash
# 使用快速启动脚本（推荐）
start_fast.bat

# 或手动启动
python3 main.py
```

### 使用 Hermes
1. 点击 "💬 AI助手" 按钮
2. 在对话框中输入消息
3. 点击 "发送"
4. 等待响应（不会卡死界面）

## 注意事项

1. **首次启动较慢** - WSL 需要 10-15 秒启动
2. **保持 WSL 运行** - 使用 `keep_wsl_alive.py` 保持 WSL 活动
3. **响应时间** - Hermes 响应约 3-5 秒（已优化）

## 故障排除

### 如果仍然卡死
1. 检查 WSL 是否运行：`wsl -l --running`
2. 检查 Hermes 状态：查看日志文件
3. 重启程序：关闭后重新启动

### 如果 Hermes 无响应
1. 检查网络连接
2. 检查 WSL 中的 Hermes 安装
3. 查看日志：`C:\Users\Administrator\aipc_helper.log`
