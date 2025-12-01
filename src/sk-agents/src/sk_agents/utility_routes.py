import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from ska_utils import AppConfig

from sk_agents.ska_types import BaseConfig

logger = logging.getLogger(__name__)


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: Optional[str] = None
    uptime: Optional[float] = None
    dependencies: Optional[Dict[str, Any]] = None


class ReadinessStatus(BaseModel):
    """Readiness check response model."""
    ready: bool
    timestamp: str
    checks: Dict[str, Any]


class LivenessStatus(BaseModel):
    """Liveness check response model."""
    alive: bool
    timestamp: str


class UtilityRoutes:
    """Utility routes for health checks and system monitoring."""
    
    def __init__(self, start_time: Optional[datetime] = None):
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
            tags=["Health"]
        )
        async def health_check(request: Request) -> HealthStatus:
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
                    uptime=uptime
                )
            except Exception as e:
                logger.exception(f"Health check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service unhealthy"
                )

        @router.get(
            "/health/live",
            response_model=LivenessStatus,
            summary="Liveness probe",
            description="Kubernetes liveness probe endpoint",
            tags=["Health"]
        )
        async def liveness_check(request: Request) -> LivenessStatus:
            """
            Liveness probe for Kubernetes deployments.
            This endpoint should return 200 if the application is running.
            """
            try:
                return LivenessStatus(
                    alive=True,
                    timestamp=datetime.now().isoformat()
                )
            except Exception as e:
                logger.exception(f"Liveness check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service not alive"
                )

        return router