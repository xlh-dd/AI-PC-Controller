import json
from pathlib import Path
import os
import threading
import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("ConfigManager")

class ConfigManager:
    """配置管理类"""
    
    CONFIG_VALIDATION = {
        "check_interval": {
            "type": int,
            "min": 1,
            "max": 3600,
            "default": 5,
            "description": "微信消息检查间隔(秒)"
        },
        "wechat_check_interval": {
            "type": int,
            "min": 1,
            "max": 3600,
            "default": 3,
            "description": "微信监听检查间隔(秒)"
        },
        "ai_timeout": {
            "type": int,
            "min": 10,
            "max": 300,
            "default": 60,
            "description": "AI响应超时时间(秒)"
        },
        "volume_step": {
            "type": int,
            "min": 1,
            "max": 20,
            "default": 5,
            "description": "音量调节步长"
        },
        "max_retries": {
            "type": int,
            "min": 1,
            "max": 10,
            "default": 3,
            "description": "最大重试次数"
        },
        "retry_delay": {
            "type": float,
            "min": 0.1,
            "max": 10.0,
            "default": 1.0,
            "description": "重试延迟(秒)"
        },
        "use_ai_features": {
            "type": bool,
            "default": False,
            "description": "是否启用AI功能"
        },
        "auto_reply_enabled": {
            "type": bool,
            "default": True,
            "description": "是否启用自动回复"
        },
        "model": {
            "type": str,
            "default": "qwen2.5:1.5b",
            "description": "AI模型名称"
        },
        "current_api_provider": {
            "type": str,
            "default": "hermes",
            "description": "当前API服务商"
        },
        "ocr_language": {
            "type": str,
            "default": "chi_sim+eng",
            "description": "OCR识别语言"
        },
        "tts_rate": {
            "type": int,
            "min": 50,
            "max": 300,
            "default": 150,
            "description": "语音合成语速"
        },
        "hermes_model": {
            "type": str,
            "default": "ds-v4-flash",
            "description": "Hermes 默认模型 (ds-v4-flash / ds-v4-flash-r / ds-v4-pro / ds-v4-pro-r)"
        },
        "tts_volume": {
            "type": float,
            "min": 0.0,
            "max": 1.0,
            "default": 1.0,
            "description": "语音合成音量"
        }
    }
    
    def __init__(self, config_file=None):
        self.config_file = config_file or Path.home() / ".aipc_helper_config.json"
        self.config = self.load_config()
        self._lock = threading.RLock()
        self._validate_and_fix_config()
    
    def _validate_and_fix_config(self):
        """验证并修复配置"""
        for key, spec in self.CONFIG_VALIDATION.items():
            if key not in self.config:
                self.config[key] = spec["default"]
                continue
            
            value = self.config[key]
            value_type = spec["type"]
            
            if value_type == bool:
                if isinstance(value, str):
                    self.config[key] = value.lower() in ("true", "yes", "1", "on")
                elif not isinstance(value, bool):
                    self.config[key] = bool(value)
            elif value_type in (int, float):
                try:
                    self.config[key] = value_type(value)
                    if "min" in spec and self.config[key] < spec["min"]:
                        self.config[key] = spec["min"]
                        logger.warning(f"配置项 {key} 值低于最小值，已调整为 {spec['min']}")
                    if "max" in spec and self.config[key] > spec["max"]:
                        self.config[key] = spec["max"]
                        logger.warning(f"配置项 {key} 值超过最大值，已调整为 {spec['max']}")
                except (ValueError, TypeError):
                    self.config[key] = spec["default"]
                    logger.warning(f"配置项 {key} 类型错误，已重置为默认值")
            elif value_type == str:
                if not isinstance(value, str):
                    self.config[key] = str(value) if value is not None else spec["default"]
    
    def validate_config_value(self, key: str, value: Any) -> tuple[bool, Any]:
        """验证配置值是否合法
        
        Args:
            key: 配置键名
            value: 配置值
            
        Returns:
            (是否有效, 修正后的值)
        """
        if key not in self.CONFIG_VALIDATION:
            return True, value
        
        spec = self.CONFIG_VALIDATION[key]
        value_type = spec["type"]
        
        try:
            if value_type == bool:
                if isinstance(value, str):
                    corrected = value.lower() in ("true", "yes", "1", "on")
                elif isinstance(value, bool):
                    corrected = value
                else:
                    corrected = bool(value)
            elif value_type in (int, float):
                corrected = value_type(value)
                if "min" in spec and corrected < spec["min"]:
                    corrected = spec["min"]
                if "max" in spec and corrected > spec["max"]:
                    corrected = spec["max"]
            elif value_type == str:
                corrected = str(value) if value is not None else spec["default"]
            else:
                corrected = value
            
            return True, corrected
        except (ValueError, TypeError):
            return False, spec["default"]
    
    def get_config_spec(self, key: Optional[str] = None) -> Union[Dict, Any]:
        """获取配置项的规格说明
        
        Args:
            key: 配置键名，如果为None则返回所有规格
            
        Returns:
            配置规格或规格字典
        """
        if key is None:
            return self.CONFIG_VALIDATION
        return self.CONFIG_VALIDATION.get(key)
    
    def reset_to_defaults(self, keys: Optional[list] = None):
        """重置配置到默认值
        
        Args:
            keys: 要重置的键列表，None表示全部重置
        """
        with self._lock:
            if keys is None:
                keys = list(self.CONFIG_VALIDATION.keys())
            
            for key in keys:
                if key in self.CONFIG_VALIDATION:
                    self.config[key] = self.CONFIG_VALIDATION[key]["default"]
            
            self.save_config()
    
    def load_config(self):
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置文件失败：{e}")
        return {}
    
    def save_config(self):
        """保存配置文件（原子写入）"""
        import tempfile
        import os
        
        with self._lock:
            try:
                config_dir = os.path.dirname(self.config_file)
                if config_dir and not os.path.exists(config_dir):
                    os.makedirs(config_dir, exist_ok=True)
                
                # 创建临时文件
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=config_dir or None,
                    prefix='.tmp_config_',
                    suffix='.json'
                )
                
                try:
                    # 写入临时文件
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        json.dump(self.config, f, ensure_ascii=False, indent=2)
                    
                    # 原子替换（os.replace 在所有平台都是原子操作）
                    os.replace(temp_path, self.config_file)
                    return True
                    
                except Exception as write_error:
                    # 写入失败，清理临时文件
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except Exception:
                        pass
                    raise write_error
                    
            except Exception as e:
                print(f"保存配置失败：{e}")
                return False
    
    def get(self, key, default=None):
        """获取配置值（带类型转换）"""
        value = self.config.get(key, default)
        
        # 对特定键进行类型转换（确保与set方法一致）
        if key == "check_interval":
            try:
                return int(value) if value is not None else default
            except (ValueError, TypeError):
                return default if default is not None else 5
        elif key == "use_ai_features":
            if isinstance(value, str):
                return value.lower() in ("true", "yes", "1", "on")
            elif isinstance(value, bool):
                return value
            else:
                return default if default is not None else False
        elif key == "model":
            if value is None or not isinstance(value, str):
                return default if default is not None else "qwen2.5:1.5b"
            return value
        elif key == "current_api_provider":
            if value is None or not isinstance(value, str):
                return default if default is not None else "hermes"
            return value
        
        return value
    
    def set(self, key, value):
        """设置配置值（带简单类型校验）"""
        with self._lock:
            # 对特定键进行类型转换和验证
            if key == "check_interval":
                try:
                    value = int(value)
                    if value < 1:
                        value = 1
                except (ValueError, TypeError):
                    value = 5  # 默认值
            elif key == "use_ai_features":
                if isinstance(value, str):
                    value = value.lower() in ("true", "yes", "1", "on")
                elif not isinstance(value, bool):
                    value = bool(value)
            elif key == "model" and not isinstance(value, str):
                value = str(value) if value is not None else "qwen2.5:1.5b"
            elif key == "current_api_provider" and not isinstance(value, str):
                value = str(value) if value is not None else "hermes"
            
            self.config[key] = value
            return self.save_config()
    
    def get_data_directory(self, subdirectory=None) -> Path:
        """获取数据存储目录
        
        Args:
            subdirectory: 子目录名
            
        Returns:
            Path对象指向数据目录
        """
        # 优先使用配置中的数据目录
        data_dir = self.config.get("data_directory")
        if data_dir:
            data_path = Path(data_dir)
        else:
            # 默认数据目录: 用户主目录下的 .aipc_helper_data
            data_path = Path.home() / ".aipc_helper_data"
        
        # 确保目录存在
        data_path.mkdir(parents=True, exist_ok=True)
        
        if subdirectory:
            subdir_path = data_path / subdirectory
            subdir_path.mkdir(parents=True, exist_ok=True)
            return subdir_path
        
        return data_path
    
    def get_default_app_paths(self):
        """获取默认应用路径"""
        local_appdata = os.environ.get('LOCALAPPDATA', '')
        return {
            "steam": [
                r"C:\Program Files (x86)\Steam\Steam.exe",
                r"C:\Program Files\Steam\Steam.exe",
                r"D:\Program Files (x86)\Steam\Steam.exe",
                r"D:\Program Files\Steam\Steam.exe"
            ],
            "雷神加速器": [
                r"C:\Program Files\雷神加速器\leigod.exe",
                r"D:\Program Files\雷神加速器\leigod.exe"
            ],
            "微信": [
                os.path.join(local_appdata, r'Tencent\WeChat\WeChat.exe'),
                r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
                r"D:\Program Files (x86)\Tencent\WeChat\WeChat.exe"
            ],
            "qq": [
                os.path.join(local_appdata, r'Tencent\QQ\Bin\QQ.exe'),
                r"C:\Program Files (x86)\Tencent\QQ\Bin\QQ.exe",
                r"D:\Program Files (x86)\Tencent\QQ\Bin\QQ.exe"
            ],
            "浏览器": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            ]
        }

    def get_default_api_providers(self):
        """获取默认API服务商配置"""
        return {
            "ollama": {
                "name": "Ollama (本地)",
                "base_url": "http://localhost:11434",
                "api_key": "",
                "models": ["qwen2.5:1.5b", "qwen2.5:3b", "llama3.1:8b", "deepseek-coder:1.3b"],
                "default_model": "qwen2.5:1.5b"
            },
            "openai": {
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
                "default_model": "gpt-4o-mini"
            },
            "deepseek": {
                "name": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "",
                "models": [
                    "deepseek-v4-flash",
                    "deepseek-v4-flash-reasoner",
                    "deepseek-v4-pro",
                    "deepseek-v4-pro-reasoner"
                ],
                "default_model": "deepseek-v4-flash"
            },
            "zhipu": {
                "name": "智谱AI",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "api_key": "",
                "models": ["glm-4", "glm-4-flash", "glm-4-plus", "glm-3-turbo"],
                "default_model": "glm-4-flash"
            },
            "hermes": {
                "name": "Hermes Agent (WSL2)",
                "wsl_distro": "Ubuntu-22.04",
                "venv_path": "~/hermes-agent/venv",
                "install_path": "~/hermes-agent",
                "api_key": "",
                "models": [
                    "deepseek/deepseek-v4-flash",
                    "deepseek/deepseek-v4-flash-reasoner",
                    "deepseek/deepseek-v4-pro",
                    "deepseek/deepseek-v4-pro-reasoner"
                ],
                "default_model": "deepseek/deepseek-v4-flash"
            },
            "anthropic": {
                "name": "Anthropic (Claude)",
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "",
                "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
                "default_model": "claude-3-5-sonnet-20241022"
            },
            "azure": {
                "name": "Azure OpenAI",
                "base_url": "",
                "api_key": "",
                "models": [],
                "default_model": ""
            }
        }

    def get_api_providers(self):
        """获取已配置的API服务商"""
        return self.config.get("api_providers", self.get_default_api_providers())

    def set_api_providers(self, providers):
        """保存API服务商配置"""
        self.config["api_providers"] = providers
        return self.save_config()

    def get_current_provider(self):
        """获取当前使用的服务商"""
        return self.config.get("current_api_provider", "hermes")

    def set_current_provider(self, provider_id):
        """设置当前使用的服务商"""
        self.config["current_api_provider"] = provider_id
        return self.save_config()
