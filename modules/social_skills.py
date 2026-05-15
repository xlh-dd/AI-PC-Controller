import logging
import re
import random
import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("SocialSkills")

class SocialSkills:
    """社交技能模块 - 处理微信、钉钉、邮件等社交通信功能"""

    def __init__(self, wechat_controller=None, config_manager=None):
        self.wechat_controller = wechat_controller
        self.config_manager = config_manager
        self.keyword_responses = {}  # 关键词-回复映射
        self.email_templates = {}    # 邮件模板
        self.load_presets()

    def load_presets(self):
        """加载预设的关键词回复和邮件模板"""
        presets_dir = Path(__file__).parent.parent / "knowledge_base" / "presets"
        presets_dir.mkdir(parents=True, exist_ok=True)

        # 加载关键词回复预设
        keyword_file = presets_dir / "keyword_responses.json"
        if keyword_file.exists():
            try:
                with open(keyword_file, 'r', encoding='utf-8') as f:
                    self.keyword_responses = json.load(f)
                logger.info(f"已加载 {len(self.keyword_responses)} 个关键词回复预设")
            except Exception as e:
                logger.error(f"加载关键词回复预设失败: {e}")
        else:
            self.keyword_responses = self._default_keyword_responses()
            self.save_keyword_responses()

        # 加载邮件模板
        templates_file = presets_dir / "email_templates.json"
        if templates_file.exists():
            try:
                with open(templates_file, 'r', encoding='utf-8') as f:
                    self.email_templates = json.load(f)
                logger.info(f"已加载 {len(self.email_templates)} 个邮件模板")
            except Exception as e:
                logger.error(f"加载邮件模板失败: {e}")
        else:
            self.email_templates = self._default_email_templates()
            self.save_email_templates()

    def _default_keyword_responses(self):
        """默认关键词回复预设"""
        return {
            "你好": ["你好！", "您好，有什么可以帮您？", "Hi！"],
            "在吗": ["在的，请说", "我在，有什么需要帮助的吗？"],
            "谢谢": ["不客气！", "很高兴能帮到您", "您太客气了"],
            "价格": ["关于价格，请查看我们的官网或联系客服", "价格信息需要具体查询，您想了解哪个产品的价格？"],
            "时间": ["现在是{current_time}", "今天日期是{current_date}"]
        }

    def _default_email_templates(self):
        """默认邮件模板"""
        return {
            "商务邀约": {
                "subject": "合作邀约 - {company_name}",
                "body": """尊敬的{recipient_name}：

您好！

我是{your_name}，来自{company_name}。我们注意到贵公司在{industry}领域的卓越成就，希望能够与您探讨潜在的合作机会。

我们公司专注于{your_business}，在{past_achievement}方面有着丰富的经验。我们相信，通过双方的合作，可以为彼此带来更大的价值。

如您方便，可否安排一次简短的线上会议，进一步交流合作的可能性？

期待您的回复！

此致
敬礼

{your_name}
{your_position}
{company_name}
{contact_info}"""
            },
            "会议纪要": {
                "subject": "{meeting_topic} 会议纪要 - {date}",
                "body": """会议纪要

会议主题：{meeting_topic}
会议时间：{meeting_time}
参会人员：{participants}
主持人：{host}

会议内容：
1. {agenda_item_1}
2. {agenda_item_2}
3. {agenda_item_3}

会议决议：
1. {decision_1}
2. {decision_2}

下一步行动：
1. {action_item_1} - 负责人：{owner_1} - 截止时间：{deadline_1}
2. {action_item_2} - 负责人：{owner_2} - 截止时间：{deadline_2}

如有任何疑问，请随时联系。

{your_name}"""
            },
            "请假申请": {
                "subject": "请假申请 - {your_name} - {date_range}",
                "body": """尊敬的{manager_name}：

您好！

因{reason}，我需要请假 {days} 天，具体时间为 {date_range}。

请假期间，我的工作安排如下：
1. {work_arrangement_1}
2. {work_arrangement_2}

紧急联系人：{emergency_contact}
联系电话：{contact_phone}

望批准为盼！

此致
敬礼

{your_name}
{department}
{date}"""
            }
        }

    def save_keyword_responses(self):
        """保存关键词回复预设"""
        presets_dir = Path(__file__).parent.parent / "knowledge_base" / "presets"
        presets_dir.mkdir(parents=True, exist_ok=True)

        keyword_file = presets_dir / "keyword_responses.json"
        try:
            with open(keyword_file, 'w', encoding='utf-8') as f:
                json.dump(self.keyword_responses, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.keyword_responses)} 个关键词回复预设")
        except Exception as e:
            logger.error(f"保存关键词回复预设失败: {e}")

    def save_email_templates(self):
        """保存邮件模板"""
        presets_dir = Path(__file__).parent.parent / "knowledge_base" / "presets"
        presets_dir.mkdir(parents=True, exist_ok=True)

        templates_file = presets_dir / "email_templates.json"
        try:
            with open(templates_file, 'w', encoding='utf-8') as f:
                json.dump(self.email_templates, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(self.email_templates)} 个邮件模板")
        except Exception as e:
            logger.error(f"保存邮件模板失败: {e}")

    def add_keyword_response(self, keyword: str, responses: List[str]):
        """添加关键词回复"""
        self.keyword_responses[keyword] = responses
        self.save_keyword_responses()
        logger.info(f"已添加关键词回复：{keyword}")

    def add_email_template(self, template_name: str, template_data: Dict[str, str]):
        """添加邮件模板"""
        self.email_templates[template_name] = template_data
        self.save_email_templates()
        logger.info(f"已添加邮件模板：{template_name}")

    def auto_reply_wechat(self, message: str) -> Optional[str]:
        """微信自动回复 - 根据关键词匹配回复"""
        if not message:
            return None

        message_lower = message.lower()

        # 检查完全匹配的关键词
        for keyword, responses in self.keyword_responses.items():
            if keyword.lower() in message_lower:
                response = random.choice(responses)

                # 替换模板变量
                response = response.replace("{current_time}", datetime.now().strftime("%H:%M:%S"))
                response = response.replace("{current_date}", datetime.now().strftime("%Y年%m月%d日"))

                return response

        # 检查部分匹配（更宽松的匹配）
        for keyword, responses in self.keyword_responses.items():
            keyword_lower = keyword.lower()
            # 检查是否包含关键词中的主要字符（长度大于2）
            if len(keyword_lower) > 2 and keyword_lower in message_lower:
                response = random.choice(responses)
                response = response.replace("{current_time}", datetime.now().strftime("%H:%M:%S"))
                response = response.replace("{current_date}", datetime.now().strftime("%Y年%m月%d日"))
                return response

        return None

    def generate_email_from_template(self, template_name: str, template_vars: Dict[str, str]) -> Dict[str, str]:
        """根据模板和变量生成邮件"""
        if template_name not in self.email_templates:
            raise ValueError(f"邮件模板 '{template_name}' 不存在")

        template = self.email_templates[template_name]
        subject = template.get("subject", "")
        body = template.get("body", "")

        # 替换模板变量
        for key, value in template_vars.items():
            placeholder = "{" + key + "}"
            subject = subject.replace(placeholder, value)
            body = body.replace(placeholder, value)

        # 替换日期时间变量
        current_time = datetime.now().strftime("%H:%M:%S")
        current_date = datetime.now().strftime("%Y年%m月%d日")
        subject = subject.replace("{current_time}", current_time)
        subject = subject.replace("{current_date}", current_date)
        body = body.replace("{current_time}", current_time)
        body = body.replace("{current_date}", current_date)

        return {
            "subject": subject,
            "body": body,
            "template": template_name
        }

    def send_email(self, to_address: str, subject: str, body: str,
                  from_address: str = None, password: str = None,
                  smtp_server: str = "smtp.gmail.com", smtp_port: int = 587) -> bool:
        """发送邮件

        注意：需要配置邮箱的SMTP设置
        """
        try:
            # 尝试使用yagmail（更简单）
            try:
                import yagmail

                # 如果未提供发件人信息，尝试从配置获取
                if not from_address and self.config_manager:
                    from_address = self.config_manager.get("email", "from_address")
                    password = self.config_manager.get("email", "password")

                if not from_address or not password:
                    logger.error("未配置发件人邮箱信息")
                    return False

                # 创建yagmail连接
                yag = yagmail.SMTP(from_address, password, host=smtp_server, port=smtp_port)
                yag.send(to=to_address, subject=subject, contents=body)
                logger.info(f"邮件发送成功：{to_address}")
                return True

            except ImportError:
                logger.warning("yagmail未安装，尝试使用smtplib")
                import smtplib
                import mimetypes
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                from email.mime.base import MIMEBase
                from email import encoders

                if not from_address or not password:
                    logger.error("未配置发件人邮箱信息")
                    return False

                # 创建邮件
                msg = MIMEMultipart()
                msg['From'] = from_address
                msg['To'] = to_address
                msg['Subject'] = subject

                # 添加邮件正文
                msg.attach(MIMEText(body, 'plain', 'utf-8'))

                # 发送邮件
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(from_address, password)
                server.send_message(msg)
                server.quit()

                logger.info(f"邮件发送成功：{to_address}")
                return True

        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False

    def monitor_and_auto_reply(self, interval_seconds: int = 10):
        """监控并自动回复微信消息

        需要配合微信控制器使用
        """
        if not self.wechat_controller:
            logger.error("微信控制器未设置，无法监控微信消息")
            return

        # 检查微信控制器是否支持所需方法
        required_methods = ['get_latest_messages', 'send_message']
        missing_methods = []
        for method in required_methods:
            if not hasattr(self.wechat_controller, method) or not callable(getattr(self.wechat_controller, method, None)):
                missing_methods.append(method)

        if missing_methods:
            logger.error(f"微信控制器缺少必需方法: {missing_methods}，无法监控微信消息")
            logger.error("请更新微信控制器模块或使用兼容的版本")
            return

        logger.info(f"开始监控微信消息，检查间隔：{interval_seconds}秒")

        try:
            while True:
                # 获取最新消息
                messages = self.wechat_controller.get_latest_messages(count=5)

                for msg in messages:
                    # 检查是否需要回复
                    reply = self.auto_reply_wechat(msg.get("content", ""))
                    if reply:
                        # 发送回复
                        self.wechat_controller.send_wechat_message(target=msg.get("sender", "文件传输助手"), message=reply)
                        logger.info(f"已自动回复消息：{msg.get('content', '')[:50]}...")

                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("微信消息监控已停止")
        except Exception as e:
            logger.error(f"微信消息监控出错: {e}")

    def get_available_templates(self) -> List[str]:
        """获取所有可用的邮件模板名称"""
        return list(self.email_templates.keys())

    def get_template_variables(self, template_name: str) -> List[str]:
        """获取模板所需的所有变量"""
        if template_name not in self.email_templates:
            return []

        template = self.email_templates[template_name]
        subject = template.get("subject", "")
        body = template.get("body", "")

        # 使用正则表达式提取所有 {variable} 格式的变量
        variables = re.findall(r'\{(\w+)\}', subject + body)
        return list(set(variables))  # 去重

    def draft_email_from_speech(self, speech_text: str) -> Dict[str, str]:
        """根据语音口述草拟邮件

        简单实现：从语音中提取关键信息并填充到合适的模板
        """
        # 简单关键词匹配选择模板
        template_name = "商务邀约"  # 默认

        if "会议" in speech_text or "纪要" in speech_text:
            template_name = "会议纪要"
        elif "请假" in speech_text or "休假" in speech_text:
            template_name = "请假申请"
        elif "合作" in speech_text or "邀约" in speech_text:
            template_name = "商务邀约"

        # 简单提取信息（实际应该使用更复杂的NLP）
        template_vars = {}

        # 尝试提取姓名
        name_match = re.search(r'[我|叫|是]\s*([\u4e00-\u9fa5]{2,4})', speech_text)
        if name_match:
            template_vars["your_name"] = name_match.group(1)

        # 尝试提取公司名
        company_match = re.search(r'[公司|来自]\s*([\u4e00-\u9fa5]{2,10}公司|[A-Za-z\s]+)', speech_text)
        if company_match:
            template_vars["company_name"] = company_match.group(1)

        # 添加当前日期
        template_vars["date"] = datetime.now().strftime("%Y年%m月%d日")

        # 生成邮件
        return self.generate_email_from_template(template_name, template_vars)