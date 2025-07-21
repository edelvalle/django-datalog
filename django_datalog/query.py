"""
Query system for djdatalog - handles querying facts with inference and optimization.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from django.db.models import Q

from django_datalog.facts import Fact


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
    # Get all available facts (both stored and inferred)
    all_facts = _get_all_facts_with_inference()

    # Get the conjunction results using both stored and inferred facts
    pk_results = _satisfy_conjunction_with_facts(list(fact_patterns), {}, all_facts)

    if hydrate:
        # Collect all results first to batch hydration
        pk_results_list = list(pk_results)
        # Hydrate PKs to model instances
        yield from _hydrate_results(pk_results_list, list(fact_patterns))
    else:
        # Return PKs directly without hydration
        yield from pk_results


def _get_all_facts_with_inference() -> list[Fact]:
    """Get all facts including both stored facts and inferred facts from rules."""
    from django_datalog.rules import apply_rules

    # Get all stored facts from the database
    stored_facts = _get_all_stored_facts()

    # Apply inference rules to derive new facts
    all_facts = apply_rules(stored_facts)

    return all_facts


def _get_all_stored_facts() -> list[Fact]:
    """Get all facts currently stored in the database."""
    from django_datalog.rules import get_rules

    stored_facts = []

    # Get all fact types used in rules to know what to load
    fact_types = set()
    for rule in get_rules():
        fact_types.add(type(rule.head))
        for condition in rule.body:
            fact_types.add(type(condition))

    # Load facts of all relevant types from the database
    for fact_type in fact_types:
        try:
            django_model = fact_type._django_model
            # Get subject and object type from fact type annotations
            subject_type, object_type = _get_fact_field_types(fact_type)

            # Load facts using select_related for efficient loading
            for row in django_model.objects.select_related("subject", "object").all():
                try:
                    # Access the related Django model instances directly
                    fact = fact_type(subject=row.subject, object=row.object)
                    stored_facts.append(fact)
                except Exception:
                    # Skip facts that can't be loaded
                    continue
        except Exception:
            # Skip fact types that can't be loaded
            continue

    return stored_facts


def _get_fact_field_types(fact_type):
    """Get the Django model types for subject and object fields of a fact type."""
    # Use the cached model types from the Fact class
    if hasattr(fact_type, "_model_types_cache"):
        cache = fact_type._model_types_cache
        return cache.get("subject"), cache.get("object")

    # Fallback: extract from type annotations
    from dataclasses import fields

    fact_fields = fields(fact_type)
    subject_field = next((f for f in fact_fields if f.name == "subject"), None)
    object_field = next((f for f in fact_fields if f.name == "object"), None)

    if not subject_field or not object_field:
        raise ValueError(f"Fact type {fact_type} missing subject or object field")

    # Extract Django model types from Union annotations (like Person | Var)
    subject_type = _extract_model_type_from_annotation(subject_field.type)
    object_type = _extract_model_type_from_annotation(object_field.type)

    return subject_type, object_type


def _extract_model_type_from_annotation(type_annotation):
    """Extract Django model type from type annotation like 'Person | Var'."""
    if hasattr(type_annotation, "__args__"):
        # Handle Union types (Person | Var)
        for arg_type in type_annotation.__args__:
            if hasattr(arg_type, "_meta") and hasattr(arg_type._meta, "app_label"):
                # This looks like a Django model
                return arg_type
    elif hasattr(type_annotation, "_meta") and hasattr(type_annotation._meta, "app_label"):
        # Direct Django model reference
        return type_annotation

    return None


def _satisfy_conjunction_with_facts(
    conditions, bindings, all_facts: list[Fact]
) -> Iterator[dict[str, Any]]:
    """Satisfy a conjunction of conditions using the combined set of stored and inferred facts."""
    if not conditions:
        yield bindings
        return

    # Take the first condition
    condition = conditions[0]
    remaining = conditions[1:]

    # Query against the complete set of facts (stored + inferred) to avoid duplication
    for result in _query_against_facts(condition, all_facts):
        new_bindings = _unify_bindings(bindings, result)
        if new_bindings is not None:
            yield from _satisfy_conjunction_with_facts(remaining, new_bindings, all_facts)


def _query_against_facts(pattern: Fact, facts: list[Fact]) -> Iterator[dict[str, Any]]:
    """Query a pattern against a set of in-memory facts."""
    pattern_type = type(pattern)

    for fact in facts:
        if type(fact) is pattern_type:
            # Try to unify the pattern with this fact
            substitution = _unify_fact_pattern(pattern, fact)
            if substitution is not None:
                yield substitution


def _unify_fact_pattern(pattern: Fact, concrete_fact: Fact) -> dict[str, Any] | None:
    """Unify a fact pattern (with variables) against a concrete fact."""
    substitution = {}

    # Check subject
    if isinstance(pattern.subject, Var):
        # Check if subject meets the variable's constraints
        if pattern.subject.where is not None:
            if not _check_q_constraint(concrete_fact.subject, pattern.subject.where):
                return None  # Subject doesn't meet constraints

        substitution[pattern.subject.name] = (
            concrete_fact.subject.pk
            if hasattr(concrete_fact.subject, "pk")
            else concrete_fact.subject
        )
    elif pattern.subject != concrete_fact.subject:
        return None  # Subjects don't match

    # Check object
    if isinstance(pattern.object, Var):
        # Check if object meets the variable's constraints
        if pattern.object.where is not None:
            if not _check_q_constraint(concrete_fact.object, pattern.object.where):
                return None  # Object doesn't meet constraints

        var_name = pattern.object.name
        obj_value = (
            concrete_fact.object.pk if hasattr(concrete_fact.object, "pk") else concrete_fact.object
        )
        # Check for conflicting bindings
        if var_name in substitution and substitution[var_name] != obj_value:
            return None
        substitution[var_name] = obj_value
    elif pattern.object != concrete_fact.object:
        return None  # Objects don't match

    return substitution


def _check_q_constraint(model_instance, q_constraint) -> bool:
    """Check if a model instance satisfies a Q constraint."""
    # Convert the Q constraint to a filter and check if the instance matches
    try:
        # Create a queryset for this model and apply the constraint
        queryset = model_instance.__class__.objects.filter(q_constraint)
        # Check if this specific instance matches the constraint
        return queryset.filter(pk=model_instance.pk).exists()
    except Exception:
        # If there's any error with the constraint check, assume it fails
        return False


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

    # Query the database with values() to get PKs
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
        # Use Django model instance directly for ForeignKey lookup
        query_params["subject"] = fact.subject
    elif fact.subject.where is not None:
        # Add Q object constraint with subject__ prefix
        prefixed_q = _prefix_q_object(fact.subject.where, "subject")
        q_objects.append(prefixed_q)

    if not isinstance(fact.object, Var):
        # Use Django model instance directly for ForeignKey lookup
        query_params["object"] = fact.object
    elif fact.object.where is not None:
        # Add Q object constraint with object__ prefix
        prefixed_q = _prefix_q_object(fact.object.where, "object")
        q_objects.append(prefixed_q)

    return query_params, q_objects


def _prefix_q_object(q_obj, prefix: str):
    """Prefix all field lookups in a Q object with the given prefix."""
    if hasattr(q_obj, "children"):
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
        # values_dict contains PKs from ForeignKey fields
        substitution[fact.subject.name] = values_dict["subject"]
    if isinstance(fact.object, Var):
        # values_dict contains PKs from ForeignKey fields
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
    if not pk_results:
        return

    # Collect all PKs that need hydration by variable name and model type
    var_to_model_type = {}
    pks_to_hydrate = {}

    # First pass: discover what models each variable represents
    for fact_pattern in fact_patterns:
        for field_name in ["subject", "object"]:
            field_val = getattr(fact_pattern, field_name)
            if isinstance(field_val, Var):
                var_name = field_val.name
                # Extract model type from fact pattern using the helper function
                model_type = _extract_model_type_from_annotation(
                    fact_pattern.__dataclass_fields__[field_name].type
                )
                if model_type and var_name not in var_to_model_type:
                    var_to_model_type[var_name] = model_type
                    pks_to_hydrate[var_name] = set()

    # Second pass: collect all PKs for each variable
    for result in pk_results:
        for var_name, pk in result.items():
            if var_name in pks_to_hydrate:
                pks_to_hydrate[var_name].add(pk)

    # Batch load models by type
    model_cache = {}
    for var_name, model_type in var_to_model_type.items():
        if var_name in pks_to_hydrate:
            pk_list = list(pks_to_hydrate[var_name])
            models = model_type.objects.in_bulk(pk_list)
            model_cache[var_name] = models

    # Hydrate results
    for result in pk_results:
        hydrated_result = {}
        for var_name, pk in result.items():
            if var_name in model_cache and pk in model_cache[var_name]:
                hydrated_result[var_name] = model_cache[var_name][pk]
            else:
                hydrated_result[var_name] = pk  # Keep as PK if can't hydrate
        yield hydrated_result
