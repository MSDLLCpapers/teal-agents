import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel

from ska_utils import Singleton

class Config(BaseModel):
    env_name: str
    is_required: bool
    default_value: str | None

class AppConfig(metaclass=Singleton):
    configs: List[Config] | None = None

    @staticmethod
    def add_config(config: Config):
        AppConfig._add_config(config)
        AppConfig()._reload_from_environment()

    @staticmethod
    def _add_config(config: Config):
        if AppConfig.configs is None:
            AppConfig.configs = []

        found = False
        for c in AppConfig.configs:
            if c.env_name == config.env_name:
                c.is_required = config.is_required
                c.default_value = config.default_value
                found = True
                break
        if not found:
            AppConfig.configs.append(config)

    @staticmethod
    def add_configs(configs: List[Config]):
        for config in configs:
            AppConfig._add_config(config)
        AppConfig()._reload_from_environment()

    def __init__(self):
        if AppConfig.configs is None:
            raise ValueError("AppConfig.configs is not initialized")

        load_dotenv()
        self._reload_from_environment()

    def _reload_from_environment(self):
        self.props = {}
        for config in AppConfig.configs:
            self.props[config.env_name] = os.getenv(config.env_name, default=config.default_value if config.default_value is not None else None)
        self.__validate_required_keys()

    def get(self, key):
        return self.props[key]

    def __validate_required_keys(self):
        for config in AppConfig.configs:
            if config.is_required and self.props[config.env_name] is None:
                raise ValueError(f"Missing required configuration key: {config.env_name}")
