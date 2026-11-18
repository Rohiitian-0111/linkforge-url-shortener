import httpx
import pytest
from redis.exceptions import ConnectionError

from conftest import create_link, sign_in


pytestmark = pytest.mark.asyncio


async def test_cache_generation_prevents_stale_repopulation(app):
    cache = app.state.cache
    code = "cache-race"
    stale = {"id": "e4c7ad50-1e36-482c-8a3e-8812c6ace4b4", "original_url": "https://example.com/old", "is_active": True, "expires_at": None, "deleted": False}
    value, generation = await cache.read(code)
    assert value is None
    # An edit commits and invalidates while an earlier cache miss reads stale DB data.
    await cache.invalidate(code)
    await cache.store(code, stale, generation)
    assert (await cache.read(code))[0] is None
    _, new_generation = await cache.read(code)
    fresh = {**stale, "original_url": "https://example.com/new"}
    await cache.store(code, fresh, new_generation)
    assert (await cache.read(code))[0] == fresh


async def test_create_rate_limit_is_shared_and_returns_retry_after(app_factory):
    app = await app_factory(rate_limit_enabled=True, create_rate_limit=2)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        auth = await sign_in(client)
        await create_link(client, auth)
        await create_link(client, auth)
        limited = await client.post("/api/v1/urls", headers=auth, json={"original_url": "https://example.com/limited"})
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0


async def test_auth_rate_limit_and_proxy_header_not_blindly_trusted(app_factory):
    app = await app_factory(rate_limit_enabled=True, auth_rate_limit=2)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        for _ in range(2):
            result = await client.post("/api/v1/auth/login", json={"email": "none@example.com", "password": "WrongPassword"})
            assert result.status_code == 401
        limited = await client.post("/api/v1/auth/login", headers={"X-Forwarded-For": "198.51.100.22"}, json={"email": "none@example.com", "password": "WrongPassword"})
        assert limited.status_code == 429


async def test_production_limiter_fails_closed_on_redis_outage(app, monkeypatch):
    app.state.settings.environment = "production"
    app.state.settings.rate_limit_enabled = True
    async def unavailable(*args, **kwargs):
        raise ConnectionError("simulated Redis outage")
    monkeypatch.setattr(app.state.redis, "eval", unavailable)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/v1/auth/login", json={"email": "none@example.com", "password": "WrongPassword"})
        assert response.status_code == 503


async def test_health_and_metrics(app, client):
    assert (await client.get("/health/live")).status_code == 200
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "linkforge" in response.text


async def test_host_header_rejected(client):
    assert (await client.get("/health/live", headers={"Host": "attacker.invalid"})).status_code == 400


async def test_corrupt_cache_payload_falls_back_to_database(app, client, auth):
    link = await create_link(client, auth)
    data_key, _ = app.state.cache.keys(link["short_code"])
    await app.state.redis.set(data_key, '{"id":"invalid"}', ex=60)
    assert (await client.get("/r/" + link["short_code"])).status_code == 302


async def test_warm_redirect_survives_database_outage_while_cold_redirect_fails(app, client, auth, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    link = await create_link(client, auth)
    assert (await client.get("/r/" + link["short_code"])).status_code == 302
    def unavailable():
        raise SQLAlchemyError("simulated DB outage")
    monkeypatch.setattr(app.state, "session_factory", unavailable)
    monkeypatch.setattr(app.state.analytics, "session_factory", unavailable)
    assert (await client.get("/r/" + link["short_code"])).status_code == 302
    assert (await client.get("/r/uncached-link")).status_code == 503


async def test_redis_outage_readiness_reports_degraded(app, client, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise ConnectionError("simulated Redis outage")
    monkeypatch.setattr(app.state.redis, "ping", unavailable)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["redis"] == "unavailable"


async def test_atomic_rate_limit_shared_between_instances(app):
    import asyncio
    from fastapi import HTTPException
    from app.cache import RateLimiter
    app.state.settings.rate_limit_enabled = True
    a = app.state.limiter
    b = RateLimiter(app.state.redis, app.state.settings, app.state.metrics)
    async def request(limiter):
        try:
            await limiter.check("concurrent", "same-user", 5, 60)
            return 200
        except HTTPException as exc:
            return exc.status_code
    results = await asyncio.gather(*(request(a if index % 2 else b) for index in range(16)))
    assert results.count(200) == 5
    assert results.count(429) == 11


async def test_real_database_connection_refusal_returns_503():
    from app.config import Settings
    from app.main import create_app
    app = create_app(Settings(environment="test", database_url="postgresql+asyncpg://unavailable@127.0.0.1:1/linkforge_test",
                              redis_url="", rate_limit_enabled=False, analytics_mode="inline"))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/r/unavailable")
            assert response.status_code == 503
            assert response.headers["retry-after"] == "5"
            assert "temporarily unavailable" in response.json()["detail"]
            assert (await client.get("/health/ready")).status_code == 503

