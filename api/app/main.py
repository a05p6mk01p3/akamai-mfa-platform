from __future__ import annotations

from functools import lru_cache
import logging
import time
import uuid

from fastapi import FastAPI, Request

from . import __version__
from .api.v2.akamai_mfa import router as akamai_mfa_v2_router
from .api.v2.eaa import router as eaa_v2_router
from .api.v2.operations import router as operations_v2_router
from .api.v2.prepare import router as prepare_v2_router
from .audit import configure_logging
from .config import Settings


APP_VERSION = __version__

configure_logging("INFO")
logger = logging.getLogger("akamai-mfa-api")

app = FastAPI(
    title="Akamai MFA API v2 — read-only contracts",
    version=APP_VERSION,
    description=(
        "Change-set 09 da linha v2. Child operations para retry explícito após "
        "REQUIRES_RECONFIRMATION; parent nunca é reativado."
    ),
)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    return settings


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.started_at = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ready",
        "version": APP_VERSION,
        "upstream_configured": True,
        "destructive_operations_enabled": settings.destructive_operations_enabled,
        "execution_framework_enabled": settings.execution_framework_enabled,
        "execution_backend": settings.execution_backend,
        "database_configured": settings.database_configured,
    }


app.include_router(eaa_v2_router)
app.include_router(akamai_mfa_v2_router)
app.include_router(prepare_v2_router)
app.include_router(operations_v2_router)
