"""
Configuration validator for detecting missing/invalid environment variables at startup.

CDW-1653: Better error handling in Agents
"""

import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ska_utils import AppConfig, Config

from sk_agents.configs import (
    TA_A2A_ENABLED,
    TA_AGENT_BASE_URL,
    TA_API_KEY,
    TA_AUTH_STORAGE_MANAGER_CLASS,
    TA_AUTH_STORAGE_MANAGER_MODULE,
    TA_AUTHORIZER_CLASS,
    TA_AUTHORIZER_MODULE,
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME,
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE,
    TA_OAUTH_BASE_URL,
    TA_OAUTH_CLIENT_NAME,
    TA_OAUTH_REDIRECT_URI,
    TA_PERSISTENCE_CLASS,
    TA_PERSISTENCE_MODULE,
    TA_PLUGIN_CATALOG_CLASS,
    TA_PLUGIN_CATALOG_FILE,
    TA_PLUGIN_CATALOG_MODULE,
    TA_PLUGIN_MODULE,
    TA_PROVIDER_ORG,
    TA_PROVIDER_URL,
    TA_REDIS_DB,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_PWD,
    TA_REDIS_SSL,
    TA_REDIS_TTL,
    TA_REMOTE_PLUGIN_PATH,
    TA_SERVICE_CONFIG,
    TA_STATE_MANAGEMENT,
    TA_STRUCTURED_OUTPUT_TRANSFORMER_MODEL,
    TA_TYPES_MODULE,
)
from sk_agents.exceptions import AgentConfigurationError, ERROR_MISSING_ENV_VAR

logger = logging.getLogger(__name__)


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, code: str, message: str, field: str | None = None):
        self.code = code
        self.message = message
        self.field = field

    def __str__(self) -> str:
        if self.field:
            return f"[{self.code}] {self.field}: {self.message}"
        return f"[{self.code}] {self.message}"


