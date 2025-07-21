from django.apps import AppConfig


class Testdjango_datalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "testdjdatalog"

    def ready(self):
        """Load datalog rules when Django starts."""
        # Import rules to register them with the datalog engine
        try:
            from . import rules  # noqa: F401
        except ImportError:
            # Rules module not found, skip loading
            pass
