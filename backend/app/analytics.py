import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from redis.exceptions import RedisError
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import ClickEvent, URL, utcnow

logger = logging.getLogger(__name__)


def classify_device(user_agent: str) -> str:
    user_agent = user_agent.lower()
    if re.search(r"bot|crawl|spider|slurp|preview|headless", user_agent):
        return "bot"
    if "ipad" in user_agent or "tablet" in user_agent or ("android" in user_agent and "mobile" not in user_agent):
        return "tablet"
    if re.search(r"mobile|iphone|ipod|android", user_agent):
        return "mobile"
    return "desktop" if user_agent else "unknown"


def referrer_hostname(referrer: str) -> str:
    try:
        parsed = urlsplit(referrer[:4096])
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host:
            return "Direct"
        return host.lower()[:253]
    except ValueError:
        return "Direct"


def make_event(url_id: str, referrer: str = "", user_agent: str = "") -> dict:
    return {"id": str(uuid.uuid4()), "url_id": url_id, "clicked_at": utcnow().isoformat(),
            "referrer": referrer_hostname(referrer), "device": classify_device(user_agent)}


def normalize_event(event: dict) -> dict:
    event_id, url_id = str(uuid.UUID(event["id"])), str(uuid.UUID(event["url_id"]))
    value = event["clicked_at"]
    clicked_at = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(clicked_at, datetime) or clicked_at.tzinfo is None:
        raise ValueError("clicked_at must be a timezone-aware timestamp")
    referrer = str(event.get("referrer", "Direct"))[:253]
    device = event.get("device", "unknown")
    if device not in {"desktop", "mobile", "tablet", "bot", "unknown"}:
        raise ValueError("Invalid device category")
    return {"id": event_id, "url_id": url_id, "clicked_at": clicked_at.astimezone(timezone.utc),
            "referrer": referrer, "device": device}


async def persist_event(session_factory, event: dict) -> bool:
    """Commit event plus counter in one transaction; a replay never increments twice."""
    values = normalize_event(event)
    async with session_factory() as session:
        async with session.begin():
            insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
            statement = insert(ClickEvent).values(**values).on_conflict_do_nothing(index_elements=["id"]).returning(ClickEvent.id)
            inserted_id = await session.scalar(statement)
            if inserted_id is None:
                return False
            await session.execute(update(URL).where(URL.id == values["url_id"]).values(click_count=URL.click_count + 1))
    return True


class AnalyticsService:
    def __init__(self, session_factory, redis_client, settings, metrics):
        self.session_factory = session_factory
        self.redis = redis_client
        self.settings = settings
        self.metrics = metrics

    async def record(self, url_id: str, referrer: str = "", user_agent: str = ""):
        event = make_event(url_id, referrer, user_agent)
        if self.settings.analytics_mode == "stream" and self.redis is not None:
            try:
                # No MAXLEN trimming: unprocessed click events must not be discarded.
                await self.redis.xadd(self.settings.analytics_stream, {"event": json.dumps(event)})
                self.metrics.analytics.labels("queued").inc()
                return
            except RedisError:
                self.metrics.redis_errors.labels("analytics_enqueue").inc()
                logger.warning("analytics_queue_unavailable; trying database fallback")
        try:
            await persist_event(self.session_factory, event)
            self.metrics.analytics.labels("stored_inline").inc()
        except Exception:
            # Redirect availability takes priority; a failed enqueue+DB write can lose a click.
            self.metrics.analytics.labels("dropped").inc()
            logger.exception("analytics_event_dropped")
