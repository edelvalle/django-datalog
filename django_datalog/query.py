"""
Query system for djdatalog - handles querying facts with inference and optimization.
"""

import uuid
from collections.abc import Iterator
from dataclasses import fields
from typing import Any

from django.db.models import Q

from .facts import Fact
from .optimizer import optimize_query, time_fact_execution
from .rules import apply_targeted_rules, get_rules
from .variables import Var


def query(*fact_patterns: Fact, hydrate: bool = True) -> Iterator[dict[str, Any]]:
    """
    Query facts from the database and apply inference rules with intelligent optimization.

    This function automatically:
    1. Propagates constraints across variables with the same name
    2. Orders query execution by selectivity (most selective predicates first)
    3. Leverages database indexes and query optimization
    4. Records performance timing for optimization analysis

    Args:
        *fact_patterns: One or more fact patterns to match as a conjunction
        hydrate: If True (default), returns full model instances. If False, returns PKs only.

    Yields:
        Dictionary mapping variable names to their values (models or PKs based on hydrate)

    Example:
        # Query with automatic optimization and performance tracking
        results = query(
            ColleaguesOf(Var("emp1"), Var("emp2", where=Q(department="Engineering"))),
            WorksFor(Var("emp1"), Var("company", where=Q(is_active=True))),
            WorksFor(Var("emp2"), Var("company"))
        )
        # Constraints are automatically propagated:
        # - emp2 gets Q(department="Engineering") in all predicates
        # - company gets Q(is_active=True) in all predicates
        # - Query execution is ordered by selectivity
        # - Performance timing is automatically recorded
    """
    # Apply query optimization (constraint propagation + execution planning)
    optimized_patterns = optimize_query(list(fact_patterns))

    # Get the conjunction results using query-specific fact loading
    pk_results = _satisfy_conjunction_with_targeted_facts(optimized_patterns, {})

    if hydrate:
        # Collect all results first to batch hydration
        pk_results_list = list(pk_results)
        # Hydrate PKs to model instances (use original patterns for type info)
        yield from _hydrate_results(pk_results_list, list(fact_patterns))
    else:
        # Return PKs directly without hydration
        yield from pk_results


def _satisfy_conjunction_with_targeted_facts(conditions, bindings) -> Iterator[dict[str, Any]]:
    """Satisfy a conjunction using targeted fact loading - only load facts relevant to the query."""
    if not conditions:
        yield bindings
        return

    condition = conditions[0]
    remaining = conditions[1:]

    # Get facts relevant to this specific condition (stored + inferred)
    relevant_facts = _get_facts_for_pattern(condition)

    # Query against the targeted fact set
    for result in _query_against_facts(condition, relevant_facts):
        new_bindings = _unify_bindings(bindings, result)
        if new_bindings is not None:
            yield from _satisfy_conjunction_with_targeted_facts(remaining, new_bindings)


def _get_facts_for_pattern(pattern: Fact) -> list[Fact]:
    """Get facts relevant to a specific pattern - both stored and inferred."""
    # 1. Load stored facts that match this pattern type
    stored_facts = _load_stored_facts_for_pattern(pattern)

    # 2. Find rules that could generate facts of this pattern type
    relevant_rules = []
    for rule in get_rules():
        if type(rule.head) is type(pattern):
            relevant_rules.append(rule)

    # 3. If no rules can generate this fact type, just return stored facts
    if not relevant_rules:
        return stored_facts

    # 4. Apply targeted rule inference using hidden variables
    inferred_facts = _apply_rules_with_hidden_variables(relevant_rules, pattern)

    # 5. Combine stored and inferred facts
    return stored_facts + inferred_facts


def _load_stored_facts_for_pattern(pattern: Fact) -> list[Fact]:
    """Load stored facts from database that match a specific fact pattern."""
    try:
        fact_class = type(pattern)

        # Skip loading for inferred facts - they have no storage
        if fact_class._is_inferred:
            return []

        django_model = fact_class._django_model

        # Convert fact pattern to Django query
        query_params, q_objects = _fact_to_django_query(pattern)

        # Build the queryset with both filter params and Q objects
        queryset = django_model.objects.select_related("subject", "object").filter(**query_params)
        for q_obj in q_objects:
            queryset = queryset.filter(q_obj)

        # Convert Django instances back to facts
        facts = []
        for instance in queryset:
            fact = fact_class(subject=instance.subject, object=instance.object)
            facts.append(fact)

        return facts

    except (AttributeError, Exception):
        # If fact doesn't have a Django model or query fails, return empty
        return []


