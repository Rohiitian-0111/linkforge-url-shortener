# Deployment and operations

The source is ready to run with Docker Compose. It has not automatically provisioned a public domain, cloud account, TLS certificate, or hosted database. This guide describes the final deployment work using infrastructure you control.

## 1. Choose a deployment shape

For a portfolio/demo, a Linux server with Docker Compose is the simplest way to preserve the entire stack. The supplied files run one PostgreSQL, one Redis, one API, one worker, and one Nginx frontend. Choose capacity based on your workload and monitor it; no server size or cost is implied here.

For a service expected to survive host failure, move PostgreSQL/Redis to managed or replicated infrastructure, keep the API/worker images, and configure their URLs. Compose's local named volumes do not protect against losing the host.

## 2. Configure the public hostname

Copy the source to the server and run:

```bash
python3 scripts/setup.py
```

Edit `.env`, preserving the generated secrets:

```dotenv
ENVIRONMENT=production
PUBLIC_BASE_URL=https://links.your-domain.example
CORS_ORIGINS=["https://links.your-domain.example"]
TRUSTED_HOSTS=["links.your-domain.example","localhost","127.0.0.1","api"]
```

Replace the illustrative hostname with one you own. Create its DNS record pointing to your server. Leave `localhost`/`127.0.0.1` for local container health checks. Keep `PUBLIC_BASE_URL` without a trailing slash.

`CORS_ORIGINS` describes browser origins, including scheme and any nonstandard port; `TRUSTED_HOSTS` contains hostnames without scheme or port. Same-origin production traffic does not require wildcard CORS.

## 3. Terminate HTTPS in front of the frontend

Place a TLS reverse proxy or your provider's HTTPS load balancer before frontend port 8080. Route it to the Nginx frontend, which already separates static assets, API, and `/r` redirects. Preserve the original Host header and configure forwarded-client handling deliberately.

For a host-level reverse proxy, bind frontend to loopback instead of all interfaces by setting this value in `.env`:

```dotenv
FRONTEND_BIND=127.0.0.1
```

The normal Compose frontend overwrites `X-Forwarded-For` with its direct peer address. This is correct when Nginx receives the actual client connection. If an additional trusted proxy sits in front, configure Nginx's real-IP module with **only that proxy's network** before using `$remote_addr` for forwarding. Otherwise every user may share the proxy's IP for rate limiting. Never trust arbitrary client-supplied forwarded headers.

The API command trusts its controlled proxy path, so its direct port must remain loopback/private. PostgreSQL and Redis have no published ports in the supplied Compose configuration. `/metrics` is blocked by the frontend and additionally needs its bearer token in production.

Use your proxy/provider's current official TLS instructions. The project does not bundle a certificate or make assumptions about a particular DNS provider.

### Optional: included Caddy HTTPS configuration

The repository includes an optional Compose overlay for automatic HTTPS. After your domain points at the server and ports 80/443 are reachable, add these settings to `.env` along with the public URL/origin/host settings above:

```dotenv
DOMAIN=links.your-domain.example
TLS_EMAIL=you@your-domain.example
FRONTEND_BIND=127.0.0.1
```

Run from the repository root:

```bash
docker compose -f docker-compose.yml -f deploy/compose.https.yml up --build -d
```

The overlay adds Caddy on ports 80/443, persists certificate state, and mounts an Nginx configuration that trusts only Caddy's fixed private address for forwarded client identity. The ordinary frontend port remains available only on loopback when `FRONTEND_BIND` is set as shown. Use both `-f` arguments for subsequent `logs`, `ps`, `up`, and `down` commands so the same service set is selected.

Its dedicated proxy subnet is `172.30.0.0/24`; Caddy uses `172.30.0.2`. If this conflicts with an existing network, change the subnet/IP in `deploy/compose.https.yml` and both occurrences of the trusted IP in `deploy/nginx.https.conf` together. Never broaden the trusted client-identity range to all addresses.

