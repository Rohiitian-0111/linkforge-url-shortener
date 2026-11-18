"""At-least-once stream consumer. Run with `python -m app.worker`."""

import argparse
import asyncio
import json
import logging
import socket
import uuid

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError, ResponseError

from app.analytics import persist_event
from app.config import Settings
from app.database import make_database

logger = logging.getLogger("linkforge.worker")


async def ensure_group(redis, settings):
    try:
        await redis.xgroup_create(settings.analytics_stream, settings.analytics_group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def process_message(redis, session_factory, message_id, fields, settings) -> bool:
    raw = ""
    try:
        raw = fields.get("event", fields.get(b"event"))
        event = json.loads(raw)
        await persist_event(session_factory, event)
    except (ValueError, KeyError, TypeError, AttributeError):
        logger.exception("malformed_click_event; moving to dead-letter stream")
        await redis.xadd(settings.analytics_stream + ":dead", {"source_id": message_id, "event": str(raw)[:8192]}, maxlen=1000)
    except Exception:
        logger.exception("click_event_database_write_failed; leaving pending for retry")
        return False
    # ACK only after the transaction commits (including a known duplicate).
    async with redis.pipeline(transaction=True) as pipe:
        pipe.xack(settings.analytics_stream, settings.analytics_group, message_id)
        pipe.xdel(settings.analytics_stream, message_id)
        await pipe.execute()
    return True


async def consume_once(redis, session_factory, settings, consumer: str, block_ms: int = 1000,
                       claim_state: dict | None = None) -> int:
    await ensure_group(redis, settings)
    processed = 0
    # Redis 6.2 returns two items; Redis 7+ additionally returns deleted pending IDs.
    claim_state = claim_state if claim_state is not None else {}
    claimed = await redis.xautoclaim(settings.analytics_stream, settings.analytics_group, consumer,
                                   min_idle_time=settings.analytics_claim_idle_ms,
                                   start_id=claim_state.get("cursor", "0-0"), count=settings.analytics_batch_size)
    claim_state["cursor"] = claimed[0]
    for message_id, fields in claimed[1]:
        processed += bool(await process_message(redis, session_factory, message_id, fields, settings))
    batches = await redis.xreadgroup(settings.analytics_group, consumer,
                                    {settings.analytics_stream: ">"}, count=settings.analytics_batch_size,
                                    block=block_ms)
    for _, messages in batches:
        for message_id, fields in messages:
            processed += bool(await process_message(redis, session_factory, message_id, fields, settings))
    return processed


async def run(once: bool = False):
    settings = Settings()
    if not settings.redis_url:
        raise RuntimeError("The analytics worker requires REDIS_URL. Use ANALYTICS_MODE=inline without a worker for SQLite development.")
    redis = Redis.from_url(settings.redis_url, decode_responses=True,
                           socket_connect_timeout=settings.redis_timeout_seconds,
                           socket_timeout=max(5.0, settings.redis_timeout_seconds),
                           retry=Retry(NoBackoff(), 0), health_check_interval=30)
    engine, session_factory = make_database(settings.database_url)
    consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    claim_state = {}
    try:
        while True:
            try:
                processed = await consume_once(redis, session_factory, settings, consumer, claim_state=claim_state)
                if processed:
                    logger.info("click_events_processed=%s", processed)
                if once:
                    break
            except RedisError:
                logger.exception("redis_temporarily_unavailable")
                if once:
                    raise
                await asyncio.sleep(2)
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process one batch and exit (smoke tests)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(once=args.once))
