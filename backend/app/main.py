import logging
import secrets
import socket
import time
import uuid
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analytics import AnalyticsService
from app.api import redirect_router, router
from app.cache import RateLimiter, URLCache
from app.config import Settings
from app.database import make_database
from app.metrics import Metrics

logger = logging.getLogger("linkforge.api")
# Uvicorn configures its own loggers, not application loggers. Make the
# sanitized request records visible without enabling raw access logs.
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def create_app(settings: Settings | None = None, redis_client=None) -> FastAPI:
    settings = settings or Settings()
    engine, session_factory = make_database(settings.database_url)
    redis = redis_client
    if redis is None and settings.redis_url:
        redis = Redis.from_url(settings.redis_url, decode_responses=True,
                               socket_connect_timeout=settings.redis_timeout_seconds,
                               socket_timeout=settings.redis_timeout_seconds,
                               retry=Retry(NoBackoff(), 0),
                               health_check_interval=30)

    @asynccontextmanager
    async def lifespan(application):
        yield
        if redis is not None:
            await redis.aclose()
        await engine.dispose()

    application = FastAPI(title="Linkforge API", version="1.0.0", lifespan=lifespan,
                          description="URL shortening, authenticated link management and asynchronous click analytics.")
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.redis = redis
    application.state.metrics = metrics = Metrics()
    application.state.cache = URLCache(redis, settings.cache_ttl_seconds, metrics)
    application.state.limiter = RateLimiter(redis, settings, metrics)
    application.state.analytics = AnalyticsService(session_factory, redis, settings, metrics)
    application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                               allow_methods=["GET", "HEAD", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    @application.middleware("http")
    async def observe(request: Request, call_next):
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 65536:
            return JSONResponse({"detail": "Request body exceeds 64 KiB"}, status_code=413)
        response = await call_next(request)
        route = request.scope.get("route")
        path = route.path if route else "unmatched"
        elapsed = time.perf_counter() - started
        metrics.requests.labels(request.method, path, str(response.status_code)).inc()
        metrics.latency.labels(request.method, path).observe(elapsed)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        logger.info("request method=%s route=%s status=%s duration_ms=%.1f request_id=%s",
                    request.method, path, response.status_code, elapsed * 1000, request_id)
        return response

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        logger.exception("database_request_failed", exc_info=exc)
        return JSONResponse({"detail": "Database temporarily unavailable. Please try again."}, status_code=503,
                            headers={"Retry-After": "5"})

    # Initial asyncpg connections can raise driver/network exceptions before
    # SQLAlchemy has a DBAPI connection with which to wrap them.
    for connection_error in (ConnectionError, TimeoutError, socket.gaierror, asyncpg.PostgresError):
        application.add_exception_handler(connection_error, database_error)

    @application.get("/health/live", tags=["Operations"])
    async def live():
        return {"status": "ok"}

    @application.get("/health/ready", tags=["Operations"])
    async def ready():
        database_ok, redis_ok = True, None
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            database_ok = False
        if redis is not None:
            try:
                redis_ok = bool(await redis.ping())
            except RedisError:
                redis_ok = False
        return JSONResponse({"status": "ok" if database_ok and redis_ok is not False else ("degraded" if database_ok else "unavailable"),
                             "database": "ok" if database_ok else "unavailable",
                             "redis": "disabled" if redis_ok is None else ("ok" if redis_ok else "unavailable")},
                            status_code=200 if database_ok else 503)

    @application.get("/metrics", include_in_schema=False)
    async def metrics_endpoint(request: Request):
        if settings.metrics_token:
            if not secrets.compare_digest(request.headers.get("Authorization", ""), "Bearer " + settings.metrics_token):
                raise HTTPException(401, "Metrics authentication required")
        elif settings.environment == "production":
            raise HTTPException(404, "Not found")
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    application.include_router(router)
    application.include_router(redirect_router)
    return application


app = create_app()
