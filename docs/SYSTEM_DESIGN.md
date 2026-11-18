# Explain Linkforge in a system design interview

This guide distinguishes what the repository implements from what you would add for a larger deployment. Use real test results from your own environment. Do not describe unbuilt replication, sharding, failover, or abuse-detection features as implemented.

## A clear opening explanation

> Linkforge turns long URLs into short links. A FastAPI service manages accounts and links in PostgreSQL, Redis caches active mappings, and a separate worker processes click events from Redis Streams. PostgreSQL enforces uniqueness. The redirect path avoids waiting for analytics aggregation. The dashboard calls the same authenticated APIs exposed in Swagger. I built and tested the failure paths as well as the normal workflow.

Replace the final sentence with the exact tests you have run and can explain. The source includes automated tests and a reproducible smoke workflow.

## 1. Establish requirements before components

Start by asking about the product and its expected behavior:

- Is shortening anonymous, authenticated, or both? This implementation requires accounts for creation.
- Can destinations change? Here they can, so cached mappings and redirect responses must reflect updates.
- Do aliases expire or become reusable? This implementation reserves deleted aliases permanently.
- Are click counts approximate or billing-grade? Here they are observed GET counts with possible loss during failures.
- Which matters more during outages: redirect availability or immediate revocation? This design accepts bounded cache staleness.
- What are expected writes, redirects, peak factor, retention, and latency targets?

Requirements determine the design. For example, billing-grade analytics would make the durability choices materially different.

## 2. Capacity math with explicit assumptions

Use this worked example as a **hypothetical interview scenario**, not a measured project capability:

| Assumption | Value |
| --- | ---: |
| New links per day | 1,000,000 |
| Redirects per day | 100,000,000 |
| Peak factor | 10× average |
| Logical bytes per stored link | 500 bytes, illustrative |
| Logical bytes per click event | 150 bytes, illustrative |
| Hot mappings in cache | 10,000,000 |
| Logical bytes per cached mapping | 300 bytes, illustrative |

Calculations:

- Average creation traffic: `1,000,000 / 86,400 ≈ 11.6 requests/second`.
- Average redirects: `100,000,000 / 86,400 ≈ 1,157 requests/second`.
- Hypothetical 10× redirect peak: about `11,574 requests/second`.
- Link payload per year: `1,000,000 × 365 × 500 ≈ 182.5 GB` in decimal units.
- Click payload per day: `100,000,000 × 150 ≈ 15 GB` before indexes, replicas, backups, and database overhead.
- Hot cache payload: `10,000,000 × 300 ≈ 3 GB` before Redis/key/object overhead and fragmentation.

The lesson is that analytics can grow much faster than the link table. Do not multiply an arbitrary row-size estimate and call it the complete disk or memory requirement. Measure actual serialized records, index sizes, replication, and operational headroom.

## 3. Why random Base62 codes?

Eight characters using 62 symbols produce:

`62^8 = 218,340,105,584,896 possible codes`.

This large namespace and random generation avoid a central ID allocator and make sequential enumeration harder. Codes are still public identifiers, not authentication secrets. Rate limits and authorization remain necessary.

The database's unique constraint handles collisions. For a custom alias, a collision returns `409`; for a generated code, the service retries.

For `n` independent generated codes and namespace `N`, the birthday approximation for the probability of at least one collision is:

`P ≈ 1 − exp(−n(n−1)/(2N))`.

At one million generated codes, this gives about 0.23% for at least one collision somewhere in the set. That does not mean 0.23% of inserts fail. At ten million occupied codes, one additional random attempt collides with probability about `10,000,000 / N ≈ 0.00000458%`. These are mathematical estimates under uniform independent draws, not measurements.

Alternative approaches:

| Approach | Advantages | Costs |
| --- | --- | --- |
| Random Base62 + unique index | Simple distributed generation, hard to predict | Collision retry, random index access |
| Base62 of a sequence | Compact, unique by construction | Central allocation or range leasing; easy enumeration |
| Distributed time-based ID | Decentralized allocation, sortable IDs | Clock/node coordination, larger encoded codes |
| Hash destination | Deterministic for same input | Collisions, privacy, and user-specific ownership/expiry semantics |

Explain the requirement that motivates a change before introducing Snowflake-style IDs.

## 4. Why PostgreSQL?

The system needs unique emails/codes, ownership relationships, updates, and transactional analytics deduplication. PostgreSQL provides those in one familiar store. The indexed short-code lookup is simple and Redis absorbs hot reads.

The implementation uses one async session per request/task. Sharing one mutable SQLAlchemy session across concurrent tasks would mix transaction state; the official [SQLAlchemy documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks) describes this constraint.

Read replicas are a possible later improvement, but introduce lag. A newly created link could miss on a replica. You might read the primary on a cache/replica miss, populate the cache on creation, or route recent writes to a primary-aware path. None of those should be assumed to happen automatically.

## 5. Cache questions worth practicing

**What is cache-aside?** The application checks Redis, then reads the database on a miss and fills the cache. PostgreSQL stays authoritative.

**What happens when Redis is down?** Reads fall back to PostgreSQL. That protects availability but can overload the database if traffic was previously mostly cache hits. Add load shedding, connection-pool limits, circuit breakers, or a bounded local cache if the required traffic justifies them.

