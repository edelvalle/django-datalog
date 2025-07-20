# Package for Datalog-like fact & inference engine

__version__ = "0.1.0"

default_app_config = 'djdatalog.apps.DjdatalogConfig'

# Public API - imported lazily to avoid Django startup issues
def __getattr__(name):
    """Lazy import of public API to avoid Django circular imports"""
    if name in ('Fact', 'Var', 'query', 'store_facts', 'retract_facts', 
                'rule', 'Rule', 'get_rules', 'clear_rules'):
        from djdatalog.models import (
            Fact, Var, query, store_facts, retract_facts,
            rule, Rule, get_rules, clear_rules
        )
        globals().update({
            'Fact': Fact, 'Var': Var, 'query': query,
            'store_facts': store_facts, 'retract_facts': retract_facts,
            'rule': rule, 'Rule': Rule, 'get_rules': get_rules, 'clear_rules': clear_rules
        })
        return globals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    'Fact', 'Var', 'query', 'store_facts', 'retract_facts',
    'rule', 'Rule', 'get_rules', 'clear_rules'
]
