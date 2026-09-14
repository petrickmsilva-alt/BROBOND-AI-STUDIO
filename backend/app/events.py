"""In-process WebSocket event hub for queue updates."""
import asyncio
import json
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class EventHub:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()

    async def connect(self, job_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.connections[str(job_id)].add(websocket)

    async def disconnect(self, job_id: UUID, websocket: WebSocket) -> None:
        async with self.lock:
            self.connections[str(job_id)].discard(websocket)

    async def publish(self, job_id: UUID, payload: dict) -> None:
        async with self.lock:
            clients = list(self.connections.get(str(job_id), set()))
        for client in clients:
            try:
                await client.send_text(json.dumps(payload))
            except Exception:
                await self.disconnect(job_id, client)


hub = EventHub()
