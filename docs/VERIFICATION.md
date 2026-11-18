# Verification report

**Verified on 18 November 2026.** This report describes the delivered source, the checks actually run, and the remaining environment-specific checks. It is not a guarantee of production capacity or uptime.

## Results

| Check | Result | Scope |
| --- | --- | --- |
| Backend suite: SQLite + fakeredis | **57 passed** | Real application factory, routes, database transactions, and Redis-compatible command behavior |
| Same backend suite: PostgreSQL + Redis | **57 passed** | Actual PostgreSQL 16.2 and Redis 6.2.14 processes; not mocks |
| Frontend component suite | **16 passed** | Production React components in jsdom, with controlled HTTP response fixtures |
| TypeScript + production build | **Passed** | `npm run build`; 32 production modules transformed |
| SQLite migrations | **Passed** | Upgrade, schema comparison, downgrade, and upgrade round trip |
| PostgreSQL migrations | **Passed** | `alembic upgrade head` and `alembic check`; no model/schema drift detected |
| Live HTTP smoke workflow | **Passed** | Separate API/worker processes with real PostgreSQL/Redis, tested directly and through the Vite frontend proxy |
| Redirect workload script | **Passed** | 40 requests at concurrency 4 returned 40 HTTP 302 responses; the worker persisted all 40 click events |
| Account-screen visual inspection | **Passed** | Login and registration pages inspected in a desktop browser |
| Configuration-generation script | **Passed** | Four distinct secrets generated; a repeated run preserved the file; placeholder configuration was refused |
| YAML and script syntax | **Passed** | Compose, HTTPS overlay, CI YAML parsed; Python helper scripts parsed |

The backend suite is the **same 57 tests run in two storage configurations**, not 114 different test cases. The frontend suite adds 16 component tests. Test fixtures are confined to test files and are not loaded by the production frontend.

## Behaviors exercised

### Authentication and ownership

- Registration, case-insensitive duplicate email rejection, password bounds, login, and profile retrieval.
- Invalid, expired, and wrong-audience JWT rejection.
- Missing authentication rejection and owner-only link/analytics access.
- Cross-owner GET, PATCH, DELETE, and analytics attempts return `404`.

### Link lifecycle and correctness

- Random code generation, deterministic collision retry, custom aliases, reserved aliases, and invalid inputs.
- Concurrent attempts to claim one alias produce one successful insert.
- Real redirect status, destination query/fragment preservation, and `Cache-Control: no-store`.
- `HEAD` redirects without incrementing click counts.
- Search, pagination, active/paused/expired filtering, editing, pause/resume, deletion, and alias reservation.
- Expiry is enforced even when a cached mapping is present; clearing expiry makes the link usable again.

### Caching and degraded behavior

- Mutation invalidation and generation-checked writes prevent a stale reader from repopulating an invalidated cache entry.
- Malformed cache payloads fall back to the database.
- Redis failure falls back to database lookup and inline analytics persistence.
- Cached redirects remain usable when the database is unavailable and analytics cannot be written.
- Cold redirects and readiness return a controlled `503` for an unavailable database, including an actual TCP connection refusal.
- Redis unavailability is reported as degraded readiness.
- Atomic counters enforce shared quotas under concurrent requests; production limits fail closed when Redis is unavailable.

### Analytics worker

- A queued event remains separate from persisted analytics until a worker consumes it.
- Replaying an already-committed event does not increment the counter twice.
- Concurrent duplicate events also produce one database effect.
- Abandoned pending events can be reclaimed by another worker.
- Database failure leaves an event pending; malformed payloads move to a dead-letter stream.
- Referrer paths/query strings and raw user-agent/IP values are not stored in click rows.
- Dashboard and per-link aggregates respect ownership and omit deleted links from visible totals.

### Frontend behavior

- Login/registration success and error handling, duplicate registration, and rate-limit feedback.
- Authenticated request headers, stored-session expiry, and sign-out after `401`.
- Dashboard data rendering, custom link creation, alias conflict errors, and refreshed link rows.
- Editing an expired link without resubmitting unchanged expiry; explicitly clearing expiry.
- Search/status query parameters, pause/resume, mutation failures, and delete confirmation.
- Analytics breakdowns and date-range requests.
- Dialog keyboard focus, Escape dismissal, and restored focus on the initiating control.

## Environment

| Component | Executed version / mode |
| --- | --- |
| OS | Linux verification workspace |
| Python | 3.12.14 |
| Node.js | 24.22.1 |
| npm | 11.9.0 |
| SQLite | 3.53.1 |
| PostgreSQL | 16.2 |
| Redis | 6.2.14 |
| Backend libraries | Versions pinned in `backend/requirements.txt` and `requirements-dev.txt` |
| Frontend libraries | Versions pinned in `frontend/package.json` and `package-lock.json` |

PostgreSQL and Redis were launched as native disposable local processes because this workspace did not have a Docker engine. The supplied Compose configuration targets **PostgreSQL 17 and Redis 7.4**. CI is configured to run the suite against those image versions, but that GitHub Actions workflow has not been executed on a user repository here.

## Checks still requiring your environment

1. **Docker images and Compose startup:** YAML was parsed and configuration was reviewed, but `docker compose up --build` was not executed in this workspace. Run it on your machine, then run `scripts/smoke_test.py`.
2. **Windows execution:** the Windows launcher and instructions are included; they were not run on a Windows host.
3. **Nginx/Caddy and public HTTPS:** configuration is included, but container-level proxy behavior, certificate issuance/renewal, DNS, and public reachability need a real deployment.
4. **Full signed-in browser workflow:** account screens were visually inspected. Signed-in functionality was tested through live HTTP and React component tests; it was not completed as a browser-to-production-Nginx test. Mobile viewport behavior also remains a manual visual check.
5. **Capacity, backups, and failover:** the small redirect workload verifies the measurement script and queue integration. It is not a load-capacity result. No cloud failover, restore drill, sustained peak workload, or public abuse-moderation workflow is claimed.

The source and deployment files are ready for those checks. See `WINDOWS_SETUP.md`, `DEPLOYMENT.md`, and `SYSTEM_DESIGN.md` for the commands, failure drills, and architectural trade-offs.

## Reproduce the main checks

From a Python environment with the backend development dependencies installed:

```bash
cd backend
pytest tests -q
```

For the same suite against real services, set `TEST_DATABASE_URL` to a **disposable PostgreSQL database whose name contains `test`** and `TEST_REDIS_URL` to a **disposable Redis database 15** before invoking pytest. Tests reset those stores. The GitHub Actions file contains a concrete service configuration.

From the frontend folder, using Node 22.12+ or a supported newer LTS release:

```bash
npm ci
npm test
npm run build
```

With the full stack running, from the repository root:

```bash
python scripts/smoke_test.py --base-url http://localhost:8080
```

The smoke test creates two disposable accounts and soft-deletes its link. It leaves the accounts in your test database and never follows the external destination.
