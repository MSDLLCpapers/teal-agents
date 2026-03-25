import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.trace import Tracer

from ska_utils import AppConfig, Telemetry, get_telemetry, initialize_telemetry
from ska_utils.telemetry import AgentTelemetryLogger


@pytest.fixture
def app_config():
    config = MagicMock(spec=AppConfig)
    config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "true",
        "TA_METRICS_ENABLED": "true",
        "TA_LOGGING_ENABLED": "true",
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
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "debug",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.DEBUG


def test_telemetry_initialization_warning(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "warning",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.WARNING


def test_telemetry_initialization_error(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "error",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.ERROR


def test_telemetry_initialization_critical(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "critical",
    }.get
    telemetry = Telemetry("test_service", app_config)
    assert telemetry._log_level == logging.CRITICAL


def test_telemetry_disabled(app_config):
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
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
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
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
        "TA_METRICS_ENABLED": "true",
        "TA_LOGGING_ENABLED": "true",
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
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
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


# ===================================================================
# Tests for AgentTelemetryLogger
# ===================================================================


@pytest.fixture
def telemetry_disabled(app_config):
    """Create a telemetry instance with telemetry disabled."""
    app_config.get.side_effect = {
        "TA_TELEMETRY_ENABLED": "false",
        "TA_METRICS_ENABLED": "false",
        "TA_LOGGING_ENABLED": "false",
        "TA_OTEL_ENDPOINT": None,
        "TA_LOG_LEVEL": "info",
    }.get
    return Telemetry("test_service", app_config)


@pytest.fixture
def telemetry_enabled(app_config):
    """Create a telemetry instance with telemetry enabled."""
    return Telemetry("test_service", app_config)


@pytest.fixture
def agent_logger(telemetry_disabled):
    """Create an AgentTelemetryLogger for testing."""
    return AgentTelemetryLogger(
        telemetry=telemetry_disabled,
        agent_name="weather_agent",
        model_name="gpt-4o",
        user_isid="user123",
    )


class TestAgentTelemetryLoggerInit:
    def test_initial_state(self, agent_logger):
        assert agent_logger.agent_name == "weather_agent"
        assert agent_logger.model_name == "gpt-4o"
        assert agent_logger.user_isid == "user123"
        assert agent_logger.tool_calls == []
        assert agent_logger.tool_call_count == 0
        assert agent_logger.internal_function_calls == []
        assert agent_logger.reasoning_entries == []
        assert agent_logger.invocation_count == 0

    def test_init_without_user_isid(self, telemetry_disabled):
        logger = AgentTelemetryLogger(
            telemetry=telemetry_disabled,
            agent_name="test_agent",
            model_name="gpt-4o",
        )
        assert logger.user_isid is None


class TestAgentTelemetryLoggerRecording:
    def test_record_tool_call(self, agent_logger):
        agent_logger.record_tool_call("get_weather")
        assert agent_logger.tool_calls == ["get_weather"]
        assert agent_logger.tool_call_count == 1

    def test_record_multiple_tool_calls(self, agent_logger):
        agent_logger.record_tool_call("get_weather")
        agent_logger.record_tool_call("get_location")
        assert agent_logger.tool_calls == ["get_weather", "get_location"]
        assert agent_logger.tool_call_count == 2

    def test_record_tool_calls_batch(self, agent_logger):
        agent_logger.record_tool_calls(["get_weather", "get_location", "get_time"])
        assert agent_logger.tool_calls == ["get_weather", "get_location", "get_time"]
        assert agent_logger.tool_call_count == 3

    def test_record_internal_function_call(self, agent_logger):
        agent_logger.record_internal_function_call("WeatherPlugin.get_weather")
        assert agent_logger.internal_function_calls == ["WeatherPlugin.get_weather"]

    def test_record_reasoning(self, agent_logger):
        agent_logger.record_reasoning("I need to check the weather first")
        assert agent_logger.reasoning_entries == ["I need to check the weather first"]

    def test_record_reasoning_empty_string_ignored(self, agent_logger):
        agent_logger.record_reasoning("")
        assert agent_logger.reasoning_entries == []

    def test_record_invocation(self, agent_logger):
        agent_logger.record_invocation()
        assert agent_logger.invocation_count == 1
        agent_logger.record_invocation()
        assert agent_logger.invocation_count == 2

    def test_tool_calls_returns_copy(self, agent_logger):
        agent_logger.record_tool_call("get_weather")
        calls = agent_logger.tool_calls
        calls.append("mutated")
        assert agent_logger.tool_calls == ["get_weather"]


class TestAgentTelemetryLoggerStandardizedLog:
    def test_get_standardized_log_basic(self, agent_logger):
        log_data = agent_logger.get_standardized_log()
        assert log_data["agent.name"] == "weather_agent"
        assert log_data["agent.model"] == "gpt-4o"
        assert log_data["agent.tool_calls"] == []
        assert log_data["agent.tool_call_count"] == 0
        assert log_data["agent.user_isid"] == "user123"
        assert log_data["agent.invocation_count"] == 0
        assert log_data["agent.session_id"] == ""
        assert log_data["agent.request_id"] == ""
        assert log_data["agent.completion_tokens"] == 0
        assert log_data["agent.prompt_tokens"] == 0
        assert log_data["agent.total_tokens"] == 0

    def test_get_standardized_log_with_tool_calls(self, agent_logger):
        agent_logger.record_tool_calls(["get_weather", "get_location"])
        agent_logger.record_internal_function_call("WeatherPlugin.get_weather")
        agent_logger.record_reasoning("reasoning_tokens=50")
        agent_logger.record_invocation()

        log_data = agent_logger.get_standardized_log(
            session_id="sess-123",
            request_id="req-456",
            completion_tokens=100,
            prompt_tokens=200,
            total_tokens=300,
        )
        assert log_data["agent.name"] == "weather_agent"
        assert log_data["agent.model"] == "gpt-4o"
        assert log_data["agent.tool_calls"] == ["get_weather", "get_location"]
        assert log_data["agent.tool_call_count"] == 2
        assert log_data["agent.internal_function_calls"] == ["WeatherPlugin.get_weather"]
        assert log_data["agent.internal_function_call_count"] == 1
        assert log_data["agent.reasoning"] == ["reasoning_tokens=50"]
        assert log_data["agent.user_isid"] == "user123"
        assert log_data["agent.invocation_count"] == 1
        assert log_data["agent.session_id"] == "sess-123"
        assert log_data["agent.request_id"] == "req-456"
        assert log_data["agent.completion_tokens"] == 100
        assert log_data["agent.prompt_tokens"] == 200
        assert log_data["agent.total_tokens"] == 300

    def test_get_standardized_log_no_user_isid(self, telemetry_disabled):
        logger = AgentTelemetryLogger(
            telemetry=telemetry_disabled,
            agent_name="test_agent",
            model_name="gpt-4o",
        )
        log_data = logger.get_standardized_log()
        assert log_data["agent.user_isid"] == ""

    def test_emit_log(self, agent_logger):
        agent_logger.record_tool_call("get_weather")
        with patch.object(agent_logger._logger, "info") as mock_info:
            log_data = agent_logger.emit_log(
                session_id="sess-1",
                request_id="req-1",
                completion_tokens=10,
                prompt_tokens=20,
                total_tokens=30,
            )
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            # Verify the log message contains JSON
            log_message_json = call_args[0][1]
            parsed = json.loads(log_message_json)
            assert parsed["agent.name"] == "weather_agent"
            assert parsed["agent.tool_calls"] == ["get_weather"]
            assert parsed["agent.tool_call_count"] == 1

        # Also verify the returned dict
        assert log_data["agent.name"] == "weather_agent"
        assert log_data["agent.total_tokens"] == 30


class TestAgentTelemetryLoggerSpanEnrichment:
    def test_enrich_span(self, agent_logger):
        mock_span = MagicMock()
        agent_logger.record_tool_calls(["get_weather", "get_location"])
        agent_logger.record_internal_function_call("WeatherPlugin.get_weather")
        agent_logger.record_reasoning("reasoning_tokens=50")
        agent_logger.record_invocation()

        agent_logger.enrich_span(
            span=mock_span,
            session_id="sess-1",
            request_id="req-1",
            completion_tokens=100,
            prompt_tokens=200,
            total_tokens=300,
            time_to_first_token_ms=42.5,
        )

        mock_span.set_attribute.assert_any_call("agent.name", "weather_agent")
        mock_span.set_attribute.assert_any_call("agent.model", "gpt-4o")
        mock_span.set_attribute.assert_any_call(
            "agent.tool_calls", ["get_weather", "get_location"]
        )
        mock_span.set_attribute.assert_any_call("agent.tool_call_count", 2)
        mock_span.set_attribute.assert_any_call(
            "agent.internal_function_calls", ["WeatherPlugin.get_weather"]
        )
        mock_span.set_attribute.assert_any_call("agent.internal_function_call_count", 1)
        mock_span.set_attribute.assert_any_call("agent.invocation_count", 1)
        mock_span.set_attribute.assert_any_call("agent.user_isid", "user123")
        mock_span.set_attribute.assert_any_call("agent.session_id", "sess-1")
        mock_span.set_attribute.assert_any_call("agent.request_id", "req-1")
        mock_span.set_attribute.assert_any_call("agent.completion_tokens", 100)
        mock_span.set_attribute.assert_any_call("agent.prompt_tokens", 200)
        mock_span.set_attribute.assert_any_call("agent.total_tokens", 300)
        mock_span.set_attribute.assert_any_call("agent.reasoning", ["reasoning_tokens=50"])
        mock_span.add_event.assert_called_once_with(
            "agent_time_to_first_token",
            attributes={"first_token_time_ms": 42.5},
        )

    def test_enrich_span_none(self, agent_logger):
        # Should not raise when span is None
        agent_logger.enrich_span(span=None)

    def test_enrich_span_no_reasoning(self, agent_logger):
        mock_span = MagicMock()
        agent_logger.enrich_span(span=mock_span)
        # Reasoning should not be set if empty
        reasoning_calls = [
            call for call in mock_span.set_attribute.call_args_list
            if call[0][0] == "agent.reasoning"
        ]
        assert len(reasoning_calls) == 0

    def test_enrich_span_no_ttft(self, agent_logger):
        mock_span = MagicMock()
        agent_logger.enrich_span(span=mock_span)
        mock_span.add_event.assert_not_called()


class TestAgentTelemetryLoggerTraceContext:
    def test_trace_agent_invocation_disabled(self, telemetry_disabled):
        logger = AgentTelemetryLogger(
            telemetry=telemetry_disabled,
            agent_name="test_agent",
            model_name="gpt-4o",
        )
        with logger.trace_agent_invocation("test-span") as span:
            assert span is None
        assert logger.invocation_count == 1

    def test_trace_agent_invocation_enabled(self, telemetry_enabled):
        logger = AgentTelemetryLogger(
            telemetry=telemetry_enabled,
            agent_name="test_agent",
            model_name="gpt-4o",
        )
        with logger.trace_agent_invocation("test-span", session_id="s1") as span:
            assert span is not None
        assert logger.invocation_count == 1

    def test_trace_agent_invocation_increments_count(self, telemetry_disabled):
        logger = AgentTelemetryLogger(
            telemetry=telemetry_disabled,
            agent_name="test_agent",
            model_name="gpt-4o",
        )
        with logger.trace_agent_invocation("span-1"):
            pass
        with logger.trace_agent_invocation("span-2"):
            pass
        assert logger.invocation_count == 2
