import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    """Pytest配置"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )


@pytest.fixture
def temp_config_file(tmp_path):
    """创建临时配置文件"""
    config_file = tmp_path / "test_config.json"
    config_file.write_text("{}")
    return str(config_file)


@pytest.fixture
def sample_config():
    """示例配置"""
    return {
        "check_interval": 5,
        "use_ai_features": True,
        "model": "qwen2.5:1.5b",
        "current_api_provider": "ollama"
    }