def _apply_rules_with_hidden_variables(rules, target_pattern: Fact) -> list[Fact]:
    """Apply rules using hidden variables to avoid bulk loading - reuse existing rule system."""
    # Create a targeted fact base by loading only facts needed for these specific rules
    targeted_facts = _build_targeted_fact_base_for_rules(rules, target_pattern)

    # Apply existing rule system to the targeted fact base
    inferred_facts = apply_targeted_rules(rules, targeted_facts)

    # Filter to only return facts of the target pattern type
    target_type = type(target_pattern)
    return [fact for fact in inferred_facts if type(fact) is target_type]


def _build_targeted_fact_base_for_rules(rules, target_pattern: Fact) -> list[Fact]:
    """Build a targeted fact base using hidden variables to avoid bulk loading."""
    targeted_facts = []

    # For each rule, analyze what facts it needs and load them with constraints
    for rule in rules:
        for condition in rule.body:
            # Create a version of the condition with hidden variables for unbound variables
            targeted_condition = _create_targeted_condition(condition, target_pattern)

            # Load facts for this targeted condition (uses existing optimized loading)
            condition_facts = _load_stored_facts_for_pattern(targeted_condition)
            targeted_facts.extend(condition_facts)

    # Remove duplicates
    seen = set()
    unique_facts = []
    for fact in targeted_facts:
        fact_key = (type(fact), fact.subject, fact.object)
        if fact_key not in seen:
            seen.add(fact_key)
            unique_facts.append(fact)

    return unique_facts


def _create_targeted_condition(condition: Fact, target_pattern: Fact) -> Fact:
    """Create a targeted version of a rule condition with hidden variables for unbound vars."""
    condition_class = type(condition)

    # For unbound variables in the condition, create hidden variables
    # This allows the existing system to handle them as unconstrained queries
    new_subject = condition.subject
    new_object = condition.object

    if isinstance(condition.subject, Var):
        # Check if this variable appears in the target pattern
        if not _variable_in_pattern(condition.subject.name, target_pattern):
            # Create hidden variable - unconstrained but with unique name
            hidden_name = f"hidden_{uuid.uuid4().hex[:8]}"
            new_subject = Var(hidden_name)

    if isinstance(condition.object, Var):
        # Check if this variable appears in the target pattern
        if not _variable_in_pattern(condition.object.name, target_pattern):
            # Create hidden variable - unconstrained but with unique name
            hidden_name = f"hidden_{uuid.uuid4().hex[:8]}"
            new_object = Var(hidden_name)

    return condition_class(subject=new_subject, object=new_object)


def _variable_in_pattern(var_name: str, pattern: Fact) -> bool:
    """Check if a variable name appears in a fact pattern."""
    if isinstance(pattern.subject, Var) and pattern.subject.name == var_name:
        return True
    if isinstance(pattern.object, Var) and pattern.object.name == var_name:
        return True
    return False


def _get_fact_field_types(fact_type):
    """Get the Django model types for subject and object fields of a fact type."""
    # Use the cached model types from the Fact class
    if hasattr(fact_type, "_model_types_cache"):
        cache = fact_type._model_types_cache
        return cache.get("subject"), cache.get("object")

    # Fallback: extract from type annotations

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


def _query_against_facts(pattern: Fact, facts: list[Fact]) -> Iterator[dict[str, Any]]:
    """Query a pattern against a set of in-memory facts with timing feedback."""
    with time_fact_execution(pattern):
        pattern_type = type(pattern)
        results = []

        for fact in facts:
            if type(fact) is pattern_type:
                # Try to unify the pattern with this fact
                substitution = _unify_fact_pattern(pattern, fact)
                if substitution is not None:
                    results.append(substitution)

        # Yield all results
        yield from results


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
    condition, *remaining = conditions

    # Generate all possible solutions for this condition
    for result in _query_single_fact(condition):
        # Try to unify with existing bindings
        new_bindings = _unify_bindings(bindings, result)
        if new_bindings is not None:
            # Recursively solve remaining conditions
            yield from _satisfy_conjunction(remaining, new_bindings)


def _query_single_fact(fact_pattern: Fact) -> Iterator[dict[str, Any]]:
    """Query a single fact pattern from the database with timing feedback."""
    with time_fact_execution(fact_pattern):
        fact_class = type(fact_pattern)

        # Handle inferred facts - they must be computed via rules
        if fact_class._is_inferred:
            # For inferred facts, get all facts (stored + inferred) and query against them
            relevant_facts = _get_facts_for_pattern(fact_pattern)
            yield from _query_against_facts(fact_pattern, relevant_facts)
            return

        # Handle stored facts - query database directly
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
