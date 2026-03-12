"""
Distributed AI Network - Main Server
Production-grade FastAPI application.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_db, check_db_connection, get_db_stats
from .routers import workers, tasks, admin_panel, wallet, auth, openai_compat
from .ws import ws_router
from .metrics import metrics_endpoint

# Logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan."""
    logger.info("Starting Distributed AI Network Server...")
    init_db()
    logger.info("Server started")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Distributed AI Network",
    description="Production-grade distributed computing platform with two-tier validation",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing(request: Request, call_next):
    """Add request timing header."""
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.time() - start)
    return response


# Routers
app.include_router(auth.router)
app.include_router(workers.router)
app.include_router(tasks.router)
app.include_router(admin_panel.router)
app.include_router(wallet.router)
app.include_router(openai_compat.router)
app.include_router(ws_router)


@app.get("/")
def root():
    return {"status": "online", "service": "ai-network-main-server"}


@app.get("/health")
def health():
    """Health check endpoint."""
    db_ok = check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": db_ok,
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "version": "1.0.0",
    }


@app.get("/metrics")
def metrics():
    """Basic metrics (JSON format)."""
    return {
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "database": get_db_stats(),
    }


@app.get("/metrics/prometheus")
async def prometheus_metrics(request: Request):
    """Prometheus format metrics endpoint."""
    return await metrics_endpoint(request)
