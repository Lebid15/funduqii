"""Authentication URLs (mounted at /api/auth/)."""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import ContextView, LogoutView, MeView, TokenObtainPairView

urlpatterns = [
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("me/", MeView.as_view(), name="auth_me"),
    path("context/", ContextView.as_view(), name="auth_context"),
]
