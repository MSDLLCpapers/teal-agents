from fastapi import FastAPI

from routes import apis, deps, websockets

# Get configurations
config = deps.get_config()

# Instance of FastAPI app
app = FastAPI(
    openapi_url=f"/{config.service_name}/{str(config.version)}/openapi.json",
    docs_url=f"/{config.service_name}/{str(config.version)}/docs",
    redoc_url=f"/{config.service_name}/{str(config.version)}/redoc",
)

# Initialize the app components
deps.initialize()
# API router to handle standard API routes
app.include_router(apis.router, prefix=f"/{config.service_name}/{str(config.version)}")
# WebSocket router for handling WebSocket connections
app.include_router(websockets.router, prefix=f"/{config.service_name}/{str(config.version)}")
