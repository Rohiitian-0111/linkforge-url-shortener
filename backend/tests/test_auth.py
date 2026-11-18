from datetime import datetime, timedelta, timezone

import jwt
import pytest


pytestmark = pytest.mark.asyncio


async def test_registration_login_profile(client, user_payload):
    registered = await client.post("/api/v1/auth/register", json=user_payload)
    assert registered.status_code == 201
    assert registered.json()["email"] == user_payload["email"]
    assert "password" not in registered.text and "password_hash" not in registered.text
    token = await client.post("/api/v1/auth/login", json={"email": user_payload["email"], "password": user_payload["password"]})
    assert token.status_code == 200
    assert token.json()["token_type"] == "bearer"
    assert token.json()["expires_in"] > 0
    profile = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token.json()["access_token"]})
    assert profile.status_code == 200
    assert profile.json()["id"] == registered.json()["id"]


async def test_duplicate_email_is_case_insensitive(client, user_payload):
    assert (await client.post("/api/v1/auth/register", json=user_payload)).status_code == 201
    user_payload["email"] = user_payload["email"].upper()
    assert (await client.post("/api/v1/auth/register", json=user_payload)).status_code == 409


@pytest.mark.parametrize("password", ["short", "x" * 129])
async def test_password_bounds(client, user_payload, password):
    user_payload["password"] = password
    assert (await client.post("/api/v1/auth/register", json=user_payload)).status_code == 422


async def test_wrong_credentials_generic_error(client, user_payload):
    await client.post("/api/v1/auth/register", json=user_payload)
    existing = await client.post("/api/v1/auth/login", json={"email": user_payload["email"], "password": "WrongPassword!"})
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "WrongPassword!"})
    assert existing.status_code == unknown.status_code == 401
    assert existing.json() == unknown.json()


async def test_protected_endpoints_require_auth(client):
    for path in ["/api/v1/auth/me", "/api/v1/urls", "/api/v1/dashboard"]:
        result = await client.get(path)
        assert result.status_code == 401, (path, result.text)
    assert (await client.post("/api/v1/urls", json={"original_url": "https://example.com"})).status_code == 401


async def test_invalid_token_rejected(client):
    result = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer broken.token.value"})
    assert result.status_code == 401


async def test_expired_and_wrong_audience_tokens_rejected(app, client, auth):
    token = auth["Authorization"].split()[1]
    payload = jwt.decode(token, options={"verify_signature": False})
    payload["exp"] = int((datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp())
    expired = jwt.encode(payload, app.state.settings.jwt_secret, algorithm="HS256")
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + expired})).status_code == 401
    payload["exp"] = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    payload["aud"] = "other-service"
    wrong = jwt.encode(payload, app.state.settings.jwt_secret, algorithm="HS256")
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + wrong})).status_code == 401

