"""
AsyncEmailClassifier - 异步邮件分类器
- 多账号并发监控
- 异步IMAP轮询
- ML文本分类（sklearn TF-IDF + NaiveBayes）兜底规则
- 自动回复草稿 → 用户确认 → 发送
"""
import logging
import json
import time
import re
import asyncio
import threading
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger("AsyncEmailClassifier")

# ML 相关
SKLEARN_AVAILABLE = False
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.pipeline import Pipeline
    SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning("sklearn 未安装，ML分类不可用。pip install scikit-learn")


# ── 数据模型 ─────────────────────────────────────────────────────────────────

class EmailCategory(Enum):
    INQUIRY     = "inquiry"       # 咨询
    COMPLAINT   = "complaint"     # 投诉
    NEWSLETTER  = "newsletter"   # 新闻订阅
    WORK        = "work"          # 工作
    PERSONAL    = "personal"      # 个人
    UNKNOWN     = "unknown"       # 未分类


class EmailPriority(Enum):
    LOW    = 0
    NORMAL = 1
    HIGH   = 2
    URGENT = 3


@dataclass
class EmailMessage:
    """邮件对象"""
    message_id: str
    subject: str
    sender: str
    recipients: List[str]
    date: datetime
    body_text: str
    body_html: str = ""
    category: EmailCategory = EmailCategory.UNKNOWN
    priority: EmailPriority = EmailPriority.NORMAL
    is_read: bool = False
    labels: List[str] = field(default_factory=list)
    thread_id: str = ""
    reply_to: Optional[str] = None
    attachments: List[Dict] = field(default_factory=list)


@dataclass
class AccountConfig:
    """单账号配置"""
    name: str
    imap_host: str
    smtp_host: str
    username: str
    password: str
    imap_port: int = 993
    smtp_port: int = 587
    folders: List[str] = None
    check_interval: int = 30  # 秒
    auto_classify: bool = True
    auto_reply: bool = False
    enable: bool = True


# ── ML 分类器 ────────────────────────────────────────────────────────────────

class MLClassifier:
    """ML 文本分类器：TF-IDF + NaiveBayes"""

    def __init__(self):
        self._pipeline: Optional[Pipeline] = None
        self._trained = False
        self._db_path = str(Path(__file__).parent.parent / "knowledge_base" / "data" / "email_ml.db")
        self._init_db()

    def _init_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS training_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                category TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def train(self, texts: List[str], labels: List[str]):
        """训练模型"""
        if not SKLEARN_AVAILABLE or len(texts) < 3:
            logger.warning("[MLClassifier] Not enough data or sklearn unavailable")
            return

        try:
            self._pipeline = Pipeline([
                ("tfidf", TfidfVectorizer(max_features=2000, ngram_range=(1, 2))),
                ("clf", MultinomialNB(alpha=0.1)),
            ])
            self._pipeline.fit(texts, labels)
            self._trained = True
            logger.info(f"[MLClassifier] Trained on {len(texts)} samples")
        except Exception as e:
            logger.error(f"[MLClassifier] Training failed: {e}")
            self._trained = False

    def train_from_db(self):
        """从数据库加载训练数据并训练"""
        conn = sqlite3.connect(self._db_path)
        c = conn.cursor()
        c.execute("SELECT text, category FROM training_data")
        rows = c.fetchall()
        conn.close()
        if len(rows) >= 3:
            self.train([r[0] for r in rows], [r[1] for r in rows])

    def predict(self, text: str) -> Optional[str]:
        """预测分类"""
        if not self._trained or not self._pipeline:
            return None
        try:
            return self._pipeline.predict([text])[0]
        except Exception as e:
            logger.warning(f"[MLClassifier] Predict failed: {e}")
            return None

    def add_training_sample(self, text: str, category: str):
        """添加训练样本"""
        conn = sqlite3.connect(self._db_path)
        c = conn.cursor()
        c.execute("INSERT INTO training_data (text, category) VALUES (?, ?)",
                 (text[:5000], category))
        conn.commit()
        conn.close()
        # 实时追加训练
        self.train_from_db()


# ── 异步邮件处理器 ────────────────────────────────────────────────────────────

