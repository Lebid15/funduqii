"""ASGI config for the Funduqii backend.

Routes HTTP to Django and WebSocket to Channels. This is the realtime
foundation; only a health WebSocket exists (no operational events).
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

from django.core.asgi import get_asgi_application  # noqa: E402

# Initialize Django (populate the app registry) before importing anything that
# may touch models or settings-dependent code.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
