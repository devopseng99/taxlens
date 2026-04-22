"""Usage metering — async buffered event logger with periodic flush to Dolt."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from db.connection import DOLT_ENABLED, get_conn

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

    Buffers events in memory and flushes to Dolt every `flush_interval` seconds
    or when the buffer reaches `flush_size` events. Call `start()` in app lifespan
    and `stop()` on shutdown.
    """

    def __init__(self, flush_size: int = 100, flush_interval: float = 30.0):
        self._buffer: list[dict] = []
        self._flush_size = flush_size
        self._flush_interval = flush_interval
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the periodic flush background task."""
        if not DOLT_ENABLED:
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
        if not DOLT_ENABLED:
            return
        event = {
            "id": uuid.uuid4().hex,
            "tenant_id": tenant_id,
            "event_type": event_type,
            "endpoint": endpoint,
            "metadata_json": metadata,
            "created_at": datetime.now(timezone.utc),
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
        """Flush buffer to Dolt. Caller must hold self._lock."""
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()

        try:
            import json
            import aiomysql
            async with get_conn() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    for event in batch:
                        await cur.execute(
                            "INSERT INTO usage_events "
                            "(id, tenant_id, event_type, endpoint, metadata_json, created_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (
                                event["id"],
                                event["tenant_id"],
                                event["event_type"],
                                event["endpoint"],
                                json.dumps(event["metadata_json"]) if event["metadata_json"] else None,
                                event["created_at"],
                            ),
                        )
            logger.debug("Flushed %d usage events to Dolt", len(batch))
        except Exception as e:
            logger.warning("Failed to flush %d usage events: %s", len(batch), e)
            # Re-buffer failed events (at front, capped to prevent unbounded growth)
            async with self._lock:
                self._buffer = batch[:500] + self._buffer[:500]


# Singleton instance
metering = MeteringLogger()
