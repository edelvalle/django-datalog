from django.apps import AppConfig


class DjdatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "djdatalog"

    def ready(self):
        pass
