# API reference

Base prefix: `/api/v1`. The production frontend uses same-origin relative requests. In local Docker, Swagger is at <http://localhost:8000/docs> and the full OpenAPI schema at <http://localhost:8000/openapi.json>.

Use `Content-Type: application/json` for request bodies. Except registration, login, redirects, and health endpoints, send `Authorization: Bearer YOUR_TOKEN`. Timestamps use ISO 8601 with a UTC offset. Identifiers are UUID strings. Treat `short_url` returned by the server as authoritative.

## Accounts

### Register — `POST /auth/register`

```json
{
  "name": "Harsh",
  "email": "harsh@example.com",
  "password": "replace-with-a-long-private-password"
}
```

Returns `201` and `{id,name,email,created_at}`. Names contain 1–80 characters, passwords 10–128. Duplicate email returns `409`. The server stores a password hash, never the supplied password.

### Log in — `POST /auth/login`

```json
{"email":"harsh@example.com","password":"replace-with-a-long-private-password"}
```

Returns:

```json
{
  "access_token": "JWT_VALUE",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {"id":"UUID","name":"Harsh","email":"harsh@example.com","created_at":"2026-11-18T10:00:00Z"}
}
```

The example timestamp and IDs are illustrative. Invalid credentials return `401`. The API does not currently issue refresh tokens or implement password reset, email verification, or server-side logout revocation.

### Profile — `GET /auth/me`

Returns the authenticated user. Missing, invalid, expired, or unsupported tokens return `401`.

## Links

### Create — `POST /urls`

```json
{
  "original_url": "https://example.com/articles/system-design",
  "title": "System design notes",
  "custom_alias": "my-design-notes",
  "expires_at": "2027-12-01T00:00:00Z"
}
```

Only `original_url` is required. Omit `custom_alias` for a generated code. Custom aliases are 3–32 ASCII letters, digits, underscores, or hyphens; reserved names are rejected. Codes are case sensitive. Duplicate or previously reserved aliases return `409`.

HTTP and HTTPS URLs are accepted. Credentials in URLs, unsafe schemes, localhost, and private/reserved literal IP addresses are rejected. Linkforge does not retrieve destination pages or determine whether a public hostname is trustworthy.

Returns `201` with a link:

```json
{
  "id": "UUID",
  "original_url": "https://example.com/articles/system-design",
  "short_code": "my-design-notes",
  "short_url": "http://localhost:8080/r/my-design-notes",
  "title": "System design notes",
  "is_active": true,
  "created_at": "2026-11-18T10:00:00Z",
  "expires_at": "2027-12-01T00:00:00Z",
  "click_count": 0
}
```

### List — `GET /urls`

Query parameters:

| Parameter | Example | Purpose |
| --- | --- | --- |
| `page` | `1` | Page number, starting at 1 |
| `page_size` | `10` | Number of records per page, subject to validation limits |
| `search` | `design` | Search owned links |
| `status` | `all`, `active`, `inactive`, `expired` | Filter links |

Returns `{items:[Link],total,page,page_size}`. Soft-deleted links are excluded. A paused link and an expired link are different concepts; expiration is evaluated using the server's time.

### Details — `GET /urls/{id}`

Returns one owned link. Unknown, deleted, and another user's links return `404`.

### Edit — `PATCH /urls/{id}`

```json
{
  "title": "Updated notes",
  "original_url": "https://example.com/new-page",
  "is_active": true,
  "expires_at": null
}
```

Fields are optional. Omit `expires_at` to preserve it; explicitly send `null` to remove an expiry. The short code cannot be changed. Returns `200` with the updated link. The cache is invalidated after the database change.

### Delete — `DELETE /urls/{id}`

Returns `204` without a response body. This is a soft delete: it hides the link from management/analytics and denies redirects while reserving the code permanently. There is no restore endpoint or end-user hard-delete workflow in v1.

## Redirects

`GET /r/{short_code}` is outside `/api/v1`. It is public and returns `302` with the destination in `Location` and `Cache-Control: no-store`. A GET submits a click event. `HEAD` returns redirect metadata without recording a click.

| State | Status |
| --- | --- |
| Valid active link | `302` |
| Paused or expired link | `410` |
| Unknown or deleted code | `404` |

If your HTTP test client follows redirects, you will see the destination site's final response instead. Disable follow-redirects to inspect Linkforge's `302`.

## Analytics

### Link analytics — `GET /urls/{id}/analytics?days=30`

Supported periods: 7, 30, or 90 days. Returns:

```json
{
  "url_id": "UUID",
  "short_code": "my-design-notes",
  "total_clicks": 42,
  "period_clicks": 12,
  "days": 30,
  "clicks_by_day": [{"date":"2026-11-18","clicks":12}],
  "referrers": [{"referrer":"example.com","clicks":8}],
  "devices": [{"device":"desktop","clicks":12}]
}
```

The numbers above are illustrative. Daily series include zero-filled dates. Buckets use UTC. Totals may lag redirect requests while the worker processes events. Referrers depend on browser privacy policy and may be absent; device type is an approximate user-agent classification.

### Dashboard — `GET /dashboard?days=30`

Returns `{total_links,active_links,total_clicks,period_clicks,clicks_by_day,top_links}`. All data is restricted to the current user. Deleted links are excluded, so displayed totals can decrease after deletion.

## Health and errors

`GET /health/live` checks that the process can respond. `GET /health/ready` checks dependencies: PostgreSQL is required; Redis can be reported degraded while redirects still have a database fallback. Worker health is not implied by API liveness. Inspect stream backlog and worker logs when analytics lag.

`GET /metrics` is intended for internal monitoring. In production it requires `Authorization: Bearer METRICS_TOKEN`; without a configured metrics token it returns `404`. The setup script generates a token, and Compose passes it to the API. The frontend reverse proxy does not expose metrics. Use the loopback API port or a private monitoring network.

Most application errors use `{"detail":"message"}`. Validation errors use FastAPI's structured `detail` array. Clients must support both forms.

| Code | Meaning |
| --- | --- |
| `401` | Missing/invalid authentication or incorrect login |
| `404` | Missing resource or deliberately concealed ownership mismatch |
| `409` | Duplicate email or short code |
| `410` | Inactive/expired redirect |
| `422` | Invalid input |
| `429` | Rate limit reached; respect `Retry-After` |
| `503` | Required dependency or production rate limiter unavailable |

Authentication limits are keyed by client IP; creation limits are keyed by user. Behind a proxy, trust forwarded addresses only from the controlled proxy path. Compose binds the direct API port to loopback and relies on its Nginx entry point.

## curl example

Run from a shell where curl is available. On Windows PowerShell, use `curl.exe` to avoid older PowerShell's alias behavior. For easiest Windows testing use Swagger or `scripts/smoke_test.py`.

```bash
curl -i http://localhost:8080/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Harsh","email":"harsh@example.com","password":"replace-with-a-long-private-password"}'

curl -s http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"harsh@example.com","password":"replace-with-a-long-private-password"}'

curl -i http://localhost:8080/api/v1/urls \
  -H 'Authorization: Bearer PASTE_YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"original_url":"https://example.com/","title":"My example"}'

curl -I http://localhost:8080/r/PASTE_YOUR_CODE
```

`curl -I` sends HEAD and intentionally does not increment clicks. Use a regular GET without `-L` to test a counted redirect while avoiding the destination request.