class ConfigValidator:
    """
    Validates configuration at application startup.
    
    Performs comprehensive validation of:
    - Required environment variables
    - File paths existence
    - URL formats
    - Conditional configurations
    - State management setup
    """

    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.errors: list[ValidationError] = []
        self.warnings: list[str] = []

    def validate_all(self) -> tuple[list[ValidationError], list[str]]:
        """
        Run all validation checks.
        
        Returns:
            Tuple of (errors, warnings)
        """
        logger.info("Starting configuration validation...")
        
        self.errors = []
        self.warnings = []

        # Core validations
        self._validate_required_vars()
        self._validate_service_config()
        self._validate_file_paths()
        self._validate_urls()
        
        # Conditional validations
        self._validate_state_management()
        self._validate_custom_chat_completion()
        self._validate_auth_storage()
        self._validate_persistence()
        self._validate_a2a_config()
        
        if self.errors:
            logger.error(f"Configuration validation failed with {len(self.errors)} error(s)")
            for error in self.errors:
                logger.error(f"  - {error}")
        else:
            logger.info("Configuration validation passed ✓")
            
        if self.warnings:
            logger.warning(f"Configuration validation has {len(self.warnings)} warning(s)")
            for warning in self.warnings:
                logger.warning(f"  - {warning}")

        return self.errors, self.warnings

    def _validate_required_vars(self):
        """Validate all required environment variables."""
        required_configs = [
            TA_API_KEY,
            TA_SERVICE_CONFIG,
            TA_STATE_MANAGEMENT,
            TA_A2A_ENABLED,
            TA_AGENT_BASE_URL,
            TA_PROVIDER_ORG,
            TA_PROVIDER_URL,
            TA_PERSISTENCE_MODULE,
            TA_PERSISTENCE_CLASS,
        ]

        for config in required_configs:
            if config.is_required:
                value = self.app_config.get(config.env_name)
                if not value or (isinstance(value, str) and value.strip() == ""):
                    self.errors.append(
                        ValidationError(
                            code="CFG-001",
                            message=f"Required environment variable is not set or empty",
                            field=config.env_name,
                        )
                    )

    def _validate_service_config(self):
        """Validate service configuration file."""
        config_file = self.app_config.get(TA_SERVICE_CONFIG.env_name)
        if config_file:
            config_path = Path(config_file)
            if not config_path.exists():
                self.errors.append(
                    ValidationError(
                        code="CFG-003",
                        message=f"Configuration file not found: {config_file}",
                        field=TA_SERVICE_CONFIG.env_name,
                    )
                )
            elif not config_path.is_file():
                self.errors.append(
                    ValidationError(
                        code="CFG-007",
                        message=f"Configuration path is not a file: {config_file}",
                        field=TA_SERVICE_CONFIG.env_name,
                    )
                )
            elif not config_path.suffix in [".yaml", ".yml"]:
                self.warnings.append(
                    f"Configuration file does not have .yaml/.yml extension: {config_file}"
                )

    def _validate_file_paths(self):
        """Validate that file paths exist."""
        file_configs = [
            (TA_PLUGIN_CATALOG_FILE, False),  # Optional
            (TA_REMOTE_PLUGIN_PATH, False),  # Optional
        ]

        for config, is_required in file_configs:
            file_path = self.app_config.get(config.env_name)
            if file_path:
                path = Path(file_path)
                if not path.exists():
                    if is_required:
                        self.errors.append(
                            ValidationError(
                                code="CFG-007",
                                message=f"File not found: {file_path}",
                                field=config.env_name,
                            )
                        )
                    else:
                        self.warnings.append(f"Optional file not found: {file_path}")

    def _validate_urls(self):
        """Validate URL formats."""
        url_configs = [
            TA_AGENT_BASE_URL,
            TA_PROVIDER_URL,
            TA_OAUTH_BASE_URL,
            TA_OAUTH_REDIRECT_URI,
        ]

        for config in url_configs:
            url = self.app_config.get(config.env_name)
            if url:
                try:
                    parsed = urlparse(url)
                    if not parsed.scheme or not parsed.netloc:
                        self.errors.append(
                            ValidationError(
                                code="CFG-006",
                                message=f"Invalid URL format: {url}",
                                field=config.env_name,
                            )
                        )
                except Exception as e:
                    self.errors.append(
                        ValidationError(
                            code="CFG-006",
                            message=f"Invalid URL: {url} - {str(e)}",
                            field=config.env_name,
                        )
                    )

    def _validate_state_management(self):
        """Validate state management configuration."""
        state_mgmt = self.app_config.get(TA_STATE_MANAGEMENT.env_name)
        
        if not state_mgmt:
            return
            
        valid_options = ["in-memory", "redis", "dynamodb"]
        if state_mgmt not in valid_options:
            self.errors.append(
                ValidationError(
                    code="CFG-004",
                    message=f"Invalid state management option: {state_mgmt}. "
                    f"Valid options are: {', '.join(valid_options)}",
                    field=TA_STATE_MANAGEMENT.env_name,
                )
            )

        # If Redis, validate Redis configs
        if state_mgmt == "redis":
            redis_configs = [
                (TA_REDIS_HOST, True),
                (TA_REDIS_PORT, True),
                (TA_REDIS_DB, False),
                (TA_REDIS_PWD, False),
            ]

            for config, is_required in redis_configs:
                value = self.app_config.get(config.env_name)
                if is_required and not value:
                    self.errors.append(
                        ValidationError(
                            code="CFG-001",
                            message=f"Required for Redis state management but not set",
                            field=config.env_name,
                        )
                    )

            # Validate Redis port is a number
            redis_port = self.app_config.get(TA_REDIS_PORT.env_name)
            if redis_port:
                try:
                    port_num = int(redis_port)
                    if port_num < 1 or port_num > 65535:
                        self.errors.append(
                            ValidationError(
                                code="CFG-004",
                                message=f"Redis port must be between 1 and 65535, got: {redis_port}",
                                field=TA_REDIS_PORT.env_name,
                            )
                        )
                except ValueError:
                    self.errors.append(
                        ValidationError(
                            code="CFG-004",
                            message=f"Redis port must be a number, got: {redis_port}",
                            field=TA_REDIS_PORT.env_name,
                        )
                    )

    def _validate_custom_chat_completion(self):
        """Validate custom chat completion factory configuration."""
        factory_module = self.app_config.get(TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name)
        factory_class = self.app_config.get(TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name)

        # Both must be set or both must be unset
        if factory_module and not factory_class:
            self.errors.append(
                ValidationError(
                    code="CFG-005",
                    message="TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE is set but "
                    "TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME is not set",
                    field=TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name,
                )
            )
        elif factory_class and not factory_module:
            self.errors.append(
                ValidationError(
                    code="CFG-005",
                    message="TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME is set but "
                    "TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE is not set",
                    field=TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name,
                )
            )

    def _validate_auth_storage(self):
        """Validate auth storage manager configuration."""
        storage_module = self.app_config.get(TA_AUTH_STORAGE_MANAGER_MODULE.env_name)
        storage_class = self.app_config.get(TA_AUTH_STORAGE_MANAGER_CLASS.env_name)

        # Both must be set or both must be unset
        if storage_module and not storage_class:
            self.errors.append(
                ValidationError(
                    code="CFG-005",
                    message="TA_AUTH_STORAGE_MANAGER_MODULE is set but "
                    "TA_AUTH_STORAGE_MANAGER_CLASS is not set",
                    field=TA_AUTH_STORAGE_MANAGER_CLASS.env_name,
                )
            )
        elif storage_class and not storage_module:
            self.errors.append(
                ValidationError(
                    code="CFG-005",
                    message="TA_AUTH_STORAGE_MANAGER_CLASS is set but "
                    "TA_AUTH_STORAGE_MANAGER_MODULE is not set",
                    field=TA_AUTH_STORAGE_MANAGER_MODULE.env_name,
                )
            )

    def _validate_persistence(self):
        """Validate persistence configuration."""
        persistence_module = self.app_config.get(TA_PERSISTENCE_MODULE.env_name)
        persistence_class = self.app_config.get(TA_PERSISTENCE_CLASS.env_name)

        # Both must be set
        if not persistence_module:
            self.errors.append(
                ValidationError(
                    code="CFG-001",
                    message="Persistence module is required",
                    field=TA_PERSISTENCE_MODULE.env_name,
                )
            )
        if not persistence_class:
            self.errors.append(
                ValidationError(
                    code="CFG-001",
                    message="Persistence class is required",
                    field=TA_PERSISTENCE_CLASS.env_name,
                )
            )

    def _validate_a2a_config(self):
        """Validate Agent-to-Agent configuration if enabled."""
        a2a_enabled_value = self.app_config.props.get(TA_A2A_ENABLED.env_name)
        a2a_enabled_str = (a2a_enabled_value or "false").lower()
        
        if a2a_enabled_str in ["true", "1", "yes"]:
            self.warnings.append(
                "A2A (Agent-to-Agent) functionality is deprecated and maintained for "
                "backward compatibility only. Consider migrating to alternative approaches."
            )


def validate_config_or_raise(app_config: AppConfig) -> None:
    """
    Validate configuration and raise exception if errors found.
    
    Args:
        app_config: Application configuration to validate
        
    Raises:
        AgentConfigurationError: If validation errors are found
    """
    validator = ConfigValidator(app_config)
    errors, warnings = validator.validate_all()

    if errors:
        error_messages = [str(error) for error in errors]
        raise AgentConfigurationError(
            message="Configuration validation failed. Please check the following errors:\n"
            + "\n".join(f"  - {msg}" for msg in error_messages),
            error_code="CFG-000",
            details={"errors": error_messages, "warnings": warnings},
        )