This HTTPS option is configuration provided for deployment. It needs your real DNS and reachable server to issue a certificate; it is not evidence that a public deployment or certificate has already been created. See [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) and its [reverse proxy header behavior](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#headers).

## 4. Start, inspect, and smoke test

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 migrate api worker
```

Migrations run as a one-shot service before API/worker startup. Only the migration service changes the schema; API startup does not call `create_all`. Do not run multiple independent migration jobs against the same database during a coordinated release.

Install `httpx` in an isolated Python environment and test the real hostname:

```bash
python scripts/smoke_test.py --base-url https://links.your-domain.example
```

The test creates disposable users and exercises the real HTTP path, including cross-owner access protection and worker analytics. It does not verify certificate renewal, disaster recovery, or provider failover. Test those separately when they are part of your availability requirements.

## 5. Backups and restoration

Back up PostgreSQL before schema changes and on a schedule appropriate to the acceptable data-loss window. For a local Compose instance, the following writes a custom-format dump to your **host** shell's current folder:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > linkforge-backup.dump
```

Use a binary-safe shell for redirection; older Windows PowerShell versions can alter binary output. On Windows, run that command in a suitable shell or copy a dump created inside the container using `docker cp`. Keep backups outside the server, encrypt them as appropriate, and restrict access.

Restore to a fresh **disposable** database first and verify accounts, link mappings, migrations, and analytics. Do not test restoration by overwriting the only live copy. Record the exact PostgreSQL version and schema revision along with each backup.

Redis AOF persists to its named volume. AOF is operational persistence, not an off-host backup. Restoring an old Redis event stream alongside a newer PostgreSQL backup can replay events; event-ID deduplication helps only for IDs still represented in the restored database. Treat cross-store recovery as a designed procedure.

## 6. Health and monitoring

| Signal | Meaning / action |
| --- | --- |
| `/health/live` fails | Process or network path unavailable |
| `/health/ready` has database unavailable | Mapping misses and DB-backed API operations cannot work |
| `/health/ready` reports Redis unavailable | Redirect fallback may work; production auth/create can fail closed |
| Analytics queued but totals lag | Inspect worker availability, Redis group backlog/pending events, DB writes |
| `linkforge_analytics_events_total{result="dropped"}` increases | Both enqueue and fallback failed; counts have been lost |
| Cache hit rate drops / DB latency rises | Inspect Redis, TTL, hot-key behavior, connection pools |
| Stream or Redis memory grows continually | Worker throughput is lower than ingestion or failures are blocking processing |

Metrics need `Authorization: Bearer <METRICS_TOKEN>` and should be collected privately from each API instance. Treat metrics secrets like any other credential. Never place them in a public dashboard URL. The worker currently reports progress/failure through logs; inspect Redis group state for lag.

The API emits sanitized route templates and request IDs and disables Uvicorn's access log in Compose. Review any additional proxy/cloud logging separately: providers may retain IP addresses and URLs outside the application database.

Runtime database connection/pool waits and commands have finite timeouts. A failed analytics enqueue followed by a failed database fallback can still add several seconds to a redirect before recording is abandoned; this is a bounded attempt, not an immediate fail-open guarantee. Measure degraded latency during your own failure drills.

`REDIS_MAXMEMORY` defaults to `256mb`. Increase it for the measured cache and backlog workload and leave additional host memory for persistence buffers, the database, containers, and the OS. `noeviction` protects queued entries from eviction but cannot protect a host that is already out of memory. A full Redis may still answer PING even while rejecting writes, so readiness alone is not sufficient monitoring.

## 7. Updates and rollback

1. Run tests and build the frontend for the candidate source revision.
2. Back up PostgreSQL and record the current application/schema version.
3. Review migration compatibility with the currently running API/worker.
4. Build and start the new revision with `docker compose up --build -d`.
5. Inspect migration, health, worker, and smoke-test results.

An application rollback is safe only when the previous code can read the migrated schema. Destructive schema downgrades are not a substitute for a backup. Prefer additive migrations and staged removal for a continuously available deployment.

Do not regenerate `.env` when updating an existing database. Changing the configured PostgreSQL password alone does not update the already-initialized database account. Rotate credentials through the database and application configuration together.

Changing `JWT_SECRET` invalidates existing access tokens. A deliberate rotation signs users out; document the operational change.

## 8. Retention and public-service additions

Raw click rows currently accumulate; the project does not automatically delete historical records. Add a scheduled retention/rollup job when deploying for long periods, and ensure it does not undermine your event-replay deduplication policy: deleting old event IDs while old queue deliveries can still replay could cause a second increment. Soft-deleted URLs reserve their aliases and remain in storage.

For an open public service, add ownership-appropriate account deletion/export, password recovery, email verification, abuse reporting/moderation, and a clear privacy/retention policy. These are defined product extensions, not features claimed by the current implementation.

The stack demonstrates system design mechanics but has single-host and single-store failure points by default. Decide your uptime, recovery time, recovery point, and analytics-loss requirements before selecting replication or a more durable queue.

## Official references

- [Docker Compose startup dependencies](https://docs.docker.com/compose/how-tos/startup-order/)
- [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
- [PostgreSQL pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html)
- [Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis Streams and consumer groups](https://redis.io/docs/latest/develop/data-types/streams/)
- [Nginx real IP configuration](https://nginx.org/en/docs/http/ngx_http_realip_module.html)
