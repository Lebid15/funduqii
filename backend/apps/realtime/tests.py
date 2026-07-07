"""WebSocket foundation test (Phase 1.5).

Exercises the /ws/health/ consumer through the ASGI application using an
in-memory channel layer — no running ASGI server or Redis required.
"""
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from config.asgi import application


class WebSocketHealthTests(TransactionTestCase):
    async def test_ws_health_handshake_and_message(self):
        communicator = WebsocketCommunicator(application, "/ws/health/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        message = await communicator.receive_json_from()
        self.assertEqual(message, {"status": "ok", "service": "funduqii-ws"})

        await communicator.send_json_to({"ping": 1})
        echo = await communicator.receive_json_from()
        self.assertEqual(echo, {"echo": {"ping": 1}})

        await communicator.disconnect()
