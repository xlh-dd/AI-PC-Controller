# Auto-generated command registry handlers
# Migrated from main.py execute_ai_command elif chain

import os
import subprocess
from tkinter import messagebox

from modules.ai_agent import AIAgent
import psutil
import shutil
from datetime import datetime
from PIL import ImageGrab
import webbrowser
def _register_migrated_commands(registry):
    """迁移自 main.py execute_ai_command 的 elif 链"""

    def cmd_find_duplicates(context, cmd_data):
        """find_duplicates"""
        context.find_duplicate_files()
    registry.register_handler("find_duplicates", cmd_find_duplicates, "find_duplicates")

    def cmd_find_large(context, cmd_data):
        """find_large"""
        context.find_large_files()
    registry.register_handler("find_large", cmd_find_large, "find_large")

    def cmd_clean_empty(context, cmd_data):
        """clean_empty"""
        context.clean_empty_files()
    registry.register_handler("clean_empty", cmd_clean_empty, "clean_empty")

    def cmd_rename_files(context, cmd_data):
        """rename_files"""
        pattern = cmd_data.get("pattern", "")
        prefix = cmd_data.get("prefix", "")
        start_num = cmd_data.get("start_num", 1)
        ext_filter = cmd_data.get("ext_filter", "")
        desc = f"{pattern} {prefix} {start_num} {ext_filter}".strip()
        if desc:
            context.rename_folder(desc)
        else:
            context.say("系统", "重命名参数不明确，请提供更详细的描述。")
    registry.register_handler("rename_files", cmd_rename_files, "rename_files")

    def cmd_rename(context, cmd_data):
        """rename"""
        desc = cmd_data.get("description", "")
        if desc:
            context.rename_folder(desc)
        else:
            context.say("系统", "改名描述不明确。")
    registry.register_handler("rename", cmd_rename, "rename")

    def cmd_shutdown(context, cmd_data):
        """shutdown"""
        delay = cmd_data.get("delay", 0)
        if messagebox.askyesno("确认", f"确定在 {delay} 分钟后关机？" if delay else "确定立即关机？"):
            seconds = int(delay) * 60 if delay else 0
            subprocess.run(["shutdown", "/s", "/t", str(seconds)], shell=False)
            context.say("系统", f"已设定 {delay} 分钟后关机。" if delay else "正在关机...")
    registry.register_handler("shutdown", cmd_shutdown, "shutdown")

    def cmd_restart(context, cmd_data):
        """restart"""
        delay = cmd_data.get("delay", 0)
        if messagebox.askyesno("确认", f"确定在 {delay} 分钟后重启？" if delay else "确定立即重启？"):
            seconds = int(delay) * 60 if delay else 0
            subprocess.run(["shutdown", "/r", "/t", str(seconds)], shell=False)
            context.say("系统", f"已设定 {delay} 分钟后重启。" if delay else "正在重启...")
    registry.register_handler("restart", cmd_restart, "restart")

    def cmd_timer_shutdown(context, cmd_data):
        """timer_shutdown"""
        delay = cmd_data.get("delay", 0)
        if messagebox.askyesno("确认", f"确定在 {delay} 分钟后关机？"):
            seconds = delay * 60
            subprocess.run(["shutdown", "/s", "/t", str(seconds)], shell=False)
            context.say("系统", f"已设定 {delay} 分钟后关机。")
    registry.register_handler("timer_shutdown", cmd_timer_shutdown, "timer_shutdown")

    def cmd_timer_restart(context, cmd_data):
        """timer_restart"""
        delay = cmd_data.get("delay", 0)
        if messagebox.askyesno("确认", f"确定在 {delay} 分钟后重启？"):
            seconds = delay * 60
            subprocess.run(["shutdown", "/r", "/t", str(seconds)], shell=False)
            context.say("系统", f"已设定 {delay} 分钟后重启。")
    registry.register_handler("timer_restart", cmd_timer_restart, "timer_restart")

    def cmd_cancel_shutdown(context, cmd_data):
        """cancel_shutdown"""
        subprocess.run(["shutdown", "/a"], shell=False)
        context.say("系统", "已取消关机/重启计划。")
    registry.register_handler("cancel_shutdown", cmd_cancel_shutdown, "cancel_shutdown")

    def cmd_sleep(context, cmd_data):
        """sleep"""
        delay = cmd_data.get("delay", 0)
        if delay:
            context.say("系统", f"将在 {delay} 分钟后进入睡眠状态...")
            time.sleep(delay * 60)
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"], shell=False)
        context.say("系统", "正在进入睡眠状态...")
    registry.register_handler("sleep", cmd_sleep, "sleep")

    def cmd_lock(context, cmd_data):
        """lock"""
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        context.say("系统", "正在锁定屏幕...")
    registry.register_handler("lock", cmd_lock, "lock")

    def cmd_logout(context, cmd_data):
        """logout"""
        subprocess.run(["shutdown", "/l"], shell=False)
    registry.register_handler("logout", cmd_logout, "logout")

    def cmd_list_files(context, cmd_data):
        """list_files"""
        path = cmd_data.get("path")
        if path:
            context.list_files(path)
        else:
            context.list_files()
    registry.register_handler("list_files", cmd_list_files, "list_files")

    def cmd_ai_chat(context, cmd_data):
        """ai_chat"""
        context.ai_chat_dialog()
    registry.register_handler("ai_chat", cmd_ai_chat, "ai_chat")

    def cmd_send_wechat(context, cmd_data):
        """send_wechat"""
        target = cmd_data.get("target")
        message = cmd_data.get("message")
        if target and message:
            def send_with_feedback():
                success = context.wechat_controller.send_wechat_message(target, message)
                if success:
                    context.say("系统", f"✅ 已成功给{target}发送消息：{message}")
                else:
                    context.say("系统", f"❌ 发送消息失败，请检查微信是否正常运行。")
            threading.Thread(target=send_with_feedback, daemon=True).start()
        else:
            context.say("系统", "发送消息参数不完整，请指定目标和内容。")
    registry.register_handler("send_wechat", cmd_send_wechat, "send_wechat")

    def cmd_schedule_wechat(context, cmd_data):
        """schedule_wechat"""
        target = cmd_data.get("target")
        message = cmd_data.get("message")
        send_time = cmd_data.get("send_time")
        schedule_type = cmd_data.get("schedule_type", "daily")
        if target and message and send_time:
            context.add_wechat_scheduled_task(target, message, send_time, schedule_type)
        else:
            context.say("系统", "定时消息参数不完整，请指定目标、内容和时间。")
    registry.register_handler("schedule_wechat", cmd_schedule_wechat, "schedule_wechat")

    def cmd_schedule_task(context, cmd_data):
        """schedule_task"""
        task = cmd_data.get("task")
        send_time = cmd_data.get("send_time")
        schedule_type = cmd_data.get("schedule_type", "daily")
        if task and send_time:
            context.task_scheduler.add_task(
                name=task,
                target="wechat",
                send_time=send_time,
                message=task,
                schedule_type=schedule_type
            )
            context.say("系统", f"✅ 已添加定时任务：{task}，执行时间：{send_time}")
        else:
            context.say("系统", "定时任务参数不完整，请指定任务内容和时间。")
    registry.register_handler("schedule_task", cmd_schedule_task, "schedule_task")

    def cmd_run_automation(context, cmd_data):
        """run_automation"""
        task_name = cmd_data.get("task_name")
        if task_name:
            context.say("系统", f"正在执行自动化任务：{task_name}")
            if "文件整理" in task_name:
                context.auto_sort_files()
            elif "批量重命名" in task_name or "重命名" in task_name:
                context.rename_folder("")
            elif "查找重复" in task_name:
                context.find_duplicate_files()
            elif "清理空文件" in task_name:
                context.clean_empty_files()
            elif "查找大文件" in task_name:
                context.find_large_files()
            else:
                context.say("系统", f"未找到自动化任务：{task_name}")
        else:
            context.say("系统", "无法识别要执行的自动化任务。")
    registry.register_handler("run_automation", cmd_run_automation, "run_automation")

    def cmd_custom_command(context, cmd_data):
        """custom_command"""
        cmd = cmd_data.get("command")
        if cmd:
            context.custom_command(cmd)
        else:
            context.say("系统", "无法识别要执行的命令。")
    registry.register_handler("custom_command", cmd_custom_command, "custom_command")

    def cmd_start_listening(context, cmd_data):
        """start_listening"""
        if not context.wechat_listener_running:
            context.toggle_wechat_listener()
        else:
            context.say("系统", "微信监听已在运行中。")
    registry.register_handler("start_listening", cmd_start_listening, "start_listening")

    def cmd_stop_listening(context, cmd_data):
        """stop_listening"""
        if context.wechat_listener_running:
            context.toggle_wechat_listener()
        else:
            context.say("系统", "微信监听未在运行。")
    registry.register_handler("stop_listening", cmd_stop_listening, "stop_listening")

    def cmd_kill_process(context, cmd_data):
        """kill_process"""
        process_name = cmd_data.get("process_name")
        pid = cmd_data.get("pid")
        if process_name:
            try:
                agent = context._create_ai_agent()
                result = agent.manage_processes(action="kill_by_name", process_name=process_name)
                if result.get("success"):
                    context.say("系统", f"✅ 已结束进程：{process_name}")
                else:
                    context.say("系统", f"❌ 结束进程失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 结束进程失败：{str(e)}")
        elif pid:
            try:
                agent = context._create_ai_agent()
                result = agent.manage_processes(action="kill", pid=pid)
                if result.get("success"):
                    context.say("系统", f"✅ 已结束PID为{pid}的进程")
                else:
                    context.say("系统", f"❌ 结束进程失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 结束进程失败：{str(e)}")
        else:
            context.say("系统", "请指定要结束的进程名称或PID。")
    registry.register_handler("kill_process", cmd_kill_process, "kill_process")

    def cmd_minimize_window(context, cmd_data):
        """minimize_window"""
        window_title = cmd_data.get("window_title")
        if window_title:
            try:
                agent = context._create_ai_agent()
                result = agent.manage_windows(action="minimize", title_pattern=window_title)
                if result.get("success"):
                    context.say("系统", f"✅ 已最小化窗口：{window_title}")
                else:
                    context.say("系统", f"❌ 最小化窗口失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 操作失败：{str(e)}")
        else:
            context.say("系统", "请指定窗口标题。")
    registry.register_handler("minimize_window", cmd_minimize_window, "minimize_window")

    def cmd_maximize_window(context, cmd_data):
        """maximize_window"""
        window_title = cmd_data.get("window_title")
        if window_title:
            try:
                agent = context._create_ai_agent()
                result = agent.manage_windows(action="maximize", title_pattern=window_title)
                if result.get("success"):
                    context.say("系统", f"✅ 已最大化窗口：{window_title}")
                else:
                    context.say("系统", f"❌ 最大化窗口失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 操作失败：{str(e)}")
        else:
            context.say("系统", "请指定窗口标题。")
    registry.register_handler("maximize_window", cmd_maximize_window, "maximize_window")

    def cmd_close_window(context, cmd_data):
        """close_window"""
        window_title = cmd_data.get("window_title")
        if window_title:
            try:
                agent = context._create_ai_agent()
                result = agent.manage_windows(action="close", title_pattern=window_title)
                if result.get("success"):
                    context.say("系统", f"✅ 已关闭窗口：{window_title}")
                else:
                    context.say("系统", f"❌ 关闭窗口失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 操作失败：{str(e)}")
        else:
            context.say("系统", "请指定窗口标题。")
    registry.register_handler("close_window", cmd_close_window, "close_window")

    def cmd_activate_window(context, cmd_data):
        """activate_window"""
        window_title = cmd_data.get("window_title")
        if window_title:
            try:
                agent = context._create_ai_agent()
                result = agent.manage_windows(action="activate", title_pattern=window_title)
                if result.get("success"):
                    context.say("系统", f"✅ 已激活窗口：{window_title}")
                else:
                    context.say("系统", f"❌ 激活窗口失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 操作失败：{str(e)}")
        else:
            context.say("系统", "请指定窗口标题。")
    registry.register_handler("activate_window", cmd_activate_window, "activate_window")

    def cmd_volume_up(context, cmd_data):
        """volume_up"""
        steps = cmd_data.get("steps", 5)
        try:
            agent = context._create_ai_agent()
            result = agent.control_volume(action="up", steps=steps)
            if result.get("success"):
                context.say("系统", f"✅ 音量已增大{steps}步")
            else:
                context.say("系统", f"❌ 音量控制失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("volume_up", cmd_volume_up, "volume_up")

    def cmd_volume_down(context, cmd_data):
        """volume_down"""
        steps = cmd_data.get("steps", 5)
        try:
            agent = context._create_ai_agent()
            result = agent.control_volume(action="down", steps=steps)
            if result.get("success"):
                context.say("系统", f"✅ 音量已减小{steps}步")
            else:
                context.say("系统", f"❌ 音量控制失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("volume_down", cmd_volume_down, "volume_down")

    def cmd_set_volume(context, cmd_data):
        """set_volume"""
        level = cmd_data.get("level", 50)
        try:
            agent = context._create_ai_agent()
            result = agent.control_volume(action="set", level=level)
            if result.get("success"):
                context.say("系统", f"✅ 音量已设置为{level}%")
            else:
                context.say("系统", f"❌ 音量控制失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("set_volume", cmd_set_volume, "set_volume")

    def cmd_toggle_mute(context, cmd_data):
        """toggle_mute"""
        try:
            agent = context._create_ai_agent()
            result = agent.control_volume(action="toggle_mute")
            if result.get("success"):
                context.say("系统", result.get("message", "✅ 静音状态已切换"))
            else:
                context.say("系统", f"❌ 操作失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("toggle_mute", cmd_toggle_mute, "toggle_mute")

    def cmd_take_screenshot(context, cmd_data):
        """take_screenshot"""
        save_path = cmd_data.get("save_path")
        try:
            agent = context._create_ai_agent()
            result = agent.take_screenshot(save_path=save_path)
            if result.get("success"):
                context.say("系统", f"✅ 截图已保存到：{result.get('path', save_path or '临时文件')}")
            else:
                context.say("系统", f"❌ 截图失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("take_screenshot", cmd_take_screenshot, "take_screenshot")

    def cmd_get_clipboard(context, cmd_data):
        """get_clipboard"""
        try:
            agent = context._create_ai_agent()
            result = agent.control_clipboard(action="get")
            if result.get("success"):
                content = result.get("content", "")
                if len(content) > 100:
                    content = content[:100] + "..."
                context.say("系统", f"📋 剪贴板内容：{content}")
            else:
                context.say("系统", f"❌ 获取剪贴板失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("get_clipboard", cmd_get_clipboard, "get_clipboard")

    def cmd_set_clipboard(context, cmd_data):
        """set_clipboard"""
        content = cmd_data.get("content")
        if content:
            try:
                agent = context._create_ai_agent()
                result = agent.control_clipboard(action="set", content=content)
                if result.get("success"):
                    context.say("系统", f"✅ 已复制到剪贴板：{content[:50]}...")
                else:
                    context.say("系统", f"❌ 设置剪贴板失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 操作失败：{str(e)}")
        else:
            context.say("系统", "请指定要复制的内容。")
    registry.register_handler("set_clipboard", cmd_set_clipboard, "set_clipboard")

    def cmd_get_system_info(context, cmd_data):
        """get_system_info"""
        try:
            agent = context._create_ai_agent()
            result = agent.get_system_info()
            if result.get("success"):
                info = result.get("system_info", {})
                msg = f"💻 系统信息：\n平台：{info.get('platform', '未知')}\n系统：{info.get('platform_release', '未知')}\nCPU：{info.get('cpu_percent', '未知')}%\n内存：{info.get('memory_percent', '未知')}%"
                context.say("系统", msg)
            else:
                context.say("系统", f"❌ 获取系统信息失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("get_system_info", cmd_get_system_info, "get_system_info")

    def cmd_hibernate(context, cmd_data):
        """hibernate"""
        try:
            agent = context._create_ai_agent()
            result = agent._system_controller.hibernate() if agent._system_controller else None
            if result and result.get("success"):
                context.say("系统", "✅ 正在进入休眠状态...")
            else:
                context.say("系统", "❌ 休眠失败")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("hibernate", cmd_hibernate, "hibernate")

    def cmd_turn_off_display(context, cmd_data):
        """turn_off_display"""
        try:
            agent = context._create_ai_agent()
            result = agent._system_controller.turn_off_display() if agent._system_controller else None
            if result and result.get("success"):
                context.say("系统", "✅ 显示器已关闭")
            else:
                context.say("系统", "❌ 关闭显示器失败")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("turn_off_display", cmd_turn_off_display, "turn_off_display")

    def cmd_list_processes(context, cmd_data):
        """list_processes"""
        filter_str = cmd_data.get("filter", "")
        try:
            agent = context._create_ai_agent()
            result = agent.manage_processes(action="list", filter_str=filter_str)
            if result.get("success"):
                processes = result.get("processes", [])[:10]
                msg = "📋 运行中的进程：\n"
                for p in processes:
                    msg += f"- {p.get('name', '未知')} (PID:{p.get('pid', '?')}) CPU:{p.get('cpu_percent', 0)}%\n"
                context.say("系统", msg)
            else:
                context.say("系统", f"❌ 获取进程列表失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("list_processes", cmd_list_processes, "list_processes")

    def cmd_list_windows(context, cmd_data):
        """list_windows"""
        filter_str = cmd_data.get("filter", "")
        try:
            agent = context._create_ai_agent()
            result = agent.manage_windows(action="list", filter_str=filter_str)
            if result.get("success"):
                windows = result.get("windows", [])[:10]
                msg = "📋 当前窗口：\n"
                for w in windows:
                    title = w.get("title", "未知")[:30]
                    msg += f"- {title}\n"
                context.say("系统", msg)
            else:
                context.say("系统", f"❌ 获取窗口列表失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("list_windows", cmd_list_windows, "list_windows")

    def cmd_get_network_info(context, cmd_data):
        """get_network_info"""
        try:
            agent = context._create_ai_agent()
            result = agent.control_network(action="get_info")
            if result.get("success"):
                interfaces = result.get("interfaces", [])
                msg = "🌐 网络信息：\n"
                for iface in interfaces[:5]:
                    msg += f"- {iface.get('interface', '未知')}: {iface.get('ipv4', '未连接')} ({iface.get('status', '未知')})\n"
                context.say("系统", msg)
            else:
                context.say("系统", f"❌ 获取网络信息失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("get_network_info", cmd_get_network_info, "get_network_info")

    def cmd_toggle_wifi(context, cmd_data):
        """toggle_wifi"""
        enable = cmd_data.get("enable")
        try:
            agent = context._create_ai_agent()
            result = agent.control_network(action="toggle_wifi", enable=enable)
            if result.get("success"):
                context.say("系统", result.get("message", "✅ Wi-Fi状态已切换"))
            else:
                context.say("系统", f"❌ Wi-Fi控制失败：{result.get('error', '未知错误')}")
        except Exception as e:
            context.say("系统", f"❌ 操作失败：{str(e)}")
    registry.register_handler("toggle_wifi", cmd_toggle_wifi, "toggle_wifi")

    def cmd_speak_text(context, cmd_data):
        """speak_text"""
        text = cmd_data.get("text")
        if text:
            try:
                agent = context._create_ai_agent()
                result = agent.speak_text(text=text)
                if result.get("success"):
                    context.say("系统", f"🔊 正在朗读：{text[:30]}...")
                else:
                    context.say("系统", f"❌ 语音合成失败：{result.get('error', '未知错误')}")
            except Exception as e:
                context.say("系统", f"❌ 操作失败：{str(e)}")
        else:
            context.say("系统", "请指定要朗读的文本。")
    registry.register_handler("speak_text", cmd_speak_text, "speak_text")

    def cmd_ai_agent(context, cmd_data):
        """ai_agent"""
        task = cmd_data.get("task")
        if task:
            context.say("系统", f"🤔 正在执行AI任务：{task}")
            threading.Thread(target=context._run_ai_agent_task_from_command, args=(task,), daemon=True).start()
        else:
            context.say("系统", "请指定AI任务内容。")
    registry.register_handler("ai_agent", cmd_ai_agent, "ai_agent")

    def cmd_move_file(context, cmd_data):
        """move_file"""
        source = cmd_data.get("source")
        destination = cmd_data.get("destination")
        if source and destination:
            try:
                shutil.move(source, destination)
                context.say("系统", f"✅ 已移动文件：{source} → {destination}")
            except Exception as e:
                context.say("系统", f"❌ 移动失败：{str(e)}")
        else:
            context.say("系统", "请指定源路径和目标路径。")
    registry.register_handler("move_file", cmd_move_file, "move_file")

    def cmd_copy_file(context, cmd_data):
        """copy_file"""
        source = cmd_data.get("source")
        destination = cmd_data.get("destination")
        if source and destination:
            try:
                shutil.copy2(source, destination)
                context.say("系统", f"✅ 已复制文件：{source} → {destination}")
            except Exception as e:
                context.say("系统", f"❌ 复制失败：{str(e)}")
        else:
            context.say("系统", "请指定源路径和目标路径。")
    registry.register_handler("copy_file", cmd_copy_file, "copy_file")

    def cmd_create_folder(context, cmd_data):
        """create_folder"""
        folder_path = cmd_data.get("folder_path")
        if folder_path:
            try:
                os.makedirs(folder_path, exist_ok=True)
                context.say("系统", f"✅ 已创建文件夹：{folder_path}")
            except Exception as e:
                context.say("系统", f"❌ 创建失败：{str(e)}")
        else:
            context.say("系统", "请指定文件夹路径。")
    registry.register_handler("create_folder", cmd_create_folder, "create_folder")

    def cmd_delete_folder(context, cmd_data):
        """delete_folder"""
        folder_path = cmd_data.get("folder_path")
        if folder_path:
            try:
                if os.path.exists(folder_path):
                    shutil.rmtree(folder_path)
                    context.say("系统", f"✅ 已删除文件夹：{folder_path}")
                else:
                    context.say("系统", f"❌ 文件夹不存在：{folder_path}")
            except Exception as e:
                context.say("系统", f"❌ 删除失败：{str(e)}")
        else:
            context.say("系统", "请指定文件夹路径。")
    registry.register_handler("delete_folder", cmd_delete_folder, "delete_folder")

    def cmd_read_file(context, cmd_data):
        """read_file"""
        file_path = cmd_data.get("file_path")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(500)
                context.say("系统", f"📄 文件内容：\n{content}")
            except Exception as e:
                context.say("系统", f"❌ 读取失败：{str(e)}")
        else:
            context.say("系统", "请指定文件路径。")
    registry.register_handler("read_file", cmd_read_file, "read_file")

    def cmd_write_file(context, cmd_data):
        """write_file"""
        file_path = cmd_data.get("file_path")
        content = cmd_data.get("content")
        if file_path and content:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                context.say("系统", f"✅ 已写入内容到：{file_path}")
            except Exception as e:
                context.say("系统", f"❌ 写入失败：{str(e)}")
        else:
            context.say("系统", "请指定文件路径和内容。")
    registry.register_handler("write_file", cmd_write_file, "write_file")

    def cmd_open_browser(context, cmd_data):
        """open_browser"""
        url = cmd_data.get("url", "https://www.baidu.com")
        try:
            webbrowser.open(url)
            context.say("系统", f"✅ 已打开浏览器：{url}")
        except Exception as e:
            context.say("系统", f"❌ 打开浏览器失败：{str(e)}")
    registry.register_handler("open_browser", cmd_open_browser, "open_browser")

    def cmd_close_browser(context, cmd_data):
        """close_browser"""
        try:
            os.system("taskkill /F /IM chrome.exe /IM msedge.exe /IM firefox.exe 2>nul")
            context.say("系统", "✅ 已关闭浏览器")
        except Exception as e:
            context.say("系统", f"❌ 关闭浏览器失败：{str(e)}")
    registry.register_handler("close_browser", cmd_close_browser, "close_browser")

    def cmd_navigate_url(context, cmd_data):
        """navigate_url"""
        url = cmd_data.get("url")
        if url:
            try:
                webbrowser.open(url)
                context.say("系统", f"✅ 已打开：{url}")
            except Exception as e:
                context.say("系统", f"❌ 打开失败：{str(e)}")
        else:
            context.say("系统", "请指定网址。")
    registry.register_handler("navigate_url", cmd_navigate_url, "navigate_url")

    def cmd_refresh_page(context, cmd_data):
        """refresh_page"""
        pyautogui.press('f5')
        context.say("系统", "✅ 已刷新页面")
    registry.register_handler("refresh_page", cmd_refresh_page, "refresh_page")

    def cmd_go_back(context, cmd_data):
        """go_back"""
        pyautogui.press('backspace')
        context.say("系统", "✅ 已后退")
    registry.register_handler("go_back", cmd_go_back, "go_back")

    def cmd_go_forward(context, cmd_data):
        """go_forward"""
        pyautogui.hotkey('alt', 'right')
        context.say("系统", "✅ 已前进")
    registry.register_handler("go_forward", cmd_go_forward, "go_forward")

    def cmd_get_cpu_usage(context, cmd_data):
        """get_cpu_usage"""
        try:
            cpu = psutil.cpu_percent(interval=1)
            context.say("系统", f"💻 CPU使用率：{cpu}%")
        except Exception as e:
            context.say("系统", f"❌ 获取失败：{str(e)}")
    registry.register_handler("get_cpu_usage", cmd_get_cpu_usage, "get_cpu_usage")

    def cmd_get_memory_usage(context, cmd_data):
        """get_memory_usage"""
        try:
            mem = psutil.virtual_memory()
            context.say("系统", f"💾 内存使用率：{mem.percent}% (已用：{mem.used/1024/1024/1024:.1f}GB/总计：{mem.total/1024/1024/1024:.1f}GB)")
        except Exception as e:
            context.say("系统", f"❌ 获取失败：{str(e)}")
    registry.register_handler("get_memory_usage", cmd_get_memory_usage, "get_memory_usage")

    def cmd_get_disk_usage(context, cmd_data):
        """get_disk_usage"""
        drive = cmd_data.get("drive", "C")
        try:
            disk = psutil.disk_usage(f"{drive}:/")
            context.say("系统", f"💽 {drive}盘使用率：{disk.percent}% (已用：{disk.used/1024/1024/1024:.1f}GB/总计：{disk.total/1024/1024/1024:.1f}GB)")
        except Exception as e:
            context.say("系统", f"❌ 获取失败：{str(e)}")
    registry.register_handler("get_disk_usage", cmd_get_disk_usage, "get_disk_usage")

    def cmd_get_battery(context, cmd_data):
        """get_battery"""
        try:
            battery = psutil.sensors_battery()
            if battery:
                context.say("系统", f"🔋 电池：{battery.percent}% {'正在充电' if battery.power_plugged else '使用电池中'}")
            else:
                context.say("系统", "❌ 无法获取电池信息（台式机或电池驱动异常）")
        except Exception as e:
            context.say("系统", f"❌ 获取失败：{str(e)}")
    registry.register_handler("get_battery", cmd_get_battery, "get_battery")

    def cmd_type_text(context, cmd_data):
        """type_text"""
        text = cmd_data.get("text")
        if text:
            pyautogui.write(text)
            context.say("系统", f"✅ 已输入文本：{text[:20]}...")
        else:
            context.say("系统", "请指定要输入的文本。")
    registry.register_handler("type_text", cmd_type_text, "type_text")

    def cmd_press_key(context, cmd_data):
        """press_key"""
        key = cmd_data.get("key")
        if key:
            pyautogui.press(key)
            context.say("系统", f"✅ 已按键：{key}")
        else:
            context.say("系统", "请指定按键。")
    registry.register_handler("press_key", cmd_press_key, "press_key")

    def cmd_move_mouse(context, cmd_data):
        """move_mouse"""
        x = cmd_data.get("x")
        y = cmd_data.get("y")
        if x is not None and y is not None:
            pyautogui.moveTo(x, y)
            context.say("系统", f"✅ 已移动鼠标到 ({x}, {y})")
        else:
            context.say("系统", "请指定坐标。")
    registry.register_handler("move_mouse", cmd_move_mouse, "move_mouse")

    def cmd_click_mouse(context, cmd_data):
        """click_mouse"""
        button = cmd_data.get("button", "left")
        pyautogui.click(button=button)
        context.say("系统", f"✅ 已点击鼠标{button}键")
    registry.register_handler("click_mouse", cmd_click_mouse, "click_mouse")

    def cmd_scroll(context, cmd_data):
        """scroll"""
        amount = cmd_data.get("amount", 3)
        pyautogui.scroll(amount)
        context.say("系统", f"✅ 已滚动 {amount} 格")
    registry.register_handler("scroll", cmd_scroll, "scroll")

    def cmd_play_media(context, cmd_data):
        """play_media"""
        pyautogui.press("playpause")
        context.say("系统", "▶ 已播放媒体")
    registry.register_handler("play_media", cmd_play_media, "play_media")

    def cmd_pause_media(context, cmd_data):
        """pause_media"""
        pyautogui.press("playpause")
        context.say("系统", "⏸ 已暂停媒体")
    registry.register_handler("pause_media", cmd_pause_media, "pause_media")

    def cmd_next_track(context, cmd_data):
        """next_track"""
        pyautogui.press("nexttrack")
        context.say("系统", "⏭ 已切换到下一曲")
    registry.register_handler("next_track", cmd_next_track, "next_track")

    def cmd_prev_track(context, cmd_data):
        """prev_track"""
        pyautogui.press("prevtrack")
        context.say("系统", "⏮ 已切换到上一曲")
    registry.register_handler("prev_track", cmd_prev_track, "prev_track")

    def cmd_open_settings(context, cmd_data):
        """open_settings"""
        os.system("start ms-settings:")
        context.say("系统", "✅ 已打开系统设置")
    registry.register_handler("open_settings", cmd_open_settings, "open_settings")

    def cmd_open_control_panel(context, cmd_data):
        """open_control_panel"""
        os.system("control panel")
        context.say("系统", "✅ 已打开控制面板")
    registry.register_handler("open_control_panel", cmd_open_control_panel, "open_control_panel")

    def cmd_open_task_manager(context, cmd_data):
        """open_task_manager"""
        os.system("taskmgr")
        context.say("系统", "✅ 已打开任务管理器")
    registry.register_handler("open_task_manager", cmd_open_task_manager, "open_task_manager")

    def cmd_open_cmd(context, cmd_data):
        """open_cmd"""
        os.system("start cmd")
        context.say("系统", "✅ 已打开命令提示符")
    registry.register_handler("open_cmd", cmd_open_cmd, "open_cmd")

    def cmd_open_powershell(context, cmd_data):
        """open_powershell"""
        os.system("start powershell")
        context.say("系统", "✅ 已打开PowerShell")
    registry.register_handler("open_powershell", cmd_open_powershell, "open_powershell")

    def cmd_get_current_time(context, cmd_data):
        """get_current_time"""
        now = datetime.now().strftime("%H:%M:%S")
        context.say("系统", f"🕐 当前时间：{now}")
    registry.register_handler("get_current_time", cmd_get_current_time, "get_current_time")

    def cmd_get_current_date(context, cmd_data):
        """get_current_date"""
        today = datetime.now().strftime("%Y年%m月%d日 %A")
        context.say("系统", f"📅 今天是：{today}")
    registry.register_handler("get_current_date", cmd_get_current_date, "get_current_date")

    def cmd_ping_host(context, cmd_data):
        """ping_host"""
        host = cmd_data.get("host", "baidu.com")
        try:
            result = os.popen(f"ping -n 1 {host}").read()
            if "TTL" in result:
                context.say("系统", f"✅ {host} 连接成功")
            else:
                context.say("系统", f"❌ {host} 连接失败")
        except Exception as e:
            context.say("系统", f"❌ Ping失败：{str(e)}")
    registry.register_handler("ping_host", cmd_ping_host, "ping_host")

    def cmd_get_ip_address(context, cmd_data):
        """get_ip_address"""
        try:
            import socket
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            context.say("系统", f"🌐 本机IP地址：{ip}")
        except Exception as e:
            context.say("系统", f"❌ 获取失败：{str(e)}")
    registry.register_handler("get_ip_address", cmd_get_ip_address, "get_ip_address")

    def cmd_disconnect_network(context, cmd_data):
        """disconnect_network"""
        os.system("netsh interface set interface \"以太网\" disable")
        context.say("系统", "⚠️ 已断开网络连接")
    registry.register_handler("disconnect_network", cmd_disconnect_network, "disconnect_network")

    def cmd_empty_recycle_bin(context, cmd_data):
        """empty_recycle_bin"""
        try:
            import winshell
            winshell.empty_recycle_bin(flags=0x00000000 | 0x00000040)
            context.say("系统", "✅ 回收站已清空")
        except:
            os.system("rd /s /q C:\\$Recycle.Bin")
            context.say("系统", "✅ 尝试清空回收站")
    registry.register_handler("empty_recycle_bin", cmd_empty_recycle_bin, "empty_recycle_bin")

    def cmd_show_desktop(context, cmd_data):
        """show_desktop"""
        pyautogui.hotkey("win", "d")
        context.say("系统", "✅ 已显示桌面")
    registry.register_handler("show_desktop", cmd_show_desktop, "show_desktop")

    def cmd_show_start_menu(context, cmd_data):
        """show_start_menu"""
        pyautogui.press("win")
        context.say("系统", "✅ 已显示开始菜单")
    registry.register_handler("show_start_menu", cmd_show_start_menu, "show_start_menu")

    def cmd_switch_user(context, cmd_data):
        """switch_user"""
        os.system("tsdiscon")
        context.say("系统", "✅ 已切换用户")
    registry.register_handler("switch_user", cmd_switch_user, "switch_user")

    def cmd_open_explorer(context, cmd_data):
        """open_explorer"""
        os.system("explorer")
        context.say("系统", "✅ 已打开文件资源管理器")
    registry.register_handler("open_explorer", cmd_open_explorer, "open_explorer")

    def cmd_open_notepad(context, cmd_data):
        """open_notepad"""
        os.system("notepad")
        context.say("系统", "✅ 已打开记事本")
    registry.register_handler("open_notepad", cmd_open_notepad, "open_notepad")

    def cmd_open_calculator(context, cmd_data):
        """open_calculator"""
        os.system("calc")
        context.say("系统", "✅ 已打开计算器")
    registry.register_handler("open_calculator", cmd_open_calculator, "open_calculator")

    def cmd_open_camera(context, cmd_data):
        """open_camera"""
        try:
            os.system("start microsoft.windows.camera:")
            context.say("系统", "✅ 已打开相机")
        except Exception as e:
            context.say("系统", f"❌ 打开相机失败：{str(e)}")
    registry.register_handler("open_camera", cmd_open_camera, "open_camera")

    def cmd_take_photo(context, cmd_data):
        """take_photo"""
        save_path = cmd_data.get("save_path")
        if not save_path:
            save_path = f"C:/Users/{os.getenv('USERNAME', 'Administrator')}/Desktop/photo.jpg"
        try:
            subprocess.run(["powershell", "-Command", f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::PrimaryScreen; Start-Process microsoft.windows.camera:"])
            context.say("系统", f"📷 请在相机应用中拍照，保存路径：{save_path}")
        except Exception as e:
            context.say("系统", f"❌ 打开相机失败：{str(e)}")
    registry.register_handler("take_photo", cmd_take_photo, "take_photo")

    def cmd_record_screen(context, cmd_data):
        """record_screen"""
        duration = cmd_data.get("duration", 10)
        save_path = cmd_data.get("save_path")
        if not save_path:
            save_path = str(Path.home() / f"Desktop/rec_{int(time.time())}.mp4")
        context.say("系统", f"🎥 开始录屏 {duration} 秒...")
        if hasattr(self, '_recording_writer') and context._recording_writer:
            context.say("系统", "已在录屏中，先停止之前的")
            context._recording_writer.release()
            context._recording_writer = None
        import cv2, numpy as np
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        screen = ImageGrab.grab()
        w, h = screen.size
        writer = cv2.VideoWriter(save_path, fourcc, 10.0, (w, h))
        context._recording_writer = writer
        def do_record():
            start = time.time()
            while time.time() - start < duration:
                frame = cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_RGB2BGR)
                writer.write(frame)
            writer.release()
            context._recording_writer = None
            context.root.after(0, lambda: context.say("系统", f"录屏完成，已保存：{save_path}"))
        threading.Thread(target=do_record, daemon=True).start()
    registry.register_handler("record_screen", cmd_record_screen, "record_screen")

    def cmd_stop_recording(context, cmd_data):
        """stop_recording"""
        if hasattr(self, '_recording_writer') and context._recording_writer:
            context._recording_writer.release()
            context._recording_writer = None
            context.say("系统", "已停止录屏")
        else:
            context.say("系统", "当前没有在录屏")
    registry.register_handler("stop_recording", cmd_stop_recording, "stop_recording")

    def cmd_get_weather(context, cmd_data):
        """get_weather"""
        city = cmd_data.get("city", "北京")
        try:
            import urllib.request, json
            url = f"https://wttr.in/{__import__('urllib.parse', fromlist=['quote']).quote(city)}?format=j1"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            current = data["current_condition"][0]
            temp = current["temp_C"]
            desc = current["weatherDesc"][0]["value"]
            wind = current["windspeedKmph"]
            hum = current["humidity"]
            context.say("系统", f"天气 {city}: {temp}C, {desc}, 风速 {wind}km/h, 湿度 {hum}%")
        except Exception as e:
            context.say("系统", f"天气查询失败: {str(e)}，请检查网络")
    registry.register_handler("get_weather", cmd_get_weather, "get_weather")

    def cmd_set_alarm(context, cmd_data):
        """set_alarm"""
        alarm_time = cmd_data.get("time")
        message = cmd_data.get("message", "闹钟提醒")
        if alarm_time:
            try:
                from datetime import datetime, timedelta
                alarm_dt = datetime.strptime(alarm_time, "%H:%M")
                now = datetime.now()
                alarm_dt = alarm_dt.replace(year=now.year, month=now.month, day=now.day)
                if alarm_dt <= now:
                    alarm_dt += timedelta(days=1)
                delay_s = (alarm_dt - now).total_seconds()
                context.say("系统", f"已设置闹钟: {alarm_time}, {int(delay_s)}秒后响铃")
                def ring_alarm():
                    try:
                        import pyttsx3
                        engine = pyttsx3.init()
                        engine.say(message)
                        engine.runAndWait()
                    except:
                        import winsound
                        winsound.Beep(1000, 2000)
                threading.Timer(delay_s, ring_alarm).start()
            except Exception as e:
                context.say("系统", f"闹钟设置失败: {str(e)}")
        else:
            context.say("系统", "请指定闹钟时间。")
    registry.register_handler("set_alarm", cmd_set_alarm, "set_alarm")

    # system_operation — 关键字分发到具体 handler (关机/重启/注销等)
    _SYS_OP_MAP = {
        "关机": "shutdown", "重启": "restart", "注销": "logout",
        "锁屏": "lock", "锁屏": "lock", "休眠": "hibernate",
        "睡眠": "sleep", "取消关机": "cancel_shutdown",
        "定时关机": "timer_shutdown", "定时重启": "timer_restart",
    }
    def cmd_system_operation(context, cmd_data):
        """分发系统操作到具体命令"""
        op = cmd_data.get("operation", "").lower()
        for kw, action in _SYS_OP_MAP.items():
            if kw in op:
                return registry.execute(action, context, cmd_data)
        context.say("系统", f"未知系统操作: {op}")
    registry.register_handler("system_operation", cmd_system_operation, "系统操作(关机/重启/注销等)")
