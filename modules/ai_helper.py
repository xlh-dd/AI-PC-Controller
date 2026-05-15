import json
import re
import logging

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

logger = logging.getLogger("AIHelper")

class AIHelper:
    """AI辅助模块"""

    def __init__(self, ollama_url="http://localhost:11434/api/generate", model="qwen2.5:1.5b", config_manager=None):
        self.ollama_url = ollama_url
        self.model = model
        self.use_ai_features = True
        self.cache = {}
        self.cache_size = 100
        self.config_manager = config_manager
        self._api_client = None
        # 立即初始化API客户端，确保服务商设置能生效
        if config_manager:
            self._get_api_client()

    def _get_api_client(self):
        """获取统一API客户端"""
        if self._api_client is None:
            from modules.unified_api_client import get_unified_client
            self._api_client = get_unified_client(self.config_manager)
        return self._api_client

    def _get_cache_key(self, method_name, *args, **kwargs):
        """生成缓存键"""
        key_parts = [method_name]
        for arg in args:
            key_parts.append(str(arg))
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return "|".join(key_parts)

    def _check_cache(self, method_name, *args, **kwargs):
        """检查缓存"""
        key = self._get_cache_key(method_name, *args, **kwargs)
        return self.cache.get(key)

    def _set_cache(self, method_name, result, *args, **kwargs):
        """设置缓存"""
        key = self._get_cache_key(method_name, *args, **kwargs)
        # 检查缓存大小
        if len(self.cache) >= self.cache_size:
            # 删除最旧的缓存项
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        self.cache[key] = result

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()

    def ai_query(self, prompt, system_prompt=None, stream_callback=None, stop_event=None, use_memory=True, timeout=60):
        """调用AI模型

        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            stream_callback: 流式响应回调函数
            stop_event: threading.Event对象，用于停止生成（可选）
            use_memory: 是否保存到对话记忆（默认True，指令解析时应为False）
            timeout: 超时时间（秒），默认60秒
        """
        if not self.use_ai_features:
            return None

        if not stream_callback:
            cached_result = self._check_cache("ai_query", prompt, system_prompt, self.model, stop_event)
            if cached_result is not None:
                logger.debug("使用缓存结果")
                return cached_result

        try:
            api_client = self._get_api_client()
            # 如果use_memory为False，使用原始方法（不保存到记忆）
            if hasattr(self, '_original_ai_query') and not use_memory:
                result = self._original_ai_query(prompt, system_prompt, stream_callback, self.model, stop_event)
            else:
                # 使用线程池实现超时控制
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(api_client.query, prompt, system_prompt, stream_callback, self.model, stop_event)
                    try:
                        result = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"AI查询超时（{timeout}秒）")
                        # 尝试取消任务
                        future.cancel()
                        return None

            if result and not stream_callback:
                self._set_cache("ai_query", result, prompt, system_prompt, self.model, stop_event)
            return result
        except Exception as e:
            logger.error(f"AI调用异常：{e}")

        return None

    def classify_file(self, filename, categories):
        """使用AI分类文件"""
        if not self.use_ai_features:
            return None

        # 检查缓存
        cached_result = self._check_cache("classify_file", filename, tuple(categories))
        if cached_result is not None:
            logger.debug("使用缓存结果")
            return cached_result

        prompt = f"请根据文件名判断它属于以下哪个类别（只返回类别名称）：\n类别列表：{', '.join(categories)}\n\n文件名：{filename}"
        resp = self.ai_query(prompt, use_memory=False)
        result = None
        if resp:
            for cat in categories:
                if cat in resp:
                    result = cat
                    break

        # 设置缓存
        self._set_cache("classify_file", result, filename, tuple(categories))
        return result

    def parse_command_with_clarification(self, msg):
        """解析用户指令，如果不确定则返回澄清问题

        返回: (result, clarification)
        - result: 解析结果dict，如果没有结果则为None
        - clarification: 澄清问题字符串，如果有不确定的地方
        """
        cached_result = self._check_cache("parse_command", msg)
        if cached_result is not None:
            return cached_result, None

        prompt = f"""你是一个指令解析专家。请分析用户指令并返回JSON格式的操作指令。

【支持的操作类型】（action字段）
1. open_app - 打开/启动/运行应用，参数: app_name
2. open_file - 打开指定文件，参数: file_path
3. open_folder - 打开指定文件夹，参数: folder_path
4. sort_files - 按类型整理文件
5. find_duplicates - 查找重复文件
6. find_large - 查找大文件
7. clean_empty - 清理空文件
8. rename_files - 批量重命名文件，参数: pattern(描述), prefix(前缀), start_num(起始编号), ext_filter(扩展名过滤)
9. shutdown - 关机，参数: delay(分钟)
10. restart - 重启，参数: delay(分钟)
11. logout - 注销
12. list_files - 列出文件
13. ai_chat - 闲聊对话
14. send_wechat - 发送微信消息，参数: target(联系人), message(内容)
15. schedule_wechat - 定时微信消息
16. schedule_task - 定时执行任务
17. start_listening - 开始监听微信
18. stop_listening - 停止监听微信
19. cancel_shutdown - 取消关机
20. sleep - 睡眠/待机
21. lock - 锁定屏幕
22. run_automation - 执行自动化任务
23. custom_command - 执行自定义命令

【重要：如果不确定，请设置clarification字段】
如果用户指令中缺少关键信息（如：发给谁？打开什么？具体时间？具体路径？），请设置clarification字段说明不确定的地方。

用户指令：{msg}

请返回以下JSON格式：
{{
    "action": "操作类型",
    "action_details": "操作详情描述",
    "参数1": "参数值",
    "参数2": "参数值",
    "clarification": "不确定的地方（如果有）"
}}

请直接返回JSON，不要其他文字。"""

        resp = self.ai_query(prompt, system_prompt="你是一个智能助手，负责解析用户指令。", use_memory=False)
        result = None
        clarification = None

        if resp:
            try:
                json_str = re.search(r'(\{.*\})', resp, re.DOTALL)
                if json_str:
                    data = json.loads(json_str.group(1))
                    # 检查是否有clarification字段
                    clarification = data.get("clarification", "")
                    if clarification:
                        # 移除clarification字段，因为它不是执行参数
                        data.pop("clarification", None)
                    result = data
            except Exception as e:
                logger.error(f"解析JSON失败: {e}")

        # 设置缓存（不缓存带clarification的结果）
        if result and not clarification:
            self._set_cache("parse_command", result, msg)

        return result, clarification

    def parse_command(self, msg):
        """解析用户指令 - 全面支持自然语言版本（兼容旧版本）"""
        cached_result = self._check_cache("parse_command", msg)
        if cached_result is not None:
            logger.debug("使用缓存结果")
            return cached_result

        prompt = f"""你是一个指令解析专家。请分析用户指令并返回JSON格式的操作指令。

【支持的操作类型】（action字段）
1. open_app - 打开/启动/运行应用，参数: app_name
2. open_file - 打开指定文件，参数: file_path
3. open_folder - 打开指定文件夹，参数: folder_path
4. sort_files - 按类型整理文件
5. find_duplicates - 查找重复文件
6. find_large - 查找大文件
7. clean_empty - 清理空文件
8. rename_files - 批量重命名文件，参数: pattern(描述，如"照片"、"文档"、"音乐"等), prefix(前缀，可选), start_num(起始编号，可选), ext_filter(扩展名过滤，如".jpg"、".mp3"等)
9. shutdown - 关机，参数: delay(分钟，可选，0或不填表示立即)
10. restart - 重启，参数: delay(分钟，可选)
11. logout - 注销
12. list_files - 列出文件，参数: path(路径，可选), filter(过滤条件，可选)
13. ai_chat - 闲聊对话
14. send_wechat - 发送微信消息，参数: target(联系人), message(内容)
15. schedule_wechat - 定时微信消息，参数: target, message, send_time(HH:MM格式)
16. schedule_task - 定时执行任务，参数: task(任务描述), send_time(HH:MM格式), schedule_type(daily/once/weekly/monthly)
17. start_listening - 开始监听微信
18. stop_listening - 停止监听微信
19. cancel_shutdown - 取消关机
20. sleep - 睡眠/待机
21. lock - 锁定屏幕
22. run_automation - 执行自动化任务，参数: task_name(任务名称，如"文件整理"、"批量重命名"等)
23. custom_command - 执行自定义命令/Shell命令，参数: command
24. ai_agent - 启动AI智能体执行复杂任务，参数: task(任务描述)
25. kill_process - 结束指定进程，参数: process_name(进程名称)或pid(进程ID)
26. minimize_window - 最小化窗口，参数: window_title(窗口标题)
27. maximize_window - 最大化窗口，参数: window_title(窗口标题)
28. close_window - 关闭窗口，参数: window_title(窗口标题)
29. activate_window - 激活窗口，参数: window_title(窗口标题)
30. volume_up - 增大音量，参数: steps(步数，默认5)
31. volume_down - 减小音量，参数: steps(步数，默认5)
32. set_volume - 设置音量，参数: level(0-100)
33. toggle_mute - 切换静音状态
34. take_screenshot - 截取屏幕，参数: save_path(保存路径，可选)
35. get_clipboard - 获取剪贴板内容
36. set_clipboard - 设置剪贴板内容，参数: content(内容)
37. get_system_info - 获取系统信息
38. hibernate - 休眠
39. turn_off_display - 关闭显示器
40. list_processes - 列出运行中的进程，参数: filter(过滤关键词，可选)
41. list_windows - 列出所有窗口，参数: filter(过滤关键词，可选)
42. get_network_info - 获取网络信息
43. toggle_wifi - 切换Wi-Fi状态，参数: enable(True开启/False关闭，可选)
44. speak_text - 语音合成/朗读文本，参数: text(要朗读的文本)
45. delete_file - 删除文件，参数: file_path(文件路径)
46. move_file - 移动文件，参数: source(源路径), destination(目标路径)
47. copy_file - 复制文件，参数: source(源路径), destination(目标路径)
48. create_folder - 创建文件夹，参数: folder_path(文件夹路径)
49. delete_folder - 删除文件夹，参数: folder_path(文件夹路径)
50. read_file - 读取文件内容，参数: file_path(文件路径)
51. write_file - 写入文件内容，参数: file_path(文件路径), content(内容)
52. open_browser - 打开浏览器，参数: url(网址，可选)
53. close_browser - 关闭浏览器
54. navigate_url - 导航到网址，参数: url(网址)
55. refresh_page - 刷新页面
56. go_back - 后退
57. go_forward - 前进
58. get_cpu_usage - 获取CPU使用率
59. get_memory_usage - 获取内存使用率
60. get_disk_usage - 获取磁盘使用情况，参数: drive(盘符，可选)
61. get_battery_status - 获取电池状态
62. type_text - 模拟输入文本，参数: text(文本内容)
63. press_key - 模拟按键，参数: key(按键名称，如ctrl、alt、enter等)
64. move_mouse - 移动鼠标，参数: x(x坐标), y(y坐标)
65. click_mouse - 模拟鼠标点击，参数: x(x坐标), y(y坐标), button(left/right，可选)
66. scroll - 滚动鼠标滚轮，参数: amount(滚动量，正数向上，负数向下)
67. play_media - 播放媒体(音乐/视频)
68. pause_media - 暂停媒体
69. next_track - 下一曲
70. prev_track - 上一曲
71. open_settings - 打开系统设置
72. open_control_panel - 打开控制面板
73. open_task_manager - 打开任务管理器
74. open_cmd - 打开命令提示符
75. open_powershell - 打开PowerShell
76. get_current_time - 获取当前时间
77. get_current_date - 获取当前日期
78. ping_host - Ping主机，参数: host(主机地址)
79. get_ip_address - 获取IP地址
80. disconnect_network - 断开网络连接
81. connect_network - 连接网络，参数: ssid(网络名称，可选)
82. empty_recycle_bin - 清空回收站
83. show_desktop - 显示桌面
84. show_start_menu - 显示开始菜单
85. switch_user - 切换用户
86. open_explorer - 打开文件资源管理器
87. open_notepad - 打开记事本
88. open_calculator - 打开计算器
89. open_camera - 打开相机
90. take_photo - 拍照保存，参数: save_path(保存路径，可选)
91. record_screen - 录屏，参数: duration(时长秒数，可选), save_path(保存路径，可选)
92. stop_recording - 停止录屏
93. get_weather - 获取天气，参数: city(城市名称)
94. set_alarm - 设置闹钟，参数: time(HH:MM格式), message(提醒内容，可选)

【特别说明】
- 对于系统控制命令（音量控制、网络控制、进程管理、窗口管理、屏幕截图、剪贴板操作、语音合成、OCR识别等），请使用 ai_agent 操作类型
- AI智能体会自动规划并执行相应的系统控制操作
- 其他简单命令（打开应用、文件操作、关机重启等）使用对应的操作类型

【自然语言理解示例】
- "打开D盘的音乐" → {{"action": "open_folder", "folder_path": "D:/音乐"}}
- "打开微信" → {{"action": "open_app", "app_name": "微信"}}
- "打开我的文档" → {{"action": "open_folder", "folder_path": "文档"}}
- "打开E:/workspace/project.py" → {{"action": "open_file", "file_path": "E:/workspace/project.py"}}
- "10分钟后关机" → {{"action": "shutdown", "delay": 10}}
- "1小时后重启" → {{"action": "restart", "delay": 60}}
- "30秒后睡眠" → {{"action": "sleep", "delay": 0.5}}
- "明天下午3点执行任务" → {{"action": "schedule_task", "task": "任务描述", "send_time": "15:00", "schedule_type": "once"}}
- "每天早上8点发消息" → {{"action": "schedule_wechat", "target": "xxx", "message": "xxx", "send_time": "08:00", "schedule_type": "daily"}}
- "给文件传输助手发消息:你好" → {{"action": "send_wechat", "target": "文件传输助手", "message": "你好"}}
- "批量重命名照片" → {{"action": "rename_files", "pattern": "照片", "prefix": "IMG_", "start_num": 1, "ext_filter": ".jpg"}}
- "把音乐文件按序号命名" → {{"action": "rename_files", "pattern": "音乐", "prefix": "music_", "start_num": 1, "ext_filter": ".mp3"}}
- "打开文件整理任务" → {{"action": "run_automation", "task_name": "文件整理"}}
- "结束Chrome进程" → {{"action": "kill_process", "process_name": "chrome"}}
- "关闭记事本窗口" → {{"action": "close_window", "window_title": "记事本"}}
- "最小化浏览器窗口" → {{"action": "minimize_window", "window_title": "浏览器"}}
- "最大化微信窗口" → {{"action": "maximize_window", "window_title": "微信"}}
- "激活钉钉窗口" → {{"action": "activate_window", "window_title": "钉钉"}}
- "增大音量" → {{"action": "volume_up", "steps": 5}}
- "减小音量3步" → {{"action": "volume_down", "steps": 3}}
- "设置音量为80" → {{"action": "set_volume", "level": 80}}
- "静音" → {{"action": "toggle_mute"}}
- "截取屏幕保存到桌面" → {{"action": "take_screenshot", "save_path": "C:/Users/Administrator/Desktop/screenshot.png"}}
- "查看剪贴板内容" → {{"action": "get_clipboard"}}
- "复制这段文字到剪贴板" → {{"action": "set_clipboard", "content": "这段文字"}}
- "查看系统信息" → {{"action": "get_system_info"}}
- "让电脑休眠" → {{"action": "hibernate"}}
- "关闭显示器" → {{"action": "turn_off_display"}}
- "查看运行中的进程" → {{"action": "list_processes"}}
- "查看所有窗口" → {{"action": "list_windows"}}
- "查看网络状态" → {{"action": "get_network_info"}}
- "关闭Wi-Fi" → {{"action": "toggle_wifi", "enable": false}}
- "朗读这段文字" → {{"action": "speak_text", "text": "这段文字"}}
- "删除D:/test.txt" → {{"action": "delete_file", "file_path": "D:/test.txt"}}
- "移动D:/a.txt到E:/b.txt" → {{"action": "move_file", "source": "D:/a.txt", "destination": "E:/b.txt"}}
- "复制D:/a.txt到E:/b.txt" → {{"action": "copy_file", "source": "D:/a.txt", "destination": "E:/b.txt"}}
- "创建文件夹D:/新建文件夹" → {{"action": "create_folder", "folder_path": "D:/新建文件夹"}}
- "删除D:/test文件夹" → {{"action": "delete_folder", "folder_path": "D:/test"}}
- "读取D:/readme.txt的内容" → {{"action": "read_file", "file_path": "D:/readme.txt"}}
- "写入内容到D:/test.txt" → {{"action": "write_file", "file_path": "D:/test.txt", "content": "要写入的内容"}}
- "打开浏览器访问百度" → {{"action": "open_browser", "url": "https://www.baidu.com"}}
- "关闭浏览器" → {{"action": "close_browser"}}
- "打开百度" → {{"action": "navigate_url", "url": "https://www.baidu.com"}}
- "刷新页面" → {{"action": "refresh_page"}}
- "后退" → {{"action": "go_back"}}
- "前进" → {{"action": "go_forward"}}
- "查看CPU使用率" → {{"action": "get_cpu_usage"}}
- "查看内存使用情况" → {{"action": "get_memory_usage"}}
- "查看D盘使用情况" → {{"action": "get_disk_usage", "drive": "D"}}
- "查看电池状态" → {{"action": "get_battery_status"}}
- "输入这段文字" → {{"action": "type_text", "text": "这段文字"}}
- "按回车键" → {{"action": "press_key", "key": "enter"}}
- "移动鼠标到100,200" → {{"action": "move_mouse", "x": 100, "y": 200}}
- "点击鼠标" → {{"action": "click_mouse"}}
- "向上滚动" → {{"action": "scroll", "amount": 3}}
- "播放音乐" → {{"action": "play_media"}}
- "暂停播放" → {{"action": "pause_media"}}
- "下一曲" → {{"action": "next_track"}}
- "上一曲" → {{"action": "prev_track"}}
- "打开系统设置" → {{"action": "open_settings"}}
- "打开控制面板" → {{"action": "open_control_panel"}}
- "打开任务管理器" → {{"action": "open_task_manager"}}
- "打开命令提示符" → {{"action": "open_cmd"}}
- "打开PowerShell" → {{"action": "open_powershell"}}
- "现在几点" → {{"action": "get_current_time"}}
- "今天是几号" → {{"action": "get_current_date"}}
- "Ping一下百度" → {{"action": "ping_host", "host": "baidu.com"}}
- "查看IP地址" → {{"action": "get_ip_address"}}
- "断开网络" → {{"action": "disconnect_network"}}
- "清空回收站" → {{"action": "empty_recycle_bin"}}
- "显示桌面" → {{"action": "show_desktop"}}
- "打开资源管理器" → {{"action": "open_explorer"}}
- "打开记事本" → {{"action": "open_notepad"}}
- "打开计算器" → {{"action": "open_calculator"}}
- "打开相机" → {{"action": "open_camera"}}
- "拍照保存到桌面" → {{"action": "take_photo", "save_path": "C:/Users/Administrator/Desktop/photo.jpg"}}
- "开始录屏10秒" → {{"action": "record_screen", "duration": 10}}
- "停止录屏" → {{"action": "stop_recording"}}
- "查看北京天气" → {{"action": "get_weather", "city": "北京"}}
- "设置早上7点的闹钟" → {{"action": "set_alarm", "time": "07:00", "message": "起床啦"}}

【关键理解规则】
1. 应用名要精确提取，如"微信"→"微信"，"记事本"→"记事本"
2. 文件/文件夹路径可以是相对路径或绝对路径
3. 延迟时间统一转换为分钟（小数如0.5表示30秒）
4. 联系人名称要完整提取
5. 重命名任务的pattern要理解用户意图：照片→.jpg/.png/.jpeg，文档→.doc/.docx/.pdf，音乐→.mp3/.wav/.flac，视频→.mp4/.avi/.mkv
6. 如果用户说的时间含"明天"、"后天"、"下周一"等，需要计算实际时间

用户指令：{msg}

请直接返回JSON，不要其他文字。"""
        resp = self.ai_query(prompt, system_prompt="你是一个智能助手，负责解析用户指令。", use_memory=False)
        result = None
        if resp:
            try:
                json_str = re.search(r'({.*})', resp, re.DOTALL)
                if json_str:
                    data = json.loads(json_str.group(1))
                    result = data
            except:
                pass

        # 设置缓存
        self._set_cache("parse_command", result, msg)
        return result

    def analyze_duplicate_files(self, files_info):
        """分析重复文件"""
        # 将文件信息转换为可哈希的元组，用于缓存键
        def files_info_to_hashable(files):
            return tuple(
                tuple(sorted(file.items()))
                for file in sorted(files, key=lambda x: x.get('path', ''))
            )

        # 检查缓存
        hashable_files = files_info_to_hashable(files_info)
        cached_result = self._check_cache("analyze_duplicate_files", hashable_files)
        if cached_result is not None:
            logger.debug("使用缓存结果")
            return cached_result

        prompt = f"""
以下是一组重复文件（MD5相同），请分析哪些文件可以安全删除（保留一个最佳版本）。
考虑因素：文件名是否合理、修改时间最新、路径是否在常见位置等。
返回要删除的文件路径列表（JSON格式）。

文件列表：
{json.dumps(files_info, indent=2, ensure_ascii=False)}

请只返回JSON，例如：["path1", "path2"]
"""
        resp = self.ai_query(prompt, use_memory=False)
        result = []
        if resp:
            try:
                json_str = re.search(r'(\[.*\])', resp, re.DOTALL)
                if json_str:
                    del_list = json.loads(json_str.group(1))
                    result = del_list
            except:
                pass

        # 设置缓存
        self._set_cache("analyze_duplicate_files", result, hashable_files)
        return result

    def generate_rename_plan(self, folders, msg):
        """生成文件改名计划"""
        # 检查缓存
        cached_result = self._check_cache("generate_rename_plan", tuple(folders), msg)
        if cached_result is not None:
            logger.debug("使用缓存结果")
            return cached_result

        prompt = f"""
当前文件夹列表：{folders}
用户要求：{msg}
请返回JSON格式的改名方案，示例：
{"rename_pairs": [{"original": "旧名1", "new": "新名1"}]}
"""
        resp = self.ai_query(prompt, use_memory=False)
        result = []
        if resp:
            try:
                data = json.loads(resp)
                result = data.get("rename_pairs", [])
            except json.JSONDecodeError:
                result = self.extract_rename_pairs_from_text(resp, folders)

        # 设置缓存
        self._set_cache("generate_rename_plan", result, tuple(folders), msg)
        return result

    def extract_rename_pairs_from_text(self, text, folders):
        """从文本中提取改名对"""
        pairs = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if '→' in line or '->' in line:
                if '→' in line:
                    old, new = line.split('→', 1)
                else:
                    old, new = line.split('->', 1)
                old = old.strip()
                new = new.strip()
                if old in folders and new:
                    pairs.append({"original": old, "new": new})
        return pairs

    def set_config(self, ollama_url=None, model=None, use_ai_features=None, provider_id=None):
        """设置AI配置"""
        if ollama_url:
            self.ollama_url = ollama_url
        if model:
            self.model = model
        if use_ai_features is not None:
            self.use_ai_features = use_ai_features
        if provider_id:
            # 确保API客户端已初始化
            if not self._api_client and self.config_manager:
                self._get_api_client()
            if self._api_client:
                self._api_client.switch_provider(provider_id)
            # 无论如何都设置当前服务商配置
            if self.config_manager:
                self.config_manager.set_current_provider(provider_id)

        self.clear_cache()
