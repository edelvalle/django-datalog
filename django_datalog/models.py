"""
Datalog system for Django - main module with public API.

This module provides the public interface for django-datalog, importing from
specialized modules for facts, queries, and rules.
"""

# Public API imports
from django_datalog.facts import Fact, FactConjunction, retract_facts, store_facts
from django_datalog.optimizer import (
    get_optimizer_timing_stats,
    optimize_query,
    record_fact_timing,
    reset_optimizer_cache,
    time_fact_execution,
)
from django_datalog.query import _fact_to_django_query, _prefix_q_object, query
from django_datalog.rules import Rule, get_rules, rule, rule_context
from django_datalog.variables import Var

# django_datalog is a library package - storage models should be defined by consuming applications

# Re-export for backward compatibility and public API
__all__ = [
    # Core classes
    "Fact",
    "FactConjunction",
    "Var",
    "Rule",
    # Core functions
    "query",
    "store_facts",
    "retract_facts",
    "rule",
    "rule_context",
    "get_rules",
    # Optimizer functions
    "optimize_query",
    "reset_optimizer_cache",
    "record_fact_timing",
    "get_optimizer_timing_stats",
    "time_fact_execution",
    # Internal functions (exposed for testing)
    "_prefix_q_object",
    "_fact_to_django_query",
]
