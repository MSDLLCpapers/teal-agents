"""Utility routes for health checks, liveness, and agent metadata."""

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
        app_config: AppConfig,  # pylint: disable=unused-argument
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
                logger.exception("Health check failed: %s", e)
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
                logger.exception("Liveness check failed: %s", e)
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
    def _extract_description(config: BaseConfig) -> str | None:
        """Extract description from config, preferring metadata.description."""
        if config.metadata is not None and config.metadata.description is not None:
            return config.metadata.description
        return config.description

    @staticmethod
    def _extract_plugins_from_agent(agent, _get) -> list[str]:
        """Extract plugin names from a single agent config."""
        plugins: list[str] = []
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
        return plugins

    @staticmethod
    def _extract_from_multi_agents(agents, plugins, _get) -> str | None:
        """Extract model and plugins from a multi-agent spec. Returns combined model string."""
        models = []
        for ag in agents:
            ag_model = _get(ag, "model")
            if ag_model and ag_model not in models:
                models.append(ag_model)
            for p in _get(ag, "plugins") or []:
                if p not in plugins:
                    plugins.append(p)
            for p in _get(ag, "remote_plugins") or []:
                if p not in plugins:
                    plugins.append(p)
        return ", ".join(models) if models else None

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
            description = UtilityRoutes._extract_description(config)
            model = None
            plugins: list[str] = []

            if config.spec is not None:
                spec = config.spec
                agent = _get(spec, "agent")
                if agent is not None:
                    model = _get(agent, "model")
                    plugins = UtilityRoutes._extract_plugins_from_agent(agent, _get)

                agents = _get(spec, "agents")
                if agents is not None:
                    model = UtilityRoutes._extract_from_multi_agents(agents, plugins, _get)

            logger.info("Extracted metadata for agent: %s", agent_name)
            return AgentMetadata(
                agent_name=agent_name,
                description=description,
                model=model,
                plugins=plugins if plugins else None,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Failed to extract metadata from config: %s", e)
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
            description=(
                "Returns metadata about the agent including"
                " name, description, model, and available plugins"
            ),
            tags=["Metadata"],
        )
        async def get_metadata() -> AgentMetadata:
            """
            Returns metadata about the agent extracted from the agent's configuration.
            """
            try:
                return metadata
            except Exception as e:
                logger.exception("Metadata endpoint failed: %s", e)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to retrieve agent metadata",
                ) from e

        return router
