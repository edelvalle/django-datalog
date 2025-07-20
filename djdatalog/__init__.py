# Package for Datalog-like fact & inference engine

__version__ = "0.1.0"

default_app_config = 'djdatalog.apps.DjdatalogConfig'

# Note: Core functionality (Fact, Var, query, etc.) is available in djdatalog.models
# Import them directly from there after Django is configured:
#   from djdatalog.models import Fact, Var, query, store_facts, retract_facts
