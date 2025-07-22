# Package for Datalog-like fact & inference engine

__version__ = "0.3.0"

default_app_config = "django_datalog.apps.DjangoDatalogConfig"

# Note: Core functionality (Fact, Var, query, etc.) is available in django_datalog.models
# Import them directly from there after Django is configured:
#   from django_datalog.models import Fact, Var, query, store_facts, retract_facts
