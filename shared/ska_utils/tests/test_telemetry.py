import logging
from unittest.mock import MagicMock, patch

import pytest

from ska_utils import AppConfig, Telemetry, get_telemetry, initialize_telemetry


@pytest.fixture
def app_config():
    config = MagicMock(spec=AppConfig)
    config.get.side_effect = lambda env_name: "true" if env_name == "TA_TELEMETRY_ENABLED" else None
    return config


def test_telemetry_initialization(app_config):
    telemetry = Telemetry("test_service", app_config)
    assert telemetry.service_name == "test_service"
    assert telemetry.telemetry_enabled() is True


def test_telemetry_disabled(app_config):
    app_config.get.side_effect = (
        lambda env_name: "false" if env_name == "TA_TELEMETRY_ENABLED" else None
    )
    telemetry = Telemetry("test_service", app_config)
    assert telemetry.telemetry_enabled() is False
    assert telemetry.tracer is None


def test_get_tracer_enabled(app_config):
    with patch("ska_utils.telemetry.trace.get_tracer") as mock_get_tracer:
        mock_get_tracer.return_value = MagicMock()
        telemetry = Telemetry("test_service", app_config)
        tracer = telemetry.tracer
        assert tracer is not None
        mock_get_tracer.assert_called_once_with("test_service-tracer")


def test_enable_tracing_with_endpoint(app_config):
    telemetry = Telemetry("test_service", app_config)
    telemetry.endpoint = "http://localhost.4317"
    with (
        patch("ska_utils.telemetry.OTLPSpanExporter") as mock_otlp_exporter,
        patch("ska_utils.telemetry.TracerProvider") as mock_tracer_provider,
        patch("ska_utils.telemetry.BatchSpanProcessor") as mock_batch_span_processor,
        patch("ska_utils.telemetry.trace.set_tracer_provider") as mock_set_tracer_provider,
    ):
        telemetry._enable_tracing()
        mock_otlp_exporter.assert_called_once_with(endpoint=telemetry.endpoint)
        mock_tracer_provider.assert_called_once_with(resource=telemetry.resource)
        mock_batch_span_processor.assert_called_once_with(mock_otlp_exporter.return_value)
        mock_tracer_provider.return_value.add_span_processor.assert_called_once_with(
            mock_batch_span_processor.return_value
        )
        mock_set_tracer_provider.assert_called_once_with(mock_tracer_provider.return_value)


def test_enable_logging_with_endpoint(app_config):
    telemetry = Telemetry("test_service", app_config)
    telemetry.endpoint = "http://localhost.4317"
    with (
        patch("ska_utils.telemetry.OTLPLogExporter") as mock_otlp_exporter,
        patch("ska_utils.telemetry.ConsoleLogExporter"),
        patch("ska_utils.telemetry.LoggerProvider") as mock_logger_provider,
        patch("ska_utils.telemetry.BatchLogRecordProcessor") as mock_batch_log_record_processor,
        patch("ska_utils.telemetry.set_logger_provider") as mock_set_logger_provider,
        patch("ska_utils.telemetry.LoggingHandler") as mock_logging_handler,
        patch("logging.getLogger") as mock_get_logger,
    ):
        mock_logger_instance = MagicMock()
        mock_get_logger.return_value = mock_logger_instance
        telemetry._enable_logging()
        mock_otlp_exporter.assert_called_once_with(endpoint=telemetry.endpoint)
        mock_logger_provider.assert_called_once_with(resource=telemetry.resource)
        mock_batch_log_record_processor.assert_called_once_with(mock_otlp_exporter.return_value)
        mock_logger_provider.return_value.add_log_record_processor.assert_called_once_with(
            mock_batch_log_record_processor.return_value
        )
        mock_set_logger_provider.assert_called_once_with(mock_logger_provider.return_value)
        mock_logging_handler.assert_called_once()
        mock_logger_instance.addHandler.assert_called_once_with(mock_logging_handler.return_value)
        mock_logger_instance.setLevel.assert_called_once_with(logging.INFO)


def test_enable_metrics_with_endpoint(app_config):
    telemetry = Telemetry("test_service", app_config)
    telemetry.endpoint = "http://localhost.4317"
    with (
        patch("ska_utils.telemetry.OTLPMetricExporter") as mock_otlp_metric_exporter,
        patch(
            "ska_utils.telemetry.PeriodicExportingMetricReader"
        ) as mock_periodic_exporting_metric_reader,
    ):
        telemetry._enable_metrics()
        mock_otlp_metric_exporter.assert_called_once_with(endpoint=telemetry.endpoint)
        mock_periodic_exporting_metric_reader.assert_called_once_with(
            mock_otlp_metric_exporter.return_value, export_interval_millis=5000
        )


def test_get_telemetry_not_initialized():
    with pytest.raises(ValueError, match="Telemetry not initialized"):
        get_telemetry()


def test_initialize_telemetry(app_config):
    initialize_telemetry("test_service", app_config)
    telemetry = get_telemetry()
    assert telemetry.service_name == "test_service"
