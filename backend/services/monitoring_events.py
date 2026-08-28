"""Realtime Monitoring Event Broadcaster (SSE) for Admin Monitoring Dashboard.

Allows backend services (agent_v2_routes, safety, feedback, judge) to broadcast
events whenever new agent runs/traces occur, and streams them to connected admin
clients over Server-Sent Events (SSE).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, AsyncGenerator

_logger = logging.getLogger(__name__)


class MonitoringEventBroadcaster:
    def __init__(self, max_queue_size: int = 100) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._max_queue_size = max_queue_size

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.add(queue)
        _logger.debug("New SSE subscriber added. Total subscribers: %d", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)
        _logger.debug("SSE subscriber removed. Total subscribers: %d", len(self._subscribers))

    def broadcast(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        if not self._subscribers:
            return

        payload = {
            "event": event_type,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                _logger.warning("Subscriber queue full, dropping event %s", event_type)
            except Exception as e:  # noqa: BLE001
                _logger.debug("Failed to deliver event to subscriber: %s", e)

    async def stream_events(self, queue: asyncio.Queue[dict[str, Any]]) -> AsyncGenerator[str, None]:
        try:
            # Yield initial connected event
            initial_event = {
                "event": "connected",
                "data": {"status": "ok"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"event: {initial_event['event']}\ndata: {json.dumps(initial_event)}\n\n"

            while True:
                try:
                    # Wait for next event or 15s timeout for keep-alive ping
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: {item['event']}\ndata: {json.dumps(item)}\n\n"
                except asyncio.TimeoutError:
                    # Send keep-alive comment / ping
                    ping = {
                        "event": "ping",
                        "data": {},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield f"event: ping\ndata: {json.dumps(ping)}\n\n"
        finally:
            self.unsubscribe(queue)


# Global singleton instance
monitoring_broadcaster = MonitoringEventBroadcaster()


def broadcast_monitoring_event(event_type: str, data: dict[str, Any] | None = None) -> None:
    """Convenience helper to broadcast an event to all connected admin dashboards."""
    monitoring_broadcaster.broadcast(event_type, data)
