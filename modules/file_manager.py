import os
import shutil
from pathlib import Path
from collections import defaultdict
import hashlib
import logging

logger = logging.getLogger("FileManager")

class FileManager:
    """文件管理模块"""
    
    # 安全路径白名单
    SAFE_DIRS = [
        str(Path.home() / "Desktop"),
        str(Path.home() / "Documents"),
        str(Path.home() / "Downloads"),
        str(Path.home() / "Pictures"),
        str(Path.home() / "Music"),
        str(Path.home() / "Videos"),
    ]
    
    # 最大遍历深度
    MAX_DEPTH = 10
    
    def __init__(self):
        self.file_types = {
            "图片": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".ico"],
            "文档": [".txt", ".doc", ".docx", ".pdf", ".epub", ".mobi", ".rtf", ".wps"],
            "表格": [".xls", ".xlsx", ".csv", ".tsv", ".ods"],
            "演示文稿": [".ppt", ".pptx", ".keynote", ".odp"],
            "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".iso", ".cab"],
            "安装包": [".exe", ".msi", ".pkg", ".dmg", ".deb", ".rpm"],
            "视频": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".mpeg", ".mpg", ".webm"],
            "音频": [".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac"],
            "代码": [".py", ".java", ".cpp", ".c", ".h", ".js", ".html", ".css", ".php", ".go", ".rs"],
            "快捷方式": [".lnk", ".url"]
        }
        self.rename_history = []
    
    def _is_safe_path(self, folder: str) -> bool:
        """检查路径是否在安全白名单内"""
        try:
            folder_path = Path(folder).resolve()
            for safe_dir in self.SAFE_DIRS:
                safe_path = Path(safe_dir).resolve()
                try:
                    folder_path.relative_to(safe_path)
                    return True
                except ValueError:
                    continue
            return False
        except Exception as e:
            logger.error(f"路径安全检查失败: {e}")
            return False
    
    def _is_system_dir(self, path: str) -> bool:
        """判断是否为系统目录"""
        path = os.path.realpath(path).lower()
        system_roots = [
            "c:\\windows", "c:\\program files", "c:\\program files (x86)",
            "c:\\system volume information", "c:\\recovery"
        ]
        return any(path.startswith(root) for root in system_roots)
    
    def auto_sort_files(self, current_folder, target_base, ai_helper=None):
        """按类型整理文件"""
        try:
            # 安全检查
            if not self._is_safe_path(current_folder):
                raise ValueError(f"目录 {current_folder} 不在安全白名单范围内")
            if not self._is_safe_path(target_base):
                raise ValueError(f"目标目录 {target_base} 不在安全白名单范围内")
            if self._is_system_dir(current_folder) or self._is_system_dir(target_base):
                raise ValueError("禁止操作系统目录")
            
            move_plan = []
            unknown_files = []
            
            # 使用深度限制的遍历
            for root, dirs, files in os.walk(current_folder, topdown=True):
                # 计算当前深度
                rel_path = os.path.relpath(root, current_folder)
                current_depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
                
                # 超过最大深度则跳过
                if current_depth > self.MAX_DEPTH:
                    logger.warning(f"达到最大遍历深度 {self.MAX_DEPTH}，跳过: {root}")
                    dirs.clear()  # 清空 dirs 阻止进一步遍历
                    continue
                
                for file in files:
                    src = os.path.join(root, file)
                    ext = os.path.splitext(file)[1].lower()
                    file_type = "其他文件"
                    found = False
                    for type_name, exts in self.file_types.items():
                        if ext in exts:
                            file_type = type_name
                            found = True
                            break
                    if not found:
                        unknown_files.append((src, file))
                    else:
                        dst_dir = os.path.join(target_base, file_type)
                        dst = os.path.join(dst_dir, file)
                        base, ext = os.path.splitext(dst)
                        counter = 1
                        while os.path.exists(dst):
                            dst = f"{base}_{counter}{ext}"
                            counter += 1
                        move_plan.append((src, dst))
            
            if ai_helper and unknown_files:
                for src, file in unknown_files:
                    category = ai_helper.classify_file(file, list(self.file_types.keys()))
                    if category and category in self.file_types:
                        dst_dir = os.path.join(target_base, category)
                    else:
                        dst_dir = os.path.join(target_base, "其他文件")
                    dst = os.path.join(dst_dir, file)
                    base, ext = os.path.splitext(dst)
                    counter = 1
                    while os.path.exists(dst):
                        dst = f"{base}_{counter}{ext}"
                        counter += 1
                    move_plan.append((src, dst))
            else:
                for src, file in unknown_files:
                    dst_dir = os.path.join(target_base, "其他文件")
                    dst = os.path.join(dst_dir, file)
                    base, ext = os.path.splitext(dst)
                    counter = 1
                    while os.path.exists(dst):
                        dst = f"{base}_{counter}{ext}"
                        counter += 1
                    move_plan.append((src, dst))
            
            return move_plan
        except Exception as e:
            raise Exception(f"按类型整理失败: {e}")
    
    def safe_move(self, src, dst):
        """安全移动文件"""
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            self.rename_history.append((src, dst))
            return True
        except Exception as e:
            logger.warning(f"移动失败 {src} -> {dst}: {e}")
            return False
    
    def find_duplicate_files(self, current_folder):
        """查找重复文件"""
        try:
            hash_map = defaultdict(list)
            for root, _, files in os.walk(current_folder):
                for file in files:
                    path = os.path.join(root, file)
                    try:
                        file_hash = self.get_file_md5(path)
                        hash_map[file_hash].append(path)
                    except Exception:
                        continue
            
            duplicates = [v for v in hash_map.values() if len(v) > 1]
            return duplicates
        except Exception as e:
            raise Exception(f"查找重复文件失败: {e}")
    
    def get_file_md5(self, file_path):
        """计算文件MD5值"""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
        return md5_hash.hexdigest()
    
    def clean_empty_files(self, current_folder):
        """清理空文件"""
        try:
            empty_files = []
            for root, _, files in os.walk(current_folder):
                for file in files:
                    path = os.path.join(root, file)
                    try:
                        if os.path.getsize(path) == 0:
                            empty_files.append(path)
                    except Exception:
                        continue
            return empty_files
        except Exception as e:
            raise Exception(f"清理空文件失败: {e}")
    
    def find_large_files(self, current_folder, min_size_gb=1):
        """查找大文件"""
        try:
            min_bytes = min_size_gb * 1024**3
            large_files = []
            for root, _, files in os.walk(current_folder):
                for file in files:
                    path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(path)
                        if size > min_bytes:
                            large_files.append((path, size))
                    except Exception:
                        continue
            large_files.sort(key=lambda x: x[1], reverse=True)
            return large_files
        except Exception as e:
            raise Exception(f"查找大文件失败: {e}")
    
    def is_system_dir(self, path):
        """判断是否为系统目录"""
        path = os.path.realpath(path).lower()
        system_roots = [
            "c:\\windows", "c:\\program files", "c:\\program files (x86)",
            "c:\\system volume information", "c:\\recovery"
        ]
        return any(path.startswith(root) for root in system_roots)
    
    def list_files(self, current_folder):
        """列出当前目录文件"""
        try:
            files = []
            folders = []
            for item in os.listdir(current_folder):
                item_path = os.path.join(current_folder, item)
                if os.path.isfile(item_path):
                    files.append(item)
                elif os.path.isdir(item_path):
                    folders.append(item)
            return folders, files
        except Exception as e:
            raise Exception(f"列出文件失败: {e}")
