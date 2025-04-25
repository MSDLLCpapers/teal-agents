import logging

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter, LogExporter
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

from ska_utils import AppConfig, Config, strtobool

TA_TELEMETRY_ENABLED = Config(
    env_name="TA_TELEMETRY_ENABLED", is_required=True, default_value="true"
)
TA_OTEL_ENDPOINT = Config(env_name="TA_OTEL_ENDPOINT", is_required=False, default_value=None)

TELEMETRY_CONFIGS: list[Config] = [TA_TELEMETRY_ENABLED, TA_OTEL_ENDPOINT]

AppConfig.add_configs(TELEMETRY_CONFIGS)


class Telemetry:
    def __init__(self, service_name: str, app_config: AppConfig):
        self.service_name = service_name
        self.resource = Resource.create({ResourceAttributes.SERVICE_NAME: self.service_name})
        self._telemetry_enabled = strtobool(str(app_config.get(TA_TELEMETRY_ENABLED.env_name)))
        self.endpoint = app_config.get(TA_OTEL_ENDPOINT.env_name)
        self._check_enable_telemetry()
        self.tracer: trace.Tracer | None = self._get_tracer()

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
        self._enable_logging()
        self._enable_metrics()

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

    def _enable_logging(self) -> None:
        exporter: LogExporter
        if self.endpoint:
            exporter = OTLPLogExporter(endpoint=self.endpoint)
        else:
            exporter = ConsoleLogExporter()

        logger_provider = LoggerProvider(resource=self.resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        set_logger_provider(logger_provider)

        handler = LoggingHandler()
        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def _enable_metrics(self) -> None:
        exporter: MetricExporter
        if self.endpoint:
            exporter = OTLPMetricExporter(endpoint=self.endpoint)
        else:
            exporter = ConsoleMetricExporter()

        meter_provider = MeterProvider(
            metric_readers=[PeriodicExportingMetricReader(exporter, export_interval_millis=5000)],
            resource=self.resource,
            views=[
                # Dropping all instrument names except for those starting with "semantic_kernel"
                View(instrument_name="*", aggregation=DropAggregation()),
                View(instrument_name="semantic_kernel*"),
            ],
        )
        set_meter_provider(meter_provider)


_services_telemetry: Telemetry | None = None


def initialize_telemetry(service_name: str, app_config: AppConfig) -> None:
    global _services_telemetry
    _services_telemetry = Telemetry(service_name, app_config)


def get_telemetry() -> Telemetry:
    if _services_telemetry is None:
        raise ValueError("Telemetry not initialized")
    return _services_telemetry
