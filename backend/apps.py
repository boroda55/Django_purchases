from django.apps import AppConfig


class BackendConfig(AppConfig):
    """App configuration for the backend Django app.

    Sets default primary key field type and app label used by Django.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backend'

    def ready(self):
        import backend.signals
