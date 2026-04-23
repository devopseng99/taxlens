"""Request ID correlation middleware.

Generates a UUID4 request ID for every HTTP request (or accepts an incoming
X-Request-ID header from the client/load balancer). Injects it into:

  1. request.state.request_id — available to route handlers and other middleware
  2. X-Request-ID response header — returned to the caller for log correlation

Pure ASGI middleware (not BaseHTTPMiddleware) to avoid deadlocks with async
httpx calls in the middleware chain.
"""

import uuid
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestIDMiddleware:
    """Pure ASGI middleware — assigns a unique request ID to every HTTP request."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        # Accept client-provided ID or generate a new one
        request_id = request.headers.get("x-request-id", "") or uuid.uuid4().hex
        request.state.request_id = request_id

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)
