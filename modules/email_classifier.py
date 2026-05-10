import logging
import json
import time
import re
import os
import imaplib
import email
import smtplib
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
import threading
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import decode_header

# 尝试导入可选依赖
try:
    import yagmail
    YAGMAIL_AVAILABLE = True
except ImportError:
    YAGMAIL_AVAILABLE = False
    logging.warning("yagmail模块未安装，邮件发送功能受限")

logger = logging.getLogger("EmailClassifier")

class EmailClassifier:
    """邮件分类与自动回复模块
    
    功能：
    1. 实时监控收件箱
    2. 根据邮件标题和内容自动分类
    3. 咨询类邮件：从知识库调取FAQ自动起草回复
    4. 投诉邮件：标记为高优先级，弹窗提醒
    5. 订阅新闻简报：自动归档到"阅读列表"文件夹
    """
    
    def __init__(self, config_manager=None, knowledge_base_builder=None, social_skills=None):
        self.config_manager = config_manager
        self.knowledge_base = knowledge_base_builder
        self.social_skills = social_skills
        
        self.monitoring_enabled = False
        self.monitoring_thread = None
        self.email_db = None
        
        # 邮件配置
        self.email_config = {}
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        
        # 分类规则
        self.classification_rules = {}
        self.faq_knowledge = {}
        self.auto_reply_templates = {}
        
        # 处理状态
        self.processed_emails = set()
        self.priority_emails = []
        
        self.load_config()
        self.init_database()
    
    def load_config(self):
        """加载配置"""
        config_dir = Path(__file__).parent.parent / "knowledge_base" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载邮件配置
        email_config_file = config_dir / "email_config.json"
        if email_config_file.exists():
            try:
                with open(email_config_file, 'r', encoding='utf-8') as f:
                    self.email_config = json.load(f)
                    
                self.imap_server = self.email_config.get("imap_server", "imap.gmail.com")
                self.imap_port = self.email_config.get("imap_port", 993)
                self.smtp_server = self.email_config.get("smtp_server", "smtp.gmail.com")
                self.smtp_port = self.email_config.get("smtp_port", 587)
                
                logger.info("邮件配置加载成功")
                
            except Exception as e:
                logger.error(f"加载邮件配置失败: {e}")
                self.set_default_config()
        else:
            self.set_default_config()
            self.save_config()
        
        # 加载分类规则
        rules_file = config_dir / "email_classification_rules.json"
        if rules_file.exists():
            try:
                with open(rules_file, 'r', encoding='utf-8') as f:
                    self.classification_rules = json.load(f)
            except Exception as e:
                logger.error(f"加载分类规则失败: {e}")
                self.set_default_classification_rules()
        else:
            self.set_default_classification_rules()
            self.save_classification_rules()
        
        # 加载FAQ知识
        faq_file = config_dir / "email_faq.json"
        if faq_file.exists():
            try:
                with open(faq_file, 'r', encoding='utf-8') as f:
                    self.faq_knowledge = json.load(f)
            except Exception as e:
                logger.error(f"加载FAQ知识失败: {e}")
        
        # 加载自动回复模板
        reply_templates_file = config_dir / "auto_reply_templates.json"
        if reply_templates_file.exists():
            try:
                with open(reply_templates_file, 'r', encoding='utf-8') as f:
                    self.auto_reply_templates = json.load(f)
            except Exception as e:
                logger.error(f"加载自动回复模板失败: {e}")
                self.set_default_auto_reply_templates()
        else:
            self.set_default_auto_reply_templates()
            self.save_auto_reply_templates()
    
    @staticmethod
    def _get_password(email_address):
        """安全获取密码：优先 keyring，回退到 config 明文"""
        try:
            import keyring
            pwd = keyring.get_password("AIPCHelper_Email", email_address)
            if pwd:
                return pwd
        except ImportError:
            pass
        return None

    @staticmethod
    def _set_password(email_address, password):
        """安全存储密码到 keyring"""
        try:
            import keyring
            keyring.set_password("AIPCHelper_Email", email_address, password)
            return True
        except ImportError:
            return False

    def _resolve_password(self):
        """获取当前配置邮箱的密码（keyring优先，config回退）"""
        email_address = self.email_config.get("email_address", "")
        # 1. 优先 keyring
        pwd = self._get_password(email_address)
        if pwd:
            return pwd
        # 2. 回退 config 明文
        plain = self.email_config.get("password", "")
        if plain:
            # 迁移：写入 keyring，清除明文
            self._set_password(email_address, plain)
            self.email_config["password"] = ""
            self.save_config()
            return plain
        return ""

    def set_default_config(self):
        """设置默认邮件配置"""
        self.email_config = {
            "email_address": "",
            "password": "",
            "imap_server": "imap.gmail.com",
            "imap_port": 993,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "check_interval": 300,  # 检查间隔（秒）
            "max_emails_per_check": 10,
            "auto_reply_enabled": True,
            "archive_subscriptions": True
        }
    
    def set_default_classification_rules(self):
        """设置默认分类规则"""
        self.classification_rules = {
            "consultation": {
                "keywords": ["咨询", "请问", "求助", "帮忙", "帮助", "问题", "疑问", "how", "help", "question"],
                "patterns": [r"如何.*", r"怎么.*", r"请问.*", r"求助.*"],
                "priority": "normal",
                "auto_reply": True,
                "folder": "INBOX"
            },
            "complaint": {
                "keywords": ["投诉", "抱怨", "不满", "愤怒", "生气", "差评", "投诉", "complain", "angry", "unhappy"],
                "patterns": [r"投诉.*", r"抱怨.*", r"太差.*", r"糟糕.*", r"不满意.*"],
                "priority": "high",
                "auto_reply": False,
                "folder": "INBOX",
                "alert": True
            },
            "subscription": {
                "keywords": ["新闻", "简报", "订阅", "newsletter", "订阅", "update", "news", "bullet"],
                "patterns": [r".*新闻.*", r".*简报.*", r".*newsletter.*", r"订阅.*"],
                "priority": "low",
                "auto_reply": False,
                "folder": "阅读列表",
                "archive": True
            },
            "urgent": {
                "keywords": ["紧急", "急", "urgent", "asap", "immediately", "critical", "important"],
                "patterns": [r"紧急.*", r"急.*", r"urgent.*", r"asap.*"],
                "priority": "high",
                "auto_reply": True,
                "folder": "INBOX",
                "alert": True
            },
            "spam": {
                "keywords": ["促销", "优惠", "打折", "广告", "推广", "sale", "promotion", "discount", "advertisement"],
                "patterns": [r".*促销.*", r".*优惠.*", r".*打折.*", r".*广告.*"],
                "priority": "low",
                "auto_reply": False,
                "folder": "垃圾邮件",
                "delete": True
            }
        }
    
    def set_default_auto_reply_templates(self):
        """设置默认自动回复模板"""
        self.auto_reply_templates = {
            "consultation_general": {
                "subject": "回复：{original_subject}",
                "body": """尊敬的{recipient_name}：

您好！

感谢您的咨询。我们已经收到您关于"{query_topic}"的问题。

根据我们的知识库，相关建议如下：
{faq_answer}

如果您需要进一步的帮助或有其他问题，请随时回复此邮件。

祝好！

{your_name}
{company_name}"""
            },
            "consultation_no_faq": {
                "subject": "回复：{original_subject}",
                "body": """尊敬的{recipient_name}：

您好！

感谢您的咨询。我们已经收到您关于"{query_topic}"的问题。

我们已经将您的问题记录并转交给相关部门。我们的团队将在24小时内给您详细的回复。

感谢您的耐心等待！

祝好！

{your_name}
{company_name}"""
            },
            "urgent_acknowledgment": {
                "subject": "已收到您的紧急邮件：{original_subject}",
                "body": """尊敬的{recipient_name}：

您好！

我们已经收到您的紧急邮件，并已将其标记为高优先级。

我们的团队将尽快处理您的问题，并在2小时内给您回复。

感谢您的理解！

祝好！

{your_name}
{company_name}"""
            }
        }
    
    def save_config(self):
        """保存配置（密码写入 keyring，不在 JSON 中保留明文）"""
        config_dir = Path(__file__).parent.parent / "knowledge_base" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # 密码迁移到 keyring
        email_address = self.email_config.get("email_address", "")
        plain_password = self.email_config.get("password", "")
        if plain_password and email_address:
            self._set_password(email_address, plain_password)
            self.email_config["password"] = ""  # 清除明文
        
        # 保存邮件配置
        email_config_file = config_dir / "email_config.json"
        try:
            with open(email_config_file, 'w', encoding='utf-8') as f:
                json.dump(self.email_config, f, ensure_ascii=False, indent=2)
            logger.info("邮件配置保存成功")
        except Exception as e:
            logger.error(f"保存邮件配置失败: {e}")
    
    def save_classification_rules(self):
        """保存分类规则"""
        config_dir = Path(__file__).parent.parent / "knowledge_base" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        rules_file = config_dir / "email_classification_rules.json"
        try:
            with open(rules_file, 'w', encoding='utf-8') as f:
                json.dump(self.classification_rules, f, ensure_ascii=False, indent=2)
            logger.info("分类规则保存成功")
        except Exception as e:
            logger.error(f"保存分类规则失败: {e}")
    
    def save_auto_reply_templates(self):
        """保存自动回复模板"""
        config_dir = Path(__file__).parent.parent / "knowledge_base" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        templates_file = config_dir / "auto_reply_templates.json"
        try:
            with open(templates_file, 'w', encoding='utf-8') as f:
                json.dump(self.auto_reply_templates, f, ensure_ascii=False, indent=2)
            logger.info("自动回复模板保存成功")
        except Exception as e:
            logger.error(f"保存自动回复模板失败: {e}")
    
    def init_database(self):
        """初始化邮件数据库"""
        data_dir = Path(__file__).parent.parent / "knowledge_base" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        db_path = data_dir / "email_classifier.db"
        self.email_db = sqlite3.connect(str(db_path))
        self.create_tables()
    
    def create_tables(self):
        """创建数据库表"""
        cursor = self.email_db.cursor()
        
        # 邮件记录表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT UNIQUE,
            sender_email TEXT,
            sender_name TEXT,
            recipient_email TEXT,
            subject TEXT,
            content TEXT,
            classification TEXT,
            priority TEXT,
            auto_replied BOOLEAN DEFAULT FALSE,
            reply_sent BOOLEAN DEFAULT FALSE,
            archived BOOLEAN DEFAULT FALSE,
            folder TEXT,
            received_at DATETIME,
            processed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # FAQ知识表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS faq_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            answer TEXT,
            category TEXT,
            tags TEXT,
            usage_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 邮件分类统计表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS classification_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            classification TEXT,
            count INTEGER DEFAULT 0,
            auto_replied INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        self.email_db.commit()
        
        # 初始化一些FAQ数据
        self.init_default_faq()
    
    def init_default_faq(self):
        """初始化默认FAQ数据"""
        cursor = self.email_db.cursor()
        
        # 检查是否已有数据
        cursor.execute("SELECT COUNT(*) FROM faq_knowledge")
        count = cursor.fetchone()[0]
        
        if count == 0:
            default_faqs = [
                {
                    "question": "如何重置密码？",
                    "answer": "您可以在登录页面点击'忘记密码'链接，按照提示操作即可重置密码。",
                    "category": "账户管理",
                    "tags": "密码,重置,账户"
                },
                {
                    "question": "产品价格是多少？",
                    "answer": "我们的产品有多个套餐，基础版每月99元，专业版每月199元，企业版需要定制报价。",
                    "category": "产品价格",
                    "tags": "价格,套餐,费用"
                },
                {
                    "question": "技术支持联系方式？",
                    "answer": "您可以通过以下方式联系技术支持：电话：400-123-4567，邮箱：support@company.com，工作时间：工作日9:00-18:00。",
                    "category": "技术支持",
                    "tags": "支持,联系,帮助"
                },
                {
                    "question": "如何取消订阅？",
                    "answer": "您可以在账户设置中找到'订阅管理'，点击'取消订阅'按钮即可。或者直接回复此邮件说明取消订阅。",
                    "category": "订阅管理",
                    "tags": "订阅,取消,退订"
                },
                {
                    "question": "发票如何申请？",
                    "answer": "请在购买后7个工作日内联系客服，提供订单号和开票信息，我们将为您开具发票。",
                    "category": "财务发票",
                    "tags": "发票,开票,财务"
                }
            ]
            
            for faq in default_faqs:
                cursor.execute('''
                INSERT INTO faq_knowledge (question, answer, category, tags)
                VALUES (?, ?, ?, ?)
                ''', (faq["question"], faq["answer"], faq["category"], faq["tags"]))
            
            self.email_db.commit()
            logger.info("已初始化默认FAQ数据")
    
    def start_monitoring(self):
        """开始监控收件箱"""
        # 检查监控状态
        if self.monitoring_enabled and self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.warning("邮件监控已在运行中")
            return False
        
        # 如果监控标志为True但线程已死，重置状态
        if self.monitoring_enabled and (not self.monitoring_thread or not self.monitoring_thread.is_alive()):
            logger.warning("监控线程已停止，重新启动监控")
            self.monitoring_enabled = False
            if self.monitoring_thread:
                try:
                    self.monitoring_thread.join(timeout=1)
                except Exception:
                    pass
        
        # 检查邮件配置
        email_address = self.email_config.get("email_address")
        password = self._resolve_password()
        
        if not email_address or not password:
            logger.error("未配置邮箱账号信息，无法启动监控")
            return False
        
        self.monitoring_enabled = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="EmailMonitorThread"
        )
        self.monitoring_thread.start()
        
        logger.info("邮件监控已启动")
        return True
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring_enabled = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        logger.info("邮件监控已停止")
        return True
    
    def _monitoring_loop(self):
        """监控循环"""
        check_interval = self.email_config.get("check_interval", 300)
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        try:
            while self.monitoring_enabled:
                try:
                    # 检查新邮件
                    new_emails = self.check_new_emails()
                    
                    if new_emails:
                        logger.info(f"发现 {len(new_emails)} 封新邮件")
                        
                        # 处理每封邮件
                        for email_data in new_emails:
                            self.process_email(email_data)
                    
                    # 成功执行，重置错误计数
                    consecutive_errors = 0
                    
                    # 等待下次检查
                    time.sleep(check_interval)
                    
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"邮件监控循环出错 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    
                    # 如果连续错误过多，增加等待时间
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"邮件监控连续失败{consecutive_errors}次，暂停监控10分钟")
                        time.sleep(600)  # 暂停10分钟
                        consecutive_errors = 0  # 重置计数，重新尝试
                    else:
                        # 错误后等待时间逐渐增加（1分钟、2分钟、4分钟...）
                        backoff_time = min(60 * (2 ** (consecutive_errors - 1)), 300)  # 最大5分钟
                        logger.info(f"等待{backoff_time}秒后重试")
                        time.sleep(backoff_time)
        
        except Exception as fatal_error:
            logger.critical(f"邮件监控线程发生致命错误，线程即将退出: {fatal_error}")
            # 线程退出，但monitoring_enabled标志可能仍为True
            # 这里可以设置一个标志或调用回调来通知需要重新启动
            # 目前只记录错误，线程结束
            self.monitoring_enabled = False  # 自动停止监控
        finally:
            logger.info("邮件监控循环已结束")
    
    def check_new_emails(self) -> List[Dict[str, Any]]:
        """检查新邮件"""
        import socket
        
        email_address = self.email_config.get("email_address")
        password = self._resolve_password()
        
        if not email_address or not password:
            logger.error("邮箱账号信息未配置")
            return []
        
        mail = None
        try:
            # 设置超时（Python 3.9+ 支持 timeout 参数）
            socket.setdefaulttimeout(30)
            
            # 连接 IMAP 服务器
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port, timeout=30)
            mail.login(email_address, password)
            mail.select("INBOX")
            
            # 搜索未读邮件
            status, messages = mail.search(None, 'UNSEEN')
            if status != 'OK':
                logger.error("搜索邮件失败")
                mail.logout()
                return []
            
            email_ids = messages[0].split()
            max_emails = self.email_config.get("max_emails_per_check", 10)
            email_ids = email_ids[:max_emails]
            
            new_emails = []
            
            for email_id in email_ids:
                try:
                    # 获取邮件
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    if status != 'OK':
                        continue
                    
                    # 解析邮件
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # 提取邮件信息
                    email_info = self.extract_email_info(msg, email_id.decode())
                    
                    # 标记为已读
                    mail.store(email_id, '+FLAGS', '\\Seen')
                    
                    new_emails.append(email_info)
                    
                except Exception as e:
                    logger.error(f"处理邮件 {email_id} 失败: {e}")
                    continue
            
            mail.logout()
            return new_emails
            
        except Exception as e:
            logger.error(f"检查新邮件失败: {e}")
            return []
    
    def _decode_header(self, header_value: Optional[str], default: str = "") -> str:
        """解码邮件头，支持多部分编码（如 =?UTF-8?B?...?= 格式）
        
        Args:
            header_value: 邮件头值，可能为None或空字符串
            default: 当header_value为None或空时返回的默认值
            
        Returns:
            解码后的字符串
        """
        if not header_value:
            return default
            
        try:
            # decode_header返回列表，每个元素是(decoded_bytes, encoding)或(decoded_str, None)
            decoded_parts = decode_header(header_value)
            decoded_text_parts = []
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    # 字节部分需要解码
                    if encoding:
                        decoded_text_parts.append(part.decode(encoding, errors='replace'))
                    else:
                        # 如果没有指定编码，尝试常用编码
                        for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
                            try:
                                decoded_text_parts.append(part.decode(enc))
                                break
                            except UnicodeDecodeError:
                                continue
                        else:
                            # 所有编码都失败，使用replace错误处理
                            decoded_text_parts.append(part.decode('utf-8', errors='replace'))
                else:
                    # 已经是字符串
                    decoded_text_parts.append(part)
            
            # 拼接所有部分
            return ''.join(decoded_text_parts).strip()
            
        except Exception as e:
            logger.error(f"解码邮件头失败: {header_value}, 错误: {e}")
            # 返回原始值或默认值
            return str(header_value) if header_value else default
    
    def extract_email_info(self, msg: email.message.Message, email_id: str) -> Dict[str, Any]:
        """提取邮件信息"""
        # 解码主题
        subject = self._decode_header(msg["Subject"], "无主题")
        
        # 解码发件人
        from_header = msg["From"]
        sender_email = ""
        sender_name = ""
        
        if from_header:
            from_text = self._decode_header(from_header, "")
            if from_text:
                # 提取邮箱和姓名
                match = re.search(r'([^<]+)<([^>]+)>', from_text)
                if match:
                    sender_name = match.group(1).strip()
                    sender_email = match.group(2).strip()
                else:
                    if '@' in from_text:
                        sender_email = from_text.strip()
                        sender_name = from_text.strip()
                    else:
                        sender_name = from_text.strip()
                        sender_email = ""
        
        # 解码收件人
        to_header = self._decode_header(msg["To"], "") if msg["To"] else ""
        
        # 提取日期
        date_header = msg["Date"] or ""
        
        # 提取邮件内容
        content = self.extract_email_content(msg)
        
        # 提取纯文本内容（用于分类）
        plain_content = self.extract_plain_text_content(msg)
        
        return {
            "message_id": email_id,
            "sender_email": sender_email,
            "sender_name": sender_name,
            "recipient_email": to_header,
            "subject": subject,
            "content": content,
            "plain_content": plain_content,
            "date": date_header,
            "received_at": datetime.now().isoformat()
        }
    
    def extract_email_content(self, msg: email.message.Message) -> str:
        """提取邮件内容（包含HTML）"""
        content = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # 跳过附件
                if "attachment" in content_disposition:
                    continue
                
                if content_type == "text/plain":
                    # 文本部分
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        content += payload.decode(charset, errors='ignore')
                    except:
                        pass
                elif content_type == "text/html":
                    # HTML部分
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        html_content = payload.decode(charset, errors='ignore')
                        # 简单提取文本（实际应该使用HTML解析器）
                        html_content = re.sub(r'<[^>]+>', ' ', html_content)
                        content += html_content
                    except:
                        pass
        else:
            # 非多部分邮件
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                content = payload.decode(charset, errors='ignore')
            except:
                content = str(msg.get_payload())
        
        return content
    
    def extract_plain_text_content(self, msg: email.message.Message) -> str:
        """提取纯文本内容（用于分类）"""
        plain_text = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # 跳过附件
                if "attachment" in content_disposition:
                    continue
                
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        plain_text += payload.decode(charset, errors='ignore')
                    except:
                        pass
        else:
            if msg.get_content_type() == "text/plain":
                try:
                    payload = msg.get_payload(decode=True)
                    charset = msg.get_content_charset() or 'utf-8'
                    plain_text = payload.decode(charset, errors='ignore')
                except:
                    plain_text = str(msg.get_payload())
        
        return plain_text
    
    def process_email(self, email_data: Dict[str, Any]):
        """处理单封邮件"""
        message_id = email_data.get("message_id")
        
        # 检查是否已处理
        if message_id in self.processed_emails:
            return
        
        # 分类邮件
        classification_result = self.classify_email(email_data)
        classification = classification_result.get("classification", "unknown")
        priority = classification_result.get("priority", "normal")
        
        # 保存到数据库
        self.save_email_to_db(email_data, classification, priority)
        
        # 标记为已处理
        self.processed_emails.add(message_id)
        
        # 根据分类处理
        if classification == "complaint" or priority == "high":
            # 投诉或高优先级邮件
            self.handle_priority_email(email_data, classification)
        
        elif classification == "consultation" and self.email_config.get("auto_reply_enabled", True):
            # 咨询类邮件，自动回复
            self.auto_reply_to_consultation(email_data, classification_result)
        
        elif classification == "subscription" and self.email_config.get("archive_subscriptions", True):
            # 订阅类邮件，归档
            self.archive_subscription_email(email_data)
        
        elif classification == "spam":
            # 垃圾邮件，标记或删除
            self.handle_spam_email(email_data)
        
        logger.info(f"邮件处理完成：{email_data.get('subject')} - 分类：{classification}")
    
    def classify_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """分类邮件"""
        subject = email_data.get("subject", "").lower()
        content = email_data.get("plain_content", "").lower()
        sender = email_data.get("sender_email", "").lower()
        
        text = f"{subject} {content}"
        
        best_match = None
        best_score = 0
        
        for category, rules in self.classification_rules.items():
            score = 0
            
            # 关键词匹配
            keywords = rules.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in text:
                    score += 2
            
            # 正则表达式匹配
            patterns = rules.get("patterns", [])
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    score += 3
            
            # 发件人匹配（订阅类邮件）
            if category == "subscription":
                subscription_keywords = ["newsletter", "subscribe", "news", "update"]
                for keyword in subscription_keywords:
                    if keyword in sender:
                        score += 5
            
            if score > best_score:
                best_score = score
                best_match = category
        
        if best_match and best_score > 0:
            return {
                "classification": best_match,
                "priority": self.classification_rules[best_match].get("priority", "normal"),
                "score": best_score,
                "auto_reply": self.classification_rules[best_match].get("auto_reply", False),
                "folder": self.classification_rules[best_match].get("folder", "INBOX")
            }
        else:
            return {
                "classification": "unknown",
                "priority": "normal",
                "score": 0,
                "auto_reply": False,
                "folder": "INBOX"
            }
    
    def save_email_to_db(self, email_data: Dict[str, Any], classification: str, priority: str):
        """保存邮件到数据库"""
        cursor = self.email_db.cursor()
        
        cursor.execute('''
        INSERT INTO emails (message_id, sender_email, sender_name, recipient_email, 
                          subject, content, classification, priority, received_at, processed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            email_data.get("message_id"),
            email_data.get("sender_email"),
            email_data.get("sender_name"),
            email_data.get("recipient_email"),
            email_data.get("subject"),
            email_data.get("content"),
            classification,
            priority,
            email_data.get("received_at"),
            datetime.now().isoformat()
        ))
        
        # 更新分类统计
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
        INSERT OR REPLACE INTO classification_stats (date, classification, count)
        VALUES (?, ?, COALESCE((SELECT count FROM classification_stats WHERE date = ? AND classification = ?), 0) + 1)
        ''', (today, classification, today, classification))
        
        self.email_db.commit()
    
    def handle_priority_email(self, email_data: Dict[str, Any], classification: str):
        """处理高优先级邮件"""
        # 添加到优先级列表
        self.priority_emails.append({
            "email": email_data,
            "classification": classification,
            "received_at": datetime.now().isoformat()
        })
        
        # 这里可以触发弹窗提醒（需要UI集成）
        logger.warning(f"高优先级邮件：{email_data.get('subject')} - 发件人：{email_data.get('sender_email')}")
        
        # 可以发送通知邮件给用户
        self.send_priority_notification(email_data)
    
    def send_priority_notification(self, email_data: Dict[str, Any]):
        """发送优先级通知（给用户自己）"""
        if not self.email_config.get("email_address"):
            return
        
        notification_email = self.email_config.get("email_address")
        subject = f"【高优先级邮件提醒】{email_data.get('subject')}"
        
        body = f"""
发现一封高优先级邮件：

发件人：{email_data.get('sender_name')} <{email_data.get('sender_email')}>
主题：{email_data.get('subject')}
时间：{email_data.get('received_at')}

邮件内容摘要：
{email_data.get('content', '')[:500]}...

请尽快处理此邮件。
        """
        
        try:
            self.send_email(
                to_address=notification_email,
                subject=subject,
                body=body
            )
            logger.info(f"已发送优先级通知邮件")
        except Exception as e:
            logger.error(f"发送优先级通知失败: {e}")
    
    def auto_reply_to_consultation(self, email_data: Dict[str, Any], classification_result: Dict[str, Any]):
        """自动回复咨询类邮件"""
        # 从邮件内容中提取问题
        question = self.extract_question_from_email(email_data)
        
        # 从FAQ知识库中查找答案
        faq_answer = self.find_faq_answer(question)
        
        # 尝试从知识库获取答案（如果配置了知识库）
        kb_answer = None
        if self.knowledge_base is not None:
            try:
                # 搜索知识库中的相关内容
                search_results = self.knowledge_base.search(question, limit=3)
                if search_results:
                    # 合并搜索结果作为参考
                    kb_answer = "\n".join([r.get("summary", "") for r in search_results if r.get("summary")])
                    logger.debug(f"从知识库找到 {len(search_results)} 条相关内容")
            except Exception as e:
                logger.warning(f"搜索知识库失败: {e}")
        else:
            logger.debug("知识库未配置，跳过知识库搜索")
        
        # 生成回复内容
        reply_data = self.generate_auto_reply(email_data, question, faq_answer or kb_answer)
        
        if reply_data:
            # 发送回复邮件
            success = self.send_email(
                to_address=email_data.get("sender_email"),
                subject=reply_data.get("subject"),
                body=reply_data.get("body")
            )
            
            if success:
                # 更新数据库
                cursor = self.email_db.cursor()
                cursor.execute('''
                UPDATE emails SET auto_replied = TRUE, reply_sent = TRUE WHERE message_id = ?
                ''', (email_data.get("message_id"),))
                
                # 更新FAQ使用统计
                if faq_answer:
                    cursor.execute('''
                    UPDATE faq_knowledge SET usage_count = usage_count + 1 WHERE id = ?
                    ''', (faq_answer.get("id"),))
                
                # 更新分类统计
                today = datetime.now().strftime("%Y-%m-%d")
                cursor.execute('''
                UPDATE classification_stats SET auto_replied = auto_replied + 1 
                WHERE date = ? AND classification = ?
                ''', (today, classification_result.get("classification")))
                
                self.email_db.commit()
                
                logger.info(f"已自动回复咨询邮件：{email_data.get('subject')}")
    
    def extract_question_from_email(self, email_data: Dict[str, Any]) -> str:
        """从邮件中提取问题"""
        content = email_data.get("plain_content", "")
        subject = email_data.get("subject", "")
        
        # 简单提取第一段或前200字符
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) > 10:
                return line[:200]
        
        # 如果没有合适的内容，使用主题
        return subject[:100]
    
    def find_faq_answer(self, question: str) -> Optional[Dict[str, Any]]:
        """从FAQ知识库中查找答案"""
        cursor = self.email_db.cursor()
        
        # 简单关键词匹配
        words = re.findall(r'\b\w+\b', question.lower())
        if not words:
            return None
        
        # 构建查询条件
        conditions = []
        params = []
        
        for word in words[:5]:  # 最多使用5个关键词
            if len(word) > 2:  # 忽略太短的词
                conditions.append("(question LIKE ? OR answer LIKE ? OR tags LIKE ?)")
                params.extend([f"%{word}%", f"%{word}%", f"%{word}%"])
        
        if not conditions:
            return None
        
        query = f"""
        SELECT id, question, answer, category, tags, usage_count
        FROM faq_knowledge
        WHERE {' OR '.join(conditions)}
        ORDER BY usage_count DESC
        LIMIT 1
        """
        
        cursor.execute(query, params)
        result = cursor.fetchone()
        
        if result:
            return {
                "id": result[0],
                "question": result[1],
                "answer": result[2],
                "category": result[3],
                "tags": result[4],
                "usage_count": result[5]
            }
        
        return None
    
    def generate_auto_reply(self, email_data: Dict[str, Any], question: str, faq_answer: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
        """生成自动回复"""
        sender_name = email_data.get("sender_name", "用户")
        original_subject = email_data.get("subject", "")
        
        if faq_answer:
            # 使用FAQ答案
            template_name = "consultation_general"
            template_vars = {
                "recipient_name": sender_name,
                "original_subject": original_subject,
                "query_topic": question[:100],
                "faq_answer": faq_answer.get("answer", ""),
                "your_name": self.email_config.get("your_name", "AI助手"),
                "company_name": self.email_config.get("company_name", "智能助手")
            }
        else:
            # 没有找到FAQ，使用通用回复
            template_name = "consultation_no_faq"
            template_vars = {
                "recipient_name": sender_name,
                "original_subject": original_subject,
                "query_topic": question[:100],
                "your_name": self.email_config.get("your_name", "AI助手"),
                "company_name": self.email_config.get("company_name", "智能助手")
            }
        
        template = self.auto_reply_templates.get(template_name)
        if not template:
            return None
        
        # 替换模板变量
        subject = template.get("subject", "")
        body = template.get("body", "")
        
        for key, value in template_vars.items():
            placeholder = "{" + key + "}"
            subject = subject.replace(placeholder, value)
            body = body.replace(placeholder, value)
        
        return {
            "subject": subject,
            "body": body
        }
    
    def archive_subscription_email(self, email_data: Dict[str, Any]):
        """归档订阅邮件"""
        # 这里应该实现IMAP移动邮件到"阅读列表"文件夹
        # 由于IMAP操作复杂，这里只记录日志
        logger.info(f"归档订阅邮件：{email_data.get('subject')}")
        
        # 更新数据库
        cursor = self.email_db.cursor()
        cursor.execute('''
        UPDATE emails SET archived = TRUE, folder = '阅读列表' WHERE message_id = ?
        ''', (email_data.get("message_id"),))
        self.email_db.commit()
    
    def handle_spam_email(self, email_data: Dict[str, Any]):
        """处理垃圾邮件"""
        logger.info(f"标记为垃圾邮件：{email_data.get('subject')}")
        
        # 更新数据库
        cursor = self.email_db.cursor()
        cursor.execute('''
        UPDATE emails SET folder = '垃圾邮件' WHERE message_id = ?
        ''', (email_data.get("message_id"),))
        self.email_db.commit()
    
    def send_email(self, to_address: str, subject: str, body: str, 
                  from_address: str = None, password: str = None,
                  attachments: List[str] = None) -> bool:
        """发送邮件（支持附件）
        
        Args:
            to_address: 收件人邮箱
            subject: 邮件主题
            body: 邮件正文
            from_address: 发件人邮箱（默认为配置中的邮箱）
            password: 发件人密码（默认为配置中的密码）
            attachments: 附件文件路径列表
            
        Returns:
            发送是否成功
        """
        if self.social_skills:
            # 使用social_skills的发送功能，检查是否支持附件
            try:
                # 尝试调用带附件参数的方法
                return self.social_skills.send_email(
                    to_address=to_address,
                    subject=subject,
                    body=body,
                    from_address=from_address,
                    password=password,
                    attachments=attachments
                )
            except TypeError:
                # social_skills的send_email可能不支持attachments参数
                logger.warning("social_skills的send_email方法不支持附件，使用内置实现")
                # 继续使用内置实现
        
        # 自己实现发送逻辑
        if not from_address:
            from_address = self.email_config.get("email_address")
            password = self._resolve_password()
        elif not password:
            password = self._resolve_password()
        
        if not from_address or not password:
            logger.error("发件人信息不完整")
            return False
        
        try:
            if YAGMAIL_AVAILABLE:
                import yagmail
                yag = yagmail.SMTP(from_address, password, host=self.smtp_server, port=self.smtp_port)
                
                # yagmail自动处理附件
                if attachments:
                    yag.send(to=to_address, subject=subject, contents=body, attachments=attachments)
                else:
                    yag.send(to=to_address, subject=subject, contents=body)
                    
                logger.info(f"邮件发送成功：{to_address}" + (f"，附件：{len(attachments)}个" if attachments else ""))
                return True
            else:
                # 使用smtplib
                msg = MIMEMultipart()
                msg['From'] = from_address
                msg['To'] = to_address
                msg['Subject'] = subject
                
                # 邮件正文
                msg.attach(MIMEText(body, 'plain', 'utf-8'))
                
                # 添加附件
                if attachments:
                    for attachment_path in attachments:
                        if not os.path.exists(attachment_path):
                            logger.warning(f"附件文件不存在：{attachment_path}")
                            continue
                        
                        try:
                            # 获取文件名和MIME类型
                            filename = os.path.basename(attachment_path)
                            mime_type, encoding = mimetypes.guess_type(attachment_path)
                            if mime_type is None or encoding is not None:
                                mime_type = 'application/octet-stream'
                            
                            main_type, sub_type = mime_type.split('/', 1)
                            
                            with open(attachment_path, 'rb') as f:
                                if main_type == 'text':
                                    # 文本文件
                                    from email.mime.text import MIMEText
                                    attachment = MIMEText(f.read().decode('utf-8', errors='ignore'), _subtype=sub_type, _charset='utf-8')
                                else:
                                    # 二进制文件
                                    from email.mime.base import MIMEBase
                                    attachment = MIMEBase(main_type, sub_type)
                                    attachment.set_payload(f.read())
                                
                            # 添加头部信息
                            attachment.add_header('Content-Disposition', 'attachment', filename=filename)
                            attachment.add_header('Content-ID', f'<{filename}>')
                            
                            # 对于非文本文件，需要编码
                            if main_type != 'text':
                                from email import encoders
                                encoders.encode_base64(attachment)
                            
                            msg.attach(attachment)
                            logger.debug(f"已添加附件：{filename}")
                            
                        except Exception as e:
                            logger.error(f"添加附件失败 {attachment_path}: {e}")
                            continue
                
                # 发送邮件
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(from_address, password)
                server.send_message(msg)
                server.quit()
                
                logger.info(f"邮件发送成功：{to_address}" + (f"，附件：{len(attachments)}个" if attachments else ""))
                return True
                
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False
    
    def add_faq(self, question: str, answer: str, category: str = "general", tags: str = ""):
        """添加FAQ到知识库"""
        cursor = self.email_db.cursor()
        
        cursor.execute('''
        INSERT INTO faq_knowledge (question, answer, category, tags)
        VALUES (?, ?, ?, ?)
        ''', (question, answer, category, tags))
        
        self.email_db.commit()
        logger.info(f"已添加FAQ：{question}")
        
        return True
    
    def search_faq(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """搜索FAQ"""
        cursor = self.email_db.cursor()
        
        cursor.execute('''
        SELECT id, question, answer, category, tags, usage_count
        FROM faq_knowledge
        WHERE question LIKE ? OR answer LIKE ? OR tags LIKE ?
        ORDER BY usage_count DESC
        LIMIT ?
        ''', (f"%{query}%", f"%{query}%", f"%{query}%", limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "question": row[1],
                "answer": row[2],
                "category": row[3],
                "tags": row[4],
                "usage_count": row[5]
            })
        
        return results
    
    def get_email_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取邮件统计信息"""
        cursor = self.email_db.cursor()
        
        # 总邮件数
        cursor.execute("SELECT COUNT(*) FROM emails")
        total_emails = cursor.fetchone()[0]
        
        # 分类统计
        cursor.execute('''
        SELECT classification, COUNT(*) as count, 
               SUM(CASE WHEN auto_replied THEN 1 ELSE 0 END) as auto_replied_count
        FROM emails
        WHERE date(received_at) >= date('now', ?)
        GROUP BY classification
        ''', (f'-{days} days',))
        
        classification_stats = {}
        for row in cursor.fetchall():
            classification_stats[row[0]] = {
                "count": row[1],
                "auto_replied": row[2]
            }
        
        # 优先级统计
        cursor.execute('''
        SELECT priority, COUNT(*) as count
        FROM emails
        WHERE date(received_at) >= date('now', ?)
        GROUP BY priority
        ''', (f'-{days} days',))
        
        priority_stats = {}
        for row in cursor.fetchall():
            priority_stats[row[0]] = row[1]
        
        return {
            "total_emails": total_emails,
            "classification_stats": classification_stats,
            "priority_stats": priority_stats,
            "monitoring_enabled": self.monitoring_enabled,
            "processed_count": len(self.processed_emails),
            "priority_emails_count": len(self.priority_emails)
        }
    
    def manual_classify_and_reply(self, email_content: str, sender_email: str, subject: str = "") -> Dict[str, Any]:
        """手动分类和回复（用于测试或手动处理）"""
        email_data = {
            "message_id": f"manual_{int(time.time())}",
            "sender_email": sender_email,
            "sender_name": sender_email,
            "recipient_email": self.email_config.get("email_address", ""),
            "subject": subject or "手动处理邮件",
            "content": email_content,
            "plain_content": email_content,
            "received_at": datetime.now().isoformat()
        }
        
        # 分类
        classification_result = self.classify_email(email_data)
        
        # 生成回复
        question = self.extract_question_from_email(email_data)
        faq_answer = self.find_faq_answer(question)
        reply_data = self.generate_auto_reply(email_data, question, faq_answer)
        
        return {
            "classification": classification_result,
            "question_extracted": question,
            "faq_found": faq_answer is not None,
            "reply_data": reply_data
        }