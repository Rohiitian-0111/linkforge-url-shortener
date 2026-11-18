"""Run unchanged against disposable SQLite/fakeredis or PostgreSQL/Redis.

Never point TEST_DATABASE_URL at application data: the test database is reset.
"""
from __future__ import annotations

import os
from contextlib import AsyncExitStack
from urllib.parse import urlsplit

import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.config import Settings
from app.main import create_app
from app.models import Base


@pytest_asyncio.fixture
async def app_factory(tmp_path):
    async with AsyncExitStack() as stack:
        created = []

        async def make(**overrides):
            database_url = os.getenv("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test-{len(created)}.db")
            if not database_url.startswith("sqlite") and "test" not in urlsplit(database_url).path.lower():
                raise RuntimeError("TEST_DATABASE_URL must name a disposable database containing 'test'.")
            redis_url = os.getenv("TEST_REDIS_URL", "")
            if redis_url:
                if urlsplit(redis_url).path != "/15":
                    raise RuntimeError("TEST_REDIS_URL must use dedicated disposable Redis database /15.")
                redis = Redis.from_url(redis_url, decode_responses=True)
                await redis.flushdb()
            else:
                redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
            config = dict(environment="test", database_url=database_url, redis_url="", jwt_secret="test-only-secret-" + "x" * 48,
                          public_base_url="http://testserver", analytics_mode="inline", rate_limit_enabled=False,
                          trusted_hosts=["testserver", "localhost", "127.0.0.1"])
            config.update(overrides)
            app = create_app(Settings(**config), redis_client=redis)
            async with app.state.engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
                await connection.run_sync(Base.metadata.create_all)
            await stack.enter_async_context(app.router.lifespan_context(app))
            created.append(app)
            return app

        yield make


@pytest_asyncio.fixture
async def app(app_factory):
    return await app_factory()


@pytest_asyncio.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", follow_redirects=False) as result:
        yield result


@pytest.fixture
def user_payload():
    return {"email": "builder@example.com", "name": "Project Builder", "password": "SafeTestPassword!82"}


async def sign_in(client, email="builder@example.com"):
    payload = {"email": email, "name": "Project Builder", "password": "SafeTestPassword!82"}
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": payload["password"]})
    assert login.status_code == 200, login.text
    return {"Authorization": "Bearer " + login.json()["access_token"]}


@pytest_asyncio.fixture
async def auth(client):
    return await sign_in(client)


async def create_link(client, auth, **overrides):
    data = {"original_url": "https://example.com/guide?source=linkforge#start", "title": "Design notes"}
    data.update(overrides)
    result = await client.post("/api/v1/urls", headers=auth, json=data)
    assert result.status_code == 201, result.text
    return result.json()

