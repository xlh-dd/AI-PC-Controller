import time
import random
import hashlib
import re
import os
import subprocess
import logging
import traceback

logger = logging.getLogger("WeChatController")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None
    logger.warning("pyautogui未安装，微信控制功能受限")

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False
    pyperclip = None
    logger.warning("pyperclip未安装，剪贴板功能受限")

try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False
    gw = None
    logger.warning("pygetwindow未安装，窗口管理功能受限")

OCR_AVAILABLE = False
TESSERACT_CMD = None
TESSDATA_DIR = None

try:
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract
    
    common_paths = [
        r"D:\AI\tesseract\tesseract.exe",
        r"D:\AI\tessdata",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tesseract.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Tesseract-OCR", "tesseract.exe"),
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            TESSERACT_CMD = path
            
            tesseract_dir = os.path.dirname(path)
            possible_tessdata = [
                os.path.join(tesseract_dir, "tessdata"),
                os.path.join(tesseract_dir, "..", "tessdata"),
                r"D:\AI\tesseract\tessdata",
                r"D:\AI\tessdata",
            ]
            
            for td in possible_tessdata:
                if os.path.exists(td):
                    TESSDATA_DIR = td
                    os.environ["TESSDATA_PREFIX"] = td + os.sep
                    logger.info(f"tessdata 目录: {td}")
                    break
            
            try:
                result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    OCR_AVAILABLE = True
                    logger.info(f"Tesseract OCR 已找到: {path}")
                    logger.info(f"版本: {result.stdout.split()[1] if result.stdout else 'unknown'}")
                    break
            except Exception as e:
                logger.warning(f"检测 Tesseract 失败: {e}")
    
    if not OCR_AVAILABLE:
        logger.warning("未找到 Tesseract OCR，OCR功能已禁用")
        logger.warning("请从 https://github.com/UB-Mannheim/tesseract/wiki 下载安装")
        
except ImportError as e:
    logger.warning(f"OCR库未安装 - {e}")
    logger.warning("请运行: pip install pytesseract Pillow")

# PaddleOCR 初始化（优先于 Tesseract）
PADDLEOCR_AVAILABLE = False
_paddle_ocr_engine = None

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
    logger.info("PaddleOCR 可用，将作为首选 OCR 方案")
except ImportError:
    logger.info("PaddleOCR 未安装，使用 Tesseract/剪贴板方案")
except Exception as e:
    logger.warning(f"PaddleOCR 初始化异常: {e}")


def _get_paddle_ocr():
    """懒加载 PaddleOCR 引擎"""
    global _paddle_ocr_engine
    if _paddle_ocr_engine is None and PADDLEOCR_AVAILABLE:
        try:
            _paddle_ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            logger.info("PaddleOCR 引擎初始化成功")
        except Exception as e:
            logger.warning(f"PaddleOCR 引擎初始化失败: {e}")
    return _paddle_ocr_engine


class WeChatController:
    """微信控制模块"""

    def __init__(self, contact="文件传输助手", check_interval=10, use_ocr=True, debug_mode=False, callback=None, root=None):
        self.contact = contact
        self.check_interval = check_interval
        self.last_message_id = ""
        self.fail_count = 0
        self.enter_fail_count = 0
        self.max_fail = 5
        self.listener_running = False
        self.listener_thread = None
        self.use_ocr = use_ocr and OCR_AVAILABLE
        self.debug_mode = debug_mode
        self.last_screenshot_path = None
        self.last_error = ""
        self.message_cache = {}
        self.callback = callback
        self.root = root
        self.last_msg_pos = None
        self.search_pos = None
        self.ocr_region = None
        self.tesseract_cmd = None

        # 检查依赖
        if not PYAUTOGUI_AVAILABLE:
            logger.error("pyautogui未安装，微信控制功能不可用")
            raise ImportError("pyautogui未安装，请运行: pip install pyautogui")
        if not PYPERCLIP_AVAILABLE:
            logger.error("pyperclip未安装，剪贴板功能不可用")
            raise ImportError("pyperclip未安装，请运行: pip install pyperclip")
        if not PYGETWINDOW_AVAILABLE:
            logger.error("pygetwindow未安装，窗口管理功能不可用")
            raise ImportError("pygetwindow未安装，请运行: pip install pygetwindow")

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

        if self.use_ocr:
            logger.info("OCR模式已启用")
        else:
            logger.info("OCR模式已禁用，使用剪贴板方案")

    def set_callback(self, callback, root):
        """设置消息回调函数和root对象"""
        self.callback = callback
        self.root = root
        logger.info("消息回调已设置")

    def is_wechat_window_visible(self):
        """检查微信窗口是否可见（非最小化）"""
        try:
            if not PYGETWINDOW_AVAILABLE:
                self.last_error = "pygetwindow不可用"
                logger.warning("pygetwindow不可用，无法检查窗口")
                return False
            
            windows = gw.getWindowsWithTitle('微信')
            if not windows:
                windows = gw.getWindowsWithTitle('WeChat')
            if not windows:
                self.last_error = "未找到微信窗口"
                logger.warning("未找到微信窗口")
                return False
            
            # 检查是否有可见窗口（非最小化）
            visible_window_found = False
            for win in windows:
                try:
                    is_minimized = win.isMinimized
                    is_visible = not is_minimized and win.visible
                    
                    logger.info(f"微信窗口: {win.title}, 位置: ({win.left}, {win.top}), 大小: {win.width}x{win.height}, "
                               f"最小化={is_minimized}, 可见={is_visible}")
                    
                    if is_visible:
                        visible_window_found = True
                        
                except AttributeError:
                    # pygetwindow版本可能不支持这些属性
                    logger.info(f"微信窗口: {win.title}, 位置: ({win.left}, {win.top}), 大小: {win.width}x{win.height}")
                    visible_window_found = True
            
            if not visible_window_found:
                self.last_error = "微信窗口不可见（可能全部最小化）"
                logger.warning("微信窗口不可见（可能全部最小化）")
                return False
            
            return True
        except Exception as e:
            self.last_error = f"检查窗口失败: {str(e)}"
            logger.error(f"检查微信窗口失败: {e}")
            return False

    def activate_wechat_window(self, max_retries=2):
        """激活微信窗口，支持最小化恢复
        
        Args:
            max_retries: 最大重试次数
            
        Returns:
            (win, was_minimized, was_active) 或 None
        """
        for retry in range(max_retries):
            try:
                windows = gw.getWindowsWithTitle('微信')
                if not windows:
                    windows = gw.getWindowsWithTitle('WeChat')
                if not windows:
                    logger.warning(f"未找到微信窗口 (重试 {retry+1}/{max_retries})")
                    if retry < max_retries - 1:
                        time.sleep(0.5)
                        continue
                    return None
                
                win = windows[0]
                was_minimized = False
                was_maximized = False
                was_active = False
                
                # 检查窗口状态
                try:
                    was_minimized = win.isMinimized
                    was_maximized = win.isMaximized
                    was_active = win.isActive
                except AttributeError:
                    # pygetwindow版本可能不支持这些属性
                    was_minimized = False
                    was_maximized = False
                    was_active = False
                
                logger.info(f"微信窗口状态: 最小化={was_minimized}, 最大化={was_maximized}, 激活={was_active}")
                
                # 恢复最小化窗口
                if was_minimized:
                    logger.info("恢复最小化的微信窗口")
                    win.restore()
                    # 等待窗口完全恢复
                    time.sleep(0.3)
                    
                    # 再次检查是否仍然最小化
                    try:
                        if win.isMinimized:
                            logger.warning("窗口恢复失败，尝试强制激活")
                            win.minimize()  # 先最小化
                            time.sleep(0.2)
                            win.restore()   # 再恢复
                    except AttributeError:
                        pass
                
                # 激活窗口
                win.activate()
                time.sleep(0.3)
                
                # 确保窗口在前台
                try:
                    if not win.isActive:
                        logger.info("窗口未激活，再次尝试激活")
                        win.activate()
                        time.sleep(0.2)
                except AttributeError:
                    pass
                
                # 额外等待窗口完全就绪
                time.sleep(0.5)
                
                logger.info(f"微信窗口激活成功 (重试 {retry+1}/{max_retries})")
                return win, was_minimized, was_active
                
            except Exception as e:
                logger.warning(f"激活微信窗口失败 (重试 {retry+1}/{max_retries}): {e}")
                if retry < max_retries - 1:
                    time.sleep(0.5)
                    continue
        
        logger.error(f"激活微信窗口失败，已达到最大重试次数 {max_retries}")
        return None

    def enter_wechat_chat_by_click(self, win, contact):
        """通过点击搜索框进入聊天窗口"""
        try:
            if self.search_pos:
                rx, ry = self.search_pos
                search_x = win.left + int(win.width * rx)
                search_y = win.top + int(win.height * ry)
            else:
                search_x = win.left + 150
                search_y = win.top + 40

            pyautogui.click(search_x, search_y)
            time.sleep(1.0)

            pyperclip.copy(contact)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1.5)

            pyautogui.press('enter')
            time.sleep(2.0)
            return True
        except Exception as e:
            logger.warning(f"点击搜索框失败：{e}")
            return False

    def _preprocess_image(self, image):
        """图像预处理，提高OCR识别率"""
        try:
            gray = image.convert('L')
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(2.0)
            sharpened = enhanced.filter(ImageFilter.SHARPEN)
            return sharpened
        except Exception as e:
            logger.warning(f"图像预处理失败: {e}")
            return image

    def _save_debug_screenshot(self, image, prefix="wechat"):
        """保存调试截图"""
        if not self.debug_mode:
            return
        try:
            debug_dir = os.path.join(os.path.expanduser("~"), "wechat_debug")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.png"
            filepath = os.path.join(debug_dir, filename)
            image.save(filepath)
            self.last_screenshot_path = filepath
            logger.info(f"调试截图已保存: {filepath}")
        except Exception as e:
            logger.warning(f"保存截图失败: {e}")

    def get_last_message(self, win):
        """获取当前聊天窗口的最后一条消息（PaddleOCR优先 -> Tesseract -> 剪贴板）"""
        # 优先 PaddleOCR
        if PADDLEOCR_AVAILABLE:
            result = self._get_last_message_by_paddle(win)
            if result:
                return result
            logger.info("PaddleOCR 失败，尝试 Tesseract")
        # 其次 Tesseract
        if self.use_ocr:
            result = self._get_last_message_by_ocr(win)
            if result:
                return result
            logger.info("OCR方案失败，尝试剪贴板方案")
        return self._get_last_message_by_clipboard(win)

    def _get_last_message_by_paddle(self, win):
        """PaddleOCR 方案获取消息（首选，中文识别率远高于 Tesseract）"""
        try:
            ocr_engine = _get_paddle_ocr()
            if ocr_engine is None:
                return None

            win.activate()
            time.sleep(0.5)
            pyautogui.hotkey('ctrl', 'end')
            time.sleep(0.5)
            for _ in range(3):
                pyautogui.press('end')
                time.sleep(0.2)

            if self.ocr_region:
                rel_left, rel_top, rel_width, rel_height = self.ocr_region
                chat_left = win.left + int(win.width * rel_left)
                chat_top = win.top + int(win.height * rel_top)
                chat_width = int(win.width * rel_width)
                chat_height = int(win.height * rel_height)
            else:
                chat_left = win.left + int(win.width * 0.3)
                chat_top = win.top + int(win.height * 0.1)
                chat_width = int(win.width * 0.65)
                chat_height = int(win.height * 0.75)

            screenshot = pyautogui.screenshot(region=(chat_left, chat_top, chat_width, chat_height))
            self._save_debug_screenshot(screenshot, "paddle_original")

            import numpy as np
            img_array = np.array(screenshot)
            result = ocr_engine.ocr(img_array, cls=True)

            if not result or not result[0]:
                return None

            lines = []
            for line in result[0]:
                text = line[1][0].strip()
                if text:
                    lines.append(text)

            if not lines:
                return None

            full_text = '\n'.join(lines)
            logger.info(f"PaddleOCR 识别 {len(lines)} 行, 总长 {len(full_text)}")

            message = self._parse_message_from_lines(lines)
            if not message:
                return None

            msg_id = hashlib.md5(message.encode('utf-8')).hexdigest()
            return {"text": message, "id": msg_id}

        except Exception as e:
            logger.warning(f"PaddleOCR 获取消息失败: {e}")
            return None

    def _get_last_message_by_ocr(self, win):
        """OCR方案获取消息"""
        if not OCR_AVAILABLE:
            return None
            
        try:
            if self.tesseract_cmd and os.path.exists(self.tesseract_cmd):
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
                logger.info(f"使用配置的Tesseract: {self.tesseract_cmd}")
            
            win.activate()
            time.sleep(0.5)

            pyautogui.hotkey('ctrl', 'end')
            time.sleep(0.5)
            for _ in range(3):
                pyautogui.press('end')
                time.sleep(0.2)

            if self.ocr_region:
                rel_left, rel_top, rel_width, rel_height = self.ocr_region
                chat_left = win.left + int(win.width * rel_left)
                chat_top = win.top + int(win.height * rel_top)
                chat_width = int(win.width * rel_width)
                chat_height = int(win.height * rel_height)
            else:
                chat_left = win.left + int(win.width * 0.3)
                chat_top = win.top + int(win.height * 0.1)
                chat_width = int(win.width * 0.65)
                chat_height = int(win.height * 0.75)

            logger.info(f"截取区域: left={chat_left}, top={chat_top}, width={chat_width}, height={chat_height}")

            screenshot = pyautogui.screenshot(region=(chat_left, chat_top, chat_width, chat_height))
            self._save_debug_screenshot(screenshot, "original")

            processed = self._preprocess_image(screenshot)
            self._save_debug_screenshot(processed, "processed")

            try:
                text = pytesseract.image_to_string(processed, lang='chi_sim+eng', config='--psm 6')
            except Exception as e:
                logger.warning(f"中文识别失败，尝试英文: {e}")
                try:
                    text = pytesseract.image_to_string(processed, lang='eng', config='--psm 6')
                except Exception as e2:
                    logger.warning(f"英文识别也失败: {e2}")
                    return None

            full_text = text.strip()
            logger.info(f"OCR识别结果长度: {len(full_text)}")
            if self.debug_mode:
                logger.debug(f"OCR识别结果: {full_text}")

            if not full_text:
                return None

            lines = [line.strip() for line in full_text.splitlines() if line.strip()]
            if not lines:
                return None

            message = self._parse_message_from_lines(lines)
            if not message:
                return None

            msg_id = hashlib.md5(message.encode('utf-8')).hexdigest()
            return {"text": message, "id": msg_id}

        except Exception as e:
            logger.error(f"OCR获取消息失败：{e}")
            logger.error(traceback.format_exc())
            return None

    def _get_last_message_by_clipboard(self, win):
        """剪贴板方案获取消息 - 改进版，支持多种点击位置"""
        original_clipboard = pyperclip.paste()
        try:
            win.activate()
            time.sleep(0.5)

            pyautogui.hotkey('ctrl', 'end')
            time.sleep(0.5)
            for _ in range(3):
                pyautogui.press('end')
                time.sleep(0.2)

            window_width = win.width
            window_height = win.height
            window_left = win.left
            window_top = win.top
            
            # 记录窗口信息用于调试
            logger.info(f"剪贴板方案 - 窗口信息: 位置({window_left}, {window_top}), 尺寸({window_width}x{window_height})")

            positions = []
            if self.last_msg_pos:
                logger.info(f"使用用户校准的坐标: {self.last_msg_pos}")
                rx, ry = self.last_msg_pos
                
                # 判断坐标类型：比例坐标(0-1)还是绝对坐标
                if abs(rx) <= 1.0 and abs(ry) <= 1.0:
                    # 比例坐标：转换为绝对坐标
                    logger.info(f"坐标类型: 比例坐标")
                    user_x = int(window_left + window_width * rx)
                    user_y = int(window_top + window_height * ry)
                    logger.info(f"比例坐标转换为绝对坐标: ({rx}, {ry}) -> ({user_x}, {user_y})")
                else:
                    # 绝对坐标：直接使用，但确保在窗口内
                    logger.info(f"坐标类型: 绝对坐标")
                    user_x = int(rx)
                    user_y = int(ry)
                    # 检查坐标是否在窗口内
                    if not (window_left <= user_x <= window_left + window_width and 
                           window_top <= user_y <= window_top + window_height):
                        logger.warning(f"绝对坐标({user_x}, {user_y})不在窗口内，窗口区域: ({window_left}, {window_top}) - ({window_left+window_width}, {window_top+window_height})")
                
                positions = [
                    (user_x, user_y),
                    (user_x + 10, user_y),
                    (user_x - 10, user_y),
                    (user_x, user_y + 5),
                    (user_x, user_y - 5),
                    (user_x + 5, user_y + 5),
                    (user_x - 5, user_y - 5),
                ]
            else:
                logger.info("未找到用户校准的坐标，使用默认位置")
                positions = [
                    (window_left + int(window_width * 0.6), window_top + int(window_height * 0.88)),
                    (window_left + int(window_width * 0.7), window_top + int(window_height * 0.88)),
                    (window_left + int(window_width * 0.5), window_top + int(window_height * 0.85)),
                    (window_left + int(window_width * 0.6), window_top + int(window_height * 0.85)),
                    (window_left + int(window_width * 0.7), window_top + int(window_height * 0.85)),
                    (window_left + int(window_width * 0.8), window_top + int(window_height * 0.85)),
                    (window_left + int(window_width * 0.6), window_top + int(window_height * 0.80)),
                    (window_left + int(window_width * 0.7), window_top + int(window_height * 0.80)),
                    (window_left + int(window_width * 0.5), window_top + int(window_height * 0.88)),
                    (window_left + int(window_width * 0.8), window_top + int(window_height * 0.80)),
                    (window_left + window_width // 2, window_top + int(window_height * 0.85)),
                    (window_left + window_width // 2, window_top + int(window_height * 0.90)),
                ]

            full_text = ""
            successful_position = None
            
            # 记录所有尝试位置用于调试
            logger.info(f"剪贴板方案将尝试 {len(positions)} 个位置: {positions}")
            
            for idx, (msg_x, msg_y) in enumerate(positions):
                try:
                    logger.info(f"尝试第 {idx+1}/{len(positions)} 个位置: ({msg_x}, {msg_y})")
                    pyautogui.moveTo(msg_x, msg_y, duration=0.2)
                    time.sleep(0.2)
                    pyautogui.click(msg_x, msg_y)
                    time.sleep(0.3)
                    pyautogui.press('esc')
                    time.sleep(0.2)
                    pyautogui.hotkey('ctrl', 'a')
                    time.sleep(0.3)
                    pyautogui.hotkey('ctrl', 'c')
                    time.sleep(0.4)
                    full_text = pyperclip.paste().strip()
                    if full_text and len(full_text) > 2:
                        successful_position = (msg_x, msg_y)
                        logger.info(f"剪贴板方案第 {idx+1} 次成功，位置: ({msg_x}, {msg_y}), 内容长度: {len(full_text)}")
                        if self.debug_mode:
                            logger.debug(f"复制内容前300字符: {full_text[:300]}")
                        break
                    else:
                        logger.info(f"第 {idx+1} 次尝试内容为空或太短，内容长度: {len(full_text) if full_text else 0}")
                except Exception as e:
                    logger.info(f"第 {idx+1} 次尝试异常: {e}")
                    logger.debug(traceback.format_exc())

            if not full_text or len(full_text) <= 2:
                logger.warning("剪贴板方案无法获取有效消息内容")
                self.last_error = "无法从剪贴板获取消息内容"
                return None

            lines = full_text.splitlines()
            message = self._parse_message_from_lines(lines)
            if not message:
                logger.warning(f"无法从文本中解析消息，原始文本: {full_text[:200]}")
                self.last_error = f"消息解析失败，原始内容: {full_text[:100]}"
                return None

            msg_id = hashlib.md5(message.encode('utf-8')).hexdigest()
            logger.info(f"成功解析消息: {message[:50]}... ID: {msg_id[:8]}...")
            return {"text": message, "id": msg_id}
        except Exception as e:
            logger.error(f"剪贴板方案获取消息失败：{e}")
            self.last_error = f"获取消息异常: {str(e)}"
            logger.error(traceback.format_exc())
            return None
        finally:
            try:
                pyperclip.copy(original_clipboard)
            except:
                pass

    def _parse_message_from_lines(self, lines):
        """从多行文本中解析出最后一条消息 - 改进版，更宽松的解析"""
        if not lines:
            return None

        skip_patterns = [
            r'^\d{1,2}:\d{2}$',
            r'^\d{4}-\d{2}-\d{2}$',
            r'^昨天',
            r'^前天',
            r'^星期[一二三四五六日]',
            r'^\d{1,2}月\d{1,2}日',
            r'^文件传输助手$',
            r'^WeChat$',
            r'^\[.*\]$',
        ]

        valid_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            should_skip = False
            for pattern in skip_patterns:
                if re.match(pattern, line):
                    should_skip = True
                    break

            if should_skip:
                continue

            if len(line) < 2:
                continue

            if len(line) < 30 and line.isalpha() and not any('\u4e00' <= c <= '\u9fff' for c in line):
                logger.debug(f"跳过纯英文/短文本: {line}")
                continue

            if re.match(r'^[\d\s\-:,\.]+$', line):
                logger.debug(f"跳过纯数字符号行: {line}")
                continue

            if 'http://' in line or 'https://' in line:
                logger.debug(f"跳过链接行: {line}")
                continue

            valid_lines.append(line)

        if not valid_lines:
            logger.warning(f"所有行都被过滤，原始行数: {len(lines)}")
            if lines:
                return lines[-1].strip()
            return None

        message = valid_lines[-1]
        logger.debug(f"解析出消息: {message[:100]}")
        return message

    def send_wechat_message(self, target, message):
        """发送微信消息"""
        logger.info(f"正在发送微信消息给：{target}")

        result = self.activate_wechat_window()
        if not result:
            logger.warning("无法激活微信窗口，发送失败。")
            return False
        win, was_minimized, was_active = result

        try:
            if not self.enter_wechat_chat_by_click(win, target):
                logger.warning(f"无法进入与「{target}」的聊天窗口。")
                return False

            time.sleep(2)

            original_clipboard = pyperclip.paste()
            try:
                input_x = win.left + win.width // 2
                input_y = win.bottom - 80

                for _ in range(2):
                    pyautogui.click(input_x, input_y)
                    time.sleep(0.5)

                for _ in range(2):
                    pyautogui.hotkey('ctrl', 'a')
                    time.sleep(0.3)
                    pyautogui.press('backspace')
                    time.sleep(0.3)

                pyperclip.copy(message)
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(1)

                pyautogui.press('enter')
                time.sleep(1)

                logger.info("微信消息发送成功！")
                return True
            except Exception as e:
                logger.error(f"发送消息失败：{e}")
                return False
            finally:
                pyperclip.copy(original_clipboard)
        finally:
            if was_minimized:
                win.minimize()

    def _with_chat_context(self, func):
        """公共上下文管理器：激活窗口、进入聊天、执行函数、恢复窗口"""
        result = self.activate_wechat_window()
        if not result:
            return None
        win, was_minimized, was_active = result
        try:
            if not self.enter_wechat_chat_by_click(win, self.contact):
                return None
            time.sleep(2)
            return func(win)
        finally:
            if was_minimized:
                win.minimize()

    def _do_check_message(self, win):
        """检查消息的内部方法"""
        msg_data = self.get_last_message(win)
        if not msg_data:
            return None
        if msg_data["id"] == self.last_message_id:
            return None
        self.last_message_id = msg_data["id"]
        return msg_data

    def check_wechat_message(self):
        """检查微信消息"""
        logger.info(f"开始检查微信消息，联系人：{self.contact}")
        
        result = self.activate_wechat_window()
        if not result:
            self.fail_count += 1
            if self.fail_count >= self.max_fail:
                logger.warning("多次无法激活微信窗口，请检查微信是否正常运行。")
                self.fail_count = 0
            return None
        win, was_minimized, was_active = result
        self.fail_count = 0
        logger.info(f"微信窗口激活成功，当前last_message_id：{self.last_message_id}")

        try:
            if not self.enter_wechat_chat_by_click(win, self.contact):
                self.enter_fail_count += 1
                if self.enter_fail_count >= 3:
                    logger.warning(f"多次无法进入「{self.contact}」的聊天窗口，请检查联系人。")
                    self.enter_fail_count = 0
                return None
            self.enter_fail_count = 0
            logger.info(f"成功进入与「{self.contact}」的聊天窗口")

            time.sleep(2)
            msg_data = self.get_last_message(win)
            if not msg_data:
                logger.warning("获取消息失败，返回None")
                return None
            logger.info(f"获取消息成功：text={msg_data['text']}, id={msg_data['id']}")

            if msg_data["id"] == self.last_message_id:
                logger.info(f"消息重复，跳过处理：last_id={self.last_message_id}, current_id={msg_data['id']}")
                return None
            logger.info(f"消息不重复，更新last_message_id：{msg_data['id']}")
            self.last_message_id = msg_data["id"]

            if self.callback and self.root:
                msg_text = msg_data.get("text", "")
                if msg_text:
                    self.root.after(0, self.callback, msg_text)

            return msg_data
        finally:
            if was_minimized:
                win.minimize()
                logger.info("微信窗口已最小化")
            logger.info("检查微信消息结束")

    def set_contact(self, contact):
        """设置监听联系人"""
        self.contact = contact

    def set_check_interval(self, interval):
        """设置检查间隔"""
        self.check_interval = interval

    def set_debug_mode(self, enabled):
        """设置调试模式"""
        self.debug_mode = enabled
        logger.info(f"调试模式: {'开启' if enabled else '关闭'}")

    def set_use_ocr(self, enabled):
        """设置是否使用OCR"""
        self.use_ocr = enabled and OCR_AVAILABLE
        logger.info(f"OCR模式: {'开启' if self.use_ocr else '关闭'}")
        if enabled and not OCR_AVAILABLE:
            logger.warning("Tesseract OCR 未安装，无法启用OCR模式")

    def _do_update_id(self, win):
        """更新ID的内部方法"""
        msg_data = self.get_last_message(win)
        return msg_data["id"] if msg_data else None

    def get_diagnostic_info(self):
        """获取诊断信息"""
        info = {
            "ocr_available": OCR_AVAILABLE,
            "ocr_enabled": self.use_ocr,
            "last_error": self.last_error,
            "last_message_id": self.last_message_id[:16] + "..." if self.last_message_id else "未设置",
            "check_interval": self.check_interval,
            "contact": self.contact,
            "wechat_visible": self.is_wechat_window_visible(),
        }
        
        try:
            windows = gw.getWindowsWithTitle('微信')
            if not windows:
                windows = gw.getWindowsWithTitle('WeChat')
            if windows:
                win = windows[0]
                info["window_info"] = {
                    "title": win.title,
                    "position": f"({win.left}, {win.top})",
                    "size": f"{win.width}x{win.height}",
                    "minimized": win.isMinimized,
                    "active": win.isActive,
                }
        except Exception as e:
            info["window_error"] = str(e)
        
        return info
    
    def get_latest_messages(self, count=5):
        """获取最新的消息
        
        Args:
            count: 要获取的消息数量（由于UI限制，目前只返回最新的一条消息）
            
        Returns:
            消息列表，每个消息是包含text和id的字典
        """
        if not count or count <= 0:
            return []
        
        try:
            # 调用check_wechat_message获取最新消息
            msg_data = self.check_wechat_message()
            if msg_data:
                # 返回包含单条消息的列表（兼容现有接口）
                return [{
                    "text": msg_data.get("text", ""),
                    "content": msg_data.get("text", ""),  # 兼容social_skills的字段名
                    "id": msg_data.get("id", "")
                }]
            else:
                return []
        except Exception as e:
            logger.error(f"获取最新消息失败: {e}")
            return []
    
    def test_wechat_connection(self):
        """测试微信连接，返回诊断信息"""
        logger.info("开始测试微信连接...")
        result = {
            "success": False,
            "steps": [],
            "error": None
        }
        
        try:
            result["steps"].append("检查窗口...")
            if not self.is_wechat_window_visible():
                result["error"] = "未找到微信窗口，请确保微信已打开"
                logger.error(result["error"])
                return result
            result["steps"].append("✓ 找到微信窗口")
            
            result["steps"].append("激活窗口...")
            activate_result = self.activate_wechat_window()
            if not activate_result:
                result["error"] = "无法激活微信窗口"
                return result
            result["steps"].append("✓ 窗口激活成功")
            win, was_minimized, was_active = activate_result
            
            result["steps"].append("进入聊天...")
            if not self.enter_wechat_chat_by_click(win, self.contact):
                result["error"] = f"无法进入与「{self.contact}」的聊天窗口"
                return result
            result["steps"].append(f"✓ 进入「{self.contact}」聊天成功")
            
            result["steps"].append("获取消息...")
            time.sleep(2)
            msg_data = self.get_last_message(win)
            if not msg_data:
                result["error"] = self.last_error or "无法获取消息内容"
                return result
            result["steps"].append(f"✓ 获取消息成功: {msg_data['text'][:30]}...")
            result["success"] = True
            
            if was_minimized:
                win.minimize()
                
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"测试连接异常: {e}")
            
        return result

    def update_last_message_id(self, max_retries=3):
        """获取最新消息并更新 last_message_id，带重试机制"""
        for attempt in range(max_retries):
            result = self.activate_wechat_window()
            if not result:
                logger.warning(f"update_last_message_id: 激活窗口失败，尝试 {attempt+1}/{max_retries}")
                time.sleep(1)
                continue
            win, was_minimized, was_active = result
            try:
                if not self.enter_wechat_chat_by_click(win, self.contact):
                    logger.warning(f"update_last_message_id: 进入聊天失败，尝试 {attempt+1}/{max_retries}")
                    time.sleep(1)
                    continue
                time.sleep(2)
                msg_data = self.get_last_message(win)
                if msg_data:
                    self.last_message_id = msg_data["id"]
                    logger.info(f"update_last_message_id: 成功更新 ID 为 {msg_data['id'][:8]}...")
                    return True
                else:
                    logger.warning(f"update_last_message_id: 获取消息失败，尝试 {attempt+1}/{max_retries}")
            finally:
                if was_minimized:
                    win.minimize()
            time.sleep(1)
        logger.error(f"update_last_message_id: 重试 {max_retries} 次后仍失败")
        return False
