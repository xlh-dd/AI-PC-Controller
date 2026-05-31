#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Macro Recorder MCP Server - keyboard/mouse macro automation"""
import json, os, time
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("macro-recorder-server")

MACRO_DIR = os.path.join(os.path.dirname(__file__), "..", "macros")
os.makedirs(MACRO_DIR, exist_ok=True)

def _pyautogui():
    try:
        import pyautogui
        return pyautogui
    except ImportError:
        os.system("pip install pyautogui -q")
        import pyautogui
        return pyautogui

@mcp.tool()
def macro_list() -> str:
    """List all saved macros"""
    macros = []
    if os.path.exists(MACRO_DIR):
        for f in os.listdir(MACRO_DIR):
            if f.endswith(".json"):
                fp = os.path.join(MACRO_DIR, f)
                with open(fp, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                macros.append({"name": data.get("name", f[:-5]),
                               "actions": data.get("action_count", len(data.get("actions", []))),
                               "size_bytes": os.path.getsize(fp),
                               "created": data.get("created", "unknown")})
    return json.dumps({"macros": macros})

@mcp.tool()
def macro_delete(name: str) -> str:
    """Delete a saved macro"""
    fp = os.path.join(MACRO_DIR, f"{name}.json")
    if os.path.exists(fp):
        os.remove(fp)
        return json.dumps({"deleted": name})
    return json.dumps({"error": f"Macro not found: {name}"})

@mcp.tool()
def macro_play(name: str, speed: float = 1.0) -> str:
    """Play back a saved macro at given speed multiplier"""
    fp = os.path.join(MACRO_DIR, f"{name}.json")
    if not os.path.exists(fp):
        return json.dumps({"error": f"Macro not found: {name}"})
    with open(fp, "r", encoding="utf-8") as f:
        macro = json.load(f)
    pg = _pyautogui()
    pg.FAILSAFE = True
    count = 0
    for action in macro.get("actions", []):
        t = action.get("type")
        if t == "mouse_move":
            pg.moveTo(action["x"], action["y"], duration=action.get("duration", 0.5) / speed)
        elif t == "click":
            pg.click(button=action.get("button", "left"))
        elif t == "type":
            pg.typewrite(action["text"], interval=action.get("interval", 0.05) / speed)
        elif t == "press":
            pg.hotkey(*action["keys"])
        count += 1
    return json.dumps({"played": name, "actions_executed": count, "speed": speed})

@mcp.tool()
def macro_mouse_move(x: int, y: int, duration: float = 0.5) -> str:
    """Move mouse to (x, y)"""
    pg = _pyautogui()
    pg.moveTo(x, y, duration=duration)
    return json.dumps({"moved_to": [x, y]})

@mcp.tool()
def macro_mouse_click(button: str = "left") -> str:
    """Click at current position (left, right, middle)"""
    pg = _pyautogui()
    pg.click(button=button)
    return json.dumps({"clicked": button})

@mcp.tool()
def macro_type(text: str, interval: float = 0.05) -> str:
    """Type text at current cursor"""
    pg = _pyautogui()
    pg.typewrite(text, interval=interval)
    return json.dumps({"typed_length": len(text)})

@mcp.tool()
def macro_key_press(keys: str) -> str:
    """Press key combo like 'ctrl+c', 'alt+tab'. Use comma for multi-key."""
    pg = _pyautogui()
    key_list = keys.replace("+", ",").split(",")
    if len(key_list) > 1:
        pg.hotkey(*key_list)
    else:
        pg.press(key_list[0])
    return json.dumps({"pressed": keys})

@mcp.tool()
def macro_screenshot(filename: str = "screenshot", region: str = "") -> str:
    """Take screenshot. region format: left,top,width,height"""
    pg = _pyautogui()
    if region:
        parts = [int(p.strip()) for p in region.split(",")]
        if len(parts) >= 4:
            img = pg.screenshot(region=tuple(parts[:4]))
        else:
            img = pg.screenshot()
    else:
        img = pg.screenshot()
    ss_dir = os.path.join(MACRO_DIR, "screenshots")
    os.makedirs(ss_dir, exist_ok=True)
    fp = os.path.join(ss_dir, filename + ".png")
    img.save(fp)
    return json.dumps({"screenshot_path": fp, "size_bytes": os.path.getsize(fp)})

@mcp.tool()
def macro_save_from_recording(name: str, json_actions: str) -> str:
    """Save a macro from externally recorded JSON actions.
    json_actions should be a JSON array of action objects like:
    [{"type":"mouse_move","x":100,"y":200,"duration":0.5},{"type":"click","button":"left"},{"type":"type","text":"hello"}]"""
    try:
        actions = json.loads(json_actions)
        macro = {
            "name": name,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action_count": len(actions),
            "actions": actions
        }
        fp = os.path.join(MACRO_DIR, f"{name}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(macro, f, ensure_ascii=False, indent=2)
        return json.dumps({"saved": name, "path": fp, "actions": len(actions)})
    except Exception as e:
        return json.dumps({"error": str(e)})

if __name__ == "__main__":
    mcp.run(transport="stdio")