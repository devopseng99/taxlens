"""Tests for the metering logger — buffer, flush, event types."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))


# --- MeteringLogger tests ---

class TestMeteringLogger:
    """Test the async buffered MeteringLogger."""

    def setup_method(self):
        """Create a fresh logger for each test."""
        with patch("db.postgrest_client.DB_ENABLED", True):
            from metering import MeteringLogger
            self.logger = MeteringLogger(flush_size=3, flush_interval=60.0)

    @pytest.mark.asyncio
    async def test_log_buffers_events(self):
        """Events are buffered, not immediately flushed."""
        with patch("metering.DB_ENABLED", True):
            self.logger._buffer = []
            await self.logger.log("tenant1", "api_call", "/health")
            assert len(self.logger._buffer) == 1
            assert self.logger._buffer[0]["tenant_id"] == "tenant1"
            assert self.logger._buffer[0]["event_type"] == "api_call"

    @pytest.mark.asyncio
    async def test_flush_on_size_limit(self):
        """Buffer flushes when reaching flush_size."""
        with patch("metering.DB_ENABLED", True), \
             patch.object(self.logger, "_flush_unlocked", new_callable=AsyncMock) as mock_flush:
            # Log flush_size events
            for i in range(3):
                await self.logger.log(f"tenant{i}", "api_call", f"/test/{i}")
            # flush_unlocked should have been called once when buffer hit 3
            mock_flush.assert_called()

    @pytest.mark.asyncio
    async def test_log_disabled_when_no_db(self):
        """Events are dropped when DB_ENABLED is False."""
        with patch("metering.DB_ENABLED", False):
            self.logger._buffer = []
            await self.logger.log("tenant1", "api_call", "/health")
            assert len(self.logger._buffer) == 0

    @pytest.mark.asyncio
    async def test_event_has_required_fields(self):
        """Buffered events have all required fields."""
        with patch("metering.DB_ENABLED", True):
            self.logger._buffer = []
            await self.logger.log("t1", "tax_computation", "/tax-draft",
                                  metadata={"filing_status": "single"})
            event = self.logger._buffer[0]
            assert "id" in event
            assert event["tenant_id"] == "t1"
            assert event["event_type"] == "tax_computation"
            assert event["endpoint"] == "/tax-draft"
            assert event["metadata_json"] == json.dumps({"filing_status": "single"})
            assert isinstance(event["created_at"], str)

    @pytest.mark.asyncio
    async def test_multiple_event_types(self):
        """Different event types are all buffered correctly."""
        with patch("metering.DB_ENABLED", True):
            self.logger._buffer = []
            await self.logger.log("t1", "api_call", "/health")
            await self.logger.log("t1", "ocr_page", "/analyze/abc")
            assert len(self.logger._buffer) == 2
            assert self.logger._buffer[0]["event_type"] == "api_call"
            assert self.logger._buffer[1]["event_type"] == "ocr_page"

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Start creates flush task, stop cancels it."""
        with patch("metering.DB_ENABLED", True):
            await self.logger.start()
            assert self.logger._flush_task is not None
            assert not self.logger._flush_task.done()
            await self.logger.stop()
            assert self.logger._flush_task.done()


# --- Event type constants ---

class TestEventTypes:
    """Verify event type constants are defined."""

    def test_event_types_defined(self):
        from metering import (EVENT_API_CALL, EVENT_TAX_COMPUTATION,
                              EVENT_OCR_PAGE, EVENT_PLAID_SYNC,
                              EVENT_MCP_TOOL_CALL, EVENT_AGENT_MESSAGE)
        assert EVENT_API_CALL == "api_call"
        assert EVENT_TAX_COMPUTATION == "tax_computation"
        assert EVENT_OCR_PAGE == "ocr_page"
        assert EVENT_PLAID_SYNC == "plaid_sync"
        assert EVENT_MCP_TOOL_CALL == "mcp_tool_call"
        assert EVENT_AGENT_MESSAGE == "agent_message"
