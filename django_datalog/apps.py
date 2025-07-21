from django.apps import AppConfig


class DjangoDatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_datalog"

    def ready(self):
        pass
