# Hermes 修复说明 - 2026-05-01

## 修复内容

### 1. AI 聊天对话框 Hermes 调用超时问题
**文件**: `main.py`
**位置**: `ai_chat_dialog` 方法中的 `ai_response` 函数

**问题**: Hermes 调用没有设置超时，可能导致 GUI 卡死
**修复**: 添加 60 秒超时控制，使用 `concurrent.futures.ThreadPoolExecutor`

```python
# 修复前
answer = self.hermes_ai.chat(full_prompt)

# 修复后
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor() as executor:
    future = executor.submit(self.hermes_ai.chat, full_prompt)
    try:
        answer = future.result(timeout=60)
    except concurrent.futures.TimeoutError:
        answer = "Hermes 响应超时，请稍后重试"
        future.cancel()
```

### 2. 执行任务按钮超时处理优化
**文件**: `main.py`
**位置**: `launch_hermes_task` 方法

**问题**: 使用 `subprocess.run` 无法中途取消，超时处理不够灵活
**修复**: 改用 `subprocess.Popen` + `communicate(timeout=120)`，支持 kill 进程

```python
# 修复前
result = subprocess.run([...], timeout=180)

# 修复后
process = subprocess.Popen([...])
try:
    stdout, stderr = process.communicate(timeout=120)
except subprocess.TimeoutExpired:
    process.kill()
    self.root.after(0, lambda: self.say("系统", "❌ Hermes 响应超时..."))
```

### 3. 测试脚本
**文件**: `test_hermes_fix.py`

创建测试脚本验证修复效果：
- WSL 命令执行测试
- Hermes 桥接测试
- 超时处理测试

## 运行测试

```bash
python test_hermes_fix.py
```

## 预期效果

1. **AI 助手对话框**: 使用 Hermes 时，如果 60 秒内无响应，会显示超时提示而不是卡死
2. **执行任务按钮**: 如果 120 秒内无响应，会显示超时提示并终止进程
3. **整体体验**: GUI 不再因为 Hermes 调用而卡死

## 已知限制

1. **首次启动仍慢**: WSL 和 Hermes 的首次启动仍需较长时间（30-60秒）
2. **进程常驻未实现**: 仍然每次调用都启动新的 WSL 进程
3. **网络依赖**: Hermes 需要网络连接，离线时无法使用

## 后续优化建议

1. **实现进程常驻**: 保持 WSL 进程在后台运行，减少启动时间
2. **添加连接池**: 复用 WSL 连接，减少开销
3. **本地缓存**: 缓存常见查询结果，减少重复调用
4. **异步预加载**: 启动时预加载 Hermes，减少首次响应时间
