from django.apps import AppConfig


class PendingActionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pending_actions'

    def ready(self):
        from . import handlers  # noqa: F401
