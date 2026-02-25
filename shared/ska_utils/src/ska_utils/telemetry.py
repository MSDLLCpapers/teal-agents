import json
import logging
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogExporter,
    LogExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import DropAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)
from opentelemetry.semconv.resource import ResourceAttributes

from ska_utils.app_config import AppConfig, Config
from ska_utils.strtobool import strtobool

TA_TELEMETRY_ENABLED = Config(
    env_name="TA_TELEMETRY_ENABLED", is_required=True, default_value="true"
)
TA_OTEL_ENDPOINT = Config(env_name="TA_OTEL_ENDPOINT", is_required=False, default_value=None)
TA_OTEL_LOGGING_ENDPOINT = Config(
    env_name="TA_OTEL_LOGGING_ENDPOINT", is_required=False, default_value=None
)
TA_OTEL_METRICS_ENDPOINT = Config(
    env_name="TA_OTEL_METRICS_ENDPOINT", is_required=False, default_value=None
)

TA_LOG_LEVEL = Config(env_name="TA_LOG_LEVEL", is_required=False, default_value="info")

TA_METRICS_ENABLED = Config(env_name="TA_METRICS_ENABLED", is_required=True, default_value="false")

TA_LOGGING_ENABLED = Config(env_name="TA_LOGGING_ENABLED", is_required=True, default_value="false")

TELEMETRY_CONFIGS: list[Config] = [
    TA_TELEMETRY_ENABLED,
    TA_OTEL_ENDPOINT,
    TA_LOG_LEVEL,
    TA_OTEL_LOGGING_ENDPOINT,
    TA_OTEL_METRICS_ENDPOINT,
    TA_METRICS_ENABLED,
    TA_LOGGING_ENABLED
]

AppConfig.add_configs(TELEMETRY_CONFIGS)


