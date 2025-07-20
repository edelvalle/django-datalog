"""
Query system for djdatalog - handles querying facts with inference and optimization.
"""

from collections.abc import Iterator
from typing import Any
from dataclasses import dataclass

from django.db.models import Q

from djdatalog.facts import Fact


@dataclass(slots=True)
class Var:
    """Variable placeholder for datalog queries."""
    
    name: str
    where: Any = None  # Q object for additional constraints
    
    def __repr__(self):
        if self.where is not None:
            return f"Var({self.name!r}, where={self.where!r})"
        return f"Var({self.name!r})"


def query(*fact_patterns: Fact, hydrate: bool = True) -> Iterator[dict[str, Any]]:
    """
    Query facts from the database and apply inference rules.
    
    Args:
        *fact_patterns: One or more fact patterns to match as a conjunction
        hydrate: If True (default), returns full model instances. If False, returns PKs only.
    
    Yields:
        Dictionary mapping variable names to their values (models or PKs based on hydrate)
    """
    # Get the conjunction results
    pk_results = _satisfy_conjunction(list(fact_patterns), {})
    
    if hydrate:
        # Collect all results first to batch hydration
        pk_results_list = list(pk_results)
        # Hydrate PKs to model instances
        yield from _hydrate_results(pk_results_list, list(fact_patterns))
    else:
        # Return PKs directly without hydration
        yield from pk_results


def _satisfy_conjunction(conditions, bindings) -> Iterator[dict[str, Any]]:
    """Satisfy a conjunction of conditions with the given variable bindings."""
    if not conditions:
        yield bindings
        return
    
    # Take the first condition
    condition = conditions[0]
    remaining = conditions[1:]
    
    # Generate all possible solutions for this condition
    for result in _query_single_fact(condition):
        # Try to unify with existing bindings
        new_bindings = _unify_bindings(bindings, result)
        if new_bindings is not None:
            # Recursively solve remaining conditions
            yield from _satisfy_conjunction(remaining, new_bindings)


def _query_single_fact(fact_pattern: Fact) -> Iterator[dict[str, Any]]:
    """Query a single fact pattern from the database."""
    # Get the Django model for this fact type
    fact_class = type(fact_pattern)
    django_model = fact_class._django_model
    
    # Convert fact pattern to Django query
    query_params, q_objects = _fact_to_django_query(fact_pattern)
    
    # Build the queryset with both filter params and Q objects
    queryset = django_model.objects.filter(**query_params)
    for q_obj in q_objects:
        queryset = queryset.filter(q_obj)
    
    # Query the database with values() to get PKs only
    for values_dict in queryset.values("subject", "object"):
        substitution = _django_result_to_substitution(fact_pattern, values_dict)
        yield substitution


def _fact_to_django_query(fact: Fact) -> tuple[dict[str, Any], list[Any]]:
    """
    Convert a fact to Django query parameters and Q objects.
    
    Returns:
        tuple: (query_params, q_objects) where q_objects are constraints for Vars
    """
    query_params = {}
    q_objects = []
    
    if not isinstance(fact.subject, Var):
        query_params["subject"] = fact.subject
    elif fact.subject.where is not None:
        # Add Q object constraint with subject__ prefix
        prefixed_q = _prefix_q_object(fact.subject.where, "subject")
        q_objects.append(prefixed_q)
    
    if not isinstance(fact.object, Var):
        query_params["object"] = fact.object
    elif fact.object.where is not None:
        # Add Q object constraint with object__ prefix  
        prefixed_q = _prefix_q_object(fact.object.where, "object")
        q_objects.append(prefixed_q)
    
    return query_params, q_objects


def _prefix_q_object(q_obj, prefix: str):
    """Prefix all field lookups in a Q object with the given prefix."""
    if hasattr(q_obj, 'children'):
        # Q object with children (AND/OR operations)
        new_q = Q()
        new_q.connector = q_obj.connector
        new_q.negated = q_obj.negated
        
        for child in q_obj.children:
            if isinstance(child, tuple):
                # This is a field lookup: (field_name, value)
                field_name, value = child
                new_field_name = f"{prefix}__{field_name}"
                new_q.children.append((new_field_name, value))
            else:
                # This is another Q object - recurse
                new_q.children.append(_prefix_q_object(child, prefix))
        return new_q
    else:
        # Simple Q object - create a new one with prefixed fields
        new_q = Q()
        new_q.connector = q_obj.connector  
        new_q.negated = q_obj.negated
        for child in q_obj.children:
            if isinstance(child, tuple):
                field_name, value = child
                new_field_name = f"{prefix}__{field_name}"
                new_q.children.append((new_field_name, value))
        return new_q


def _django_result_to_substitution(fact: Fact, values_dict: dict) -> dict[str, Any]:
    """Convert Django query result to variable substitution."""
    substitution = {}
    if isinstance(fact.subject, Var):
        substitution[fact.subject.name] = values_dict["subject"]
    if isinstance(fact.object, Var):
        substitution[fact.object.name] = values_dict["object"]
    return substitution


def _unify_bindings(existing: dict, new: dict) -> dict[str, Any] | None:
    """Try to unify two sets of variable bindings."""
    result = existing.copy()
    for var, value in new.items():
        if var in result:
            if result[var] != value:
                return None  # Conflict
        else:
            result[var] = value
    return result


def _hydrate_results(pk_results: list[dict], fact_patterns: list[Fact]) -> Iterator[dict[str, Any]]:
    """Hydrate PK results to full model instances."""
    # For now, just return the PK results as-is
    # In a full implementation, this would batch-load the models
    for result in pk_results:
        # TODO: Implement actual hydration
        yield result