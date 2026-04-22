"""Usage metering — async buffered event logger with periodic flush to PostgreSQL via PostgREST."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from db.postgrest_client import postgrest, DB_ENABLED

logger = logging.getLogger(__name__)

# Event types
EVENT_API_CALL = "api_call"
EVENT_TAX_COMPUTATION = "tax_computation"
EVENT_OCR_PAGE = "ocr_page"
EVENT_PLAID_SYNC = "plaid_sync"
EVENT_MCP_TOOL_CALL = "mcp_tool_call"
EVENT_AGENT_MESSAGE = "agent_message"


class MeteringLogger:
    """Async buffered usage event logger.

    Buffers events in memory and flushes to PostgreSQL (via PostgREST) every
    `flush_interval` seconds or when the buffer reaches `flush_size` events.
    Call `start()` in app lifespan and `stop()` on shutdown.
    """

    def __init__(self, flush_size: int = 100, flush_interval: float = 30.0):
        self._buffer: list[dict] = []
        self._flush_size = flush_size
        self._flush_interval = flush_interval
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the periodic flush background task."""
        if not DB_ENABLED:
            return
        self._flush_task = asyncio.create_task(self._periodic_flush())
        logger.info("MeteringLogger started (flush_size=%d, interval=%.0fs)",
                     self._flush_size, self._flush_interval)

    async def stop(self):
        """Flush remaining events and cancel the background task."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush()
        logger.info("MeteringLogger stopped")

    async def log(self, tenant_id: str, event_type: str,
                  endpoint: str = "", metadata: dict | None = None):
        """Buffer a usage event. Non-blocking."""
        if not DB_ENABLED:
            return
        event = {
            "id": uuid.uuid4().hex,
            "tenant_id": tenant_id,
            "event_type": event_type,
            "endpoint": endpoint,
            "metadata_json": json.dumps(metadata) if metadata else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        async with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self._flush_size:
                await self._flush_unlocked()

    async def _periodic_flush(self):
        """Background loop: flush buffer every `flush_interval` seconds."""
        while True:
            await asyncio.sleep(self._flush_interval)
            async with self._lock:
                await self._flush_unlocked()

    async def _flush(self):
        """Thread-safe flush."""
        async with self._lock:
            await self._flush_unlocked()

    async def _flush_unlocked(self):
        """Flush buffer to PostgreSQL via PostgREST. Caller must hold self._lock."""
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()

        try:
            admin_token = postgrest.mint_jwt("__admin__", role="app_admin")
            await postgrest.create_many("usage_events", batch, token=admin_token)
            logger.debug("Flushed %d usage events to PostgreSQL", len(batch))
        except Exception as e:
            logger.warning("Failed to flush %d usage events: %s", len(batch), e)
            # Re-buffer failed events (capped to prevent unbounded growth)
            async with self._lock:
                self._buffer = batch[:500] + self._buffer[:500]


# Singleton instance
metering = MeteringLogger()
