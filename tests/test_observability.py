"""Tests for Wave 21 observability features — request ID, IP rate limiter, JSON logging, metrics."""

import asyncio
import logging
import sys
import os
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


# --- Request ID Middleware Tests ---


class TestRequestIDMiddleware:
    """Test X-Request-ID correlation middleware."""

    @pytest.mark.asyncio
    async def test_generates_request_id(self):
        from middleware.request_id import RequestIDMiddleware

        captured_id = None

        async def mock_app(scope, receive, send):
            from starlette.requests import Request
            request = Request(scope)
            nonlocal captured_id
            captured_id = request.state.request_id

        middleware = RequestIDMiddleware(mock_app)
        scope = {"type": "http", "method": "GET", "path": "/test",
                 "headers": [], "query_string": b"", "root_path": "",
                 "server": ("localhost", 8000)}

        await middleware(scope, _mock_receive, _mock_send)
        assert captured_id is not None
        assert len(captured_id) == 32  # uuid4 hex

    @pytest.mark.asyncio
    async def test_accepts_client_request_id(self):
        from middleware.request_id import RequestIDMiddleware

        captured_id = None

        async def mock_app(scope, receive, send):
            from starlette.requests import Request
            request = Request(scope)
            nonlocal captured_id
            captured_id = request.state.request_id

        middleware = RequestIDMiddleware(mock_app)
        scope = {"type": "http", "method": "GET", "path": "/test",
                 "headers": [(b"x-request-id", b"my-custom-id-123")],
                 "query_string": b"", "root_path": "",
                 "server": ("localhost", 8000)}

        await middleware(scope, _mock_receive, _mock_send)
        assert captured_id == "my-custom-id-123"

    @pytest.mark.asyncio
    async def test_adds_request_id_to_response(self):
        from middleware.request_id import RequestIDMiddleware

        response_headers = {}

        async def mock_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def capture_send(message):
            if message["type"] == "http.response.start":
                for k, v in message.get("headers", []):
                    response_headers[k.decode()] = v.decode()

        middleware = RequestIDMiddleware(mock_app)
        scope = {"type": "http", "method": "GET", "path": "/test",
                 "headers": [], "query_string": b"", "root_path": "",
                 "server": ("localhost", 8000)}

        await middleware(scope, _mock_receive, capture_send)
        assert "x-request-id" in response_headers
        assert len(response_headers["x-request-id"]) == 32

    @pytest.mark.asyncio
    async def test_skips_non_http(self):
        from middleware.request_id import RequestIDMiddleware

        called = False

        async def mock_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = RequestIDMiddleware(mock_app)
        await middleware({"type": "websocket"}, _mock_receive, _mock_send)
        assert called


# --- IP Rate Limiter Tests ---


class TestIPRateLimiter:
    """Test per-IP rate limiter."""

    def test_allows_within_limit(self):
        from rate_limiter import IPRateLimiter
        limiter = IPRateLimiter(default_rpm=10)
        allowed, headers = limiter.check("1.2.3.4")
        assert allowed
        assert "X-RateLimit-Limit" in headers

    def test_blocks_after_burst(self):
        from rate_limiter import IPRateLimiter
        limiter = IPRateLimiter(default_rpm=5)
        for _ in range(5):
            limiter.check("1.2.3.4")
        allowed, headers = limiter.check("1.2.3.4")
        assert not allowed
        assert "Retry-After" in headers

    def test_separate_ip_buckets(self):
        from rate_limiter import IPRateLimiter
        limiter = IPRateLimiter(default_rpm=3)
        # Exhaust IP 1
        for _ in range(3):
            limiter.check("1.1.1.1")
        allowed1, _ = limiter.check("1.1.1.1")
        assert not allowed1
        # IP 2 should still work
        allowed2, _ = limiter.check("2.2.2.2")
        assert allowed2

    def test_custom_rpm_override(self):
        from rate_limiter import IPRateLimiter
        limiter = IPRateLimiter(default_rpm=100)
        # Override with small limit
        for _ in range(3):
            limiter.check("1.2.3.4", rpm=3)
        allowed, _ = limiter.check("1.2.3.4", rpm=3)
        assert not allowed

    def test_eviction_when_full(self):
        from rate_limiter import IPRateLimiter
        limiter = IPRateLimiter(default_rpm=10)
        limiter._max_ips = 3
        for i in range(5):
            limiter.check(f"10.0.0.{i}")
        assert len(limiter._buckets) <= 3

    def test_ip_rate_limits_config(self):
        from rate_limiter import IP_RATE_LIMITS
        assert "/health" in IP_RATE_LIMITS
        assert "/billing/plans" in IP_RATE_LIMITS
        assert "/billing/onboarding/free" in IP_RATE_LIMITS


# --- JSON Logging Tests ---


class TestStructuredLogging:
    """Test that JSON formatter is configured correctly."""

    def test_json_formatter_available(self):
        from pythonjsonlogger.json import JsonFormatter
        fmt = JsonFormatter(fmt="%(asctime)s %(levelname)s %(name)s %(message)s")
        assert fmt is not None

    def test_json_formatter_output(self):
        import json
        from pythonjsonlogger.json import JsonFormatter
        import io

        handler = logging.StreamHandler(io.StringIO())
        handler.setFormatter(JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        ))
        test_logger = logging.getLogger("test_json_output")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.WARNING)
        test_logger.warning("test message here")

        output = handler.stream.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["level"] == "WARNING"
        assert parsed["message"] == "test message here"
        assert "timestamp" in parsed

    def test_extra_fields_in_json(self):
        import json
        from pythonjsonlogger.json import JsonFormatter
        import io

        handler = logging.StreamHandler(io.StringIO())
        handler.setFormatter(JsonFormatter(fmt="%(levelname)s %(message)s"))
        test_logger = logging.getLogger("test_extra_fields")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.WARNING)
        test_logger.warning("event", extra={"request_id": "abc123", "tenant_id": "t1"})

        output = handler.stream.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["request_id"] == "abc123"
        assert parsed["tenant_id"] == "t1"


# --- Prometheus Metrics Tests ---


class TestPrometheusMetrics:
    """Test prometheus-fastapi-instrumentator integration."""

    def test_instrumentator_import(self):
        from prometheus_fastapi_instrumentator import Instrumentator
        inst = Instrumentator(should_ignore_untemplated=True)
        assert inst is not None

    def test_metrics_endpoint_excluded_paths(self):
        """Verify /health and /metrics are excluded from instrumentation."""
        from prometheus_fastapi_instrumentator import Instrumentator
        inst = Instrumentator(
            excluded_handlers=["/health", "/docs", "/openapi.json", "/metrics"],
        )
        # excluded_handlers are compiled to regex patterns
        patterns = [p.pattern for p in inst.excluded_handlers]
        assert "/metrics" in patterns
        assert "/health" in patterns


# --- Helpers ---

async def _mock_receive():
    return {"type": "http.request", "body": b""}

async def _mock_send(message):
    pass
