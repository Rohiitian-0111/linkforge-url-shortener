from prometheus_client import CollectorRegistry, Counter, Histogram


class Metrics:
    def __init__(self):
        # One registry per app keeps isolated tests and multiple app factories safe.
        self.registry = CollectorRegistry()
        self.requests = Counter("linkforge_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=self.registry)
        self.latency = Histogram("linkforge_http_request_seconds", "HTTP request latency", ["method", "route"], registry=self.registry)
        self.cache = Counter("linkforge_cache_lookups_total", "Redirect cache lookup results", ["result"], registry=self.registry)
        self.analytics = Counter("linkforge_analytics_events_total", "Click event ingestion", ["result"], registry=self.registry)
        self.redis_errors = Counter("linkforge_redis_errors_total", "Redis operation failures", ["operation"], registry=self.registry)