**Why not cache forever?** Destinations and active flags can change. A TTL bounds the stale-data window when invalidation fails.

**How do you stop stale repopulation?** This code compares a per-code generation captured before the DB read with the current generation during cache fill. A mutation increments it atomically with cache deletion.

**Is that strongly consistent?** No. Database commit and Redis invalidation are separate. There is a brief commit/invalidation gap, and an outage can leave stale data until TTL. Say exactly which race is addressed and which is not.

**What about a viral hot link?** Redis handles repeated reads, but expiry can create a stampede. Future options include TTL jitter, single-flight fills, bounded stale serving, and replication. Serving stale links may conflict with immediate revocation requirements.

## 6. Analytics questions

**Why a queue?** Redirects should not wait for expensive aggregation and reporting. The request enqueues a small event; the worker persists it. A queue also absorbs bursts while processing catches up.

**Is the queue durable?** Redis has AOF enabled, but `appendfsync everysec` can lose recently accepted events on a hard crash. The worker commits before ACK and recovers pending deliveries. This improves recovery but does not make ingestion zero-loss.

**How do retries avoid double counts?** Each click has a UUID. Insert-on-conflict does nothing for an existing event. The event insert and counter increment are one transaction. This gives an idempotent database effect under at-least-once delivery.

**What happens if the worker stops?** Redirects keep enqueuing. Counts lag and memory grows. The primary stream does not trim unprocessed entries. Monitor backlog and memory; a bounded infrastructure budget eventually requires rejection or load shedding.

**Why not Kafka?** The required behavior can be demonstrated with Redis Streams and fewer moving parts. A larger retention/replay/event-consumer workload may justify a dedicated streaming platform. Choosing it should follow requirements, not the size of its logo on the diagram.

**What makes a click?** An observed GET that passes link validity checks. It is not proof of a human, a unique visitor, or a loaded destination page.

## 7. Failure drills to demonstrate

Use a disposable local deployment. Run one change at a time and restore the service afterwards.

| Drill | How | What you should observe |
| --- | --- | --- |
| Stop worker | `docker compose stop worker` | Redirects work; analytics wait; Redis stream grows |
| Restart worker | `docker compose start worker` | Backlog processes; totals catch up |
| Stop Redis | `docker compose stop redis` | Redirects use DB; production auth/create blocked by rate-limit dependency |
| Restart Redis | `docker compose start redis` | Cache and stream recover; inspect TTL/invalidation trade-offs |
| Pause a warm link | Use UI after redirecting it once | Future redirects return `410` when invalidation is reachable |
| Replay an event | Run the idempotence test | Stored click count increases once |
| Concurrent alias claims | Run concurrency tests | One claim succeeds; duplicate gets `409` |
| Another user's link ID | Run ownership tests | Management and analytics return `404` |

Do not intentionally stop a shared or production service for a demo. These drills target your own local project.

## 8. How the architecture evolves

### First growth step: more application capacity

Run multiple API containers behind a load balancer. Keep data and rate counters shared. Size each connection pool and multiply by the instance count; database connections are finite. Monitor queue lag separately from API latency. Scrape metrics per instance.

### Next step: isolate workloads

Split cache Redis from durable event Redis. Move analytics aggregations to precomputed daily rollups or an analytical database. Partition raw events by time and add an explicit retention job. Keep immutable event IDs long enough to match replay policy; deleting deduplication state while old events can replay can reintroduce double counting.

### Availability step: remove single points of failure

Use PostgreSQL replication/failover, Redis HA or a dedicated queue, automated backups, tested restores, health-aware load balancing, timeouts, and resource limits. These changes require operational procedures and failure tests, not just extra boxes in the diagram.

### Very large scale: partition only when necessary

Hash-partition mappings by short code when one database cannot meet capacity or operational requirements. Custom-alias uniqueness then needs deterministic routing or a separate namespace authority. Decide how dashboards query a user's links across shards. Do not hide those costs behind the word “sharding”.

### Geographic scale

Global caches and regional application instances reduce network latency, but replicated updates and revocations introduce consistency trade-offs. Decide where aliases are created, which region owns writes, how failover works, and how long outdated destinations are acceptable.

## 9. Suggested demo sequence

1. Register and create a custom alias.
2. Open the short link and show the real destination.
3. Show a click appearing in analytics.
4. Pause the link and explain cache invalidation.
5. Show automated ownership, uniqueness, expiry, and worker replay tests.
6. Draw the redirect and queue paths.
7. Explain one failure you tested and one limitation you deliberately accepted.
8. Show measured latency with workload and environment details.

## 10. Resume wording after you run it

Accurate baseline:

> Built a full-stack URL shortener using FastAPI, PostgreSQL, Redis, and React, with JWT authentication, Redis caching/rate limits, and asynchronous click analytics. Implemented database-enforced alias uniqueness, owner-scoped APIs, expiry checks, and idempotent worker processing; packaged the application with Docker and automated tests.

Add a performance number only after measuring it yourself, for example: “Measured p95 redirect latency of [result] ms at [concurrency] on [hardware/configuration], with [error rate].” Do not describe a single-machine load test as proof of global scale.
