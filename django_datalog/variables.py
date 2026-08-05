"""
Variable definitions for django_datalog.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Var[T]:
    """Typed variable placeholder for datalog queries.

    The type parameter records what kind of value the variable stands for, so
    a variable declared as ``Var[Employee]("emp")`` only fits into fact slots
    that expect an ``Employee``. Reuse the same typed variable across the
    conditions of a rule/query to keep the binding type-consistent::

        emp = Var[Employee]("emp")
        company = Var[Company]("company")
        query(WorksFor(emp, company))

    Bare ``Var("emp")`` remains valid (inferred from the slot it is passed to),
    so the type parameter is opt-in and fully backward compatible.
    """

    name: str
    where: Any = None  # Q object for additional constraints

    def __repr__(self):
        if self.where is not None:
            return f"Var({self.name!r}, where={self.where!r})"
        return f"Var({self.name!r})"


# A "term" in a fact slot is either a concrete value or a variable standing for
# one. Use it in fact definitions: ``subject: Term[Employee]`` is exactly
# ``Employee | Var[Employee]`` but keeps the model name from repeating.
type Term[X] = X | Var[X]


def has_variable_references(q_obj) -> bool:
    """Check if a Q object contains references to Var instances."""
    if not hasattr(q_obj, 'children'):
        return False
        
    for child in q_obj.children:
        if isinstance(child, tuple):
            # This is a field lookup: (field_name, value)
            field_name, value = child
            if _value_has_variables(value):
                return True
        else:
            # This is another Q object - recurse
            if has_variable_references(child):
                return True
    return False


def _value_has_variables(value) -> bool:
    """Check if a value contains Var instances, handling nested structures."""
    if isinstance(value, Var):
        return True
    elif isinstance(value, (list, tuple)):
        return any(_value_has_variables(item) for item in value)
    else:
        return False


def satisfies_constraint(value, q_obj) -> bool:
    """Check a concrete value against a literal Q constraint (no Var references).

    For a Django model instance, filter its own model by the Q and test that the
    instance still matches (by pk). A value that is not a saved model instance
    cannot be evaluated against a Q, so it is treated as passing — the only gate
    for such a position is the load-time filter.
    """
    pk = getattr(value, "pk", None)
    manager = getattr(type(value), "_default_manager", None)
    if pk is None or manager is None:
        return True
    try:
        return manager.filter(q_obj).filter(pk=pk).exists()
    except Exception:
        # A malformed or inapplicable constraint should not silently drop the row.
        return True


def extract_variable_references(q_obj) -> dict[str, list[str]]:
    """
    Extract variable references from a Q object.
    
    Returns:
        dict mapping variable names to list of field paths where they're referenced
    """
    references = {}
    
    if not hasattr(q_obj, 'children'):
        return references
        
    for child in q_obj.children:
        if isinstance(child, tuple):
            # This is a field lookup: (field_name, value)
            field_name, value = child
            var_refs = _extract_variables_from_value(value)
            for var_name in var_refs:
                if var_name not in references:
                    references[var_name] = []
                references[var_name].append(field_name)
        else:
            # This is another Q object - recurse and merge
            child_refs = extract_variable_references(child)
            for var_name, field_paths in child_refs.items():
                if var_name not in references:
                    references[var_name] = []
                references[var_name].extend(field_paths)
                
    return references


def _extract_variables_from_value(value) -> list[str]:
    """Extract variable names from a value, handling nested structures."""
    if isinstance(value, Var):
        return [value.name]
    elif isinstance(value, (list, tuple)):
        var_names = []
        for item in value:
            var_names.extend(_extract_variables_from_value(item))
        return var_names
    else:
        return []


def substitute_variables_in_q(q_obj, substitutions: dict[str, Any]):
    """
    Replace Var instances in a Q object with actual values from substitutions.
    
    Args:
        q_obj: Q object potentially containing Var references
        substitutions: dict mapping variable names to actual values
        
    Returns:
        New Q object with variables substituted
    """
    if not hasattr(q_obj, 'children'):
        return q_obj
        
    from django.db.models import Q
    
    new_q = Q()
    new_q.connector = q_obj.connector
    new_q.negated = q_obj.negated
    
    for child in q_obj.children:
        if isinstance(child, tuple):
            # This is a field lookup: (field_name, value)
            field_name, value = child
            substituted_value = _substitute_value_recursively(value, substitutions)
            new_q.children.append((field_name, substituted_value))
        else:
            # This is another Q object - recurse
            substituted_child = substitute_variables_in_q(child, substitutions)
            new_q.children.append(substituted_child)
            
    return new_q


def _substitute_value_recursively(value, substitutions: dict[str, Any]):
    """
    Recursively substitute Var instances in a value, handling nested structures like lists.
    
    Args:
        value: The value to substitute (could be Var, list, or any other type)
        substitutions: dict mapping variable names to actual values
        
    Returns:
        Value with Var instances substituted
    """
    if isinstance(value, Var):
        # Direct variable - substitute if available
        if value.name in substitutions:
            return substitutions[value.name]
        else:
            # Variable not yet bound - keep as is
            return value
    elif isinstance(value, list):
        # List - recursively substitute each element
        return [_substitute_value_recursively(item, substitutions) for item in value]
    elif isinstance(value, tuple):
        # Tuple - recursively substitute each element
        return tuple(_substitute_value_recursively(item, substitutions) for item in value)
    else:
        # Regular value - keep as is
        return value
