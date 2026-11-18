"""Migrations must create the same schema that the application expects."""
import os
from pathlib import Path
import subprocess
import sys


def test_sqlite_migration_roundtrip_and_model_consistency(tmp_path):
    env = dict(os.environ)
    env.update(ENVIRONMENT="test", DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path}/migrations.db", REDIS_URL="",
               ANALYTICS_MODE="inline", RATE_LIMIT_ENABLED="false")
    backend = Path(__file__).resolve().parents[1]
    for args in [["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]]:
        result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=backend, env=env,
                                text=True, capture_output=True, timeout=45)
        assert result.returncode == 0, result.stdout + result.stderr
