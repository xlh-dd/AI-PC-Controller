#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""System Control MCP Server - Windows system control bridge
Protocol: MCP stdio via FastMCP"""
import json, sys, subprocess, os, asyncio

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("system-control-server")

def _ps(cmd, timeout=30):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
        capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    return {"ok": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}

@mcp.tool()
def sys_volume_set(level: int) -> str:
    """Set system volume (0-100)"""
    import ctypes
    vol = int(level / 100 * 0xFFFF)
    ctypes.windll.winmm.waveOutSetVolume(0, vol * 0x10000 + vol)
    return json.dumps({"volume_level": level})

@mcp.tool()
def sys_volume_mute() -> str:
    """Toggle system mute"""
    import ctypes
    VK_VOLUME_MUTE = 0xAD
    ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0x0001, 0)
    ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0x0003, 0)
    return json.dumps({"action": "toggled_mute"})

@mcp.tool()
def sys_shutdown(force: bool = False) -> str:
    """Shutdown computer (10s delay, can be cancelled)"""
    f = "/f" if force else ""
    _ps(f"shutdown /s /t 10 {f}")
    return json.dumps({"shutdown_scheduled": "10s"})

@mcp.tool()
def sys_restart(force: bool = False) -> str:
    """Restart computer (10s delay, can be cancelled)"""
    f = "/f" if force else ""
    _ps(f"shutdown /r /t 10 {f}")
    return json.dumps({"restart_scheduled": "10s"})

@mcp.tool()
def sys_sleep() -> str:
    """Enter sleep mode"""
    _ps("Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $true)")
    return json.dumps({"action": "sleep"})

@mcp.tool()
def sys_hibernate() -> str:
    """Enter hibernation"""
    _ps("shutdown /h")
    return json.dumps({"action": "hibernate"})

@mcp.tool()
def sys_lock() -> str:
    """Lock workstation"""
    _ps("rundll32.exe user32.dll,LockWorkStation")
    return json.dumps({"action": "locked"})

@mcp.tool()
def sys_logout() -> str:
    """Log out current user"""
    _ps("shutdown /l")
    return json.dumps({"action": "logout"})

@mcp.tool()
def sys_cancel_shutdown() -> str:
    """Cancel planned shutdown or restart"""
    _ps("shutdown /a")
    return json.dumps({"cancelled": True})

@mcp.tool()
def sys_open_task_manager() -> str:
    """Open Task Manager"""
    subprocess.Popen("taskmgr.exe")
    return json.dumps({"opened": "task_manager"})

@mcp.tool()
def sys_get_power_status() -> str:
    """Get power/battery status"""
    r = _ps("Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue | Select-Object EstimatedChargeRemaining,BatteryStatus | ConvertTo-Json -Compress")
    if r["stdout"]:
        info = json.loads(r["stdout"])
        status_map = {1: "discharging", 2: "AC_power", 3: "fully_charged", 4: "low", 255: "no_battery"}
        info["status_text"] = status_map.get(info.get("BatteryStatus", 255), "unknown")
        return json.dumps({"power": info})
    return json.dumps({"power": "no_battery_detected"})

@mcp.tool()
def sys_timer_shutdown(seconds: int) -> str:
    """Schedule shutdown in N seconds"""
    _ps(f"shutdown /s /t {seconds}")
    return json.dumps({"timer_shutdown_seconds": seconds})

@mcp.tool()
def sys_timer_restart(seconds: int) -> str:
    """Schedule restart in N seconds"""
    _ps(f"shutdown /r /t {seconds}")
    return json.dumps({"timer_restart_seconds": seconds})

@mcp.tool()
def sys_open_app(name: str) -> str:
    """Open application by name (notepad, calc, cmd, powershell, explorer, task manager, paint, control panel, device manager, registry editor)"""
    known = {
        "notepad": "notepad.exe", "calc": "calc.exe", "calculator": "calc.exe",
        "cmd": "cmd.exe", "powershell": "powershell.exe", "explorer": "explorer.exe",
        "task manager": "taskmgr.exe", "paint": "mspaint.exe", "control panel": "control.exe",
        "device manager": "devmgmt.msc", "disk management": "diskmgmt.msc",
        "registry editor": "regedit.exe", "event viewer": "eventvwr.msc",
        "services": "services.msc", "performance": "perfmon.msc"
    }
    target = known.get(name.lower(), name + ".exe" if "." not in name else name)
    subprocess.Popen(target, shell=True)
    return json.dumps({"opened": target})

@mcp.tool()
def sys_screenshot(region: str = "") -> str:
    """Take screenshot. Optional region as WxH+X+Y like 1920x1080+0+0"""
    try:
        import io, base64
        from PIL import ImageGrab
        if region:
            parts = region.replace("x", " ").replace("+", " ").split()
            if len(parts) >= 4:
                bbox = tuple(int(p) for p in parts[:4])
                img = ImageGrab.grab(bbox=bbox)
            else:
                img = ImageGrab.grab()
        else:
            img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return json.dumps({"screenshot_base64": base64.b64encode(buf.getvalue()).decode(), "format": "png", "size_bytes": len(buf.getvalue())})
    except ImportError:
        return json.dumps({"error": "Pillow not installed. Run: pip install Pillow"})

@mcp.tool()
def sys_clipboard_get() -> str:
    """Get clipboard text content"""
    import ctypes, ctypes.wintypes
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(0):
        return json.dumps({"error": "Cannot open clipboard"})
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        kernel32.GlobalLock.restype = ctypes.c_wchar_p
        text = kernel32.GlobalLock(h) or ""
        kernel32.GlobalUnlock(h)
        return json.dumps({"clipboard": text})
    finally:
        user32.CloseClipboard()

@mcp.tool()
def sys_clipboard_set(text: str) -> str:
    """Set clipboard text content"""
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(0):
        return json.dumps({"error": "Cannot open clipboard"})
    try:
        user32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        h = kernel32.GlobalAlloc(0x0042, len(buf) * 2)
        ctypes.memmove(kernel32.GlobalLock(h), buf, len(buf) * 2)
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(13, h)
        return json.dumps({"set_clipboard_length": len(text)})
    finally:
        user32.CloseClipboard()

if __name__ == "__main__":
    mcp.run(transport="stdio")