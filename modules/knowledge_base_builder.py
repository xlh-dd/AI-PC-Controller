import logging
import json
import time
import os
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union, Callable
import threading
import hashlib
import mimetypes
from collections import Counter
from contextlib import contextmanager
import shutil

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logging.warning("requests模块未安装，网页抓取功能受限")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber模块未安装，PDF解析功能受限")

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    logging.warning("notion-client模块未安装，Notion集成功能受限")

try:
    import bs4
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logging.warning("beautifulsoup4模块未安装，HTML解析功能受限")

try:
    import win32file
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

logger = logging.getLogger("KnowledgeBaseBuilder")


class DatabaseManager:
    """数据库管理器 - 统一管理所有数据库操作"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._connection_pool: Dict[int, sqlite3.Connection] = {}
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()
    
    @contextmanager
    def get_connection(self):
        """获取线程安全的数据库连接"""
        thread_id = threading.get_ident()
        
        with self._lock:
            if thread_id not in self._connection_pool:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.row_factory = sqlite3.Row
                self._connection_pool[thread_id] = conn
            conn = self._connection_pool[thread_id]
        
        try:
            yield conn
        except Exception as e:
            logger.error(f"数据库操作错误: {e}")
            raise
    
    def _create_tables(self):
        """创建数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                title TEXT,
                content TEXT,
                summary TEXT,
                categories TEXT,
                tags TEXT,
                keywords TEXT,
                source_type TEXT,
                file_path TEXT,
                file_size INTEGER,
                visit_count INTEGER DEFAULT 1,
                last_visit_time DATETIME,
                total_stay_time INTEGER DEFAULT 0,
                quality_score REAL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            self._migrate_tables(cursor)
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS browser_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                title TEXT,
                visit_time DATETIME,
                stay_time INTEGER,
                browser_type TEXT,
                processed BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE,
                file_name TEXT,
                file_type TEXT,
                file_size INTEGER,
                download_time DATETIME,
                processed BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS page_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                visit_start DATETIME,
                visit_end DATETIME,
                stay_time INTEGER,
                browser_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS notion_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                notion_id TEXT,
                synced_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                sync_status TEXT DEFAULT 'pending',
                error_message TEXT,
                FOREIGN KEY (article_id) REFERENCES articles (id)
            )
            ''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                category TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            self._create_indexes(cursor)
            conn.commit()
    
    def _create_indexes(self, cursor):
        """创建数据库索引"""
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_articles_categories ON articles(categories)
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_browser_history_url ON browser_history(url)
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_browser_history_processed ON browser_history(processed)
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_downloads_processed ON downloads(processed)
        ''')
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_page_visits_url ON page_visits(url)
        ''')

    def _migrate_tables(self, cursor):
        """数据库迁移 - 添加缺失的列"""
        migrations = [
            ("articles", "keywords", "TEXT"),
            ("articles", "quality_score", "REAL DEFAULT 0"),
            ("browser_history", "browser_type", "TEXT"),
            ("browser_history", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("downloads", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ]
        
        for table, column, col_type in migrations:
            try:
                cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                    logger.info(f"数据库迁移: {table}.{column} 列已添加")
                except Exception as e:
                    logger.debug(f"迁移 {table}.{column} 失败: {e}")
    
    def close(self):
        """关闭所有连接"""
        with self._lock:
            for conn in self._connection_pool.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self._connection_pool.clear()
    
    def execute(self, query: str, params: tuple = (), commit: bool = True) -> sqlite3.Cursor:
        """执行SQL语句"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit:
                conn.commit()
            return cursor
    
    def fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """查询单条记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
    
    def fetchall(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """查询多条记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()


class BrowserHistoryReader:
    """浏览器历史记录读取器"""
    
    BROWSER_PATHS = {
        "chrome": {
            "history": "AppData/Local/Google/Chrome/User Data/Default/History",
            "name": "Google Chrome"
        },
        "edge": {
            "history": "AppData/Local/Microsoft/Edge/User Data/Default/History",
            "name": "Microsoft Edge"
        },
        "firefox": {
            "history": "AppData/Roaming/Mozilla/Firefox/Profiles",
            "name": "Mozilla Firefox"
        }
    }
    
    def __init__(self):
        self.home = Path.home()
    
    def get_available_browsers(self) -> List[Dict[str, str]]:
        """获取可用的浏览器列表"""
        available = []
        for browser_id, browser_info in self.BROWSER_PATHS.items():
            history_path = self.home / browser_info["history"]
            if browser_id == "firefox":
                history_path = self._find_firefox_profile()
            
            if history_path and history_path.exists():
                available.append({
                    "id": browser_id,
                    "name": browser_info["name"],
                    "path": str(history_path)
                })
        return available
    
    def _find_firefox_profile(self) -> Optional[Path]:
        """查找Firefox配置文件"""
        firefox_profiles = self.home / "AppData/Roaming/Mozilla/Firefox/Profiles"
        if firefox_profiles.exists():
            for profile in firefox_profiles.iterdir():
                places_db = profile / "places.sqlite"
                if places_db.exists():
                    return places_db
        return None
    
    def read_history(self, browser_path: str, browser_type: str = "chrome", 
                     since: datetime = None, limit: int = 100) -> List[Dict[str, Any]]:
        """读取浏览器历史记录"""
        if not os.path.exists(browser_path):
            logger.warning(f"浏览器历史数据库不存在: {browser_path}")
            return []
        
        temp_db_path = None
        
        try:
            temp_db_path = self._copy_database_safely(browser_path)
            if not temp_db_path:
                logger.error(f"无法复制浏览器数据库: {browser_path}")
                return []
            
            records = self._query_history(temp_db_path, browser_type, since, limit)
            return records
            
        except Exception as e:
            logger.error(f"读取浏览器历史记录失败: {e}")
            return []
        finally:
            if temp_db_path and os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass
    
    def _copy_database_safely(self, db_path: str) -> Optional[str]:
        """安全复制数据库文件"""
        temp_db_path = str(db_path) + ".temp_copy"
        
        try:
            shutil.copy2(db_path, temp_db_path)
            return temp_db_path
        except Exception as e:
            logger.debug(f"标准复制失败: {e}")
        
        if WIN32_AVAILABLE:
            try:
                return self._copy_with_win32(db_path, temp_db_path)
            except Exception as e:
                logger.debug(f"Win32复制失败: {e}")
        
        return None
    
    def _copy_with_win32(self, src_path: str, dst_path: str) -> str:
        """使用Win32 API复制文件"""
        src_handle = win32file.CreateFile(
            src_path,
            win32file.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            0,
            None
        )
        
        dst_handle = win32file.CreateFile(
            dst_path,
            win32file.GENERIC_WRITE,
            0,
            None,
            win32con.CREATE_ALWAYS,
            0,
            None
        )
        
        try:
            buffer_size = 65536
            while True:
                _, data = win32file.ReadFile(src_handle, buffer_size)
                if not data:
                    break
                win32file.WriteFile(dst_handle, data)
        finally:
            win32file.CloseHandle(src_handle)
            win32file.CloseHandle(dst_handle)
        
        return dst_path
    
    def _query_history(self, db_path: str, browser_type: str, 
                       since: datetime, limit: int) -> List[Dict[str, Any]]:
        """查询历史记录"""
        records = []
        
        conn = sqlite3.connect(db_path, timeout=10.0)
        cursor = conn.cursor()
        
        try:
            if browser_type in ["chrome", "edge"]:
                records = self._query_chromium_history(cursor, since, limit)
            elif browser_type == "firefox":
                records = self._query_firefox_history(cursor, since, limit)
        except sqlite3.OperationalError as e:
            logger.warning(f"查询历史记录表结构错误: {e}")
        finally:
            conn.close()
        
        return records
    
    def _query_chromium_history(self, cursor: sqlite3.Cursor, 
                                 since: datetime, limit: int) -> List[Dict[str, Any]]:
        """查询Chrome/Edge历史记录"""
        query = '''
        SELECT url, title, last_visit_time, visit_count
        FROM urls
        ORDER BY last_visit_time DESC
        LIMIT ?
        '''
        
        cursor.execute(query, (limit * 2,))
        
        records = []
        for url, title, last_visit_time, visit_count in cursor.fetchall():
            visit_time = self._convert_chromium_time(last_visit_time)
            
            if since and visit_time < since:
                continue
            
            records.append({
                "url": url,
                "title": title or "",
                "visit_time": visit_time,
                "visit_count": visit_count,
                "browser_type": "chromium"
            })
            
            if len(records) >= limit:
                break
        
        return records
    
    def _query_firefox_history(self, cursor: sqlite3.Cursor,
                                since: datetime, limit: int) -> List[Dict[str, Any]]:
        """查询Firefox历史记录"""
        query = '''
        SELECT url, title, last_visit_date, visit_count
        FROM moz_places
        WHERE last_visit_date IS NOT NULL
        ORDER BY last_visit_date DESC
        LIMIT ?
        '''
        
        cursor.execute(query, (limit * 2,))
        
        records = []
        for url, title, last_visit_time, visit_count in cursor.fetchall():
            visit_time = self._convert_firefox_time(last_visit_time)
            
            if since and visit_time < since:
                continue
            
            records.append({
                "url": url,
                "title": title or "",
                "visit_time": visit_time,
                "visit_count": visit_count,
                "browser_type": "firefox"
            })
            
            if len(records) >= limit:
                break
        
        return records
    
    def _convert_chromium_time(self, timestamp: int) -> datetime:
        """转换Chromium时间戳"""
        if timestamp > 10000000000000000:
            return datetime(1601, 1, 1) + timedelta(microseconds=timestamp)
        return datetime.fromtimestamp(timestamp / 1000000)
    
    def _convert_firefox_time(self, timestamp: int) -> datetime:
        """转换Firefox时间戳"""
        if timestamp > 10000000000000000:
            return datetime.fromtimestamp(timestamp / 1000000)
        return datetime.fromtimestamp(timestamp)


class StayTimeTracker:
    """页面停留时间追踪器"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._active_pages: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._min_stay_time = 30
    
    def start_visit(self, url: str, title: str = "", browser_type: str = ""):
        """开始访问页面"""
        with self._lock:
            if url in self._active_pages:
                self.end_visit(url)
            
            self._active_pages[url] = {
                "title": title,
                "start_time": datetime.now(),
                "browser_type": browser_type
            }
    
    def end_visit(self, url: str) -> Optional[int]:
        """结束访问页面，返回停留时间（秒）"""
        with self._lock:
            if url not in self._active_pages:
                return None
            
            page_info = self._active_pages.pop(url)
            end_time = datetime.now()
            stay_time = int((end_time - page_info["start_time"]).total_seconds())
            
            if stay_time >= self._min_stay_time:
                self._save_visit(url, page_info, end_time, stay_time)
            
            return stay_time
    
    def _save_visit(self, url: str, page_info: Dict, end_time: datetime, stay_time: int):
        """保存访问记录"""
        try:
            self.db.execute('''
            INSERT INTO page_visits (url, visit_start, visit_end, stay_time, browser_type)
            VALUES (?, ?, ?, ?, ?)
            ''', (url, page_info["start_time"].isoformat(), 
                  end_time.isoformat(), stay_time, page_info.get("browser_type", "")))
        except Exception as e:
            logger.error(f"保存访问记录失败: {e}")
    
    def get_total_stay_time(self, url: str) -> int:
        """获取URL的总停留时间"""
        result = self.db.fetchone(
            "SELECT COALESCE(SUM(stay_time), 0) as total FROM page_visits WHERE url = ?",
            (url,)
        )
        return result["total"] if result else 0
    
    def cleanup_stale_visits(self, max_duration: int = 3600):
        """清理超时的访问记录"""
        cutoff = datetime.now() - timedelta(seconds=max_duration)
        
        with self._lock:
            stale_urls = [
                url for url, info in self._active_pages.items()
                if info["start_time"] < cutoff
            ]
            
            for url in stale_urls:
                self.end_visit(url)
                logger.debug(f"清理超时访问: {url}")


class ContentExtractor:
    """内容提取器"""
    
    STOP_WORDS = {
        "的", "了", "和", "是", "在", "我", "有", "就", "不", "人", "都", "一", "一个",
        "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
        "自己", "这", "那", "中", "他", "她", "它", "们", "这个", "那个", "什么", "怎么",
        "可以", "可能", "因为", "所以", "但是", "如果", "虽然", "或者", "而且", "以及",
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
        "may", "might", "must", "shall", "can", "need", "dare", "ought", "used",
        "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below", "between", "under",
        "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
        "not", "only", "own", "same", "than", "too", "very", "just", "also"
    }
    
    def __init__(self):
        pass
    
    def extract_web_content(self, url: str, title: str = "") -> Dict[str, Any]:
        """抓取网页内容"""
        if not REQUESTS_AVAILABLE:
            return self._create_placeholder_result(url, title, "requests模块未安装")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '')
            
            if 'text/html' not in content_type:
                return self._create_placeholder_result(
                    url, title, f"非HTML内容: {content_type}"
                )
            
            html_content = response.text
            extracted = self._extract_html_content(html_content, url)
            
            return {
                "url": url,
                "title": extracted.get("title") or title or self._extract_title(html_content),
                "content": extracted.get("content", ""),
                "summary": extracted.get("summary", ""),
                "keywords": extracted.get("keywords", []),
                "status_code": response.status_code,
                "content_type": content_type,
                "success": True
            }
            
        except requests.exceptions.Timeout:
            return self._create_placeholder_result(url, title, "请求超时")
        except requests.exceptions.ConnectionError:
            return self._create_placeholder_result(url, title, "连接错误")
        except requests.exceptions.HTTPError as e:
            return self._create_placeholder_result(url, title, f"HTTP错误: {e}")
        except Exception as e:
            return self._create_placeholder_result(url, title, f"抓取失败: {str(e)}")
    
    def _create_placeholder_result(self, url: str, title: str, error: str) -> Dict[str, Any]:
        """创建占位结果"""
        return {
            "url": url,
            "title": title or url,
            "content": f"[内容获取失败: {error}]",
            "summary": f"无法获取内容 - {error}",
            "keywords": [],
            "success": False,
            "error": error
        }
    
    def _extract_html_content(self, html: str, url: str) -> Dict[str, Any]:
        """提取HTML内容"""
        result = {
            "title": "",
            "content": "",
            "summary": "",
            "keywords": []
        }
        
        if BS4_AVAILABLE:
            return self._extract_with_beautifulsoup(html, url)
        
        return self._extract_with_regex(html, url)
    
    def _extract_with_beautifulsoup(self, html: str, url: str) -> Dict[str, Any]:
        """使用BeautifulSoup提取内容"""
        try:
            soup = bs4.BeautifulSoup(html, 'html.parser')
            
            for tag in ["script", "style", "nav", "footer", "header", "aside",
                       "iframe", "noscript", "svg", "form"]:
                for element in soup.find_all(tag):
                    element.decompose()
            
            for class_pattern in ["nav", "footer", "header", "sidebar", "ad", "ads",
                                  "advertisement", "banner", "popup", "modal", "cookie",
                                  "newsletter", "social", "share", "comment", "related",
                                  "recommend", "widget", "menu"]:
                for element in soup.find_all(class_=re.compile(class_pattern, re.I)):
                    element.decompose()
            
            title = ""
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()
            
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content']
            
            content = ""
            selectors = [
                'article', 'main', '[role="main"]',
                '.article-content', '.post-content', '.entry-content',
                '.content', '#content', '.post-body', '.article-body',
                '.story-content', '.text-content', '.main-content',
                '.page-content', '.article-text', '.blog-content'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    texts = []
                    for elem in elements:
                        text = elem.get_text(separator=' ', strip=True)
                        if text and len(text) > 100:
                            texts.append(text)
                    if texts:
                        content = "\n\n".join(texts)
                        break
            
            if not content:
                paragraphs = soup.find_all(['p', 'div'])
                texts = []
                for p in paragraphs:
                    text = p.get_text(separator=' ', strip=True)
                    if len(text) > 50 and len(text) < 5000:
                        texts.append(text)
                
                if texts:
                    texts.sort(key=len, reverse=True)
                    content = "\n\n".join(texts[:15])
            
            content = re.sub(r'\s+', ' ', content).strip()
            content = re.sub(r'\n\s*\n+', '\n\n', content)
            
            if len(content) > 15000:
                content = content[:15000] + "..."
            
            keywords = self._extract_keywords(title + " " + content)
            summary = self._generate_summary(content)
            
            return {
                "title": title,
                "content": content,
                "summary": summary,
                "keywords": keywords
            }
            
        except Exception as e:
            logger.error(f"BeautifulSoup解析失败: {e}")
            return self._extract_with_regex(html, url)
    
    def _extract_with_regex(self, html: str, url: str) -> Dict[str, Any]:
        """使用正则表达式提取内容"""
        try:
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
            
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ""
            
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            
            if len(text) > 10000:
                text = text[:10000] + "..."
            
            keywords = self._extract_keywords(title + " " + text)
            summary = text[:300] + "..." if len(text) > 300 else text
            
            return {
                "title": title,
                "content": text,
                "summary": summary,
                "keywords": keywords
            }
            
        except Exception as e:
            logger.error(f"正则提取失败: {e}")
            return {
                "title": "",
                "content": f"[内容提取失败: {url}]",
                "summary": "",
                "keywords": []
            }
    
    def _extract_title(self, html: str) -> str:
        """提取标题"""
        if BS4_AVAILABLE:
            try:
                soup = bs4.BeautifulSoup(html, 'html.parser')
                title_tag = soup.find('title')
                return title_tag.get_text().strip() if title_tag else "无标题"
            except Exception:
                pass
        
        match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if match:
            return re.sub(r'<[^>]+>', '', match.group(1)).strip()
        return "无标题"
    
    def _extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """提取关键词"""
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}|[a-zA-Z]{3,}', text.lower())
        
        filtered = [w for w in words if w not in self.STOP_WORDS]
        
        counter = Counter(filtered)
        return [word for word, _ in counter.most_common(max_keywords)]
    
    def _generate_summary(self, content: str, max_length: int = 300) -> str:
        """生成摘要"""
        if len(content) <= max_length:
            return content
        
        sentences = re.split(r'[。！？.!?]', content)
        
        summary = ""
        for sentence in sentences:
            if len(summary) + len(sentence) > max_length:
                break
            if sentence.strip():
                summary += sentence.strip() + "。"
        
        return summary.strip() or content[:max_length] + "..."
    
    def extract_pdf_content(self, file_path: str) -> Dict[str, Any]:
        """提取PDF内容"""
        if not PDFPLUMBER_AVAILABLE:
            return {
                "content": f"[PDF解析需要pdfplumber模块: {Path(file_path).name}]",
                "success": False,
                "error": "pdfplumber未安装"
            }
        
        try:
            content_parts = []
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages[:20]):
                    text = page.extract_text()
                    if text:
                        content_parts.append(text)
            
            content = "\n\n".join(content_parts)
            
            if len(content) > 20000:
                content = content[:20000] + "..."
            
            keywords = self._extract_keywords(content)
            summary = self._generate_summary(content)
            
            return {
                "content": content,
                "keywords": keywords,
                "summary": summary,
                "page_count": len(pdf.pages),
                "success": True
            }
            
        except Exception as e:
            logger.error(f"PDF解析失败 {file_path}: {e}")
            return {
                "content": f"[PDF解析失败: {str(e)}]",
                "success": False,
                "error": str(e)
            }
    
    def extract_text_content(self, file_path: str) -> Dict[str, Any]:
        """提取文本文件内容"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'latin-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read(20000)
                
                keywords = self._extract_keywords(content)
                summary = self._generate_summary(content)
                
                return {
                    "content": content,
                    "keywords": keywords,
                    "summary": summary,
                    "encoding": encoding,
                    "success": True
                }
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error(f"读取文本文件失败 {file_path}: {e}")
                return {
                    "content": f"[文件读取失败: {str(e)}]",
                    "success": False,
                    "error": str(e)
                }
        
        return {
            "content": "[无法识别文件编码]",
            "success": False,
            "error": "编码识别失败"
        }


class ContentClassifier:
    """内容分类器"""
    
    DEFAULT_CATEGORIES = {
        "技术": ["python", "编程", "开发", "技术", "代码", "AI", "人工智能", 
                "机器学习", "深度学习", "算法", "数据结构", "前端", "后端",
                "数据库", "API", "框架", "开源", "GitHub", "Stack Overflow"],
        "工作": ["项目", "工作", "会议", "报告", "周报", "计划", "任务",
                "团队", "协作", "管理", "进度", "需求", "测试", "部署"],
        "学习": ["教程", "学习", "课程", "教育", "读书", "阅读", "培训",
                "笔记", "知识", "技能", "练习", "考试", "认证"],
        "生活": ["生活", "健康", "旅行", "美食", "娱乐", "家庭", "运动",
                "购物", "美食", "电影", "音乐", "游戏"],
        "财经": ["财经", "投资", "股票", "理财", "经济", "金融", "基金",
                "银行", "保险", "税务", "财务", "交易"],
        "新闻": ["新闻", "热点", "事件", "政治", "社会", "国际", "国内",
                "报道", "媒体", "记者"],
        "产品": ["产品", "设计", "用户体验", "UX", "UI", "原型", "需求",
                "功能", "迭代", "版本", "发布"]
    }
    
    def __init__(self, categories: Dict[str, List[str]] = None):
        self.categories = categories or self.DEFAULT_CATEGORIES.copy()
        self._build_keyword_index()
    
    def _build_keyword_index(self):
        """构建关键词索引"""
        self._keyword_to_category: Dict[str, str] = {}
        for category, keywords in self.categories.items():
            for keyword in keywords:
                self._keyword_to_category[keyword.lower()] = category
    
    def classify(self, title: str, content: str, keywords: List[str] = None) -> Tuple[List[str], float]:
        """分类内容"""
        text = (title + " " + content).lower()
        
        scores: Dict[str, int] = Counter()
        
        for keyword, category in self._keyword_to_category.items():
            if keyword in text:
                scores[category] += 1
        
        if keywords:
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in self._keyword_to_category:
                    scores[self._keyword_to_category[keyword_lower]] += 2
        
        if not scores:
            return ["未分类"], 0.0
        
        max_score = max(scores.values())
        total_score = sum(scores.values())
        
        threshold = max(1, max_score * 0.5)
        matched_categories = [cat for cat, score in scores.items() if score >= threshold]
        
        matched_categories.sort(key=lambda x: scores[x], reverse=True)
        
        confidence = max_score / (total_score + 1) if total_score > 0 else 0.0
        
        return matched_categories[:3], confidence
    
    def add_category(self, category: str, keywords: List[str]):
        """添加分类"""
        if category not in self.categories:
            self.categories[category] = []
        
        for keyword in keywords:
            if keyword not in self.categories[category]:
                self.categories[category].append(keyword)
                self._keyword_to_category[keyword.lower()] = category
    
    def get_categories(self) -> Dict[str, List[str]]:
        """获取所有分类"""
        return self.categories.copy()


class KnowledgeBaseBuilder:
    """个人知识库自动构建模块
    
    功能：
    1. 监控浏览器历史记录和下载文件夹
    2. 检测页面停留时间（可配置阈值）
    3. 自动抓取链接、标题、摘要
    4. 智能分类和关键词提取
    5. 支持导出和备份
    """
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.monitoring_enabled = False
        self.monitoring_thread = None
        self._stop_event = threading.Event()
        
        self.download_folders: List[str] = []
        self.browser_history_paths: List[str] = []
        self.min_stay_time = 120
        self.notion_config: Dict[str, Any] = {}
        self.monitor_interval = 60
        self.max_content_length = 15000
        
        self._init_paths()
        
        self.db: Optional[DatabaseManager] = None
        self.browser_reader: Optional[BrowserHistoryReader] = None
        self.stay_tracker: Optional[StayTimeTracker] = None
        self.content_extractor: Optional[ContentExtractor] = None
        self.classifier: Optional[ContentClassifier] = None
        
        self._init_components()
        self._load_config()
        
        self._status_callbacks: List[Callable] = []
        self._last_check_time: Dict[str, datetime] = {}
    
    def _init_paths(self):
        """初始化路径"""
        self.config_dir = Path(__file__).parent.parent / "knowledge_base" / "config"
        self.data_dir = Path(__file__).parent.parent / "knowledge_base" / "data"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_components(self):
        """初始化组件"""
        db_path = self.data_dir / "knowledge_base.db"
        self.db = DatabaseManager(str(db_path))
        
        self.browser_reader = BrowserHistoryReader()
        self.stay_tracker = StayTimeTracker(self.db)
        self.content_extractor = ContentExtractor()
        self.classifier = ContentClassifier()
    
    def _load_config(self):
        """加载配置"""
        config_file = self.config_dir / "knowledge_base_config.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.download_folders = config.get("download_folders", self._get_default_download_folders())
                self.browser_history_paths = config.get("browser_history_paths", [])
                self.min_stay_time = config.get("min_stay_time", 120)
                self.notion_config = config.get("notion", {})
                self.monitor_interval = config.get("monitor_interval", 60)
                self.max_content_length = config.get("max_content_length", 15000)
                
                categories_file = self.config_dir / "categories.json"
                if categories_file.exists():
                    with open(categories_file, 'r', encoding='utf-8') as f:
                        categories = json.load(f)
                    self.classifier = ContentClassifier(categories)
                
                logger.info("知识库配置加载成功")
                
            except Exception as e:
                logger.error(f"加载知识库配置失败: {e}")
                self._set_default_config()
        else:
            self._set_default_config()
            self._save_config()
    
    def _get_default_download_folders(self) -> List[str]:
        """获取默认下载文件夹"""
        return [
            str(Path.home() / "Downloads"),
            str(Path.home() / "Desktop")
        ]
    
    def _set_default_config(self):
        """设置默认配置"""
        self.download_folders = self._get_default_download_folders()
        self.browser_history_paths = []
        self.min_stay_time = 120
        self.notion_config = {
            "enabled": False,
            "api_key": "",
            "database_id": "",
            "sync_interval": 300
        }
        self.monitor_interval = 60
        self.max_content_length = 15000
        self.classifier = ContentClassifier()
    
    def _save_config(self):
        """保存配置"""
        try:
            config = {
                "download_folders": self.download_folders,
                "browser_history_paths": self.browser_history_paths,
                "min_stay_time": self.min_stay_time,
                "notion": self.notion_config,
                "monitor_interval": self.monitor_interval,
                "max_content_length": self.max_content_length
            }
            
            config_file = self.config_dir / "knowledge_base_config.json"
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            categories_file = self.config_dir / "categories.json"
            with open(categories_file, 'w', encoding='utf-8') as f:
                json.dump(self.classifier.get_categories(), f, ensure_ascii=False, indent=2)
            
            logger.info("知识库配置保存成功")
        except Exception as e:
            logger.error(f"保存知识库配置失败: {e}")
    
    def add_status_callback(self, callback: Callable):
        """添加状态回调函数"""
        self._status_callbacks.append(callback)
    
    def _notify_status(self, message: str, level: str = "info"):
        """通知状态更新"""
        for callback in self._status_callbacks:
            try:
                callback(message, level)
            except Exception as e:
                logger.error(f"状态回调失败: {e}")
    
    def start_monitoring(self) -> bool:
        """开始监控"""
        if self.monitoring_enabled:
            logger.warning("监控已在运行中")
            return False
        
        self.monitoring_enabled = True
        self._stop_event.clear()
        
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="KnowledgeBaseMonitor"
        )
        self.monitoring_thread.start()
        
        self._notify_status("知识库监控已启动", "info")
        logger.info("知识库监控已启动")
        return True
    
    def stop_monitoring(self) -> bool:
        """停止监控"""
        if not self.monitoring_enabled:
            return True
        
        self.monitoring_enabled = False
        self._stop_event.set()
        
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=10)
        
        self._notify_status("知识库监控已停止", "info")
        logger.info("知识库监控已停止")
        return True
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.monitoring_enabled and not self._stop_event.is_set():
            try:
                self._monitor_browser_history()
                self._monitor_downloads()
                self._process_pending_records()
                self._cleanup_old_data()
                
                if self.notion_config.get("enabled") and NOTION_AVAILABLE:
                    self._sync_to_notion()
                
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                self._notify_status(f"监控出错: {e}", "error")
            
            self._stop_event.wait(self.monitor_interval)
    
    def _monitor_browser_history(self):
        """监控浏览器历史记录"""
        browsers = self.browser_reader.get_available_browsers()
        
        for browser in browsers:
            try:
                since = self._last_check_time.get(browser["id"])
                if since is None:
                    since = datetime.now() - timedelta(hours=1)
                
                records = self.browser_reader.read_history(
                    browser["path"],
                    browser["id"],
                    since=since,
                    limit=50
                )
                
                for record in records:
                    self._save_browser_history(
                        record["url"],
                        record["title"],
                        record["visit_time"],
                        record["visit_count"],
                        browser["id"]
                    )
                
                self._last_check_time[browser["id"]] = datetime.now()
                
                if records:
                    logger.debug(f"从{browser['name']}读取{len(records)}条历史记录")
                    
            except Exception as e:
                logger.error(f"读取{browser['name']}历史记录失败: {e}")
    
    def _save_browser_history(self, url: str, title: str, visit_time: datetime,
                              visit_count: int, browser_type: str):
        """保存浏览器历史记录"""
        try:
            existing = self.db.fetchone(
                "SELECT id, visit_count FROM browser_history WHERE url = ? ORDER BY visit_time DESC LIMIT 1",
                (url,)
            )
            
            if existing:
                self.db.execute('''
                UPDATE browser_history 
                SET visit_time = ?, visit_count = ?, processed = FALSE
                WHERE id = ?
                ''', (visit_time.isoformat(), visit_count, existing["id"]))
            else:
                self.db.execute('''
                INSERT INTO browser_history (url, title, visit_time, stay_time, browser_type, processed)
                VALUES (?, ?, ?, ?, ?, FALSE)
                ''', (url, title, visit_time.isoformat(), 0, browser_type))
                
        except Exception as e:
            logger.error(f"保存浏览器历史记录失败: {e}")
    
    def _monitor_downloads(self):
        """监控下载文件夹"""
        for folder_path in self.download_folders:
            if not os.path.exists(folder_path):
                continue
            
            try:
                self._scan_download_folder(folder_path)
            except Exception as e:
                logger.error(f"扫描下载文件夹失败 {folder_path}: {e}")
    
    def _scan_download_folder(self, folder_path: str):
        """扫描下载文件夹"""
        folder = Path(folder_path)
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for file_path in folder.glob("*"):
            if not file_path.is_file():
                continue
            
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                
                if mtime < cutoff_time:
                    continue
                
                existing = self.db.fetchone(
                    "SELECT id FROM downloads WHERE file_path = ?",
                    (str(file_path),)
                )
                
                if existing:
                    continue
                
                file_type = mimetypes.guess_type(str(file_path))[0] or "unknown"
                
                self.db.execute('''
                INSERT INTO downloads (file_path, file_name, file_type, file_size, download_time, processed)
                VALUES (?, ?, ?, ?, ?, FALSE)
                ''', (
                    str(file_path),
                    file_path.name,
                    file_type,
                    file_path.stat().st_size,
                    mtime.isoformat()
                ))
                
                logger.debug(f"发现新下载文件: {file_path.name}")
                
            except Exception as e:
                logger.error(f"处理文件失败 {file_path}: {e}")
    
    def _process_pending_records(self):
        """处理未处理的记录"""
        self._process_pending_browser_history()
        self._process_pending_downloads()
    
    def _process_pending_browser_history(self):
        """处理待处理的浏览器历史记录"""
        records = self.db.fetchall('''
        SELECT id, url, title, visit_count
        FROM browser_history 
        WHERE processed = FALSE
        ORDER BY visit_time DESC
        LIMIT 20
        ''')
        
        for record in records:
            try:
                url = record["url"]
                title = record["title"] or ""
                
                if self._should_skip_url(url):
                    self.db.execute("UPDATE browser_history SET processed = TRUE WHERE id = ?", (record["id"],))
                    continue
                
                total_stay_time = self.stay_tracker.get_total_stay_time(url)
                
                if total_stay_time < self.min_stay_time and record["visit_count"] < 3:
                    self.db.execute("UPDATE browser_history SET processed = TRUE WHERE id = ?", (record["id"],))
                    continue
                
                article_data = self.content_extractor.extract_web_content(url, title)
                
                if article_data.get("success", False):
                    categories, confidence = self.classifier.classify(
                        article_data["title"],
                        article_data["content"],
                        article_data.get("keywords", [])
                    )
                    
                    article_data["categories"] = categories
                    article_data["confidence"] = confidence
                    article_data["total_stay_time"] = total_stay_time
                    
                    self._save_article(article_data, "web")
                    
                    self._notify_status(f"已收录: {article_data['title'][:30]}...", "success")
                
                self.db.execute("UPDATE browser_history SET processed = TRUE WHERE id = ?", (record["id"],))
                
            except Exception as e:
                logger.error(f"处理历史记录失败: {e}")
                self.db.execute("UPDATE browser_history SET processed = TRUE WHERE id = ?", (record["id"],))
    
    def _process_pending_downloads(self):
        """处理待处理的下载文件"""
        records = self.db.fetchall('''
        SELECT id, file_path, file_name, file_type
        FROM downloads 
        WHERE processed = FALSE 
        AND file_type IN ('application/pdf', 'text/plain', 'text/markdown', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        ORDER BY download_time DESC
        LIMIT 10
        ''')
        
        for record in records:
            try:
                file_path = record["file_path"]
                file_name = record["file_name"]
                file_type = record["file_type"]
                
                if not os.path.exists(file_path):
                    self.db.execute("UPDATE downloads SET processed = TRUE WHERE id = ?", (record["id"],))
                    continue
                
                content_data = self._extract_file_content(file_path, file_type)
                
                if content_data.get("success", False):
                    categories, confidence = self.classifier.classify(
                        file_name,
                        content_data["content"],
                        content_data.get("keywords", [])
                    )
                    
                    article_data = {
                        "url": f"file://{file_path}",
                        "title": file_name,
                        "content": content_data["content"],
                        "summary": content_data.get("summary", ""),
                        "keywords": content_data.get("keywords", []),
                        "categories": categories,
                        "confidence": confidence,
                        "file_path": file_path,
                        "file_type": file_type,
                        "file_size": os.path.getsize(file_path)
                    }
                    
                    self._save_article(article_data, "file")
                    self._notify_status(f"已收录文件: {file_name}", "success")
                
                self.db.execute("UPDATE downloads SET processed = TRUE WHERE id = ?", (record["id"],))
                
            except Exception as e:
                logger.error(f"处理下载文件失败: {e}")
                self.db.execute("UPDATE downloads SET processed = TRUE WHERE id = ?", (record["id"],))
    
    def _should_skip_url(self, url: str) -> bool:
        """判断是否应该跳过URL"""
        skip_patterns = [
            r'^chrome://',
            r'^edge://',
            r'^about:',
            r'^file://',
            r'localhost',
            r'127\.0\.0\.1',
            r'\.pdf$',
            r'\.zip$',
            r'\.exe$',
            r'\.dmg$',
            r'google\.com/search',
            r'bing\.com/search',
            r'baidu\.com/s\?',
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False
    
    def _extract_file_content(self, file_path: str, file_type: str) -> Dict[str, Any]:
        """提取文件内容"""
        if file_type == 'application/pdf':
            return self.content_extractor.extract_pdf_content(file_path)
        else:
            return self.content_extractor.extract_text_content(file_path)
    
    def _save_article(self, article_data: Dict[str, Any], source_type: str):
        """保存文章到知识库（使用原子性操作）"""
        try:
            url = article_data.get("url", "")
            title = article_data.get("title", "")
            content = article_data.get("content", "")[:self.max_content_length]
            summary = article_data.get("summary", "")
            categories = json.dumps(article_data.get("categories", []), ensure_ascii=False)
            keywords = json.dumps(article_data.get("keywords", []), ensure_ascii=False)
            total_stay_time = article_data.get("total_stay_time", 0)
            file_path = article_data.get("file_path")
            file_size = article_data.get("file_size")
            
            # 使用 INSERT ... ON CONFLICT DO UPDATE 保证原子性
            # SQLite 3.24+ 支持 ON CONFLICT 子句
            self.db.execute('''
            INSERT INTO articles (url, title, content, summary, categories, keywords, 
                                 source_type, file_path, file_size, total_stay_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                summary = excluded.summary,
                categories = excluded.categories,
                keywords = excluded.keywords,
                total_stay_time = total_stay_time + excluded.total_stay_time,
                visit_count = visit_count + 1,
                updated_at = CURRENT_TIMESTAMP
            ''', (url, title, content, summary, categories, keywords,
                  source_type, file_path, file_size, total_stay_time))
            
            logger.info(f"保存文章: {title[:50]}")
            
        except Exception as e:
            logger.error(f"保存文章失败: {e}")
    
    def _cleanup_old_data(self):
        """清理旧数据"""
        try:
            cutoff = datetime.now() - timedelta(days=30)
            
            self.db.execute(
                "DELETE FROM browser_history WHERE processed = TRUE AND visit_time < ?",
                (cutoff.isoformat(),)
            )
            
            self.db.execute(
                "DELETE FROM downloads WHERE processed = TRUE AND download_time < ?",
                (cutoff.isoformat(),)
            )
            
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")
    
    def _sync_to_notion(self):
        """同步到Notion"""
        if not NOTION_AVAILABLE or not self.notion_config.get("enabled"):
            return
        
        api_key = self.notion_config.get("api_key")
        database_id = self.notion_config.get("database_id")
        
        if not api_key or not database_id:
            return
        
        try:
            notion = Client(auth=api_key)
            
            articles = self.db.fetchall('''
            SELECT a.id, a.url, a.title, a.content, a.summary, a.categories, a.source_type, a.created_at
            FROM articles a
            LEFT JOIN notion_sync n ON a.id = n.article_id
            WHERE n.id IS NULL
            LIMIT 10
            ''')
            
            for article in articles:
                try:
                    categories = json.loads(article["categories"]) if article["categories"] else []
                    
                    page_properties = {
                        "标题": {"title": [{"text": {"content": article["title"] or "无标题"}}]},
                        "URL": {"url": article["url"]},
                        "摘要": {"rich_text": [{"text": {"content": (article["summary"] or "")[:2000]}}]},
                        "分类": {"multi_select": [{"name": cat} for cat in categories[:3]]},
                        "来源": {"select": {"name": article["source_type"] or "web"}},
                    }
                    
                    response = notion.pages.create(
                        parent={"database_id": database_id},
                        properties=page_properties
                    )
                    
                    notion_id = response.get("id")
                    if notion_id:
                        self.db.execute(
                            "INSERT INTO notion_sync (article_id, notion_id, sync_status) VALUES (?, ?, 'success')",
                            (article["id"], notion_id)
                        )
                        logger.info(f"已同步到Notion: {article['title']}")
                    
                except Exception as e:
                    logger.error(f"同步单篇文章到Notion失败: {e}")
                    self.db.execute(
                        "INSERT INTO notion_sync (article_id, notion_id, sync_status, error_message) VALUES (?, NULL, 'failed', ?)",
                        (article["id"], str(e)[:500])
                    )
                    
        except Exception as e:
            logger.error(f"Notion同步失败: {e}")
    
    def search(self, query: str, category: str = None, source_type: str = None,
               limit: int = 20) -> List[Dict[str, Any]]:
        """搜索知识库"""
        conditions = ["(title LIKE ? OR content LIKE ? OR summary LIKE ?)"]
        params = [f"%{query}%", f"%{query}%", f"%{query}%"]
        
        if category:
            conditions.append("categories LIKE ?")
            params.append(f"%{category}%")
        
        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        
        params.append(limit)
        
        sql = f'''
        SELECT url, title, summary, categories, keywords, source_type, 
               visit_count, total_stay_time, created_at
        FROM articles
        WHERE {' AND '.join(conditions)}
        ORDER BY visit_count DESC, total_stay_time DESC, created_at DESC
        LIMIT ?
        '''
        
        results = []
        for row in self.db.fetchall(sql, tuple(params)):
            results.append({
                "url": row["url"],
                "title": row["title"],
                "summary": row["summary"],
                "categories": json.loads(row["categories"]) if row["categories"] else [],
                "keywords": json.loads(row["keywords"]) if row["keywords"] else [],
                "source_type": row["source_type"],
                "visit_count": row["visit_count"],
                "stay_time": row["total_stay_time"],
                "created_at": row["created_at"]
            })
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        stats = {}
        
        total = self.db.fetchone("SELECT COUNT(*) as count FROM articles")
        stats["total_articles"] = total["count"] if total else 0
        
        web_count = self.db.fetchone("SELECT COUNT(*) as count FROM articles WHERE source_type = 'web'")
        stats["web_articles"] = web_count["count"] if web_count else 0
        
        file_count = self.db.fetchone("SELECT COUNT(*) as count FROM articles WHERE source_type = 'file'")
        stats["file_articles"] = file_count["count"] if file_count else 0
        
        categories_rows = self.db.fetchall("SELECT categories FROM articles WHERE categories IS NOT NULL")
        category_counter = Counter()
        for row in categories_rows:
            try:
                cats = json.loads(row["categories"])
                category_counter.update(cats)
            except Exception:
                pass
        
        stats["category_distribution"] = dict(category_counter.most_common(10))
        stats["monitoring_enabled"] = self.monitoring_enabled
        
        recent = self.db.fetchone('''
        SELECT COUNT(*) as count FROM articles 
        WHERE created_at >= datetime('now', '-7 days')
        ''')
        stats["recent_articles"] = recent["count"] if recent else 0
        
        return stats
    
    def export_data(self, output_path: str = None, format: str = "json",
                    category: str = None, days: int = None) -> str:
        """导出知识库数据"""
        conditions = []
        params = []
        
        if category:
            conditions.append("categories LIKE ?")
            params.append(f"%{category}%")
        
        if days:
            conditions.append("created_at >= datetime('now', ?)")
            params.append(f"-{days} days")
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        articles = self.db.fetchall(f'''
        SELECT url, title, content, summary, categories, keywords, 
               source_type, file_path, visit_count, total_stay_time, created_at
        FROM articles
        {where_clause}
        ORDER BY created_at DESC
        ''', tuple(params))
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(self.data_dir / f"export_{timestamp}.{format}")
        
        if format == "json":
            data = []
            for row in articles:
                data.append({
                    "url": row["url"],
                    "title": row["title"],
                    "content": row["content"],
                    "summary": row["summary"],
                    "categories": json.loads(row["categories"]) if row["categories"] else [],
                    "keywords": json.loads(row["keywords"]) if row["keywords"] else [],
                    "source_type": row["source_type"],
                    "visit_count": row["visit_count"],
                    "stay_time": row["total_stay_time"],
                    "created_at": row["created_at"]
                })
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        elif format == "csv":
            import csv
            with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["标题", "URL", "分类", "摘要", "来源", "访问次数", "停留时间", "创建时间"])
                
                for row in articles:
                    writer.writerow([
                        row["title"],
                        row["url"],
                        ", ".join(json.loads(row["categories"]) if row["categories"] else []),
                        row["summary"],
                        row["source_type"],
                        row["visit_count"],
                        row["total_stay_time"],
                        row["created_at"]
                    ])
        
        elif format == "markdown":
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("# 知识库导出\n\n")
                f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"共 {len(articles)} 条记录\n\n")
                f.write("---\n\n")
                
                for i, row in enumerate(articles, 1):
                    categories = json.loads(row["categories"]) if row["categories"] else []
                    f.write(f"## {i}. {row['title']}\n\n")
                    f.write(f"- **URL**: {row['url']}\n")
                    f.write(f"- **分类**: {', '.join(categories)}\n")
                    f.write(f"- **来源**: {row['source_type']}\n")
                    f.write(f"- **访问次数**: {row['visit_count']}\n")
                    f.write(f"- **创建时间**: {row['created_at']}\n\n")
                    if row["summary"]:
                        f.write(f"**摘要**: {row['summary']}\n\n")
                    f.write("---\n\n")
        
        logger.info(f"导出完成: {output_path}")
        return output_path
    
    def backup_database(self, backup_path: str = None) -> str:
        """备份数据库"""
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = str(self.data_dir / f"backup_{timestamp}.db")
        
        db_path = self.data_dir / "knowledge_base.db"
        
        if db_path.exists():
            shutil.copy2(str(db_path), backup_path)
            logger.info(f"数据库备份完成: {backup_path}")
        
        return backup_path
    
    def manual_save(self, url: str = None, file_path: str = None, 
                    title: str = "", content: str = "") -> Dict[str, Any]:
        """手动保存内容到知识库"""
        article_data = None
        source_type = "manual"
        
        if url:
            article_data = self.content_extractor.extract_web_content(url, title)
            source_type = "web"
        elif file_path and os.path.exists(file_path):
            file_type = mimetypes.guess_type(file_path)[0] or "unknown"
            content_data = self._extract_file_content(file_path, file_type)
            
            article_data = {
                "url": f"file://{file_path}",
                "title": title or Path(file_path).name,
                "content": content_data.get("content", ""),
                "summary": content_data.get("summary", ""),
                "keywords": content_data.get("keywords", []),
                "file_path": file_path,
                "file_type": file_type,
                "file_size": os.path.getsize(file_path),
                "success": content_data.get("success", False)
            }
            source_type = "file"
        elif content:
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            article_data = {
                "url": f"manual:{content_hash}",
                "title": title or "手动保存内容",
                "content": content,
                "summary": content[:200] + "..." if len(content) > 200 else content,
                "keywords": self.content_extractor._extract_keywords(content),
                "success": True
            }
        else:
            return {"success": False, "error": "必须提供url、file_path或content"}
        
        if article_data.get("success", False):
            categories, confidence = self.classifier.classify(
                article_data["title"],
                article_data["content"],
                article_data.get("keywords", [])
            )
            
            article_data["categories"] = categories
            article_data["confidence"] = confidence
            
            self._save_article(article_data, source_type)
            
            return {
                "success": True,
                "title": article_data.get("title"),
                "summary": article_data.get("summary"),
                "categories": categories,
                "saved_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": article_data.get("error", "内容提取失败")
            }
    
    def add_category(self, category: str, keywords: List[str]):
        """添加自定义分类"""
        self.classifier.add_category(category, keywords)
        self._save_config()
    
    def get_categories(self) -> Dict[str, List[str]]:
        """获取所有分类"""
        return self.classifier.get_categories()
    
    def delete_article(self, url: str) -> bool:
        """删除文章"""
        try:
            self.db.execute("DELETE FROM articles WHERE url = ?", (url,))
            self.db.execute("DELETE FROM notion_sync WHERE article_id NOT IN (SELECT id FROM articles)")
            return True
        except Exception as e:
            logger.error(f"删除文章失败: {e}")
            return False
    
    def close(self):
        """关闭资源"""
        self.stop_monitoring()
        if self.db:
            self.db.close()
