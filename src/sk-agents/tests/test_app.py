import sys
from unittest.mock import MagicMock

import pytest


# Mock for sk_agents.configs
class MockTA_SERVICE_CONFIG:
    env_name = "TA_SERVICE_CONFIG_FILE"


class MockConfigs:
    TA_SERVICE_CONFIG = MockTA_SERVICE_CONFIG()


# Mock for sk_agents.ska_types
class MockBaseConfig:
    def __init__(self, apiVersion, version, name=None, service_name=None):
        self.apiVersion = apiVersion
        self.version = version
        self.name = name
        self.service_name = service_name


@pytest.fixture
def mock_initialize_telemetry(mocker):
    """Mocks ska_utils.initialize_telemetry and returns the mock object."""
    return mocker.patch("ska_utils.initialize_telemetry", autospec=True)


@pytest.fixture(autouse=True)
def mock_dependencies(mocker, mock_initialize_telemetry):
    """Mocks all external dependencies for every test."""
    # Mock modules that are imported by the main application
    mocker.patch("sk_agents.configs.TA_SERVICE_CONFIG", MockTA_SERVICE_CONFIG)
    mocker.patch("sk_agents.configs.configs", MockConfigs())
    mocker.patch("sk_agents.ska_types.BaseConfig", MockBaseConfig)

    # Mock classes and functions
    mocker.patch("ska_utils.AppConfig", autospec=True)
    mocker.patch("pydantic_yaml.parse_yaml_file_as", autospec=True)
    mocker.patch("ska_utils.get_telemetry", return_value=MagicMock())
    mocker.patch("fastapi.FastAPI", autospec=True)
    mocker.patch("sk_agents.middleware.TelemetryMiddleware", autospec=True)
    mocker.patch("sk_agents.appv1.AppV1.run", autospec=True)
    mocker.patch("sk_agents.appv2.AppV2.run", autospec=True)

    # Ensure a clean slate for each test by removing the main app module from cache
    if "sk_agents.app" in sys.modules:
        del sys.modules["sk_agents.app"]


@pytest.fixture
def mock_app_config(mocker):
    """Fixture to get the mocked AppConfig class for further customization."""
    return mocker.patch("ska_utils.AppConfig")


@pytest.fixture
def mock_parse_yaml(mocker):
    """Fixture to get the mocked parse_yaml_file_as function."""
    return mocker.patch("pydantic_yaml.parse_yaml_file_as")


def test_app_v1_initialization_successful(
    mocker, mock_app_config, mock_parse_yaml, mock_initialize_telemetry
):
    """
    Tests if the application initializes correctly for API version v1,
    calling the appropriate AppV1 runner.
    """
    # Arrange: Create mocks BEFORE importing app
    mock_fastapi_instance = MagicMock()
    mock_fastapi_class = mocker.patch("fastapi.FastAPI", return_value=mock_fastapi_instance)

    mock_appv1_run = mocker.patch("sk_agents.appv1.AppV1.run")

    # Setup AppConfig to return the config path
    mock_app_config.return_value.get.return_value = "/fake/path/to/config.yaml"

    # Setup YAML to return a valid config object
    mock_config_v1 = MockBaseConfig(
        apiVersion="skagents/v1alpha1", version="1.2.3", service_name="test-service-v1"
    )
    mock_parse_yaml.return_value = mock_config_v1

    # Act: Now import the module (this runs the app setup logic)
    import sk_agents.app  # noqa: F401

    # Assert: Verify FastAPI was constructed with expected URLs
    mock_fastapi_class.assert_called_once_with(
        openapi_url="/test-service-v1/1.2.3/openapi.json",
        docs_url="/test-service-v1/1.2.3/docs",
        redoc_url="/test-service-v1/1.2.3/redoc",
    )
    mock_fastapi_instance.add_middleware.assert_called_once()
    mock_initialize_telemetry.assert_called_once()
    mock_appv1_run.assert_called_once_with(
        "test-service-v1",
        "1.2.3",
        mock_app_config.return_value,
        mock_config_v1,
        mock_fastapi_instance,
    )


def test_app_v2_initialization_successful(
    mocker, mock_app_config, mock_parse_yaml, mock_initialize_telemetry
):
    """
    Tests if the application initializes correctly for API version v2,
    calling the appropriate AppV2 runner.
    """
    # Arrange: Set up mocks BEFORE importing app
    mock_fastapi_instance = MagicMock()
    mock_fastapi_class = mocker.patch("fastapi.FastAPI", return_value=mock_fastapi_instance)

    mock_appv2_run = mocker.patch("sk_agents.appv2.AppV2.run")

    # Set mock config path
    mock_app_config.return_value.get.return_value = "/fake/path/to/config_v2.yaml"

    # Provide v2 config object
    mock_config_v2 = MockBaseConfig(
        apiVersion="skagents/v2alpha1", version="2.0.0", name="test-service-v2"
    )
    mock_parse_yaml.return_value = mock_config_v2

    # Act: Trigger app logic via import
    import sk_agents.app  # noqa: F401

    # Assert: Check FastAPI and AppV2 interactions
    mock_fastapi_class.assert_called_once_with(
        openapi_url="/test-service-v2/2.0.0/openapi.json",
        docs_url="/test-service-v2/2.0.0/docs",
        redoc_url="/test-service-v2/2.0.0/redoc",
    )
    mock_fastapi_instance.add_middleware.assert_called_once()
    mock_initialize_telemetry.assert_called_once()
    mock_appv2_run.assert_called_once_with(
        "test-service-v2",
        "2.0.0",
        mock_app_config.return_value,
        mock_config_v2,
        mock_fastapi_instance,
    )