class AsyncEmailProcessor:
    """
    异步邮件处理器。

    使用 asyncio + threading 混合：
    - 账号轮询用 asyncio（协程切换，多账号并发）
    - IMAP/SMTP 操作用同步库包在 run_in_executor 里
    """

    def __init__(self, config_manager=None, event_bus=None):
        self.config_manager = config_manager
        self.event_bus = event_bus
        self._accounts: Dict[str, AccountConfig] = {}
        self._account_tasks: Dict[str, asyncio.Task] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._executor = threading.Thread(target=self._run_executor, daemon=True)
        self._executor.start()
        self._processed_ids: Dict[str, set] = defaultdict(set)  # account -> seen ids
        self._draft_queue: List[Dict] = []   # 待确认草稿
        self._draft_lock = threading.Lock()
        self._ml = MLClassifier() if SKLEARN_AVAILABLE else None
        self._rules = self._load_rules()
        self._running = False

    # ── 配置 ─────────────────────────────────────────────────────────────

    def add_account(self, config: AccountConfig):
        """添加账号"""
        self._accounts[config.name] = config
        logger.info(f"[AsyncEmail] Added account: {config.name}")

    def _load_rules(self) -> Dict:
        """加载分类规则"""
        rule_file = Path(__file__).parent.parent / "knowledge_base" / "config" / "email_classification_rules.json"
        if rule_file.exists():
            try:
                with open(rule_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    # ── 生命周期 ─────────────────────────────────────────────────────────

    async def start(self):
        """启动所有账号的轮询"""
        self._running = True
        logger.info(f"[AsyncEmail] Starting {len(self._accounts)} accounts...")
        for name, account in self._accounts.items():
            if account.enable:
                task = asyncio.create_task(self._poll_account(account))
                self._account_tasks[name] = task

    async def stop(self):
        """停止"""
        self._running = False
        for task in self._account_tasks.values():
            task.cancel()
        await asyncio.gather(*self._account_tasks.values(), return_exceptions=True)
        self._account_tasks.clear()
        logger.info("[AsyncEmail] Stopped")

    # ── 核心轮询 ─────────────────────────────────────────────────────────

    async def _poll_account(self, account: AccountConfig):
        """轮询单个账号"""
        seen_ids = self._processed_ids[account.name]
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # 在线程池里执行同步 IMAP 操作
                emails = await loop.run_in_executor(
                    None, self._fetch_new_emails, account, seen_ids
                )
                for email in emails:
                    seen_ids.add(email.message_id)
                    await self._process_email(email, account)
            except Exception as e:
                logger.error(f"[AsyncEmail] Poll error for {account.name}: {e}", exc_info=True)

            await asyncio.sleep(account.check_interval)

    def _fetch_new_emails(self, account: AccountConfig, seen_ids: set) -> List[EmailMessage]:
        """同步获取新邮件"""
        import imaplib
        emails = []
        try:
            mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
            mail.login(account.username, account.password)
            folders = account.folders or ["INBOX"]
            for folder in folders:
                try:
                    mail.select(folder)
                    _, msg_ids = mail.search(None, "UNSEEN")
                    for msg_id in msg_ids[0].split():
                        if msg_id.decode() in seen_ids:
                            continue
                        try:
                            email = self._parse_email(mail, msg_id)
                            if email:
                                emails.append(email)
                        except Exception as e:
                            logger.warning(f"[AsyncEmail] Parse error msg {msg_id}: {e}")
                except Exception as e:
                    logger.warning(f"[AsyncEmail] Folder error {folder}: {e}")
            mail.logout()
        except Exception as e:
            logger.error(f"[AsyncEmail] IMAP error for {account.name}: {e}")
        return emails

    def _parse_email(self, mail, msg_id) -> Optional[EmailMessage]:
        """解析单封邮件"""
        import email
        from email.header import decode_header

        _, data = mail.fetch(msg_id, "(RFC822)")
        raw = email.message_from_bytes(data[0][1])

        # 解码主题
        subject_raw = raw.get("Subject", "")
        subject = self._decode_header_str(subject_raw)

        # 发件人
        sender = self._decode_header_str(raw.get("From", ""))

        # 日期
        date_str = raw.get("Date", "")
        try:
            from email.utils import parsedate_to_datetime
            date = parsedate_to_datetime(date_str)
        except Exception:
            date = datetime.now()

        # Message-ID
        msg_id_str = raw.get("Message-ID", msg_id.decode())
        if isinstance(msg_id_str, bytes):
            msg_id_str = msg_id_str.decode(errors="replace")

        # 提取正文
        body_text, body_html = self._extract_body(raw)

        return EmailMessage(
            message_id=hashlib.md5(msg_id_str.encode()).hexdigest()[:16],
            subject=subject,
            sender=sender,
            recipients=[raw.get("To", "")],
            date=date,
            body_text=body_text,
            body_html=body_html,
        )

    def _decode_header_str(self, raw: str) -> str:
        """解码 email 编码的头"""
        try:
            import email.header
            parts = email.header.decode_header(raw)
            result = []
            for part, encoding in parts:
                if isinstance(part, bytes):
                    result.append(part.decode(encoding or "utf-8", errors="replace"))
                else:
                    result.append(part)
            return "".join(result)
        except Exception:
            return raw or ""

    def _extract_body(self, raw) -> tuple:
        """提取邮件正文"""
        body_text, body_html = "", ""
        if raw.is_multipart():
            for part in raw.walk():
                ct = part.get_content_type()
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    text = payload.decode(charset, errors="replace")
                except Exception:
                    text = payload.decode("utf-8", errors="replace")
                if ct == "text/plain":
                    body_text = text
                elif ct == "text/html":
                    body_html = text
        else:
            payload = raw.get_payload(decode=True)
            if payload:
                charset = raw.get_content_charset() or "utf-8"
                try:
                    body_text = payload.decode(charset, errors="replace")
                except Exception:
                    body_text = payload.decode("utf-8", errors="replace")
        return body_text[:10000], body_html  # 截断防止过大

    # ── 处理邮件 ─────────────────────────────────────────────────────────

    async def _process_email(self, email: EmailMessage, account: AccountConfig):
        """处理单封邮件"""
        logger.info(f"[AsyncEmail] Processing: {email.subject[:60]} from {email.sender}")

        # 1. 分类
        if account.auto_classify:
            email.category = await self._classify_email(email)

        # 2. 优先级判定
        email.priority = self._determine_priority(email)

        # 3. 发布事件
        if self.event_bus:
            self.event_bus.post("email:new", email, source="AsyncEmailClassifier")

        # 4. 自动回复
        if account.auto_reply and email.category == EmailCategory.INQUIRY:
            draft = await self._draft_reply(email, account)
            if draft:
                with self._draft_lock:
                    self._draft_queue.append(draft)

    async def _classify_email(self, email: EmailMessage) -> EmailCategory:
        """分类邮件"""
        full_text = f"{email.subject}\n{email.body_text[:3000]}"

        # 1. ML 预测
        if self._ml:
            pred = self._ml.predict(full_text)
            if pred:
                try:
                    return EmailCategory(pred)
                except ValueError:
                    pass

        # 2. 规则兜底
        rules = self._rules
        for cat_name, cat_rules in rules.items():
            for rule in cat_rules.get("keywords", []):
                if rule.lower() in full_text.lower():
                    try:
                        return EmailCategory(cat_name)
                    except ValueError:
                        pass

        return EmailCategory.UNKNOWN

    def _determine_priority(self, email: EmailMessage) -> EmailPriority:
        """判定优先级"""
        text = f"{email.subject}\n{email.body_text}".lower()
        urgent_keywords = ["紧急", "urgent", "!!!", "asap", "critical", "严重", "马上", "立刻"]
        high_keywords = ["重要", "important", "请尽快", " deadline", "截止"]
        for kw in urgent_keywords:
            if kw in text:
                return EmailPriority.URGENT
        for kw in high_keywords:
            if kw in text:
                return EmailPriority.HIGH
        if email.category == EmailCategory.COMPLAINT:
            return EmailPriority.HIGH
        return EmailPriority.NORMAL

    async def _draft_reply(self, email: EmailMessage, account: AccountConfig) -> Optional[Dict]:
        """生成回复草稿"""
        # 简单模板回复，后续可接 AI 生成
        body = f"""您好，感谢您的来信。

关于「{email.subject}」，我们正在处理中，如有需要会进一步与您联系。

祝好
AI 电脑管家"""

        return {
            "message_id": email.message_id,
            "to": email.sender,
            "subject": f"Re: {email.subject}",
            "body": body,
            "account": account.name,
            "created_at": datetime.now().isoformat(),
        }

    # ── 草稿操作 ─────────────────────────────────────────────────────────

    def get_pending_drafts(self) -> List[Dict]:
        with self._draft_lock:
            return list(self._draft_queue)

    def approve_draft(self, index: int) -> bool:
        """确认发送草稿"""
        with self._draft_lock:
            if 0 <= index < len(self._draft_queue):
                draft = self._draft_queue.pop(index)
                threading.Thread(target=self._send_draft, args=(draft,)).start()
                return True
        return False

    def _send_draft(self, draft: Dict):
        """发送草稿"""
        import smtplib
        from email.mime.text import MIMEText
        account = self._accounts.get(draft.get("account", ""))
        if not account:
            return
        try:
            msg = MIMEText(draft["body"], "plain", "utf-8")
            msg["Subject"] = draft["subject"]
            msg["From"] = account.username
            msg["To"] = draft["to"]
            with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=30) as s:
                s.ehlo()
                s.starttls()
                s.login(account.username, account.password)
                s.send_message(msg)
            logger.info(f"[AsyncEmail] Sent draft to {draft['to']}")
        except Exception as e:
            logger.error(f"[AsyncEmail] Send failed: {e}")

    # ── 内部运行 ─────────────────────────────────────────────────────────

    def _run_executor(self):
        """在后台线程运行事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run_async(self, coro):
        """在线程池事件循环里运行协程"""
        if self._loop:
            return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=30)
