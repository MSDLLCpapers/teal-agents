import json
import os
from unittest.mock import patch

import pytest

from ska_utils import AppConfig, Config


def test_init_without_configs():
    AppConfig.reset()
    new_instance = AppConfig.__new__(AppConfig)
    with pytest.raises(ValueError, match="AppConfig.configs is not initialized"):
        new_instance.__init__()


def test_add_config():
    config = Config(env_name="TEST_KEY", is_required=True, default_value="default_value")
    AppConfig.add_config(config)
    app_config = AppConfig()
    assert app_config.props["TEST_KEY"] == "default_value"


def test_add_configs():
    configs = [
        Config(env_name="TEST_KEY1", is_required=True, default_value="default_value1"),
        Config(env_name="TEST_KEY2", is_required=False, default_value="default_value2"),
    ]
    AppConfig.add_configs(configs)
    app_config = AppConfig()
    assert app_config.props["TEST_KEY1"] == "default_value1"
    assert app_config.props["TEST_KEY2"] == "default_value2"


def test_add_existing_config_updates():
    config1 = Config(env_name="TEST_KEY", is_required=True, default_value="default_value")
    AppConfig.add_config(config1)
    config2 = Config(env_name="TEST_KEY", is_required=False, default_value="new_default_value")
    AppConfig.add_config(config2)
    app_config = AppConfig()
    assert app_config.props["TEST_KEY"] == "new_default_value"


def test_get_existing_key():
    config = Config(env_name="TEST_KEY", is_required=True, default_value="default_value")
    AppConfig.add_config(config)
    app_config = AppConfig()
    assert app_config.get("TEST_KEY") == "default_value"


def test_required_key_missing():
    config = Config(env_name="MISSING_KEY", is_required=True, default_value=None)
    with pytest.raises(ValueError, match="Missing required configuration key: MISSING_KEY"):
        AppConfig.add_config(config)


def test_parse_ta_env_store_valid_json():
    with patch.dict(os.environ, {"TA_ENV_STORE": '{"KEY1": "value1", "KEY2": "value2"}'}):
        app_config = AppConfig()
        app_config._parse_ta_env_store()
        assert os.getenv("KEY1") == "value1"
        assert os.getenv("KEY2") == "value2"


def test_parse_ta_env_store_invalid_json():
    with patch.dict(os.environ, {"TA_ENV_STORE": '{"KEY1": "value1", "KEY2": value2}'}):
        app_config = AppConfig()
        with pytest.raises(json.JSONDecodeError):
            app_config._parse_ta_env_store()


def test_parse_ta_env_global_store_valid_json():
    with patch.dict(os.environ, {"TA_ENV_STORE": '{"KEY1": "value1", "KEY2": "value2"}'}):
        app_config = AppConfig()
        app_config._parse_ta_env_global_store()
        assert os.getenv("KEY1") == "value1"
        assert os.getenv("KEY2") == "value2"


def test_parse_ta_env_global_store_invalid_json():
    with patch.dict(os.environ, {"TA_ENV_STORE": '{"KEY1": "value1", "KEY2": value2}'}):
        app_config = AppConfig()
        with pytest.raises(json.JSONDecodeError):
            app_config._parse_ta_env_global_store()


def test_reload_from_environment_without_configs():
    AppConfig.reset()
    new_instance = AppConfig.__new__(AppConfig)
    new_instance._reload_from_environment()


def test_reload_from_environment_valid_json():
    with patch.dict(os.environ, {"TA_ENV_STORE": '{"KEY1": "value1", "KEY2": "value2"}'}):
        app_config = AppConfig()
        app_config._reload_from_environment()
        assert os.getenv("KEY1") == "value1"
        assert os.getenv("KEY2") == "value2"


def test_reload_from_environment_invalid_json():
    with patch.dict(os.environ, {"TA_ENV_STORE": '{"KEY1": "value1", "KEY2": value2}'}):
        app_config = AppConfig()
        with pytest.raises(json.JSONDecodeError):
            app_config._reload_from_environment()
