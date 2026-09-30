"""VECTOR local agent entry point.

Starts the FastAPI application bound to 127.0.0.1 (loopback only).
Never binds to 0.0.0.0 by default.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vector_agent import __version__
from vector_agent.api import devices, health, scans
from vector_agent.core.config import get_settings
from vector_agent.core.errors import VectorError
from vector_agent.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "VECTOR agent starting | version=%s | mode=%s",
            __version__,
            "DEMO" if settings.demo_mode else "LIVE",
        )
        yield
        logger.info("VECTOR agent shutting down.")

    app = FastAPI(
        title="VECTOR Local Agent",
        description=(
            "Local hardware agent for VECTOR smartphone diagnostics. "
            "Runs on a Windows laptop and communicates with connected devices via ADB / libimobiledevice."
        ),
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ---- CORS ----
    # Only allow the Vite dev server. In production the React build is served
    # from the same origin so CORS is not needed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept"],
    )

    # ---- Error handlers ----
    @app.exception_handler(VectorError)
    async def vector_error_handler(request: Request, exc: VectorError) -> JSONResponse:
        logger.warning("VectorError | %s | %s", exc.code.value, exc.message)
        return JSONResponse(
            status_code=_error_to_status(exc),
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An internal error occurred. Check the agent logs.",
                "detail": None,
                "recoverable": False,
            },
        )

    # ---- Routers ----
    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(devices.router, prefix=prefix)
    app.include_router(scans.router, prefix=prefix)

    return app


def _error_to_status(exc: VectorError) -> int:
    from vector_agent.core.errors import VectorErrorCode

    code_map = {
        VectorErrorCode.DEVICE_NOT_FOUND: 404,
        VectorErrorCode.MULTIPLE_DEVICES_FOUND: 409,
        VectorErrorCode.SCAN_NOT_FOUND: 404,
        VectorErrorCode.ADB_NOT_INSTALLED: 503,
        VectorErrorCode.ADB_UNAUTHORIZED: 503,
        VectorErrorCode.ADB_OFFLINE: 503,
        VectorErrorCode.IOS_DEPENDENCY_MISSING: 503,
        VectorErrorCode.IOS_NOT_TRUSTED: 503,
        VectorErrorCode.IOS_PAIRING_REQUIRED: 503,
        VectorErrorCode.SUBPROCESS_POLICY_VIOLATION: 400,
    }
    return code_map.get(exc.code, 500)


app = create_app()


def start() -> None:
    """Entry point for the ``vector-agent`` CLI command."""
    settings = get_settings()
    uvicorn.run(
        "vector_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    start()
