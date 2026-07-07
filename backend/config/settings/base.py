"""
Base settings shared by every environment for the Funduqii backend.

Environment-specific overrides live in ``development.py`` and ``production.py``.
Anything sensitive or environment-dependent is read from the environment via
``django-environ``; no real secrets are stored in this file.
"""
from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers

# backend/  (base.py -> settings -> config -> backend)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

# Load backend/.env if present (never committed). See backend/.env.example.
environ.Env.read_env(BASE_DIR / ".env")

# --- Core -------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# --- Applications -----------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.tenancy",
    "apps.rbac",
    "apps.realtime",
    "apps.integrations",
    "apps.subscriptions",
    "apps.platform",
    "apps.hotels",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Custom user ------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# --- Database ---------------------------------------------------------------
# PostgreSQL is the canonical database (see docker-compose.yml and
# .env.example). The local SQLite default keeps first-run and the test suite
# working without a running Postgres; it is NOT the production database.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    ),
}

# --- Password validation ----------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalization ---------------------------------------------------
# The product supports Arabic, English and Turkish at the application layer
# (from Phase 2). English is the backend's default locale.
LANGUAGE_CODE = env("LANGUAGE_CODE", default="en-us")
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# --- Static & media ---------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CORS -------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
# Allow the tenant-context header used to scope requests to a hotel.
CORS_ALLOW_HEADERS = (*default_headers, "x-hotel-id")

# --- Django REST Framework --------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Secure by default: every view requires an authenticated, active user
    # unless it explicitly opts out (e.g. health check, token endpoints).
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.rbac.permissions.IsAuthenticatedAndActive",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # Every list endpoint is paginated by default (see apps/common/pagination.py).
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    # Unified, translatable error envelope: {"code", "message", "details"?}.
    "EXCEPTION_HANDLER": "apps.common.exceptions.funduqii_exception_handler",
}

# --- JWT (SimpleJWT) --------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ===========================================================================
# Scalability / performance / realtime foundation (Phase 1.5)
#
# Redis powers caching, the Celery broker/result backend, and the Channels
# layer. When Redis is not configured (development/tests), safe in-process
# fallbacks keep everything working; REAL performance and realtime require
# Redis. See docs/PERFORMANCE_AND_REALTIME_STRATEGY.md.
# ===========================================================================
REDIS_URL = env("REDIS_URL", default="")

# --- Cache ------------------------------------------------------------------
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    # In-process fallback: works without Redis, but is per-process and NOT for
    # production. Do not cache sensitive data.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "funduqii-locmem",
        }
    }

# --- Celery (background tasks foundation) -----------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

# --- Channels (realtime foundation) -----------------------------------------
# Realtime uses Django Channels + a Redis channel layer. Without Redis, an
# in-memory layer is used (single-process; dev/tests only).
CHANNEL_LAYER_REDIS_URL = env("CHANNEL_LAYER_REDIS_URL", default="")
if CHANNEL_LAYER_REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [CHANNEL_LAYER_REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }

# ===========================================================================
# Maps, messaging & external integrations foundation (Phase 1.6)
#
# Foundation ONLY: every provider defaults to "disabled"/empty. No real keys,
# no external calls, no messages are sent. Real providers plug in later behind
# the adapter/provider interfaces in apps/integrations. See:
#   docs/MAPS_AND_LOCATION_STRATEGY.md
#   docs/WHATSAPP_AND_MESSAGING_STRATEGY.md
#   docs/EXTERNAL_INTEGRATIONS_ARCHITECTURE.md
# Do NOT put real secrets here or in Git — only in server env files.
# ===========================================================================

# Maps (provider-neutral; keys stay in the backend env, restricted by domain).
MAP_PROVIDER = env("MAP_PROVIDER", default="disabled")
GOOGLE_MAPS_API_KEY = env("GOOGLE_MAPS_API_KEY", default="")
GOOGLE_MAPS_BROWSER_KEY = env("GOOGLE_MAPS_BROWSER_KEY", default="")
MAPBOX_ACCESS_TOKEN = env("MAPBOX_ACCESS_TOKEN", default="")

# Messaging / WhatsApp (official WhatsApp Business Platform / Cloud API only).
MESSAGING_PROVIDER = env("MESSAGING_PROVIDER", default="disabled")
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", default="disabled")
WHATSAPP_API_BASE_URL = env("WHATSAPP_API_BASE_URL", default="")
WHATSAPP_BUSINESS_ACCOUNT_ID = env("WHATSAPP_BUSINESS_ACCOUNT_ID", default="")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = env("WHATSAPP_WEBHOOK_VERIFY_TOKEN", default="")

# Contact / locale defaults (non-secret).
DEFAULT_COUNTRY_CODE = env("DEFAULT_COUNTRY_CODE", default="")
PLATFORM_SUPPORT_WHATSAPP = env("PLATFORM_SUPPORT_WHATSAPP", default="")
PLATFORM_SUPPORT_PHONE = env("PLATFORM_SUPPORT_PHONE", default="")

# ===========================================================================
# Hotel media upload limits (Phase 4)
#
# Raster images only (jpg/jpeg/png/webp) — SVG is rejected for security. Limits
# are overridable via env. See docs/HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md.
# ===========================================================================
HOTEL_MEDIA_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
HOTEL_MEDIA_LOGO_MAX_BYTES = env.int("HOTEL_MEDIA_LOGO_MAX_BYTES", default=1 * 1024 * 1024)
HOTEL_MEDIA_COVER_MAX_BYTES = env.int("HOTEL_MEDIA_COVER_MAX_BYTES", default=5 * 1024 * 1024)
HOTEL_MEDIA_GALLERY_MAX_BYTES = env.int(
    "HOTEL_MEDIA_GALLERY_MAX_BYTES", default=5 * 1024 * 1024
)
HOTEL_MEDIA_GALLERY_MAX_COUNT = env.int("HOTEL_MEDIA_GALLERY_MAX_COUNT", default=10)
