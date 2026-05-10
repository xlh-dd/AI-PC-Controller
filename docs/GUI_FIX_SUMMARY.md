# GUI 卡死问题修复总结

## 问题
发送消息后 GUI 卡死，半天没反应

## 原因
1. AI 查询没有超时控制，可能无限等待
2. 某些情况下 AI 调用可能阻塞主线程

## 修复内容

### 1. 修复 `main.py` - AI 聊天对话框
- 重构 `ai_response()` 函数，统一错误处理
- 添加 30 秒超时保护
- 确保所有 GUI 更新都在主线程中执行

### 2. 修复 `modules/ai_helper.py`
- 添加 `timeout` 参数到 `ai_query()` 方法
- 使用 `concurrent.futures` 实现超时控制
- 超时后自动取消任务，避免阻塞

### 3. 现有保护机制
- Hermes 桥接已有 120 秒超时
- WSL 预热检查
- 后台线程执行 AI 调用

## 测试方法

### 启动程序
```bash
# 使用快速启动脚本（预启动 WSL）
start_fast.bat

# 或普通启动
python3 main.py
```

### 测试步骤
1. 点击 "💬 AI助手" 按钮
2. 输入测试消息："你好"
3. 点击发送
4. 观察：
   - 输入框应该立即禁用（防止重复发送）
   - 显示 "AI: " 等待响应
   - 3-5 秒内应该收到回复
   - 如果超时，会显示错误信息

## 如果仍然卡死

### 检查清单
1. **WSL 是否运行**
   ```bash
   wsl -l --running
   ```

2. **Hermes 是否可用**
   ```bash
   wsl -d Ubuntu-22.04 bash -c "cd /home/xlh/hermes-agent && source venv/bin/activate && python3 hermes --version"
   ```

3. **查看日志**
   ```bash
   type C:\Users\Administrator\aipc_helper.log
   ```

### 紧急处理
如果 GUI 完全卡死：
1. 按 `Ctrl+C` 尝试中断
2. 或关闭命令行窗口强制退出
3. 重新启动程序

## 性能优化建议

1. **预启动 WSL**
   - 使用 `start_fast.bat` 自动预启动
   - 或手动运行 `wsl -d Ubuntu-22.04`

2. **保持 WSL 运行**
   - 运行 `keep_wsl_alive.py`
   - 避免 WSL 自动休眠

3. **网络检查**
   - 确保网络连接正常
   - Hermes 需要访问 DeepSeek API