class Telemetry:
    def __init__(self, service_name: str, app_config: AppConfig):
        self.service_name = service_name
        self._handler: LoggingHandler | None = None
        self.resource = Resource.create({ResourceAttributes.SERVICE_NAME: self.service_name})
        self._telemetry_enabled = strtobool(str(app_config.get(TA_TELEMETRY_ENABLED.env_name)))
        self._metrics_enabled = strtobool(str(app_config.get(TA_METRICS_ENABLED.env_name)))
        self._logging_enabled = strtobool(str(app_config.get(TA_LOGGING_ENABLED.env_name)))
        self.endpoint = app_config.get(TA_OTEL_ENDPOINT.env_name)
        self.logging_endpoint = app_config.get(TA_OTEL_LOGGING_ENDPOINT.env_name)
        self.metrics_endpoint = app_config.get(TA_OTEL_METRICS_ENDPOINT.env_name)
        self._check_enable_telemetry()
        self.tracer: trace.Tracer | None = self._get_tracer()

        match app_config.get(TA_LOG_LEVEL.env_name):
            case "debug":
                self._log_level = logging.DEBUG
            case "warning":
                self._log_level = logging.WARNING
            case "error":
                self._log_level = logging.ERROR
            case "critical":
                self._log_level = logging.CRITICAL
            case _:
                self._log_level = logging.INFO

    def telemetry_enabled(self) -> bool:
        return self._telemetry_enabled

    def _get_tracer(self) -> trace.Tracer | None:
        if self._telemetry_enabled:
            return trace.get_tracer(f"{self.service_name}-tracer")
        else:
            return None

    def _check_enable_telemetry(self) -> None:
        if not self._telemetry_enabled:
            return

        self._enable_tracing()

        if self._metrics_enabled:
            self._enable_metrics()

        if self._logging_enabled:
            self._enable_logging()

    def _enable_tracing(self) -> None:
        exporter: SpanExporter
        if self.endpoint:
            exporter = OTLPSpanExporter(endpoint=self.endpoint)
        else:
            exporter = ConsoleSpanExporter()

        provider = TracerProvider(resource=self.resource)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

        trace.set_tracer_provider(provider)

    def get_logger(self, name: str) -> logging.Logger:
        if not self._telemetry_enabled:
            logger = logging.getLogger(name)
            logger.setLevel(self._log_level)
            return logger

        logger = logging.getLogger(name)
        logger.addHandler(self._get_handler())
        logger.setLevel(self._log_level)
        logger.propagate = False
        return logger

    def _get_handler(self) -> LoggingHandler:
        if self._handler is None:
            self._handler = LoggingHandler()
        return self._handler

    def _enable_logging(self) -> None:
        exporter: LogExporter
        if self.logging_endpoint:
            exporter = OTLPLogExporter(endpoint=self.logging_endpoint)
        else:
            exporter = ConsoleLogExporter()

        logger_provider = LoggerProvider(resource=self.resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        set_logger_provider(logger_provider)

        logger = logging.getLogger()
        logger.addHandler(self._get_handler())
        logger.setLevel(logging.INFO)

    def _enable_metrics(self) -> None:
        exporter: MetricExporter
        if self.metrics_endpoint:
            exporter = OTLPMetricExporter(endpoint=self.metrics_endpoint)
        else:
            exporter = ConsoleMetricExporter()

        meter_provider = MeterProvider(
            metric_readers=[PeriodicExportingMetricReader(exporter, export_interval_millis=5000)],
            resource=self.resource,
            views=[
                # Dropping all instrument names except
                # for those starting with "semantic_kernel"
                View(instrument_name="*", aggregation=DropAggregation()),
                View(instrument_name="semantic_kernel*"),
            ],
        )
        set_meter_provider(meter_provider)


class AgentTelemetryLogger:
    """Provides standardized structured telemetry logging and span enrichment
    for agent invocations.

    Captures metadata including: agent name, model used, tool calls,
    tool call count, reasoning/thinking, user ISID, internal function calls,
    and token usage.

    Log output follows a standardized JSON-like format:
        {
            "agent.name": "weather agent",
            "agent.model": "gpt-4o",
            "agent.tool_calls": ["get_weather", "get_location"],
            "agent.tool_call_count": 2,
            "agent.reasoning": "...",
            "agent.user_isid": "user123",
            ...
        }
    """

    def __init__(
        self,
        agent_name: str,
        model_name: str,
        user_isid: str | None = None,
        telemetry: "Telemetry | None" = None,
    ):
        self._telemetry = telemetry
        self._logger = logging.getLogger(f"agent_telemetry.{agent_name}")
        self._agent_name = agent_name
        self._model_name = model_name
        self._user_isid = user_isid
        self._tool_calls: list[str] = []
        self._internal_function_calls: list[str] = []
        self._reasoning_entries: list[str] = []
        self._invocation_count: int = 0

    @property
    def agent_name(self) -> str:
        return self._agent_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def user_isid(self) -> str | None:
        return self._user_isid

    @property
    def tool_calls(self) -> list[str]:
        return list(self._tool_calls)

    @property
    def tool_call_count(self) -> int:
        return len(self._tool_calls)

    @property
    def internal_function_calls(self) -> list[str]:
        return list(self._internal_function_calls)

    @property
    def reasoning_entries(self) -> list[str]:
        return list(self._reasoning_entries)

    @property
    def invocation_count(self) -> int:
        return self._invocation_count

    def record_tool_call(self, tool_name: str) -> None:
        """Record a tool/plugin call made by the agent."""
        self._tool_calls.append(tool_name)

    def record_tool_calls(self, tool_names: list[str]) -> None:
        """Record multiple tool/plugin calls made by the agent."""
        self._tool_calls.extend(tool_names)

    def record_internal_function_call(self, function_name: str) -> None:
        """Record an internal function call (kernel function invocation)."""
        self._internal_function_calls.append(function_name)

    def record_reasoning(self, reasoning: str) -> None:
        """Record a reasoning/thinking step performed by the agent."""
        if reasoning:
            self._reasoning_entries.append(reasoning)

    def record_invocation(self) -> None:
        """Increment the agent invocation counter."""
        self._invocation_count += 1

    def get_standardized_log(
        self,
        session_id: str | None = None,
        request_id: str | None = None,
        completion_tokens: int = 0,
        prompt_tokens: int = 0,
        total_tokens: int = 0,
    ) -> dict[str, Any]:
        """Return the standardized metadata dict for structured logging.

        Returns a dict with keys following the ``agent.*`` namespace:
            agent.name, agent.model, agent.tool_calls, agent.tool_call_count,
            agent.internal_function_calls, agent.internal_function_call_count,
            agent.reasoning, agent.user_isid, agent.invocation_count,
            agent.session_id, agent.request_id, agent.completion_tokens,
            agent.prompt_tokens, agent.total_tokens.
        """
        log_data: dict[str, Any] = {
            "agent.name": self._agent_name,
            "agent.model": self._model_name,
            "agent.tool_calls": list(self._tool_calls),
            "agent.tool_call_count": self.tool_call_count,
            "agent.internal_function_calls": list(self._internal_function_calls),
            "agent.internal_function_call_count": len(self._internal_function_calls),
            "agent.reasoning": list(self._reasoning_entries),
            "agent.user_isid": self._user_isid or "",
            "agent.invocation_count": self._invocation_count,
            "agent.session_id": session_id or "",
            "agent.request_id": request_id or "",
            "agent.completion_tokens": completion_tokens,
            "agent.prompt_tokens": prompt_tokens,
            "agent.total_tokens": total_tokens,
        }
        return log_data

    def emit_log(
        self,
        session_id: str | None = None,
        request_id: str | None = None,
        completion_tokens: int = 0,
        prompt_tokens: int = 0,
        total_tokens: int = 0,
    ) -> dict[str, Any]:
        """Emit a structured log message with all collected agent metadata.

        Returns the log data dict for convenience.
        """
        log_data = self.get_standardized_log(
            session_id=session_id,
            request_id=request_id,
            completion_tokens=completion_tokens,
            prompt_tokens=prompt_tokens,
            total_tokens=total_tokens,
        )
        self._logger.info("agent_invocation_summary: %s", json.dumps(log_data))
        return log_data

    def enrich_span(
        self,
        span: trace.Span | None,
        session_id: str | None = None,
        request_id: str | None = None,
        completion_tokens: int = 0,
        prompt_tokens: int = 0,
        total_tokens: int = 0,
        time_to_first_token_ms: float | None = None,
    ) -> None:
        """Enrich an OpenTelemetry span with all collected agent metadata."""
        if span is None:
            return

        span.set_attribute("agent.name", self._agent_name)
        span.set_attribute("agent.model", self._model_name)
        span.set_attribute("agent.tool_calls", list(self._tool_calls))
        span.set_attribute("agent.tool_call_count", self.tool_call_count)
        span.set_attribute(
            "agent.internal_function_calls", list(self._internal_function_calls)
        )
        span.set_attribute(
            "agent.internal_function_call_count", len(self._internal_function_calls)
        )
        span.set_attribute("agent.invocation_count", self._invocation_count)
        span.set_attribute("agent.user_isid", self._user_isid or "")
        span.set_attribute("agent.session_id", session_id or "")
        span.set_attribute("agent.request_id", request_id or "")
        span.set_attribute("agent.completion_tokens", completion_tokens)
        span.set_attribute("agent.prompt_tokens", prompt_tokens)
        span.set_attribute("agent.total_tokens", total_tokens)

        if self._reasoning_entries:
            span.set_attribute("agent.reasoning", list(self._reasoning_entries))

        if time_to_first_token_ms is not None:
            span.add_event(
                "agent_time_to_first_token",
                attributes={"first_token_time_ms": time_to_first_token_ms},
            )

    @contextmanager
    def trace_agent_invocation(
        self,
        span_name: str,
        session_id: str | None = None,
        request_id: str | None = None,
    ):
        """Context manager that creates a span for agent invocation and
        automatically enriches it on exit with all collected metadata.

        Usage::

            with agent_logger.trace_agent_invocation("handler-invoke") as span:
                # ... perform agent work, record tool calls, etc.
                pass
            # span is automatically enriched on exit

        Yields the span (or ``None`` if telemetry is disabled).
        """
        from contextlib import nullcontext

        self.record_invocation()

        if (
            self._telemetry is not None
            and self._telemetry.telemetry_enabled()
            and self._telemetry.tracer
        ):
            with self._telemetry.tracer.start_as_current_span(span_name) as span:
                yield span
        else:
            yield None


_services_telemetry: Telemetry | None = None


def initialize_telemetry(service_name: str, app_config: AppConfig) -> None:
    global _services_telemetry
    _services_telemetry = Telemetry(service_name, app_config)


def get_telemetry() -> Telemetry:
    if _services_telemetry is None:
        raise ValueError("Telemetry not initialized")
    return _services_telemetry
