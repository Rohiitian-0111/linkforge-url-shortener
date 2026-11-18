import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from conftest import create_link, sign_in


pytestmark = pytest.mark.asyncio


async def test_create_redirect_and_no_cache(client, auth):
    link = await create_link(client, auth)
    assert len(link["short_code"]) == 8
    assert link["short_url"] == "http://testserver/r/" + link["short_code"]
    result = await client.get("/r/" + link["short_code"])
    assert result.status_code == 302
    assert result.headers["location"] == link["original_url"]
    assert "no-store" in result.headers["cache-control"]


async def test_head_does_not_count_and_unknown_is_404(client, auth):
    link = await create_link(client, auth)
    head = await client.head("/r/" + link["short_code"])
    assert head.status_code == 302
    details = await client.get(f'/api/v1/urls/{link["id"]}', headers=auth)
    assert details.json()["click_count"] == 0
    assert (await client.get("/r/does-not-exist")).status_code == 404


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://example.com/file", "file:///etc/passwd", "https://user:pass@example.com", "http://localhost:8000", "http://127.0.0.1", "http://10.0.0.1/path", "http://169.254.169.254", "http://[::1]"])
async def test_invalid_or_unsafe_destinations(client, auth, url):
    response = await client.post("/api/v1/urls", headers=auth, json={"original_url": url})
    assert response.status_code == 422, response.text


async def test_custom_alias_conflict_and_case_sensitivity(client, auth):
    link = await create_link(client, auth, custom_alias="My_Portfolio-1")
    assert link["short_code"] == "My_Portfolio-1"
    conflict = await client.post("/api/v1/urls", headers=auth, json={"original_url": "https://example.org", "custom_alias": "My_Portfolio-1"})
    assert conflict.status_code == 409
    assert (await client.get("/r/My_Portfolio-1")).status_code == 302


@pytest.mark.parametrize("alias", ["ab", "has space", "../secret", "snow☃", "x" * 33, "api", "docs"])
async def test_invalid_or_reserved_aliases(client, auth, alias):
    response = await client.post("/api/v1/urls", headers=auth, json={"original_url": "https://example.com", "custom_alias": alias})
    assert response.status_code == 422, response.text


async def test_ownership_enforced_everywhere(client, auth):
    link = await create_link(client, auth)
    other = await sign_in(client, "other@example.com")
    base = f'/api/v1/urls/{link["id"]}'
    assert (await client.get(base, headers=other)).status_code == 404
    assert (await client.get(base + "/analytics", headers=other)).status_code == 404
    assert (await client.patch(base, headers=other, json={"title": "stolen"})).status_code == 404
    assert (await client.delete(base, headers=other)).status_code == 404
    assert (await client.get("/api/v1/urls", headers=other)).json()["total"] == 0


async def test_edit_pause_resume_and_delete_invalidate_cache(client, auth):
    link = await create_link(client, auth, custom_alias="lifecycle")
    route = "/r/" + link["short_code"]
    endpoint = f'/api/v1/urls/{link["id"]}'
    assert (await client.get(route)).status_code == 302
    edit = await client.patch(endpoint, headers=auth, json={"original_url": "https://example.org/new", "title": "Updated"})
    assert edit.status_code == 200
    assert (await client.get(route)).headers["location"] == "https://example.org/new"
    assert (await client.patch(endpoint, headers=auth, json={"is_active": False})).status_code == 200
    assert (await client.get(route)).status_code == 410
    await client.patch(endpoint, headers=auth, json={"is_active": True})
    assert (await client.get(route)).status_code == 302
    assert (await client.delete(endpoint, headers=auth)).status_code == 204
    assert (await client.get(route)).status_code == 404
    assert (await client.get(endpoint, headers=auth)).status_code == 404
    reuse = await client.post("/api/v1/urls", headers=auth, json={"original_url": "https://example.net", "custom_alias": "lifecycle"})
    assert reuse.status_code == 409


async def test_expiry_survives_cache_hits_and_can_be_cleared(client, auth):
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=1.3)).isoformat()
    link = await create_link(client, auth, expires_at=expiry)
    route = "/r/" + link["short_code"]
    assert (await client.get(route)).status_code == 302
    await asyncio.sleep(1.4)
    assert (await client.get(route)).status_code == 410
    cleared = await client.patch(f'/api/v1/urls/{link["id"]}', headers=auth, json={"expires_at": None})
    assert cleared.status_code == 200
    assert cleared.json()["expires_at"] is None
    assert (await client.get(route)).status_code == 302


async def test_past_expiry_and_invalid_query_parameters(client, auth):
    expiry = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    assert (await client.post("/api/v1/urls", headers=auth, json={"original_url": "https://example.com", "expires_at": expiry})).status_code == 422
    for query in ["page=0", "page_size=1001", "status=wrong"]:
        assert (await client.get("/api/v1/urls?" + query, headers=auth)).status_code == 422


async def test_pagination_search_and_filters(client, auth):
    first = await create_link(client, auth, title="API documentation")
    await create_link(client, auth, title="Portfolio")
    await create_link(client, auth, title="Conference")
    page = await client.get("/api/v1/urls?page=1&page_size=2", headers=auth)
    assert page.status_code == 200 and page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    assert len((await client.get("/api/v1/urls?page=2&page_size=2", headers=auth)).json()["items"]) == 1
    search = await client.get("/api/v1/urls?search=Portfolio", headers=auth)
    assert search.json()["total"] == 1
    await client.patch(f'/api/v1/urls/{first["id"]}', headers=auth, json={"is_active": False})
    assert (await client.get("/api/v1/urls?status=inactive", headers=auth)).json()["total"] == 1
    assert (await client.get("/api/v1/urls?status=active", headers=auth)).json()["total"] == 2


async def test_concurrent_alias_creation_has_one_winner(client, auth):
    async def create():
        return await client.post("/api/v1/urls", headers=auth, json={"original_url": "https://example.com", "custom_alias": "same-alias"})
    results = await asyncio.gather(create(), create(), create())
    assert sorted(response.status_code for response in results) == [201, 409, 409]


async def test_random_code_collision_retries_transaction(client, auth, monkeypatch):
    await create_link(client, auth, custom_alias="occupied")
    codes = iter(["occupied", "newcode8"])
    monkeypatch.setattr("app.security.generate_short_code", lambda: next(codes))
    link = await create_link(client, auth)
    assert link["short_code"] == "newcode8"
    assert (await client.get("/r/newcode8")).status_code == 302

