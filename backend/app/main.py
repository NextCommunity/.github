"""NextCommunity Leaderboard Backend — FastAPI application."""

from __future__ import annotations

import hmac
import logging
import time

from fastapi import Depends, FastAPI, HTTPException, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from backend.app.config import settings
from backend.app.models.leaderboard import HealthResponse
from backend.app.routers import contributors, leaderboard, stats

logger = logging.getLogger("backend")

app = FastAPI(
    title="NextCommunity Leaderboard API",
    description=(
        "Dynamic API serving the NextCommunity organization leaderboard "
        "with gamified levels, achievements, points, and streaks."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request timing middleware ---


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.monotonic()
    response: Response = await call_next(request)
    elapsed = time.monotonic() - start
    response.headers["X-Process-Time"] = f"{elapsed:.3f}"
    return response


# --- API key security for protected endpoints ---

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the API key for protected endpoints."""
    if not settings.api_key:
        # No key configured — allow all (development mode)
        return ""
    if not api_key or not hmac.compare_digest(api_key, settings.api_key):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


# --- Routers ---
app.include_router(leaderboard.router)
app.include_router(contributors.router)
app.include_router(stats.router)


# Override the refresh endpoint to require API key when configured
@app.post(
    "/api/refresh",
    response_model=leaderboard.RefreshResponse,
    tags=["leaderboard"],
    summary="Refresh leaderboard data (requires API key when configured)",
    include_in_schema=True,
)
async def refresh_with_auth(
    _key: str = Depends(verify_api_key),
):
    return await leaderboard.refresh_leaderboard()


# Remove the unprotected refresh route added by the router
for route in app.routes:
    if hasattr(route, "path") and route.path == "/api/refresh" and hasattr(route, "endpoint"):
        if route.endpoint is not refresh_with_auth:
            app.routes.remove(route)
            break


# --- Health endpoint ---


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", version="1.0.0")
