from django.apps import AppConfig
from django.core import checks


class ContextConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "context"

    def ready(self):
        from context.checks import core_database_schema

        checks.register(core_database_schema)
