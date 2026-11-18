"""Measure one existing short link; does not follow the destination redirect.

Use a dedicated test link: successful GET requests count as clicks.
Run only against infrastructure you own or are permitted to test.
"""

import argparse
import asyncio
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import time

import httpx


def percentile(values: list[float], proportion: float) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * proportion) - 1)]


async def run(args: argparse.Namespace) -> dict:
    latencies: list[float] = []
    statuses: Counter[str] = Counter()
    remaining = iter(range(args.requests))
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(timeout=args.timeout, follow_redirects=False, limits=limits) as client:
        async def worker() -> None:
            for _ in remaining:
                start = time.perf_counter()
                try:
                    response = await client.get(args.url)
                    statuses[str(response.status_code)] += 1
                except httpx.HTTPError as exc:
                    statuses[type(exc).__name__] += 1
                latencies.append((time.perf_counter() - start) * 1000)
        started = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(args.concurrency)))
        elapsed = time.perf_counter() - started
    return {
        "url": args.url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(args.requests / elapsed, 2),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
        },
        "status_counts": dict(statuses),
        "all_redirects_succeeded": statuses.get("302", 0) == args.requests,
        "note": "Client-observed latency includes queue submission; not a production capacity guarantee.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="A full short URL on your own deployment")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()
    if not 1 <= args.requests <= 1_000_000 or not 1 <= args.concurrency <= 500 or args.timeout <= 0:
        parser.error("Use 1..1,000,000 requests, 1..500 concurrency, and a positive timeout.")
    if not args.url.startswith(("https://", "http://")):
        parser.error("URL must begin with http:// or https://.")
    result = asyncio.run(run(args))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_redirects_succeeded"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
