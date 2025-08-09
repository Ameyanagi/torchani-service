"""Main FastAPI application."""

import logging
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api import routes
from app.config import settings
from app.core.model_manager import model_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting TorchANI Service...")
    
    # Initialize model manager
    await model_manager.initialize()
    logger.info("Model manager initialized")
    
    # Log GPU availability
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        logger.info(f"GPU available: {device_name}")
    else:
        logger.warning("No GPU available, using CPU")
    
    yield
    
    # Shutdown
    logger.info("Shutting down TorchANI Service...")
    await model_manager.close()
    logger.info("Cleanup complete")


# Create FastAPI app
app = FastAPI(
    title="TorchANI Service",
    description="GPU-optimized molecular structure optimization service",
    version=settings.version,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(routes.router, prefix=settings.api_prefix)

# Add Prometheus metrics endpoint
if settings.prometheus_enabled:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# Health check endpoint (outside API prefix)
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    gpu_available = torch.cuda.is_available()
    redis_connected = model_manager.redis_client is not None
    
    return {
        "status": "healthy" if redis_connected else "degraded",
        "version": settings.version,
        "gpu_available": gpu_available,
        "redis_connected": redis_connected,
    }

# Ready check endpoint
@app.get("/ready")
async def ready_check():
    """Readiness check endpoint."""
    try:
        # Check if we can access Redis
        if model_manager.redis_client:
            await model_manager.redis_client.ping()
        
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "not ready", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info" if not settings.debug else "debug",
    )