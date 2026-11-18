"""Run a real HTTP workflow against a running Linkforge deployment.

Usage: python scripts/smoke_test.py --base-url http://localhost:8080
Requires httpx. It creates a disposable account and soft-deletes its test links.
"""

import argparse
import secrets
import time

import httpx


def expect(response: httpx.Response, status: int) -> dict:
    if response.status_code != status:
        raise RuntimeError(f"{response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}: {response.text[:500]}")
    return response.json() if response.content else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--analytics-timeout", type=float, default=30)
    args = parser.parse_args()
    suffix = secrets.token_hex(6)
    email, password = f"smoke-{suffix}@example.com", secrets.token_urlsafe(24)
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=10, follow_redirects=False) as client:
        expect(client.get("/health/live"), 200)
        expect(client.get("/health/ready"), 200)
        expect(client.get("/api/v1/urls"), 401)
        expect(client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": "Smoke test"}), 201)
        login = expect(client.post("/api/v1/auth/login", json={"email": email, "password": password}), 200)
        client.headers["Authorization"] = f"Bearer {login['access_token']}"
        expect(client.get("/api/v1/auth/me"), 200)
        link = expect(client.post("/api/v1/urls", json={"original_url": "https://example.com/", "title": "Smoke test", "custom_alias": f"smoke-{suffix}"}), 201)
        link_id, path = link["id"], f"/r/{link['short_code']}"
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=10, follow_redirects=False) as other:
            other_email = f"smoke-other-{suffix}@example.com"
            expect(other.post("/api/v1/auth/register", json={"email": other_email, "password": password, "name": "Other smoke user"}), 201)
            other_login = expect(other.post("/api/v1/auth/login", json={"email": other_email, "password": password}), 200)
            other.headers["Authorization"] = f"Bearer {other_login['access_token']}"
            expect(other.get(f"/api/v1/urls/{link_id}"), 404)
            expect(other.patch(f"/api/v1/urls/{link_id}", json={"is_active": False}), 404)
            expect(other.get(f"/api/v1/urls/{link_id}/analytics?days=7"), 404)
        expect(client.head(path), 302)
        for _ in range(3):
            redirected = client.get(path)
            expect(redirected, 302)
            assert redirected.headers["location"] == "https://example.com/"
            assert "no-store" in redirected.headers.get("cache-control", "")
        deadline = time.monotonic() + args.analytics_timeout
        while True:
            analytics = expect(client.get(f"/api/v1/urls/{link_id}/analytics?days=7"), 200)
            if analytics["total_clicks"] >= 3:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Analytics did not receive three clicks. Check worker logs / Redis connectivity.")
            time.sleep(0.5)
        expect(client.patch(f"/api/v1/urls/{link_id}", json={"is_active": False}), 200)
        expect(client.get(path), 410)
        expect(client.patch(f"/api/v1/urls/{link_id}", json={"is_active": True, "title": "Updated smoke test"}), 200)
        expect(client.get(path), 302)
        dashboard = expect(client.get("/api/v1/dashboard?days=7"), 200)
        assert dashboard["total_links"] == 1
        expect(client.delete(f"/api/v1/urls/{link_id}"), 204)
        expect(client.get(path), 404)
        expect(client.get(f"/api/v1/urls/{link_id}"), 404)
    print("PASS: health, registration, JWT, ownership-protected CRUD, redirect, cache invalidation, worker analytics, dashboard, soft deletion.")
    print(f"Created disposable accounts {email} and {other_email}; test link is deleted. No destination was fetched.")


if __name__ == "__main__":
    main()
