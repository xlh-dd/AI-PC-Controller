#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WeChat Control MCP Server - WeChat desktop automation"""
import json, os, subprocess, time
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("wechat-control-server")

def _wx_running():
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WeChat.exe"],
                           capture_output=True, encoding="utf-8")
        return "WeChat.exe" in r.stdout
    except Exception:
        return False

def _ensure_libs():
    try:
        import pyautogui, pyperclip
    except ImportError:
        os.system("pip install pyautogui pyperclip -q")
        import pyautogui, pyperclip
    return pyautogui, pyperclip

@mcp.tool()
def wx_check_status() -> str:
    """Check if WeChat desktop is running"""
    return json.dumps({"wechat_running": _wx_running()})

@mcp.tool()
def wx_launch() -> str:
    """Launch WeChat desktop app"""
    paths = [
        r"C:\Program Files\Tencent\WeChat\WeChat.exe",
        r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
    ]
    for wp in paths:
        if os.path.exists(wp):
            subprocess.Popen([wp])
            return json.dumps({"launched": True, "path": wp})
    return json.dumps({"error": "WeChat.exe not found in known locations"})

@mcp.tool()
def wx_send_message(contact: str, message: str) -> str:
    """Send a text message to a WeChat contact. Requires WeChat desktop running."""
    if not _wx_running():
        return json.dumps({"error": "WeChat not running"})
    pg, clip = _ensure_libs()
    pg.FAILSAFE = True
    # Search contact
    pg.hotkey("ctrl", "f")
    time.sleep(0.3)
    clip.copy(contact)
    pg.hotkey("ctrl", "v")
    time.sleep(0.5)
    pg.press("enter")
    time.sleep(0.3)
    # Type message
    clip.copy(message)
    pg.hotkey("ctrl", "v")
    time.sleep(0.2)
    pg.press("enter")
    return json.dumps({"sent_to": contact, "message_length": len(message)})

@mcp.tool()
def wx_send_file(contact: str, file_path: str) -> str:
    """Send a file to a WeChat contact. Requires WeChat desktop running."""
    if not os.path.exists(file_path):
        return json.dumps({"error": f"File not found: {file_path}"})
    if not _wx_running():
        return json.dumps({"error": "WeChat not running"})
    pg, clip = _ensure_libs()
    pg.FAILSAFE = True
    pg.hotkey("ctrl", "f")
    time.sleep(0.3)
    clip.copy(contact)
    pg.hotkey("ctrl", "v")
    time.sleep(0.5)
    pg.press("enter")
    time.sleep(0.3)
    clip.copy(file_path)
    pg.hotkey("ctrl", "v")
    time.sleep(0.3)
    pg.press("enter")
    return json.dumps({"sent_file_to": contact, "file": os.path.basename(file_path)})

@mcp.tool()
def wx_search_contact(contact: str) -> str:
    """Search for and open a contact chat window in WeChat"""
    if not _wx_running():
        return json.dumps({"error": "WeChat not running"})
    pg, clip = _ensure_libs()
    pg.FAILSAFE = True
    pg.hotkey("ctrl", "f")
    time.sleep(0.3)
    clip.copy(contact)
    pg.hotkey("ctrl", "v")
    time.sleep(0.5)
    pg.press("enter")
    time.sleep(0.5)
    return json.dumps({"searched": contact})

if __name__ == "__main__":
    mcp.run(transport="stdio")