def test_app_v3_initialization_successful(
    mocker, mock_app_config, mock_parse_yaml, mock_initialize_telemetry
):
    """
    Tests if the application initializes correctly for API version v3,
    calling the appropriate AppV3 runner.
    """
    # Arrange: Set up mocks BEFORE importing app
    mock_fastapi_instance = MagicMock()
    mock_fastapi_class = mocker.patch("fastapi.FastAPI", return_value=mock_fastapi_instance)

    mock_appv3_run = mocker.patch("sk_agents.appv3.AppV3.run")

    # Set mock config path
    mock_app_config.return_value.get.return_value = "/fake/path/to/config_v3.yaml"

    # Provide v3 config object
    mock_config_v3 = MockBaseConfig(
        apiVersion="tealagents/v1alpha1", version="2.0.0", name="test-service-v3"
    )
    mock_parse_yaml.return_value = mock_config_v3

    # Act: Trigger app logic via import
    import sk_agents.app  # noqa: F401

    # Assert: Check FastAPI and AppV3 interactions
    mock_fastapi_class.assert_called_once_with(
        openapi_url="/test-service-v3/2.0.0/openapi.json",
        docs_url="/test-service-v3/2.0.0/docs",
        redoc_url="/test-service-v3/2.0.0/redoc",
    )
    mock_fastapi_instance.add_middleware.assert_called_once()
    mock_initialize_telemetry.assert_called_once()
    mock_appv3_run.assert_called_once_with(
        "test-service-v3",
        "2.0.0",
        mock_app_config.return_value,
        mock_config_v3,
        mock_fastapi_instance,
    )


def test_config_file_not_found(mock_app_config):
    """
    Tests if the application raises FileNotFoundError when the config file path is not set.
    """
    # Arrange
    mock_app_config.return_value.get.return_value = None

    # Act & Assert
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        import sk_agents.app  # noqa: F401


def test_yaml_parsing_fails(mock_app_config, mock_parse_yaml):
    """
    Tests if the application raises an exception when YAML parsing fails.
    """
    # Arrange
    mock_app_config.return_value.get.return_value = "/fake/path/to/bad_config.yaml"
    mock_parse_yaml.side_effect = Exception("Invalid YAML format")

    # Act & Assert
    with pytest.raises(Exception, match="Invalid YAML format"):
        import sk_agents.app  # noqa: F401


def test_invalid_api_version_format(mock_app_config, mock_parse_yaml):
    """
    Tests if the application raises a ValueError for an incorrectly formatted apiVersion.
    """
    # Arrange
    mock_app_config.return_value.get.return_value = "/fake/path/to/config.yaml"
    mock_config_invalid_api = MockBaseConfig(
        apiVersion="invalid-format", version="1.0.0", service_name="test-service"
    )
    mock_parse_yaml.return_value = mock_config_invalid_api

    # Act & Assert
    # CORRECTED: The original ValueError from .split() is re-raised.
    # We now match against the standard Python error message for this operation.
    with pytest.raises(ValueError, match="not enough values to unpack"):
        import sk_agents.app  # noqa: F401


def test_missing_service_name_in_config(mock_app_config, mock_parse_yaml):
    """
    Tests if the application raises a ValueError if the service name is not defined.
    """
    # Arrange
    mock_app_config.return_value.get.return_value = "/fake/path/to/config.yaml"
    # Simulate a config where 'service_name' (for v1) is None
    mock_config_no_name = MockBaseConfig(
        apiVersion="skagents/v1alpha1", version="1.0.0", service_name=None
    )
    mock_parse_yaml.return_value = mock_config_no_name

    # Act & Assert
    with pytest.raises(ValueError, match="Service name is not defined in the configuration file."):
        import sk_agents.app  # noqa: F401


def test_missing_service_version_in_config(mock_app_config, mock_parse_yaml):
    """
    Tests if the application raises a ValueError if the service version is not defined.
    """
    # Arrange: set up a config with missing version
    mock_app_config.return_value.get.return_value = "/fake/path/to/config.yaml"
    mock_config_missing_version = MockBaseConfig(
        apiVersion="skagents/v2alpha1",  # or v1alpha1
        version="",
        name="test-service",
    )
    mock_parse_yaml.return_value = mock_config_missing_version

    # Act & Assert: expect ValueError
    with pytest.raises(ValueError, match="Service version is not defined"):
        import sk_agents.app  # noqa: F401


def test_invalid_api_version_in_config(mock_app_config, mock_parse_yaml):
    """
    Tests if the application raises a ValueError if the apiVersion is invalid.
    """
    # Arrange: set up a config with invalid apiVersion
    mock_app_config.return_value.get.return_value = "/fake/path/to/config.yaml"
    mock_config_missing_version = MockBaseConfig(
        apiVersion="invalid/v2alpha1",  # or v1alpha1
        version="",
        service_name="test-service",
    )
    mock_parse_yaml.return_value = mock_config_missing_version

    # Act & Assert: expect ValueError
    with pytest.raises(ValueError, match="Invalid apiVersion defined in the configuration file."):
        import sk_agents.app  # noqa: F401
