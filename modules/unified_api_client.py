import json
import logging
import os
import subprocess
import tempfile
import time

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

logger = logging.getLogger("UnifiedAPIClient")

class UnifiedAPIClient:
    """统一API客户端 - 支持多种AI服务商"""

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.client = None
        self.current_provider = None
        self.provider_config = None
        self._session = requests.Session() if requests else None

    def load_provider_config(self, provider_id=None):
        """加载服务商配置"""
        if not self.config_manager:
            return None

        if provider_id is None:
            provider_id = self.config_manager.get_current_provider()

        providers = self.config_manager.get_api_providers()
        self.current_provider = provider_id
        self.provider_config = providers.get(provider_id, {})
        return self.provider_config

    def switch_provider(self, provider_id):
        """切换服务商"""
        self.load_provider_config(provider_id)
        if self.config_manager:
            self.config_manager.set_current_provider(provider_id)
        logger.info(f"已切换到服务商: {self.provider_config.get('name', provider_id)}")

    def get_available_providers(self):
        """获取可用的服务商列表"""
        if not self.config_manager:
            return []
        providers = self.config_manager.get_api_providers()
        return [
            {
                "id": pid,
                "name": p.get("name", pid),
                "has_api_key": bool(p.get("api_key"))
            }
            for pid, p in providers.items()
        ]

    def query(self, prompt, system_prompt=None, stream_callback=None, model=None, stop_event=None):
        """统一的AI查询接口

        Args:
            prompt: 用户输入
            system_prompt: 系统提示词
            stream_callback: 流式响应回调函数
            model: 模型名称
            stop_event: threading.Event对象，用于停止生成（可选）
        """
        if not REQUESTS_AVAILABLE:
            logger.error("requests模块未安装，无法调用AI API")
            return None

        if not self.provider_config:
            self.load_provider_config()

        provider_id = self.current_provider

        if provider_id == "ollama":
            return self._query_ollama(prompt, system_prompt, stream_callback, model, stop_event)
        elif provider_id in ["openai", "deepseek", "zhipu"]:
            return self._query_openai_compatible(prompt, system_prompt, stream_callback, model, stop_event)
        elif provider_id == "hermes":
            return self._query_hermes(prompt, system_prompt, stream_callback, model, stop_event)
        elif provider_id == "anthropic":
            return self._query_anthropic(prompt, system_prompt, stream_callback, model, stop_event)
        else:
            logger.warning(f"未知服务商: {provider_id}")
            return self._query_ollama(prompt, system_prompt, stream_callback, model, stop_event)

    def _query_ollama(self, prompt, system_prompt, stream_callback, model, stop_event=None):
        """Ollama查询"""
        base_url = self.provider_config.get("base_url", "http://localhost:11434")
        url = f"{base_url}/api/generate"

        if model is None:
            model = self.provider_config.get("default_model", "qwen2.5:1.5b")

        data = {
            "model": model,
            "prompt": prompt,
            "stream": bool(stream_callback),
            "options": {"temperature": 0.5, "num_predict": 512, "top_k": 40}
        }
        if system_prompt:
            data["system"] = system_prompt

        try:
            if stream_callback:
                response = self._session.post(url, json=data, timeout=60, stream=True)
                if response.status_code == 200:
                    full_response = ""
                    for line in response.iter_lines():
                        # 检查停止标志
                        if stop_event and stop_event.is_set():
                            logger.info("生成已停止")
                            return full_response.strip()

                        if line:
                            try:
                                chunk = json.loads(line.decode('utf-8'))
                                if 'response' in chunk:
                                    full_response += chunk['response']
                                    stream_callback(chunk['response'])  # 传递增量内容，而不是累积内容
                                if chunk.get('done', False):
                                    break
                            except Exception:
                                pass
                    return full_response.strip()
            else:
                response = self._session.post(url, json=data, timeout=30)
                if response.status_code == 200:
                    return response.json().get("response", "").strip()

            logger.error(f"Ollama返回错误：{response.status_code}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning("无法连接到Ollama服务")
            return None
        except Exception as e:
            logger.error(f"Ollama调用异常：{e}")
            return None

    def _query_openai_compatible(self, prompt, system_prompt, stream_callback, model, stop_event=None):
        """OpenAI兼容接口查询 (OpenAI, DeepSeek, 智谱等)"""
        base_url = self.provider_config.get("base_url", "https://api.openai.com/v1")
        api_key = self.provider_config.get("api_key", "")

        if not api_key:
            logger.warning(f"{self.provider_config.get('name')} 未配置API密钥")
            return None

        if model is None:
            model = self.provider_config.get("default_model", "gpt-4o-mini")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        if self.current_provider == "zhipu":
            headers["Authorization"] = f"Bearer {api_key}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        data = {
            "model": model,
            "messages": messages,
            "stream": bool(stream_callback),
            "temperature": 0.5,
            "max_tokens": 512
        }

        try:
            url = f"{base_url}/chat/completions"

            if stream_callback:
                response = self._session.post(url, headers=headers, json=data, timeout=60, stream=True)
                if response.status_code == 200:
                    full_response = ""
                    for line in response.iter_lines():
                        # 检查停止标志
                        if stop_event and stop_event.is_set():
                            logger.info("生成已停止")
                            return full_response.strip()

                        if line:
                            line = line.decode('utf-8')
                            if line.startswith('data: '):
                                if line == 'data: [DONE]':
                                    break
                                try:
                                    chunk_data = json.loads(line[6:])
                                    if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                        delta = chunk_data['choices'][0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            full_response += content
                                            stream_callback(content)  # 传递增量内容，而不是累积内容
                                except Exception:
                                    pass
                    return full_response.strip()
            else:
                response = self._session.post(url, headers=headers, json=data, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        return result['choices'][0]['message']['content'].strip()

            logger.error(f"API返回错误：{response.status_code} - {response.text}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"无法连接到{self.provider_config.get('name')}服务")
            return None
        except Exception as e:
            logger.error(f"API调用异常：{e}")
            return None

    def _query_anthropic(self, prompt, system_prompt, stream_callback, model, stop_event=None):
        """Anthropic (Claude) 查询"""
        api_key = self.provider_config.get("api_key", "")

        if not api_key:
            logger.warning("Anthropic 未配置API密钥")
            return None

        if model is None:
            model = self.provider_config.get("default_model", "claude-3-5-sonnet-20241022")

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        data = {
            "model": model,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.5
        }

        try:
            url = "https://api.anthropic.com/v1/messages"

            if stream_callback:
                logger.warning("Anthropic 暂不支持流式响应")
                response = self._session.post(url, headers=headers, json=data, timeout=30)
            else:
                response = self._session.post(url, headers=headers, json=data, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if 'content' in result and len(result['content']) > 0:
                    return result['content'][0].text.strip()

            logger.error(f"Anthropic返回错误：{response.status_code} - {response.text}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning("无法连接到Anthropic服务")
            return None
        except Exception as e:
            logger.error(f"Anthropic调用异常：{e}")
            return None

    def _query_hermes(self, prompt, system_prompt, stream_callback, model, stop_event=None):
        """通过 HermesService 调用 Hermes Agent（全能力对接）

        委托给 services/hermes_service.py，支持:
        - 流式输出透传
        - 会话持久化
        - 模型指定
        """
        try:
            # 检查停止标志
            if stop_event and stop_event.is_set():
                return None

            from services.hermes_service import get_hermes_service

            hermes = get_hermes_service(
                config_manager=getattr(self, '_config_manager', None),
                wsl_distro=self.provider_config.get("wsl_distro", "Ubuntu-22.04")
            )

            if not hermes.ensure_ready():
                return "[Hermes 不可用，请检查 WSL 和 API 密钥配置]"

            answer = hermes.oneshot(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                stream_callback=stream_callback,
            )

            return answer

        except Exception as e:
            logger.error(f"Hermes 调用异常: {e}")
            return None

    def test_connection(self, provider_id=None):
        """测试API连接"""
        old_provider = self.current_provider

        try:
            if provider_id:
                self.load_provider_config(provider_id)
            elif not self.current_provider:
                self.load_provider_config()

            test_prompt = "你好，请回复'测试成功'"
            result = self.query(test_prompt)
            return result is not None
        finally:
            # 恢复原来的provider
            if old_provider != self.current_provider:
                self.load_provider_config(old_provider)


_client_instance = None

def get_unified_client(config_manager=None):
    """获取统一API客户端单例"""
    global _client_instance
    if _client_instance is None:
        _client_instance = UnifiedAPIClient(config_manager)
    return _client_instance
