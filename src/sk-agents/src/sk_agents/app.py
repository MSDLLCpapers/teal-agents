import logging
import uuid
from datetime import datetime
from enum import Enum

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, get_telemetry, initialize_telemetry

from sk_agents.appv1 import AppV1
from sk_agents.appv2 import AppV2
from sk_agents.appv3 import AppV3
from sk_agents.config_validator import validate_config_or_raise
from sk_agents.configs import (
    TA_SERVICE_CONFIG,
    configs,
)
from sk_agents.error_models import ErrorDetail, ErrorResponse, create_error_response
from sk_agents.exceptions import (
    AgentAuthenticationError,
    AgentConfigurationError,
    AgentException,
    AgentExecutionError,
    AgentResourceError,
    AgentStateError,
    AgentTimeoutError,
    AgentValidationError,
)
from sk_agents.middleware import TelemetryMiddleware
from sk_agents.ska_types import (
    BaseConfig,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AppVersion(Enum):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"


try:
    AppConfig.add_configs(configs)
    app_config = AppConfig()

    # Validate configuration at startup
    logger.info("Validating configuration...")
    try:
        validate_config_or_raise(app_config)
        logger.info("Configuration validation passed ✓")
    except AgentConfigurationError as e:
        logger.error(f"Configuration validation failed: {e.message}")
        if e.details:
            logger.error(f"Details: {e.details}")
        raise SystemExit(1)

    config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
    if not config_file:
        raise AgentConfigurationError(
            message=f"Configuration file path not found for {TA_SERVICE_CONFIG.env_name}",
            error_code="CFG-003",
        )
    try:
        config: BaseConfig = parse_yaml_file_as(BaseConfig, config_file)
    except Exception as e:
        logger.exception(f"Failed to parse YAML configuration: {e}")
        raise AgentConfigurationError(
            message=f"Failed to parse YAML configuration file: {config_file}",
            error_code="CFG-002",
            details={"file": config_file, "error": str(e)},
        )

    try:
        (root_handler, api_version) = config.apiVersion.split("/")
    except ValueError as e:
        logger.exception("Invalid API version format")
        raise AgentConfigurationError(
            message=f"Invalid API version format: {config.apiVersion}",
            error_code="CFG-004",
            details={"api_version": config.apiVersion},
        )

    name: str | None = None
    version = str(config.version)
    app_version: str | None = None

    if root_handler == "tealagents":
        if api_version == "v1alpha1":
            app_version = AppVersion.V3
            name = config.name
    elif root_handler == "skagents":
        if api_version == "v2alpha1":
            app_version = AppVersion.V2
            name = config.name
        else:
            app_version = AppVersion.V1
            name = config.service_name

    if not app_version:
        raise AgentConfigurationError(
            message=f"Invalid apiVersion defined in configuration file: {config.apiVersion}",
            error_code="CFG-004",
            details={"api_version": config.apiVersion},
        )
    if not name:
        raise AgentConfigurationError(
            message="Service name is not defined in the configuration file",
            error_code="CFG-005",
        )
    if not version:
        raise AgentConfigurationError(
            message="Service version is not defined in the configuration file",
            error_code="CFG-005",
        )

    initialize_telemetry(f"{name}-{version}", app_config)

    app = FastAPI(
        openapi_url=f"/{name}/{version}/openapi.json",
        docs_url=f"/{name}/{version}/docs",
        redoc_url=f"/{name}/{version}/redoc",
    )
    # noinspection PyTypeChecker
    app.add_middleware(TelemetryMiddleware, st=get_telemetry())

    # ============================================================================
    # Global Exception Handlers
    # ============================================================================

    @app.exception_handler(AgentConfigurationError)
    async def configuration_error_handler(
        request: Request, exc: AgentConfigurationError
    ) -> JSONResponse:
        """Handle configuration errors (HTTP 503)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.error(
            f"Configuration error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "trace_id": trace_id,
                "path": str(request.url.path),
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error="Configuration Error",
                error_code=exc.error_code,
                message=exc.message,
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(AgentAuthenticationError)
    async def authentication_error_handler(
        request: Request, exc: AgentAuthenticationError
    ) -> JSONResponse:
        """Handle authentication errors (HTTP 401)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.warning(
            f"Authentication error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "trace_id": trace_id,
                "path": str(request.url.path),
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error="Authentication Error",
                error_code=exc.error_code,
                message=exc.message,
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(AgentValidationError)
    async def validation_error_handler(
        request: Request, exc: AgentValidationError
    ) -> JSONResponse:
        """Handle validation errors (HTTP 400)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.warning(
            f"Validation error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "trace_id": trace_id,
                "path": str(request.url.path),
                "details": exc.details,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error="Validation Error",
                error_code=exc.error_code,
                message=exc.message,
                details=(
                    [
                        ErrorDetail(code=exc.error_code, message=str(v), field=k)
                        for k, v in exc.details.items()
                    ]
                    if exc.details
                    else None
                ),
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(AgentExecutionError)
    async def execution_error_handler(
        request: Request, exc: AgentExecutionError
    ) -> JSONResponse:
        """Handle execution errors (HTTP 500)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.error(
            f"Execution error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "trace_id": trace_id,
                "path": str(request.url.path),
                "details": exc.details,
            },
            exc_info=True,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error="Execution Error",
                error_code=exc.error_code,
                message=exc.message,
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(AgentTimeoutError)
    async def timeout_error_handler(request: Request, exc: AgentTimeoutError) -> JSONResponse:
        """Handle timeout errors (HTTP 504)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.warning(
            f"Timeout error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "trace_id": trace_id,
                "path": str(request.url.path),
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error="Timeout Error",
                error_code=exc.error_code,
                message=exc.message,
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(AgentResourceError)
    async def resource_error_handler(
        request: Request, exc: AgentResourceError
    ) -> JSONResponse:
        """Handle resource errors (HTTP 503)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.error(
            f"Resource error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "trace_id": trace_id,
                "path": str(request.url.path),
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error="Resource Error",
                error_code=exc.error_code,
                message=exc.message,
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(AgentStateError)
    async def state_error_handler(request: Request, exc: AgentStateError) -> JSONResponse:
        """Handle state management errors (HTTP 409)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.warning(
            f"State error: {exc.message}",
            extra={
                "error_code": exc.error_code,
                "trace_id": trace_id,
                "path": str(request.url.path),
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error="State Error",
                error_code=exc.error_code,
                message=exc.message,
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def pydantic_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors from FastAPI (HTTP 400)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        errors = exc.errors()
        logger.warning(
            f"Request validation failed: {len(errors)} error(s)",
            extra={"trace_id": trace_id, "path": str(request.url.path), "errors": errors},
        )

        details = [
            ErrorDetail(
                code="VAL-001",
                message=err.get("msg", "Validation error"),
                field=".".join(str(loc) for loc in err.get("loc", [])),
            )
            for err in errors
        ]

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=create_error_response(
                error="Validation Error",
                error_code="VAL-001",
                message="Request validation failed",
                details=details,
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle FastAPI HTTP exceptions."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.warning(
            f"HTTP {exc.status_code} error: {exc.detail}",
            extra={"trace_id": trace_id, "path": str(request.url.path)},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error=f"HTTP {exc.status_code} Error",
                error_code=f"HTTP-{exc.status_code}",
                message=str(exc.detail),
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler for unexpected exceptions (HTTP 500)."""
        trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
        logger.exception(
            f"Unexpected error: {str(exc)}",
            extra={"trace_id": trace_id, "path": str(request.url.path)},
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=create_error_response(
                error="Internal Server Error",
                error_code="EXEC-005",
                message="An unexpected error occurred. Please contact support with the trace ID.",
                trace_id=trace_id,
                path=str(request.url.path),
            ).model_dump(),
        )

    # ============================================================================
    # End of Exception Handlers
    # ============================================================================

    match app_version:
        case AppVersion.V1:
            AppV1.run(name, version, app_config, config, app)
        case AppVersion.V2:
            # DEPRECATION NOTICE: AppV2 and its A2A functionality is deprecated.
            # Maintained for backward compatibility only. Avoid A2A for new development.
            AppV2.run(name, version, app_config, config, app)
        case AppVersion.V3:
            AppV3.run(name, version, app_config, config, app)

except AgentConfigurationError as e:
    # Configuration errors are already logged and should exit gracefully
    logger.error(f"Application startup failed due to configuration error: {e.message}")
    raise SystemExit(1)
except Exception as e:
    logger.exception(f"Application failed to start due to an unexpected error: {e}")
    raise SystemExit(1)
