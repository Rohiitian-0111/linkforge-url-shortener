from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_SECRET = "development-only-change-this-before-deployment-0000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./linkforge.db"
    redis_url: str = ""
    jwt_secret: str = DEVELOPMENT_SECRET
    jwt_issuer: str = "linkforge"
    jwt_audience: str = "linkforge-api"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    public_base_url: str = "http://localhost:8080"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "api", "frontend"]
    cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    redis_timeout_seconds: float = Field(default=0.5, gt=0, le=10)
    rate_limit_enabled: bool = True
    auth_rate_limit: int = Field(default=20, ge=1)
    create_rate_limit: int = Field(default=100, ge=1)
    analytics_mode: Literal["stream", "inline"] = "stream"
    analytics_stream: str = "linkforge:clicks"
    analytics_group: str = "linkforge-workers"
    analytics_claim_idle_ms: int = Field(default=60000, ge=1)
    analytics_batch_size: int = Field(default=100, ge=1, le=1000)
    metrics_token: str = ""

    @model_validator(mode="after")
    def validate_deployment(self):
        self.public_base_url = self.public_base_url.rstrip("/")
        if not self.public_base_url.startswith(("http://", "https://")):
            raise ValueError("PUBLIC_BASE_URL must be an http(s) URL")
        if self.environment == "production":
            if len(self.jwt_secret) < 32 or self.jwt_secret == DEVELOPMENT_SECRET:
                raise ValueError("Set JWT_SECRET to a strong random secret of at least 32 characters")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production requires PostgreSQL")
            if "*" in self.cors_origins or "*" in self.trusted_hosts:
                raise ValueError("Production CORS_ORIGINS and TRUSTED_HOSTS must be explicit")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
