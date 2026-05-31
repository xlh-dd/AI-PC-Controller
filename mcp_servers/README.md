# AI-PC-Controller MCP Servers → OpenHuman Integration

## 概述

4 个 MCP Server 将 AI-PC-Controller 的核心能力桥接到任何支持 MCP 协议的 AI 平台（OpenHuman、Claude Desktop 等）。

| Server | 工具数 | 能力 |
|--------|--------|------|
| system-control | 17 | 音量、关机/重启/睡眠/休眠、截图、剪贴板、定时任务 |
| macro-recorder | 9 | 鼠标/键盘宏录制回放、屏幕截图 |
| file-manager | 9 | 大文件扫描、查重、智能归类、批量重命名、磁盘分析 |
| wechat-control | 5 | 微信发送消息/文件、联系人搜索 |

## 前置条件

```powershell
# Python 3.10+ 已安装
pip install mcp pyautogui pyperclip Pillow
```

## 方式一：接入 OpenHuman

### 1. 安装 OpenHuman

下载安装器：`C:\Users\Administrator\Desktop\AI\dist\OpenHuman_0.56.0_x64-setup.exe`

双击运行安装。安装完成后，OpenHuman 配置文件位于：
- `%APPDATA%\openhuman\config.yaml` 或 `~/.openhuman/config.yaml`

### 2. 配置 MCP Servers

将 `mcp_servers/openhuman_config.json` 的内容合并到 OpenHuman 的 `mcp_config` 部分：

```yaml
# openhuman config.yaml
mcp:
  servers:
    system-control:
      command: python
      args: ["mcp_servers/system_control_server.py"]
      cwd: "C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器"
    macro-recorder:
      command: python
      args: ["mcp_servers/macro_server.py"]
      cwd: "C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器"
    file-manager:
      command: python
      args: ["mcp_servers/file_manager_server.py"]
      cwd: "C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器"
    wechat-control:
      command: python
      args: ["mcp_servers/wechat_server.py"]
      cwd: "C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器"
```

### 3. 重启 OpenHuman

配置生效后，在 OpenHuman 中即可调用 40 个系统控制工具。

## 方式二：接入 Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "system-control": {
      "command": "python",
      "args": ["C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器\\mcp_servers\\system_control_server.py"]
    },
    "macro-recorder": {
      "command": "python",
      "args": ["C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器\\mcp_servers\\macro_server.py"]
    },
    "file-manager": {
      "command": "python",
      "args": ["C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器\\mcp_servers\\file_manager_server.py"]
    },
    "wechat-control": {
      "command": "python",
      "args": ["C:\\Users\\Administrator\\Desktop\\AI\\AI电脑控制器\\mcp_servers\\wechat_server.py"]
    }
  }
}
```

## 手动测试

```powershell
cd "C:\Users\Administrator\Desktop\AI\AI电脑控制器"
python -c "
from mcp_servers.system_control_server import mcp
tools = mcp._tool_manager.list_tools()
for t in tools: print(f'{t.name}: {t.description}')
"
```

## 文件结构

```
mcp_servers/
├── system_control_server.py    # 系统控制 (17 tools)
├── macro_server.py             # 宏录制 (9 tools)
├── file_manager_server.py      # 文件管理 (9 tools)
├── wechat_server.py            # 微信控制 (5 tools)
└── openhuman_config.json       # OpenHuman 配置参考
```

## 协议

MCP stdio (JSON-RPC 2.0) / FastMCP SDK 1.27+
