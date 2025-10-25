import logging
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.trace import Tracer

from ska_utils import AppConfig, Telemetry, get_telemetry, initialize_telemetry


@pytest.fixture
def app_config():
    config = MagicMock(spec=AppConfig)
    config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "true",
        "TA_OTEL_ENDPOINT": "http://localhost:4317",
        "TA_OTEL_METRICS_ENDPOINT": "http://localhost:4317",
        "TA_LOG_LEVEL": "info",
    }.get
    return config


def test_telemetry_initialization_info(app_config):
    telemetry = Telemetry("test_service", app_config)
    assert telemetry.service_name == "test_service"
    assert telemetry._telemetry_enabled is True
    assert telemetry.endpoint == "http://localhost:4317"
    assert telemetry._log_level == logging.INFO


def test_telemetry_initialization_debug(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "debug",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.DEBUG


def test_telemetry_initialization_warning(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "warning",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.WARNING


def test_telemetry_initialization_error(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "error",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.ERROR


def test_telemetry_initialization_critical(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "critical",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.CRITICAL


def test_telemetry_disabled(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "info",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry.telemetry_enabled() is False
    assert telemetry.tracer is None


def test_get_tracer_enabled(app_config):
    telemetry = Telemetry("test_service", app_config)
    tracer = telemetry._get_tracer()
    assert tracer is not None
    assert isinstance(tracer, Tracer)


def test_get_tracer_disabled(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "info",
    }.get
    telemetry = Telemetry("test_service", app_config)
    tracer = telemetry._get_tracer()
    assert tracer is None


def test_enable_tracing(app_config):
    telemetry = Telemetry("test_service", app_config)
    with (
        patch("ska_utils.telemetry.OTLPSpanExporter") as mock_otlp_exporter,
        patch("ska_utils.telemetry.TracerProvider") as mock_tracer_provider,
        patch("ska_utils.telemetry.BatchSpanProcessor") as mock_batch_processor,
        patch("opentelemetry.trace.set_tracer_provider") as mock_set_tracer_provider,
    ):
        telemetry._enable_tracing()
        mock_otlp_exporter.assert_called_once_with(endpoint=telemetry.endpoint)
        mock_tracer_provider.assert_called_once_with(resource=telemetry.resource)
        mock_batch_processor.assert_called_once()
        mock_set_tracer_provider.assert_called_once()


def test_enable_tracing_without_endpoint(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "true",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "info",
    }.get
    telemetry = Telemetry("test_service", app_config)
    with (
        patch("ska_utils.telemetry.ConsoleSpanExporter") as mock_console_span_exporter,
        patch("ska_utils.telemetry.TracerProvider") as mock_tracer_provider,
        patch("ska_utils.telemetry.BatchSpanProcessor") as mock_batch_processor,
        patch("opentelemetry.trace.set_tracer_provider") as mock_set_tracer_provider,
    ):
        telemetry._enable_tracing()
        mock_console_span_exporter.assert_called_once()
        mock_tracer_provider.assert_called_once_with(resource=telemetry.resource)
        mock_batch_processor.assert_called_once()
        mock_set_tracer_provider.assert_called_once()


def test_get_logger(app_config):
    telemetry = Telemetry("test_service", app_config)
    logger = telemetry.get_logger("test-logger")
    assert isinstance(logger, logging.Logger)


def test_get_logger_telemetry_disabled(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "info",
    }.get
    telemetry = Telemetry("test_service", app_config)
    logger = telemetry.get_logger("test-logger")
    assert isinstance(logger, logging.Logger)


def test_enable_metrics(app_config):
    telemetry = Telemetry("test_service", app_config)
    with (
        patch("ska_utils.telemetry.OTLPMetricExporter") as mock_otlp_exporter,
        patch("ska_utils.telemetry.ConsoleMetricExporter"),
        patch("ska_utils.telemetry.MeterProvider") as mock_meter_provider,
        patch("ska_utils.telemetry.PeriodicExportingMetricReader"),
        patch("ska_utils.telemetry.set_meter_provider") as mock_set_meter_provider,
    ):
        telemetry._enable_metrics()
        mock_otlp_exporter.assert_called_once_with(endpoint=telemetry.metrics_endpoint)
        mock_meter_provider.assert_called_once()
        mock_set_meter_provider.assert_called_once()


def test_get_telemetry_not_initialized():
    with pytest.raises(ValueError, match="Telemetry not initialized"):
        get_telemetry()


def test_initialize_telemetry(app_config):
    initialize_telemetry("test_service", app_config)
    telemetry = get_telemetry()
    assert telemetry.service_name == "test_service"
