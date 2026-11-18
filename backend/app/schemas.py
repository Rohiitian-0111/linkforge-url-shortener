import ipaddress
import re
from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, TypeAdapter, field_validator

from app.models import utcnow


RESERVED_CODES = {"api", "admin", "health", "docs", "redoc", "metrics", "login", "register", "dashboard", "app", "static", "assets", "favicon", "robots"}
URL_ADAPTER = TypeAdapter(HttpUrl)


def validate_destination(value: str) -> str:
    if len(value) > 4096 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("URL must be at most 4096 characters with no control characters")
    try:
        url = URL_ADAPTER.validate_python(value)
    except Exception as exc:
        raise ValueError("Enter a valid http or https URL") from exc
    if url.username or url.password:
        raise ValueError("URLs containing credentials are not allowed")
    host = (url.host or "").strip("[]").lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host and ":" not in host:
        raise ValueError("Local and internal addresses are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private, loopback and reserved IP addresses are not allowed")
    return str(url)


def validate_expiry(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("Expiry must include a timezone, for example 2027-01-01T00:00:00Z")
    value = value.astimezone(timezone.utc)
    if value <= utcnow():
        raise ValueError("Expiry must be in the future")
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: Annotated[str, Field(min_length=10, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=80)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class URLCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_url: str
    title: str = Field(default="", max_length=160)
    custom_alias: str | None = None
    expires_at: datetime | None = None

    _destination = field_validator("original_url")(validate_destination)
    _expiry = field_validator("expires_at")(validate_expiry)

    @field_validator("custom_alias")
    @classmethod
    def validate_alias(cls, value):
        if value is None:
            return value
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", value):
            raise ValueError("Alias must be 3–32 ASCII letters, numbers, hyphens or underscores")
        if value.lower() in RESERVED_CODES:
            raise ValueError("This alias is reserved")
        return value


class URLPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_url: str | None = None
    title: str | None = Field(default=None, max_length=160)
    expires_at: datetime | None = None
    is_active: bool | None = None

    @field_validator("original_url")
    @classmethod
    def validate_original_url(cls, value):
        if value is None:
            raise ValueError("original_url cannot be null")
        return validate_destination(value)

    @field_validator("title", "is_active")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value

    _expiry = field_validator("expires_at")(validate_expiry)


class URLResponse(BaseModel):
    id: str
    original_url: str
    short_code: str
    short_url: str
    title: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    click_count: int


class URLListResponse(BaseModel):
    items: list[URLResponse]
    total: int
    page: int
    page_size: int
