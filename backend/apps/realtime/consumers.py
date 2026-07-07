"""WebSocket consumers (realtime foundation, Phase 1.5).

Only a health consumer exists. It proves the WebSocket/ASGI/Channels pipeline
works. It sends NO operational events (no reservation/room/notification updates)
— those belong to later phases.
"""
from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class HealthConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        await self.accept()
        await self.send_json({"status": "ok", "service": "funduqii-ws"})

    async def receive_json(self, content, **kwargs) -> None:
        # Echo back only — no business logic. Confirms the socket is alive.
        await self.send_json({"echo": content})

    async def disconnect(self, code) -> None:
        return None
