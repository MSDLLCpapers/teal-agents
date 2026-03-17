import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from ska_utils import AppConfig

from sk_agents.ska_types import BaseConfig

logger = logging.getLogger(__name__)


class HealthStatus(BaseModel):
    """Health check response model."""

    status: str
    timestamp: str
    version: str | None = None
    uptime: float | None = None
    dependencies: dict[str, Any] | None = None


class ReadinessStatus(BaseModel):
    """Readiness check response model."""

    ready: bool
    timestamp: str
    checks: dict[str, Any]


class LivenessStatus(BaseModel):
    """Liveness check response model."""

    alive: bool
    timestamp: str


class AgentMetadata(BaseModel):
    """Agent metadata response model."""

    agent_name: str | None = None
    description: str | None = None
    model: str | None = None
    plugins: list[str] | None = None


class UtilityRoutes:
    """Utility routes for health checks and system monitoring."""

    def __init__(self, start_time: datetime | None = None):
        self.start_time = start_time or datetime.now()

    def get_health_routes(
        self,
        config: BaseConfig,
        app_config: AppConfig,
    ) -> APIRouter:
        """
        Get health check routes for the application.

        Args:
            config: Base configuration
            app_config: Application configuration

        Returns:
            APIRouter: Router with health check endpoints
        """
        router = APIRouter()

        @router.get(
            "/health",
            response_model=HealthStatus,
            summary="Health check endpoint",
            description="Returns the health status of the application",
            tags=["Health"],
        )
        async def health_check() -> HealthStatus:
            """
            Basic health check endpoint that returns the application status.
            """
            try:
                current_time = datetime.now()
                uptime = (current_time - self.start_time).total_seconds()

                return HealthStatus(
                    status="healthy",
                    timestamp=current_time.isoformat(),
                    version=str(config.version) if config.version else None,
                    uptime=uptime,
                )
            except Exception as e:
                logger.exception(f"Health check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unhealthy"
                ) from e

        @router.get(
            "/health/live",
            response_model=LivenessStatus,
            summary="Liveness probe",
            description="Kubernetes liveness probe endpoint",
            tags=["Health"],
        )
        async def liveness_check() -> LivenessStatus:
            """
            Liveness probe for Kubernetes deployments.
            This endpoint should return 200 if the application is running.
            """
            try:
                return LivenessStatus(alive=True, timestamp=datetime.now().isoformat())
            except Exception as e:
                logger.exception(f"Liveness check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not alive"
                ) from e

        return router

    @staticmethod
    def _safe_get(obj, key, default=None):
        """Safely get a value from an object that may be a dict or an object with attributes."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _extract_metadata(config: BaseConfig) -> AgentMetadata:
        """
        Extract metadata from the agent configuration.

        Supports both skagents (v1) and tealagents (v1alpha1) config formats.

        Args:
            config: Base configuration

        Returns:
            AgentMetadata: Extracted metadata about the agent
        """
        try:
            _get = UtilityRoutes._safe_get
            agent_name = config.name or config.service_name
            description = None
            model = None
            plugins: list[str] = []

            # Get description from metadata if available, otherwise from top-level
            if config.metadata is not None and config.metadata.description is not None:
                description = config.metadata.description
            elif config.description is not None:
                description = config.description

            # Extract model and plugins from spec.agent (both skagents and tealagents)
            if config.spec is not None:
                spec = config.spec
                # Handle single agent config (chat / tealagents)
                agent = _get(spec, "agent")
                if agent is not None:
                    model = _get(agent, "model")
                    agent_plugins = _get(agent, "plugins")
                    if agent_plugins:
                        plugins.extend(agent_plugins)
                    remote_plugins = _get(agent, "remote_plugins")
                    if remote_plugins:
                        plugins.extend(remote_plugins)
                    mcp_servers = _get(agent, "mcp_servers")
                    if mcp_servers:
                        for server in mcp_servers:
                            server_name = _get(server, "name")
                            if server_name:
                                plugins.append(f"mcp:{server_name}")

                # Handle multi-agent config (sequential)
                agents = _get(spec, "agents")
                if agents is not None:
                    models = []
                    for ag in agents:
                        ag_model = _get(ag, "model")
                        if ag_model and ag_model not in models:
                            models.append(ag_model)
                        ag_plugins = _get(ag, "plugins")
                        if ag_plugins:
                            for p in ag_plugins:
                                if p not in plugins:
                                    plugins.append(p)
                        ag_remote = _get(ag, "remote_plugins")
                        if ag_remote:
                            for p in ag_remote:
                                if p not in plugins:
                                    plugins.append(p)
                    if models:
                        model = ", ".join(models)

            logger.info(f"Extracted metadata for agent: {agent_name}")
            return AgentMetadata(
                agent_name=agent_name,
                description=description,
                model=model,
                plugins=plugins if plugins else None,
            )
        except Exception as e:
            logger.exception(f"Failed to extract metadata from config: {e}")
            return AgentMetadata()

    def get_metadata_routes(
        self,
        config: BaseConfig,
    ) -> APIRouter:
        """
        Get metadata routes for the application.

        Args:
            config: Base configuration

        Returns:
            APIRouter: Router with metadata endpoint
        """
        metadata = self._extract_metadata(config)
        router = APIRouter()

        @router.get(
            "/metadata",
            response_model=AgentMetadata,
            summary="Agent metadata endpoint",
            description="Returns metadata about the agent including name, description, model, and available plugins",
            tags=["Metadata"],
        )
        async def get_metadata() -> AgentMetadata:
            """
            Returns metadata about the agent extracted from the agent's configuration.
            """
            try:
                return metadata
            except Exception as e:
                logger.exception(f"Metadata endpoint failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve agent metadata",
                ) from e

        return router
