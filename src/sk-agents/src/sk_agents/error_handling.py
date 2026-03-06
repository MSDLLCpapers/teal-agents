"""
Comprehensive Error Handling for Teal Agents (CDW-1653)

This module provides:
- Custom exception classes with HTTP status code mapping
- Standardized error response models
- Error code constants organized by category
- Helper functions for error response creation

Usage:
    from sk_agents.error_handling import (
        AgentValidationError,
        ERROR_MISSING_REQUIRED_FIELD,
        ErrorResponse
    )
    
    raise AgentValidationError(
        message="Missing required field",
        error_code=ERROR_MISSING_REQUIRED_FIELD,
        details={"field": "input"}
    )
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# ============================================================================
# Exception Classes
# ============================================================================

class AgentException(Exception):
    """
    Base exception for all agent-related errors with error codes.
    
    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code (e.g., "CFG-001")
        details: Additional context about the error
        status_code: HTTP status code to return
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        details: dict[str, Any] | None = None,
        status_code: int = 500,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"


class AgentConfigurationError(AgentException):
    """Configuration errors (missing env vars, invalid config, etc.) - HTTP 503"""
    def __init__(self, message: str, error_code: str = "CFG-000", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details, status_code=503)


class AgentAuthenticationError(AgentException):
    """Authentication failures (missing/invalid tokens, etc.) - HTTP 401"""
    def __init__(self, message: str, error_code: str = "AUTH-000", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details, status_code=401)


class AgentValidationError(AgentException):
    """Input validation failures (missing fields, invalid format, etc.) - HTTP 400"""
    def __init__(self, message: str, error_code: str = "VAL-000", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details, status_code=400)


class AgentExecutionError(AgentException):
    """Execution failures (handler errors, model failures, etc.) - HTTP 500"""
    def __init__(self, message: str, error_code: str = "EXEC-000", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details, status_code=500)


class AgentTimeoutError(AgentException):
    """Timeout errors (request timeout, model timeout, etc.) - HTTP 504"""
    def __init__(self, message: str, error_code: str = "TO-000", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details, status_code=504)


class AgentResourceError(AgentException):
    """Resource errors (model unavailable, service down, etc.) - HTTP 503"""
    def __init__(self, message: str, error_code: str = "RES-000", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details, status_code=503)


class AgentStateError(AgentException):
    """State errors (session not found, invalid transitions, etc.) - HTTP 409"""
    def __init__(self, message: str, error_code: str = "STATE-000", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details, status_code=409)


# ============================================================================
# Error Code Constants (31 codes across 7 categories)
# ============================================================================

# Configuration Errors (CFG-XXX) - 7 codes
ERROR_MISSING_ENV_VAR = "CFG-001"
ERROR_INVALID_CONFIG_FORMAT = "CFG-002"
ERROR_CONFIG_FILE_NOT_FOUND = "CFG-003"
ERROR_INVALID_API_VERSION = "CFG-004"
ERROR_MISSING_SERVICE_INFO = "CFG-005"
ERROR_INVALID_URL_FORMAT = "CFG-006"
ERROR_INVALID_FILE_PATH = "CFG-007"

# Authentication Errors (AUTH-XXX) - 4 codes
ERROR_MISSING_AUTH_HEADER = "AUTH-001"
ERROR_INVALID_TOKEN = "AUTH-002"
ERROR_TOKEN_EXPIRED = "AUTH-003"
ERROR_INSUFFICIENT_PERMISSIONS = "AUTH-004"

# Validation Errors (VAL-XXX) - 4 codes
ERROR_MISSING_REQUIRED_FIELD = "VAL-001"
ERROR_INVALID_INPUT_FORMAT = "VAL-002"
ERROR_INPUT_EXCEEDS_LIMITS = "VAL-003"
ERROR_INVALID_PARAMETER_VALUE = "VAL-004"

