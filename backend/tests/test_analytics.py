import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import func, select

from app.analytics import make_event, persist_event
from app.models import ClickEvent, URL
from app.worker import consume_once, ensure_group, process_message
from conftest import create_link, sign_in


pytestmark = pytest.mark.asyncio


async def test_dashboard_zero_filled_and_analytics_private(client, auth):
    dashboard = await client.get("/api/v1/dashboard?days=7", headers=auth)
    assert dashboard.status_code == 200
    assert dashboard.json()["total_links"] == 0
    assert dashboard.json()["total_clicks"] == 0
    assert len(dashboard.json()["clicks_by_day"]) == 7
    assert all(day["clicks"] == 0 for day in dashboard.json()["clicks_by_day"])


async def test_counting_time_series_referrer_privacy_and_scope(app, client, auth):
    link = await create_link(client, auth)
    for _ in range(3):
        response = await client.get("/r/" + link["short_code"], headers={"Referer": "https://news.example.com/private/path?token=SECRET", "User-Agent": "Mozilla/5.0 (iPhone; Mobile)"})
        assert response.status_code == 302
    stats = (await client.get(f'/api/v1/urls/{link["id"]}/analytics?days=7', headers=auth)).json()
    assert stats["total_clicks"] == stats["period_clicks"] == 3
    assert len(stats["clicks_by_day"]) == 7
    assert sum(item["clicks"] for item in stats["clicks_by_day"]) == 3
    assert {item["referrer"] for item in stats["referrers"]} == {"news.example.com"}
    assert stats["devices"] == [{"device": "mobile", "clicks": 3}]
    assert "SECRET" not in json.dumps(stats)
    async with app.state.session_factory() as session:
        events = (await session.scalars(select(ClickEvent))).all()
        assert len(events) == 3 and all(e.referrer == "news.example.com" for e in events)
    dashboard = (await client.get("/api/v1/dashboard", headers=auth)).json()
    assert dashboard["total_clicks"] == 3 and dashboard["total_links"] == 1
    other = await sign_in(client, "analytics-other@example.com")
    assert (await client.get("/api/v1/dashboard", headers=other)).json()["total_clicks"] == 0


async def test_duplicate_event_is_idempotent_and_counter_atomic(app, client, auth):
    link = await create_link(client, auth)
    event = make_event(link["id"], "https://example.org/path", "")
    assert await persist_event(app.state.session_factory, event) is True
    assert await persist_event(app.state.session_factory, event) is False
    stats = (await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)).json()
    assert stats["click_count"] == 1
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ClickEvent)) == 1


async def test_concurrent_duplicate_events_increment_once(app, client, auth):
    import asyncio
    link = await create_link(client, auth)
    event = make_event(link["id"])
    outcomes = await asyncio.gather(*(persist_event(app.state.session_factory, event) for _ in range(3)))
    assert outcomes.count(True) == 1
    assert (await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)).json()["click_count"] == 1


async def test_dashboard_excludes_deleted_links(client, auth):
    link = await create_link(client, auth)
    await client.get("/r/" + link["short_code"])
    await client.delete(f'/api/v1/urls/{link["id"]}', headers=auth)
    dashboard = (await client.get("/api/v1/dashboard", headers=auth)).json()
    assert dashboard["total_links"] == 0
    assert dashboard["total_clicks"] == 0


async def test_stream_queue_worker_and_ack(app_factory):
    app = await app_factory(analytics_mode="stream", analytics_claim_idle_ms=1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        auth = await sign_in(client)
        link = await create_link(client, auth)
        await client.get("/r/" + link["short_code"])
        before = (await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)).json()
        assert before["click_count"] == 0
        assert await app.state.redis.xlen(app.state.settings.analytics_stream) == 1
        processed = await consume_once(app.state.redis, app.state.session_factory, app.state.settings, "test-consumer", block_ms=1)
        assert processed == 1
        after = (await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)).json()
        assert after["click_count"] == 1
        assert await app.state.redis.xlen(app.state.settings.analytics_stream) == 0


async def test_worker_replays_after_commit_before_ack_without_double_count(app, client, auth):
    link = await create_link(client, auth)
    settings = app.state.settings
    await ensure_group(app.state.redis, settings)
    event = make_event(link["id"])
    fields = {"event": json.dumps(event)}
    message_id = await app.state.redis.xadd(settings.analytics_stream, fields)
    await app.state.redis.xreadgroup(settings.analytics_group, "crashed-consumer", {settings.analytics_stream: ">"})
    # Reproduce a process dying immediately after DB commit and before stream ACK.
    await persist_event(app.state.session_factory, event)
    assert await process_message(app.state.redis, app.state.session_factory, message_id, fields, settings)
    assert (await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)).json()["click_count"] == 1
    pending = await app.state.redis.xpending(settings.analytics_stream, settings.analytics_group)
    assert pending["pending"] == 0


async def test_pending_event_reclaimed_after_worker_failure(app, client, auth):
    import asyncio
    settings = app.state.settings
    settings.analytics_claim_idle_ms = 1
    link = await create_link(client, auth)
    await ensure_group(app.state.redis, settings)
    await app.state.redis.xadd(settings.analytics_stream, {"event": json.dumps(make_event(link["id"]))})
    await app.state.redis.xreadgroup(settings.analytics_group, "abandoned", {settings.analytics_stream: ">"})
    await asyncio.sleep(0.015)
    assert await consume_once(app.state.redis, app.state.session_factory, settings, "replacement", block_ms=1) == 1
    assert (await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)).json()["click_count"] == 1


async def test_database_failure_keeps_event_pending(app, client, auth, monkeypatch):
    link = await create_link(client, auth)
    settings = app.state.settings
    await ensure_group(app.state.redis, settings)
    fields = {"event": json.dumps(make_event(link["id"]))}
    message_id = await app.state.redis.xadd(settings.analytics_stream, fields)
    await app.state.redis.xreadgroup(settings.analytics_group, "consumer", {settings.analytics_stream: ">"})
    async def unavailable(*args, **kwargs):
        raise RuntimeError("simulated DB outage")
    monkeypatch.setattr("app.worker.persist_event", unavailable)
    assert not await process_message(app.state.redis, app.state.session_factory, message_id, fields, settings)
    assert (await app.state.redis.xpending(settings.analytics_stream, settings.analytics_group))["pending"] == 1
    assert await app.state.redis.xlen(settings.analytics_stream) == 1


async def test_malformed_event_does_not_block_worker(app):
    settings = app.state.settings
    await ensure_group(app.state.redis, settings)
    fields = {"event": "not-json"}
    message_id = await app.state.redis.xadd(settings.analytics_stream, fields)
    await app.state.redis.xreadgroup(settings.analytics_group, "consumer", {settings.analytics_stream: ">"})
    assert await process_message(app.state.redis, app.state.session_factory, message_id, fields, settings)
    assert await app.state.redis.xlen(settings.analytics_stream + ":dead") == 1
    assert (await app.state.redis.xpending(settings.analytics_stream, settings.analytics_group))["pending"] == 0


async def test_redis_outage_falls_back_to_db_and_still_redirects(app, client, auth, monkeypatch):
    link = await create_link(client, auth)
    app.state.settings.analytics_mode = "stream"
    async def unavailable(*args, **kwargs):
        raise ConnectionError("simulated Redis outage")
    monkeypatch.setattr(app.state.redis, "mget", unavailable)
    monkeypatch.setattr(app.state.redis, "xadd", unavailable)
    response = await client.get("/r/" + link["short_code"])
    assert response.status_code == 302
    assert (await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)).json()["click_count"] == 1

