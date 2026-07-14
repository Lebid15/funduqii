from django.apps import AppConfig


class ReservationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reservations"
    verbose_name = "Reservations & Availability"

    def ready(self) -> None:
        # DI-F3: register the post_delete receivers that clean up private
        # document files from storage on cascade/manual deletes. Imported for
        # the side effect of connecting the ``@receiver``-decorated handlers.
        from . import signals  # noqa: F401
