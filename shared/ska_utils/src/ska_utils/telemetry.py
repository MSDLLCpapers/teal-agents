import logging
import mlflow
import os

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
TA_LOG_LEVEL = Config(env_name="TA_LOG_LEVEL", is_required=False, default_value="info")
TA_TRACES_DESTINATION = Config(
    env_name="TA_TRACES_DESTINATION", is_required=False, default_value="aspire"
)
TA_MLFLOW_EXPERIMENT_NAME = Config(env_name="TA_MLFLOW_EXPERIMENT_NAME", is_required=False, default_value="agentic-app-traces")
TELEMETRY_CONFIGS: list[Config] = [TA_TELEMETRY_ENABLED, TA_OTEL_ENDPOINT, TA_LOG_LEVEL, TA_TRACES_DESTINATION, TA_MLFLOW_EXPERIMENT_NAME]

AppConfig.add_configs(TELEMETRY_CONFIGS)


class Telemetry:
    def __init__(self, service_name: str, app_config: AppConfig):
        self.service_name = service_name
        self._handler: LoggingHandler | None = None
        self.resource = Resource.create({ResourceAttributes.SERVICE_NAME: self.service_name})
        self._telemetry_enabled = strtobool(str(app_config.get(TA_TELEMETRY_ENABLED.env_name)))
        self.endpoint = app_config.get(TA_OTEL_ENDPOINT.env_name)
        self.traces_destination = app_config.get(TA_TRACES_DESTINATION.env_name)
        self.mlflow_experiment_name = app_config.get(TA_MLFLOW_EXPERIMENT_NAME.env_name)
        self.tracer: trace.Tracer | None = None#self._get_tracer()
        
        
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
        
        self._check_enable_telemetry()
        if self._telemetry_enabled:
            self.tracer = trace.get_tracer(f"{self.service_name}-tracer")

    def telemetry_enabled(self) -> bool:
        return self._telemetry_enabled

    def _get_tracer(self) -> trace.Tracer | None:
        if self._telemetry_enabled and self.tracer is None:
            self.tracer = trace.get_tracer(f"{self.service_name}-tracer")
        return self.tracer

    def _check_enable_telemetry(self) -> None:
        if not self._telemetry_enabled:
            return

        self._enable_tracing()
        self._enable_logging()
        self._enable_metrics()

    def _enable_tracing(self) -> None:
        if self.traces_destination == "mlflow":
            logging.info(f"Configuring MLflow tracing for experiment: {self.mlflow_experiment_name}")
            try:
                # Set tracking URI if not already set via env var
                if os.environ.get("MLFLOW_TRACKING_URI") is None and os.environ.get("DATABRICKS_HOST"):
                    os.environ["MLFLOW_TRACKING_URI"] = "databricks"
                
                # Check if a tracking URI is now available
                if not os.environ.get("MLFLOW_TRACKING_URI"):
                    logging.warning(
                        "MLflow tracing requested but no MLFLOW_TRACKING_URI, DATABRICKS_HOST, or DATABRICKS_TOKEN is set. "
                        "Traces may not be exported. Falling back to no-op tracer."
                    )
                    trace.set_tracer_provider(trace.NoOpTracerProvider())
                    return
                
                mlflow.set_experiment(self.mlflow_experiment_name)
                # MLflow autologging enables MLflow's internal tracing and context propagation.
                # It is the only thing needed to get MLflow tracing working.
                mlflow.autolog(log_traces=True)
                logging.info("MLflow autolog enabled with log_traces=True.")
                
                # IMPORTANT: With MLflow tracing enabled, it takes over the global TracerProvider.
                # We need to set a no-op provider to avoid conflicting with MLflow's own.
                # MLflow's autolog handles the OpenTelemetry integration internally.
                trace.set_tracer_provider(trace.NoOpTracerProvider())
                
            except Exception as e:
                logging.exception("Failed to configure MLflow tracing: %s", e)
                trace.set_tracer_provider(trace.NoOpTracerProvider()) # Fallback to no-op

            
        elif self.endpoint:
            exporter = OTLPSpanExporter(endpoint=self.endpoint)
            provider = TracerProvider(resource=self.resource)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            print("Exporting traces to OTLP endpoint")
        else:
            exporter = ConsoleSpanExporter()
            provider = TracerProvider(resource=self.resource)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            print("Exporting traces to console")

            
        
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
        if self.endpoint:
            exporter = OTLPLogExporter(endpoint=self.endpoint)
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
    if _services_telemetry is None:
        _services_telemetry = Telemetry(service_name, app_config)
    # _services_telemetry = Telemetry(service_name, app_config)


def get_telemetry() -> Telemetry:
    if _services_telemetry is None:
        raise ValueError("Telemetry not initialized")
    return _services_telemetry
