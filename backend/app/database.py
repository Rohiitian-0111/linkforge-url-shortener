from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def make_database(database_url: str):
    # Database exceptions must not leak destination query strings or password hashes.
    kwargs = {"pool_pre_ping": True, "hide_parameters": True}
    if not database_url.startswith("sqlite"):
        kwargs.update(pool_size=10, max_overflow=10, pool_timeout=5)
        if database_url.startswith("postgresql+asyncpg"):
            kwargs["connect_args"] = {
                "timeout": 3.0,
                "command_timeout": 5.0,
                "server_settings": {"timezone": "UTC"},
            }
    engine = create_async_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_pragmas(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory
