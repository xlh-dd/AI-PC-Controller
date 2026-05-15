import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import ConfigManager


class TestConfigManager:
    """测试配置管理器"""

    def test_config_manager_init(self):
        """测试初始化"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name

        try:
            cm = ConfigManager(config_file=temp_file)
            assert cm.config is not None
        finally:
            os.unlink(temp_file)

    def test_validate_config_value_int(self):
        """测试整数配置验证"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name

        try:
            cm = ConfigManager(config_file=temp_file)

            valid, value = cm.validate_config_value("check_interval", 10)
            assert valid is True
            assert value == 10

            valid, value = cm.validate_config_value("check_interval", 5000)
            assert valid is True
            assert value == 3600

            valid, value = cm.validate_config_value("check_interval", 0)
            assert valid is True
            assert value == 1
        finally:
            os.unlink(temp_file)

    def test_validate_config_value_bool(self):
        """测试布尔配置验证"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name

        try:
            cm = ConfigManager(config_file=temp_file)

            valid, value = cm.validate_config_value("use_ai_features", "true")
            assert valid is True
            assert value is True

            valid, value = cm.validate_config_value("use_ai_features", "false")
            assert valid is True
            assert value is False
        finally:
            os.unlink(temp_file)

    def test_validate_config_value_float(self):
        """测试浮点数配置验证"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name

        try:
            cm = ConfigManager(config_file=temp_file)

            valid, value = cm.validate_config_value("tts_volume", 0.5)
            assert valid is True
            assert value == 0.5

            valid, value = cm.validate_config_value("tts_volume", 1.5)
            assert valid is True
            assert value == 1.0
        finally:
            os.unlink(temp_file)

    def test_get_config_spec(self):
        """测试获取配置规格"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            temp_file = f.name

        try:
            cm = ConfigManager(config_file=temp_file)

            spec = cm.get_config_spec()
            assert "check_interval" in spec
            assert "use_ai_features" in spec

            check_interval_spec = cm.get_config_spec("check_interval")
            assert check_interval_spec["type"] == int
            assert check_interval_spec["min"] == 1
            assert check_interval_spec["max"] == 3600
        finally:
            os.unlink(temp_file)

    def test_validate_and_fix_config(self):
        """测试配置验证和修复"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"check_interval": 10, "invalid_key": "value"}')
            temp_file = f.name

        try:
            cm = ConfigManager(config_file=temp_file)
            assert cm.config["check_interval"] == 10
        finally:
            os.unlink(temp_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