# Execution Errors (EXEC-XXX) - 5 codes
ERROR_HANDLER_INIT_FAILED = "EXEC-001"
ERROR_MODEL_INVOCATION_FAILED = "EXEC-002"
ERROR_PLUGIN_EXECUTION_FAILED = "EXEC-003"
ERROR_STREAMING_ERROR = "EXEC-004"
ERROR_UNEXPECTED_ERROR = "EXEC-005"

# Resource Errors (RES-XXX) - 4 codes
ERROR_MODEL_NOT_AVAILABLE = "RES-001"
ERROR_PLUGIN_NOT_FOUND = "RES-002"
ERROR_SERVICE_UNAVAILABLE = "RES-003"
ERROR_RESOURCE_LIMIT_EXCEEDED = "RES-004"

# Timeout Errors (TO-XXX) - 3 codes
ERROR_REQUEST_TIMEOUT = "TO-001"
ERROR_MODEL_TIMEOUT = "TO-002"
ERROR_PLUGIN_TIMEOUT = "TO-003"

# State Errors (STATE-XXX) - 4 codes
ERROR_SESSION_NOT_FOUND = "STATE-001"
ERROR_TASK_NOT_FOUND = "STATE-002"
ERROR_INVALID_STATE_TRANSITION = "STATE-003"
ERROR_STATE_PERSISTENCE_FAILED = "STATE-004"


# ============================================================================
# Error Response Models
# ============================================================================

class ErrorDetail(BaseModel):
    """Detailed information about a specific error (for validation errors)."""
    code: str = Field(..., description="Error code for this specific detail")
    message: str = Field(..., description="Human-readable error message")
    field: str | None = Field(None, description="Field name that caused the error")
    value: Any | None = Field(None, description="The value that caused the error")


class ErrorResponse(BaseModel):
    """
    Standardized error response for all API errors.
    
    Example:
        {
            "error": "Validation Error",
            "error_code": "VAL-001",
            "message": "Missing required field: input",
            "details": [{...}],
            "trace_id": "abc123-def456",
            "timestamp": "2026-03-05T10:30:00Z"
        }
    """
    error: str = Field(..., description="High-level error type")
    error_code: str = Field(..., description="Machine-readable error code (e.g., 'VAL-001')")
    message: str = Field(..., description="Human-readable error message")
    details: list[ErrorDetail] | None = Field(None, description="Additional error details")
    trace_id: str | None = Field(None, description="Trace ID for request tracking")
    request_id: str | None = Field(None, description="Request ID for debugging")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Timestamp when error occurred (ISO 8601)",
    )
    path: str | None = Field(None, description="API path where error occurred")
    help_url: str | None = Field(None, description="URL to documentation")


class HealthErrorResponse(BaseModel):
    """Error response for health check endpoints."""
    status: str = Field(..., description="Health status ('unhealthy', 'degraded', etc.)")
    error: str = Field(..., description="Error message")
    checks: dict[str, str] | None = Field(None, description="Individual health check results")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Timestamp of health check",
    )


# ============================================================================
# Helper Functions
# ============================================================================

def create_error_response(
    error: str,
    error_code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
    path: str | None = None,
    help_url: str | None = None,
) -> ErrorResponse:
    """
    Helper function to create an ErrorResponse.
    
    Args:
        error: High-level error type
        error_code: Machine-readable error code
        message: Human-readable error message
        details: Additional error details
        trace_id: Trace ID for request tracking
        request_id: Request ID for debugging
        path: API path where error occurred
        help_url: URL to documentation
        
    Returns:
        ErrorResponse object
    """
    return ErrorResponse(
        error=error,
        error_code=error_code,
        message=message,
        details=details,
        trace_id=trace_id,
        request_id=request_id,
        path=path,
        help_url=help_url,
    )


# ============================================================================
# Legacy Exceptions (for backward compatibility)
# ============================================================================
# These remain in exceptions.py for backward compatibility
# New code should use the classes above
