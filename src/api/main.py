"""FastAPI application for EDFS v2."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.data.db.session import create_tables
from src.api.model_registry import load_models

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting EDFS API...")
    create_tables()
    load_models()
    yield
    logger.info("Shutting down EDFS API")


app = FastAPI(
    title="EDFS API",
    description="Electricity Demand Forecasting System for Delhi Power Grid",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for Next.js frontend (localhost:3000 in dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routers after app is created to avoid circular imports
from src.api.routers import forecast, dashboard, auth, health, admin  # noqa: E402

app.include_router(health.router, prefix="/api/v1/health", tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(forecast.router, prefix="/api/v1/forecast", tags=["Forecast"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
