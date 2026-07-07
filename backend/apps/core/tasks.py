"""Foundation Celery tasks (Phase 1.5).

Only a trivial health task — proves the worker can load and run a task. No
operational tasks exist yet.
"""
from celery import shared_task


@shared_task(name="core.ping")
def ping() -> str:
    """Return a constant so we can verify the Celery pipeline end to end."""
    return "pong"
